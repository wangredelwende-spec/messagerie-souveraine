# Traduction des écrans de connexion (mooré, jula, fulfuldé…)

`phrases.csv` contient **uniquement** les phrases visibles sur les écrans de connexion,
de changement de mot de passe, de configuration et de saisie du code OTP.
Une colonne par langue : `fr` (référence), `mos` (mooré), `dyu` (jula), `ff` (fulfuldé).

**Règle** : une langue n'est proposée sur la page de connexion que lorsque **toutes** ses phrases
sont remplies. Une langue incomplète n'apparaît pas (pas d'écran à moitié traduit).
Dans le sélecteur, chaque langue s'affiche sous son propre nom : Mooré, Julakan, Fulfulde.

## Pour le traducteur

1. Ouvrir `phrases.csv` (Excel, LibreOffice ou un éditeur de texte), séparateur **point-virgule**.
2. Remplir uniquement la colonne de sa langue. Ne pas toucher aux colonnes `cle`, `ecran`, `fr`.
3. Garder tels quels les repères **`{0}`** : Keycloak les remplace par une valeur
   (un nombre de caractères, le nom de la messagerie…).
4. Enregistrer en **CSV UTF-8, séparateur point-virgule** (pour que les caractères ɛ, ɩ, ʋ… soient conservés).

## Pour l'intégration

```sh
python traduction-moore/integrer.py
docker compose restart keycloak
```

Le script indique pour chaque langue le nombre de phrases remplies et si elle est publiée. Il met à
jour les fichiers de messages, `theme.properties`, `keycloak/realm-administration.json` et le realm
déjà en place (pas besoin de tout réinitialiser).

## Ajouter une langue en 3 étapes

1. **Une colonne** : ajouter dans `phrases.csv` une colonne nommée par le code de la langue
   (ISO 639, par exemple `gux` pour le gourmantché).
2. **Son nom** : ajouter dans `integrer.py`, dictionnaire `LANGUES`, la ligne
   `"gux": "<nom de la langue écrit dans cette langue>",` (c'est ce nom qui apparaît dans le sélecteur).
3. **La traduction** : remplir toutes les phrases de la colonne, puis lancer les deux commandes
   ci-dessus. La langue apparaît sur la page de connexion.
