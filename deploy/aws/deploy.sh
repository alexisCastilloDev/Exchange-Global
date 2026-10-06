#!/usr/bin/env bash
# Despliegue en la EC2. Lo ejecuta GitHub Actions vía SSM (como usuario
# ubuntu) después de hacer git pull de main. También se puede correr a mano:
#   bash ~/global_exchange/deploy/aws/deploy.sh
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE=(docker compose --env-file ../../.env)

echo "==> Commit desplegado: $(git rev-parse --short HEAD) (rama $(git branch --show-current))"

echo "==> Construyendo y levantando contenedores"
"${COMPOSE[@]}" up -d --build

echo "==> Reiniciando Nginx (para que resuelva las IPs nuevas de app y keycloak)"
"${COMPOSE[@]}" restart nginx

echo "==> Limpiando imágenes viejas para no llenar el disco"
docker image prune -f

DOMINIO=$(grep -E '^DOMINIO=' ../../.env | cut -d= -f2-)
echo "==> Verificando que https://${DOMINIO}/ responda"
for i in $(seq 1 20); do
  if curl -fsS -o /dev/null "https://${DOMINIO}/"; then
    echo "==> Sitio respondiendo correctamente"
    "${COMPOSE[@]}" ps
    exit 0
  fi
  sleep 6
done

echo "ERROR: el sitio no respondió después de 2 minutos" >&2
"${COMPOSE[@]}" ps >&2
"${COMPOSE[@]}" logs --tail 50 app >&2
exit 1
