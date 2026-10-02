#!/bin/sh
# Punto de entrada del contenedor de la app en producción:
# aplica migraciones, recolecta estáticos y levanta Gunicorn.
# Se corre una sola vez por despliegue (no hay tareas en segundo plano
# ni locking entre réplicas porque, en este entorno académico, solo
# existe una instancia de la app).
set -e

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

echo "Iniciando Gunicorn..."
exec gunicorn global_exchange.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --access-logfile - \
    --error-logfile -
