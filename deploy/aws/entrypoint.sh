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

# Reconstruye la documentación Sphinx (docs/build/, servida por
# global_exchange.views.documentacion) a partir de docs/source/ en cada
# despliegue. Sin este paso, docs/build/ queda como una foto fija del
# último commit en el que alguien la reconstruyó a mano, y no refleja los
# cambios de documentación que sí se desplegaron en el resto de la app.
# Sin "-W" y con el "|| true": un warning o error de Sphinx no debe
# impedir que la aplicación levante.
echo "Reconstruyendo documentación Sphinx..."
python -m sphinx -b html docs/source docs/build || echo "Aviso: la documentación Sphinx no se pudo reconstruir; se sirve la versión existente."

echo "Iniciando Gunicorn..."
exec gunicorn global_exchange.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --access-logfile - \
    --error-logfile -
