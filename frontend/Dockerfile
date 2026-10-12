FROM nginx:1.27-alpine
COPY templates/campus-shop.html /usr/share/nginx/html/index.html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
RUN printf '{"id":"%s"}\n' "$(date -u +%Y%m%d%H%M%S)" > /usr/share/nginx/html/version.json
