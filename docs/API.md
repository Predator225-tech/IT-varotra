# API

L'API FastAPI est préfixée par `/api` et sa documentation interactive est disponible sur `/docs`.

- `POST /api/auth/login` : connexion OAuth2 avec `ADMIN_USER` et `ADMIN_PASSWORD`.
- `GET /api/auth/me` : vérifie le JWT.
- `GET /api/produits` : liste des produits de démonstration protégée par JWT.
- `POST /api/fichiers` : accepte une image JPEG, PNG ou WebP de 5 Mo maximum.

Les liens d'envoi sont volontairement générés côté service avec `wa.me` ou `mailto` ; aucun message n'est envoyé par le serveur.
