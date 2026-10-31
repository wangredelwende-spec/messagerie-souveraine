# Ce que le serveur sait des fichiers envoyés (table `local_media_repository`)

Relevé fait le 31/10/2026 sur la démo, après l'envoi de `note.txt` (contenu : « Le colis de vaccins
arrive mardi ») dans un salon chiffré par `awa.ouedraogo`. Commande (lecture seule) :

```sh
docker compose exec -T postgres psql -U postgres -d synapse -c "SELECT media_id, media_type, media_length,
  upload_name, user_id, to_timestamp(created_ts/1000) AS cree, last_access_ts, authenticated,
  sha256 IS NOT NULL AS empreinte FROM local_media_repository"
```

| media_id | media_type | media_length | upload_name | user_id | créé (UTC) | authenticated |
|---|---|---|---|---|---|---|
| `HMBmsuhjvtfIpNbmGUuflhoB` | application/octet-stream | 0 | *(vide)* | @awa.ouedraogo:messagerie.test | 16:57:00 | oui |
| `ImTqGSXxBRwdWAWmFVXGOoMf` | application/octet-stream | 32 | *(vide)* | @awa.ouedraogo:messagerie.test | 16:58:53 | oui |

## Ce qui est caché au serveur

- **Le nom d'origine** : `upload_name` est vide. Element chiffre le fichier dans le navigateur puis
  l'envoie sans nom ; « note.txt » n'existe que dans le message chiffré (événement `m.room.encrypted`).
- **Le vrai type** : `application/octet-stream` pour tous les fichiers chiffrés (le type `text/plain`
  est lui aussi dans le message chiffré).
- **Le contenu** : le fichier stocké dans `/data/media_store` est chiffré (AES-256-CTR, clé connue
  seulement des participants). `scripts/verifier-serveur-aveugle.sh` ne retrouve la phrase nulle part.

## Ce que le serveur voit quand même

- **La taille exacte** : 32 octets, c'est exactement la longueur de la phrase. Le chiffrement AES-CTR
  ne rembourre pas : la taille du fichier chiffré égale celle du fichier d'origine. Pour un court
  fichier texte, cela donne la longueur du texte.
- **Qui a envoyé un fichier, et quand** (`user_id`, `created_ts`) : une métadonnée de communication.
  Le salon de destination n'est pas dans cette table, mais il se retrouve par l'heure des messages.
- **Une empreinte SHA-256 du fichier chiffré** : elle permet de reconnaître le même fichier chiffré
  envoyé deux fois, pas d'en déduire le contenu.
- **Une ligne à 0 octet** : identifiant de média réservé sans contenu (probablement une première
  tentative d'envoi interrompue). Elle révèle seulement une action d'envoi à 16:57.

Ce qui n'est **pas** exposé : `authenticated = oui` signifie que le téléchargement exige d'être
connecté ; aucune miniature n'est générée (impossible sur un fichier chiffré) ; `last_access_ts` est vide.

## Pistes d'amélioration (non mises en œuvre)

- Rembourrer les fichiers à des tailles fixes côté client pour masquer la longueur : non
  disponible dans Element, ce serait une modification du client.
- Purger les médias anciens (`media_retention` dans Synapse) pour limiter l'historique conservé.
