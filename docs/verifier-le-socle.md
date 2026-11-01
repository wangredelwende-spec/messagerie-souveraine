# Vérifier le socle de sécurité

Pour chaque exigence : la manipulation ou la commande, puis le résultat attendu.
Commandes à taper à la racine du dépôt, dans **Git Bash** (ou un terminal Linux/macOS).

## Prérequis

- Pile démarrée et saine : `docker compose up -d --wait` puis `docker compose ps` (tout « healthy »).
- Python 3 avec `requests` et `pyotp` pour les scripts : `pip install -r console/tests/requirements.txt`.
- Une application TOTP open source (Aegis ou FreeOTP) pour les comptes de démonstration.
- Sous Git Bash, préfixer par `MSYS_NO_PATHCONV=1` les commandes `docker compose exec` qui contiennent
  un chemin `/data/...` (sinon Git Bash le transforme en chemin Windows). Les scripts le font déjà.

---

## 1. Le serveur ne lit rien

### a) Trafic réseau dans le navigateur

1. Dans Element, **F12** → onglet **Réseau** (Network) → filtre : `send`.
2. Écrire une phrase dans un salon, Entrée.
3. Ouvrir la requête **`PUT …/rooms/!…/send/m.room.encrypted/…`** → onglet **Charge utile** (Payload).

**Attendu** : `{"algorithm": "m.megolm.v1.aes-sha2", "ciphertext": "AwgAEp…", "session_id": "…", …}`,
de type `m.room.encrypted`, **sans champ `body`** : la phrase n'est pas dans la requête.

Fichier : envoyer un fichier, ouvrir la requête **`POST …/_matrix/media/v3/upload`**.
**Attendu** : `Content-Type: application/octet-stream`, aucun nom de fichier, contenu binaire illisible.

### b) Base de données, médias et journaux

Envoyer d'abord depuis Element une phrase témoin (en message, puis dans un fichier texte), puis :
```sh
scripts/verifier-serveur-aveugle.sh "<phrase témoin>"
```
**Attendu** : `absente` pour la base (dump complet), le dossier des médias et les journaux, puis
`RÉSULTAT : phrase introuvable…` (code 0).

**Contre-test** (le script sait trouver une donnée en clair) :
```sh
scripts/contre-test-serveur-aveugle.sh
```
**Attendu** : `TROUVÉE base de données Synapse …` pour « Ministère de la Santé » (le nom d'un salon est
un événement d'état non chiffré), puis `CONTRE-TEST RÉUSSI`.

Inspection directe de la base :
```sh
docker compose exec -T postgres psql -U postgres -d synapse -c \
  "SELECT e.type, left(j.json, 200) FROM events e JOIN event_json j USING (event_id)
   WHERE e.type = 'm.room.encrypted' ORDER BY e.stream_ordering DESC LIMIT 2"
```
**Attendu** : `m.room.encrypted` et un JSON ne contenant que `ciphertext`, `session_id`, `algorithm`.

Ce que le serveur voit malgré tout (expéditeur, salon, heure, taille des fichiers) :
`docs/metadonnees-medias.md` et `docs/securite.md`.

---

## 2. Révocation d'un agent pendant une conversation de groupe

Le **Départ est définitif** (compte Matrix désactivé pour toujours) : utiliser un agent enrôlé pour
l'occasion dans la console, qui a fait sa première connexion et se trouve donc dans le canal de son
ministère.

1. Trois agents du même canal, chacun dans un navigateur (ou un profil) différent, s'envoient un message.
2. Console (`admin.messagerie`) → **Annuaire** → ministère → l'agent → **Départ de l'agent** → la page
   liste les effets → **Confirmer**.

**Attendu** :
- console : « Compte Keycloak désactivé, sessions fermées », « Compte Matrix @…:messagerie.test
  désactivé », statut **Révoqué** ;
- navigateur de l'agent révoqué : en quelques secondes, Element indique que la session est terminée
  (le serveur répond 401 à sa synchronisation) ;
- un autre agent écrit : les membres restants le lisent ; le canal affiche « … a quitté le salon » ;
- l'agent révoqué tente de se reconnecter : Keycloak refuse (« compte désactivé ») ;
- console → **Journal d'audit** : ligne `admin.messagerie | depart | <agent> | ok` avec l'heure.

**Perte d'appareil** : même parcours avec le bouton **Perte d'appareil**. **Attendu** : statut
**Suspendu** (TOTP supprimé, appareils Matrix supprimés, sessions fermées) ; le bouton **Réactiver**
affiche une seule fois un mot de passe temporaire et impose un nouvel enrôlement TOTP.

Test automatique (perte d'appareil, réactivation, départ, journal d'audit) :
```sh
python console/tests/test_revocation.py
```
**Attendu** : quatre lignes `OK`, code 0.

---

## 3. Intrusion d'un compte non enrôlé

```sh
scripts/test-intrus.sh
```
**Attendu** :
```
REFUSÉ  (attendu)  1. Inscription d'un nouveau compte Matrix          HTTP 403 M_FORBIDDEN
REFUSÉ  (attendu)  2. Connexion Matrix par mot de passe              HTTP 400 Password login has been disabled
REFUSÉ  (attendu)  3. Compte inexistant sur la page de connexion Keycloak
REFUSÉ  (attendu)  4. Compte sans le rôle agent (stagiaire.sansrole) « You are not allowed to log in here »
REFUSÉ  (attendu)  5. Agent non invité … canaux institutionnels      HTTP [403, 403, 403]
RÉSULTAT : les 5 tentatives d'intrusion ont été refusées.
```

À la main :
1. **Compte inexistant** : fenêtre privée → https://chat.messagerie.test → `intrus` / n'importe quel
   mot de passe. **Attendu** : Keycloak refuse ; ni bouton d'inscription ni lien « mot de passe oublié ».
2. **Agent non invité** : console → **Canaux** → copier l'identifiant `!…` du canal Santé. Dans Element,
   connecté en `mariam.kabore` (autre ministère), taper `/join !…:messagerie.test`.
   **Attendu** : refus (« vous n'êtes pas invité »).

---

## 4. Identité vérifiée et TOTP obligatoire

1. Première connexion d'un compte de démonstration (voir le README) sur https://chat.messagerie.test.
   **Attendu** : redirection immédiate vers Keycloak ; après le mot de passe, configuration du TOTP
   imposée (QR code) avant tout accès ; aux connexions suivantes, mot de passe **et** code TOTP.
2. Console → **Enrôler un agent**. **Attendu** : mot de passe temporaire affiché une seule fois ; à la
   première connexion, changement du mot de passe puis enrôlement TOTP imposés ; l'agent apparaît dans
   l'**Annuaire** (ministère, fonction, statut **Actif**) et dans le canal de son ministère.
   Test automatique : `python console/tests/test_enrolement.py` (quatre lignes `OK`, code 0).
3. Console d'administration : un compte sans le rôle `admin-messagerie` est refusé.
4. Console technique de Keycloak non publiée :
   ```sh
   curl -sk -o /dev/null -w '%{http_code}\n' https://auth.messagerie.test/admin/
   curl -sk -o /dev/null -w '%{http_code}\n' https://auth.messagerie.test/realms/master/
   ```
   **Attendu** : `404` et `404`.
5. Force brute : après 5 échecs de connexion, le compte est bloqué temporairement.

---

## 5. Aucun service tiers

1. Navigateur : **F12** → **Réseau**, puis utiliser Element (connexion, salons, envoi d'un message et
   d'un fichier). **Attendu** : aucune requête hors de `*.messagerie.test`, aucune violation CSP dans
   la console du navigateur.
2. Politique de sécurité du contenu envoyée par Caddy :
   ```sh
   curl -skI https://chat.messagerie.test/ | grep -i content-security-policy
   ```
   **Attendu** : `connect-src 'self' https://matrix.messagerie.test https://auth.messagerie.test`,
   aucun autre domaine.
3. Les conteneurs n'ont pas accès à Internet :
   ```sh
   docker compose exec -T synapse python -c "import urllib.request; urllib.request.urlopen('https://matrix.org', timeout=5)"
   ```
   **Attendu** : `URLError … Temporary failure in name resolution`.

Réglages correspondants : `element/LISEZMOI.md`, `synapse/homeserver.yaml`, `caddy/Caddyfile`.

---

## 6. Salons « Confidentiel » à expiration automatique

1. Console → **Canaux** → « Créer un salon Confidentiel » : un sujet, durée **5 minutes
   (démonstration)**, cocher deux agents → **Créer le salon**.
   **Attendu** : « Salon « [CONFIDENTIEL] … » créé… 2 membre(s) », puis le salon dans le tableau avec
   sa durée.
2. Dans Element : le salon apparaît, son sujet annonce l'effacement automatique. Écrire deux messages.
3. Un membre tente d'inviter quelqu'un ou de renommer le salon. **Attendu** : refus (seule la console
   en a le droit).
4. Après la durée choisie (purge chaque minute), les messages sont effacés **du serveur**. Element
   garde ceux déjà affichés dans son cache local : la preuve se fait sur le serveur, pas à l'écran.
   Test automatique (salon de 1 minute, vérifie le 404 et l'absence dans la table `events`) :
   ```sh
   python console/tests/test_confidentiel.py
   ```
   **Attendu** : quatre lignes `OK`, code 0 (environ 3 minutes).
5. **Journal d'audit** : `confidentiel-creation` (sujet, durée, membres) et `confidentiel-ajout`.

Limite : les copies déjà reçues restent sur les appareils (voir `docs/securite.md`).
