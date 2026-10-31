"""Intègre la traduction en mooré dans le thème de connexion Keycloak.

Lit phrases.csv (colonnes : cle ; ecran ; texte_francais ; moore) et écrit
keycloak/themes/messagerie/login/messages/messages_mos.properties.
Si la case « moore » est vide, on garde le texte français : sans cela, Keycloak
afficherait l'anglais.

Utilisation :  python traduction-moore/integrer.py
puis :         docker compose restart keycloak
"""
import csv
from pathlib import Path

ICI = Path(__file__).parent
SORTIE = ICI.parent / "keycloak/themes/messagerie/login/messages/messages_mos.properties"

lignes = [
    "# Fichier GÉNÉRÉ par traduction-moore/integrer.py à partir de phrases.csv : ne pas modifier à la main.",
    "locale_fr=Français",
]
traduites = 0

# « utf-8-sig » : accepte le marqueur BOM qu'ajoute Excel en enregistrant un CSV
with open(ICI / "phrases.csv", encoding="utf-8-sig", newline="") as fichier:
    for ligne in csv.DictReader(fichier, delimiter=";"):
        texte = ligne["moore"].strip()
        if texte:
            traduites += 1
        else:
            texte = ligne["texte_francais"]
        # Keycloak utilise MessageFormat (Java) : une apostrophe doit être doublée
        texte = texte.replace("'", "''")
        lignes.append(f"{ligne['cle']}={texte}")

# newline="\n" : fins de ligne Unix, même sous Windows
SORTIE.write_text("\n".join(lignes) + "\n", encoding="utf-8", newline="\n")
print(f"{traduites} phrases en mooré, {len(lignes) - 2 - traduites} restées en français -> {SORTIE}")
