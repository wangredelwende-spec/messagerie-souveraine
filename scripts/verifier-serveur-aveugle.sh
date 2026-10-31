#!/usr/bin/env bash
# Preuve que le serveur est « aveugle » : la phrase donnée n'apparaît NULLE PART côté serveur,
# ni dans la base Synapse, ni dans les fichiers envoyés (médias), ni dans les journaux.
#
# Usage (depuis la racine du dépôt, la pile démarrée) :
#   scripts/verifier-serveur-aveugle.sh "Le colis de vaccins arrive mardi"
# Codes de sortie : 0 = introuvable (serveur aveugle), 1 = trouvée en clair, 2 = erreur.
#
# Toutes les recherches se font sur l'ordinateur hôte (la phrase n'est pas transmise aux conteneurs),
# sans tenir compte des majuscules, sous trois formes : texte UTF-8, texte échappé à la façon JSON
# (« è » devient \u00e8, comme dans les événements stockés par Synapse) et cette même forme avec
# les barres obliques doublées (format COPY du dump PostgreSQL).
set -uo pipefail
# Git Bash (Windows) : ne pas convertir /data/... en chemin Windows dans les commandes docker
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.." || exit 2
# Premier Python 3 qui s'exécute vraiment (sous Windows, « python3 » peut être un faux raccourci)
PYTHON=
for p in python3 python; do
	if "$p" -c 'import sys; sys.exit(sys.version_info < (3,))' >/dev/null 2>&1; then PYTHON=$p; break; fi
done
[ -n "$PYTHON" ] || { echo "Erreur : Python 3 est requis" >&2; exit 2; }

if [ $# -ne 1 ] || [ -z "$1" ]; then
	echo "Usage : $0 \"phrase à rechercher\"" >&2
	exit 2
fi
PHRASE=$1
trouvee=0

# Compte les lignes de l'entrée standard qui contiennent la phrase (sous l'une des trois formes)
compter() {
	PHRASE="$PHRASE" "$PYTHON" -c '
import json, os, sys
phrase = os.environ["PHRASE"].lower()
echappee = json.dumps(phrase)[1:-1]
formes = {f.encode() for f in (phrase, echappee, echappee.replace("\\", "\\\\"))}
print(sum(1 for ligne in sys.stdin.buffer if any(f in ligne.lower() for f in formes)))'
}

chercher() { # $1 = description de l'endroit ; la donnée arrive sur l'entrée standard
	local n
	# Une recherche qui échoue n'est JAMAIS comptée comme « absente »
	if ! n=$(compter) || ! [[ "$n" =~ ^[0-9]+$ ]]; then
		echo "Erreur : recherche impossible dans $1" >&2
		exit 2
	fi
	if [ "$n" -gt 0 ]; then
		echo "  TROUVÉE  $1 : $n ligne(s) contiennent la phrase en clair"
		trouvee=1
	else
		echo "  absente  $1"
	fi
}

echo "Recherche de « $PHRASE » côté serveur :"

dump=$(mktemp)
trap 'rm -f "$dump"' EXIT
if ! docker compose exec -T postgres pg_dump -U postgres --no-owner synapse >"$dump"; then
	echo "Erreur : impossible d'exporter la base Synapse (la pile est-elle démarrée ?)" >&2
	exit 2
fi
chercher "base de données Synapse (dump complet de $(wc -c <"$dump") octets)" <"$dump"

# Le dossier des médias est lu en archive tar : contenus des fichiers ET noms des fichiers
medias=$(mktemp)
trap 'rm -f "$dump" "$medias"' EXIT
if ! docker compose exec -T synapse tar -C /data/media_store -cf - . >"$medias"; then
	echo "Erreur : impossible de lire le dossier des médias de Synapse" >&2
	exit 2
fi
chercher "dossier des médias de Synapse ($(wc -c <"$medias") octets archivés)" <"$medias"

chercher "journaux de tous les conteneurs" < <(docker compose logs --no-color --no-log-prefix 2>&1)

echo
if [ "$trouvee" -eq 0 ]; then
	echo "RÉSULTAT : phrase introuvable. Le serveur ne détient que du contenu chiffré : il est aveugle."
	exit 0
fi
echo "RÉSULTAT : phrase TROUVÉE en clair côté serveur (voir ci-dessus)."
exit 1
