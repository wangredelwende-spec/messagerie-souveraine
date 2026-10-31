"""Adresses et constantes de la console."""
from pathlib import Path

REALM = "administration"
# Le navigateur voit l'adresse publique ; la console appelle les services par le réseau Docker interne
KEYCLOAK_PUBLIC = "https://auth.messagerie.test"
KEYCLOAK_INTERNE = "http://keycloak:8080"
SYNAPSE_INTERNE = "http://synapse:8008"
SERVER_NAME = "messagerie.test"
CONSOLE_URL = "https://admin.messagerie.test"

CLIENT_ID = "console"
ROLE_ADMIN = "admin-messagerie"
DONNEES = Path("/donnees")


def lire_secret(nom: str) -> str:
    """Secrets fournis par docker compose dans /run/secrets/ (jamais dans les variables d'environnement)."""
    return Path("/run/secrets", nom).read_text().strip()


def matrix_id(identifiant: str) -> str:
    """Identifiant Keycloak -> identifiant Matrix (même règle que localpart_template de Synapse)."""
    return f"@{identifiant}:{SERVER_NAME}"
