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

Un cliente con un cliente activo seleccionado puede realizar tres tipos de
operación. El cálculo previo ("Calcular importe") no persiste nada: solo
muestra el detalle y su vigencia. La operación se registra recién al
confirmar el importe, siempre en estado "Pendiente de confirmación" y a
nombre del cliente activo:

* **Compra/venta contra PYG**: usa la tasa de venta (compra) o de compra
  (venta) de la divisa elegida. Al confirmarse crea un
  ``apps.divisas.models.CalculoOperacion``.
* **Cambio entre dos divisas extranjeras**: triangula por PYG, usando la
  tasa de compra de la divisa origen y la tasa de venta de la divisa
  destino, y expone la tasa cruzada implícita resultante. Al confirmarse
  (``apps.divisas.views.confirmar_triangulacion_view``) crea un
  ``apps.divisas.models.CalculoTriangulacion`` con las tasas, el equivalente
  en guaraníes, la comisión y el importe a recibir en la divisa destino. Si
  venció el tiempo de reserva o cambió la cotización de cualquiera de las
  dos divisas, exige recalcular.

Los administradores y analistas cambiarios consultan todas las transacciones
(compras, ventas y cambios) en el historial de transacciones
(``apps.divisas.views.HistorialTransaccionesView``), con tipo, estado,
usuario, cliente, divisa, monto, tasa aplicada, comisión e importe final.

El simulador de conversión ofrece los mismos tres modos (compra, venta,
cambio) sin persistir el resultado ni exigir confirmación.

Venta de divisas
----------------

Un cliente vende divisas desde ``/divisas/operar/venta/`` (vista
``apps.divisas.views.CalculoOperacionView`` con ``tipo=venta``). El flujo es:

#. **Cálculo (Paso 1).** El cliente indica divisa y monto. El importe a
   recibir se calcula con la tasa de compra vigente de la divisa, restando la
   comisión del cliente activo
   (``apps.divisas.views._calcular_importe_operacion``, mismo cálculo de la
   HU "Cálculo del importe de la operación"). No se crea ninguna
   transacción todavía.
#. **Confirmación (Paso 2).** ``apps.divisas.views.confirmar_calculo_operacion_view``
   revalida que el cálculo no haya vencido y que la cotización siga siendo
   la usada, recalcula el importe con la tasa actual y crea el
   ``CalculoOperacion`` con estado "Pendiente de confirmación".

Cada transacción registra el tipo de operación ("Venta"), el cliente activo,
la divisa, el monto y la fecha de creación. La operación se rechaza, sin
crear ninguna transacción, cuando:

* El monto es negativo, cero o no numérico
  (``apps.divisas.forms.CalculoOperacionForm``).
* La divisa está inactiva o no existe: el formulario la rechaza con el
  mensaje "La divisa seleccionada está inactiva o no está disponible para
  operar", tanto en el cálculo como en la confirmación.
* La divisa no tiene cotización vigente: se informa que no hay cotización
  disponible.
* El tipo de la ruta no es ``compra`` ni ``venta`` (responde 404).
* El usuario no es un cliente asociado o no tiene un cliente activo
  seleccionado.

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
