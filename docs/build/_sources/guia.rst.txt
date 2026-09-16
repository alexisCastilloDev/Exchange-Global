Guía del sistema
================

Arquitectura
------------

Global Exchange es una aplicación Django organizada por dominios funcionales:

* ``apps.authentication``: integración OIDC con Keycloak, roles de sesión,
  filtros de plantillas y auditoría de bajas.
* ``apps.clientes``: perfiles de clientes, selección del cliente activo,
  asociaciones de usuarios y métodos de pago.
* ``apps.divisas``: catálogo de divisas, cotizaciones, historial y simulación.
* ``apps.users``: sincronización de usuarios y roles con la API administrativa
  de Keycloak.
* ``global_exchange``: configuración, URLs y vistas generales del proyecto.

Flujo de autenticación
----------------------

#. El usuario inicia sesión mediante Keycloak usando OIDC.
#. El backend valida las claims y extrae los roles de negocio.
#. Los roles efectivos se guardan en ``request.session['keycloak_roles']``.
#. Las vistas comprueban la sesión mediante decoradores o mixins de Django.
#. El callback redirige al usuario hacia el panel apropiado según su rol.

Flujo operativo de divisas
--------------------------

Las divisas activas se muestran en las tasas vigentes. Los roles autorizados
pueden registrar nuevas cotizaciones, que conservan el usuario y la fecha de
actualización.

Un cliente puede calcular tres tipos de operación, cada una persistida con
tasa, comisión y vencimiento hasta que se confirma o se recalcula:

* **Compra/venta contra PYG**: usa la tasa de venta (compra) o de compra
  (venta) de la divisa elegida.
* **Cambio entre dos divisas extranjeras**: triangula por PYG, usando la
  tasa de compra de la divisa origen y la tasa de venta de la divisa
  destino, y expone la tasa cruzada implícita resultante.

El simulador de conversión ofrece los mismos tres modos (compra, venta,
cambio) sin persistir el resultado ni exigir confirmación.

Comisión configurable
----------------------

El porcentaje de comisión aplicado a un cálculo se resuelve en este orden:

#. Comisión personalizada del cliente (campo opcional en su ficha), pensada
   para un trato preferencial único.
#. Comisión configurada para el segmento del cliente (Minorista, VIP,
   Corporativo), editable por ``admin`` y ``analista_cambiario``.
#. Comisión por defecto del sistema (``settings.COMISION_OPERACION_PORCENTAJE``),
   si el segmento no tiene una configuración propia.

Ver ``apps.divisas.models.ConfiguracionComision.porcentaje_para``.

Cómo leer la referencia
-----------------------

La sección :doc:`reference/modules` enlaza la documentación generada con
``automodule``. Cada página se alimenta de los docstrings en español de los
módulos, clases y funciones, e incluye enlaces al código fuente cuando están
disponibles.
