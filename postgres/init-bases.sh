#!/bin/bash
# Exécuté UNE SEULE FOIS par l'image postgres, quand le volume de données est vide.
# Crée deux bases séparées, chacune avec son propre utilisateur :
# Synapse ne peut pas lire la base de Keycloak, et inversement.
set -euo pipefail

# Les mots de passe sont passés comme variables psql (:'...'), ce qui les
# entoure de guillemets correctement, même s'ils contiennent une apostrophe.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" \
     -v mdp_synapse="$SYNAPSE_DB_PASSWORD" \
     -v mdp_keycloak="$KEYCLOAK_DB_PASSWORD" <<'SQL'
CREATE USER synapse WITH PASSWORD :'mdp_synapse';
-- Synapse exige l'interclassement « C » (tri octet par octet), d'où template0.
CREATE DATABASE synapse OWNER synapse ENCODING 'UTF8'
    LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;

CREATE USER keycloak WITH PASSWORD :'mdp_keycloak';
CREATE DATABASE keycloak OWNER keycloak;

-- Personne d'autre que le propriétaire ne peut se connecter à chaque base.
REVOKE CONNECT ON DATABASE synapse FROM PUBLIC;
REVOKE CONNECT ON DATABASE keycloak FROM PUBLIC;
SQL
