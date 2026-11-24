---
title: Moonie Signal
description: Relie un compte Signal à un workflow n8n, pour lire les messages des personnes et des groupes autorisés, leur répondre et leur écrire.
status: Version 4.0.0
github: https://github.com/LunaCreatoris/Moonie-Signal
order: 5
---

## Ce que fait Moonie Signal {#what-signal-does}

Moonie Signal est un petit relais entre un compte Signal et un webhook n8n. Le compte tourne dans
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) ; le relais écoute ses messages et les
transmet à n8n, qui décide quoi en faire.

- **Recevoir** : chaque message autorisé part vers le webhook n8n en JSON, texte, mentions, citation et pièces jointes
  compris.
- **Répondre** : la réponse JSON du webhook repart dans la même conversation. Une réponse vide n'envoie rien.
- **Envoyer de soi-même** : un workflow n8n peut envoyer un message à tout moment par la route `/signal/send`,
  protégée par un jeton.

## Qui peut parler au bot {#who-can-talk}

Rien ne passe par défaut. Une conversation directe passe si la personne est dans une liste blanche. Un groupe passe
s'il est autorisé **et** si chacun de ses membres est dans une autre liste blanche : un inconnu ajouté au groupe le
rend muet. Les refus sont silencieux. Voir [Listes blanches et groupes](whitelists-and-groups.md).

Les journaux ne donnent que des compteurs et des codes : jamais un numéro, un identifiant, un nom, un texte ou un
jeton.

## Les pages du guide {#pages}

- [Démarrer](getting-started.md) : le compte Signal, le réseau, le jeton, le lancement et le webhook n8n.
- [Listes blanches et groupes](whitelists-and-groups.md) : autoriser des personnes et des groupes.
- [Répondre et envoyer depuis n8n](sending-from-n8n.md) : la réponse du webhook et la route d'envoi.
- [Dépannage](troubleshooting.md) : lire les journaux et régler les problèmes courants.

## La référence technique {#reference}

Tous les réglages, le format exact des messages et les codes d'erreur sont décrits dans le
[README du dépôt](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md), en anglais.
