"""API d'administration de Synapse, appelée avec le compte de service de la console.

Ce compte de service ne publie JAMAIS de clés de chiffrement (aucun appel à /keys/upload) :
aucun appareil ne lui partage donc de clé Megolm, et il ne peut déchiffrer aucun message.
Il ne sert qu'aux actions d'administration (désactivation, appareils, salons).
"""
import hashlib
import hmac
import os
import secrets
from urllib.parse import quote

import httpx

from .config import DONNEES, SYNAPSE_INTERNE

COMPTE_SERVICE = "console-service"
FICHIER_JETON = DONNEES / "synapse_jeton"


class Synapse:
    def __init__(self):
        self._http = httpx.AsyncClient(base_url=SYNAPSE_INTERNE, timeout=30)

    async def demarrer(self, secret_enregistrement: str):
        """Réutilise le jeton du volume, ou crée le compte de service au premier démarrage."""
        if not FICHIER_JETON.exists():
            FICHIER_JETON.write_text(await self._enregistrer(secret_enregistrement))
            os.chmod(FICHIER_JETON, 0o600)
        self._http.headers["Authorization"] = f"Bearer {FICHIER_JETON.read_text().strip()}"
        (await self._http.get("/_matrix/client/v3/account/whoami")).raise_for_status()

    async def _enregistrer(self, secret_enregistrement: str) -> str:
        r = await self._http.get("/_synapse/admin/v1/register")
        r.raise_for_status()
        nonce = r.json()["nonce"]
        # Mot de passe aléatoire jamais conservé : la connexion par mot de passe est coupée dans Synapse
        mot_de_passe = secrets.token_urlsafe(32)
        # Seul HMAC du dépôt : signature exigée par l'API d'enregistrement par secret partagé de Synapse
        # (HMAC-SHA1 de « nonce \0 identifiant \0 mot de passe \0 admin », clé = registration_shared_secret).
        # https://element-hq.github.io/synapse/latest/admin_api/register_api.html
        mac = hmac.new(
            secret_enregistrement.encode(),
            b"\x00".join([nonce.encode(), COMPTE_SERVICE.encode(), mot_de_passe.encode(), b"admin"]),
            hashlib.sha1,
        ).hexdigest()
        r = await self._http.post("/_synapse/admin/v1/register", json={
            "nonce": nonce, "username": COMPTE_SERVICE, "password": mot_de_passe, "admin": True, "mac": mac,
        })
        r.raise_for_status()
        return r.json()["access_token"]

    async def existe(self, user_id: str) -> bool:
        r = await self._http.get(f"/_synapse/admin/v2/users/{quote(user_id, safe='')}")
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return True

    async def creer_compte(self, user_id: str, nom_affiche: str, sub_keycloak: str):
        """Pré-crée le compte Matrix, lié à l'identité Keycloak : à sa première connexion SSO,
        Synapse retrouve l'agent par son « sub » et ouvre ce compte."""
        r = await self._http.put(f"/_synapse/admin/v2/users/{quote(user_id, safe='')}", json={
            "displayname": nom_affiche, "admin": False,
            "external_ids": [{"auth_provider": "oidc-keycloak", "external_id": sub_keycloak}],
        })
        r.raise_for_status()

    async def creer_canal(self, nom: str) -> str:
        """Salon institutionnel : chiffré (Megolm), sur invitation, historique visible seulement
        à partir de l'arrivée, nom neutre sans sujet ni avatar.
        Le compte de service en est membre (pour y ajouter les agents) mais, sans clés publiées,
        aucun appareil ne lui partage les clés du salon : il ne lit rien."""
        r = await self._http.post("/_matrix/client/v3/createRoom", json={
            "name": nom,
            "preset": "private_chat",            # entrée sur invitation uniquement
            "visibility": "private",             # absent de l'annuaire des salons
            "initial_state": [
                {"type": "m.room.encryption", "state_key": "", "content": {"algorithm": "m.megolm.v1.aes-sha2"}},
                {"type": "m.room.history_visibility", "state_key": "", "content": {"history_visibility": "joined"}},
                {"type": "m.room.guest_access", "state_key": "", "content": {"guest_access": "forbidden"}},
            ],
            # Seule la console gère les membres : les agents ne peuvent ni inviter ni exclure
            "power_level_content_override": {"invite": 100, "kick": 100, "ban": 100},
        })
        r.raise_for_status()
        return r.json()["room_id"]

    async def membres_canal(self, room_id: str) -> set[str]:
        r = await self._http.get(f"/_synapse/admin/v1/rooms/{quote(room_id, safe='')}/members")
        r.raise_for_status()
        return set(r.json()["members"])

    async def ajouter_au_canal(self, room_id: str, user_id: str):
        r = await self._http.post(f"/_synapse/admin/v1/join/{quote(room_id, safe='')}", json={"user_id": user_id})
        r.raise_for_status()

    async def desactiver(self, user_id: str) -> bool:
        """Jetons et appareils supprimés, sortie de tous les salons. Faux si l'agent ne s'est jamais connecté."""
        if not await self.existe(user_id):
            return False
        r = await self._http.post(f"/_synapse/admin/v1/deactivate/{quote(user_id, safe='')}", json={"erase": False})
        r.raise_for_status()
        return True

    async def supprimer_appareils(self, user_id: str) -> int:
        """Supprime tous les appareils (et donc leurs jetons) ; le compte Matrix est conservé."""
        if not await self.existe(user_id):
            return 0
        chemin = f"/_synapse/admin/v2/users/{quote(user_id, safe='')}"
        r = await self._http.get(f"{chemin}/devices")
        r.raise_for_status()
        appareils = [a["device_id"] for a in r.json()["devices"]]
        if appareils:
            (await self._http.post(f"{chemin}/delete_devices", json={"devices": appareils})).raise_for_status()
        return len(appareils)
