#!/bin/sh
# Punto de entrada del contenedor de sipap-sim: aplica migraciones
# (incluida la que carga los datos de prueba, solo la primera vez) y
# levanta Gunicorn.
set -e

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Iniciando Gunicorn..."
exec gunicorn sipap_sim.wsgi:application \
    --bind 0.0.0.0:8001 \
    --workers 2 \
    --access-logfile - \
    --error-logfile -
