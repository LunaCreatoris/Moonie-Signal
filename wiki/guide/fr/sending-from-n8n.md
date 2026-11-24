---
title: Répondre et envoyer depuis n8n
description: Répondre dans la conversation par la réponse du webhook, ou écrire à tout moment par la route d'envoi protégée par un jeton.
order: 3
---

## Répondre à un message {#reply}

Le relais attend la réponse du webhook et l'envoie dans la conversation d'où vient le message. Terminez le workflow
par un nœud **Respond to Webhook** qui répond en JSON :

```json
{"reply": "Bien reçu, **merci** !"}
```

- `reply` : le texte de la réponse.
- `text_mode` : la mise en forme, facultative (voir plus bas).
- `attachments` : des pièces jointes, facultatives (voir plus bas).

Une réponse `{}`, ou sans corps, et le bot se tait. Le webhook a 120 secondes pour répondre ; passé ce délai, rien
n'est envoyé et le message n'est pas renvoyé.

## Envoyer un message {#push}

Un workflow peut écrire à tout moment, par exemple sur une alerte ou un horaire, avec un nœud **HTTP Request** :

1. Méthode `POST`, adresse `http://moonie-signal:8080/signal/send`.
2. Authentification : « Generic Credential Type », puis « Header Auth », avec le nom `Authorization` et la valeur
   `Bearer` suivie d'une espace et du jeton de `secrets/push_token`.
3. Corps en JSON :

```json
{
  "to": ["5d1f0b0e-3a3c-4c1f-9a51-6f0e2b1c7d42", "group.QUFFQ0F3UUZCZ2NJQ1FvTERBME9EeEFSRWhNVUZSWVhHQmthR3h3ZEhoOD0="],
  "text": "La sauvegarde de cette nuit est **terminée**."
}
```

`to` prend jusqu'à 16 destinataires : identifiants, numéros ou groupes. Chacun doit être autorisé (voir
[Listes blanches et groupes](whitelists-and-groups.md)), et un groupe passe aussi le contrôle de ses membres.

## La réponse de la route {#push-answer}

- `200` avec `{"ok": true, "results": [...]}` : tout est parti.
- `502` avec `signal.send_failed` : au moins un envoi a échoué ; `results` donne le résultat de chaque destinataire.
- `401` : jeton absent ou faux. `503` avec `http.auth_not_configured` : le relais n'a pas de jeton valide.
- `403` avec `signal.not_allowed` : un destinataire n'est pas dans les listes. `detail` dit lequel, par sa
  position (`to[1]`).
- `400`, `413`, `415` : corps invalide, trop gros ou qui n'est pas du JSON. `detail` nomme le champ fautif.

Pour qu'un workflow rejoué n'envoie pas deux fois le même message, ajoutez un en-tête `Idempotency-Key` (lettres,
chiffres et `._:-`, 128 caractères au plus). La même clé avec le même corps rend la première réponse sans renvoyer ;
la même clé avec un autre corps donne `409`.

## La mise en forme {#text-modes}

`text_mode` choisit comment le texte est lu, pour une réponse comme pour un envoi :

- `markdown` (par défaut) : `**gras**`, `*italique*`, `~~barré~~`, `` `code` ``, listes et titres sont convertis en
  styles Signal.
- `styled` : la syntaxe propre à signal-cli, `**gras**`, `*italique*`, `~barré~`, `` `mono` ``, `||spoiler||`.
- `normal` : le texte part tel qu'il est écrit.

Le mode par défaut se change avec `MOONIE_SIGNAL_TEXT_MODE`.

## Les pièces jointes {#attachments}

`attachments` est une liste de 16 pièces au plus, chacune sous l'une de ces formes :

- une data URI : `data:image/png;filename=graphe.png;base64,iVBORw0…` ;
- du base64 brut ;
- un objet `{"data": "…", "content_type": "application/pdf", "filename": "rapport.pdf"}`.

Les pièces reçues arrivent dans le webhook de la même façon, en base64 dans `attachments[].data`. La taille totale
par message est limitée à 10 Mio, dans les deux sens ; elle se change avec `MOONIE_SIGNAL_MAX_ATTACHMENT_BYTES`.
