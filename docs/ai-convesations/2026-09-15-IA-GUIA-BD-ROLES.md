# Conversación con IA — Guía de base de datos y mecanismo de roles

**Fecha:** 15/09/2026  
**Herramienta:** GitHub Copilot  
**Proyecto:** Global Exchange

## Contexto

Se necesitaba explicar el esquema actual de PostgreSQL, la función de cada
tabla y la forma en que Keycloak y Django colaboran para autenticar y autorizar.

## Trabajo realizado

Se verificó la configuración de desarrollo y producción, los modelos Django,
las migraciones aplicadas y las tablas existentes en la base activa. El esquema
confirmado contiene 17 tablas: tablas de identidad local, clientes, métodos de
pago, divisas, cotizaciones, cálculos de operaciones, auditoría y tablas
internas de Django.

También se documentó que los roles de negocio no se persisten en una tabla
propia. Keycloak es la fuente de verdad; durante el login sus claims se filtran
y se guardan en `request.session['keycloak_roles']`. Las vistas consultan esa
sesión mediante decoradores, mixins y el context processor del menú.

## Documento agregado

La explicación completa quedó en `docs/source/base-datos-roles.rst` y fue
vinculada desde `docs/source/index.rst`. Incluye:

- responsabilidades de Keycloak, Django y PostgreSQL;
- las 17 tablas y sus propósitos;
- relaciones entre usuarios, clientes, divisas y cálculos;
- roles actuales y mecanismo de autorización;
- diferencia entre tablas de negocio y tablas técnicas;
- datos que deben existir y cambios que no deben hacerse manualmente.

## Verificación

La lista de tablas se obtuvo mediante la introspección de Django. La base
verificada utiliza PostgreSQL, conserva clientes y usuarios, y no contiene el
grupo local legado eliminado por la migración anterior. La guía se integró al
árbol de navegación de Sphinx.
