"""Test de bout en bout de l'enrôlement, de l'annuaire et des canaux institutionnels.

Depuis la racine du dépôt :  python console/tests/test_enrolement.py
À la fin, les comptes créés sont désactivés dans Synapse et supprimés de Keycloak.
"""
import re
import secrets
import subprocess

import requests

from outils import (CONSOLE, MATRIX, connexion_console, creer_comptes, csrf, mot_de_passe_affiche,
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

        canaux = console.get(f"{CONSOLE}/canaux").text
        ligne = re.search(r"<td>Ministère de la Santé</td>\s*<td><code>([^<]+)</code>.*?</tr>", canaux, re.S)
        salon = ligne.group(1)
        assert salon in requests.get(f"{MATRIX}/_matrix/client/v3/joined_rooms", verify=False,
                                     headers={"Authorization": f"Bearer {jeton}"}).json()["joined_rooms"]
        def etat(type_):
            return requests.get(f"{MATRIX}/_matrix/client/v3/rooms/{salon}/state/{type_}", verify=False,
                                headers={"Authorization": f"Bearer {jeton}"}).json()
        assert etat("m.room.encryption")["algorithm"] == "m.megolm.v1.aes-sha2"
        assert etat("m.room.history_visibility")["history_visibility"] == "joined"
        assert etat("m.room.join_rules")["join_rule"] == "invite"
        print("OK  canal du ministère : agent membre, salon chiffré Megolm, sur invitation, historique « joined »")

        if "/synchroniser" in ligne.group(0):
            id_sante = re.search(r'action="/canaux/([0-9a-f-]{36})/synchroniser"', ligne.group(0)).group(1)
            r = console.post(f"{CONSOLE}/canaux/{id_sante}/synchroniser", data={"csrf": csrf(canaux)})
            assert "agent(s) ajouté(s)" in r.text
        ligne = re.search(r"<td>Ministère de la Santé</td>.*?</tr>", console.get(f"{CONSOLE}/canaux").text, re.S)
        assert "/synchroniser" not in ligne.group(0)
        print("OK  synchronisation : tous les agents actifs de la Santé sont dans le canal")
    finally:
        supprimer_comptes(noms)


if __name__ == "__main__":
    main()
