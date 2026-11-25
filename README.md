# Moonie Signal

Moonie Signal sits in front of signal-cli and translates it. Instead of its raw API, you get a simple route to send
messages, and every message received reaches your webhook (n8n, for example) in a stable format.

It talks to signal-cli through
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) in `json-rpc` mode. One Python file
(`app.py`): Flask for the push route, `websocket-client` for receiving, `requests` with urllib3's retries for the
outgoing calls, `markdown-it-py` for the Markdown text mode.

**Requirements**: a host with Docker and Docker Compose, a service that receives the webhook (an HTTP endpoint that
accepts a JSON `POST` and answers in JSON), and a phone number for the bot's Signal account.

**Guide**: a step-by-step user guide, from the first start to troubleshooting, is in
[English](wiki/guide/en/index.md) and in [French](wiki/guide/fr/index.md). This README is the technical reference.

## What it does

- **Receives** every message on the WebSocket `/v1/receive/<account>`. Receipts, typing, calls, stories, syncs, edits,
  reactions, deletions, view-once and group updates are ignored; a message seen twice is relayed once.
- **Filters**: a direct message goes through when its sender's uuid or number is in `WHITELIST_DIRECT`. A group
  message goes through when the group is in `ALLOWED_GROUPS` **and** every member, every pending invite and the sender
  are in `WHITELIST_GROUPS` (read from `/v1/groups/<account>/<group>?expand=true` for each message; an unreadable list
  refuses the group). Refusals are silent.
- **Forwards** each allowed message to the webhook as a `POST` (payload version 1: `version`, `id`, `account`,
  `timestamp`, `chat`, `sender`, `text`, `mentions`, `quote`, `attachments` with base64 `data`, raw `envelope`), with
  `Idempotency-Key: <id>` and, when set, `Authorization: Bearer <webhook token>`. Retried only when the webhook was
  never reached or answered 429/503 (waits 2, 10, 30 s, `Retry-After` honoured up to 60 s); never after a timeout.
  Messages are handled one at a time, in order; received attachments are deleted from signal-cli afterwards.
- **Replies**: the webhook's JSON answer `{"reply", "text_mode", "attachments"}` goes back to the same chat. `{}` or
  no answer body means silence. Attachments are data URIs, bare base64 or `{data, content_type, filename}`.
- **Pushes**: `POST /signal/send` with `Authorization: Bearer <push token>` and
  `{"to": [...], "text": "...", "text_mode": "...", "attachments": [...]}` sends to allowed people and groups
  (`to` takes uuids, numbers and group ids; groups also pass the member check). Answers `200 {"ok": true, "results"}`,
  `502 signal.send_failed` with per-recipient results, or `{"error", "detail"}` (400, 401, 403, 409, 413, 415, 503).
  An optional `Idempotency-Key` replays the first answer for the same body (`Idempotency-Replayed: true`), and gives
  409 for another body or while the first push runs. At most 3 pushes run at once.
- **Text modes**: `markdown` (default; converted to Signal styles, a text with no style goes as written), `styled`
  (signal-cli's own `**bold**`, `*italic*`, `~strike~`, `` `mono` ``, `||spoiler||`) or `normal`.
- **Health**: `GET /health` answers 503 once the WebSocket has been down for 120 seconds; the image's health check
  calls it.

Logs carry counts and outcome codes only: never a number, a uuid, a name, a text or a token.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `MOONIE_SIGNAL_ACCOUNT` | required | The registered number, `+` and digits |
| `MOONIE_SIGNAL_WEBHOOK_URL` | required | The webhook, such as `http://receiver:8000/<your-webhook-path>` |
| `MOONIE_SIGNAL_API_URL` | `http://signal:8080` | signal-cli-rest-api |
| `MOONIE_SIGNAL_WHITELIST_DIRECT` | empty | Who may write in direct (uuids or numbers, comma-separated) |
| `MOONIE_SIGNAL_ALLOWED_GROUPS` | empty | Groups served (`group:<id>`, raw base64 or REST `group.<id>`) |
| `MOONIE_SIGNAL_WHITELIST_GROUPS` | empty | Who may be in an allowed group (uuids, numbers, `PNI:<uuid>`) |
| `MOONIE_SIGNAL_PUSH_TOKEN_FILE` | unset | File holding the push token (32+ characters); unset turns pushing off (503) |
| `MOONIE_SIGNAL_WEBHOOK_TOKEN_FILE` | unset | File holding the webhook's bearer token (see below) |
| `MOONIE_SIGNAL_WEBHOOK_SECONDS` | `120` | Time the webhook has to answer (5 to 600) |
| `MOONIE_SIGNAL_TEXT_MODE` | `markdown` | Default mode of replies and pushes |
| `MOONIE_SIGNAL_MAX_ATTACHMENT_BYTES` | `10485760` | Attachment bytes per message, both directions |
| `MOONIE_HTTP_PORT` | `8080` | Port of the push route (`compose.yml` keeps 8080, the port push clients call) |
| `MOONIE_HTTP_MAX_BODY_BYTES` | `67108864` | Largest push body |

`compose.yml` passes every setting above from `.env`; an empty value means the default. It sets the API URL itself
and does not pass `MOONIE_HTTP_PORT`. To send a bearer token to the webhook, write it to `secrets/webhook_token`
(owned and readable by uid 10001 only, like the push token), add it in a `compose.override.yml`:

```yaml
services:
  moonie:
    secrets: [push_token, webhook_token]
secrets:
  webhook_token:
    file: ./secrets/webhook_token
```

and set `MOONIE_SIGNAL_WEBHOOK_TOKEN_FILE=/run/secrets/webhook_token` in `.env`.

An invalid value (a list item that is not an id, an out-of-range number) stops the start with a line naming the
variable and the item's position, never its value.

## Working on it

`just` lists the recipes; each one runs in the pinned Python image, so only Docker and `just` are needed.

- `just test`, `just lint`, `just format`, `just ci` (lint then tests)
- `just ci` is the only CI: there is no hosted pipeline, and a change merges only on a green local `just ci`
- `just build` builds `moonie-signal:local`; `just run` builds and starts `compose.yml`
- `just lock` re-pins `requirements*.txt` from `requirements*.in` (needs `uv`)

Before publishing a fork or a change, `just privacy-check` scans every repository file for the words that would
identify your own deployment (host names, domains, names, address ranges). Keep that list outside the repository,
one word per line (`#` starts a comment, matching ignores case), and point `PRIVATE_WORDS_FILE` at it:
`PRIVATE_WORDS_FILE=~/signal-private-words just privacy-check`. A hit names the file, the line and the word's line
in your list, never the word. `just test` runs the same check skipped, plus a generic one that refuses any private
(RFC 1918) address: examples use 192.0.2.x, 198.51.100.x and 203.0.113.x.

## Deploying

1. `docker network create --internal moonie-signal-hook` once, and attach the webhook receiver to it.
2. Copy `.env.example` to `.env` and fill it in; write `secrets/push_token` as `.env.example` says.
3. Put the signal-cli data folder in `./signal-cli` (owned 1000:1000), or register the account with signal-cli.
4. `docker compose up -d --build` (or `just run`): it builds the app's image from this checkout, tagged
   `MOONIE_SIGNAL_IMAGE` (`moonie-signal:local` by default), and starts the stack. No prebuilt image is published.

Stop any other relay of the same account first: both would answer every message. The waitress server runs in the
same process as the receive and deliver threads, so the app is one process, one container.

## Licence

Copyright (C) 2026 LunaCreatoris.

Moonie Signal is free software under the GNU Affero General Public License, version 3 or any later version
(SPDX: `AGPL-3.0-or-later`). The full text is in [LICENSE](LICENSE). If you run a modified version as a network
service, the licence asks you to offer its source to the people who use it.
