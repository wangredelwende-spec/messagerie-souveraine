"""Test de bout en bout des salons « Confidentiel » à expiration automatique.

Depuis la racine du dépôt :  python console/tests/test_confidentiel.py   (≈ 3 minutes)
La console crée un salon d'une durée de vie de 1 minute avec un agent jetable ; on vérifie le
verrouillage, puis que l'événement expiré n'est plus servi et a disparu de la base.
À la fin, les comptes créés sont désactivés dans Synapse et supprimés de Keycloak.
"""
import re
import secrets
import subprocess
import time

import requests

from outils import (CONSOLE, MATRIX, MDP, connexion_console, creer_comptes, csrf, etape, session_matrix,
                    supprimer_comptes)

SUFFIXE = secrets.token_hex(3)
ADMIN, AGENT = f"test.admin.{SUFFIXE}", f"test.confidentiel.{SUFFIXE}"
SUJET = f"Essai expiration {SUFFIXE}"
DELAI_MAX = 300  # 1 min de durée de vie + purge toutes les minutes, avec de la marge


def matrix(methode, chemin, jeton, corps=None):
    return requests.request(methode, f"{MATRIX}/_matrix/client/v3{chemin}", json=corps, verify=False,
                            headers={"Authorization": f"Bearer {jeton}"}, timeout=20)


def evenement_en_base(event_id):
    sortie = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "synapse", "-tAc",
         f"SELECT count(*) FROM events WHERE event_id = '{event_id}'"],
        check=True, capture_output=True, text=True).stdout
    return int(sortie.strip()) > 0


def main():
    creer_comptes([(ADMIN, "admin-messagerie"), (AGENT, "agent")])
    try:
        console = connexion_console(ADMIN)
        page = console.get(f"{CONSOLE}/canaux").text
        id_agent = re.search(r'value="([0-9a-f-]{36})"> %s ' % re.escape(AGENT), page).group(1)
        r = console.post(f"{CONSOLE}/confidentiels", data={
            "csrf": csrf(page), "sujet": SUJET, "duree": "1min", "agents": [id_agent]})
        assert r.status_code == 200, (r.status_code, r.text)
        salon = re.search(r"créé \((![^)]+)\) : 1 membre", r.text).group(1)
        assert re.search(r"\[CONFIDENTIEL\] %s<br><code>%s</code></td>\s*<td>1 minute \(test\)</td>\s*<td>%s</td>"
                         % (re.escape(SUJET), re.escape(salon), re.escape(AGENT)), r.text)
        etape(f"salon créé par la console : {salon}, durée 1 minute, agent ajouté")

        jeton = session_matrix(AGENT, MDP)
        assert jeton
        etat = matrix("GET", f"/rooms/{salon}/state", jeton).json()
        par_type = {e["type"]: e["content"] for e in etat}
        assert par_type["m.room.name"]["name"] == f"[CONFIDENTIEL] {SUJET}"
        assert "1 minute" in par_type["m.room.topic"]["topic"]
        assert par_type["m.room.retention"]["max_lifetime"] == 60_000
        assert par_type["m.room.encryption"]["algorithm"] == "m.megolm.v1.aes-sha2"
        assert par_type["m.room.join_rules"]["join_rule"] == "invite"
        assert par_type["m.room.history_visibility"]["history_visibility"] == "joined"
        etape("état du salon : nom, sujet, rétention 60 s, Megolm, sur invitation, historique « joined »")

        refus = {
            "inviter": matrix("POST", f"/rooms/{salon}/invite", jeton, {"user_id": "@intrus.inexistant:messagerie.test"}),
            "renommer": matrix("PUT", f"/rooms/{salon}/state/m.room.name/", jeton, {"name": "Ouvert"}),
            "allonger la rétention": matrix("PUT", f"/rooms/{salon}/state/m.room.retention/", jeton,
                                            {"max_lifetime": 31_536_000_000}),
            "ouvrir le salon": matrix("PUT", f"/rooms/{salon}/state/m.room.join_rules/", jeton, {"join_rule": "public"}),
        }
        assert all(r.status_code == 403 for r in refus.values()), {k: r.status_code for k, r in refus.items()}
        etape(f"un membre ne peut pas : {', '.join(refus)} (HTTP 403)")

        # Faux message chiffré (le serveur ne vérifie pas le contenu), suivi d'un second événement :
        # Synapse ne purge jamais le dernier événement d'un salon, il le cache seulement.
        faux = {"algorithm": "m.megolm.v1.aes-sha2", "ciphertext": "FAUX", "session_id": "test",
                "sender_key": "test", "device_id": "TEST"}
        cible = matrix("PUT", f"/rooms/{salon}/send/m.room.encrypted/a{SUFFIXE}", jeton, faux).json()["event_id"]
        matrix("PUT", f"/rooms/{salon}/send/m.room.encrypted/b{SUFFIXE}", jeton, faux).raise_for_status()
        assert matrix("GET", f"/rooms/{salon}/event/{cible}", jeton).status_code == 200
        assert evenement_en_base(cible)
        etape(f"événement chiffré factice envoyé : {cible} (servi et présent en base)")

        debut = time.monotonic()
        while time.monotonic() - debut < DELAI_MAX:
            time.sleep(15)
            servi = matrix("GET", f"/rooms/{salon}/event/{cible}", jeton).status_code
            if servi == 404 and not evenement_en_base(cible):
                break
        else:
            raise AssertionError(f"événement toujours présent après {DELAI_MAX} s (HTTP {servi})")
        etape(f"après {int(time.monotonic() - debut)} s : événement plus servi (404) et absent de la table events")
        matrix("POST", "/logout", jeton, {})
    finally:
        supprimer_comptes([ADMIN, AGENT])


if __name__ == "__main__":
    main()
