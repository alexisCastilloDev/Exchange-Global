Guía del sistema
================

Arquitectura
------------

Global Exchange es una aplicación Django organizada por dominios funcionales:

* ``apps.authentication``: integración OIDC con Keycloak, roles de sesión,
  filtros de plantillas y auditoría de bajas.
* ``apps.caja``: apertura de caja y saldo inicial por moneda de un cajero.
* ``apps.clientes``: perfiles de clientes, selección del cliente activo,
  asociaciones de usuarios y métodos de pago.
* ``apps.divisas``: catálogo de divisas, cotizaciones, historial y simulación.
* ``apps.users``: sincronización de usuarios y roles con la API administrativa
  de Keycloak.
* ``global_exchange``: configuración, URLs y vistas generales del proyecto.

Formato numérico
----------------

Todos los montos, tasas y comisiones que se muestran en pantalla usan "."
como separador de miles y "," como separador decimal (por ejemplo
``747.400,00``), la convención paraguaya/argentina. Se logra con
``USE_THOUSAND_SEPARATOR = True`` más un módulo de formato propio
(``global_exchange/formats/en_US/formats.py``, referenciado desde
``FORMAT_MODULE_PATH``) que sobreescribe, solo para los separadores
numéricos, lo que Django trae por defecto para ``LANGUAGE_CODE = 'en-us'``
— sin cambiar ese ``LANGUAGE_CODE`` ni, por lo tanto, los mensajes de
validación en inglés que el resto del proyecto ya reemplaza a mano por
mensajes en español.

Los campos ocultos que viajan entre pasos (por ejemplo ``monto``,
``cotizacion_id`` o ``vence_en_timestamp`` en los formularios de "Calcular
importe" y "Confirmar operación") se renderizan con el filtro
``|unlocalize`` (``{% load l10n %}``) para que sigan llegando sin
separadores: esos valores no se muestran, se vuelven a parsear en el
servidor, y un separador de miles los rompería.

Flujo de autenticación
----------------------

#. El usuario inicia sesión mediante Keycloak usando OIDC.
#. El backend valida las claims y extrae los roles de negocio.
#. Los roles efectivos se guardan en ``request.session['keycloak_roles']``.
#. Las vistas comprueban la sesión mediante decoradores o mixins de Django.
#. El callback (``apps.authentication.views.CustomOIDCCallbackView.login_success``)
   redirige siempre a "Inicio" (``home``), sin importar el rol: cada pantalla de
   inicio ya muestra únicamente los accesos que corresponden al rol del usuario.

Administración de usuarios y roles vía Keycloak
-------------------------------------------------

``apps.users.services`` administra usuarios y realm roles contra la Admin API de
Keycloak (sincronizar usuarios, consultar o asignar roles): todo vía
``python-keycloak``, sin persistir roles en ``auth.Group``/``auth.Permission`` de
Django. Para que esas llamadas funcionen, ``settings.KEYCLOAK_SERVER_URL`` debe
terminar en ``/`` si Keycloak corre bajo un path propio (por ejemplo
``--http-relative-path /auth``, como en producción): ``python-keycloak`` arma cada
endpoint con ``urllib.parse.urljoin(server_url, path)``, que **descarta** el
último tramo del path si ``server_url`` no termina en "/" (``urljoin('.../auth',
'admin/realms/x')`` da ``'.../admin/realms/x'``, perdiendo ``/auth``). En
desarrollo esto no se nota porque ``KEYCLOAK_SERVER_URL`` ahí no tiene ningún
tramo de path propio. ``apps.users.services._obtener_keycloak_admin`` ya
normaliza la URL para que esto no dependa de cómo se escriba la variable de
entorno, pero el valor configurado en ``.env`` conviene dejarlo con la barra
final igual, para que coincida con lo que el código termina usando realmente.

Flujo operativo de divisas
--------------------------

Las divisas activas se muestran en las tasas vigentes. Los roles autorizados
pueden registrar nuevas cotizaciones, que conservan el usuario y la fecha de
actualización.

Un cliente con un cliente activo seleccionado puede realizar tres tipos de
operación, en tres pasos:

#. **Calcular importe.** Solo previsualiza (no persiste nada): muestra tasa,
   comisión, monto final y hasta cuándo es válido ese cálculo.
#. **Confirmar importe.** Revalida que la cotización usada siga vigente y
   que no haya pasado el tiempo de reserva; si es así, recién ahí crea la
   transacción, siempre en estado "Pendiente de confirmación" y a nombre del
   cliente activo.
#. **Confirmar operación.** El cliente ve el resumen completo de la
   transacción pendiente y decide: si confirma y la tasa vigente no cambió
   desde el cálculo inicial, pasa a "Confirmada" y se registra la fecha y
   hora de confirmación (``confirmado_en``); si cancela manualmente, pasa a
   "Cancelada" y no se procesa más. Si la tasa vigente ya cambió, la
   confirmación se rechaza y pide recalcular.

Si el cliente nunca vuelve a la pantalla de confirmación (por ejemplo, cierra
la pestaña) la transacción no queda "Pendiente de confirmación" para siempre:
tiene un ``vence_en`` (``settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS``
después de crearse) y, pasado ese tiempo sin resolverse, pasa a "Vencida".
Este vencimiento es perezoso, como el resto del sistema (no hay tareas en
segundo plano): se persiste recién la próxima vez que alguien abre esa
transacción (``CalculoOperacion.marcar_vencida_si_corresponde`` /
``CalculoTriangulacion.marcar_vencida_si_corresponde``), y mientras tanto se
calcula al vuelo con ``estado_efectivo``, que es lo que usa el historial de
administración para mostrar el estado correcto aunque nadie haya vuelto a
tocar el registro. Una transacción "Vencida" ya no puede confirmarse ni
cancelarse: debe recalcularse desde cero.

Los dos tipos de operación:

* **Compra/venta contra PYG**: usa la tasa de venta (compra) o de compra
  (venta) de la divisa elegida. Se registra como un
  ``apps.divisas.models.CalculoOperacion``; el Paso 3 lo resuelve
  ``apps.divisas.views.ConfirmarTransaccionOperacionView``.
* **Cambio entre dos divisas extranjeras**: triangula por PYG, usando la
  tasa de compra de la divisa origen y la tasa de venta de la divisa
  destino, y expone la tasa cruzada implícita resultante. Se registra como
  un ``apps.divisas.models.CalculoTriangulacion`` con las tasas, el
  equivalente en guaraníes, la comisión y el importe a recibir en la divisa
  destino; el Paso 3 lo resuelve
  ``apps.divisas.views.ConfirmarTransaccionCambioView``.

Los administradores y analistas cambiarios consultan todas las transacciones
(compras, ventas y cambios, en cualquier estado) en el historial de
transacciones (``apps.divisas.views.HistorialTransaccionesView``), con tipo,
estado, usuario, cliente, divisa, monto, tasa aplicada, comisión e importe
final.

Un cliente, en cambio, consulta únicamente las transacciones registradas a
nombre de su propio cliente activo (``apps.divisas.views.MiHistorialTransaccionesView``,
en ``/divisas/transacciones/mias/``), con la misma información por fila
(tipo, divisa, monto, tasa aplicada, estado y fecha, además de comisión e
importe final) y paginado de a 20. Admite filtrar el listado por rango de
fechas de creación (``fecha_desde``/``fecha_hasta``) y por estado, comparando
siempre contra el estado *efectivo* de cada transacción (ver
``CalculoOperacion.estado_efectivo``), no solo el persistido; sin
transacciones que mostrar, indica un mensaje en vez de dejar la tabla vacía
sin explicación. Desde cada fila se accede al detalle completo de esa
transacción (``apps.divisas.views.DetalleTransaccionOperacionView`` para
compra/venta, ``apps.divisas.views.DetalleTransaccionCambioView`` para un
cambio entre divisas): a diferencia de las pantallas de confirmación
(``ConfirmarTransaccionOperacionView``/``ConfirmarTransaccionCambioView``),
el detalle del historial es de solo consulta y no ofrece ninguna acción para
confirmar, cancelar ni reprocesar la transacción, sin importar su estado.

El simulador de conversión ofrece los mismos tres modos (compra, venta,
cambio) sin persistir el resultado ni exigir confirmación.

Las pantallas de "Confirmar operación" (Paso 3), "Pagar" y el detalle de una
transacción propia dependen de que esta pertenezca al **cliente activo**
del momento. Si el cliente activo cambia (por ejemplo, en otra pestaña)
mientras una de esas pantallas quedó abierta con una transacción del
cliente *anterior*, ``apps.divisas.views._resolver_transaccion_propia``
distingue dos casos: si la transacción no tiene ninguna relación con el
usuario autenticado, sigue respondiendo 404 (acceso a una transacción
realmente ajena); si es de otro cliente propio del mismo usuario, en vez de
un error de Django informa con un mensaje ("Esta transacción no corresponde
al cliente activo...") y redirige, ya que no hay nada que ocultarle al
propio usuario sobre su otra transacción.

Pago de una transacción confirmada
-----------------------------------

Una vez que una transacción (compra/venta o cambio) está "Confirmada", el
cliente puede pagarla desde ``apps.divisas.views.PagarTransaccionOperacionView``
o ``PagarTransaccionCambioView``, eligiendo uno de sus métodos de pago ya
guardados (``apps.clientes.models.MetodoPago``, de la HU "Métodos de pago").
El monto a pagar es siempre el ``monto_final`` ya calculado por el sistema;
el cliente no puede modificarlo.

El registro del pago pasa siempre por ``apps.divisas.models.Pago.registrar_pago``,
pensado como punto de entrada único e idempotente:

* Asocia el pago a una única transacción (``calculo_operacion`` o
  ``calculo_triangulacion``, nunca ambas), con el medio de pago, el
  proveedor, un identificador externo, el monto y la fecha.
* Si la transacción no está "Confirmada" (está pendiente, vencida,
  cancelada o ya "Pagada"), rechaza el pago con
  ``apps.divisas.models.PagoRechazadoError`` en vez de crear nada.
* Si ya tiene un pago exitoso, rechaza cualquier otro intento —
  ``calculo_operacion``/``calculo_triangulacion`` son ``OneToOneField``, así
  que la base de datos lo garantiza sin importar el medio del segundo
  intento.
* Si llega más de una vez la misma confirmación (mismo ``proveedor`` e
  ``identificador_externo``, la clave de idempotencia, con una restricción
  ``UniqueConstraint`` en la base), devuelve el pago ya existente sin crear
  un segundo registro ni volver a tocar la transacción.
* Al registrarse un pago exitoso, la transacción pasa a "Pagada".

Esta HU ("Asociación de pagos a transacciones") es, a propósito, la base de
dos HU futuras que todavía no están implementadas: pago con tarjeta vía
Stripe y pago por transferencia vía SIPAP. Ambas se integrarán como
webhooks de su proveedor (con su propia verificación de firma, que no es
responsabilidad de ``Pago``) que arman los mismos datos genéricos
(medio, proveedor, identificador externo, monto) a partir de su propio
payload y llaman a ``registrar_pago``, en vez de duplicar esta lógica. El
flujo manual de esta HU usa ``Pago.PROVEEDOR_MANUAL`` como proveedor y el
``pk`` de la transacción como identificador externo, lo que de paso lo hace
naturalmente idempotente ante un doble clic en "Pagar".

Tanto el detalle de una compra/venta como el de un cambio entre divisas
(``DetalleTransaccionOperacionView``/``DetalleTransaccionCambioView``)
muestran el pago asociado (medio, monto, fecha e identificador) o,
si todavía no se registró ninguno, un mensaje indicándolo en vez de dejar
la sección vacía sin explicación.

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
#. **Confirmación de la operación (Paso 3).** En
   ``apps.divisas.views.ConfirmarTransaccionOperacionView`` el cliente revisa
   el resumen completo de esa transacción pendiente y la confirma (si la
   tasa vigente no cambió, pasa a "Confirmada" y se registra
   ``confirmado_en``) o la cancela manualmente (pasa a "Cancelada").

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

Tiempos de espera configurables
--------------------------------

Los dos tiempos de espera del flujo de operaciones (vigencia del cálculo, Paso 1→2, y vigencia de
la confirmación, Paso 2→3) son editables por un administrador en ``/divisas/configuracion/vigencia/``
(``apps.divisas.views.ConfiguracionVigenciaUpdateView``, exclusiva del rol ``admin`` — a diferencia
de la comisión, acá no participa ``analista_cambiario``). Se resuelven así:

#. Configuración guardada por el administrador (registro único, patrón singleton), si existe.
#. Valores por defecto del sistema (``settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS`` y
   ``settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS``), si todavía no se configuró nada.

Ver ``apps.divisas.models.ConfiguracionVigencia.vigencia_calculo_segundos`` y
``vigencia_confirmacion_segundos``.

Apertura de caja
-----------------

Un usuario con rol ``cajero`` abre su caja en ``/caja/abrir/``
(``apps.caja.views.AbrirCajaView``), registrando el saldo inicial de cada
divisa activa del sistema (incluido PYG, si existe como divisa activa):
``apps.caja.forms.AperturaCajaForm`` genera un campo por divisa en vez de
pedirle al cajero que elija cuáles va a manejar, así que un saldo en cero
simplemente significa que no maneja esa moneda en el turno. Al confirmar,
se crea una ``apps.caja.models.Caja`` en estado "Abierta" —asociada al
cajero y a la fecha y hora de apertura— junto con un
``apps.caja.models.SaldoInicialCaja`` por cada divisa.

Un cajero no puede tener dos cajas "Abierta" al mismo tiempo: además de la
validación en la vista, ``Caja.Meta.constraints`` agrega una restricción
única parcial en la base de datos (solo entre filas con
``estado='ABIERTA'``) para que ni una carrera entre dos pestañas pueda
crear una segunda. El panel del cajero (``/caja/``,
``apps.caja.views.PanelCajaView``) muestra la caja abierta con el saldo
inicial de cada moneda tal como se registró, o la invitación a abrir una si
todavía no tiene ninguna.

El cierre de caja, las operaciones de caja, el arqueo y los movimientos son
HU futuras que no existen todavía en este código; ``Caja.estado`` ya
contempla "Cerrada" para no tener que migrar el modelo de nuevo cuando se
implementen. El acceso a cualquier función de caja está restringido al rol
``cajero`` exclusivamente (sin excepción para administración ni análisis
cambiario, a diferencia de otras pantallas de este sistema).

Acceso a esta documentación desde el sistema
----------------------------------------------

Esta documentación (una vez compilada en ``docs/build/``) también se sirve dentro
de la propia aplicación en ``/docs/`` (``global_exchange.views.documentacion``),
con un enlace "Documentación" en el sidebar, dentro de la sección
"Administración". El acceso es exclusivo de administración (rol ``admin`` en
sesión, o ``is_staff``/``is_superuser``) para no exponer detalles internos de
implementación a clientes ni a roles operativos; cualquier otro usuario
autenticado recibe 403, y uno sin sesión es redirigido al login.

Cómo leer la referencia
-----------------------

La sección :doc:`reference/modules` enlaza la documentación generada con
``automodule``. Cada página se alimenta de los docstrings en español de los
módulos, clases y funciones, e incluye enlaces al código fuente cuando están
disponibles.
