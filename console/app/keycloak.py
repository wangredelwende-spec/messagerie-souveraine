"""API d'administration de Keycloak, appelée avec le compte de service du client « console »."""
import time

import httpx

from .config import CLIENT_ID, KEYCLOAK_INTERNE, REALM


class Keycloak:
    def __init__(self, secret_client: str):
        self._http = httpx.AsyncClient(base_url=f"{KEYCLOAK_INTERNE}/admin/realms/{REALM}", timeout=15)
        self._secret = secret_client
        self._jeton = ""
        self._expiration = 0.0

    async def _entetes(self) -> dict:
        if time.monotonic() > self._expiration - 30:
            r = await self._http.post(
                f"{KEYCLOAK_INTERNE}/realms/{REALM}/protocol/openid-connect/token",
                data={"grant_type": "client_credentials"},
                auth=(CLIENT_ID, self._secret),
            )
            r.raise_for_status()
            donnees = r.json()
            self._jeton = donnees["access_token"]
            self._expiration = time.monotonic() + donnees["expires_in"]
        return {"Authorization": f"Bearer {self._jeton}"}

    async def _requete(self, methode: str, chemin: str, **kwargs):
        r = await self._http.request(methode, chemin, headers=await self._entetes(), **kwargs)
        r.raise_for_status()
        return r.json() if r.content else None

    async def agents(self) -> list[dict]:
        utilisateurs = await self._requete("GET", "/users", params={"max": 5000, "briefRepresentation": "true"})
        return [u for u in utilisateurs if not u["username"].startswith("service-account-")]

    async def agent(self, id_agent: str) -> dict:
        return await self._requete("GET", f"/users/{id_agent}")

    async def _modifier(self, id_agent: str, **champs):
        # On renvoie la représentation complète : un PUT partiel pourrait effacer des attributs
        representation = await self.agent(id_agent)
        representation.update(champs)
        await self._requete("PUT", f"/users/{id_agent}", json=representation)

    async def suspendre(self, id_agent: str):
        """Compte désactivé (plus aucune connexion possible) et sessions ouvertes fermées."""
        await self._modifier(id_agent, enabled=False)
        await self._requete("POST", f"/users/{id_agent}/logout")

    async def supprimer_otp(self, id_agent: str) -> int:
        identifiants = await self._requete("GET", f"/users/{id_agent}/credentials")
        otp = [c for c in identifiants if c["type"] == "otp"]
        for c in otp:
            await self._requete("DELETE", f"/users/{id_agent}/credentials/{c['id']}")
        return len(otp)

    async def reactiver(self, id_agent: str, mot_de_passe_temporaire: str):
        """Nouveau mot de passe temporaire ; à la connexion : changer le mot de passe puis enrôler un TOTP."""
        await self.supprimer_otp(id_agent)
        await self._requete("PUT", f"/users/{id_agent}/reset-password",
                            json={"type": "password", "value": mot_de_passe_temporaire, "temporary": True})
        await self._modifier(id_agent, enabled=True, requiredActions=["UPDATE_PASSWORD", "CONFIGURE_TOTP"])
        # Efface un éventuel blocage anti-force brute
        await self._requete("DELETE", f"/attack-detection/brute-force/users/{id_agent}")
