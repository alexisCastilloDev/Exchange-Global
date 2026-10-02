# Imagen de producción de Global Exchange (Django + Gunicorn).
# El reverse proxy (Nginx) y Keycloak corren en contenedores separados,
# definidos en deploy/aws/docker-compose.yml.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# libpq-dev + gcc: requeridos para compilar psycopg2-binary en algunas
# arquitecturas; se eliminan después de instalar para no inflar la imagen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x deploy/aws/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["deploy/aws/entrypoint.sh"]
