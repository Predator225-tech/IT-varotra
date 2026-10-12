# Campus Shop

Back office français pour la gestion des produits, ventes, facilités de paiement et dettes. L'interface de référence est conservée dans [templates/campus-shop.html](templates/campus-shop.html) et est utilisée directement par le conteneur web.

## Démarrage Docker

```sh
cp .env.example .env
docker compose up --build
```

Puis ouvrir <http://localhost:8080>. L'API reste accessible au web via le proxy nginx sur `/api`.

Les navigateurs connectés au même site reçoivent les changements par SSE sans actualisation. Si SSE est indisponible, le frontend utilise un polling de secours toutes les 30 secondes. Pour vérifier : ouvrez `http://localhost:8080` sur deux navigateurs, enregistrez une vente dans l'un et observez l'autre en moins de deux secondes.

En développement, lancez `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build` : Uvicorn recharge automatiquement le backend et les fichiers HTML/CSS sont montés directement dans nginx. Le dépôt ne contient pas Vite/Vue, donc le remplacement automatique du navigateur pendant l'édition frontend n'est pas disponible dans ce prototype ; un rechargement manuel reste nécessaire après une modification frontend.

## Développement

```sh
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Le prototype peut aussi être ouvert directement dans un navigateur pour travailler sur l'interface de référence. En mode Docker, son état est partagé via `/api/sync` et le dossier `data/`; `localStorage` sert seulement de secours hors connexion.

Le fichier `version.json` est généré lors du build Docker et vérifié au démarrage, toutes les cinq minutes et au retour sur l'onglet. Une nouvelle version affiche une bannière de rechargement.
# IT-varotra
