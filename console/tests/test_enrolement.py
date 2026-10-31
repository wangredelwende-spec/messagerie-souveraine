"""Test de bout en bout de l'enrôlement et de l'annuaire.

Depuis la racine du dépôt :  python console/tests/test_enrolement.py
L'administrateur et l'agent créés sont supprimés de Keycloak à la fin ; le compte Matrix de l'agent reste.
"""
import re
import secrets
import subprocess

from outils import (CONSOLE, connexion_console, creer_comptes, csrf, mot_de_passe_affiche,
                    session_matrix, supprimer_comptes, whoami)

SUFFIXE = secrets.token_hex(3)
ADMIN = f"test.admin.{SUFFIXE}"
PRENOM, NOM = "Aïcha", f"Traoré-Test {SUFFIXE}"
ATTENDU = f"aicha.traore-test-{SUFFIXE}"   # identifiant sans accents ni espaces


def main():
    creer_comptes([(ADMIN, "admin-messagerie")])
    noms = [ADMIN]
    try:
        console = connexion_console(ADMIN)
        formulaire = console.get(f"{CONSOLE}/enroler").text
        sante = re.search(r'<option value="([0-9a-f-]{36})"[^>]*>Ministère de la Santé<', formulaire).group(1)
        r = console.post(f"{CONSOLE}/enroler", data={"csrf": csrf(formulaire), "prenom": PRENOM, "nom": NOM,
                                                     "ministere": sante, "fonction": "Sage-femme"})
        assert r.status_code == 200, (r.status_code, r.text)
        identifiant = re.search(r'<code id="identifiant">([^<]+)</code>', r.text).group(1)
        noms.append(identifiant)
        assert identifiant == ATTENDU, identifiant
        print(f"OK  enrôlement : identifiant {identifiant}, mot de passe temporaire affiché")

        # Compte Matrix pré-créé et lié à Keycloak avant toute connexion de l'agent
        compte = subprocess.run(
            ["docker", "compose", "exec", "-T", "console", "python", "-c",
             "import httpx; j = open('/donnees/synapse_jeton').read().strip(); "
             f"print(httpx.get('http://synapse:8008/_synapse/admin/v2/users/@{identifiant}:messagerie.test', "
             "headers={'Authorization': 'Bearer ' + j}).text)"], check=True, capture_output=True, text=True).stdout
        assert '"auth_provider":"oidc-keycloak"' in compte.replace(" ", ""), compte
        jeton = session_matrix(identifiant, mot_de_passe_affiche(r.text), "Nouveau-Demo-2026!")
        assert jeton and whoami(jeton).json()["user_id"] == f"@{identifiant}:messagerie.test"
        print("OK  première connexion : mot de passe changé, TOTP enrôlé, compte Matrix pré-créé ouvert")

        annuaire = console.get(f"{CONSOLE}/").text
        section = annuaire.split("<h2>Ministère de la Santé</h2>")[1].split("<h2>")[0]
        assert re.search(r"<td>Sage-femme</td>\s*<td>Aïcha Traoré-Test %s</td>\s*<td><a [^>]*>%s</a></td>\s*"
                         r'<td><span class="statut actif">Actif</span>' % (SUFFIXE, identifiant), section)
        print("OK  annuaire : agent listé dans son ministère, avec sa fonction et le statut Actif")
    finally:
        supprimer_comptes(noms)


if __name__ == "__main__":
    main()
