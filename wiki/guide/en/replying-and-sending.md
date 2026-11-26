---
title: Replying and sending
description: Reply in the conversation through the webhook's answer, or send at any time through the send route protected by a token.
order: 4
---

## Reply to a message {#reply}

The relay waits for the webhook's answer and sends it to the conversation the message came from. The service that
receives the webhook answers with a `2xx` code and a JSON body:

```json
{"reply": "Got it, **thanks**!"}
```

- `reply`: the reply's text.
- `text_mode`: the formatting, optional (see below).
- `attachments`: attachments, optional (see below).

With a `{}` answer or no body, the bot stays silent. The webhook has 120 seconds to answer; past that, nothing is
sent and the message is not retried.

## Push a message {#push}

An HTTP client can send a message at any time, for example on an alert or a schedule, with a request to the send
route:

1. Method `POST`, address `http://moonie-signal:8080/signal/send`, from the `moonie-signal-hook` network (see
   [Getting started](getting-started.md#network)).
2. `Authorization` header: `Bearer` followed by a space and the token from `secrets/push_token`.
3. `Content-Type: application/json` header, and a JSON body:

```json
{
  "to": ["5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42", "group.QUFFQ0F3UUZCZ2NJQ1FvTERBME9EeEFSRWhNVUZSWVhHQmthR3h3ZEhoOD0="],
  "text": "Last night's backup is **done**."
}
```

With curl, from a container on the `moonie-signal-hook` network, with the token in the `PUSH_TOKEN` variable:

```sh
curl -X POST http://moonie-signal:8080/signal/send \
  -H "Authorization: Bearer $PUSH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to": ["+15555550101"], "text": "Hello"}'
```

`to` takes up to 16 recipients: ids, numbers or groups. Each one must be allowed (see
[Whitelists and groups](whitelists-and-groups.md)), and a group also goes through the member check.

The same push from an n8n HTTP Request node is described in [Tested setups](tested-setups.md#n8n-http-request).

## The route's answer {#push-answer}

- `200` with `{"ok": true, "results": [...]}`: everything went out.
- `502` with `signal.send_failed`: at least one send failed; `results` gives each recipient's outcome.
- `401`: missing or wrong token. `503` with `http.auth_not_configured`: the relay has no valid token.
- `403` with `signal.not_allowed`: a recipient is not in the lists. `detail` says which one, by its position
  (`to[1]`).
- `400`, `413`, `415`: a body that is invalid, too large or not JSON. `detail` names the faulty field.

So that a replayed request does not send the same message twice, add an `Idempotency-Key` header (letters, digits
and `._:-`, 128 characters at most). The same key with the same body gives back the first answer without sending
again; the same key with another body gives `409`.

## Formatting {#text-modes}

`text_mode` chooses how the text is read, for a reply as for a push:

- `markdown` (default): `**bold**`, `*italic*`, `~~strike~~`, `` `code` ``, lists and headings are turned into
  Signal styles.
- `styled`: signal-cli's own syntax, `**bold**`, `*italic*`, `~strike~`, `` `mono` ``, `||spoiler||`.
- `normal`: the text goes as written.

The default mode is changed with `MOONIE_SIGNAL_TEXT_MODE`.

## Attachments {#attachments}

`attachments` is a list of 16 items at most, each in one of these forms:

- a data URI: `data:image/png;filename=chart.png;base64,iVBORw0…`;
- bare base64;
- an object `{"data": "…", "content_type": "application/pdf", "filename": "report.pdf"}`.

Received attachments reach the webhook the same way, in base64 in `attachments[].data`. The total size per message
is capped at 10 MiB, both ways; it is changed with `MOONIE_SIGNAL_MAX_ATTACHMENT_BYTES`.
