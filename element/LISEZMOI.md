# Element Web : configuration

Image officielle `vectorim/element-web`, sans modification du code. Seul `config.json` est fourni
(le format JSON n'accepte pas de commentaires, d'où ce fichier).

| Réglage | Rôle |
|---|---|
| `default_server_config`, `disable_custom_urls` | Serveur fixé sur `matrix.messagerie.test`, impossible d'en choisir un autre |
| `disable_guests`, `disable_3pid_login` | Pas d'invités, pas de connexion par email ou téléphone |
| `sso_redirect_options.immediate` | Redirection directe vers Keycloak, sans écran intermédiaire |
| `logout_redirect_url` | La déconnexion ferme aussi la session Keycloak (sinon reconnexion automatique sans mot de passe) |
| `default_device_display_name` | Nom d'appareil neutre : le serveur ne voit ni le navigateur ni le système |
| `default_federate: false` | Salons créés comme non fédérables |
| `enable_client_well_known_lookups: false` | Pas de requêtes `.well-known` vers d'autres domaines |
| `integrations_*: null` | Désactive le gestionnaire d'intégrations (par défaut : `scalar.vector.im`) |
| `jitsi.preferred_domain: ""` | Supprime le serveur Jitsi par défaut (`meet.element.io`) |
| `element_call.disable` | Pas d'Element Call |
| `UIFeature.voip`, `UIFeature.widgets` | Pas d'appels, pas de widgets (qui chargent des pages externes) |
| `UIFeature.locationSharing` | Pas de partage de position (nécessite un serveur de cartes externe) |
| `UIFeature.urlPreviews`, `urlPreviewsEnabled*` | Pas d'aperçu de liens |
| `UIFeature.feedback` | Pas d'envoi de retours ou de rapports de bug |
| `UIFeature.identityServer`, `UIFeature.thirdPartyId` | Pas de serveur d'identité, pas d'email ou de téléphone |
| `UIFeature.registration`, `passwordReset`, `deactivate` | Comptes gérés uniquement dans Keycloak et la console |
| `UIFeature.allowCreatingPublic*` | Pas de salon ni d'espace public |
| `setting_defaults.language` | Interface en français |

Aucune clé `posthog`, `sentry` ou `bug_report_endpoint_url` : pas d'analytics, pas de rapports d'erreurs.
En complément, Caddy envoie un en-tête `Content-Security-Policy` qui interdit au navigateur
de contacter un autre domaine que `*.messagerie.test` (voir `caddy/Caddyfile`).
