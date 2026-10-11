# PROMPT POUR L'AGENT CODEX — Projet « Campus Shop » (back office de revendeur)

Tu es un ingénieur logiciel senior full-stack. Tu dois réaliser ce projet **de A à Z, de façon autonome** : code, base de données, tests, documentation et lancement. Ne me pose pas de questions sauf si tu es réellement bloqué : fais des hypothèses raisonnables et note-les dans `docs/HYPOTHESES.md`.

## 1. Contexte et objectif

Je suis revendeur et je vends des produits dans mon université (Madagascar). Je veux un **back office web** (un seul administrateur : moi) pour :

- gérer mes produits (avec photo) ;
- enregistrer mes ventes, avec ou sans **facilité de paiement** ;
- calculer mon **chiffre d'affaires**, mes **gains**, une **courbe de croissance**, et mes gains sur n'importe quel intervalle de dates **par jour ou par semaine** ;
- suivre les dettes des clients en facilité ;
- produire une **facture PDF** et une **reconnaissance de dette PDF** ;
- choisir, **vente par vente**, d'envoyer ou non la facture au client, et le moyen d'envoi (**WhatsApp** ou **email**), de façon **manuelle** : l'application prépare le message et ouvre WhatsApp ou la messagerie, c'est l'utilisateur qui appuie lui-même sur « envoyer ». **Aucun envoi automatique, aucun serveur SMTP.**

Langue de l'interface : **français**. Monnaie : **Ariary (Ar)**, sans centimes. Le site doit être **responsive** (téléphone en priorité, puis tablette et ordinateur).

Si les fichiers `reference/base.sql` (schéma PostgreSQL) et `reference/campus-shop.html` (prototype fonctionnel en un seul fichier) sont présents dans le dépôt, **lis-les en premier** : ils font foi pour les règles métier, les calculs et le design. Reproduis leur comportement.

## 2. Stack technique imposée

**Backend (Python 3.12)**
- FastAPI, Uvicorn
- SQLAlchemy 2.x + Alembic (migrations)
- PostgreSQL 13+ (driver `psycopg` v3)
- Pydantic v2, pydantic-settings (configuration par variables d'environnement)
- Authentification : JWT (python-jose ou PyJWT), mots de passe hachés avec bcrypt (passlib ou bcrypt)
- PDF : ReportLab (pur Python, sans dépendance système)
- Envoi : aucun service d'envoi côté serveur ; le backend génère seulement les liens `https://wa.me/...` et `mailto:...` avec le message préparé
- Images : Pillow (validation et redimensionnement)
- Tests : pytest + httpx (TestClient), base de test PostgreSQL ou SQLite uniquement si le comportement reste identique
- Qualité : ruff, mypy facultatif

**Frontend**
- Vue 3 (Composition API, `<script setup>`), Vite, TypeScript
- Vue Router, Pinia, Axios
- Graphiques : Chart.js via `vue-chartjs` (ou SVG maison)
- CSS maison avec variables CSS (pas de grosse bibliothèque d'interface)
- Tests : Vitest pour la logique (formatage, validation)

**Infrastructure**
- `docker-compose.yml` : `db` (PostgreSQL), `api`, `web` (build Vite servi par nginx), volume pour `uploads/`
- Fichier `.env.example` complet. **Aucun secret dans le dépôt.**

## 3. Structure du dépôt

```
campus-shop/
├─ backend/
│  ├─ app/ (main.py, config.py, db.py, deps.py, security.py)
│  │   ├─ models/  schemas/  routers/  services/  pdf/  utils/
│  ├─ alembic/  tests/  pyproject.toml  Dockerfile
├─ frontend/
│  ├─ src/ (api/, stores/, router/, views/, components/, composables/, styles/)
│  ├─ index.html  vite.config.ts  Dockerfile  nginx.conf
├─ reference/ (base.sql, campus-shop.html si fournis)
├─ docs/ (README, HYPOTHESES.md, API.md)
├─ docker-compose.yml  .env.example  README.md
```

## 4. Modèle de données (PostgreSQL, via Alembic)

Montants : `NUMERIC(12,0)`. Clés primaires : identités auto. Ajoute les index sur les dates et les clés étrangères.

**utilisateur** : id, nom_utilisateur (unique), mot_de_passe_hash, created_at. Un compte admin est créé par un script `seed` à partir de `ADMIN_USER` et `ADMIN_PASSWORD` du `.env`.

**client** : id_client, nom.

**produit** : id_produit, nom, prix_achat ≥ 0, prix_vente ≥ 0, stock ≥ 0, photo (id de fichier, nullable), facilite_paiement (bool, défaut faux), nb_tranches (2 à 6), intervalle_jours (7, 14 ou 30), created_at.
Contrainte : si `facilite_paiement` est vrai, `nb_tranches` et `intervalle_jours` sont obligatoires ; sinon ils sont nuls. La facilité est **initialisée par l'admin à la création du produit**.

**vente** : id_vente, numero_facture (entier séquentiel unique), id_client, id_produit, date_vente, quantite > 0, prix_achat_unitaire, prix_vente_unitaire (copiés du produit au moment de la vente : un changement de prix ne modifie jamais les anciens gains), avec_facilite (bool, **faux par défaut**), acompte ≥ 0 et ≤ total, **canal_envoi** (`aucun` par défaut / `whatsapp` / `email` : choix de l'utilisateur pour envoyer la facture), **destinataire_envoi** (numéro ou email, nul si `aucun`).

**paiement** : id_paiement, id_vente, date_paiement, montant > 0.

**echeance** : (id_vente, numero_tranche) clé primaire, date_echeance, montant_prevu > 0.

**reconnaissance_dette** (au plus une par vente, **uniquement si la vente est avec facilité et que l'acompte est inférieur au total**) : id_reconnaissance, id_vente (unique), numero_etu (exactement 4 chiffres, regex `^[0-9]{4}$`), photo_client (id de fichier), telephone, a_whatsapp (bool : ce numéro est avec ou sans WhatsApp), email (nullable), signature (id de fichier, image PNG), date_signature, montant_reconnu (= total − acompte).

**fichier** : id (UUID), chemin, type_mime, taille, created_at. Les images sont stockées sur disque (`uploads/`) avec un nom aléatoire.

## 5. Règles métier (à implémenter dans la couche `services/`, avec tests)

1. **Total** = quantité × prix_vente_unitaire. **Gain** = quantité × (prix_vente_unitaire − prix_achat_unitaire), compté à la date de la vente, même si le client n'a pas tout payé.
2. **Vente sans facilité (défaut)** : paiement comptant. L'acompte est forcé au total, un paiement du total est créé, aucune reconnaissance.
3. **Vente avec facilité** : autorisée seulement si `produit.facilite_paiement` est vrai (sinon erreur 422). L'acompte est saisi (0 ≤ acompte ≤ total) et crée un premier paiement s'il est > 0.
   - Si acompte = total : c'est une vente comptant, pas de reconnaissance.
   - Si acompte < total : la **reconnaissance de dette est obligatoire** : numéro ETU à 4 chiffres, photo du client, numéro de téléphone (au moins 9 chiffres), option avec/sans WhatsApp, signature (PNG en base64), case « le client reconnaît la dette » cochée. Sans tout cela, refuser la vente.
4. **Stock** : refuser si quantité > stock (erreur 409 avec message clair), sinon décrémenter dans la même transaction.
5. **Échéancier** (vente avec facilité et reste > 0) : reste = total − acompte ; montant de base = `floor(reste / nb_tranches)` ; tranche k (1 à n) à la date `date_vente + k × intervalle_jours` ; la dernière tranche reçoit le reliquat. Génération dans la même transaction que la vente.
6. **Paiement** : refuser s'il dépasse le reste à payer. Montant > 0.
7. **Reste** = total − somme des paiements.
8. **En retard** = reste > 0 **et** total payé < acompte + somme des montants d'échéances dont la date ≤ aujourd'hui.
9. **Prochaine échéance** d'une vente = première tranche non couverte par le total payé (calcul cumulé), avec le montant encore dû sur cette tranche.
10. **Numéro de facture** : séquentiel, jamais réutilisé.
11. **Suppression d'un produit** : refusée (409) s'il a des ventes ; proposer sinon la suppression.
12. **Normalisation du téléphone** : chiffres uniquement ; si le numéro commence par `261` on le garde, sinon on retire le `0` initial et on préfixe `261` (utilisé pour les liens WhatsApp).
13. **Envoi de la facture (manuel)** : à la création d'une vente, l'utilisateur choisit `canal_envoi` = `aucun` (**défaut**), `whatsapp` ou `email`.
    - `whatsapp` : le destinataire est un numéro d'au moins 9 chiffres. `email` : le destinataire est une adresse email valide.
    - Si le destinataire est vide et que la vente a une reconnaissance de dette, reprendre son téléphone (pour `whatsapp`) ou son email (pour `email`).
    - Si le destinataire reste invalide, **refuser la vente (422) sans rien enregistrer** : la validation se fait avant l'enregistrement.
    - Le serveur n'envoie rien : il fournit les liens et le message. Message en français : bonjour + nom du client, n° de facture et date, article et quantité, total, déjà payé, reste à payer, prochaine échéance si facilité, « Merci pour votre confiance. — Campus Shop ». Le texte est encodé correctement dans les URL (`encodeURIComponent` côté client, `urllib.parse.quote` côté serveur).

## 6. API REST (préfixe `/api`, JSON, documentation OpenAPI automatique)

Toutes les routes sauf la connexion exigent un JWT (`Authorization: Bearer`).

- `POST /auth/login` → `{access_token}` ; `GET /auth/me`
- `GET/POST /produits`, `GET/PUT/DELETE /produits/{id}` ; `POST /produits/{id}/photo` (multipart)
- `GET /clients?q=`
- `POST /fichiers` (multipart, image uniquement, 5 Mo max, redimensionnée à 800 px max, convertie en JPEG ou PNG) → `{id}` ; `GET /fichiers/{id}` (authentifié)
- `GET /ventes` (filtres : `date_debut`, `date_fin`, `client`, `statut` = payé / en_cours / en_retard, pagination)
- `POST /ventes` : corps JSON `{id_produit, quantite, client_nom, avec_facilite, acompte, reconnaissance?, canal_envoi?, destinataire_envoi?}` où `reconnaissance = {numero_etu, telephone, a_whatsapp, email?, photo_fichier_id, signature_png_base64, case_cochee}`
- `GET /ventes/{id}` (détail avec paiements, échéancier, reconnaissance)
- `POST /ventes/{id}/paiements` `{montant}`
- `GET /ventes/{id}/facture.pdf` ; `GET /ventes/{id}/reconnaissance.pdf` (404 si la vente n'en a pas)
- `GET /ventes/{id}/liens-envoi?canal=&destinataire=` → `{whatsapp_url, mailto_url, message}` : liens `https://wa.me/<numéro normalisé>?text=...` et `mailto:<email>?subject=...&body=...` avec le message préparé ; `canal` et `destinataire` sont facultatifs (par défaut les valeurs enregistrées sur la vente) ; erreur 422 si le destinataire est invalide
- Pas de route d'envoi automatique : l'envoi se fait toujours à la main depuis le navigateur de l'utilisateur.
- `GET /dettes` (ventes avec reste > 0, avec ETU, téléphone, a_whatsapp, prochaine échéance, statut en retard)
- `GET /stats/resume?date_debut&date_fin` → chiffre d'affaires, gains, marge en %, nombre de ventes, reste à encaisser total
- `GET /stats/gains?date_debut&date_fin&regroupement=jour|semaine` → liste `{periode, chiffre_affaires, gain}` (semaine commençant le lundi)
- `GET /stats/croissance?jours=30` → chiffre d'affaires cumulé par jour

Codes d'erreur cohérents (400, 401, 404, 409, 422) avec un message en français exploitable par l'interface.

## 7. Frontend : pages et comportements

**Design** (reprendre `reference/campus-shop.html`) : fond `#F6F7FB`, texte `#101828`, gris `#5B6478`, bordures `#E3E7F1`, bleu principal `#2438F0`, fond bleu clair `#E8ECFF`, vert `#0E7A4B` / `#DDF5E8`, orange `#8A4B00` / `#FFEBCB`, rouge `#B42318` / `#FEE4E2`. Polices : **Bricolage Grotesque** (titres) et **Figtree** (texte) via Google Fonts, avec repli système. Boutons arrondis, cibles tactiles d'au moins 44 px, focus clavier visible, contrastes accessibles, `label` réels pour chaque champ.

**Navigation** : barre en haut, défilante sur petit écran : Tableau de bord, Produits, Ventes, Facilités et dettes. Bouton « Nouvelle vente ». Guard de routes : redirection vers `/connexion` sans jeton valide.

1. **Connexion** : nom d'utilisateur et mot de passe, message d'erreur clair.
2. **Tableau de bord** : grand bloc bleu avec les **gains de la période** ; sélecteurs de dates « Du / Au » (par défaut les 7 derniers jours) ; bascule **Par jour / Par semaine** ; quatre indicateurs (chiffre d'affaires, gains, marge, reste à encaisser) ; détail des gains par période en barres horizontales ; **courbe de croissance** (chiffre d'affaires cumulé sur 30 jours).
3. **Produits** : formulaire de création avec **photo** (choix de fichier ou appareil photo, aperçu), nom, prix d'achat, prix de vente, stock, **Facilité de paiement** (Non autorisée / Autorisée) et, si autorisée, nombre de tranches (2 à 6) et intervalle (7, 14, 30 jours). Tableau avec miniature, gain unitaire, stock, badge de facilité, bouton supprimer (avec confirmation).
4. **Ventes** : formulaire avec produit (photo et prix affichés), quantité, client, et **Mode de paiement : « Sans facilité de paiement » (par défaut) / « Avec facilité de paiement »** (option désactivée si le produit n'autorise pas la facilité). Sans facilité : montant payé = total, champ verrouillé. Avec facilité : champ acompte (par défaut la moitié) et, si acompte < total, apparition du bloc **Reconnaissance de dette** : numéro ETU (4 chiffres), téléphone, sélecteur **Avec WhatsApp / Sans WhatsApp**, email (facultatif), photo du client (appareil photo frontal ou fichier), **zone de signature** dessinée au doigt ou à la souris (événements `pointer`, `touch-action: none`, bouton « Effacer »), case de reconnaissance. Champ **Envoi de la facture** : « Ne pas envoyer » (**défaut**) / « Envoyer par WhatsApp » / « Envoyer par email ». Quand un envoi est choisi, un champ destinataire apparaît (libellé et type adaptés : numéro WhatsApp ou email) ; s'il est laissé vide et qu'une reconnaissance existe, il reprend son téléphone ou son email. Validation côté client identique aux règles serveur, **y compris le destinataire, avant tout enregistrement**. Après enregistrement : ouvrir la facture, puis, si un envoi a été choisi, **ouvrir directement WhatsApp (nouvel onglet) ou la messagerie** avec le message préparé, dans le même geste utilisateur pour ne pas être bloqué par le navigateur ; l'utilisateur appuie lui-même sur « envoyer ». Liste des ventes avec statut (Payé / Reste X / En retard), boutons Facture et Reconnaissance.
5. **Facilités et dettes** : tableau des dettes (photo, nom, ETU, téléphone avec lien WhatsApp de rappel si le numéro est avec WhatsApp, produit, total, payé, reste, prochaine échéance, statut), champ et bouton « Encaisser » un versement.
6. **Facture / reconnaissance** : affichage de la facture (n°, date, client, article avec photo, total, payé, reste, historique des paiements, échéancier, lignes de signature), boutons **Télécharger le PDF** et **Imprimer**, et un bloc **Envoyer la facture** (masqué à l'impression) : champ numéro WhatsApp et champ email (préremplis avec ceux de la reconnaissance ou de la vente, modifiables), boutons **Envoyer par WhatsApp** (lien `wa.me`, numéro normalisé), **Envoyer par email** (`mailto:`) et **Partager** (Web Share API : avec le PDF en fichier si `navigator.canShare({files})` le permet, sinon texte seul ; bouton masqué si l'API n'existe pas). Ajoute une aide visible : « Le PDF n'est pas joint automatiquement : télécharge-le, puis ajoute-le à la main dans WhatsApp ou ton email. » Messages d'erreur clairs pour un numéro ou un email invalide.

Gère les états de chargement, d'erreur et les listes vides avec des messages utiles. Notifications (toasts) pour chaque action. Les images protégées sont chargées via Axios en `blob` (l'authentification passe par l'en-tête) puis affichées avec des URL d'objet.

## 8. Documents PDF (ReportLab)

- **Facture** : en-tête « Campus Shop », n° de facture sur 4 chiffres, date, client (avec ETU si reconnaissance), tableau de l'article, total / payé / reste, paiements, échéancier si facilité, lignes de signature, mention « Merci pour votre confiance ».
- **Reconnaissance de dette** : « Je soussigné(e) [nom], étudiant(e) portant le numéro ETU [ETU], joignable au [téléphone] ([avec WhatsApp / sans WhatsApp]), reconnais devoir à Campus Shop la somme de [montant], solde de mon achat de [produit × quantité] d'un montant total de [total] effectué le [date]. J'ai versé un acompte de [acompte]. Je m'engage à payer ce solde en [n] tranche(s) selon l'échéancier suivant : … », photo du client, signature du client (image) et ligne de signature du vendeur. Ajoute une note : « modèle simple, à faire relire par un juriste pour avoir une valeur juridique ».
- Montants formatés en français (`1 234 567 Ar`), dates en français.

## 9. Sécurité et données personnelles

Les photos, numéros ETU, téléphones et signatures sont des **données personnelles** : protège-les.

- Routes protégées par JWT (expiration configurable), hachage bcrypt, limite de tentatives de connexion (rate limiting simple en mémoire).
- CORS restreint aux origines du `.env`.
- Validation stricte des fichiers : type MIME réel (Pillow), taille maximale, noms aléatoires, aucun accès direct au dossier `uploads/` depuis nginx.
- Requêtes SQL uniquement via l'ORM (pas de SQL construit par concaténation) ; échapper les sorties HTML côté Vue (pas de `v-html` sur des données utilisateur).
- Journaux sans mots de passe, jetons ni données personnelles.
- Les numéros de téléphone et emails ne sont jamais écrits dans les journaux ; les liens d'envoi sont générés à la demande et non stockés.

## 10. Tests (obligatoires)

Backend (pytest) : au minimum
- calcul de total, gain, reste ;
- vente sans facilité (acompte forcé, pas de reconnaissance) ;
- facilité refusée pour un produit non autorisé ;
- reconnaissance obligatoire si acompte < total (ETU invalide, photo ou signature manquante, téléphone trop court) ;
- stock insuffisant et décrément de stock ;
- échéancier (répartition, reliquat sur la dernière tranche, dates) ;
- paiement supérieur au reste refusé ;
- statut « en retard » ;
- statistiques sur un intervalle, par jour et par semaine (semaine commençant le lundi) ;
- envoi de la facture : `canal_envoi` par défaut `aucun` ; WhatsApp avec numéro invalide → 422 et **aucune vente enregistrée** ; email invalide → 422 ; destinataire vide repris de la reconnaissance ; normalisation du numéro (`034 00 000 00` → `261340000000`, `+261...` conservé) ; liens `wa.me` et `mailto:` correctement encodés ;
- accès refusé sans jeton.

Frontend (Vitest) : formatage des montants, validation ETU, calcul de l'aperçu d'échéancier, validation du destinataire (numéro et email), normalisation du numéro et construction du message d'envoi.

## 11. Données d'exemple et lancement

- Script `seed` : crée l'admin, 4 produits (Clé USB 32 Go 18 000/25 000 en facilité 2 tranches/14 j ; Powerbank 10 000 mAh 45 000/60 000 en facilité 3 tranches/14 j ; Cahier 200 pages 2 000/3 000 sans facilité ; Écouteurs filaires 6 000/10 000 sans facilité) et une trentaine de ventes sur 30 jours dont quelques-unes en facilité avec reconnaissance et quelques retards.
- `docker compose up --build` doit suffire pour tout lancer ; ajoute aussi les commandes pour lancer le backend et le frontend en développement sans Docker.

## 12. Méthode de travail et livrables

Travaille par étapes, avec un commit clair à la fin de chacune, et **lance les tests à chaque étape** :

1. Squelette du dépôt, Docker, configuration.
2. Base de données, modèles, migrations Alembic, seed.
3. Authentification.
4. Produits et fichiers.
5. Ventes, paiements, échéancier, reconnaissance, règles métier et tests.
6. Statistiques.
7. PDF et liens d'envoi manuel (WhatsApp, email), sans SMTP.
8. Frontend : connexion, tableau de bord, produits, ventes, dettes, facture.
9. Finitions : responsive, accessibilité, états de chargement et d'erreur.
10. Documentation : `README.md` (installation, lancement, variables d'environnement, déploiement), `docs/API.md`, `docs/HYPOTHESES.md`.

**Critères d'acceptation** (vérifie-les tous avant de terminer) :
- [ ] `docker compose up --build` démarre l'ensemble sans erreur et le seed fonctionne.
- [ ] Tous les tests backend et frontend passent.
- [ ] Je peux me connecter, créer un produit avec photo et statut de facilité, et le voir dans la liste.
- [ ] Une vente sans facilité n'exige aucun champ de reconnaissance.
- [ ] Une vente avec facilité exige ETU (4 chiffres), téléphone avec option WhatsApp, photo, signature et case cochée, puis génère l'échéancier.
- [ ] Le tableau de bord affiche les gains sur un intervalle de dates, par jour et par semaine, et la courbe de croissance.
- [ ] Je peux encaisser un versement, voir le statut « en retard », et ouvrir le lien WhatsApp de rappel.
- [ ] La facture et la reconnaissance de dette se téléchargent en PDF et s'impriment correctement.
- [ ] Dans le formulaire de vente, je peux choisir « Ne pas envoyer » (défaut), « WhatsApp » ou « email » ; la vente est refusée sans rien enregistrer si le destinataire est invalide ; après l'enregistrement, WhatsApp ou ma messagerie s'ouvre avec le message préparé et je dois appuyer moi-même sur « envoyer ».
- [ ] Depuis une facture, les boutons WhatsApp, email et Partager fonctionnent comme décrit et l'aide sur la pièce jointe PDF est visible.
- [ ] L'interface est utilisable sur un écran de 375 px de large.
- [ ] Aucun secret n'est présent dans le dépôt.

À la fin, résume ce qui a été fait, ce qui reste à faire et les hypothèses prises.