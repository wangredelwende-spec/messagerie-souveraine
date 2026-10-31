#!/usr/bin/env bash
# Test d'intrusion : cinq tentatives d'entrée illégitimes, toutes doivent être refusées.
#   1. inscription Matrix          2. connexion Matrix par mot de passe
#   3. compte inexistant (Keycloak) 4. compte sans le rôle agent (refusé par Synapse)
#   5. agent non invité qui tente d'entrer dans un canal institutionnel
# Usage (racine du dépôt, pile démarrée) :  scripts/test-intrus.sh
# Prérequis : Python 3 avec requests et pyotp (pip install -r console/tests/requirements.txt).
# Codes de sortie : 0 = tout est refusé, 1 = au moins une intrusion a réussi, 2 = erreur.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.." || exit 2
for p in python3 python; do
	if "$p" -c 'import sys; sys.exit(sys.version_info < (3,))' >/dev/null 2>&1; then
		"$p" scripts/test_intrus.py
		code=$?
		[ "$code" -le 1 ] || exit 2
		exit "$code"
	fi
done
echo "Erreur : Python 3 est requis" >&2
exit 2
