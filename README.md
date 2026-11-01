# Messagerie souveraine de l'administration

Prototype réalisé pour le sprint technique pré-hackathon du MTDPCE (Burkina Faso).
Toutes les données et tous les comptes sont fictifs.

## Concept

Griot Secure est une messagerie instantanée pour les agents de l'administration publique du Burkina Faso. Les agents s'écrivent, créent des groupes et partagent des fichiers, comme sur les applications du marché.

Mais ici, le serveur est installé chez l'État, les messages sont chiffrés de bout en bout (même le serveur ne peut pas les lire), et seuls les agents inscrits par l'administration peuvent entrer, avec un mot de passe et un code à six chiffres. Si un agent quitte l'administration ou perd son téléphone, ses accès sont coupés en un clic, sur tous ses appareils.

Le nom vient du griot, qui porte la parole de confiance.

## Architecture

```
Navigateur de l'agent ──HTTPS──► Caddy (seule porte d'entrée, port 443)
                                  ├─► Element Web : l'application ; le chiffrement se fait sur l'appareil
                                  ├─► Synapse + PostgreSQL : serveur Matrix, ne stocke que du chiffré
                                  ├─► Keycloak : identités, mot de passe + TOTP, rôles, ministères
                                  └─► Console d'administration : enrôlement, annuaire, révocation, audit
```

Réseau Docker interne sans accès à Internet ; seul Caddy est exposé. Fédération Matrix coupée : aucune donnée ne quitte le serveur de l'État.

## Technologies et licences

- **Synapse** 1.164.1, serveur Matrix — AGPL-3.0 — https://github.com/element-hq/synapse
- **Element Web** 1.12.33, client — AGPL-3.0 ou GPL-3.0 — https://github.com/element-hq/element-web
- **matrix-sdk-crypto**, chiffrement Olm/Megolm intégré à Element — Apache-2.0 — https://github.com/matrix-org/matrix-rust-sdk
- **Keycloak** 26.8.1, identités, TOTP, rôles — Apache-2.0 — https://github.com/keycloak/keycloak
- **PostgreSQL** 17, base de données — PostgreSQL License — https://www.postgresql.org
- **Caddy** 2.11, HTTPS et autorité de certification interne — Apache-2.0 — https://github.com/caddyserver/caddy
- **Docker Compose**, déploiement — Apache-2.0 — https://github.com/docker/compose
- **FastAPI**, console — MIT — https://github.com/fastapi/fastapi
- **Uvicorn, Jinja2, httpx, Authlib, itsdangerous**, console — BSD-3-Clause ; **python-multipart** — Apache-2.0 — dépôts GitHub `encode/uvicorn`, `pallets/jinja`, `encode/httpx`, `authlib/authlib`, `pallets/itsdangerous`, `Kludex/python-multipart`
- **pyotp**, tests automatisés — MIT — https://github.com/pyauth/pyotp
- **Aegis** / **FreeOTP**, applications TOTP des agents — GPL-3.0 / Apache-2.0 — https://github.com/beemdevelopment/Aegis · https://github.com/freeotp/freeotp-android

Notre code est publié sous **AGPL-3.0**.

## Niveau d'engagement

**Étendre et adapter.**

Nous n'avons pas créé de messagerie de zéro. Nous avons utilisé Element et Synapse, deux logiciels open source qui existent déjà et que nous n'avons pas modifiés dans leur code.

Nous n'avons écrit aucune cryptographie : le chiffrement des messages est celui d'Element.

Nous les avons installés et configurés pour l'administration : le chiffrement est obligatoire dans tous les salons et personne ne peut s'inscrire seul.

Nous avons ajouté notre propre console d'administration, qui permet d'inscrire un agent, de le bloquer et de consulter un journal des actions. Nous avons aussi ajouté des salons « Confidentiel », dont les messages sont effacés automatiquement du serveur.

## Installation

Prérequis : Docker et Docker Compose, ports 80 et 443 libres, environ 3 Go de RAM.

1. Déclarer les noms dans le fichier hosts (Windows : `C:\Windows\System32\drivers\etc\hosts`, en administrateur) :
   ```
   127.0.0.1 chat.messagerie.test matrix.messagerie.test auth.messagerie.test admin.messagerie.test
   ```
2. Lancer :
   ```sh
   cp .env.example .env      # en déploiement réel : changer toutes les valeurs
   docker compose up -d --wait
   ```
   Au premier démarrage (environ 1 minute), tout s'initialise automatiquement : bases PostgreSQL,
   clé de signature Synapse, import du realm Keycloak, autorité de certification de Caddy.
3. Faire confiance à l'autorité de certification interne de Caddy :
   ```sh
   docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-racine.crt
   ```
   - **Chrome / Edge (Windows)** : `certutil -addstore -user Root caddy-racine.crt`, accepter, puis redémarrer le navigateur.
   - **Firefox** : Paramètres → Vie privée et sécurité → Certificats → Afficher les certificats →
     Autorités → Importer → cocher « Confirmer cette AC pour identifier des sites web ».

   Cette CA est propre à chaque installation (elle est recréée si le volume `caddy_donnees` est supprimé).
4. Ouvrir https://chat.messagerie.test

Remise à zéro complète (toutes les données sont effacées) : `docker compose down -v`.

## Comptes de démonstration

Tous les comptes sont **fictifs**. À la première connexion, Keycloak impose de configurer un code
TOTP avec une application open source (Aegis ou FreeOTP) : scanner le QR code, puis saisir le code.

| Identifiant | Mot de passe | Ministère | Fonction | Rôle |
|---|---|---|---|---|
| `awa.ouedraogo` | `Agent-Demo-2026!` | Santé | Médecin-chef de district | agent |
| `boukary.zongo` | `Agent-Demo-2026!` | Santé | Responsable de la logistique | agent |
| `issa.sawadogo` | `Agent-Demo-2026!` | Économie et Finances | Contrôleur financier | agent |
| `mariam.kabore` | `Agent-Demo-2026!` | Transition digitale | Cheffe de projet numérique | agent |
| `admin.messagerie` | `Admin-Demo-2026!` | Transition digitale | Administratrice de la messagerie | admin-messagerie |
| `stagiaire.sansrole` | `Stagiaire-Demo-2026!` | Santé | Stagiaire | *aucun* : refusé par Synapse (test d'intrusion) |

Vérifier le socle de sécurité, commande par commande : `docs/verifier-le-socle.md`.

La console technique Keycloak (`/admin`) et le realm `master` ne sont pas publiés (404). Administration
technique depuis le réseau interne uniquement, par exemple :
`docker compose exec keycloak /opt/keycloak/bin/kcadm.sh config credentials --server http://keycloak:8080 --realm master --user admin`
(mot de passe `KEYCLOAK_ADMIN_PASSWORD` du `.env`).

## Limites

- **Appareil volé encore ouvert :** la révocation coupe l'accès au serveur et aux nouveaux messages ; ce qui est déjà sur l'appareil peut rester lisible.
- **Captures d'écran et transferts :** impossibles à bloquer dans un navigateur. Salons Confidentiel : la purge a lieu sur le serveur, pas sur les appareils.
- **Métadonnées :** le serveur voit qui échange avec qui et quand, la taille des messages et des fichiers, les noms des salons et les adresses IP (conservées 1 jour). Détail : `docs/securite.md`.
- **Client web :** clés stockées dans le navigateur ; un poste infecté ou un serveur qui sert un client modifié compromet les messages. En production : application signée.
- **Langues :** seuls les écrans de connexion sont traduits en mooré ; l'application Element reste en français.
- **Prototype :** un seul serveur, sans haute disponibilité ni sauvegarde automatique ; autorité de certification et secrets de démonstration, à remplacer par ceux de l'État ; liaisons internes (Synapse, console, Keycloak) en HTTP dans le réseau Docker.

## Licence

Ce dépôt est publié sous licence **AGPL-3.0** (voir `LICENSE`).
