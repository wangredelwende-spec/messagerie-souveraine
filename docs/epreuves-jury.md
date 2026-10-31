# Épreuves du jury : déroulé en direct

3 épreuves sur 5 sont tirées au sort ; **8 minutes au total**, donc **moins de 3 minutes par épreuve**.
Toutes les commandes se tapent à la racine du dépôt, dans **Git Bash** (ou un terminal Linux/macOS).

## Préparation commune (la veille, puis 15 min avant)

1. Pile démarrée et saine : `docker compose up -d --wait` puis `docker compose ps` (tout « healthy »).
2. **Téléphones** : Aegis ou FreeOTP avec le code TOTP déjà enrôlé pour `awa.ouedraogo`,
   `boukary.zongo`, `mariam.kabore` et `admin.messagerie` (enrôlement à la première connexion).
3. **Agent sacrifiable pour l'épreuve 2** : le Départ est **définitif** (compte Matrix désactivé pour
   toujours). Enrôler avant le passage un agent dédié dans la console : prénom `Moussa`, nom `Démo`,
   ministère **Santé**, fonction `Infirmier`. Noter son mot de passe temporaire, faire sa première
   connexion (nouveau mot de passe + TOTP sur un téléphone). Il est automatiquement dans le canal Santé.
4. **Navigateurs**, un profil par personne (cookies séparés) :
   - Chrome : `awa.ouedraogo` sur https://chat.messagerie.test
   - Firefox : `boukary.zongo`
   - Edge : `moussa.demo` (l'agent sacrifiable)
   - Un 4e onglet (fenêtre privée) : console https://admin.messagerie.test avec `admin.messagerie`
5. Dans le **canal « Ministère de la Santé »** : quelques messages déjà échangés, dont la phrase témoin
   « Le colis de vaccins arrive mardi » et le fichier `note.txt` qui la contient.
6. Lancer une fois `scripts/test-intrus.sh` et `scripts/verifier-serveur-aveugle.sh "Le colis de vaccins arrive mardi"`
   pour vérifier que tout répond (et pour que Python, `requests`, `pyotp` soient prêts).

> Sous Git Bash, préfixer les commandes `docker compose exec` qui contiennent un chemin `/data/...`
> par `MSYS_NO_PATHCONV=1`, sinon Git Bash le transforme en chemin Windows. Les scripts le font déjà.

---

## Épreuve 1 : le serveur ne lit rien (≈ 3 min)

**Message à faire passer** : le serveur stocke et transporte uniquement du contenu chiffré ; les clés
ne quittent jamais les appareils des agents.

### a) Trafic réseau dans le navigateur (1 min)

1. Dans Chrome (awa), **F12** → onglet **Réseau** (Network) → filtre : `send`.
2. Écrire dans le canal Santé une phrase **dictée par le jury**, Entrée.
3. Cliquer la requête **`PUT …/rooms/!…/send/m.room.encrypted/…`** → onglet **Charge utile** (Payload).
4. **À l'écran** : `{"algorithm": "m.megolm.v1.aes-sha2", "ciphertext": "AwgAEp…", "session_id": "…", …}`.
   Le type est `m.room.encrypted`, il n'y a **aucun champ `body`** : la phrase n'est pas dans la requête.
5. Option fichier : envoyer un fichier, cliquer la requête **`POST …/_matrix/media/v3/upload`** :
   `Content-Type: application/octet-stream`, aucun nom de fichier, contenu binaire illisible.

### b) Base de données, médias et journaux (1 min 30)

```sh
scripts/verifier-serveur-aveugle.sh "<la phrase dictée par le jury>"
```
**À l'écran** : `absente` pour la base (dump complet), le dossier des médias et les journaux, puis
`RÉSULTAT : phrase introuvable…` (code 0).

**Contre-test** (prouve que le script sait trouver une donnée en clair) :
```sh
scripts/contre-test-serveur-aveugle.sh
```
**À l'écran** : `TROUVÉE base de données Synapse … : 9 ligne(s)` pour « Ministère de la Santé » (le nom
d'un salon est un événement d'état non chiffré), puis `CONTRE-TEST RÉUSSI`.

Si le jury veut voir la base de ses yeux :
```sh
docker compose exec -T postgres psql -U postgres -d synapse -c \
  "SELECT e.type, left(j.json, 200) FROM events e JOIN event_json j USING (event_id)
   WHERE e.type = 'm.room.encrypted' ORDER BY e.stream_ordering DESC LIMIT 2"
```
**À l'écran** : `m.room.encrypted` et un JSON ne contenant que `ciphertext`, `session_id`, `algorithm`.

### c) Option : trafic entre Caddy et Synapse dans le réseau Docker (non testé ici)

Capture avec un conteneur `tcpdump` jetable qui partage l'interface réseau de Synapse. L'image
`nicolaka/netshoot` doit être **téléchargée en préparation** (`docker pull nicolaka/netshoot:v0.13`) :
cette commande n'a pas encore été essayée sur la démo, la répéter avant le passage.
```sh
MSYS_NO_PATHCONV=1 docker run --rm --network container:messagerie-synapse-1 nicolaka/netshoot:v0.13 \
  tcpdump -i eth0 -A -s0 'tcp port 8008' | grep -a --line-buffered -E 'ciphertext|PUT /_matrix'
```
Puis envoyer un message : on voit passer `PUT /_matrix/client/v3/rooms/…/send/m.room.encrypted/…` et
`"ciphertext":"…"`, jamais la phrase. (Le HTTPS s'arrête à Caddy ; à l'intérieur, le message est
**toujours** chiffré de bout en bout.)

**À retenir** : ce que le serveur voit quand même (expéditeur, salon, heure, taille des fichiers) est
détaillé dans `docs/metadonnees-medias.md`. Le dire avant que le jury le demande.

---

## Épreuve 2 : révocation pendant une conversation de groupe (≈ 2 min 30)

**Scénario** : awa, boukary et moussa.demo discutent dans le canal Santé. Le jury désigne moussa.demo
(proposer l'agent sacrifiable ; un Départ ne s'annule pas).

1. Les trois agents s'envoient un message chacun (montrer les trois écrans).
2. Console (`admin.messagerie`) → **Annuaire** → Ministère de la Santé → `moussa.demo` →
   **Départ de l'agent** → la page liste les effets → **Confirmer**.
3. **À l'écran** (console) : « Compte Keycloak désactivé, sessions fermées », « Compte Matrix
   @moussa.demo:messagerie.test désactivé », statut **Révoqué**.
4. **À l'écran** (Edge, moussa.demo) : en quelques secondes Element affiche que la session est
   terminée (son jeton a été supprimé : le serveur répond 401 à sa synchronisation).
5. awa écrit un nouveau message. **À l'écran** : awa et boukary le voient ; dans le canal, l'événement
   « Moussa Démo a quitté le salon » est affiché.
6. moussa.demo tente de se reconnecter sur https://chat.messagerie.test : Keycloak refuse
   (« compte désactivé »).
7. Console → **Journal d'audit** : ligne `admin.messagerie | depart | moussa.demo | ok` avec l'heure.

**Pourquoi les nouveaux messages lui sont illisibles** (à dire en 30 s) :
- **Côté serveur** : `synapse.desactiver` supprime ses jetons et appareils et le fait sortir de tous
  les salons. Il ne peut même plus télécharger les messages chiffrés.
- **Côté chiffrement** : chaque salon chiffre les messages avec une **session Megolm** (une clé de
  groupe qui avance à chaque message). Quand un membre **quitte** le salon, Element jette sa session
  sortante et en crée une **nouvelle**, dont la clé n'est envoyée (via Olm, appareil par appareil)
  qu'aux appareils des membres **restants**. Même s'il avait gardé une copie des anciennes clés ou des
  messages chiffrés, il ne pourrait pas déchiffrer les messages écrits après son départ.
- **Côté identité** : son compte Keycloak est désactivé, il ne peut pas obtenir de nouvelle session.

Variante « Perte d'appareil » (si le jury la demande) : même parcours avec le bouton **Perte
d'appareil** ; le compte est **suspendu** (pas révoqué) et le bouton **Réactiver** donne un mot de
passe temporaire affiché une seule fois, avec nouvel enrôlement TOTP obligatoire.

---

## Épreuve 3 : un intrus tente d'entrer (≈ 2 min)

```sh
scripts/test-intrus.sh
```
**À l'écran** (≈ 1 min) :
```
REFUSÉ  (attendu)  1. Inscription d'un nouveau compte Matrix          HTTP 403 M_FORBIDDEN
REFUSÉ  (attendu)  2. Connexion Matrix par mot de passe              HTTP 400 Password login has been disabled
REFUSÉ  (attendu)  3. Compte inexistant sur la page de connexion Keycloak
REFUSÉ  (attendu)  4. Compte sans le rôle agent (stagiaire.sansrole) « You are not allowed to log in here »
REFUSÉ  (attendu)  5. Agent non invité … canaux institutionnels      HTTP [403, 403, 403]
RÉSULTAT : les 5 tentatives d'intrusion ont été refusées.
```

En direct, à la main (si le jury le préfère) :
1. **Compte non enrôlé** : fenêtre privée → https://chat.messagerie.test → saisir `intrus` / n'importe
   quel mot de passe → **À l'écran** : Keycloak refuse (identifiant ou mot de passe invalide).
   Il n'existe ni bouton d'inscription ni lien « mot de passe oublié ».
2. **Agent non invité dans un groupe** : console → **Canaux** → copier l'identifiant `!…` du canal
   Santé. Dans Firefox, se connecter en `mariam.kabore` (ministère Numérique) et taper dans un salon
   `/join !…:messagerie.test` → **À l'écran** : refus (« vous n'êtes pas invité »).

Expliquer : l'entrée passe obligatoirement par Keycloak (mot de passe **et** TOTP), puis Synapse exige
le rôle `agent` ; les canaux sont sur invitation et seule la console ajoute des membres.

---

## Épreuve 4 : innovation, la console d'administration (≈ 3 min)

1. https://admin.messagerie.test → connexion `admin.messagerie` + code TOTP.
   **À dire** : seul le rôle `admin-messagerie` entre ; la console n'a aucun JavaScript.
2. **Écrans en mooré** (20 s) : sur la page de connexion Keycloak, sélecteur de langue → **Mooré**,
   montrer les libellés traduits, revenir en français.
3. **Enrôler un agent** : prénom `Fatimata`, nom `Ouédraogo-Démo`, ministère **Économie et Finances**,
   fonction `Comptable` → **Enrôler**. **À l'écran** : identifiant `fatimata.ouedraogo-demo` (sans
   accents), mot de passe temporaire **affiché une seule fois**, « Canal du ministère : ajouté ».
4. **Canaux** : le canal Économie et Finances liste désormais l'agent ; aucun « manquant ».
5. **Annuaire** : l'agent apparaît sous son ministère, avec sa fonction et le statut **Actif**.
6. **Révocation en un clic** : sur sa fiche → **Perte d'appareil** → **Confirmer** → statut **Suspendu**
   (TOTP supprimé, appareils Matrix supprimés, sessions fermées).
7. **Journal d'audit** : `enrolement`, `canal-ajout`, `perte-appareil`, avec administrateur, heure et
   agent. **À dire** : journal en ajout seul (la base refuse toute modification), aucun contenu de message.

---

### Option : salon « Confidentiel » à expiration automatique (≈ 1 min 30, plus 5 min d'attente)

Répond à l'exigence du ministère « niveaux de classification… expiration automatique ».
**Préparation** : créer le salon **5 à 6 minutes avant** le passage, pour montrer l'effacement en direct.

1. Console → **Canaux** → « Créer un salon Confidentiel » : sujet `Réunion logistique`, durée
   **5 minutes (démonstration)**, cocher `awa.ouedraogo` et `boukary.zongo` → **Créer le salon**.
   **À l'écran** : « Salon « [CONFIDENTIEL] Réunion logistique » créé… 2 membre(s) », puis le salon dans
   le tableau avec sa durée.
2. Dans Element (awa) : le salon apparaît, son sujet annonce « messages effacés automatiquement après
   5 minutes ». awa écrit deux messages.
3. Montrer le verrouillage : awa tente d'inviter quelqu'un ou de renommer le salon → refusé (seule la
   console en a le droit).
4. Après 5 minutes (purge chaque minute) : les messages disparaissent de l'historique et de la base.
   Preuve automatique (≈ 3 min, salon de 1 minute) : `python console/tests/test_confidentiel.py`.
5. **Journal d'audit** : `confidentiel-creation` (sujet, durée, membres) et `confidentiel-ajout`.

**À dire** : le serveur purge les messages chiffrés expirés, mais les copies déjà reçues restent sur
les appareils (limites dans `docs/elements-securite.md`).

---

## Épreuve 5 : explication du code (≈ 2 min par fonction)

Le jury désigne la fonction **et** la personne qui l'explique : chaque membre doit connaître toute la
liste. Ouvrir le fichier à la bonne ligne dans l'éditeur, puis expliquer en 3-4 phrases.

### Connexion OIDC de Synapse et `attribute_requirements`
`synapse/homeserver.yaml`, lignes 98-126 (`attribute_requirements` : lignes 117-119).
Synapse ne gère aucun mot de passe : il délègue la connexion à Keycloak par OpenID Connect. Le
navigateur va sur l'adresse publique de Keycloak, mais Synapse échange le code contre un jeton par le
réseau Docker interne (`http://keycloak:8080`), avec PKCE pour qu'un code volé soit inutilisable.
`attribute_requirements` vérifie que le jeton contient le rôle `agent` : sinon, refus (« You are not
allowed to log in here »), même avec un mot de passe et un TOTP corrects.

### Flux OTP de Keycloak
`keycloak/realm-administration.json`, lignes 57-81 (politique TOTP : lignes 25-29 ; anti-force brute : ligne 14).
Le flux de connexion `navigateur-otp-obligatoire` accepte soit une session déjà ouverte, soit le
sous-flux `mot-de-passe-puis-otp`, où mot de passe **et** code TOTP sont tous deux `REQUIRED` : il n'y a
pas d'OTP « conditionnel » qu'on pourrait contourner. Le TOTP est un code à 6 chiffres qui change toutes
les 30 s, calculé par l'application du téléphone à partir d'un secret partagé à l'enrôlement. Après 5
échecs, le compte est bloqué temporairement.

### `keycloak.suspendre`
`console/app/keycloak.py`, lignes 86-89 (utilise `_modifier`, lignes 80-84).
La fonction relit la fiche complète de l'agent, passe `enabled` à faux et la renvoie (un envoi partiel
risquerait d'effacer des attributs). Elle ferme ensuite toutes ses sessions Keycloak ouvertes. Résultat :
plus aucune connexion n'est possible et une session en cours ne peut plus être renouvelée. Elle sert
au Départ comme à la Perte d'appareil.

### `synapse.desactiver`
`console/app/synapse.py`, lignes 98-104.
Elle vérifie d'abord que le compte Matrix existe (un agent qui ne s'est jamais connecté n'en a pas).
Puis elle appelle l'API d'administration `POST /_synapse/admin/v1/deactivate/<id>` : Synapse supprime
tous ses jetons et appareils et le fait sortir de tous les salons. La sortie des salons déclenche, chez
les autres membres, la rotation de la clé Megolm (voir épreuve 2).

### `synapse._enregistrer` et son HMAC
`console/app/synapse.py`, lignes 33-51 (appelée par `demarrer`, lignes 25-31).
Au premier démarrage, la console crée son compte de service administrateur sur Synapse. Synapse fournit
un nonce (valeur à usage unique) ; la console signe « nonce, identifiant, mot de passe, admin » avec un
HMAC-SHA1 dont la clé est le secret partagé (`SYNAPSE_REGISTRATION_SECRET`). Synapse refait le calcul :
s'il obtient la même signature, la demande vient bien de quelqu'un qui connaît le secret. C'est le
**seul** HMAC écrit dans le dépôt ; le compte ne publie jamais de clés de chiffrement, donc il ne peut
lire aucun message.

### Blocage par Caddy
`caddy/Caddyfile`, lignes 53-62.
Caddy est la seule porte d'entrée. Pour `auth.messagerie.test`, toute adresse qui commence par `/admin`
(console technique de Keycloak) ou `/realms/master` (realm des super-administrateurs) reçoit un 404
avant d'atteindre Keycloak ; le reste (connexion des agents) est transmis. La comparaison se fait après
décodage du chemin et sans tenir compte des majuscules (`/ADMIN`, `/%61dmin`, `//admin` sont aussi
bloqués). L'administration ne passe que par le réseau Docker interne.

### Chiffrement Olm / Megolm côté Element
Pas de code dans le dépôt : Element est l'image officielle (`vectorim/element-web`), qui chiffre dans le
navigateur avec la bibliothèque `matrix-rust-sdk-crypto` (WebAssembly). Côté dépôt : chiffrement imposé
dans tous les salons (`synapse/homeserver.yaml`, ligne 55) et canaux créés chiffrés (`console/app/synapse.py`,
`creer_canal`, lignes 69-87).
**Olm** relie deux **appareils** (échange de clés Curve25519 puis « double ratchet ») : il sert à
transporter les clés de groupe. **Megolm** chiffre les **messages d'un salon** (AES-256 + HMAC-SHA256) avec
une clé qui avance à chaque message ; chaque appareil reçoit cette clé par Olm. Les fichiers sont
chiffrés en AES-256-CTR avec une clé placée dans le message chiffré. Le serveur ne reçoit jamais
aucune de ces clés.

### Autres fonctions possibles
- Contrôle d'accès à la console : `console/app/main.py`, `oauth.register` lignes 49-59 et
  `retour_keycloak` lignes 181-194 (refus si le rôle `admin-messagerie` est absent).
- Pré-création du compte Matrix lié à Keycloak : `console/app/synapse.py`, `creer_compte` lignes 60-67
  (`external_ids` : Synapse retrouve l'agent par son `sub` Keycloak à sa première connexion).
