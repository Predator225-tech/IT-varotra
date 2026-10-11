# Campus Shop

Back office français pour la gestion des produits, ventes, facilités de paiement et dettes. L'interface de référence est conservée dans [templates/campus-shop.html](templates/campus-shop.html) et est utilisée directement par le conteneur web.

## Démarrage Docker

```sh
cp .env.example .env
docker compose up --build
```

Puis ouvrir <http://localhost:8080>. L'API reste accessible au web via le proxy nginx sur `/api`.

## Développement

```sh
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Le prototype peut aussi être ouvert directement dans un navigateur pour travailler sur l'interface de référence. Les données du prototype sont locales au navigateur ; l'intégration des écrans avec l'API sera l'étape suivante.
# IT-varotra
