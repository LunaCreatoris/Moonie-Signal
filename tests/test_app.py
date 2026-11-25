"""The relay against a fake signal-cli-rest-api and a fake webhook receiver, both in-process (the `responses` library
mocks every HTTP call; WebSocket frames are fed straight to `Relay.on_frame`)."""

import base64
import json

import pytest
import responses
from responses import matchers

import app

API = "http://signal:8080"
HOOK = "http://receiver:8000/webhook/test-hook"
ACCOUNT = "+15555550100"
ALICE = "5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42"
ALICE_NUMBER = "+15555550101"
STRANGER = "0b6c2f1e-8d7a-4e3b-9c2d-1a2b3c4d5e6f"
GROUP_B64 = base64.b64encode(b"G" * 32).decode()
GROUP = "group:" + GROUP_B64
REST_GROUP = app.rest_group(GROUP)
TOKEN = "t" * 40


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    monkeypatch.setattr(app.WebhookRetry, "WAITS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(app.SendRetry, "WAITS", (0.0, 0.0))


@pytest.fixture
def relay():
    env = {
        "MOONIE_SIGNAL_ACCOUNT": ACCOUNT,
        "MOONIE_SIGNAL_WEBHOOK_URL": HOOK,
        "MOONIE_SIGNAL_WHITELIST_DIRECT": ALICE,
        "MOONIE_SIGNAL_ALLOWED_GROUPS": REST_GROUP,
        "MOONIE_SIGNAL_WHITELIST_GROUPS": f"{ALICE}, {ALICE_NUMBER}",
    }
    settings = app.Settings.from_env(env)
    return app.Relay(app.Settings(**{**settings.__dict__, "push_token": TOKEN}))


@pytest.fixture
def client(relay):
    return app.create_app(relay).test_client()


def frame(text="/ping", sender=ALICE, group=None, attachments=None, timestamp=1731500000123):
    data = {"timestamp": timestamp, "message": text}
    if group:
        data["groupInfo"] = {"groupId": group, "type": "DELIVER", "groupName": "Family"}
    if attachments:
        data["attachments"] = attachments
    envelope = {"sourceUuid": sender, "sourceNumber": ALICE_NUMBER, "sourceName": "Alice", "timestamp": timestamp}
    return json.dumps({"params": {"account": ACCOUNT, "envelope": {**envelope, "dataMessage": data}}})


def run(relay, text):
    relay.on_frame(text)
    while not relay.queue.empty():
        relay.handle(relay.queue.get())


def sends():
    return [json.loads(c.request.body) for c in responses.calls if c.request.url.endswith("/v2/send")]


def hooks():
    return [c.request for c in responses.calls if c.request.url == HOOK]


def members(*people):
    return {"id": REST_GROUP, "members": [{"number": ACCOUNT, "uuid": ""}, *people], "pending_invites": []}


# Receiving and replying


@responses.activate
def test_ping_goes_to_the_webhook_and_its_pong_comes_back(relay):
    responses.post(HOOK, json={"reply": "pong"})
    responses.post(f"{API}/v2/send", json={"timestamp": "1731500000999"}, status=201)
    run(relay, frame("/ping"))
    (hook,) = hooks()
    payload = json.loads(hook.body)
    assert payload["version"] == 1 and payload["text"] == "/ping"
    assert payload["id"] == f"{ALICE}:1731500000123"
    assert payload["chat"] == {"type": "direct", "id": ALICE}
    assert payload["sender"] == {"id": ALICE, "number": ALICE_NUMBER, "name": "Alice"}
    assert hook.headers["Idempotency-Key"] == payload["id"]
    assert "Authorization" not in hook.headers
    assert sends() == [{"number": ACCOUNT, "recipients": [ALICE], "message": "pong", "text_mode": "normal"}]


@responses.activate
def test_duplicate_frames_are_relayed_once(relay):
    responses.post(HOOK, json={})
    run(relay, frame())
    run(relay, frame())
    assert len(hooks()) == 1 and sends() == []


@responses.activate
def test_markdown_reply_goes_styled(relay):
    responses.post(HOOK, json={"reply": "# Done\n- **a** 2*3"})
    responses.post(f"{API}/v2/send", json={"timestamp": 1})
    run(relay, frame())
    (sent,) = sends()
    assert sent["text_mode"] == "styled"
    assert sent["message"] == "**Done**\n\n\u2022 **a** 2\\*3"


@responses.activate
def test_stranger_is_ignored_and_its_attachment_deleted(relay):
    responses.delete(f"{API}/v1/attachments/abc.jpg")
    run(relay, frame(sender=STRANGER, attachments=[{"id": "abc.jpg", "contentType": "image/jpeg"}]))
    assert hooks() == []
    assert responses.calls[-1].request.method == "DELETE"


@responses.activate
def test_attachments_are_forwarded_then_deleted(relay):
    responses.get(f"{API}/v1/attachments/abc.jpg", body=b"\xff\xd8")
    responses.delete(f"{API}/v1/attachments/abc.jpg")
    responses.post(HOOK, json={})
    run(relay, frame("", attachments=[{"id": "abc.jpg", "contentType": "image/jpeg", "filename": "a/b.jpg"}]))
    (attachment,) = json.loads(hooks()[0].body)["attachments"]
    assert attachment["data"] == "/9g=" and attachment["omitted"] is None and attachment["filename"] == "ab.jpg"
    assert responses.calls[-1].request.method == "DELETE"


@responses.activate
def test_group_with_only_whitelisted_members_is_served(relay):
    responses.get(f"{API}/v1/groups/%2B15555550100/{REST_GROUP}", json=members({"number": "", "uuid": ALICE}))
    responses.post(HOOK, json={"reply": "hi"})
    responses.post(f"{API}/v2/send", json={})
    run(relay, frame(group=GROUP_B64))
    assert json.loads(hooks()[0].body)["chat"] == {"type": "group", "id": GROUP, "name": "Family"}
    assert sends()[0]["recipients"] == [REST_GROUP]


@pytest.mark.parametrize(
    "answer",
    [members({"uuid": ALICE}, {"uuid": STRANGER}), {"error": "boom"}],
    ids=["stranger-in-group", "members-unreadable"],
)
@responses.activate
def test_group_with_a_stranger_or_unknown_members_is_silent(relay, answer):
    responses.get(f"{API}/v1/groups/%2B15555550100/{REST_GROUP}", json=answer)
    run(relay, frame(group=GROUP_B64))
    assert hooks() == [] and sends() == []


@responses.activate
def test_webhook_retried_on_503_then_lost_without_reply(relay):
    responses.post(HOOK, status=503)
    run(relay, frame())
    assert len(hooks()) == 4 and sends() == []


@responses.activate
def test_webhook_token_is_sent_when_set(relay):
    relay.s = app.Settings(**{**relay.s.__dict__, "webhook_token": "secret"})
    responses.post(HOOK, json={}, match=[matchers.header_matcher({"Authorization": "Bearer secret"})])
    run(relay, frame())
    assert len(hooks()) == 1


def test_invalid_whitelist_item_refuses_the_start():
    env = {"MOONIE_SIGNAL_ACCOUNT": ACCOUNT, "MOONIE_SIGNAL_WEBHOOK_URL": HOOK, "MOONIE_SIGNAL_WHITELIST_DIRECT": "x"}
    with pytest.raises(SystemExit, match="WHITELIST_DIRECT: item 1"):
        app.Settings.from_env(env)


def test_empty_optional_settings_take_their_defaults():
    # compose.yml passes every optional setting, empty when .env leaves it blank
    optional = (
        "WEBHOOK_TOKEN_FILE",
        "WEBHOOK_SECONDS",
        "TEXT_MODE",
        "MAX_ATTACHMENT_BYTES",
        "PUSH_TOKEN_FILE",
    )
    env = {"MOONIE_SIGNAL_ACCOUNT": ACCOUNT, "MOONIE_SIGNAL_WEBHOOK_URL": HOOK, "MOONIE_HTTP_MAX_BODY_BYTES": ""}
    env |= {f"MOONIE_SIGNAL_{name}": "" for name in optional}
    assert app.Settings.from_env(env) == app.Settings.from_env(
        {"MOONIE_SIGNAL_ACCOUNT": ACCOUNT, "MOONIE_SIGNAL_WEBHOOK_URL": HOOK}
    )
    settings = app.Settings.from_env(env)
    assert (settings.webhook_token, settings.webhook_seconds, settings.text_mode) == (None, 120, "markdown")
    assert (settings.max_attachment_bytes, settings.max_body_bytes) == (10 * app.MIB, 64 * app.MIB)


# Pushing


def push(client, body, key=None, token=TOKEN):
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    return client.post("/signal/send", data=json.dumps(body), headers=headers, content_type="application/json")


def test_push_needs_the_bearer_token(client):
    answer = push(client, {"to": [ALICE], "text": "x"}, token="wrong")
    assert answer.status_code == 401 and answer.json["error"] == "http.unauthorized"


def test_push_is_off_without_a_long_enough_token(relay):
    relay.s = app.Settings(**{**relay.s.__dict__, "push_token": "short"})
    answer = push(app.create_app(relay).test_client(), {"to": [ALICE], "text": "x"}, token="short")
    assert answer.status_code == 503 and answer.json["error"] == "http.auth_not_configured"


@pytest.mark.parametrize(
    ("body", "status", "error", "detail"),
    [
        ({"to": [ALICE], "text": "x", "extra": 1}, 400, "signal.invalid", "body"),
        ({"to": [], "text": "x"}, 400, "signal.invalid", "to"),
        ({"to": [ALICE, "nope"], "text": "x"}, 400, "signal.invalid", "to[1]"),
        ({"to": [ALICE, STRANGER], "text": "x"}, 403, "signal.not_allowed", "to[1]"),
        ({"to": [ALICE_NUMBER], "text": "x"}, 403, "signal.not_allowed", "to[0]"),
        ({"to": [ALICE], "text": "x" * 70_000}, 413, "signal.too_large", "text"),
        ({"to": [ALICE], "attachments": ["!!"]}, 400, "signal.invalid", "attachments[0]"),
    ],
)
def test_push_body_is_strict(client, body, status, error, detail):
    answer = push(client, body)
    assert (answer.status_code, answer.json) == (status, {"error": error, "detail": detail})


@responses.activate
def test_push_sends_to_each_recipient(client):
    responses.get(f"{API}/v1/groups/%2B15555550100/{REST_GROUP}", json=members({"uuid": ALICE}))
    responses.post(f"{API}/v2/send", json={"timestamp": "42"})
    data_uri = "data:application/pdf;filename=r.pdf;base64," + base64.b64encode(b"%PDF").decode()
    answer = push(client, {"to": [GROUP, ALICE], "text": "hi", "text_mode": "normal", "attachments": [data_uri]})
    assert answer.status_code == 200
    assert answer.json == {
        "ok": True,
        "results": [{"to": GROUP, "ok": True, "timestamp": 42}, {"to": ALICE, "ok": True, "timestamp": 42}],
    }
    assert [s["recipients"] for s in sends()] == [[REST_GROUP], [ALICE]]
    assert sends()[0]["base64_attachments"] == [data_uri]


@responses.activate
def test_push_reports_a_failed_recipient_with_502(client):
    responses.post(f"{API}/v2/send", status=429)
    answer = push(client, {"to": [ALICE], "text": "hi"})
    assert answer.status_code == 502
    assert answer.json == {
        "error": "signal.send_failed",
        "ok": False,
        "results": [{"to": ALICE, "ok": False, "error": "signal.rate_limited"}],
    }
    assert len(sends()) == 1


@responses.activate
def test_idempotency_key_replays_and_conflicts(client):
    responses.post(f"{API}/v2/send", json={"timestamp": 7})
    first = push(client, {"to": [ALICE], "text": "hi"}, key="report-1")
    again = push(client, {"to": [ALICE], "text": "hi"}, key="report-1")
    other = push(client, {"to": [ALICE], "text": "changed"}, key="report-1")
    assert first.status_code == again.status_code == 200 and again.json == first.json
    assert again.headers["Idempotency-Replayed"] == "true"
    assert (other.status_code, other.json["error"]) == (409, "signal.idempotency_conflict")
    assert len(sends()) == 1
    bad = push(client, {"to": [ALICE], "text": "hi"}, key="bad key!")
    assert (bad.status_code, bad.json["detail"]) == (400, "Idempotency-Key")


def test_health_answers(client):
    assert client.get("/health").status_code == 200
