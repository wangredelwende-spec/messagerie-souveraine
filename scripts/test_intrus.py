"""Test d'intrusion : cinq tentatives d'entrée illégitimes, qui doivent TOUTES être refusées.

Lancé par scripts/test-intrus.sh. Comptes utilisés :
- stagiaire.sansrole (compte réel SANS le rôle agent) : son TOTP est remis à zéro avant et après ;
- un agent jetable « test.intrus.xxxxxx », désactivé dans Synapse et supprimé de Keycloak à la fin.
Aucun autre compte n'est touché.
"""
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "console" / "tests"))
import requests  # noqa: E402
from outils import (AUTH, MATRIX, MDP, connexion_keycloak, creer_comptes, kcadm,  # noqa: E402
                    session_matrix, supprimer_comptes)

STAGIAIRE, MDP_STAGIAIRE = "stagiaire.sansrole", "Stagiaire-Demo-2026!"
resultats = []


def verdict(titre, refuse, detail):
    resultats.append(refuse)
    print(f"{'REFUSÉ  (attendu)' if refuse else 'ACCEPTÉ (FAILLE !)'}  {titre}\n          {detail}")


def post_matrix(chemin, corps, jeton=None):
    entetes = {"Authorization": f"Bearer {jeton}"} if jeton else {}
    return requests.post(f"{MATRIX}{chemin}", json=corps, headers=entetes, verify=False, timeout=20)


def reinitialiser_stagiaire():
    """Supprime le TOTP du stagiaire et ferme ses sessions : il revient à l'état « première connexion »."""
    kcadm(f"ID=$($K get users $C -r administration -q username={STAGIAIRE} -q exact=true --fields id "
          "--format csv --noquotes) && for CID in $($K get users/$ID/credentials $C -r administration "
          "--fields id,type --format csv --noquotes | grep ',otp$' | cut -d, -f1); do "
          "$K delete users/$ID/credentials/$CID $C -r administration; done && "
          "$K update users/$ID $C -r administration -s 'requiredActions=[\"CONFIGURE_TOTP\"]' && "
          "$K create users/$ID/logout $C -r administration")


def salons_institutionnels():
    sortie = subprocess.run(
        ["docker", "compose", "exec", "-T", "console", "python", "-c",
         "import sqlite3; print('\\n'.join(r[0] for r in sqlite3.connect('/donnees/journal.sqlite3')"
         ".execute('SELECT room_id FROM canaux')))"], check=True, capture_output=True, text=True).stdout
    return sortie.split()


def main():
    print("=== Test d'intrusion de la messagerie ===\n")

    # 1. Création de compte sur Synapse
    r = post_matrix("/_matrix/client/v3/register",
                    {"username": "intrus", "password": "Intrus-2026!x", "auth": {"type": "m.login.dummy"}})
    verdict("1. Inscription d'un nouveau compte Matrix", r.status_code == 403 and "access_token" not in r.text,
            f"HTTP {r.status_code} {r.json().get('errcode')} : {r.json().get('error')}")

    # 2. Connexion Matrix par mot de passe (contournement de Keycloak et du TOTP)
    flux = [f["type"] for f in requests.get(f"{MATRIX}/_matrix/client/v3/login", verify=False).json()["flows"]]
    r = post_matrix("/_matrix/client/v3/login", {"type": "m.login.password", "password": MDP_STAGIAIRE,
                                                  "identifier": {"type": "m.id.user", "user": STAGIAIRE}})
    verdict("2. Connexion Matrix par mot de passe", r.status_code in (400, 403) and "access_token" not in r.text,
            f"HTTP {r.status_code} {r.json().get('errcode')} : {r.json().get('error')} "
            f"(méthodes proposées par Synapse : {', '.join(flux)})")

    # 3. Compte inexistant présenté à Keycloak
    s = requests.Session()
    s.verify = False
    r = s.get(f"{MATRIX}/_matrix/client/v3/login/sso/redirect/oidc-keycloak",
              params={"redirectUrl": "https://chat.messagerie.test/"})
    r = connexion_keycloak(s, r, "intrus.inconnu", "Nimporte-Quoi-2026!")
    verdict("3. Compte inexistant sur la page de connexion Keycloak",
            r.url.startswith(AUTH) and 'id="kc-form-login"' in r.text,
            "Keycloak réaffiche la page de connexion avec une erreur ; aucun jeton n'est émis")

    # 4. Compte valide dans Keycloak (mot de passe + TOTP) mais SANS le rôle agent
    reinitialiser_stagiaire()
    try:
        s = requests.Session()
        s.verify = False
        r = s.get(f"{MATRIX}/_matrix/client/v3/login/sso/redirect/oidc-keycloak",
                  params={"redirectUrl": "https://chat.messagerie.test/"})
        r = connexion_keycloak(s, r, STAGIAIRE, MDP_STAGIAIRE)
        sans_jeton = not parse_qs(urlparse(r.url).query).get("loginToken")
        # Message de Synapse quand attribute_requirements (roles = agent) n'est pas satisfait
        refus_role = "You are not allowed to log in here" in r.text
        verdict("4. Compte sans le rôle agent (stagiaire.sansrole, mot de passe et TOTP corrects)",
                sans_jeton and refus_role and r.url.startswith(MATRIX),
                f"Keycloak l'authentifie, puis Synapse refuse (HTTP {r.status_code}, « You are not allowed "
                "to log in here ») : rôle « agent » absent")
    finally:
        reinitialiser_stagiaire()

    # 5. Agent légitime qui tente d'entrer dans un canal où il n'est pas invité
    agent = f"test.intrus.{__import__('secrets').token_hex(3)}"
    creer_comptes([(agent, "agent")])
    try:
        jeton = session_matrix(agent, MDP)
        assert jeton, "l'agent jetable n'a pas pu se connecter"
        salons = salons_institutionnels()
        codes = [post_matrix(f"/_matrix/client/v3/join/{salon}", {}, jeton).status_code for salon in salons]
        verdict(f"5. Agent non invité qui tente d'entrer dans les {len(salons)} canaux institutionnels",
                bool(salons) and all(c == 403 for c in codes), f"réponses de Synapse : HTTP {codes}")
        post_matrix("/_matrix/client/v3/logout", {}, jeton)
    finally:
        supprimer_comptes([agent])

    print()
    if all(resultats):
        print(f"RÉSULTAT : les {len(resultats)} tentatives d'intrusion ont été refusées.")
        return 0
    print(f"RÉSULTAT : {resultats.count(False)} tentative(s) ont RÉUSSI : faille à corriger.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
