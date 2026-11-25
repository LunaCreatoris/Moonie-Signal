# Copyright (C) 2026 LunaCreatoris
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Moonie Signal: a bridge between a Signal account (through signal-cli-rest-api) and an HTTP webhook.

- A background thread holds the WebSocket `/v1/receive/<account>` of signal-cli-rest-api (json-rpc mode).
- Each kept message from an allowed chat is POSTed to the webhook (payload version 1); the webhook's JSON answer
  (`reply`, `text_mode`, `attachments`) goes back to the same chat.
- `POST /signal/send` lets an HTTP client push messages to allowed people and groups (bearer token, optional
  Idempotency-Key).

Everything is in this one file on purpose. Logs never carry a number, a uuid, a name, a text or a token.
"""

import base64
import hmac
import json
import logging
import mimetypes
import os
import queue
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import requests
import websocket
from flask import Flask, Response, request
from markdown_it import MarkdownIt
from requests.adapters import HTTPAdapter
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.util.retry import Retry
from werkzeug.exceptions import RequestEntityTooLarge

VERSION = "4.0.0"
USER_AGENT = f"moonie-signal/{VERSION}"
log = logging.getLogger("moonie-signal")

MIB = 1 << 20
MAX_TEXT = 65_536
MAX_ATTACHMENTS = 16
MAX_RECIPIENTS = 16
TEXT_MODES = ("markdown", "styled", "normal")
PUSH_TOKEN_MIN = 32
QUEUE_MESSAGES = 256
SEEN_SIZE = 1024
IDEMPOTENCY_KEYS = 256
REST_SECONDS = 10
SEND_SECONDS = 60
HEALTH_GRACE_SECONDS = 120

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I | re.A)
NUMBER = re.compile(r"\+[1-9][0-9]{6,14}", re.A)
IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9._:-]{1,128}", re.A)
MIME = re.compile(r"[a-z0-9][a-z0-9.+-]{0,62}/[a-z0-9][a-z0-9.+-]{0,62}", re.A)
ATTACHMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", re.A)
CONTROLS = re.compile("[\x00-\x08\x0b-\x1f]")
SURROGATE = re.compile("[\ud800-\udfff]")
# Envelope kinds that are never relayed
IGNORED_KINDS = ("receiptMessage", "typingMessage", "callMessage", "storyMessage", "syncMessage", "editMessage")
OCTET_STREAM = "application/octet-stream"
RESERVED_STEMS = {"con", "prn", "aux", "nul"} | {f"{p}{n}" for p in ("com", "lpt") for n in "123456789"}


class Invalid(Exception):
    """A reply or push body refused: the field path (never its value), the HTTP status and the error code."""

    def __init__(self, path: str, status: int = 400, code: str = "signal.invalid") -> None:
        super().__init__(path)
        self.path, self.status, self.code = path, status, code


# --- Signal identities -------------------------------------------------------------------------------------------


def as_uuid(text: object) -> str | None:
    return text.strip().lower() if isinstance(text, str) and UUID.fullmatch(text.strip()) else None


def as_number(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    candidate = text.strip().replace(" ", "")
    return candidate if NUMBER.fullmatch(candidate) else None


def as_pni(text: object) -> str | None:
    if isinstance(text, str) and text.strip().startswith("PNI:") and UUID.fullmatch(text.strip()[4:]):
        return "PNI:" + text.strip()[4:].lower()
    return None


def _b64_32(text: str) -> bytes | None:
    """The 32 bytes of a group id written in standard or URL-safe base64, padding optional."""
    text = text.rstrip("=").replace("-", "+").replace("_", "/")
    try:
        raw = base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
    except ValueError:
        return None
    return raw if len(raw) == 32 else None


def as_group(text: object) -> str | None:
    """A group id in any accepted form (`group:<b64>`, raw base64, REST `group.<b64 of b64>`), canonical as
    `group:` + standard padded base64."""
    if not isinstance(text, str) or len(text.strip()) > 128:
        return None
    text = text.strip()
    prefix = text[:6].lower()
    if prefix == "group:":
        raw = _b64_32(text[6:])
    elif prefix == "group.":
        try:
            raw = _b64_32(base64.b64decode(text[6:] + "=" * (-len(text[6:]) % 4), validate=True).decode("ascii"))
        except ValueError:
            raw = None
    else:
        raw = _b64_32(text)
    return None if raw is None else "group:" + base64.b64encode(raw).decode("ascii")


def rest_group(canonical: str) -> str:
    """signal-cli-rest-api's form of a canonical group id: `group.` + base64 of the base64 text."""
    return "group." + base64.b64encode(canonical[6:].encode("ascii")).decode("ascii")


def as_person(text: object) -> str | None:
    return as_uuid(text) or as_number(text)


# --- Settings ----------------------------------------------------------------------------------------------------


def _read_secret(env: dict[str, str], name: str) -> str | None:
    """A token read from the file `<name>_FILE` points at; None when unset."""
    path = env.get(f"{name}_FILE", "").strip()
    return Path(path).read_text(encoding="utf-8").strip() if path else None


def _items(env: dict[str, str], name: str, parse) -> frozenset[str]:
    """A comma-separated list; one invalid item refuses the start (named by position, never by value)."""
    found = set()
    for index, item in enumerate(env.get(name, "").split(","), start=1):
        if not item.strip():
            continue
        value = parse(item)
        if value is None:
            raise SystemExit(f"{name}: item {index} is not valid")
        found.add(value)
    return frozenset(found)


@dataclass(frozen=True)
class Settings:
    account: str
    webhook_url: str
    api_url: str = "http://signal:8080"
    webhook_token: str | None = None
    webhook_seconds: int = 120
    whitelist_direct: frozenset[str] = frozenset()
    allowed_groups: frozenset[str] = frozenset()
    whitelist_groups: frozenset[str] = frozenset()
    text_mode: str = "markdown"
    max_attachment_bytes: int = 10 * MIB
    push_token: str | None = None
    max_body_bytes: int = 64 * MIB

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "Settings":
        """Read every `MOONIE_SIGNAL_*` setting; anything invalid stops the start with a message naming it."""
        p = "MOONIE_SIGNAL_"
        account = as_number(env.get(p + "ACCOUNT", ""))
        if account is None:
            raise SystemExit(p + "ACCOUNT: missing or not a number")
        webhook_url = env.get(p + "WEBHOOK_URL", "").strip()
        if not webhook_url.startswith(("http://", "https://")):
            raise SystemExit(p + "WEBHOOK_URL: missing or not http(s)")
        text_mode = env.get(p + "TEXT_MODE", "").strip() or "markdown"
        if text_mode not in TEXT_MODES:
            raise SystemExit(p + "TEXT_MODE: not markdown, styled or normal")

        def integer(name: str, default: int, low: int, high: int) -> int:
            raw = env.get(name, "").strip()
            value = int(raw) if raw.isdigit() else (default if not raw else -1)
            if not low <= value <= high:
                raise SystemExit(f"{name}: out of range {low}..{high}")
            return value

        return cls(
            account=account,
            webhook_url=webhook_url,
            api_url=(env.get(p + "API_URL", "").strip() or "http://signal:8080").rstrip("/"),
            webhook_token=_read_secret(env, p + "WEBHOOK_TOKEN") or None,
            webhook_seconds=integer(p + "WEBHOOK_SECONDS", 120, 5, 600),
            whitelist_direct=_items(env, p + "WHITELIST_DIRECT", as_person),
            allowed_groups=_items(env, p + "ALLOWED_GROUPS", as_group),
            whitelist_groups=_items(env, p + "WHITELIST_GROUPS", lambda t: as_person(t) or as_pni(t)),
            text_mode=text_mode,
            max_attachment_bytes=integer(p + "MAX_ATTACHMENT_BYTES", 10 * MIB, 0, 100 * MIB),
            push_token=_read_secret(env, p + "PUSH_TOKEN") or None,
            max_body_bytes=integer("MOONIE_HTTP_MAX_BODY_BYTES", 64 * MIB, 1024, 1024 * MIB),
        )


# --- HTTP sessions with retries ----------------------------------------------------------------------------------


class _Waits(Retry):
    """urllib3's Retry with a fixed list of waits instead of exponential backoff, and Retry-After capped at 60 s."""

    WAITS: tuple[float, ...] = ()

    def get_backoff_time(self) -> float:
        return self.WAITS[min(len(self.history), len(self.WAITS)) - 1] if self.history else 0.0

    def get_retry_after(self, response) -> float | None:
        after = super().get_retry_after(response)
        return None if after is None else min(after, 60.0)


class WebhookRetry(_Waits):
    WAITS = (2, 10, 30)


class SendRetry(_Waits):
    WAITS = (1, 3)


def session(retry_class: type[_Waits] | None = None, statuses: tuple[int, ...] = ()) -> requests.Session:
    """A requests session. With a retry class: retried only when the request never reached the server (connect
    errors) or on `statuses`; never after it was sent (read=0), so a workflow or a send never runs twice."""
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    if retry_class is not None:
        tries = len(retry_class.WAITS)
        retry = retry_class(
            total=tries, connect=tries, read=0, status=tries, other=0, redirect=0,
            status_forcelist=statuses, allowed_methods=None, raise_on_status=False, raise_on_redirect=False,
        )  # fmt: skip
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def never_sent(error: requests.ConnectionError) -> bool:
    """Whether the request never reached the server (no connection made), as opposed to sent and unanswered."""
    reason = getattr(error.args[0], "reason", error.args[0]) if error.args else None
    return isinstance(reason, NewConnectionError | ConnectTimeoutError)


# --- Text: cleaning and the Markdown mode ------------------------------------------------------------------------

_MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
_STYLED_MARKS = re.compile(r"([*~`|])")
_SPOILER = re.compile(r"\|\|(.+?)\|\|")
# A style mark the converter wrote (a literal one carries a backslash)
_UNESCAPED_MARK = re.compile(r"(?<!\\)[*~`|]")


def clean_text(text: str, *, strict: bool) -> str:
    """CRLF becomes LF, controls but TAB and LF are dropped; a reply over the cap is cut with an ellipsis, a push
    over it (strict) is refused with 413."""
    if SURROGATE.search(text):
        if strict:
            raise Invalid("text")
        text = SURROGATE.sub("\ufffd", text)
    text = CONTROLS.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    if len(text) > MAX_TEXT:
        if strict:
            raise Invalid("text", 413, "signal.too_large")
        text = text[: MAX_TEXT - 1] + "\u2026"
    return text


def _escape(text: str) -> str:
    """A backslash before every literal mark signal-cli's styled parser would read as a style."""
    return _STYLED_MARKS.sub(r"\\\1", text)


def _inline(children, item_start: bool) -> str:
    """One inline run in signal-cli's styled syntax."""
    out: list[str] = []
    links: list[tuple[str, int]] = []
    for tok in children:
        kind = tok.type
        if kind == "text":
            text = tok.content
            if item_start and text[:4] in ("[ ] ", "[x] ", "[X] "):
                text = ("\u2610 " if text[1] == " " else "\u2611 ") + text[4:]
            item_start = False
            parts = _SPOILER.split(text)
            # Odd parts are spoiler contents
            out.append("".join(f"||{_escape(p)}||" if i % 2 else _escape(p) for i, p in enumerate(parts)))
        elif kind in ("softbreak", "hardbreak"):
            out.append("\n")
        elif kind in ("strong_open", "strong_close"):
            out.append("**")
        elif kind in ("em_open", "em_close"):
            out.append("*")
        elif kind in ("s_open", "s_close"):
            out.append("~")
        elif kind == "code_inline":
            out.append("`" + _escape(tok.content) + "`")
        elif kind == "link_open":
            links.append((tok.attrGet("href") or "", len(out)))
        elif kind == "link_close" and links:
            href, start = links.pop()
            label = "".join(out[start:])
            del out[start:]
            out.append(_escape(href) if label == _escape(href) else f"{label} ({_escape(href)})")
        elif kind == "image":
            out.append(f"{_escape(tok.content)} ({_escape(tok.attrGet('src') or '')})")
        else:
            out.append(_escape(tok.content))
    return "".join(out)


def _table(rows: list[list[str]]) -> list[str]:
    """A table as monospace lines, cells trimmed and lined up."""
    widths = [max(len(row[i]) if i < len(row) else 0 for row in rows) for i in range(max(map(len, rows)))]
    return ["`" + " | ".join(c.ljust(w) for c, w in zip(row, widths, strict=False)).rstrip() + "`" for row in rows]


def markdown_to_styled(text: str) -> str:
    """Standard Markdown in signal-cli's styled syntax: bold headings, `•` bullets, monospace code and tables,
    `text (url)` links, `||spoiler||` kept."""
    lines: list[str] = []
    lists: list[str] = []
    rows: list[list[str]] | None = None
    current = ""
    item_start = False
    for tok in _MD.parse(text):
        kind = tok.type
        if kind in ("bullet_list_open", "ordered_list_open"):
            lists.append(kind)
        elif kind in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
            if not lists:
                lines.append("")
        elif kind == "list_item_open":
            bullet = "\u2022" if lists[-1] == "bullet_list_open" else f"{tok.info}{tok.markup}"
            current = "  " * (len(lists) - 1) + bullet + " "
            item_start = True
        elif kind == "heading_open":
            current = "**"
        elif kind == "heading_close":
            lines += [current + "**", ""]
            current = ""
        elif kind == "inline" and rows is not None:
            rows[-1].append(_inline(tok.children or [], False).replace("`", "'").strip())
        elif kind == "inline":
            current += _inline(tok.children or [], item_start)
            item_start = False
        elif kind == "paragraph_close":
            lines.append(current)
            current = ""
            if not tok.hidden:
                lines.append("")
        elif kind in ("fence", "code_block"):
            lines += [f"`{_escape(line)}`" if line else "" for line in tok.content.rstrip("\n").split("\n")] + [""]
        elif kind == "table_open":
            rows = []
        elif kind == "tr_open" and rows is not None:
            rows.append([])
        elif kind == "table_close" and rows is not None:
            lines += _table(rows) + [""]
            rows = None
        elif kind == "hr":
            lines += ["---", ""]
        elif kind == "html_block":
            lines += [_escape(tok.content.rstrip("\n")), ""]
    return "\n".join(lines).strip("\n")


def wire_text(text: str, mode: str) -> tuple[str, str]:
    """The text and the mode /v2/send gets (`styled` or `normal`, never `markdown`). A Markdown text with no style
    goes untouched as `normal`; a conversion error sends the raw text as `normal`."""
    if mode != "markdown" or not text:
        return text, mode if text else "normal"
    try:
        styled = markdown_to_styled(text)
    except Exception:
        log.warning("markdown conversion failed")
        return text, "normal"
    if not _UNESCAPED_MARK.search(styled):
        # No style at all: the raw text goes as written
        return text, "normal"
    return styled, "styled"


# --- Attachments -------------------------------------------------------------------------------------------------


def mime(value: object) -> str:
    if not isinstance(value, str):
        return OCTET_STREAM
    candidate = value.split(";", 1)[0].strip().lower()
    return candidate if MIME.fullmatch(candidate) else OCTET_STREAM


def clean_filename(value: str, content_type: str = OCTET_STREAM) -> str:
    """A filename safe on every system: letters, digits and `._-()+ ` only, 128 UTF-8 bytes at most, a Windows
    reserved stem gets `_`, an empty one becomes `file` plus the type's extension."""
    text = unicodedata.normalize("NFC", SURROGATE.sub("", value))
    text = re.sub(" {2,}", " ", "".join(c for c in text if c.isalnum() or c in "._-()+ ")).strip(". ")
    text = text.encode("utf-8")[:128].decode("utf-8", "ignore").strip(". ")
    if not text:
        return "file" + (mimetypes.guess_extension(content_type) or "")
    stem, dot, rest = text.partition(".")
    return stem + "_" + dot + rest if stem.strip().lower() in RESERVED_STEMS else text


@dataclass(frozen=True)
class Attachment:
    content_type: str
    filename: str
    data: bytes

    def data_uri(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.content_type};filename={self.filename};base64,{encoded}"


def _decode(text: str, path: str, budget: int) -> bytes:
    if not text or len(text) % 4 or not re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", text):
        raise Invalid(path)
    if len(text) // 4 * 3 - text.count("=") > budget:
        raise Invalid(path, 413, "signal.too_large")
    data = base64.b64decode(text, validate=True)
    if not data:
        raise Invalid(path)
    return data


def parse_attachments(value: object, budget: int, *, strict: bool) -> list[Attachment]:
    """A data URI, a bare base64 string or `{data, content_type?, filename?}`; 16 at most, `budget` bytes in all."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_ATTACHMENTS:
        raise Invalid("attachments")
    found = []
    for index, item in enumerate(value):
        path = f"attachments[{index}]"
        if isinstance(item, str) and item[:5].lower() == "data:":
            head, mark, body = item.partition(";base64,")
            if not mark:
                raise Invalid(path)
            params = head[5:].split(";")
            kind = mime(params[0])
            name = next((p.split("=", 1)[1] for p in params[1:] if p.lower().startswith("filename=")), "")
            attachment = Attachment(kind, clean_filename(name, kind), _decode(body, path, budget))
        elif isinstance(item, str):
            attachment = Attachment(OCTET_STREAM, clean_filename(""), _decode(item, path, budget))
        elif isinstance(item, dict):
            if strict and not set(item) <= {"data", "content_type", "filename"}:
                raise Invalid(path)
            for key in ("content_type", "filename"):
                if item.get(key) is not None and not isinstance(item[key], str):
                    raise Invalid(f"{path}.{key}")
            if not isinstance(item.get("data"), str):
                raise Invalid(f"{path}.data")
            kind = mime(item.get("content_type"))
            data = _decode(item["data"], f"{path}.data", budget)
            attachment = Attachment(kind, clean_filename(item.get("filename") or "", kind), data)
        else:
            raise Invalid(path)
        budget -= len(attachment.data)
        found.append(attachment)
    return found


@dataclass
class Outgoing:
    text: str
    mode: str
    attachments: list[Attachment] = field(default_factory=list)


def parse_outgoing(body: dict, text_key: str, default_mode: str, budget: int, *, strict: bool) -> Outgoing:
    text = body.get(text_key)
    if text is not None and not isinstance(text, str):
        raise Invalid(text_key)
    mode = body.get("text_mode", default_mode)
    if mode is None:
        mode = default_mode
    if mode not in TEXT_MODES:
        raise Invalid("text_mode")
    attachments = parse_attachments(body.get("attachments"), budget, strict=strict)
    wire, wire_mode = wire_text(clean_text(text or "", strict=strict), mode)
    return Outgoing(wire, wire_mode, attachments)


# --- Received frames ---------------------------------------------------------------------------------------------


def _name(value: object) -> str | None:
    return SURROGATE.sub("\ufffd", value) if isinstance(value, str) and value else None


def _count(value: object) -> int | None:
    ok = isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**63
    return value if ok else None


def parse_frame(frame: object, account: str) -> dict | None:
    """One WebSocket frame: the normalized message, or None for anything not relayed (receipts, typing, syncs,
    edits, reactions, stories, group updates, own or other-account messages, empty or malformed frames)."""
    holder = frame if isinstance(frame, dict) and "envelope" in frame else None
    for wrapper in ("params", "result"):
        inner = frame.get(wrapper) if isinstance(frame, dict) else None
        if holder is None and isinstance(inner, dict) and "envelope" in inner:
            holder = inner
    if holder is None or as_number(holder.get("account")) != account:
        return None
    env = holder["envelope"]
    if not isinstance(env, dict) or any(env.get(k) is not None for k in IGNORED_KINDS):
        return None
    data = env.get("dataMessage")
    sender = as_uuid(env.get("sourceUuid"))
    timestamp = _count(env.get("timestamp")) or _count(data.get("timestamp") if isinstance(data, dict) else None)
    if not isinstance(data, dict) or sender is None or not timestamp:
        return None
    number = as_number(env.get("sourceNumber")) or as_number(env.get("source"))
    if number == account or data.get("viewOnce") is True:
        return None
    if any(data.get(k) is not None for k in ("reaction", "remoteDelete", "storyContext")):
        return None
    info = data.get("groupInfo")
    if info is None:
        chat = {"type": "direct", "id": sender}
    elif isinstance(info, dict) and info.get("type", "DELIVER") in ("DELIVER", None):
        group = as_group(info.get("groupId"))
        if group is None:
            return None
        chat = {"type": "group", "id": group, "name": _name(info.get("groupName"))}
    else:
        return None
    text = data.get("message") or ""
    attachments = data.get("attachments") or []
    if not isinstance(text, str) or not isinstance(attachments, list) or not (text or attachments):
        return None
    mentions = []
    for item in data.get("mentions") or []:
        if isinstance(item, dict) and as_uuid(item.get("uuid")):
            mentions.append((_count(item.get("start")), as_uuid(item.get("uuid")), _name(item.get("name"))))
    # Each U+FFFC at a mention's start (UTF-16 units, as Signal counts) becomes @name, or @ and 8 uuid characters
    by_start = {start: (uid, name) for start, uid, name in reversed(mentions) if start is not None}
    out, offset = [], 0
    for ch in SURROGATE.sub("\ufffd", text):
        hit = by_start.get(offset) if ch == "\ufffc" else None
        out.append("@" + (hit[1] or hit[0][:8]) if hit else ch)
        offset += 2 if ord(ch) > 0xFFFF else 1
    quote_ = data.get("quote")
    metas = []
    for item in attachments:
        item = item if isinstance(item, dict) else {}
        raw_id = item.get("id")
        kind = mime(item.get("contentType"))
        usable = isinstance(raw_id, str) and ATTACHMENT_ID.fullmatch(raw_id) and ".." not in raw_id
        metas.append({
            "id": raw_id if usable else None,
            "content_type": kind,
            "filename": clean_filename(item["filename"], kind) if _name(item.get("filename")) else None,
            "size": _count(item.get("size")),
            "width": _count(item.get("width")),
            "height": _count(item.get("height")),
            "caption": _name(item.get("caption")),
        })  # fmt: skip
    return {
        "version": 1,
        "id": f"{sender}:{timestamp}",
        "account": account,
        "timestamp": timestamp,
        "chat": chat,
        "sender": {"id": sender, "number": number, "name": _name(env.get("sourceName"))},
        "text": "".join(out),
        "mentions": [{"id": uid, "name": name} for _, uid, name in mentions],
        "quote": None
        if not isinstance(quote_, dict)
        else {
            "timestamp": _count(quote_.get("id")) or None,
            "author_id": as_uuid(quote_.get("authorUuid")),
            "text": _name(quote_.get("text")) if isinstance(quote_.get("text"), str) else None,
        },
        "attachments": metas,
        "envelope": env,
    }


# --- The relay ---------------------------------------------------------------------------------------------------


class Relay:
    """Receive, filter, forward to the webhook, reply; and push. One worker thread handles messages in order."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.rest = session()
        self.sender = session(SendRetry, (503,))
        self.webhook = session(WebhookRetry, (429, 503))
        self.queue: queue.Queue[dict] = queue.Queue(QUEUE_MESSAGES)
        self.seen: OrderedDict[str, None] = OrderedDict()
        self.keys: OrderedDict[str, tuple[bytes, int | None, dict | None]] = OrderedDict()
        self.keys_lock = threading.Lock()
        self.pushes = threading.BoundedSemaphore(3)
        self.connected = False
        self.down_since = time.monotonic()
        self.count = 0

    # Receiving

    def on_frame(self, text: str) -> None:
        """One WebSocket text frame: parse, dedupe, queue (oldest dropped when full)."""
        try:
            message = parse_frame(json.loads(text), self.s.account)
        except ValueError:
            return
        if message is None or message["id"] in self.seen:
            return
        self.seen[message["id"]] = None
        if len(self.seen) > SEEN_SIZE:
            self.seen.popitem(last=False)
        while True:
            try:
                self.queue.put_nowait(message)
                return
            except queue.Full:
                try:
                    self.queue.get_nowait()
                    log.warning("queue full: dropped 1 message")
                except queue.Empty:
                    pass

    def receive_forever(self) -> None:
        """Hold the WebSocket, reconnecting every 5 seconds when it drops."""
        url = self.s.api_url.replace("http", "ws", 1) + "/v1/receive/" + quote(self.s.account, safe="")

        def opened(_ws) -> None:
            self.connected = True
            log.info("websocket connected")

        def closed(_ws, *_args) -> None:
            if self.connected:
                self.down_since = time.monotonic()
            self.connected = False
            log.info("websocket closed")

        app = websocket.WebSocketApp(
            url, header={"User-Agent": USER_AGENT}, on_open=opened, on_close=closed,
            on_message=lambda _ws, text: self.on_frame(text),
            on_error=lambda _ws, error: log.info("websocket error: %s", type(error).__name__),
        )  # fmt: skip
        while True:
            app.run_forever(ping_interval=30, ping_timeout=10, reconnect=5)
            time.sleep(5)

    def deliver_forever(self) -> None:
        while True:
            message = self.queue.get()
            try:
                self.handle(message)
            except Exception:
                log.exception("message handling failed")

    # Policy

    def members_allowed(self, group: str, sender: dict | None) -> bool | None:
        """Whether every member and pending invite of `group` (and the sender) is in WHITELIST_GROUPS; None when the
        member list cannot be read. The account itself is left out."""
        allowed = self.s.whitelist_groups
        if not allowed:
            return False
        url = f"{self.s.api_url}/v1/groups/{quote(self.s.account, safe='')}/{quote(rest_group(group), safe='=')}"
        try:
            answer = self.rest.get(url, params={"expand": "true"}, timeout=REST_SECONDS)
            value = answer.json() if answer.status_code == 200 else None
        except (requests.RequestException, ValueError):
            value = None
        if not isinstance(value, dict) or not isinstance(value.get("members"), list):
            return None
        entries = []
        for entry in value["members"] + (value.get("pending_invites") or []):
            if isinstance(entry, str):
                entry = {"number": entry} if as_number(entry) else {"uuid": entry}
            if not isinstance(entry, dict):
                return None
            number = as_number(entry.get("number") or "")
            uid = as_uuid(entry.get("uuid") or "") or as_pni(entry.get("uuid") or "")
            if number is None and uid is None:
                return None
            entries.append((number, uid))
        own = {uid for number, uid in entries if number == self.s.account}
        for number, uid in entries:
            if number == self.s.account or (uid is not None and uid in own):
                continue
            if number not in allowed and uid not in allowed:
                return False
        return sender is None or sender["id"] in allowed or sender["number"] in allowed

    def chat_allowed(self, message: dict) -> str | None:
        """None when the message may go to the webhook, else the reason it is dropped."""
        chat, sender = message["chat"], message["sender"]
        if chat["type"] == "direct":
            ok = sender["id"] in self.s.whitelist_direct or sender["number"] in self.s.whitelist_direct
            return None if ok else "not_allowed"
        if chat["id"] not in self.s.allowed_groups:
            return "not_allowed"
        members = self.members_allowed(chat["id"], sender)
        return None if members else ("members_unknown" if members is None else "members_not_allowed")

    # Handling one message

    def handle(self, message: dict) -> None:
        started = time.monotonic()
        ids = [a["id"] for a in message["attachments"] if a["id"]]
        try:
            refused = self.chat_allowed(message)
            if refused == "not_allowed":
                log.info("refused 1 message from a chat not allowed (%s)", message["chat"]["type"])
                return
            self.count += 1
            if refused:
                outcome = f"lost:{refused}"
            else:
                outcome = self.forward(message)
            log.info(
                "message %d: %s, %d attachments, %s, %d ms", self.count, message["chat"]["type"],
                len(ids), outcome, (time.monotonic() - started) * 1000,
            )  # fmt: skip
        finally:
            for attachment_id in ids:
                try:
                    self.rest.delete(f"{self.s.api_url}/v1/attachments/{quote(attachment_id, safe='')}", timeout=10)
                except requests.RequestException:
                    pass

    def fetch_attachments(self, message: dict) -> None:
        """Fill `data` and `omitted` for each attachment, in order, within MAX_ATTACHMENT_BYTES."""
        left = self.s.max_attachment_bytes
        for meta in message["attachments"]:
            attachment_id = meta.pop("id")
            meta["data"], meta["omitted"] = None, "unavailable"
            if attachment_id is None:
                continue
            if meta["size"] is not None and meta["size"] > left:
                meta["omitted"] = "too_large"
                continue
            try:
                url = f"{self.s.api_url}/v1/attachments/{quote(attachment_id, safe='')}"
                answer = self.rest.get(url, timeout=SEND_SECONDS)
            except requests.RequestException:
                continue
            if answer.status_code != 200:
                continue
            if len(answer.content) > left:
                meta["omitted"] = "too_large"
                continue
            left -= len(answer.content)
            meta["data"], meta["omitted"] = base64.b64encode(answer.content).decode("ascii"), None

    def forward(self, message: dict) -> str:
        """POST to the webhook, then send its reply to the chat. Returns the outcome for the log line."""
        self.fetch_attachments(message)
        headers = {"Content-Type": "application/json", "Idempotency-Key": message["id"]}
        if self.s.webhook_token:
            headers["Authorization"] = "Bearer " + self.s.webhook_token
        try:
            answer = self.webhook.post(
                self.s.webhook_url, data=json.dumps(message).encode("ascii"), headers=headers,
                timeout=(REST_SECONDS, self.s.webhook_seconds), allow_redirects=False,
            )  # fmt: skip
        except requests.ConnectionError as error:
            code = "unreachable" if never_sent(error) else "timeout"
            log.warning("webhook failed: %s", code)
            return f"lost:{code}"
        except requests.RequestException:
            log.warning("webhook failed: timeout")
            return "lost:timeout"
        if not 200 <= answer.status_code < 300:
            log.warning("webhook failed: http_%d", answer.status_code)
            return f"lost:http_{answer.status_code}"
        try:
            body = answer.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            log.warning("invalid reply: body")
            return "silence"
        try:
            reply = parse_outgoing(body, "reply", self.s.text_mode, self.s.max_attachment_bytes, strict=False)
        except Invalid as error:
            log.warning("invalid reply: %s", error.path)
            return "lost:invalid_reply"
        if not reply.text and not reply.attachments:
            return "silence"
        chat = message["chat"]
        recipient = rest_group(chat["id"]) if chat["type"] == "group" else chat["id"]
        code, _ = self.send(recipient, reply)
        return "replied" if code is None else f"lost:send_{code}"

    # Sending

    def send(self, recipient: str, out: Outgoing) -> tuple[str | None, int | None]:
        """One /v2/send: (None, timestamp) when sent, else (code, None). Retried on connect errors and 503 only."""
        body: dict = {"number": self.s.account, "recipients": [recipient], "message": out.text, "text_mode": out.mode}
        if out.attachments:
            body["base64_attachments"] = [a.data_uri() for a in out.attachments]
        try:
            answer = self.sender.post(f"{self.s.api_url}/v2/send", json=body, timeout=(REST_SECONDS, SEND_SECONDS))
        except requests.ConnectionError as error:
            code = "unavailable" if never_sent(error) else "timeout"
        except requests.RequestException:
            code = "timeout"
        else:
            if answer.status_code in (200, 201):
                try:
                    stamp = answer.json()
                    stamp = (stamp[0] if isinstance(stamp, list) and stamp else stamp).get("timestamp")
                    stamp = int(stamp) if str(stamp).isdigit() and len(str(stamp)) <= 19 else None
                except (ValueError, AttributeError):
                    stamp = None
                return None, stamp
            code = {503: "unavailable", 429: "rate_limited"}.get(answer.status_code)
            code = code or ("refused" if 400 <= answer.status_code < 500 else "timeout")
        log.warning("send failed: %s", code)
        return code, None

    # Pushing

    def push(self, raw: bytes, key: str | None) -> tuple[int, dict, dict]:
        """`POST /signal/send` once authenticated: (status, body, extra headers)."""
        if key is not None:
            with self.keys_lock:
                kept = self.keys.get(key)
                if kept is not None:
                    if kept[0] != raw:
                        return 409, {"error": "signal.idempotency_conflict", "detail": "Idempotency-Key"}, {}
                    if kept[1] is None:
                        return 409, {"error": "signal.in_progress", "detail": "Idempotency-Key"}, {}
                    return kept[1], kept[2], {"Idempotency-Replayed": "true"}
                self.keys[key] = (raw, None, None)
        status, body = 500, {"error": "signal.internal", "detail": None}
        try:
            status, body = self._push(raw)
        finally:
            if key is not None:
                with self.keys_lock:
                    # Only pushes that went out (200 or 502) keep their key
                    if status in (200, 502):
                        self.keys[key] = (raw, status, body)
                        while len(self.keys) > IDEMPOTENCY_KEYS:
                            oldest = next(k for k, v in self.keys.items() if v[1] is not None)
                            del self.keys[oldest]
                    else:
                        self.keys.pop(key, None)
        return status, body, {}

    def _push(self, raw: bytes) -> tuple[int, dict]:
        try:
            body = json.loads(raw)
        except ValueError:
            return 400, {"error": "http.bad_json", "detail": "the body is not strict JSON"}
        try:
            if not isinstance(body, dict) or not set(body) <= {"to", "text", "text_mode", "attachments"}:
                raise Invalid("body")
            targets = body.get("to")
            if not isinstance(targets, list) or not 1 <= len(targets) <= MAX_RECIPIENTS:
                raise Invalid("to")
            recipients: dict[str, str] = {}
            for index, target in enumerate(targets):
                canonical = as_person(target) or as_group(target)
                if canonical is None:
                    raise Invalid(f"to[{index}]")
                allowed = self.s.allowed_groups if canonical.startswith("group:") else self.s.whitelist_direct
                if canonical not in allowed:
                    raise Invalid(f"to[{index}]", 403, "signal.not_allowed")
                recipients.setdefault(canonical, target)
            if body.get("text") is None and body.get("attachments") is None:
                raise Invalid("text")
            out = parse_outgoing(body, "text", self.s.text_mode, self.s.max_attachment_bytes, strict=True)
            if len(out.text) > MAX_TEXT:
                raise Invalid("text", 413, "signal.too_large")
            if not out.text and not out.attachments:
                raise Invalid("text")
        except Invalid as error:
            return error.status, {"error": error.code, "detail": error.path}
        results = []
        for canonical, given in recipients.items():
            code: str | None = None
            stamp = None
            if canonical.startswith("group:"):
                members = self.members_allowed(canonical, None)
                code = None if members else ("backend_unavailable" if members is None else "not_allowed")
            if code is None:
                code, stamp = self.send(rest_group(canonical) if canonical.startswith("group:") else canonical, out)
                code = {"unavailable": "backend_unavailable"}.get(code, code)
            ok = code is None
            results.append({"to": given, "ok": True, "timestamp": stamp} if ok else
                           {"to": given, "ok": False, "error": f"signal.{code}"})  # fmt: skip
        sent = sum(r["ok"] for r in results)
        log.info("push: %d recipients, %d sent, %d failed", len(results), sent, len(results) - sent)
        if sent == len(results):
            return 200, {"ok": True, "results": results}
        return 502, {"error": "signal.send_failed", "ok": False, "results": results}


# --- HTTP --------------------------------------------------------------------------------------------------------


def create_app(relay: Relay) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = relay.s.max_body_bytes
    push_token = relay.s.push_token
    if not push_token:
        log.warning("push token not set: pushing is off")
    elif len(push_token) < PUSH_TOKEN_MIN:
        log.warning("push token shorter than 32 characters: pushing is off")

    def answer(status: int, body: dict, headers: dict | None = None) -> Response:
        return Response(json.dumps(body), status, headers or {}, mimetype="application/json")

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error) -> Response:
        return answer(413, {"error": "http.body_too_large", "detail": "the body is larger than this route takes"})

    @app.get("/health")
    def health() -> Response:
        ok = relay.connected or time.monotonic() - relay.down_since < HEALTH_GRACE_SECONDS
        return answer(200 if ok else 503, {"ok": ok, "websocket": relay.connected, "queued": relay.queue.qsize()})

    @app.post("/signal/send")
    def send() -> Response:
        if not push_token or len(push_token) < PUSH_TOKEN_MIN:
            return answer(503, {"error": "http.auth_not_configured", "detail": "no push token"})
        given = request.headers.get("Authorization", "")
        if not given.startswith("Bearer ") or not hmac.compare_digest(given[7:].encode(), push_token.encode()):
            body = {"error": "http.unauthorized", "detail": "a valid bearer token is required"}
            return answer(401, body, {"WWW-Authenticate": "Bearer"})
        if request.mimetype != "application/json":
            return answer(415, {"error": "http.unsupported_media_type", "detail": "this route takes application/json"})
        key = request.headers.get("Idempotency-Key")
        if key is not None and not IDEMPOTENCY_KEY.fullmatch(key):
            return answer(400, {"error": "signal.invalid", "detail": "Idempotency-Key"})
        if not relay.pushes.acquire(timeout=1.0):
            return answer(503, {"error": "http.busy", "detail": "too many pushes at once"}, {"Retry-After": "1"})
        try:
            return answer(*relay.push(request.get_data(), key))
        finally:
            relay.pushes.release()

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("websocket").setLevel(logging.CRITICAL)
    relay = Relay(Settings.from_env(dict(os.environ)))
    if relay.s.allowed_groups and not relay.s.whitelist_groups:
        log.warning("whitelist_groups empty: no allowed group is served")
    threading.Thread(target=relay.receive_forever, name="receive", daemon=True).start()
    threading.Thread(target=relay.deliver_forever, name="deliver", daemon=True).start()
    from waitress import serve

    serve(create_app(relay), host="0.0.0.0", port=int(os.environ.get("MOONIE_HTTP_PORT", "8080")), threads=4)


if __name__ == "__main__":
    main()
