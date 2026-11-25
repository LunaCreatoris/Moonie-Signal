---
title: Moonie Signal
description: Moonie Signal sits in front of signal-cli and translates it.
status: Version 4.0.0
github: https://github.com/LunaCreatoris/Moonie-Signal
order: 5
---

## What Moonie Signal does {#what-signal-does}

Moonie Signal sits in front of signal-cli and translates it. Instead of its raw API, you get a simple route to send
messages, and every message received reaches your webhook (n8n, for example) in a stable format.

The Signal account runs in
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api); the relay listens to its messages and
forwards them to the webhook, and the service that receives the webhook decides what to do with them.

- **Receive**: every allowed message goes to the webhook as JSON, with its text, mentions, quote and attachments.
- **Reply**: the webhook's JSON answer goes back to the same conversation. An empty answer sends nothing.
- **Send on its own**: an HTTP client can send a message at any time through the `/signal/send` route, protected
  by a token.

## Who can talk to the bot {#who-can-talk}

Nothing goes through by default. A direct conversation goes through when the person is in a whitelist. A group goes
through when it is allowed **and** every one of its members is in another whitelist: a stranger added to the group
makes it silent. Refusals are silent. See [Whitelists and groups](whitelists-and-groups.md).

The logs only give counts and codes: never a number, an id, a name, a text or a token.

## The guide's pages {#pages}

- [Getting started](getting-started.md): the Signal account, the network, the token, the webhook and the start.
- [Whitelists and groups](whitelists-and-groups.md): allow people and groups.
- [Replying and sending](replying-and-sending.md): the webhook's answer and the send route.
- [Troubleshooting](troubleshooting.md): read the logs and fix the common problems.

## The technical reference {#reference}

Every setting, the exact message format and the error codes are described in the
[repository's README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md).
