#!/usr/bin/env bash
set -euo pipefail

export DOMAIN="${DOMAIN:-ritclinic-utils.ru}" 
export BASE_DIR="${BASE_DIR:-/home/shanti/rit-utils}"
export NGINX_CONTAINER="${NGINX_CONTAINER:-rit-utils-nginx}"

WEBROOT="${BASE_DIR}/certbot-webroot"
LE="/etc/letsencrypt"
LIB="/var/lib/letsencrypt"

echo "🔄 Renew SSL: ${DOMAIN}"
sudo docker run --rm --name "certbot-renew-${DOMAIN}" \
  -v "${LE}:/etc/letsencrypt" \
  -v "${LIB}:/var/lib/letsencrypt" \
  -v "${WEBROOT}:/var/www/certbot" \
  certbot/certbot renew \
  --cert-name "${DOMAIN}" \
  --webroot -w /var/www/certbot

sudo mkdir -p "${BASE_DIR}/nginx/ssl/renewal"
sudo cp -aL "${LE}/live/${DOMAIN}" "${BASE_DIR}/nginx/ssl/live/"
sudo cp -aL "${LE}/archive/${DOMAIN}" "${BASE_DIR}/nginx/ssl/archive/"
sudo cp -a "${LE}/renewal/${DOMAIN}.conf" "${BASE_DIR}/nginx/ssl/renewal/"

sudo docker exec "${NGINX_CONTAINER}" nginx -t
sudo docker exec "${NGINX_CONTAINER}" nginx -s reload

echo "✅ Готово: ${DOMAIN}"
