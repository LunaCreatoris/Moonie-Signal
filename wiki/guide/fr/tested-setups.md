---
title: Cas testés
description: Les installations réellement essayées avec Moonie Signal, avec leurs étapes concrètes.
order: 6
---

## Ce que contient cette page {#about}

Le reste du guide décrit le relais de façon générique : un webhook HTTP en entrée, une route d'envoi en sortie. Cette
page rassemble les installations qui ont été essayées pour de vrai avec Moonie Signal, avec les étapes propres à
chaque produit. Les adresses et les noms sont des exemples.

## n8n {#n8n}

n8n reçoit le webhook dans un workflow, y répond dans la conversation, et envoie des messages à tout moment par la
route d'envoi. Les deux tournent dans Docker, sur le même hôte.

### Le réseau {#n8n-network}

Branchez n8n sur le réseau interne `moonie-signal-hook` (voir [Démarrer](getting-started.md#network)), dans son
propre fichier compose, sous le nom `n8n` :

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

Sur ce réseau, le relais joint n8n à `http://n8n:5678`, et n8n joint le relais à `http://moonie-signal:8080`. Aucun
port n'est publié sur l'hôte.

### Le nœud Webhook {#n8n-webhook-node}

Créez un workflow qui commence par un nœud **Webhook** :

1. Méthode HTTP `POST`, et un chemin à vous.
2. Réponse : « Using 'Respond to Webhook' node » si le workflow répond dans la conversation, sinon une réponse
   immédiate.
3. Activez le workflow : le relais appelle l'adresse de production (`/webhook/`), pas celle de test
   (`/webhook-test/`).

Dans `.env`, `MOONIE_SIGNAL_WEBHOOK_URL` est l'adresse de production de ce nœud :

```sh
MOONIE_SIGNAL_WEBHOOK_URL=http://n8n:5678/webhook/<your-webhook-path>
```

Écrivez au bot depuis un numéro de la liste blanche : le message arrive dans les exécutions du workflow.

### Répondre avec Respond to Webhook {#n8n-respond}

Terminez le workflow par un nœud **Respond to Webhook** qui répond en JSON :

```json
{"reply": "Bien reçu, **merci** !"}
```

`text_mode` et `attachments` sont acceptés aussi (voir [Répondre et envoyer](replying-and-sending.md#reply)). Une
réponse `{}` et le bot se tait. Le workflow a 120 secondes pour arriver à ce nœud.

### Envoyer avec HTTP Request {#n8n-http-request}

Un workflow peut écrire à tout moment, par exemple sur une alerte ou un horaire, avec un nœud **HTTP Request** :

1. Méthode `POST`, adresse `http://moonie-signal:8080/signal/send`.
2. Authentification : « Generic Credential Type », puis « Header Auth », avec le nom `Authorization` et la valeur
   `Bearer` suivie d'une espace et du jeton de `secrets/push_token`.
3. Corps en JSON, par exemple :

```json
{
  "to": ["5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42"],
  "text": "La sauvegarde de cette nuit est **terminée**."
}
```

Pour qu'une exécution rejouée n'envoie pas deux fois le même message, ajoutez dans le même nœud un en-tête
`Idempotency-Key` (voir [Répondre et envoyer](replying-and-sending.md#push-answer)).

### Les pièges rencontrés {#n8n-pitfalls}

- **`lost:http_404`** : le workflow n'est pas activé, ou l'adresse est celle de test (`/webhook-test/`) au lieu de
  celle de production (`/webhook/`).
- **`lost:unreachable`** : n8n n'est pas sur le réseau `moonie-signal-hook`, ou pas sous le nom `n8n`.
- **`lost:timeout`** : le workflow a mis plus de 120 secondes à arriver au nœud Respond to Webhook. Répondez plus
  tôt, ou allongez le délai avec `MOONIE_SIGNAL_WEBHOOK_SECONDS` (600 secondes au plus).
