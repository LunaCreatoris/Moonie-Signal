---
title: Deploy with Portainer
description: Run the relay as a Portainer CE stack deployed from the Git repository, with no just and no published image.
order: 2
---

## What Portainer does here {#what-works}

No image of the relay is published: it is built from the repository. In Portainer, that works with one stack type
only, **Repository** (a stack deployed from Git). Portainer clones the repository and runs `docker compose` in the
clone, so `compose.yml` builds the relay's image there, at every deployment and every update.

- **Web editor** and **Upload** stacks hold the compose file alone, with no copy of the repository: the relay's
  image cannot be built that way. They are only used below for a temporary signal-cli stack.
- **Relative paths**: in Portainer Community Edition, a Git stack does not resolve the `./signal-cli` and
  `./secrets` folders of `compose.yml` (that option belongs to the Business Edition). Give them absolute paths on
  the host with `MOONIE_SIGNAL_DATA_DIR` and `MOONIE_SIGNAL_SECRETS_DIR`.
- **Host files**: the stack reads a token file on the host. Deploy it as a Portainer administrator: when bind
  mounts are hidden from the other users, their stacks cannot reference host files.

This page follows Portainer's documented behaviour; it is not yet among the [Tested setups](tested-setups.md).
The [Getting started](getting-started.md) page explains each setting; only the Portainer-specific steps are here.

## Prepare the host {#prepare-the-host}

Portainer does not create files on the host, so these steps run once in a shell on the Docker host. The folder
`/srv/moonie-signal` is an example: any absolute path works.

```sh
sudo install -d -o 1000 -g 1000 /srv/moonie-signal/signal-cli
sudo install -d -m 0700 /srv/moonie-signal/secrets
openssl rand -hex 32 | sudo tee /srv/moonie-signal/secrets/push_token > /dev/null
sudo chown 10001:10001 /srv/moonie-signal/secrets/push_token
sudo chmod 0400 /srv/moonie-signal/secrets/push_token
```

The first folder holds the Signal account (uid 1000, signal-cli's user); the token is the one the client that
pushes sends (see [The push token](getting-started.md#push-token)), readable by uid 10001, the relay's user, only.
To read it back: `sudo cat /srv/moonie-signal/secrets/push_token`.

## Create the hook network {#hook-network}

In Portainer, **Networks**, **Add network**: name it `moonie-signal-hook`, driver `bridge`, and turn
**Isolated network** on (Docker's internal network). It is the same network as
`docker network create --internal moonie-signal-hook`, described in [The network](getting-started.md#network).

The stack of the service that receives the webhook joins it as an external network, as shown on that page.

## Link the Signal account {#link-account}

If `/srv/moonie-signal/signal-cli` already holds the account's data, skip this step. Otherwise, add a temporary
stack with **Web editor**, named `signal-link`:

```yaml
services:
  signal:
    image: bbernhard/signal-cli-rest-api:0.101
    environment:
      MODE: json-rpc
    ports: ["127.0.0.1:8080:8080"]
    volumes:
      - /srv/moonie-signal/signal-cli:/home/.local/share/signal-cli
```

The API is published on the host's loopback only, since it has no authentication. Open
`http://127.0.0.1:8080/v1/qrcodelink?device_name=moonie-signal` on the host, or from your computer through an SSH
tunnel (`ssh -L 8080:127.0.0.1:8080` followed by the host), and scan the code from Signal on the phone (Settings,
Linked devices). While the stack runs, note the group ids too (see
[Whitelists and groups](whitelists-and-groups.md#find-a-group-id)).

Then delete the `signal-link` stack: two signal-cli on the same account folder must never run together.

## Create the stack {#create-the-stack}

**Stacks**, **Add stack**, name `moonie-signal`, build method **Repository**:

- the repository `https://github.com/LunaCreatoris/Moonie-Signal` (its URL, or a Git source created with it,
  depending on the Portainer version);
- the reference `refs/heads/main`;
- the Compose path `compose.yml`.

Under **Environment variables**, add the settings one by one, or load a copy of `.env.example` filled in with
**Load variables from .env file**. At least:

```sh
MOONIE_SIGNAL_ACCOUNT=+15555550100
MOONIE_SIGNAL_WEBHOOK_URL=http://receiver:8000/<your-webhook-path>
MOONIE_SIGNAL_WHITELIST_DIRECT=+15555550101
MOONIE_SIGNAL_DATA_DIR=/srv/moonie-signal/signal-cli
MOONIE_SIGNAL_SECRETS_DIR=/srv/moonie-signal/secrets
```

These values stay in Portainer, never in the repository. Then **Deploy the stack**: Portainer clones the repository,
builds the relay's image and starts both containers.

## Check and update {#check-and-update}

In **Containers**, open the relay's log (`moonie-signal-moonie-1`): it should show `websocket connected`.
Write to the bot from a whitelisted number: the message reaches the webhook.

To update, open the stack and use **Pull and redeploy**: Portainer fetches the new commits and rebuilds the image.
**GitOps updates** can do it on their own, by polling or webhook. Changing a setting is done in the same stack's
environment variables, then redeploying.

## The webhook token {#webhook-token}

A bearer token for the webhook needs a second compose file (see the
[README's settings](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#settings)). Portainer only
reads compose files from the repository, through **Additional paths**: keep that file in your own fork of the
repository, deploy the stack from the fork, and put the token file in `/srv/moonie-signal/secrets` with the same
owner and mode as the push token.
