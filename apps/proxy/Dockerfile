FROM nginx:alpine

ENV NGINX_ENVSUBST_FILTER="BUCKET|PORT"

COPY default.conf.template /etc/nginx/templates/default.conf.template
