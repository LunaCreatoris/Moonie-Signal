---
title: Getting started
description: Prepare the Signal account, the network and the token, connect the relay to a webhook and start it.
order: 1
---

## What you need {#requirements}

- A Linux host with Docker and Docker Compose.
- A service that receives the webhook: an HTTP address that accepts a JSON `POST` and answers in JSON.
- A phone number for the bot's Signal account. A separate number is advised: the relay answers everything this
  account receives from allowed people.
- A copy of the repository, for `compose.yml` and `.env.example`.

One relay per Signal account: two relays on the same account would each answer every message.

## The network {#network}

signal-cli-rest-api's API has no authentication: whoever reaches it controls the account. So the relay and
signal-cli have their own network, which nothing else joins. This network reaches the Internet: the relay can call
a webhook at any address it can reach.

For the send route, the relay can only be reached through an internal network, created once:

```sh
docker network create --internal moonie-signal-hook
```

Attach to this network, in its own compose file, the service that receives the webhook and calls the send route,
here under the name `receiver`:

```yaml
services:
  receiver:
    networks:
      default: {}
      moonie-signal-hook: {}

networks:
  moonie-signal-hook:
    external: true
```

On this network, that service reaches the relay at `http://moonie-signal:8080`, and the relay reaches that service
by its name, for example `http://receiver:8000`. No port is published on the host.

## The settings {#settings}

Copy `.env.example` to `.env` (mode 600, never versioned) and fill in at least:

```sh
MOONIE_SIGNAL_ACCOUNT=+15555550100
MOONIE_SIGNAL_WEBHOOK_URL=http://receiver:8000/<your-webhook-path>
MOONIE_SIGNAL_WHITELIST_DIRECT=+15555550101
```

- `MOONIE_SIGNAL_ACCOUNT` is the bot's number, in international format: `+` then the digits.
- `MOONIE_SIGNAL_WEBHOOK_URL` is the webhook's full address (see below).
- `MOONIE_SIGNAL_IMAGE` is the tag of the relay's image, built from your copy of the repository.

The whitelists are explained in [Whitelists and groups](whitelists-and-groups.md).

## The push token {#push-token}

The `/signal/send` route needs a random token of at least 32 characters, readable by the relay's user (uid 10001)
only:

```sh
install -d -m 0700 secrets
python3 -c "import secrets; print(secrets.token_hex(32))" > secrets/push_token
sudo chown 10001:10001 secrets/push_token && sudo chmod 0400 secrets/push_token
```

Keep this token: the client that pushes sends it with every push. Without a valid token the send route is off;
receiving still works.

## The Signal account {#signal-account}

The account's data lives in `./signal-cli`, next to `compose.yml`, owned by uid 1000:

```sh
sudo install -d -o 1000 -g 1000 signal-cli
```

If you already have a signal-cli folder for this number, copy it there. Otherwise, link the account as a secondary
device of a phone. To do so, publish the API on the host for the time of the link only, with a
`compose.override.yml` file:

```yaml
services:
  signal:
    ports: ["127.0.0.1:8080:8080"]
```

```sh
docker compose up -d signal
```

Open `http://127.0.0.1:8080/v1/qrcodelink?device_name=moonie-signal` on the host and scan the code from Signal on
the phone (Settings, Linked devices). The other ways, such as registering a new number, are in the
[signal-cli-rest-api documentation](https://github.com/bbernhard/signal-cli-rest-api).

Keep the API published while you look up the group ids (see
[Whitelists and groups](whitelists-and-groups.md#find-a-group-id)), then delete `compose.override.yml`.

## The webhook {#webhook}

The relay sends each allowed message as a `POST`, with a JSON body, to the address in `MOONIE_SIGNAL_WEBHOOK_URL`.
The service that receives this webhook must:

1. accept a JSON `POST` at this address;
2. answer in JSON: `{"reply": "…"}` to reply in the conversation, `{}` or an empty body to stay silent
   (see [Replying and sending](replying-and-sending.md#reply));
3. answer with a `2xx` code. A `429` or a `503` makes the relay retry; any other code loses the message. Redirects
   are not followed.

Each message arrives as a JSON object: `text` for the text, `chat.type` (`direct` or `group`) and `chat.id` for
the conversation, `sender.id`, `sender.number` and `sender.name` for the author, `attachments` for the attachments
in base64. Each field is detailed in the
[README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#what-it-does).

The webhook has 120 seconds to answer. To protect the webhook with a token, see
`MOONIE_SIGNAL_WEBHOOK_TOKEN_FILE` and the `compose.override.yml` example in the
[README's settings](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#settings).

A setup tested with n8n, node by node, is described in [Tested setups](tested-setups.md#n8n).

## Start {#start}

First stop any other relay of the same account, then build the relay's image from your copy of the repository
and start the stack:

```sh
docker compose up -d --build
docker compose logs -f moonie
```

The log should show `websocket connected`. Write to the bot from a whitelisted number: the message reaches the
webhook.

Next: [Replying and sending](replying-and-sending.md).
