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
el cliente no puede modificarlo. Hay un único botón "Pagar": si el método
elegido es de tipo "tarjeta" (``MetodoPago.TIPO_TARJETA``), la vista
redirige a cobrar con Stripe (ver `Pago con tarjeta vía Stripe`_ más abajo)
en vez de registrar el pago ahí mismo; para transferencia o billetera, el
registro sigue siendo inmediato, como se describe a continuación.

El registro del pago (para transferencia o billetera; el caso de tarjeta
se resuelve del lado de Stripe) pasa siempre por
``apps.divisas.models.Pago.registrar_pago``, pensado como punto de entrada
único e idempotente:

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

Esta HU ("Asociación de pagos a transacciones") se diseñó, a propósito,
como la base de HU futuras de pago real: pago con tarjeta vía Stripe (ya
implementado, ver `Pago con tarjeta vía Stripe`_ más abajo) y pago por
transferencia vía SIPAP (todavía no implementado). Ambas se integran como
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

Pago con tarjeta vía Stripe
---------------------------

Implementa la HU "Pago con tarjeta vía Stripe" (``apps.divisas.pagos_stripe``),
la primera de las dos HU futuras para las que GE-25 se diseñó como base (ver
sección anterior). Una tarjeta es, a todos los efectos de la UI, un
``apps.clientes.models.MetodoPago`` más (HU "Métodos de pago", GE-19): no
agrega ningún botón nuevo a la pantalla de pago de una transacción "Confirmada"
(``pagar_transaccion.html``/``pagar_transaccion_cambio.html``), el cliente
sigue viendo un único botón "Pagar", y es la propia vista
(``PagarTransaccionOperacionView``/``PagarTransaccionCambioView``) la que
decide qué hacer según el tipo del método de pago elegido. Si es de tipo
"tarjeta" (``MetodoPago.TIPO_TARJETA``), en vez de registrar el pago en el
momento redirige a cobrar con esa tarjeta puntual vía Stripe (pasando su
``pk`` como ``?metodo_pago=``); para transferencia o billetera sigue
registrando el pago manualmente, como ya hacía GE-25. El flujo de Stripe
tiene dos mitades independientes:

#. **Cobrar** (``IniciarPagoStripeOperacionView``/
   ``IniciarPagoStripeCambioView``, en ``apps.divisas.pagos_stripe``).
   Resuelve el ``MetodoPago`` elegido (``_resolver_metodo_pago_tarjeta``):
   tiene que ser del cliente, de tipo tarjeta y tener una
   ``referencia_externa`` de Stripe; si no, se pide elegir una tarjeta
   guardada válida, sin llamar a Stripe para nada. Con esa referencia y el
   ``Customer`` de Stripe del cliente (``_obtener_o_crear_cliente_stripe``,
   ver más abajo), cobra directo por API con un ``PaymentIntent``
   ``off_session=True, confirm=True`` — sin mostrar ninguna página de
   Stripe — por el monto exacto de ``transaccion.monto_final`` (criterio 1;
   nunca editable por el cliente), en PYG para una compra/venta o en la
   divisa de destino para un cambio (``_moneda_de_liquidacion``, convertida
   a la unidad que espera Stripe con ``_monto_en_unidad_minima_stripe``,
   sin centavos para PYG). Si el banco la rechaza
   (``stripe.error.CardError``, criterio 4) o exige una autenticación
   adicional (3-D Secure/SCA, ``status == "requires_action"``), cae a una
   sesión de `Stripe Checkout <https://stripe.com/docs/payments/checkout>`_
   (``customer=...``, para que esa misma tarjeta aparezca preseleccionada)
   para que el cliente confirme ahí. En cualquiera de los dos casos, si
   Stripe no responde o la conexión falla (``stripe.error.StripeError``),
   se informa el problema sin tocar la transacción (criterio 6); si el
   cliente abandona o cancela el pago en la página de Stripe, vuelve al
   detalle de la transacción con un aviso, también sin que nada se haya
   tocado (criterio 5).
#. **Confirmar el pago.** Para el cobro directo, la propia respuesta
   síncrona del ``PaymentIntent`` (``status == "succeeded"``) es la
   confirmación: no hace falta esperar ningún webhook. Para el camino de
   Checkout (solo cuando el cobro directo no alcanzó), confirma
   ``stripe_webhook_view`` (expuesta en ``/webhooks/stripe/`` fuera de
   cualquier namespace de la aplicación, porque la URL la configura una
   vez el dashboard de Stripe): valida la firma con
   ``stripe.Webhook.construct_event`` antes de mirar el contenido; si no
   es válida, la rechaza con un 400 sin tocar ninguna transacción
   (criterio 3). Si la firma es válida y el evento es
   ``checkout.session.completed`` con ``payment_status == "paid"``, llama
   a ``Pago.registrar_pago`` con el identificador de Stripe (el
   ``payment_intent``) y ``MetodoPago.TIPO_TARJETA`` (criterio 2).
   Cualquier otro evento, o una sesión todavía no cobrada, no modifica
   nada.

Tarjeta guardada: alta vía Stripe, cobro directo sin pasar por Stripe
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Una tarjeta se agrega desde el mismo listado de métodos de pago
(``clientes:metodo_pago_list``, botón "Agregar tarjeta"), pero **no** a
través del formulario manual de GE-19
(``apps.clientes.forms.MetodoPagoForm``, que desde esta HU dejó de ofrecer
"Tarjeta" como opción): el número de tarjeta nunca pasa por un campo de
Global Exchange ni se guarda en esta base. El alta tiene también dos
mitades:

#. **Iniciar** (``IniciarAgregarTarjetaStripeView``). Pide solo el nombre
   del titular (``apps.clientes.forms.AgregarTarjetaStripeForm``),
   precargado con ``Cliente.nombre_completo`` (solo el nombre, a
   diferencia de ``Cliente.__str__`` que agrega el identificador y el
   estado entre paréntesis — útil en un listado administrativo, pero no
   acá, de cara al propio cliente) y crea una sesión de Stripe Checkout en
   modo ``"setup"`` (guarda una tarjeta sin cobrar nada), asociada al
   ``Customer`` de Stripe del cliente, con el nombre del titular en los
   metadatos del ``SetupIntent`` para recuperarlo al confirmar.
#. **Confirmar** (``confirmar_tarjeta_stripe_view``, el ``success_url`` de
   la sesión anterior). Recupera la sesión y su ``SetupIntent``; si la
   sesión no corresponde al ``Customer`` de este cliente, responde 404 (no
   hay nada legítimo que hacer con una sesión ajena). Si el ``SetupIntent``
   llegó a ``"succeeded"``, consulta el ``PaymentMethod`` que generó
   (``stripe.PaymentMethod.retrieve``) y recién ahí crea el ``MetodoPago``:
   ``tipo_medio=TARJETA``, ``proveedor_externo=STRIPE``,
   ``referencia_externa`` (el id del ``PaymentMethod``), y, solo para
   mostrarlo en el listado, la marca (``entidad_financiera``) y los
   últimos 4 dígitos (``numero_tarjeta``) que devuelve Stripe — nunca el
   número completo, que Stripe jamás entrega. Confirmar la misma sesión
   dos veces (el cliente refresca la página de vuelta) no duplica el
   método: se detecta por ``referencia_externa`` ya existente.

``proveedor_externo``/``referencia_externa`` son campos genéricos de
``MetodoPago`` (no específicos de Stripe) a propósito: la idea es que una
futura integración con SIPAP pueda identificar del mismo modo una cuenta
bancaria real (``proveedor_externo=SIPAP``) sin guardar sus datos
completos acá, y que el mismo listado de métodos de pago termine
mostrando, con el tiempo, tanto tarjetas (Stripe) como cuentas bancarias
(SIPAP) de manera uniforme.

Ningún método de pago se edita: ``apps.clientes.views`` ya no tiene una
vista de edición, ``apps.clientes.forms.MetodoPagoForm`` solo se usa para
crear una transferencia o billetera, y ``metodo_pago_list.html`` ofrece
únicamente "Eliminar" junto a cada método. Para cambiar cualquier dato, el
flujo es eliminar el método y crear uno nuevo; para una tarjeta de Stripe,
eso además evita el problema de "editar" datos que en realidad viven del
lado de Stripe (marca, últimos 4 dígitos) y no tendría sentido escribir a
mano.

Al pagar, cobrar directo con el ``MetodoPago`` elegido usa una
``idempotency_key`` fija por transacción
(``f'ge22-pago-directo-{transaccion.pk}'``): si la vista se llama dos veces
para la misma transacción (doble clic, el cliente vuelve atrás y refresca),
Stripe devuelve el mismo ``PaymentIntent`` ya creado en vez de cobrar la
tarjeta una segunda vez — el mismo problema que la clave de idempotencia
``(proveedor, identificador_externo)`` de ``Pago.registrar_pago`` resuelve
para el resto de los medios de pago, pero un paso antes, porque acá la
vista misma es la que ejecuta el cobro (no solo lo registra).

La sesión de Checkout se crea **sin** pasar ``payment_method_types``: Stripe
retiró ese parámetro de ``checkout.Session.create`` (ahora los métodos de
pago aceptados se configuran desde el Dashboard de Stripe, no desde el
código) y volver a agregarlo rompe la creación de la sesión con un
``InvalidRequestError`` en cualquier cuenta nueva. Sin ninguna restricción,
Checkout ofrece cualquier medio habilitado en la cuenta — típicamente
también "Link" (el autocompletado propio de Stripe), mostrado de forma muy
prominente —, y si el cliente lo elige en vez de una tarjeta, el
``PaymentMethod`` resultante es de tipo ``"link"``, sin los datos de
tarjeta que esta HU necesita guardar. En su lugar, ambas sesiones de
Checkout (el alta de una tarjeta y el fallback de pago) se crean con
``payment_method_configuration=_configuracion_solo_tarjeta()``: una
``PaymentMethodConfiguration`` propia, creada (o reutilizada, cacheada en
el proceso) con tarjeta prendida y Link apagado, así Checkout nunca
ofrece otra cosa. Como defensa adicional, ``confirmar_tarjeta_stripe_view``
revisa que el ``PaymentMethod`` devuelto tenga de verdad el atributo
``card`` antes de leerlo, y si no, informa el problema sin crear nada en
vez de romper con un ``AttributeError``.

Los objetos que devuelve el SDK de Stripe (``StripeObject``: una sesión de
Checkout, un ``SetupIntent``, el evento de un webhook) **no** son dicts en
esta versión del SDK: no tienen ``.get()`` ni son iterables, aunque sí
soportan ``objeto['clave']`` y ``objeto.clave``. Por eso
``_procesar_sesion_completada`` y ``confirmar_tarjeta_stripe_view`` pasan
cualquier ``metadata``/sesión por ``_a_dict`` (que llama a
``.to_dict()``, recursivo) antes de usar ``.get()`` sobre ellos — omitir
ese paso tira ``AttributeError: 'get' is a dict method, but a StripeObject
is not a dict`` en cuanto se usa contra Stripe de verdad, algo que un mock
armado con un dict plano o un ``SimpleNamespace`` no detecta (los tests de
este módulo usan, a propósito, ``StripeObject`` reales para cubrir este
caso).

Ni la vista de inicio, ni el cobro directo, ni el webhook tocan
``transaccion.estado`` directamente: los tres construyen los mismos datos
genéricos (medio, proveedor "STRIPE", identificador externo, monto) y
llaman a ``Pago.registrar_pago``, igual que ya hace el flujo manual de
GE-25. Esto también resuelve la idempotencia ante un webhook reenviado por
Stripe (algo que Stripe hace activamente si no recibe un 200 a tiempo): la
segunda llamada con el mismo ``(proveedor, identificador_externo)`` devuelve
el pago ya existente sin duplicar nada.

``STRIPE_SECRET_KEY`` y ``STRIPE_WEBHOOK_SECRET`` (ver ``.env.example``) son
opcionales en desarrollo (``default=''``): sin una cuenta de Stripe
configurada, iniciar un pago con tarjeta simplemente falla con el mismo
mensaje de "no se pudo conectar con Stripe" que un corte de comunicación
real, sin impedir trabajar en el resto del sistema.

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
