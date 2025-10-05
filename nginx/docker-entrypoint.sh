#!/bin/sh
set -e

# Injicera INFLUX_TOKEN i nginx config
envsubst '$INFLUX_TOKEN' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

exec "$@"
