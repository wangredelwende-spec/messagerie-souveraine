"""Journal d'audit (SQLite) : qui, quoi, quand, sur quel agent.

Il ne contient JAMAIS de contenu de message : la console n'y a pas accès (tout est chiffré de bout en bout).
Le journal est en ajout seul : des déclencheurs SQLite refusent toute modification ou suppression.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Actions qui déterminent le statut d'un compte désactivé (révoqué ou suspendu)
REVOCATIONS = ("depart", "perte-appareil", "reactivation")


class Journal:
    def __init__(self, chemin: Path):
        self._db = sqlite3.connect(chemin, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                horodatage TEXT NOT NULL,   -- UTC
                acteur TEXT NOT NULL,       -- administrateur connecté
                action TEXT NOT NULL,
                cible TEXT NOT NULL,        -- identifiant de l'agent
                resultat TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS journal_sans_modification BEFORE UPDATE ON journal
                BEGIN SELECT RAISE(ABORT, 'journal en ajout seul'); END;
            CREATE TRIGGER IF NOT EXISTS journal_sans_suppression BEFORE DELETE ON journal
                BEGIN SELECT RAISE(ABORT, 'journal en ajout seul'); END;
            -- Canal institutionnel de chaque ministère (groupe Keycloak -> salon Matrix)
            CREATE TABLE IF NOT EXISTS canaux (ministere TEXT PRIMARY KEY, room_id TEXT NOT NULL);
        """)

    def ecrire(self, acteur: str, action: str, cible: str, resultat: str):
        self._db.execute(
            "INSERT INTO journal (horodatage, acteur, action, cible, resultat) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), acteur, action, cible, resultat),
        )

    def lire(self, limite: int = 500) -> list[sqlite3.Row]:
        return self._db.execute("SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limite,)).fetchall()

    def canal(self, id_ministere: str) -> str | None:
        ligne = self._db.execute("SELECT room_id FROM canaux WHERE ministere = ?", (id_ministere,)).fetchone()
        return ligne["room_id"] if ligne else None

    def enregistrer_canal(self, id_ministere: str, room_id: str):
        self._db.execute("INSERT INTO canaux (ministere, room_id) VALUES (?, ?)", (id_ministere, room_id))

    def dernieres_revocations(self) -> dict[str, str]:
        """Pour chaque agent, la dernière action de révocation réussie."""
        lignes = self._db.execute(f"""
            SELECT cible, action FROM journal WHERE id IN (
                SELECT MAX(id) FROM journal
                WHERE resultat = 'ok' AND action IN ({','.join('?' * len(REVOCATIONS))})
                GROUP BY cible)""", REVOCATIONS).fetchall()
        return {l["cible"]: l["action"] for l in lignes}
