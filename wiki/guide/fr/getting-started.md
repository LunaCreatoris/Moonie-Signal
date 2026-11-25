---
title: Démarrer
description: Préparer le compte Signal, le réseau et le jeton, brancher le relais sur un webhook et le lancer.
order: 1
---

## Ce qu'il faut {#requirements}

- Un hôte Linux avec Docker et Docker Compose.
- Un service qui reçoit le webhook : une adresse HTTP qui accepte un `POST` en JSON et répond en JSON.
- Un numéro de téléphone pour le compte Signal du bot. Un numéro à part est conseillé : le relais répond à tout ce
  que ce compte reçoit des personnes autorisées.
- Une copie du dépôt, pour `compose.yml` et `.env.example`.

Un seul relais par compte Signal : deux relais sur le même compte répondraient chacun à chaque message.

## Le réseau {#network}

L'API de signal-cli-rest-api n'a aucune authentification : qui la joint contrôle le compte. Le relais et
signal-cli ont donc leur propre réseau, que rien d'autre ne rejoint. Ce réseau sort vers Internet : le relais peut
appeler un webhook à n'importe quelle adresse qu'il joint.

Pour la route d'envoi, le relais n'est joignable que par un réseau interne, créé une fois :

```sh
docker network create --internal moonie-signal-hook
```

Branchez sur ce réseau, dans son propre fichier compose, le service qui reçoit le webhook et appelle la route
d'envoi, ici sous le nom `receiver` :

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

Sur ce réseau, ce service joint le relais à `http://moonie-signal:8080`, et le relais joint ce service par son nom,
par exemple `http://receiver:8000`. Aucun port n'est publié sur l'hôte.

## Les réglages {#settings}

Copiez `.env.example` en `.env` (mode 600, jamais versionné) et remplissez au moins :

```sh
MOONIE_SIGNAL_ACCOUNT=+15555550100
MOONIE_SIGNAL_WEBHOOK_URL=http://receiver:8000/<your-webhook-path>
MOONIE_SIGNAL_WHITELIST_DIRECT=+15555550101
```

- `MOONIE_SIGNAL_ACCOUNT` est le numéro du bot, au format international : `+` puis les chiffres.
- `MOONIE_SIGNAL_WEBHOOK_URL` est l'adresse complète du webhook (voir plus bas).
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

Gardez ce jeton : le client qui envoie le donne à chaque envoi. Sans jeton valide, la route d'envoi est coupée,
la réception marche quand même.

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

## Le webhook {#webhook}

Le relais envoie chaque message autorisé en `POST`, avec un corps JSON, à l'adresse de `MOONIE_SIGNAL_WEBHOOK_URL`.
Le service qui reçoit ce webhook doit :

1. accepter un `POST` en JSON sur cette adresse ;
2. répondre en JSON : `{"reply": "…"}` pour répondre dans la conversation, `{}` ou un corps vide pour se taire
   (voir [Répondre et envoyer](replying-and-sending.md#reply)) ;
3. répondre par un code `2xx`. Un `429` ou un `503` fait réessayer le relais ; tout autre code perd le message. Les
   redirections ne sont pas suivies.

Chaque message arrive comme un objet JSON : `text` pour le texte, `chat.type` (`direct` ou `group`) et `chat.id`
pour la conversation, `sender.id`, `sender.number` et `sender.name` pour l'auteur, `attachments` pour les pièces
jointes en base64. Le détail de chaque champ est dans le
[README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#what-it-does).

Le webhook a 120 secondes pour répondre. Pour protéger le webhook par un jeton, voir
`MOONIE_SIGNAL_WEBHOOK_TOKEN_FILE` et l'exemple de `compose.override.yml` dans les
[réglages du README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#settings).

Une installation testée avec n8n, nœud par nœud, est décrite dans [Cas testés](tested-setups.md#n8n).

## Lancer {#start}

Arrêtez d'abord tout autre relais du même compte, puis construisez l'image du relais depuis votre copie du dépôt
et lancez la pile :

```sh
docker compose up -d --build
docker compose logs -f moonie
```

Le journal doit montrer `websocket connected`. Écrivez au bot depuis un numéro de la liste blanche : le message
arrive sur le webhook.

Ensuite : [Répondre et envoyer](replying-and-sending.md).
