FROM nginx:alpine

# Installera gettext för envsubst
RUN apk add --no-cache gettext

# Kopiera config template
COPY nginx.conf /etc/nginx/nginx.conf.template

# Entrypoint som injicerar INFLUX_TOKEN
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
