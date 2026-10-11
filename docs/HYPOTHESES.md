# Hypothèses

- Le fichier `templates/campus-shop.html` est la référence visuelle et fonctionnelle retenue pour le premier écran.
- Le prototype reste utilisable hors ligne avec ses données locales ; l'API constitue le socle de migration vers la persistance PostgreSQL.
- Les images téléchargées sont stockées dans le volume `uploads` et ne sont pas exposées directement par nginx.
- Le compte administrateur est fourni par `ADMIN_USER` et `ADMIN_PASSWORD`; aucune valeur secrète réelle n'est versionnée.
