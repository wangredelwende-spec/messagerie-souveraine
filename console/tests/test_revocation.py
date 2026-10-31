"""Test de bout en bout de la révocation : Perte d'appareil, Réactiver, Départ, journal d'audit.

Prérequis : la pile tourne (docker compose up -d --wait) et le fichier hosts est configuré.
Depuis la racine du dépôt :
    pip install -r console/tests/requirements.txt
    python console/tests/test_revocation.py

Le test crée des comptes jetables (suffixe aléatoire) et les supprime de Keycloak à la fin ;
les comptes Matrix correspondants restent dans Synapse (désactivés ou sans appareil).
"""
import re
import secrets

import requests

from outils import (CONSOLE, MATRIX, MDP, connexion_console, creer_comptes, csrf, etape, mot_de_passe_affiche,
                    session_matrix, supprimer_comptes, whoami)

SUFFIXE = secrets.token_hex(3)
ADMIN, PERTE, DEPART = (f"test.{r}.{SUFFIXE}" for r in ("admin", "perte", "depart"))


def main():
    creer_comptes([(ADMIN, "admin-messagerie"), (PERTE, "agent"), (DEPART, "agent")])
    try:
        jeton_perte, jeton_depart = session_matrix(PERTE, MDP), session_matrix(DEPART, MDP)
        assert jeton_perte and jeton_depart
        etape("deux agents connectés à la messagerie")

        console = connexion_console(ADMIN)
        etape("administrateur connecté à la console")

        def agir(nom, action):
            id_agent = re.search(r'href="/agents/([0-9a-f-]{36})">%s<' % re.escape(nom),
                                 console.get(f"{CONSOLE}/").text).group(1)
            confirmation = console.get(f"{CONSOLE}/agents/{id_agent}/{action}")
            r = console.post(f"{CONSOLE}/agents/{id_agent}/{action}", data={"csrf": csrf(confirmation.text)})
            assert r.status_code == 200, (r.status_code, r.text)
            return r

        assert "Suspendu" in agir(PERTE, "perte-appareil").text
        assert whoami(jeton_perte).status_code == 401
        assert session_matrix(PERTE, MDP) is None
        etape("perte d'appareil : jeton Matrix invalidé, connexion refusée")

        r = agir(PERTE, "reactiver")
        temporaire = mot_de_passe_affiche(r.text)
        nouveau = session_matrix(PERTE, temporaire, "Nouveau-Demo-2026!")
        assert nouveau and whoami(nouveau).json()["user_id"] == f"@{PERTE}:messagerie.test"
        etape("réactivation : mot de passe temporaire changé, nouveau TOTP, même compte Matrix")
        requests.post(f"{MATRIX}/_matrix/client/v3/logout", verify=False,
                      headers={"Authorization": f"Bearer {nouveau}"})

        assert "Révoqué" in agir(DEPART, "depart").text
        assert whoami(jeton_depart).status_code == 401
        assert session_matrix(DEPART, MDP) is None
        etape("départ : compte Matrix désactivé, connexion refusée")

        journal = console.get(f"{CONSOLE}/journal").text
        for action, cible in (("perte-appareil", PERTE), ("reactivation", PERTE), ("depart", DEPART)):
            assert re.search(rf"<td>{re.escape(ADMIN)}</td><td>{action}</td><td>{re.escape(cible)}</td><td>ok</td>",
                             journal), action
        etape("journal d'audit : les trois actions sont tracées")
    finally:
        supprimer_comptes([ADMIN, PERTE, DEPART])


if __name__ == "__main__":
    main()
