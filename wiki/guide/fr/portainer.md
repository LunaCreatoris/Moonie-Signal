---
title: Déployer avec Portainer
description: Faire tourner le relais dans une pile Portainer CE déployée depuis le dépôt Git, sans just et sans image publiée.
order: 2
---

## Ce que fait Portainer ici {#what-works}

Aucune image du relais n'est publiée : elle est construite à partir du dépôt. Dans Portainer, un seul type de pile
le permet : **Repository** (une pile déployée depuis Git). Portainer clone le dépôt et lance `docker compose` dans
ce clone : `compose.yml` y construit l'image du relais, à chaque déploiement et à chaque mise à jour.

- Les piles **Web editor** et **Upload** ne contiennent que le fichier compose, sans copie du dépôt : l'image du
  relais ne peut pas être construite ainsi. Elles ne servent plus bas que pour une pile signal-cli temporaire.
- **Chemins relatifs** : dans Portainer Community Edition, une pile Git ne résout pas les dossiers `./signal-cli`
  et `./secrets` de `compose.yml` (cette option est réservée à la Business Edition). Donnez-leur des chemins
  absolus sur l'hôte avec `MOONIE_SIGNAL_DATA_DIR` et `MOONIE_SIGNAL_SECRETS_DIR`.
- **Fichiers de l'hôte** : la pile lit un fichier de jeton sur l'hôte. Déployez-la avec un compte administrateur
  de Portainer : quand les montages de l'hôte sont masqués aux autres utilisateurs, leurs piles ne peuvent pas
  désigner de fichier de l'hôte.

Cette page suit le comportement documenté de Portainer ; elle ne figure pas encore dans les
[Cas testés](tested-setups.md). La page [Démarrer](getting-started.md) explique chaque réglage ; seules les étapes
propres à Portainer sont ici.

## Préparer l'hôte {#prepare-the-host}

Portainer ne crée pas de fichiers sur l'hôte : ces étapes se font une fois, dans un terminal sur l'hôte Docker.
Le dossier `/srv/moonie-signal` est un exemple : tout chemin absolu convient.

```sh
sudo install -d -o 1000 -g 1000 /srv/moonie-signal/signal-cli
sudo install -d -m 0700 /srv/moonie-signal/secrets
openssl rand -hex 32 | sudo tee /srv/moonie-signal/secrets/push_token > /dev/null
sudo chown 10001:10001 /srv/moonie-signal/secrets/push_token
sudo chmod 0400 /srv/moonie-signal/secrets/push_token
```

Le premier dossier contient le compte Signal (uid 1000, l'utilisateur de signal-cli) ; le jeton est celui que
donne le client qui envoie (voir [Le jeton d'envoi](getting-started.md#push-token)), lisible par l'uid 10001,
l'utilisateur du relais, et lui seul. Pour le relire : `sudo cat /srv/moonie-signal/secrets/push_token`.

## Créer le réseau du webhook {#hook-network}

Dans Portainer, **Networks**, **Add network** : nommez-le `moonie-signal-hook`, pilote `bridge`, et activez
**Isolated network** (le réseau interne de Docker). C'est le même réseau que
`docker network create --internal moonie-signal-hook`, décrit dans [Le réseau](getting-started.md#network).

La pile du service qui reçoit le webhook le rejoint comme réseau externe, comme le montre cette page.

## Lier le compte Signal {#link-account}

Si `/srv/moonie-signal/signal-cli` contient déjà les données du compte, passez cette étape. Sinon, ajoutez une
pile temporaire en **Web editor**, nommée `signal-link` :

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

L'API n'est publiée que sur la boucle locale de l'hôte, puisqu'elle n'a aucune authentification. Ouvrez
`http://127.0.0.1:8080/v1/qrcodelink?device_name=moonie-signal` sur l'hôte, ou depuis votre ordinateur par un
tunnel SSH (`ssh -L 8080:127.0.0.1:8080` suivi de l'hôte), et scannez le code depuis Signal sur le téléphone
(Réglages, Appareils liés). Tant que la pile tourne, relevez aussi les identifiants de groupes (voir
[Listes blanches et groupes](whitelists-and-groups.md#find-a-group-id)).

Supprimez ensuite la pile `signal-link` : deux signal-cli ne doivent jamais tourner en même temps sur le même
dossier de compte.

## Créer la pile {#create-the-stack}

**Stacks**, **Add stack**, nom `moonie-signal`, méthode **Repository** :

- le dépôt `https://github.com/LunaCreatoris/Moonie-Signal` (son adresse, ou une source Git créée avec elle,
  selon la version de Portainer) ;
- la référence `refs/heads/main` ;
- le chemin du fichier compose, `compose.yml`.

Sous **Environment variables**, ajoutez les réglages un par un, ou chargez une copie remplie de `.env.example`
avec **Load variables from .env file**. Au minimum :

```sh
MOONIE_SIGNAL_ACCOUNT=+15555550100
MOONIE_SIGNAL_WEBHOOK_URL=http://receiver:8000/<your-webhook-path>
MOONIE_SIGNAL_WHITELIST_DIRECT=+15555550101
MOONIE_SIGNAL_DATA_DIR=/srv/moonie-signal/signal-cli
MOONIE_SIGNAL_SECRETS_DIR=/srv/moonie-signal/secrets
```

Ces valeurs restent dans Portainer, jamais dans le dépôt. Puis **Deploy the stack** : Portainer clone le dépôt,
construit l'image du relais et démarre les deux conteneurs.

## Vérifier et mettre à jour {#check-and-update}

Dans **Containers**, ouvrez le journal du relais (`moonie-signal-moonie-1`) : il doit montrer
`websocket connected`. Écrivez au bot depuis un numéro de la liste blanche : le message arrive sur le webhook.

Pour mettre à jour, ouvrez la pile et choisissez **Pull and redeploy** : Portainer récupère les nouveaux commits
et reconstruit l'image. Les **GitOps updates** peuvent le faire d'elles-mêmes, par interrogation régulière ou par
webhook. Pour changer un réglage, modifiez les variables d'environnement de la pile, puis redéployez.

## Le jeton du webhook {#webhook-token}

Un jeton porteur pour le webhook demande un second fichier compose (voir les
[réglages du README](https://github.com/LunaCreatoris/Moonie-Signal/blob/main/README.md#settings)). Portainer ne
lit de fichiers compose que dans le dépôt, par **Additional paths** : gardez ce fichier dans votre propre fork du
dépôt, déployez la pile depuis ce fork, et placez le fichier du jeton dans `/srv/moonie-signal/secrets`, avec le
même propriétaire et les mêmes droits que le jeton d'envoi.
