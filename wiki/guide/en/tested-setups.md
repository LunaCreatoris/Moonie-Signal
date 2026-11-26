---
title: Tested setups
description: The setups actually tried with Moonie Signal, with their concrete steps.
order: 6
---

## What this page holds {#about}

The rest of the guide describes the relay in generic terms: an HTTP webhook in, a send route out. This page gathers
the setups that were actually tried with Moonie Signal, with the steps specific to each product. Addresses and
names are examples.

## n8n {#n8n}

n8n receives the webhook in a workflow, replies in the conversation, and sends messages at any time through the send
route. Both run in Docker, on the same host.

### The network {#n8n-network}

Attach n8n to the internal `moonie-signal-hook` network (see [Getting started](getting-started.md#network)), in its
own compose file, under the name `n8n`:

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

### The Webhook node {#n8n-webhook-node}

Create a workflow that starts with a **Webhook** node:

1. HTTP method `POST`, and a path of your own.
2. Respond: "Using 'Respond to Webhook' node" if the workflow replies in the conversation, otherwise an immediate
   answer.
3. Activate the workflow: the relay calls the production address (`/webhook/`), not the test one
   (`/webhook-test/`).

In `.env`, `MOONIE_SIGNAL_WEBHOOK_URL` is this node's production address:

```sh
MOONIE_SIGNAL_WEBHOOK_URL=http://n8n:5678/webhook/<your-webhook-path>
```

Write to the bot from a whitelisted number: the message shows up in the workflow's executions.

### Reply with Respond to Webhook {#n8n-respond}

End the workflow with a **Respond to Webhook** node that answers in JSON:

```json
{"reply": "Got it, **thanks**!"}
```

`text_mode` and `attachments` are accepted too (see [Replying and sending](replying-and-sending.md#reply)). With a
`{}` answer, the bot stays silent. The workflow has 120 seconds to reach this node.

### Send with HTTP Request {#n8n-http-request}

A workflow can send a message at any time, for example on an alert or a schedule, with an **HTTP Request** node:

1. Method `POST`, address `http://moonie-signal:8080/signal/send`.
2. Authentication: "Generic Credential Type", then "Header Auth", with the name `Authorization` and the value
   `Bearer` followed by a space and the token from `secrets/push_token`.
3. JSON body, for example:

```json
{
  "to": ["5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42"],
  "text": "Last night's backup is **done**."
}
```

So that a replayed execution does not send the same message twice, add an `Idempotency-Key` header in the same node
(see [Replying and sending](replying-and-sending.md#push-answer)).

### Pitfalls met {#n8n-pitfalls}

- **`lost:http_404`**: the workflow is not active, or the address is the test one (`/webhook-test/`) instead of the
  production one (`/webhook/`).
- **`lost:unreachable`**: n8n is not on the `moonie-signal-hook` network, or not under the name `n8n`.
- **`lost:timeout`**: the workflow took more than 120 seconds to reach the Respond to Webhook node. Answer sooner,
  or raise the timeout with `MOONIE_SIGNAL_WEBHOOK_SECONDS` (600 seconds at most).
