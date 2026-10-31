# Traduction des écrans de connexion en mooré

`phrases.csv` contient **uniquement** les phrases visibles sur les écrans de connexion,
de changement de mot de passe, de configuration et de saisie du code OTP.

## Pour le traducteur (PJ)

1. Ouvrir `phrases.csv` (Excel, LibreOffice ou un éditeur de texte), séparateur **point-virgule**.
2. Remplir uniquement la colonne **`moore`**. Ne pas toucher aux colonnes `cle`, `ecran`, `texte_francais`.
3. Garder tels quels les repères **`{0}`** : Keycloak les remplace par une valeur
   (un nombre de caractères, le nom de la messagerie…).
4. Une case laissée vide affichera le texte français.
5. Enregistrer en **CSV UTF-8, séparateur point-virgule** (pour que les caractères ɛ, ɩ, ʋ… soient conservés).

## Pour l'intégration

```sh
python traduction-moore/integrer.py
docker compose restart keycloak
```

Le mooré est ensuite proposé dans le sélecteur de langue de la page de connexion.
