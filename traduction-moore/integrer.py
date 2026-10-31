"""Intègre les traductions des écrans de connexion dans le thème Keycloak.

phrases.csv (séparateur ;) : cle ; ecran ; fr ; puis une colonne par langue (mos, dyu, ff…).
Une langue n'est publiée que si TOUTES ses phrases sont remplies : sinon son fichier de messages
est retiré et elle n'est pas proposée (pas d'écran à moitié traduit).

Le script met à jour :
- keycloak/themes/messagerie/login/messages/messages_<code>.properties (langues complètes) ;
- le nom de chaque langue dans tous les fichiers de messages (sélecteur de langue) ;
- « locales » de theme.properties et « supportedLocales » de keycloak/realm-administration.json ;
- le realm « administration » déjà en place (par kcadm, réseau interne), si la pile tourne.

Utilisation :  python traduction-moore/integrer.py
puis :         docker compose restart keycloak
"""
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).parent
RACINE = ICI.parent
THEME = RACINE / "keycloak/themes/messagerie/login"
MESSAGES = THEME / "messages"
REALM = RACINE / "keycloak/realm-administration.json"

# Code de langue -> nom de la langue écrit dans cette langue (affiché dans le sélecteur)
LANGUES = {
    "fr": "Français",
    "mos": "Mooré",
    "dyu": "Julakan",
    "ff": "Fulfulde",
}
COLONNES_FIXES = ("cle", "ecran", "fr")


def lire_phrases() -> tuple[list[dict], list[str]]:
    # « utf-8-sig » : accepte le marqueur BOM qu'ajoute Excel en enregistrant un CSV
    with open(ICI / "phrases.csv", encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier, delimiter=";")
        langues = [c for c in lecteur.fieldnames if c not in COLONNES_FIXES]
        phrases = list(lecteur)
    inconnues = [code for code in langues if code not in LANGUES]
    if inconnues:
        sys.exit(f"Erreur : ajoutez le nom de la langue {', '.join(inconnues)} dans LANGUES (integrer.py)")
    return phrases, langues


def noms_des_langues(publiees: list[str]) -> list[str]:
    return [f"locale_{code}={LANGUES[code]}" for code in publiees]


def echapper(texte: str) -> str:
    # Keycloak utilise MessageFormat (Java) : une apostrophe doit être doublée
    return texte.replace("'", "''")


def mettre_a_jour_francais(publiees: list[str]):
    """messages_fr.properties est écrit à la main : on n'y remplace que les noms des langues."""
    fichier = MESSAGES / "messages_fr.properties"
    lignes = [l for l in fichier.read_text(encoding="utf-8").splitlines() if not l.startswith("locale_")]
    debut = next(i for i, l in enumerate(lignes) if not l.startswith("#"))
    lignes[debut:debut] = noms_des_langues(publiees)
    fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8", newline="\n")


def mettre_a_jour_realm_en_place(publiees: list[str]) -> str:
    valeur = json.dumps(publiees)
    script = ('K=/opt/keycloak/bin/kcadm.sh; C="--config /tmp/langues.cfg"; '
              '($K config credentials $C --server http://keycloak:8080 --realm master --user admin '
              '--password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null && '
              f"$K update realms/administration $C -s 'supportedLocales={valeur}'); "
              's=$?; rm -f /tmp/langues.cfg; exit $s')
    try:
        subprocess.run(["docker", "compose", "exec", "-T", "keycloak", "bash", "-c", script],
                       cwd=RACINE, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return "realm en place NON mis à jour (pile arrêtée ?) : relancer le script une fois la pile démarrée"
    return "realm en place mis à jour"


def main():
    phrases, langues = lire_phrases()
    publiees = ["fr"]
    for code in langues:
        manquantes = [p["cle"] for p in phrases if not (p[code] or "").strip()]
        fichier = MESSAGES / f"messages_{code}.properties"
        if manquantes:
            fichier.unlink(missing_ok=True)
            print(f"{LANGUES[code]} ({code}) : {len(phrases) - len(manquantes)}/{len(phrases)} phrases, "
                  "NON publiée (toutes les phrases doivent être remplies)")
            continue
        publiees.append(code)
    for code in publiees[1:]:
        lignes = ["# Fichier GÉNÉRÉ par traduction-moore/integrer.py à partir de phrases.csv : "
                  "ne pas modifier à la main."]
        lignes += noms_des_langues(publiees)
        lignes += [f"{p['cle']}={echapper(p[code].strip())}" for p in phrases]
        # newline="\n" : fins de ligne Unix, même sous Windows
        (MESSAGES / f"messages_{code}.properties").write_text("\n".join(lignes) + "\n", encoding="utf-8",
                                                               newline="\n")
        print(f"{LANGUES[code]} ({code}) : {len(phrases)}/{len(phrases)} phrases, publiée")
    mettre_a_jour_francais(publiees)

    theme = THEME / "theme.properties"
    theme.write_text(re.sub(r"(?m)^locales=.*$", f"locales={','.join(publiees)}", theme.read_text(encoding="utf-8")),
                     encoding="utf-8", newline="\n")
    # Remplacement ciblé : le reste du fichier du realm garde sa mise en forme
    REALM.write_text(re.sub(r'"supportedLocales": \[[^\]]*\]', f'"supportedLocales": {json.dumps(publiees)}',
                            REALM.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")

    print(f"Langues proposées : {', '.join(LANGUES[c] for c in publiees)} ; {mettre_a_jour_realm_en_place(publiees)}")
    print("Puis : docker compose restart keycloak")


if __name__ == "__main__":
    main()
