"""Console d'administration de la messagerie : rendu serveur, aucun JavaScript.

Accès protégé par Keycloak (OIDC, client « console ») : seul le rôle admin-messagerie entre.
"""
import re
import secrets
import string
import unicodedata
from contextlib import asynccontextmanager
from urllib.parse import urlencode
from uuid import UUID

import httpx
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .audit import Journal
from .config import (CLIENT_ID, CONSOLE_URL, DONNEES, KEYCLOAK_INTERNE, KEYCLOAK_PUBLIC, REALM,
                     ROLE_ADMIN, lire_secret, matrix_id)
from .keycloak import Keycloak
from .synapse import COMPTE_SERVICE, Synapse

SECRET_OIDC = lire_secret("console_oidc")
keycloak = Keycloak(SECRET_OIDC)
synapse = Synapse()
journal = Journal(DONNEES / "journal.sqlite3")


@asynccontextmanager
async def cycle_de_vie(_app):
    await synapse.demarrer(lire_secret("synapse_enregistrement"))
    for ministere in await keycloak.ministeres():
        await canal_du_ministere(ministere, "console")
    yield


app = FastAPI(lifespan=cycle_de_vie, docs_url=None, redoc_url=None, openapi_url=None)
# Clé de session tirée à chaque démarrage : redémarrer la console déconnecte les administrateurs.
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32), session_cookie="console_session",
                   https_only=True, same_site="lax", max_age=8 * 3600)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

oauth = OAuth()
oauth.register(
    "keycloak",
    client_id=CLIENT_ID,
    client_secret=SECRET_OIDC,
    # Le navigateur va sur l'adresse publique ; l'échange du code et les clés passent par le réseau interne
    authorize_url=f"{KEYCLOAK_PUBLIC}/realms/{REALM}/protocol/openid-connect/auth",
    access_token_url=f"{KEYCLOAK_INTERNE}/realms/{REALM}/protocol/openid-connect/token",
    jwks_uri=f"{KEYCLOAK_INTERNE}/realms/{REALM}/protocol/openid-connect/certs",
    issuer=f"{KEYCLOAK_PUBLIC}/realms/{REALM}",
    client_kwargs={"scope": "openid profile", "code_challenge_method": "S256"},
)

# Actions de révocation : texte de confirmation et statuts depuis lesquels elles sont permises
ACTIONS = {
    "depart": {
        "titre": "Départ de l'agent",
        "effets": [
            "Le compte Keycloak est désactivé et toutes ses sessions sont fermées.",
            "Le compte Matrix est désactivé définitivement : jetons et appareils supprimés, "
            "sortie de tous les salons.",
        ],
        "depuis": {"actif", "suspendu"},
    },
    "perte-appareil": {
        "titre": "Perte d'appareil",
        "effets": [
            "Le compte Keycloak est suspendu et toutes ses sessions sont fermées.",
            "Le code TOTP enrôlé est supprimé.",
            "Tous les appareils Matrix de l'agent sont supprimés (le compte Matrix est conservé).",
            "L'agent ne peut plus se connecter jusqu'à sa réactivation par un administrateur.",
        ],
        "depuis": {"actif"},
    },
    "reactiver": {
        "titre": "Réactiver l'agent",
        "effets": [
            "Un nouveau mot de passe temporaire est créé et affiché une seule fois.",
            "À la connexion, l'agent devra changer ce mot de passe puis enrôler un nouveau code TOTP.",
        ],
        "depuis": {"suspendu"},
    },
}
ACTION_JOURNAL = {"depart": "depart", "perte-appareil": "perte-appareil", "reactiver": "reactivation"}
STATUTS = {"actif": "Actif", "suspendu": "Suspendu", "revoque": "Révoqué"}


class NonConnecte(Exception):
    pass


@app.exception_handler(NonConnecte)
async def vers_connexion(_request, _exc):
    return RedirectResponse("/connexion", status_code=303)


def exiger_admin(request: Request) -> str:
    admin = request.session.get("admin")
    if not admin:
        raise NonConnecte()
    return admin


def verifier_csrf(request: Request, jeton: str):
    attendu = request.session.get("csrf", "")
    if not attendu or not secrets.compare_digest(jeton.encode(), attendu.encode()):
        raise HTTPException(403, "Jeton de formulaire invalide")


def page(request: Request, modele: str, statut: int = 200, **contexte):
    contexte |= {"admin": request.session.get("admin"), "csrf": request.session.get("csrf"), "statuts": STATUTS}
    return templates.TemplateResponse(request, modele, contexte, status_code=statut)


def statut(agent: dict, derniere_revocation: str | None) -> str:
    if agent.get("enabled"):
        return "actif"
    return "revoque" if derniere_revocation == "depart" else "suspendu"


async def canal_du_ministere(ministere: dict, acteur: str) -> str:
    """Salon Matrix du ministère, créé à la première demande."""
    room_id = journal.canal(ministere["id"])
    if room_id is None:
        room_id = await synapse.creer_canal(ministere["name"])
        journal.enregistrer_canal(ministere["id"], room_id)
        journal.ecrire(acteur, "canal-creation", ministere["name"], "ok")
    return room_id


async def ajouter_au_canal(ministere: dict, identifiant: str, acteur: str) -> bool:
    try:
        await synapse.ajouter_au_canal(await canal_du_ministere(ministere, acteur), matrix_id(identifiant))
    except httpx.HTTPError as e:
        journal.ecrire(acteur, "canal-ajout", identifiant, f"échec ({ministere['name']}) : {e}")
        return False
    journal.ecrire(acteur, "canal-ajout", identifiant, f"ok ({ministere['name']})")
    return True


def mot_de_passe_temporaire() -> str:
    """20 caractères aléatoires respectant la politique du realm (majuscule, minuscule, chiffre, spécial)."""
    alphabet = string.ascii_letters + string.digits
    return ("".join(secrets.choice(alphabet) for _ in range(16)) + secrets.choice(string.ascii_uppercase)
            + secrets.choice(string.ascii_lowercase) + secrets.choice(string.digits) + secrets.choice("!#%+=?@"))


async def charger_agent(id_agent: UUID) -> dict:
    try:
        agent = await keycloak.agent(str(id_agent))
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, "Agent introuvable")
        raise
    if agent["username"].startswith("service-account-"):
        raise HTTPException(404, "Agent introuvable")
    agent["statut"] = statut(agent, journal.dernieres_revocations().get(agent["username"]))
    return agent


# --- Connexion des administrateurs ---

@app.get("/sante", include_in_schema=False)
async def sante():
    return PlainTextResponse("ok")


@app.get("/connexion")
async def connexion(request: Request):
    return await oauth.keycloak.authorize_redirect(request, f"{CONSOLE_URL}/auth/callback")


@app.get("/auth/callback")
async def retour_keycloak(request: Request):
    try:
        jeton = await oauth.keycloak.authorize_access_token(request)
    except OAuthError:
        return page(request, "erreur.html", 400, message="La connexion a échoué. Veuillez réessayer.")
    infos = jeton["userinfo"]
    nom = infos.get("preferred_username", infos["sub"])
    request.session.clear()
    if ROLE_ADMIN not in infos.get("roles", []):
        journal.ecrire(nom, "connexion-console", "-", "refusé : rôle admin-messagerie absent")
        return page(request, "erreur.html", 403, message="Accès réservé aux administrateurs de la messagerie.")
    request.session.update(admin=nom, id_token=jeton["id_token"], csrf=secrets.token_urlsafe(32))
    journal.ecrire(nom, "connexion-console", "-", "ok")
    return RedirectResponse("/", status_code=303)


@app.post("/deconnexion")
async def deconnexion(request: Request, csrf: str = Form(...)):
    verifier_csrf(request, csrf)
    parametres = {"client_id": CLIENT_ID, "post_logout_redirect_uri": f"{CONSOLE_URL}/",
                  "id_token_hint": request.session.get("id_token", "")}
    request.session.clear()
    return RedirectResponse(f"{KEYCLOAK_PUBLIC}/realms/{REALM}/protocol/openid-connect/logout?"
                            f"{urlencode(parametres)}", status_code=303)


# --- Agents et révocation ---

def fonction(agent: dict) -> str:
    return (agent.get("attributes") or {}).get("fonction", [""])[0]


@app.get("/")
async def annuaire(request: Request, admin: str = Depends(exiger_admin)):
    """Annuaire : agents par ministère, triés par fonction, avec leur statut."""
    revocations = journal.dernieres_revocations()
    agents = {a["id"]: a for a in await keycloak.agents()}
    for a in agents.values():
        a["statut"], a["fonction"] = statut(a, revocations.get(a["username"])), fonction(a)
    sections, ranges = [], set()
    for ministere in sorted(await keycloak.ministeres(), key=lambda g: g["name"]):
        ids = [m["id"] for m in await keycloak.membres(ministere["id"]) if m["id"] in agents]
        ranges.update(ids)
        sections.append({"nom": ministere["name"], "agents": [agents[i] for i in ids]})
    sans_ministere = [a for i, a in agents.items() if i not in ranges]
    if sans_ministere:
        sections.append({"nom": "Sans ministère", "agents": sans_ministere})
    for section in sections:
        section["agents"].sort(key=lambda a: (a["fonction"], a["username"]))
    return page(request, "accueil.html", sections=sections)


def normaliser(texte: str) -> str:
    """« Ouédraogo » -> « ouedraogo » : identifiant ASCII, valide aussi comme identifiant Matrix."""
    ascii_ = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")


async def identifiant_libre(prenom: str, nom: str) -> str:
    """prenom.nom, puis prenom.nom2, prenom.nom3… s'il est déjà pris dans Keycloak ou dans Synapse
    (un agent parti garde son compte Matrix désactivé : son identifiant n'est jamais réattribué)."""
    base = f"{normaliser(prenom)}.{normaliser(nom)}"
    for n in range(1, 100):
        candidat = base if n == 1 else f"{base}{n}"
        if not await keycloak.identifiant_pris(candidat) and not await synapse.existe(matrix_id(candidat)):
            return candidat
    raise HTTPException(409, "Aucun identifiant disponible")


@app.get("/enroler")
async def formulaire_enrolement(request: Request, admin: str = Depends(exiger_admin)):
    return page(request, "enroler.html", ministeres=sorted(await keycloak.ministeres(), key=lambda g: g["name"]),
                valeurs={}, erreur=None)


@app.post("/enroler")
async def enroler(request: Request, csrf: str = Form(...), prenom: str = Form(""), nom: str = Form(""),
                  ministere: str = Form(""), fonction_agent: str = Form("", alias="fonction"),
                  admin: str = Depends(exiger_admin)):
    verifier_csrf(request, csrf)
    ministeres = sorted(await keycloak.ministeres(), key=lambda g: g["name"])
    groupe = next((g for g in ministeres if g["id"] == ministere), None)
    valeurs = {"prenom": prenom.strip(), "nom": nom.strip(), "ministere": ministere, "fonction": fonction_agent.strip()}
    erreur = None
    if not (valeurs["prenom"] and valeurs["nom"] and valeurs["fonction"] and groupe):
        erreur = "Tous les champs sont obligatoires."
    elif not (normaliser(valeurs["prenom"]) and normaliser(valeurs["nom"])):
        erreur = "Le prénom et le nom doivent contenir des lettres."
    elif max(len(v) for v in valeurs.values()) > 100:
        erreur = "Chaque champ est limité à 100 caractères."
    if erreur:
        return page(request, "enroler.html", 400, ministeres=ministeres, valeurs=valeurs, erreur=erreur)

    identifiant = await identifiant_libre(valeurs["prenom"], valeurs["nom"])
    mot_de_passe = mot_de_passe_temporaire()
    try:
        id_agent = await keycloak.creer_agent(identifiant, valeurs["prenom"], valeurs["nom"], valeurs["fonction"],
                                              groupe["path"], mot_de_passe)
        try:
            # Le « sub » des jetons Keycloak est l'identifiant interne de l'agent
            await synapse.creer_compte(matrix_id(identifiant), f"{valeurs['prenom']} {valeurs['nom']}", id_agent)
        except httpx.HTTPError:
            await keycloak.supprimer_agent(id_agent)
            raise
    except httpx.HTTPError as e:
        journal.ecrire(admin, "enrolement", identifiant, f"échec : {e}")
        return page(request, "erreur.html", 502, message="L'enrôlement n'a pas abouti ; rien n'a été créé.")
    journal.ecrire(admin, "enrolement", identifiant, "ok")
    dans_canal = await ajouter_au_canal(groupe, identifiant, admin)
    return page(request, "enrole.html", agent=await charger_agent(UUID(id_agent)), ministere=groupe["name"],
                identifiant=identifiant, mot_de_passe=mot_de_passe, dans_canal=dans_canal)


# --- Canaux institutionnels ---

async def etat_canaux() -> list[dict]:
    agents = {a["id"]: a for a in await keycloak.agents()}
    role_agent = await keycloak.ids_role_agent()
    canaux = []
    for ministere in sorted(await keycloak.ministeres(), key=lambda g: g["name"]):
        room_id = await canal_du_ministere(ministere, "console")
        membres = await synapse.membres_canal(room_id)
        # Agents attendus : membres du ministère, actifs, avec le rôle « agent »
        attendus = [agents[m["id"]] for m in await keycloak.membres(ministere["id"])
                    if m["id"] in agents and m["id"] in role_agent and agents[m["id"]].get("enabled")]
        canaux.append({"ministere": ministere, "room_id": room_id, "attendus": attendus,
                       "manquants": [a for a in attendus if matrix_id(a["username"]) not in membres]})
    return canaux


@app.get("/canaux")
async def voir_canaux(request: Request, admin: str = Depends(exiger_admin)):
    return await page_canaux(request)


@app.post("/canaux/{id_ministere}/synchroniser")
async def synchroniser_canal(request: Request, id_ministere: UUID, csrf: str = Form(...),
                             admin: str = Depends(exiger_admin)):
    """Ajoute au canal les agents actifs du ministère qui n'y sont pas encore (comptes Matrix
    pré-créés au besoin, par exemple pour les comptes importés avant la console)."""
    verifier_csrf(request, csrf)
    canal = next((c for c in await etat_canaux() if c["ministere"]["id"] == str(id_ministere)), None)
    if canal is None:
        raise HTTPException(404, "Ministère introuvable")
    ajoutes = 0
    for agent in canal["manquants"]:
        if await assurer_compte_matrix(agent, admin, "canal-ajout"):
            ajoutes += await ajouter_au_canal(canal["ministere"], agent["username"], admin)
    return await page_canaux(request,
                             message=f"{canal['ministere']['name']} : {ajoutes} agent(s) ajouté(s) au canal.")


async def assurer_compte_matrix(agent: dict, admin: str, action: str) -> bool:
    """Pré-crée le compte Matrix d'un agent qui ne s'est jamais connecté (lié à son sub Keycloak)."""
    user_id = matrix_id(agent["username"])
    try:
        if not await synapse.existe(user_id):
            await synapse.creer_compte(user_id, f"{agent['firstName']} {agent['lastName']}", agent["id"])
    except httpx.HTTPError as e:
        journal.ecrire(admin, action, agent["username"], f"échec (compte Matrix) : {e}")
        return False
    return True


# --- Salons « Confidentiel » à expiration automatique ---

# Durée de vie des messages proposée dans le formulaire : (libellé, millisecondes)
DUREES = {
    "5min": ("5 minutes (démonstration)", 5 * 60_000),
    "1j": ("1 jour", 86_400_000),
    "7j": ("7 jours", 7 * 86_400_000),
    "30j": ("30 jours", 30 * 86_400_000),
}
# Réservée au test automatique : acceptée mais absente du formulaire
DUREE_TEST = {"1min": ("1 minute (test)", 60_000)}


async def agents_invitables() -> list[dict]:
    """Agents actifs ayant le rôle « agent », pour le formulaire d'invitation."""
    role_agent = await keycloak.ids_role_agent()
    return sorted((a for a in await keycloak.agents() if a["id"] in role_agent and a.get("enabled")),
                  key=lambda a: a["username"])


async def page_canaux(request: Request, statut_http: int = 200, **contexte):
    confidentiels = []
    for salon in journal.salons_confidentiels():
        membres = await synapse.membres_canal(salon["room_id"])
        membres.discard(matrix_id(COMPTE_SERVICE))
        confidentiels.append({**dict(salon), "membres": sorted(m.split(":")[0][1:] for m in membres)})
    return page(request, "canaux.html", statut_http, canaux=await etat_canaux(), confidentiels=confidentiels,
                agents=await agents_invitables(), durees=DUREES, **contexte)


@app.post("/confidentiels")
async def creer_salon_confidentiel(request: Request, csrf: str = Form(...), sujet: str = Form(""),
                                   duree: str = Form(""), agents: list[str] = Form([]),
                                   admin: str = Depends(exiger_admin)):
    verifier_csrf(request, csrf)
    sujet = sujet.strip()
    choix = {a["id"]: a for a in await agents_invitables()}
    invites = [choix[i] for i in dict.fromkeys(agents) if i in choix]
    libelle, duree_ms = (DUREES | DUREE_TEST).get(duree, (None, None))
    if not sujet or len(sujet) > 80 or not libelle or not invites:
        return await page_canaux(request, 400, erreur="Indiquez un sujet (80 caractères au plus), "
                                 "une durée et au moins un agent.")
    nom = f"[CONFIDENTIEL] {sujet}"
    try:
        room_id = await synapse.creer_salon_confidentiel(
            nom, f"Salon confidentiel : les messages sont effacés automatiquement après {libelle}.", duree_ms)
    except httpx.HTTPError as e:
        journal.ecrire(admin, "confidentiel-creation", nom, f"échec : {e}")
        return await page_canaux(request, 502, erreur="La création du salon a échoué.")
    journal.enregistrer_salon_confidentiel(room_id, sujet, libelle, admin)
    journal.ecrire(admin, "confidentiel-creation", nom,
                   f"ok ; durée : {libelle} ; membres : {', '.join(a['username'] for a in invites)}")
    ajoutes = 0
    for agent in invites:
        if not await assurer_compte_matrix(agent, admin, "confidentiel-ajout"):
            continue
        try:
            await synapse.ajouter_au_canal(room_id, matrix_id(agent["username"]))
        except httpx.HTTPError as e:
            journal.ecrire(admin, "confidentiel-ajout", agent["username"], f"échec ({nom}) : {e}")
            continue
        journal.ecrire(admin, "confidentiel-ajout", agent["username"], f"ok ({nom})")
        ajoutes += 1
    return await page_canaux(request, message=f"Salon « {nom} » créé ({room_id}) : {ajoutes} membre(s) "
                             f"sur {len(invites)}, messages effacés après {libelle}.")


@app.get("/agents/{id_agent}")
async def fiche_agent(request: Request, id_agent: UUID, admin: str = Depends(exiger_admin)):
    agent = await charger_agent(id_agent)
    possibles = {} if agent["username"] == admin else \
        {cle: a for cle, a in ACTIONS.items() if agent["statut"] in a["depuis"]}
    return page(request, "agent.html", agent=agent, actions=possibles)


def action_permise(nom_action: str, agent: dict, admin: str) -> dict:
    action = ACTIONS.get(nom_action)
    if action is None:
        raise HTTPException(404, "Action inconnue")
    if agent["username"] == admin:
        raise HTTPException(403, "Un administrateur ne peut pas agir sur son propre compte")
    if agent["statut"] not in action["depuis"]:
        raise HTTPException(409, "Action impossible dans l'état actuel du compte")
    return action


@app.get("/agents/{id_agent}/{nom_action}")
async def confirmer(request: Request, id_agent: UUID, nom_action: str, admin: str = Depends(exiger_admin)):
    agent = await charger_agent(id_agent)
    return page(request, "confirmer.html", agent=agent, nom_action=nom_action,
                action=action_permise(nom_action, agent, admin))


@app.post("/agents/{id_agent}/{nom_action}")
async def executer(request: Request, id_agent: UUID, nom_action: str, csrf: str = Form(...),
                   admin: str = Depends(exiger_admin)):
    verifier_csrf(request, csrf)
    agent = await charger_agent(id_agent)
    action = action_permise(nom_action, agent, admin)
    user_id = matrix_id(agent["username"])
    compte_rendu, mot_de_passe = [], None
    try:
        if nom_action == "depart":
            await keycloak.suspendre(agent["id"])
            compte_rendu.append("Compte Keycloak désactivé, sessions fermées.")
            if await synapse.desactiver(user_id):
                compte_rendu.append(f"Compte Matrix {user_id} désactivé.")
            else:
                compte_rendu.append("Aucun compte Matrix : l'agent ne s'était jamais connecté.")
        elif nom_action == "perte-appareil":
            await keycloak.suspendre(agent["id"])
            otp = await keycloak.supprimer_otp(agent["id"])
            appareils = await synapse.supprimer_appareils(user_id)
            compte_rendu += ["Compte Keycloak suspendu, sessions fermées.", f"Codes TOTP supprimés : {otp}.",
                             f"Appareils Matrix supprimés : {appareils}."]
        else:
            mot_de_passe = mot_de_passe_temporaire()
            await keycloak.reactiver(agent["id"], mot_de_passe)
            compte_rendu.append("Compte réactivé : changement du mot de passe et enrôlement TOTP exigés.")
    except httpx.HTTPError as e:
        journal.ecrire(admin, ACTION_JOURNAL[nom_action], agent["username"], f"échec : {e}")
        return page(request, "erreur.html", 502,
                    message="L'action n'a pas abouti. Les étapes déjà faites :",
                    details=compte_rendu or ["aucune"])
    journal.ecrire(admin, ACTION_JOURNAL[nom_action], agent["username"], "ok")
    agent = await charger_agent(id_agent)
    return page(request, "resultat.html", agent=agent, action=action, compte_rendu=compte_rendu,
                mot_de_passe=mot_de_passe)


@app.get("/journal")
async def voir_journal(request: Request, admin: str = Depends(exiger_admin)):
    return page(request, "journal.html", lignes=journal.lire())
