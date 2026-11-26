---
title: Moonie Signal
description: Moonie Signal se place devant signal-cli et le traduit.
status: Version 4.0.0
github: https://github.com/LunaCreatoris/Moonie-Signal
order: 5
---

## Ce que fait Moonie Signal {#what-signal-does}

Moonie Signal se place devant signal-cli et le traduit. Au lieu de son API brute, vous avez une route simple pour
envoyer des messages, et chaque message reçu arrive à votre webhook, n8n par exemple, dans un format stable.

Le compte Signal tourne dans
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) ; le relais écoute ses messages et les
transmet au webhook, et le service qui reçoit le webhook décide quoi en faire.

- **Recevoir** : chaque message autorisé part vers le webhook en JSON, texte, mentions, citation et pièces jointes
  compris.
- **Répondre** : la réponse JSON du webhook repart dans la même conversation. Une réponse vide n'envoie rien.
- **Envoyer de soi-même** : un client HTTP peut envoyer un message à tout moment par la route `/signal/send`,
  protégée par un jeton.

## Qui peut parler au bot {#who-can-talk}

Rien ne passe par défaut. Une conversation directe passe si la personne est dans une liste blanche. Un groupe passe
s'il est autorisé **et** si chacun de ses membres est dans une autre liste blanche : un inconnu ajouté au groupe le
rend muet. Les refus sont silencieux. Voir [Listes blanches et groupes](whitelists-and-groups.md).

Les journaux ne donnent que des compteurs et des codes : jamais un numéro, un identifiant, un nom, un texte ou un
jeton.

## Les pages du guide {#pages}

- [Démarrer](getting-started.md) : les deux façons de déployer, le compte Signal, le réseau, le jeton, le webhook
  et le lancement.
- [Déployer avec Portainer](portainer.md) : le même relais dans une pile Portainer construite depuis le dépôt Git.
- [Listes blanches et groupes](whitelists-and-groups.md) : autoriser des personnes et des groupes.
- [Répondre et envoyer](replying-and-sending.md) : la réponse du webhook et la route d'envoi.
- [Dépannage](troubleshooting.md) : lire les journaux et régler les problèmes courants.
- [Cas testés](tested-setups.md) : les installations essayées pour de vrai, n8n compris, étape par étape.

## La référence technique {#reference}

Tous les réglages, le format exact des messages et les codes d'erreur sont décrits dans le
[README du dépôt](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md), en anglais.
