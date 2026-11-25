---
title: Listes blanches et groupes
description: Choisir qui peut écrire au bot en direct, quels groupes il sert et qui peut être membre de ces groupes.
order: 2
---

## Trois listes {#three-lists}

Tout se règle dans `.env`, avec des listes séparées par des virgules. Une liste vide n'autorise personne.

| Variable | Ce qu'elle autorise |
|---|---|
| `MOONIE_SIGNAL_WHITELIST_DIRECT` | Les personnes qui peuvent écrire au bot en direct |
| `MOONIE_SIGNAL_ALLOWED_GROUPS` | Les groupes que le bot sert |
| `MOONIE_SIGNAL_WHITELIST_GROUPS` | Les personnes qui peuvent être dans un groupe servi |

Les mêmes listes valent pour l'envoi : la route d'envoi ne peut écrire qu'à une personne de
`MOONIE_SIGNAL_WHITELIST_DIRECT` ou à un groupe de `MOONIE_SIGNAL_ALLOWED_GROUPS`.

Après un changement, relancez le relais avec `docker compose up -d`. Une valeur invalide arrête le démarrage avec
une ligne qui nomme la variable et la position de l'élément, jamais sa valeur.

## Numéros et identifiants {#numbers-and-uuids}

Une personne s'écrit par son numéro (`+15555550101`) ou par son identifiant Signal, un uuid
(`5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42`). L'identifiant est préférable : il ne change pas avec le numéro, et il
marche aussi pour une personne qui cache son numéro.

Pour relever l'identifiant d'une personne :

1. Mettez d'abord son numéro dans `MOONIE_SIGNAL_WHITELIST_DIRECT` et relancez.
2. Demandez-lui d'écrire au bot, puis lisez le message reçu par le webhook : l'identifiant est dans
   `sender.id`.
3. Remplacez le numéro par cet identifiant.

```sh
MOONIE_SIGNAL_WHITELIST_DIRECT=5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42,+15555550102
```

## Trouver l'identifiant d'un groupe {#find-a-group-id}

Ajoutez le compte du bot au groupe depuis un téléphone. Puis, avec l'API publiée le temps du lien (voir
[Démarrer](getting-started.md#signal-account)), listez les groupes du compte :

```sh
curl http://127.0.0.1:8080/v1/groups/+15555550100
```

Chaque groupe a un champ `id` de la forme `group.…` : copiez-le tel quel dans `MOONIE_SIGNAL_ALLOWED_GROUPS`. Les
formes `group:…` et l'identifiant base64 brut sont aussi acceptées. Une fois un groupe servi, son identifiant arrive
aussi dans `chat.id` de chaque message.

## Les membres d'un groupe {#group-members}

Un groupe n'est servi que si **chaque** membre, **chaque** invitation en attente et l'auteur du message sont dans
`MOONIE_SIGNAL_WHITELIST_GROUPS`. Le compte du bot lui-même n'a pas à y être.

```sh
MOONIE_SIGNAL_ALLOWED_GROUPS=group.QUFFQ0F3UUZCZ2NJQ1FvTERBME9EeEFSRWhNVUZSWVhHQmthR3h3ZEhoOD0=
MOONIE_SIGNAL_WHITELIST_GROUPS=5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42,+15555550102
```

- La liste des membres est relue auprès de signal-cli à chaque message. Si quelqu'un d'inconnu rejoint le groupe ou
  y est invité, le bot se tait dans ce groupe jusqu'à ce que la personne parte ou soit ajoutée à la liste.
- Si la liste des membres ne peut pas être lue, le groupe est refusé.
- Un membre connu seulement par un identifiant `PNI:` s'écrit `PNI:` suivi de l'uuid.
- Avec `MOONIE_SIGNAL_ALLOWED_GROUPS` rempli mais `MOONIE_SIGNAL_WHITELIST_GROUPS` vide, aucun groupe n'est servi :
  le journal le signale au démarrage.

## Ce que voit une personne refusée {#refusals}

Rien. Le relais ne répond pas et n'envoie pas d'erreur : il écrit seulement une ligne dans son journal, sans aucun
détail sur la personne. Voir [Dépannage](troubleshooting.md#nothing-reaches-the-webhook).
