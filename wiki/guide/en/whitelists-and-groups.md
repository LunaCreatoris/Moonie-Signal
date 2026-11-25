---
title: Whitelists and groups
description: Choose who may write to the bot directly, which groups it serves and who may be a member of those groups.
order: 2
---

## Three lists {#three-lists}

Everything is set in `.env`, with comma-separated lists. An empty list allows no one.

| Variable | What it allows |
|---|---|
| `MOONIE_SIGNAL_WHITELIST_DIRECT` | The people who may write to the bot directly |
| `MOONIE_SIGNAL_ALLOWED_GROUPS` | The groups the bot serves |
| `MOONIE_SIGNAL_WHITELIST_GROUPS` | The people who may be in a served group |

The same lists apply to sending: the send route can only write to a person in `MOONIE_SIGNAL_WHITELIST_DIRECT` or
to a group in `MOONIE_SIGNAL_ALLOWED_GROUPS`.

After a change, restart the relay with `docker compose up -d`. An invalid value stops the start with a line naming
the variable and the item's position, never its value.

## Numbers and ids {#numbers-and-uuids}

A person is written by their number (`+15555550101`) or by their Signal id, a uuid
(`5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42`). The id is better: it does not change with the number, and it also works
for a person who hides their number.

To note a person's id:

1. First put their number in `MOONIE_SIGNAL_WHITELIST_DIRECT` and restart.
2. Ask them to write to the bot, then read the message the webhook received: the id is in
   `sender.id`.
3. Replace the number with that id.

```sh
MOONIE_SIGNAL_WHITELIST_DIRECT=5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42,+15555550102
```

## Find a group's id {#find-a-group-id}

Add the bot's account to the group from a phone. Then, with the API published for the time of the link (see
[Getting started](getting-started.md#signal-account)), list the account's groups:

```sh
curl http://127.0.0.1:8080/v1/groups/+15555550100
```

Each group has an `id` field of the form `group.…`: copy it as it is into `MOONIE_SIGNAL_ALLOWED_GROUPS`. The
`group:…` forms and the raw base64 id are accepted too. Once a group is served, its id also comes in the `chat.id`
of every message.

## A group's members {#group-members}

A group is served only when **every** member, **every** pending invite and the message's author are in
`MOONIE_SIGNAL_WHITELIST_GROUPS`. The bot's own account does not need to be there.

```sh
MOONIE_SIGNAL_ALLOWED_GROUPS=group.QUFFQ0F3UUZCZ2NJQ1FvTERBME9EeEFSRWhNVUZSWVhHQmthR3h3ZEhoOD0=
MOONIE_SIGNAL_WHITELIST_GROUPS=5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42,+15555550102
```

- The member list is read again from signal-cli for every message. If a stranger joins the group or is invited, the
  bot stays silent in that group until the person leaves or is added to the list.
- If the member list cannot be read, the group is refused.
- A member known only by a `PNI:` id is written `PNI:` followed by the uuid.
- With `MOONIE_SIGNAL_ALLOWED_GROUPS` filled but `MOONIE_SIGNAL_WHITELIST_GROUPS` empty, no group is served: the log
  says so at start.

## What a refused person sees {#refusals}

Nothing. The relay does not answer and sends no error: it only writes a line in its log, with no detail about the
person. See [Troubleshooting](troubleshooting.md#nothing-reaches-the-webhook).
