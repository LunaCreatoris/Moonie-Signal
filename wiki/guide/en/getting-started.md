---
title: Getting started
description: Prepare the Signal account, the network and the token, start the relay and connect it to an n8n webhook.
order: 1
---

## What you need {#requirements}

- A Linux host with Docker and Docker Compose.
- An n8n instance in Docker, on the same host.
- A phone number for the bot's Signal account. A separate number is advised: the relay answers everything this
  account receives from allowed people.
- A copy of the repository, for `compose.yml` and `.env.example`.

One relay per Signal account: two relays on the same account would each answer every message.

## The network {#network}

signal-cli-rest-api's API has no authentication: whoever reaches it controls the account. So the relay and
signal-cli have their own network, and n8n only sees the relay, through an internal network created once:

```sh
docker network create --internal moonie-signal-hook
```

Attach n8n to this network in its own compose file, under the name `n8n`:

```yaml
services:
  n8n:
    networks:
      default: {}
      moonie-signal-hook: {}

networks:
  moonie-signal-hook:
    external: true
```

On this network, the relay reaches n8n at `http://n8n:5678`, and n8n reaches the relay at
`http://moonie-signal:8080`. No port is published on the host.

## The settings {#settings}

Copy `.env.example` to `.env` (mode 600, never versioned) and fill in at least:

```sh
MOONIE_SIGNAL_ACCOUNT=+15555550100
MOONIE_SIGNAL_WEBHOOK_URL=http://n8n:5678/webhook/<your-webhook-path>
MOONIE_SIGNAL_WHITELIST_DIRECT=+15555550101
```

- `MOONIE_SIGNAL_ACCOUNT` is the bot's number, in international format: `+` then the digits.
- `MOONIE_SIGNAL_WEBHOOK_URL` is the n8n webhook's production address (see below).
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

Keep this token: n8n sends it with every push. Without a valid token the send route is off; receiving still works.

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

## The n8n webhook {#n8n-webhook}

In n8n, create a workflow that starts with a **Webhook** node:

1. HTTP method `POST`, and a path of your own, the one you put in `MOONIE_SIGNAL_WEBHOOK_URL`.
2. Respond: "Using 'Respond to Webhook' node" if the workflow replies in the conversation, otherwise an immediate
   answer.
3. Activate the workflow: the relay calls the production address (`/webhook/`), not the test one
   (`/webhook-test/`).

Each message arrives as a JSON object: `text` for the text, `chat.type` (`direct` or `group`) and `chat.id` for
the conversation, `sender.id`, `sender.number` and `sender.name` for the author, `attachments` for the attachments
in base64. Each field is detailed in the
[README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#what-it-does).

The webhook has 120 seconds to answer. To protect the webhook with a token, see
`MOONIE_SIGNAL_WEBHOOK_TOKEN_FILE` and the `compose.override.yml` example in the
[README's settings](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#settings).

## Start {#start}

First stop any other relay of the same account, then build the relay's image from your copy of the repository
and start the stack:

```sh
docker compose up -d --build
docker compose logs -f moonie
```

The log should show `websocket connected`. Write to the bot from a whitelisted number: the message shows up in the
n8n workflow's executions.

Next: [Replying and sending from n8n](sending-from-n8n.md).
