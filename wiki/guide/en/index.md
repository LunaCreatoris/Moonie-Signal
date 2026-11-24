---
title: Moonie Signal
description: Connects a Signal account to an n8n workflow, to read messages from allowed people and groups, reply to them and write to them.
status: Version 4.0.0
github: https://github.com/LunaCreatoris/Moonie-Signal
order: 5
---

## What Moonie Signal does {#what-signal-does}

Moonie Signal is a small relay between a Signal account and an n8n webhook. The account runs in
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api); the relay listens to its messages and
forwards them to n8n, which decides what to do with them.

- **Receive**: every allowed message goes to the n8n webhook as JSON, with its text, mentions, quote and
  attachments.
- **Reply**: the webhook's JSON answer goes back to the same conversation. An empty answer sends nothing.
- **Send on its own**: an n8n workflow can send a message at any time through the `/signal/send` route, protected
  by a token.

## Who can talk to the bot {#who-can-talk}

Nothing goes through by default. A direct conversation goes through when the person is in a whitelist. A group goes
through when it is allowed **and** every one of its members is in another whitelist: a stranger added to the group
makes it silent. Refusals are silent. See [Whitelists and groups](whitelists-and-groups.md).

The logs only give counts and codes: never a number, an id, a name, a text or a token.

## The guide's pages {#pages}

- [Getting started](getting-started.md): the Signal account, the network, the token, the start and the n8n webhook.
- [Whitelists and groups](whitelists-and-groups.md): allow people and groups.
- [Replying and sending from n8n](sending-from-n8n.md): the webhook's answer and the send route.
- [Troubleshooting](troubleshooting.md): read the logs and fix the common problems.

## The technical reference {#reference}

Every setting, the exact message format and the error codes are described in the
[repository's README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md).
