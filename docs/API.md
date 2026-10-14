# API

L'API FastAPI est préfixée par `/api` et sa documentation interactive est disponible sur `/docs`.

- `POST /api/auth/login` : connexion OAuth2 avec `ADMIN_USER` et `ADMIN_PASSWORD`.
- `GET /api/auth/me` : vérifie le JWT.
- `GET /api/produits` : liste des produits de démonstration protégée par JWT.
- `POST /api/fichiers` : accepte une image JPEG, PNG ou WebP de 5 Mo maximum.
- `GET /api/sync` et `PUT /api/sync` : lecture et écriture de l'état partagé du prototype.
- `POST /api/evenements/ticket` : crée un ticket SSE à usage unique valable 30 secondes.
- `GET /api/evenements?ticket=...` : flux Server-Sent Events avec reprise `Last-Event-ID`, battement de cœur et événement `resync`.
- `GET /api/biometrie/inscription/options` et `POST /api/biometrie/inscription/verification` : inscription d'une passkey.
- `GET /api/biometrie/approbation/options` et `POST /api/biometrie/approbation/verification` : validation WebAuthn d'une reconnaissance de dette.

Toutes les réponses `/api/*` utilisent `Cache-Control: no-store`. Les événements ne contiennent que `id`, `type`, `ressource_id` et `ts`, jamais de données personnelles.

Les liens d'envoi sont volontairement générés côté service avec `wa.me` ou `mailto` ; aucun message n'est envoyé par le serveur.
