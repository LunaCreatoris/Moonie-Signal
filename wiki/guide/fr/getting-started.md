---
title: Démarrer
description: Préparer le compte Signal, le réseau et le jeton, lancer le relais et le brancher sur un webhook n8n.
order: 1
---

## Ce qu'il faut {#requirements}

- Un hôte Linux avec Docker et Docker Compose.
- Une instance n8n dans Docker, sur le même hôte.
- Un numéro de téléphone pour le compte Signal du bot. Un numéro à part est conseillé : le relais répond à tout ce
  que ce compte reçoit des personnes autorisées.
- Une copie du dépôt, pour `compose.yml` et `.env.example`.

Un seul relais par compte Signal : deux relais sur le même compte répondraient chacun à chaque message.

## Le réseau {#network}

L'API de signal-cli-rest-api n'a aucune authentification : qui la joint contrôle le compte. Le relais et
signal-cli ont donc leur propre réseau, et n8n ne voit que le relais, par un réseau interne créé une fois :

```sh
docker network create --internal moonie-signal-hook
```

Branchez n8n sur ce réseau dans son propre fichier compose, sous le nom `n8n` :

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

## Les réglages {#settings}

Copiez `.env.example` en `.env` (mode 600, jamais versionné) et remplissez au moins :

```sh
MOONIE_SIGNAL_ACCOUNT=+15555550100
MOONIE_SIGNAL_WEBHOOK_URL=http://n8n:5678/webhook/<your-webhook-path>
MOONIE_SIGNAL_WHITELIST_DIRECT=+15555550101
```

- `MOONIE_SIGNAL_ACCOUNT` est le numéro du bot, au format international : `+` puis les chiffres.
- `MOONIE_SIGNAL_WEBHOOK_URL` est l'adresse de production du webhook n8n (voir plus bas).
- `MOONIE_SIGNAL_IMAGE` est l'étiquette de l'image du relais, construite depuis votre copie du dépôt.

Les listes blanches sont expliquées dans [Listes blanches et groupes](whitelists-and-groups.md).

## Le jeton d'envoi {#push-token}

La route d'envoi `/signal/send` demande un jeton aléatoire d'au moins 32 caractères, lisible par l'utilisateur du
relais (uid 10001) seul :

```sh
install -d -m 0700 secrets
python3 -c "import secrets; print(secrets.token_hex(32))" > secrets/push_token
sudo chown 10001:10001 secrets/push_token && sudo chmod 0400 secrets/push_token
```

Gardez ce jeton : n8n le donnera à chaque envoi. Sans jeton valide, la route d'envoi est coupée, la réception
marche quand même.

## Le compte Signal {#signal-account}

Les données du compte vivent dans le dossier `./signal-cli`, à côté de `compose.yml`, qui appartient à l'uid 1000 :

```sh
sudo install -d -o 1000 -g 1000 signal-cli
```

Si vous avez déjà un dossier signal-cli pour ce numéro, copiez-le là. Sinon, liez le compte comme appareil
secondaire d'un téléphone. Pour cela, publiez l'API sur l'hôte le temps du lien seulement, avec un fichier
`compose.override.yml` :

```yaml
services:
  signal:
    ports: ["127.0.0.1:8080:8080"]
```

```sh
docker compose up -d signal
```

Ouvrez `http://127.0.0.1:8080/v1/qrcodelink?device_name=moonie-signal` sur l'hôte et scannez le code depuis
Signal sur le téléphone (Réglages, Appareils liés). Les autres façons de faire, comme l'enregistrement d'un nouveau
numéro, sont dans la
[documentation de signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api).

Gardez l'API publiée le temps de relever les identifiants de groupes (voir
[Listes blanches et groupes](whitelists-and-groups.md#find-a-group-id)), puis supprimez `compose.override.yml`.

## Le webhook n8n {#n8n-webhook}

Dans n8n, créez un workflow qui commence par un nœud **Webhook** :

1. Méthode HTTP `POST`, et un chemin à vous, celui que vous mettez dans `MOONIE_SIGNAL_WEBHOOK_URL`.
2. Réponse : « Using 'Respond to Webhook' node » si le workflow répond dans la conversation, sinon une réponse
   immédiate.
3. Activez le workflow : le relais appelle l'adresse de production (`/webhook/`), pas celle de test
   (`/webhook-test/`).

Chaque message arrive comme un objet JSON : `text` pour le texte, `chat.type` (`direct` ou `group`) et `chat.id`
pour la conversation, `sender.id`, `sender.number` et `sender.name` pour l'auteur, `attachments` pour les pièces
jointes en base64. Le détail de chaque champ est dans le
[README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#what-it-does).

Le webhook a 120 secondes pour répondre. Pour protéger le webhook par un jeton, voir
`MOONIE_SIGNAL_WEBHOOK_TOKEN_FILE` et l'exemple de `compose.override.yml` dans les
[réglages du README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#settings).

## Lancer {#start}

Arrêtez d'abord tout autre relais du même compte, puis construisez l'image du relais depuis votre copie du dépôt
et lancez la pile :

```sh
docker compose up -d --build
docker compose logs -f moonie
```

Le journal doit montrer `websocket connected`. Écrivez au bot depuis un numéro de la liste blanche : le message
arrive dans les exécutions du workflow n8n.

Ensuite : [Répondre et envoyer depuis n8n](sending-from-n8n.md).
