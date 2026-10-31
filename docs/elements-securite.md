# Éléments pour la note de sécurité

Matière brute pour la note de sécurité (2 pages maximum à rendre). Tout ce qui suit a été construit **et testé** sur le prototype. À condenser : garder les menaces, les protections avec leur preuve, les métadonnées et les limites.

---

## 1. Architecture en 3 lignes

- **Element Web** (client dans le navigateur) → **Caddy** (HTTPS, autorité de certification interne) → **Synapse** (serveur Matrix) + **PostgreSQL**.
- **Keycloak** gère les identités (mot de passe + code TOTP, rôles) ; la **console d'administration** enrôle et révoque les agents.
- Tout tourne dans un réseau Docker **interne, sans accès à Internet**. Seul Caddy est exposé (port 443).

---

## 2. Menaces prises en compte

| # | Menace |
|---|---|
| M1 | Serveur curieux ou compromis (administrateur indiscret, intrus sur la machine, saisie du serveur) qui veut lire messages et fichiers |
| M2 | Écoute du réseau (Wi-Fi public, opérateur) |
| M3 | Intrus non enrôlé : inscription libre, compte inventé, compte sans habilitation, entrée dans un groupe sans invitation |
| M4 | Vol ou devinette du mot de passe (hameçonnage, réutilisation, force brute) |
| M5 | Agent qui quitte l'administration, ou qui perd son téléphone |
| M6 | Fuite de données vers des services tiers (Google, matrix.org, statistiques, rapports d'erreurs…) |
| M7 | Administrateur malveillant ou erreur d'administration |
| M8 | Quelqu'un qui a volé une session et veut remplacer les clés de chiffrement d'un agent |

---

## 3. Protections mises en place

**M1, serveur aveugle.**
- Chiffrement de bout en bout Matrix, avec deux protocoles open source exécutés dans le navigateur par Element :
  - **Olm** : échange de clés entre appareils, double ratchet ;
  - **Megolm** : clés de groupe.
- Aucune cryptographie écrite par l'équipe.
- Chiffrement activé d'office dans **tous** les salons (`encryption_enabled_by_default_for_room_type: all`).
- Fichiers chiffrés (AES-256) dans le navigateur avant l'envoi ; le serveur ne connaît ni leur nom ni leur vrai type.
- *Preuve :* `scripts/verifier-serveur-aveugle.sh`. La phrase témoin est introuvable dans la base, les fichiers et les journaux. Le contre-test montre que le script détecte bien une donnée stockée en clair.

**M2, réseau.**
- HTTPS obligatoire (HSTS) via Caddy.
- Même déchiffré par un intermédiaire, le contenu reste chiffré de bout en bout.

**M3, intrus.**
- Inscription désactivée, connexion Matrix par mot de passe désactivée : on n'entre que par Keycloak.
- Comptes créés uniquement par un administrateur.
- Synapse refuse tout compte sans le rôle `agent`, même authentifié (`attribute_requirements`).
- Canaux sur invitation uniquement.
- *Preuve :* `scripts/test-intrus.sh`, 5 tentatives sur 5 refusées.

**M4, mot de passe volé.**
- Second facteur TOTP **obligatoire pour tous**, sans exception (applications open source Aegis ou FreeOTP).
- Mot de passe de 12 caractères minimum, avec majuscule, minuscule, chiffre et caractère spécial ; les 3 derniers ne peuvent pas être réutilisés.
- Blocage progressif après 5 échecs.

**M5, départ ou perte d'appareil, via la console.**
- **Départ :**
  - le compte Keycloak est désactivé et ses sessions sont fermées ;
  - le compte Matrix est désactivé : jetons et appareils supprimés, sortie de tous les salons ;
  - les autres appareils changent alors la clé Megolm, donc les nouveaux messages lui sont illisibles.
- **Perte d'appareil :**
  - le compte est suspendu, son TOTP supprimé et tous ses appareils Matrix supprimés ;
  - la réactivation par un administrateur impose un mot de passe temporaire, un nouveau mot de passe (l'ancien est refusé) et un nouveau TOTP ;
  - le nouvel appareil ne peut pas lire les anciens messages sans la clé de récupération.

**M6, services tiers.**
- Réseau interne sans sortie vers Internet.
- Synapse :
  - fédération coupée ;
  - aucun serveur de clés externe ;
  - pas de statistiques, pas d'aperçus de liens, pas de notifications push.
- Element : intégrations, Jitsi, Element Call, cartes et rapports de bug désactivés.
- Politique de sécurité du contenu (CSP) qui bloque tout domaine externe dans le navigateur.
- Certificats émis par une autorité interne (pas de Let's Encrypt).
- *Preuve :* dans l'outil réseau du navigateur, aucune requête hors `*.messagerie.test`, et aucune violation CSP.

**M7, administrateurs.**
- Console réservée au rôle `admin-messagerie`, avec TOTP.
- Confirmation et protection CSRF sur chaque action ; un administrateur ne peut pas agir sur son propre compte.
- Journal d'audit **en ajout seul** (modification et suppression bloquées) : qui, quoi, quand, sur quel agent, jamais de contenu de message.
- API d'administration de Synapse et console de Keycloak **non publiées** (404 depuis l'extérieur).

**M8, remplacement des clés.**
- Réinitialiser l'identité de chiffrement d'un compte exige une nouvelle authentification Keycloak (mot de passe + TOTP).

**Le compte de service de la console.** Il est membre des canaux pour pouvoir y ajouter des agents, mais il ne publie aucune clé de chiffrement. Aucun appareil ne lui envoie donc de clé Megolm : il ne peut rien déchiffrer.

---

## 4. Métadonnées : ce que le serveur voit malgré tout

**Ce qui reste visible :**
- qui est membre de quel salon, qui invite qui, qui écrit dans quel salon et à quelle heure ;
- la **taille** des messages et la **taille exacte** des fichiers : le chiffrement AES-CTR ne rembourre pas, donc le fichier témoin de 32 octets correspond exactement à la longueur de la phrase ;
- les **noms des salons**, les noms affichés et les identifiants, qui ne sont pas chiffrés en Matrix (le contre-test retrouve « Ministère de la Santé » en clair) ;
- les adresses IP et les appareils de connexion ;
- les accusés de lecture et les indicateurs « en train d'écrire », non chiffrés en Matrix ;
- une empreinte SHA-256 de chaque fichier chiffré.

**Mesures pour réduire ces métadonnées :**
- fédération coupée : ces métadonnées ne quittent jamais le serveur de l'État ;
- adresses IP conservées **1 jour** au lieu de 28 ;
- journaux Synapse réduits au niveau « avertissement » (pas de trace de chaque requête) ;
- indicateur de présence « en ligne » désactivé ;
- profils visibles seulement entre agents qui partagent un salon ;
- salons oubliés dès qu'on les quitte ;
- canaux institutionnels : historique visible seulement à partir de l'arrivée ;
- consigne d'usage : noms de salons neutres.

---

## 5. Limites connues

- **Appareil volé encore ouvert :** ce qui est déjà affiché ou stocké sur l'appareil reste lisible. La révocation coupe l'accès au serveur et aux nouveaux messages, mais il n'y a pas d'effacement à distance.
- **Captures d'écran :** impossible à empêcher dans un navigateur.
- **Client web :**
  - les clés sont stockées dans le navigateur, qui peut les effacer s'il manque de place, ce qui oblige l'agent à se reconnecter ;
  - un poste infecté (virus, extension malveillante) compromet les messages ;
  - Element Web est servi par le serveur lui-même : un serveur compromis pourrait servir un client modifié.
  - En production : application de bureau ou mobile signée.
- **Salons « Confidentiel » à expiration automatique :** l'effacement porte sur le serveur.
  - Dans un navigateur, impossible de bloquer les captures d'écran, les copier-coller et les transferts.
  - Les copies déjà reçues restent sur les appareils des membres (Element ne les efface pas tout seul).
  - Synapse ne supprime jamais le dernier message d'un salon : il le cache seulement (il reste
    chiffré en base jusqu'à l'arrivée d'un message plus récent).
  - Le sujet du salon (« [CONFIDENTIEL] … ») est visible du serveur : il doit rester neutre.
- **Métadonnées** de la section 4, non chiffrées par nature dans Matrix.
- **Vérification des appareils** laissée aux agents : sans vérification croisée, on fait confiance au serveur pour la liste des appareils d'un collègue.
- **Canal interne Synapse ↔ Keycloak en HTTP**, dans le réseau Docker non exposé. En production : TLS interne avec l'infrastructure de clés de l'État.
- **Autorité de certification interne de Caddy :** en production, la remplacer par l'infrastructure de clés de l'État ; le certificat racine doit être installé sur chaque poste.
- **Sauvegarde des clés sur le serveur :** chiffrée dans le navigateur et illisible par le serveur. Mais si l'agent perd sa clé de récupération, son historique est perdu.
- **Prototype :**
  - secrets de démonstration à remplacer ;
  - un seul serveur, sans haute disponibilité ni sauvegarde automatique ;
  - limite de connexions de Synapse assouplie (le jeton de connexion est à usage unique, et la force brute est bloquée par Keycloak).
