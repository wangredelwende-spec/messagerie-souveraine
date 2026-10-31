"""Test de bout en bout de la révocation : Perte d'appareil, Réactiver, Départ, journal d'audit.

Prérequis : la pile tourne (docker compose up -d --wait) et le fichier hosts est configuré.
Depuis la racine du dépôt :
    pip install -r console/tests/requirements.txt
    python console/tests/test_revocation.py

Le test crée des comptes jetables (suffixe aléatoire) et les supprime de Keycloak à la fin ;
les comptes Matrix correspondants restent dans Synapse (désactivés ou sans appareil).
"""
import base64
import html
import re
import secrets
import subprocess
from urllib.parse import parse_qs, urlparse

import pyotp
import requests
import urllib3

urllib3.disable_warnings()  # certificats signés par la CA interne de Caddy
AUTH = "https://auth.messagerie.test/"
MATRIX = "https://matrix.messagerie.test"
CONSOLE = "https://admin.messagerie.test"
SUFFIXE = secrets.token_hex(3)
ADMIN, PERTE, DEPART = (f"test.{r}.{SUFFIXE}" for r in ("admin", "perte", "depart"))
MDP = "Test-Demo-2026!"


def kcadm(commandes: str) -> str:
    """Commandes kcadm dans le conteneur Keycloak, par le réseau interne (l'API admin n'est pas publiée)."""
    script = ('K=/opt/keycloak/bin/kcadm.sh; C="--config /tmp/test.cfg"; '
              '($K config credentials $C --server http://keycloak:8080 --realm master --user admin '
              f'--password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null && {commandes}); s=$?; rm -f /tmp/test.cfg; exit $s')
    return subprocess.run(["docker", "compose", "exec", "-T", "keycloak", "bash", "-c", script],
                          check=True, capture_output=True, text=True).stdout


def creer_comptes():
    commandes = []
    for nom, role in ((ADMIN, "admin-messagerie"), (PERTE, "agent"), (DEPART, "agent")):
        commandes += [
            f"$K create users $C -r administration -s username={nom} -s enabled=true -s firstName=Test "
            f"-s lastName=Revocation -s 'requiredActions=[\"CONFIGURE_TOTP\"]'",
            f"$K set-password $C -r administration --username {nom} --new-password '{MDP}'",
            f"$K add-roles $C -r administration --uusername {nom} --rolename {role}",
        ]
    kcadm(" && ".join(commandes))


def supprimer_comptes():
    kcadm(" ; ".join(
        f"$K delete users/$($K get users $C -r administration -q username={nom} -q exact=true "
        f"--fields id --format csv --noquotes) $C -r administration" for nom in (ADMIN, PERTE, DEPART)))


def action_formulaire(page: str, id_formulaire: str) -> str:
    m = re.search(r'<form[^>]*id="%s"[^>]*action="([^"]+)"' % id_formulaire, page) or \
        re.search(r'<form[^>]*action="([^"]+)"[^>]*id="%s"' % id_formulaire, page)
    assert m, f"formulaire {id_formulaire} introuvable"
    return html.unescape(m.group(1))


def connexion_keycloak(s, r, nom, mdp, nouveau_mdp=None):
    """Remplit les pages Keycloak (mot de passe, changement de mot de passe, enrôlement TOTP)."""
    deja_essaye = False
    while r.url.startswith(AUTH):
        page = r.text
        if 'id="kc-form-login"' in page:
            if deja_essaye:
                return r  # identifiants refusés ou compte désactivé
            deja_essaye = True
            r = s.post(action_formulaire(page, "kc-form-login"),
                       data={"username": nom, "password": mdp, "credentialId": ""})
        elif 'id="kc-passwd-update-form"' in page:
            r = s.post(action_formulaire(page, "kc-passwd-update-form"),
                       data={"password-new": nouveau_mdp, "password-confirm": nouveau_mdp})
        elif 'id="kc-totp-settings-form"' in page:
            brut = re.search(r'name="totpSecret" value="([^"]+)"', page).group(1)
            code = pyotp.TOTP(base64.b32encode(brut.encode()).decode()).now()
            r = s.post(action_formulaire(page, "kc-totp-settings-form"),
                       data={"totp": code, "totpSecret": brut, "userLabel": "test"})
        else:
            return r
    return r


def session_matrix(nom, mdp, nouveau_mdp=None):
    """Connexion SSO comme Element ; renvoie un jeton d'accès Matrix, ou None si refusée."""
    s = requests.Session()
    s.verify = False
    r = s.get(f"{MATRIX}/_matrix/client/v3/login/sso/redirect/oidc-keycloak",
              params={"redirectUrl": "https://chat.messagerie.test/"})
    r = connexion_keycloak(s, r, nom, mdp, nouveau_mdp)
    jeton = parse_qs(urlparse(r.url).query).get("loginToken")
    if not jeton:
        return None
    r = s.post(f"{MATRIX}/_matrix/client/v3/login", json={"type": "m.login.token", "token": jeton[0]})
    r.raise_for_status()
    return r.json()["access_token"]


def whoami(jeton):
    return requests.get(f"{MATRIX}/_matrix/client/v3/account/whoami", verify=False,
                        headers={"Authorization": f"Bearer {jeton}"})


def etape(texte):
    print("OK  " + texte)


def main():
    creer_comptes()
    try:
        jeton_perte, jeton_depart = session_matrix(PERTE, MDP), session_matrix(DEPART, MDP)
        assert jeton_perte and jeton_depart
        etape("deux agents connectés à la messagerie")

        console = requests.Session()
        console.verify = False
        r = connexion_keycloak(console, console.get(f"{CONSOLE}/"), ADMIN, MDP)
        assert r.url == f"{CONSOLE}/" and ADMIN in r.text, r.url
        etape("administrateur connecté à la console")

        def agir(nom, action):
            id_agent = re.search(r'href="/agents/([0-9a-f-]{36})">%s<' % re.escape(nom),
                                 console.get(f"{CONSOLE}/").text).group(1)
            confirmation = console.get(f"{CONSOLE}/agents/{id_agent}/{action}")
            csrf = re.search(r'name="csrf" value="([^"]+)"', confirmation.text).group(1)
            r = console.post(f"{CONSOLE}/agents/{id_agent}/{action}", data={"csrf": csrf})
            assert r.status_code == 200, (r.status_code, r.text)
            return r

        assert "Suspendu" in agir(PERTE, "perte-appareil").text
        assert whoami(jeton_perte).status_code == 401
        assert session_matrix(PERTE, MDP) is None
        etape("perte d'appareil : jeton Matrix invalidé, connexion refusée")

        r = agir(PERTE, "reactiver")
        temporaire = html.unescape(re.search(r'<code id="mot-de-passe">([^<]+)</code>', r.text).group(1))
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
        supprimer_comptes()


if __name__ == "__main__":
    main()
