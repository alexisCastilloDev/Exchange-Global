# Registro consolidado de trabajo con IA

**Fecha:** 15/09/2026  
**Herramienta:** GitHub Copilot  
**Proyecto:** Global Exchange

Este archivo consolida toda la documentación de trabajo realizada durante el
15/09/2026.

## 1. Normalización de docstrings

Se revisó todo el código Python del proyecto mediante AST y se agregaron o
corrigieron docstrings en español para módulos, clases y funciones. Se
incluyeron aplicaciones, modelos, vistas, formularios, servicios, migraciones,
scripts y pruebas.

La validación final confirmó que todos los archivos Python tienen docstrings y
la suite de pruebas pasó correctamente.

## 2. Documentación con Sphinx

Se corrigió la configuración de Sphinx para que la documentación se lea y
navegue correctamente:

- Se habilitó `sphinx_rtd_theme`.
- Se agregó una portada más clara y una guía de arquitectura.
- Se configuró `autodoc` para mostrar tipos y firmas de forma legible.
- Se agregó `custom.css` para mejorar tipografía, tablas, admoniciones y código.
- Se corrigió la advertencia causada por la carpeta `_static` inexistente.
- La compilación estricta con `-W` terminó sin errores ni advertencias.

## 3. Base de datos y roles

La base activa utiliza PostgreSQL. Las tablas de negocio principales son:

- `auth_user`: representación local de usuarios.
- `clientes_cliente`: perfil comercial del cliente.
- `clientes_cliente_usuarios`: asociaciones muchos a muchos entre clientes y usuarios.
- `clientes_metodopago`: métodos de pago.
- `divisas_divisa`: catálogo de divisas.
- `divisas_cotizacion`: historial de tasas de compra y venta.
- `divisas_calculooperacion`: cálculos previos con comisión y vencimiento.
- `authentication_historialbaja`: auditoría de bajas lógicas.

También existen las tablas técnicas de Django para sesiones, migraciones,
permisos, grupos, tipos de contenido y administración.

Keycloak es la fuente de verdad para roles. Django recibe las claims OIDC,
filtra roles técnicos y guarda los roles de negocio en
`request.session['keycloak_roles']`. Las vistas usan esa sesión mediante
mixins y decoradores.

Los roles funcionales vigentes son:

- `admin`: administración general.
- `analista_cambiario`: cotizaciones y operación cambiaria operativa.
- `usuarios`: gestión de usuarios.
- `gestion_roles`: administración de roles en Keycloak.
- `cliente`: operaciones propias del cliente y métodos de pago.

Se eliminó el rol duplicado anterior mediante una migración idempotente, sin
modificar usuarios, clientes ni asociaciones.

## 4. Cálculo de importes

Se implementó el flujo de compra y venta de divisas:

- Compra: usa la tasa de venta y suma la comisión.
- Venta: usa la tasa de compra y descuenta la comisión.
- La comisión actual es `1.00%` y queda configurable.
- Cada cálculo se guarda con tasa, comisión, monto final y vencimiento.
- La confirmación rechaza cálculos vencidos y obliga a recalcular.
- La divisa base es PYG; no se ofrece como opción seleccionable en compra/venta.

La interfaz incluye los accesos de Comprar divisas y Vender divisas, con un
desglose ordenado de operación, monto, tasa, comisión e importe final, usando
dos decimales.

## 5. Correcciones de interfaz y permisos

Se corrigió el menú lateral para que:

- “Tasas actuales” solo quede activo en su propia ruta.
- Comprar y Vender divisas solo sean visibles para usuarios con rol `cliente`
  y una asociación activa a un cliente.
- Administradores y analistas no vean esos accesos ni puedan usar sus URLs.
- Los clientes sigan viendo las tasas, pero sin fecha ni usuario de la última
  actualización.
- Administradores y analistas conserven la información de auditoría de tasas.

La restricción se aplica tanto en la interfaz como en las vistas y en la
confirmación de la operación; ocultar enlaces no es la única protección.

## 6. Verificación final

- Suite completa: `104 passed, 0 failed`.
- Pruebas específicas de compra/venta, visibilidad y auditoría: `7 passed`.
- `manage.py check`: sin problemas.
- Migraciones sincronizadas.
- Documentación Sphinx compilada con `-W` sin advertencias.
