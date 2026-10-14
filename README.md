# Campus Shop

Back office français pour la gestion des produits, ventes, facilités de paiement et dettes. L'interface de référence est conservée dans [templates/campus-shop.html](templates/campus-shop.html) et est utilisée directement par le conteneur web.

## Démarrage Docker

```sh
cp .env.example .env
docker compose up --build
```

Puis ouvrir <https://localhost:8443> ou `https://192.168.0.91:8443` depuis le téléphone. Si votre adresse réseau redevient `192.168.0.31`, utilisez cette adresse. Le port HTTP `8080` redirige vers HTTPS. Le certificat local est auto-signé : acceptez l'avertissement du navigateur sur le réseau local.

Pour activer WebAuthn sur Android, installez le certificat CA `certs/campus-shop-ca.crt` dans les paramètres du téléphone : **Paramètres > Sécurité > Chiffrement et identifiants > Installer un certificat > Certificat CA**. Transférez d'abord ce fichier sur le téléphone, installez-le, redémarrez Chrome, puis vérifiez que le X rouge a disparu. Le certificat CA est local et n'est pas publié dans Git.

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

Pour une vente avec facilité de paiement, le formulaire propose `Sans empreinte` ou `Avec empreinte biométrique`. Le second choix utilise WebAuthn/Passkey : le téléphone vérifie l'empreinte, le serveur vérifie la preuve cryptographique, puis la reconnaissance est validée. L'empreinte elle-même n'est jamais envoyée ni stockée.

La première utilisation de `Avec empreinte biométrique` enregistre la passkey sur l'appareil. WebAuthn lie cette passkey à l'origine HTTPS et à l'identifiant de confiance (`WEBAUTHN_RP_ID`). Utilisez toujours la même adresse, par exemple `https://192.168.0.91:8443`; ne mélangez pas `.91`, `.31` et `localhost` pour une même inscription. Les identifiants biométriques sont actuellement conservés en mémoire dans le prototype et devront être réinscrits après un redémarrage de l'API.
# IT-varotra

## Déploiement Netlify

Netlify héberge le frontend statique. L'API FastAPI et PostgreSQL doivent rester accessibles sur un hébergeur séparé (le `docker-compose.yml` local n'est pas déployé par Netlify). Déployez d'abord l'API avec une base PostgreSQL persistante et une adresse HTTPS, puis configurez dans Netlify la variable `API_BASE_URL` avec l'URL publique de l'API, sans barre oblique finale, par exemple `https://api.exemple.com`. Le build échoue volontairement si cette variable manque ou ne commence pas par HTTPS.

Dans Netlify, importez le dépôt Git et laissez `netlify.toml` fournir la commande de build et le dossier publié (`dist`). Pour que l'API accepte le frontend, réglez `CORS_ORIGINS` côté API sur l'origine Netlify exacte, par exemple `https://nom-du-site.netlify.app` (sans chemin final). Si vous utilisez un domaine personnalisé, mettez son origine à la place. Configurez également `WEBAUTHN_RP_ID` avec le nom d'hôte du site (sans `https://`) et `WEBAUTHN_ORIGIN` avec son URL HTTPS exacte ; les passkeys sont liées à ce domaine et devront être réinscrites après un changement de domaine.

Avant de rendre le site public, remplacez les mots de passe de démonstration et `JWT_SECRET` par des valeurs fortes dans les variables secrètes de l'hébergeur API. Le fichier `.env` local est ignoré pour les prochains ajouts, mais il est déjà suivi par Git et reste dans son historique : retirez-le avec `git rm --cached .env`, puis renouvelez ses identifiants, car une suppression du dernier commit ne les efface pas de l'historique. N'ajoutez jamais ces secrets à Netlify ou au dépôt. Vérifiez ensuite `/api/health`, l'ouverture du site en HTTPS, la connexion à l'API, les mises à jour en direct et la conservation des données après redémarrage de l'API. Les fichiers d'envoi et factures doivent aussi être placés dans un stockage persistant côté API.
