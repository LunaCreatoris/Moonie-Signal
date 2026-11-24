---
title: Dépannage
description: Lire les journaux du relais et régler les problèmes les plus courants.
order: 4
---

## Lire les journaux {#logs}

```sh
docker compose logs -f moonie
```

Chaque message traité donne une ligne avec son type de conversation, le nombre de pièces jointes, le résultat et la
durée, par exemple `message 12: direct, 0 attachments, replied, 840 ms`. Le résultat vaut `replied`, `silence`
(réponse vide) ou `lost:` suivi de la raison. Le journal ne contient jamais de numéro, d'identifiant, de nom, de
texte ni de jeton.

## Rien n'arrive dans n8n {#nothing-reaches-n8n}

- **`refused 1 message from a chat not allowed`** : la personne ou le groupe n'est pas dans les listes. Voir
  [Listes blanches et groupes](whitelists-and-groups.md).
- **`lost:members_not_allowed`** : un membre ou une invitation du groupe n'est pas dans
  `MOONIE_SIGNAL_WHITELIST_GROUPS`. **`lost:members_unknown`** : la liste des membres n'a pas pu être lue.
- **`lost:unreachable`** : le relais ne joint pas n8n. Vérifiez que n8n est sur le réseau `moonie-signal-hook` sous
  le nom `n8n`, et l'adresse de `MOONIE_SIGNAL_WEBHOOK_URL`.
- **`lost:http_404`** : le workflow n'est pas activé, ou l'adresse est celle de test (`/webhook-test/`) au lieu de
  celle de production (`/webhook/`).
- **`lost:timeout`** : le workflow a mis plus de 120 secondes à répondre. Répondez plus tôt, ou allongez le délai
  avec `MOONIE_SIGNAL_WEBHOOK_SECONDS` (600 secondes au plus).
- **Aucune ligne du tout** : le relais ne reçoit rien de signal-cli. Voir la section suivante.

## Le relais ne reçoit rien {#no-messages}

Le journal doit montrer `websocket connected`. S'il montre `websocket closed` en boucle, regardez celui de
signal-cli :

```sh
docker compose logs -f signal
```

Vérifiez que `./signal-cli` contient bien les données du compte, qu'il appartient à l'uid 1000, et que
`MOONIE_SIGNAL_ACCOUNT` est le même numéro. `docker compose ps` montre le relais `unhealthy` quand la connexion est
coupée depuis plus de deux minutes.

## Chaque message reçoit deux réponses {#double-replies}

Un autre relais tourne sur le même compte, ici ou sur une autre machine. Arrêtez-le : un seul relais par compte.

## La route d'envoi refuse {#push-refused}

- **`503 http.auth_not_configured`** : le jeton manque, fait moins de 32 caractères ou n'est pas lisible par
  l'uid 10001. Le journal le dit au démarrage. Voir [Démarrer](getting-started.md#push-token).
- **`401 http.unauthorized`** : l'en-tête `Authorization` n'est pas `Bearer` suivi du bon jeton.
- **`403 signal.not_allowed`** : le destinataire n'est pas dans les listes.
- **`502`** avec `signal.not_allowed` pour un groupe autorisé : un membre du groupe n'est pas dans
  `MOONIE_SIGNAL_WHITELIST_GROUPS`. Avec `signal.backend_unavailable` : signal-cli ne répond pas.
- **`503 http.busy`** : trois envois tournent déjà. Réessayez après une seconde.

## Le relais ne démarre pas {#start-fails}

Une ligne du journal nomme la variable fautive et la position de l'élément dans la liste, sans sa valeur : un
numéro sans `+`, un identifiant mal copié, un nombre hors limites. Corrigez `.env` et relancez.

## Plus d'aide {#more-help}

Tous les codes d'erreur et réglages sont dans le
[README du dépôt](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md).
