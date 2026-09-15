# Conversación con IA — Unificación del rol cambiario

**Fecha:** 15/09/2026  
**Herramienta:** GitHub Copilot  
**Proyecto:** Global Exchange

## Contexto

El sistema tenía referencias a un rol duplicado para la operación cambiaria. La
convención definitiva del proyecto es usar únicamente `analista_cambiario`.
La autenticación y los roles de negocio se administran en Keycloak; Django solo
conserva los roles efectivos en la sesión y no debe modificar las relaciones de
clientes o usuarios para resolver esta limpieza.

## Conversación simulada

**Desarrollador:** La función de análisis cambiario debe tener un único nombre.

**IA:** Se eliminaron las referencias de autorización al rol duplicado en el
context processor, las vistas de divisas y las pruebas. El acceso operativo
queda autorizado únicamente para `analista_cambiario`, junto con los roles que
ya tenían permiso independiente, como `admin` y `cliente` cuando corresponde.

**Desarrollador:** ¿Qué pasa con los datos existentes?

**IA:** Se agregó la migración `0006_eliminar_rol_agente`. Es idempotente y borra
solo el grupo local legado que tenga ese nombre, junto con sus relaciones de
permisos. No elimina usuarios, clientes, asociaciones, cotizaciones ni otros
roles. La asignación equivalente debe gestionarse en Keycloak usando
`analista_cambiario`.

**Desarrollador:** ¿Se tocó la gestión de clientes o usuarios?

**IA:** No. Solo se actualizaron pruebas que simulaban el rol duplicado y la
redacción de la guía de entorno. Los modelos, vistas y relaciones de clientes y
usuarios permanecen sin cambios.

## Verificación

- `python manage.py check`: sin problemas.
- `python manage.py makemigrations --check --dry-run`: sin cambios pendientes.
- Suite completa: `102 passed, 0 failed`.
- La migración se ejecuta de forma segura cuando el grupo legado existe y no
  produce cambios cuando ya fue eliminado.
