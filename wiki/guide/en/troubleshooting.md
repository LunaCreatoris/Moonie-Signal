---
title: Troubleshooting
description: Read the relay's logs and fix the most common problems.
order: 4
---

## Read the logs {#logs}

```sh
docker compose logs -f moonie
```

Each handled message gives one line with its conversation type, the number of attachments, the outcome and the
duration, for example `message 12: direct, 0 attachments, replied, 840 ms`. The outcome is `replied`, `silence`
(empty answer) or `lost:` followed by the reason. The log never holds a number, an id, a name, a text or a token.

## Nothing reaches the webhook {#nothing-reaches-the-webhook}

- **`refused 1 message from a chat not allowed`**: the person or the group is not in the lists. See
  [Whitelists and groups](whitelists-and-groups.md).
- **`lost:members_not_allowed`**: a member or an invite of the group is not in `MOONIE_SIGNAL_WHITELIST_GROUPS`.
  **`lost:members_unknown`**: the member list could not be read.
- **`lost:unreachable`**: the relay cannot reach the webhook. Check the address in `MOONIE_SIGNAL_WEBHOOK_URL`, and
  that the service that receives it is on a network the relay reaches, for example `moonie-signal-hook`.
- **`lost:http_` followed by a code**: the webhook answered with this code instead of a `2xx`. A `404` often comes
  from a wrong path in `MOONIE_SIGNAL_WEBHOOK_URL`, a `401` or a `403` from a missing or wrong webhook token, a `3xx`
  from a redirect, which the relay does not follow.
- **`lost:timeout`**: the webhook took more than 120 seconds to answer. Answer sooner, or raise the timeout with
  `MOONIE_SIGNAL_WEBHOOK_SECONDS` (600 seconds at most).
- **No line at all**: the relay receives nothing from signal-cli. See the next section.

## The relay receives nothing {#no-messages}

The log should show `websocket connected`. If it shows `websocket closed` over and over, look at signal-cli's:

```sh
docker compose logs -f signal
```

Check that `./signal-cli` holds the account's data, that it belongs to uid 1000, and that `MOONIE_SIGNAL_ACCOUNT`
is the same number. `docker compose ps` shows the relay `unhealthy` once the connection has been down for more than
two minutes.

## Every message gets two replies {#double-replies}

Another relay runs on the same account, here or on another machine. Stop it: one relay per account.

## The send route refuses {#push-refused}

- **`503 http.auth_not_configured`**: the token is missing, shorter than 32 characters or not readable by uid
  10001. The log says so at start. See [Getting started](getting-started.md#push-token).
- **`401 http.unauthorized`**: the `Authorization` header is not `Bearer` followed by the right token.
- **`403 signal.not_allowed`**: the recipient is not in the lists.
- **`502`** with `signal.not_allowed` for an allowed group: a member of the group is not in
  `MOONIE_SIGNAL_WHITELIST_GROUPS`. With `signal.backend_unavailable`: signal-cli does not answer.
- **`503 http.busy`**: three pushes are already running. Retry after a second.

## The relay does not start {#start-fails}

A log line names the faulty variable and the item's position in the list, without its value: a number without `+`,
a badly copied id, a number out of range. Fix `.env` and restart.

## More help {#more-help}

Every error code and setting is in the
[repository's README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md).
