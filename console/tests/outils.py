"""Fonctions communes aux tests de bout en bout de la console."""
import base64
import html
import re
import subprocess
import time
from urllib.parse import parse_qs, urlparse

import pyotp
import requests
import urllib3

urllib3.disable_warnings()  # certificats signés par la CA interne de Caddy
AUTH = "https://auth.messagerie.test/"
MATRIX = "https://matrix.messagerie.test"
CONSOLE = "https://admin.messagerie.test"
MDP = "Test-Demo-2026!"


def kcadm(commandes: str) -> str:
    """Commandes kcadm dans le conteneur Keycloak, par le réseau interne (l'API admin n'est pas publiée)."""
    script = ('K=/opt/keycloak/bin/kcadm.sh; C="--config /tmp/test.cfg"; '
              '($K config credentials $C --server http://keycloak:8080 --realm master --user admin '
              f'--password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null && {commandes}); s=$?; rm -f /tmp/test.cfg; exit $s')
    return subprocess.run(["docker", "compose", "exec", "-T", "keycloak", "bash", "-c", script],
                          check=True, capture_output=True, text=True).stdout


def creer_comptes(comptes):
    """comptes : [(identifiant, rôle)] créés avec le mot de passe MDP et le TOTP à enrôler."""
    commandes = []
    for nom, role in comptes:
        commandes += [
            f"$K create users $C -r administration -s username={nom} -s enabled=true -s firstName=Test "
            f"-s lastName=Revocation -s 'requiredActions=[\"CONFIGURE_TOTP\"]'",
            f"$K set-password $C -r administration --username {nom} --new-password '{MDP}'",
            f"$K add-roles $C -r administration --uusername {nom} --rolename {role}",
        ]
    kcadm(" && ".join(commandes))


def supprimer_comptes(noms):
    kcadm(" ; ".join(
        f"$K delete users/$($K get users $C -r administration -q username={nom} -q exact=true "
        f"--fields id --format csv --noquotes) $C -r administration" for nom in noms))


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
    while True:
        r = s.get(f"{MATRIX}/_matrix/client/v3/login/sso/redirect/oidc-keycloak",
                  params={"redirectUrl": "https://chat.messagerie.test/"})
        r = connexion_keycloak(s, r, nom, mdp, nouveau_mdp)
        jeton = parse_qs(urlparse(r.url).query).get("loginToken")
        if not jeton:
            return None
        r = s.post(f"{MATRIX}/_matrix/client/v3/login", json={"type": "m.login.token", "token": jeton[0]})
        if r.status_code != 429:
            break
        # Limite de connexions de Synapse : le jeton est consommé ; on attend puis on en redemande
        # un (la session Keycloak est ouverte, plus besoin des identifiants).
        time.sleep(r.json().get("retry_after_ms", 5000) / 1000 + 1)
    r.raise_for_status()
    return r.json()["access_token"]


def whoami(jeton):
    return requests.get(f"{MATRIX}/_matrix/client/v3/account/whoami", verify=False,
                        headers={"Authorization": f"Bearer {jeton}"})


def etape(texte):
    print("OK  " + texte)


def connexion_console(nom):
    """Session de la console ouverte par un administrateur (mot de passe MDP, TOTP enrôlé au passage)."""
    console = requests.Session()
    console.verify = False
    r = connexion_keycloak(console, console.get(f"{CONSOLE}/"), nom, MDP)
    assert r.url == f"{CONSOLE}/" and nom in r.text, r.url
    return console


def csrf(page):
    return re.search(r'name="csrf" value="([^"]+)"', page).group(1)


def mot_de_passe_affiche(page):
    return html.unescape(re.search(r'<code id="mot-de-passe">([^<]+)</code>', page).group(1))
