# Messagerie souveraine de l'administration

Prototype réalisé pour le sprint technique pré-hackathon du MTDPCE (Burkina Faso).
Toutes les données et tous les comptes sont fictifs.

## Concept

Griot Secure est une messagerie instantanée pour les agents de l'administration publique du Burkina Faso. Les agents s'écrivent, créent des groupes et partagent des fichiers, comme sur les applications du marché.

Mais ici, le serveur est installé chez l'État, les messages sont chiffrés de bout en bout (même le serveur ne peut pas les lire), et seuls les agents inscrits par l'administration peuvent entrer, avec un mot de passe et un code à six chiffres. Si un agent quitte l'administration ou perd son téléphone, il est bloqué en un clic, sur tous ses appareils.

Le nom vient du griot, qui porte la parole de confiance.

## Architecture

_À compléter (phase 4)._

## Technologies et licences

_À compléter (phase 4). Détail dans `docs/technologies.md`._

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

La console technique Keycloak (`/admin`) et le realm `master` ne sont pas publiés (404). Administration
technique depuis le réseau interne uniquement, par exemple :
`docker compose exec keycloak /opt/keycloak/bin/kcadm.sh config credentials --server http://keycloak:8080 --realm master --user admin`
(mot de passe `KEYCLOAK_ADMIN_PASSWORD` du `.env`).

## Limites

_À compléter (phase 4)._

## Licence

Ce dépôt est publié sous licence **AGPL-3.0** (voir `LICENSE`).
