FROM nginx:1.27-alpine
COPY certs/campus-shop.key /etc/nginx/certs/campus-shop.key
COPY certs/campus-shop.crt /etc/nginx/certs/campus-shop.crt
COPY templates/campus-shop.html /usr/share/nginx/html/index.html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
RUN printf '{"id":"%s"}\n' "$(date -u +%Y%m%d%H%M%S)" > /usr/share/nginx/html/version.json
