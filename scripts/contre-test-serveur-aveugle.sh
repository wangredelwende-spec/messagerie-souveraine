#!/usr/bin/env bash
# Contre-test : prouve que verifier-serveur-aveugle.sh détecte bien une chaîne qui EST en clair.
# Le nom d'un salon est un événement d'état non chiffré (Matrix ne chiffre que le contenu des
# messages) : le script doit donc le trouver dans la base et répondre par le code 1.
#
# Usage : scripts/contre-test-serveur-aveugle.sh ["chaîne en clair"]   (défaut : nom du canal Santé)
cd "$(dirname "$0")/.." || exit 2
TEMOIN=${1:-"Ministère de la Santé"}

scripts/verifier-serveur-aveugle.sh "$TEMOIN"
code=$?
echo
if [ "$code" -eq 1 ]; then
	echo "CONTRE-TEST RÉUSSI : « $TEMOIN », stocké en clair, a bien été détecté (code 1)."
	echo "Le script est donc capable de trouver une donnée en clair : son « introuvable » est fiable."
	exit 0
fi
echo "CONTRE-TEST ÉCHOUÉ : « $TEMOIN » n'a pas été détecté (code $code)." >&2
exit 1
