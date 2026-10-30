"""Emisión de Facturas Electrónicas ante SIFEN, a través de la API de Factura Segura (ESI).

Implementa la HU "Integración con API de facturación electrónica":
apenas una compra, venta o cambio queda "Pagada" (criterio 1), Global
Exchange le emite al cliente una Factura Electrónica, con los mismos
montos y moneda que ya calcula ``apps.divisas.entrega`` para la entrega
real de dinero. Es un proceso **independiente** de esa entrega: llama
a este módulo exactamente desde los mismos 3 puntos que ya disparan
``apps.divisas.entrega.realizar_entrega`` (``apps.divisas.pagos_stripe``/
``apps.divisas.pagos_sipap``), pero una falla acá nunca bloquea ni
revierte el pago ya confirmado, y viceversa (criterio 3): se usa
siempre ``intentar_emitir_documento_electronico``, que no relanza nada
hacia quien la llama.

Autenticación: vía un ``Authentication-Token`` de larga duración
(``settings.FACTURASEGURA_AUTH_TOKEN``), obtenido una sola vez por un
administrador contra ``POST /login?include_auth_token`` y válido hasta
que se cambie la contraseña de esa cuenta — este módulo nunca lo
renueva ni hace login por su cuenta, solo lo envía como header.

Numeración (recurso real y finito, ver ``apps.divisas.models.
ContadorDocumentoElectronico``): el número de documento se reserva
**antes** de llamar a Factura Segura y nunca se libera ni reutiliza,
ni siquiera si la emisión después falla — un número "quemado" es
preferible a arriesgar un ``dNumDoc`` duplicado.

Reintentos (criterio 4): la propia documentación de Factura Segura
advierte textualmente que la petición es síncrona y que, ante un
timeout o una conexión interrumpida, "el resultado queda sin
confirmar, ya que el servidor pudo haber procesado la solicitud" y que
hay que verificarlo "mediante los mecanismos de consulta... o
solicitar asistencia a soporte" antes de reenviarla. Por eso este
módulo **nunca reintenta ``generar_de`` solo**, ni ante un timeout ni
ante un rechazo: ambos casos dejan el documento en
``DocumentoElectronico.ESTADO_ERROR_GENERACION``, visible para un
administrador, que debe primero confirmar con soporte si el documento
ya se generó del otro lado antes de pedir un reintento explícito (ver
``reintentar_emision``). Consultar el estado ante SIFEN
(``consultar_estado_sifen``) es, en cambio, una simple lectura
(``get_estado_sifen``): se puede repetir sin ningún riesgo.

Idempotencia (criterio 5): ``emitir_documento_electronico`` nunca crea
un segundo ``DocumentoElectronico`` para la misma transacción —
``DocumentoElectronico.calculo_operacion``/``calculo_triangulacion``
son ``OneToOneField``, así que la base de datos lo impide por
cualquier camino, no solo por el chequeo explícito al principio de la
función.

Armado del documento (``_armar_resumido_de``/``_calcular``): se
factura con dos ítems (``_grupos_item_resumido``) — el valor de la
operación cambiaria en sí, Exento de IVA (no hay IVA sobre el tipo de
cambio), y la comisión de Global Exchange como ítem separado, Gravado
al 10% de IVA (decisión confirmada con el usuario: la comisión es un
servicio propio, no parte del cambio de divisa exento) — y receptor
modelado siempre como "No Contribuyente"/consumidor final por cédula,
con **moneda de la factura siempre PYG** (``_total_en_pyg``) — Factura Segura solo admite
``cMoneOpe`` ``PYG`` o ``USD``, y la mayoría de las divisas de este
sistema no son ninguna de esas dos, así que facturar siempre en PYG
evita mezclar monedas según el tipo de transacción (decisión tomada
con el usuario). Los totales de la factura (IVA, descuentos, etc.)
**no se calculan a mano**: se arma solo el ``JSON_RESUMIDO_DE``
mínimo y se usa tal cual el ``DE`` completo que devuelve
``calcular_de`` como entrada de ``generar_de`` — así ninguna fórmula
propia puede quedar mal calculada, SIFEN/Factura Segura hace esa
cuenta. ``iTipTra``/``dDesTipTra`` (tipo de transacción, ver
``_tipo_transaccion``) ya está verificado contra la tabla real del
Manual Técnico SIFEN (``5``="Venta de divisas", ``6``="Compra de
divisas", específicos para una casa de cambio). Otros códigos de
clasificación que la guía solo describe como "ver Manual SIFEN"
(``iTipEmi``, ``iTImp``, ``iIndPres``) quedan con el valor más
plausible según la guía, no una verificación campo por campo contra el
Manual Técnico de SIFEN 150 completo: revisar antes de la primera
emisión real.
"""

import logging
from decimal import ROUND_HALF_UP

import requests
from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from apps.clientes.models import MetodoPago
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    ContadorDocumentoElectronico,
    DocumentoElectronico,
    RangoDocumentosAgotadoError,
)

logger = logging.getLogger(__name__)

# Estados de una transacción que ya pasó por un pago confirmado y, por
# lo tanto, debe tener (o estar esperando) su factura electrónica.
ESTADOS_FACTURABLES = (
    CalculoOperacion.ESTADO_PAGADA,
    CalculoOperacion.ESTADO_ENTREGA_FALLIDA,
    CalculoOperacion.ESTADO_ACREDITADA,
    CalculoOperacion.ESTADO_RETIRADA,
)


class FacturaSeguraRechazadaError(Exception):
    """Factura Segura respondió, pero rechazó la solicitud (``code`` negativo en el sobre de respuesta).

    A diferencia de un timeout o un error de conexión, acá sí hubo
    respuesta: es un rechazo claro de Factura Segura (datos inválidos,
    etc.), nunca una situación incierta.
    """


def _solicitar(operation, params):
    """Envía una operación al endpoint único de Factura Segura y devuelve su sobre de respuesta.

    Args:
        operation (str): Nombre de la operación (p. ej. ``'generar_de'``).
        params (dict): Parámetros propios de esa operación.

    Returns:
        dict: El cuerpo completo de la respuesta (``code``,
        ``description``, ``operation_info``, ``results``).

    Raises:
        requests.exceptions.RequestException: Sin respuesta confirmada
            (timeout, conexión cortada, error 5xx) — ver la advertencia
            de la propia documentación citada en el docstring del
            módulo: no se sabe si Factura Segura llegó a procesar la
            solicitud.
        FacturaSeguraRechazadaError: Hubo respuesta, pero con ``code``
            negativo: rechazo claro, no es una situación incierta.
    """
    respuesta = requests.post(
        settings.FACTURASEGURA_BASE_URL,
        json={'operation': operation, 'params': params},
        headers={'Authentication-Token': settings.FACTURASEGURA_AUTH_TOKEN},
        timeout=30,
    )
    respuesta.raise_for_status()
    cuerpo = respuesta.json()
    if cuerpo.get('code', -1) < 0:
        raise FacturaSeguraRechazadaError(cuerpo.get('description') or 'Factura Segura rechazó la solicitud.')
    return cuerpo


def _primer_resultado(cuerpo):
    """Primer elemento de ``results`` (el protocolo lo define como ARRAY, incluso cuando trae un solo registro).

    Devuelve ``{}`` si ``results`` vino vacío, para que el resto del
    código pueda seguir usando ``.get(...)`` con tranquilidad.
    """
    resultados = cuerpo.get('results') or []
    return resultados[0] if resultados else {}


def _total_en_pyg(transaccion):
    """Valor total de la operación, siempre en PYG y redondeado a entero (el Guaraní no tiene subunidad).

    Factura Segura solo admite ``cMoneOpe`` ``PYG`` o ``USD`` — ninguna
    otra divisa de este sistema (EUR, BRL, ARS, etc.) es facturable
    directamente, así que **toda** Factura Electrónica se emite en
    PYG, sin importar la moneda realmente entregada (decisión tomada
    con el usuario). Tanto en una compra como en una venta,
    ``monto_final`` ya está en PYG (ver ``apps.divisas.models.
    monto_a_pagar``/``monto_a_entregar``) y ya incluye el efecto de la
    comisión (sumada en una compra, restada en una venta). En un
    cambio entre divisas, ``monto_final`` está en la divisa de
    **destino** (Paso B de ``apps.divisas.views._calcular_triangulacion``)
    y también ya tiene la comisión restada: se convierte a PYG con
    ``tasa_venta_aplicada``, la misma tasa de ese Paso B. No se usa
    ``monto_equivalente_pyg`` (el bruto triangulado del Paso A, antes
    de la comisión): facturar ese valor ignoraba por completo el
    efecto de la comisión en un cambio, a diferencia de lo que ya
    hacía ``monto_final`` para una compra/venta (bug corregido).
    El redondeo a entero reutiliza el mismo criterio que
    ``apps.divisas.pagos_stripe`` ya usa para cobrar en PYG (moneda sin
    decimales, tanto en Stripe como en SIFEN).
    """
    if isinstance(transaccion, CalculoTriangulacion):
        monto = transaccion.monto_final * transaccion.tasa_venta_aplicada
    else:
        monto = transaccion.monto_final
    return monto.to_integral_value(rounding=ROUND_HALF_UP)


def _comision_en_pyg(transaccion):
    """Comisión de Global Exchange en la operación, siempre en PYG y redondeada a entero.

    En una compra o venta, ``comision`` ya está en PYG (todo
    ``apps.divisas.views._calcular_importe_operacion`` opera en PYG).
    En un cambio, ``comision`` se calculó en la divisa de **destino**
    (Paso B de ``_calcular_triangulacion``): se convierte a PYG con la
    misma tasa usada en ese paso (``tasa_venta_aplicada``), igual que
    ``_total_en_pyg``.
    """
    if isinstance(transaccion, CalculoTriangulacion):
        comision = transaccion.comision * transaccion.tasa_venta_aplicada
    else:
        comision = transaccion.comision
    return comision.to_integral_value(rounding=ROUND_HALF_UP)


def _grupo_item(codigo, descripcion, monto, *, afecta_iva):
    """Un ítem del ``JSON_RESUMIDO_DE`` (entrada de ``calcular_de``): sin ningún campo calculado.

    ``cUniMed='77'`` es, de las opciones que documenta la guía, la
    única plausible para un ítem de este tipo de operación. Sin
    descuentos ni anticipos (no aplican a esta operación). Los totales
    derivados (``dTotBruOpeItem``, ``dTotOpeItem``, ``dBasGravIVA``,
    etc.) no se calculan a mano: los completa ``calcular_de`` (ver
    ``_calcular``). Si el ítem está gravado, ``monto`` ya es el precio
    final con IVA incluido (así factura SIFEN: ``calcular_de`` extrae
    cuánto de ese precio es base y cuánto es IVA, no hay que sumarle
    nada encima).
    """
    if afecta_iva:
        iva = {'iAfecIVA': '1', 'dPropIVA': '100', 'dTasaIVA': '10'}
    else:
        iva = {'iAfecIVA': '3', 'dPropIVA': '0', 'dTasaIVA': '0'}
    return {
        'dCodInt': codigo,
        'dDesProSer': descripcion,
        'cUniMed': '77',
        'dCantProSer': '1',
        'dPUniProSer': str(monto),
        'dDescItem': '0',
        'dDescGloItem': '0',
        'dAntPreUniIt': '0',
        'dAntGloPreUniIt': '0',
        **iva,
    }


def _grupos_item_resumido(transaccion, total):
    """Ítems del ``JSON_RESUMIDO_DE``: separa la comisión (gravada al 10% IVA) del resto de la operación (exento).

    Confirmado con el usuario: la comisión de Global Exchange es un
    servicio propio, gravado al 10% de IVA, no parte del cambio de
    divisa en sí (que sigue exento, no hay IVA sobre el tipo de
    cambio). El ítem exento es siempre ``total - comisión``
    (``_total_en_pyg``/``_comision_en_pyg``), nunca el bruto de la
    operación calculado aparte, para que los dos ítems sumen
    exactamente el total ya correcto, sin descuadres de redondeo. Si
    la comisión del cliente es 0% (``ConfiguracionComision``), queda
    un único ítem exento, igual que antes de este cambio.
    """
    comision = _comision_en_pyg(transaccion)
    base = total - comision
    items = []
    if base > 0:
        items.append(_grupo_item('CAMBIO-DIVISA', _descripcion_operacion(transaccion), base, afecta_iva=False))
    if comision > 0:
        items.append(_grupo_item('COMISION', 'Comisión por el servicio de cambio de divisas', comision, afecta_iva=True))
    return items


def _tipo_transaccion(transaccion):
    """Código y descripción de ``iTipTra``/``dDesTipTra`` (Manual Técnico SIFEN, campo D011).

    Confirmado con la tabla real de códigos (compartida por el usuario):
    ``5``="Venta de divisas" y ``6``="Compra de divisas" son los códigos
    propios de una casa de cambio — no ``1`` ("Venta de mercadería"), el
    valor que se usaba antes sin verificar (bug corregido). Una compra
    (Global Exchange le compra la divisa al cliente) es código ``6``;
    una venta (Global Exchange le vende la divisa al cliente) es código
    ``5``. Un cambio entre divisas combina ambas piernas en una sola
    operación (Global Exchange recibe la divisa origen y entrega la
    divisa destino) y no tiene un código propio en la tabla: decisión
    tomada con el usuario, se factura siempre como "Venta de divisas",
    consistente con lo que Global Exchange finalmente le entrega al
    cliente (la divisa de destino), igual criterio que ya usa
    ``_descripcion_operacion`` ("Cambio de X a Y").

    ``dDesTipTra`` es obligatorio siempre que se envíe ``iTipTra``: no
    alcanza con mandar el código solo, hay que mandar también su texto.
    """
    if isinstance(transaccion, CalculoTriangulacion):
        return '5', 'Venta de divisas'
    if transaccion.tipo == CalculoOperacion.TIPO_COMPRA:
        return '6', 'Compra de divisas'
    return '5', 'Venta de divisas'


def _descripcion_operacion(transaccion):
    """Descripción legible del ítem, distinta para una compra/venta o un cambio entre divisas."""
    if isinstance(transaccion, CalculoTriangulacion):
        return f'Cambio de {transaccion.codigo_divisa_origen} a {transaccion.codigo_divisa_destino}'
    return f'{transaccion.get_tipo_display()} de {transaccion.codigo_divisa}'


def _email_receptor(cliente):
    """Devuelve el email real del cliente para ``dEmailRec``: el de un usuario real, no el legado.

    ``Cliente.email`` es un campo legado (ver el comentario en
    ``ClienteForm``: "el correo operativo pertenece al usuario"), que no
    se completa en ningún alta real — el email verdadero y verificado es
    el de Keycloak. En la práctica, muchos clientes no tienen
    ``Cliente.user`` (el ``OneToOneField`` "titular") asignado en
    absoluto: el vínculo real con sus usuarios es siempre
    ``Cliente.usuarios`` (el ``ManyToManyField`` que también usa
    ``test_func`` en las vistas propias del cliente, vía
    ``request.user.clientes``). Se prueba primero el titular si está,
    después cualquier usuario asociado que tenga un email cargado, y
    el campo legado solo como último respaldo.
    """
    if cliente.user and cliente.user.email:
        return cliente.user.email
    usuario_con_email = cliente.usuarios.exclude(email='').first()
    if usuario_con_email:
        return usuario_con_email.email
    return cliente.email or ''


def _info_adicional(transaccion):
    """Texto para ``dInfAdic``: deja constancia de la tasa aplicada, impresa en el KuDE.

    El esquema de Factura Segura no tiene ningún campo estructurado
    para "la tasa de cambio que usó Global Exchange en esta
    operación" (``dTiCam`` es la tasa de la propia factura cuando
    ``cMoneOpe`` no es PYG, que en este módulo siempre es PYG, ver
    ``_total_en_pyg``): ``dInfAdic`` es, según la guía, el único lugar
    pensado para texto libre impreso en el comprobante sin formar parte
    del XML firmado, así que es donde se deja la tasa para que el
    criterio de "información completa de la operación" (cliente,
    monto, divisa, tasa, fecha) quede satisfecho también en ese dato.
    """
    if isinstance(transaccion, CalculoTriangulacion):
        return (
            f'Tasa aplicada: {transaccion.tasa_cruzada} '
            f'({transaccion.codigo_divisa_origen}/{transaccion.codigo_divisa_destino})'
        )
    return f'Tasa aplicada: {transaccion.tasa_aplicada} ({transaccion.codigo_divisa}/PYG)'


def _grupo_pago(transaccion, monto):
    """Mapea el medio de pago real (``Pago.medio_pago``) al tipo de pago que espera la API.

    Un único pago por el total de la operación, ya en PYG (ver
    ``_total_en_pyg``): esta HU no reparte el cobro en más de un medio.
    """
    base = {'dMonTiPag': str(monto), 'cMoneTiPag': 'PYG', 'dTiCamTiPag': '1'}
    if transaccion.pago.medio_pago == MetodoPago.TIPO_TARJETA:
        return {**base, 'iTiPago': '3', 'iDenTarj': '1', 'iForProPa': '1'}
    return {**base, 'iTiPago': '5'}


def _armar_resumido_de(documento, transaccion, monto):
    """Arma el ``JSON_RESUMIDO_DE``: la entrada de ``calcular_de``, sin ningún campo calculado.

    Se factura siempre en PYG (``cMoneOpe='PYG'``, ver
    ``_total_en_pyg``) y con dos ítems (``_grupos_item_resumido``): el
    cambio de divisa en sí, exento de IVA (no hay IVA sobre el tipo de
    cambio), y la comisión de Global Exchange, gravada al 10%.
    Receptor modelado siempre como "No Contribuyente"/consumidor final
    por cédula (``iNatRec='2'``), lo que a su vez implica
    ``iTiOpe='2'`` (B2C): un "No Contribuyente" nunca es la contraparte
    de una operación B2B.

    Nota: varios códigos de clasificación documentados solo como
    "ver Manual SIFEN" (``iTipEmi``, ``iTImp``, ``iIndPres``) quedan
    con el valor más plausible según la guía de Factura Segura, no una
    verificación campo por campo contra el Manual Técnico de SIFEN 150
    completo — revisar antes de la primera emisión real. ``iTipTra``/
    ``dDesTipTra`` (ver ``_tipo_transaccion``) sí están verificados
    contra la tabla real del manual.
    """
    cliente = transaccion.cliente
    ahora = timezone.localtime(timezone.now())
    tipo_transaccion, descripcion_tipo_transaccion = _tipo_transaccion(transaccion)
    return {
        'iTipEmi': '1',
        'iTiDE': documento.tipo_documento,
        'dNumTim': settings.FACTURASEGURA_EMISOR_NUM_TIMBRADO,
        'dFeIniT': settings.FACTURASEGURA_EMISOR_FECHA_INICIO_TIMBRADO,
        'dEst': settings.FACTURASEGURA_ESTABLECIMIENTO,
        'dPunExp': settings.FACTURASEGURA_PUNTO_EXPEDICION,
        'dNumDoc': documento.numero_documento,
        'dFeEmiDE': ahora.strftime('%Y-%m-%dT%H:%M:%S'),
        'iTipTra': tipo_transaccion,
        'dDesTipTra': descripcion_tipo_transaccion,
        'iTImp': '1',
        'cMoneOpe': 'PYG',
        'dRucEm': settings.FACTURASEGURA_EMISOR_RUC,
        'dDVEmi': settings.FACTURASEGURA_EMISOR_DV,
        'iTipCont': settings.FACTURASEGURA_EMISOR_TIPO_CONTRIBUYENTE,
        'dNomEmi': settings.FACTURASEGURA_EMISOR_NOMBRE,
        'dDirEmi': settings.FACTURASEGURA_EMISOR_DIRECCION,
        'dNumCas': settings.FACTURASEGURA_EMISOR_NUMERO_CASA,
        'cDepEmi': settings.FACTURASEGURA_EMISOR_COD_DEPARTAMENTO,
        'dDesDepEmi': settings.FACTURASEGURA_EMISOR_DESC_DEPARTAMENTO,
        'cCiuEmi': settings.FACTURASEGURA_EMISOR_COD_CIUDAD,
        'dDesCiuEmi': settings.FACTURASEGURA_EMISOR_DESC_CIUDAD,
        'dTelEmi': settings.FACTURASEGURA_EMISOR_TELEFONO,
        'dEmailE': settings.FACTURASEGURA_EMISOR_EMAIL,
        'gActEco': settings.FACTURASEGURA_EMISOR_ACTIVIDADES_ECONOMICAS,
        'iNatRec': '2',
        'iTiOpe': '2',
        'cPaisRec': 'PRY',
        'iTipIDRec': '1',
        'dNumIDRec': cliente.identificador,
        'dNomRec': cliente.nombre_completo,
        'dEmailRec': _email_receptor(cliente),
        'iIndPres': '1',
        'iCondOpe': '1',
        'gPaConEIni': [_grupo_pago(transaccion, monto)],
        'iCondCred': '1',
        'dPlazoCre': '0',
        'gCamItem': _grupos_item_resumido(transaccion, monto),
        'CDC': '0',
        'dCodSeg': '0',
        'dDVId': '0',
        'dSisFact': '1',
        'dInfAdic': _info_adicional(transaccion),
    }


def _calcular(documento, transaccion, monto):
    """Llama a ``calcular_de`` y devuelve el ``DE`` completo, con los totales ya calculados por SIFEN.

    Nunca confía en fórmulas propias para los totales de una factura:
    arma solo el ``JSON_RESUMIDO_DE`` (``_armar_resumido_de``, sin
    ningún campo derivado) y usa tal cual el ``DE`` que devuelve
    ``calcular_de`` como entrada de ``generar_de`` — es, según la
    guía, "el JSON completo con los campos calculados según SIFEN...
    ya listo para ser enviado en la operación generar_de". A
    diferencia de ``generar_de``, esta operación **no genera ningún
    documento real** (no consume ningún recurso de numeración): es
    seguro reintentarla cuantas veces haga falta.

    Raises:
        requests.exceptions.RequestException, FacturaSeguraRechazadaError:
            Mismo criterio que ``_solicitar``.
    """
    cuerpo = _solicitar('calcular_de', {'DE': _armar_resumido_de(documento, transaccion, monto)})
    return _primer_resultado(cuerpo).get('DE') or {}


def _generar(documento, transaccion):
    """Llama a ``calcular_de`` + ``generar_de`` para ``documento`` y actualiza su estado según el resultado.

    Nunca relanza: cualquier falla (comunicación incierta o rechazo
    claro, en cualquiera de las dos llamadas) queda registrada en
    ``documento.estado``/``error_generacion``, nunca como una
    excepción hacia quien llama a esta función interna. Una falla en
    ``calcular_de`` es indistinguible, para quien llama, de una falla
    en ``generar_de``: en ambos casos no se generó nada del otro lado,
    y el número ya reservado queda igual de "quemado" por diseño (ver
    el docstring del módulo).

    Antes de llamar a la API, valida que el cliente tenga un email
    cargado (``_email_receptor``): ``dEmailRec`` es obligatorio para
    Factura Segura (lo confirmó un rechazo real, ``code=-10009``,
    durante las pruebas de esta HU). Si falta, no se llama a la API en
    absoluto: es un dato que nunca va a cambiar solo reintentando
    contra el mismo número.
    """
    limite = DocumentoElectronico._meta.get_field('error_generacion').max_length
    if not _email_receptor(transaccion.cliente):
        documento.error_generacion = (
            'El cliente no tiene un email cargado (ni en su usuario de Keycloak ni en el '
            'campo legado). dEmailRec es obligatorio para Factura Segura: cargar el email '
            'del cliente y reintentar.'
        )[:limite]
        documento.estado = DocumentoElectronico.ESTADO_ERROR_GENERACION
        documento.save(update_fields=['estado', 'error_generacion', 'actualizado_en'])
        return

    monto = _total_en_pyg(transaccion)
    try:
        de_completo = _calcular(documento, transaccion, monto)
        cuerpo = _solicitar('generar_de', {'DE': de_completo})
    except requests.exceptions.RequestException as exc:
        # str(exc) de una excepción de red puede ser arbitrariamente largo
        # (urllib3 anida toda la cadena de reintentos/causas en su repr):
        # se recorta siempre al límite del campo, para que un mensaje de
        # error nunca pueda romper el propio guardado del error.
        mensaje = (
            f'Sin confirmación de Factura Segura (timeout o error de conexión): {exc}. '
            'No reintentar sin antes verificar con soporte si el documento ya se generó.'
        )
        documento.error_generacion = mensaje[:limite]
        documento.estado = DocumentoElectronico.ESTADO_ERROR_GENERACION
        documento.save(update_fields=['estado', 'error_generacion', 'actualizado_en'])
        return
    except FacturaSeguraRechazadaError as exc:
        documento.error_generacion = str(exc)[:limite]
        documento.estado = DocumentoElectronico.ESTADO_ERROR_GENERACION
        documento.save(update_fields=['estado', 'error_generacion', 'actualizado_en'])
        return

    resultados = _primer_resultado(cuerpo)
    documento.cdc = resultados.get('CDC', '')
    documento.operation_id = str(cuerpo.get('operation_info', {}).get('id', ''))
    documento.estado = DocumentoElectronico.ESTADO_GENERADO
    documento.error_generacion = ''
    # Criterio 4: la fecha y hora de emisión se registra solo cuando la
    # factura se generó correctamente (hay CDC), nunca en una falla.
    documento.emitida_en = timezone.now()
    documento.save(update_fields=['estado', 'cdc', 'operation_id', 'error_generacion', 'emitida_en', 'actualizado_en'])


def factura_pendiente_de_generacion(transaccion):
    """Indica si a una transacción ya pagada todavía le falta su factura electrónica (criterio 3).

    Es ``True`` cuando la transacción ya fue pagada y, o bien no tiene
    ningún ``DocumentoElectronico`` (p. ej. se agotó el rango de
    numeración), o bien el que tiene está rechazado/fallido
    (``DocumentoElectronico.factura_pendiente``). Las pantallas de
    detalle lo usan para informarle al cliente que la factura está
    "pendiente de generación" **sin ocultar ni bloquear** el resto de los
    datos de la operación.

    Args:
        transaccion: Una ``CalculoOperacion`` o ``CalculoTriangulacion``.

    Returns:
        bool: ``False`` si la transacción aún no fue pagada (todavía no
        corresponde facturar) o si su factura se generó correctamente.
    """
    if transaccion.estado not in ESTADOS_FACTURABLES:
        return False
    documento = getattr(transaccion, 'documento_electronico', None)
    return documento is None or documento.factura_pendiente


def emitir_documento_electronico(transaccion):
    """Emite (o recupera, si ya existe) la Factura Electrónica de una transacción ya pagada.

    Punto de entrada principal, llamado por
    ``intentar_emitir_documento_electronico`` desde los mismos 3 sitios
    que disparan ``apps.divisas.entrega.realizar_entrega``. Idempotente
    (criterio 5): si la transacción ya tiene un ``DocumentoElectronico``
    (exitoso o no), lo devuelve sin volver a llamar a Factura Segura.

    Args:
        transaccion: Una ``CalculoOperacion`` o ``CalculoTriangulacion``
            recién marcada "Pagada".

    Returns:
        DocumentoElectronico | None: El documento (nuevo o ya
        existente). ``None`` únicamente si no quedaban números
        disponibles en el rango habilitado (``RangoDocumentosAgotadoError``,
        que queda logueada: requiere pedir un rango nuevo a Factura
        Segura antes de poder emitir cualquier otra factura de este
        tipo).
    """
    documento_existente = getattr(transaccion, 'documento_electronico', None)
    if documento_existente is not None:
        return documento_existente

    campo = 'calculo_operacion' if isinstance(transaccion, CalculoOperacion) else 'calculo_triangulacion'
    try:
        numero_documento = ContadorDocumentoElectronico.siguiente_numero(ContadorDocumentoElectronico.TIPO_FACTURA)
    except RangoDocumentosAgotadoError:
        logger.error(
            'No se pudo emitir la Factura Electrónica de %s #%s: se agotó el rango de numeración.',
            campo, transaccion.pk,
        )
        return None

    try:
        documento = DocumentoElectronico.objects.create(
            **{campo: transaccion},
            tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento=numero_documento,
        )
    except IntegrityError:
        # Carrera entre dos llamadas simultáneas para la misma transacción
        # (p. ej. un webhook y un cobro directo compitiendo): la otra ya
        # ganó y creó el documento, se devuelve esa en vez de una segunda.
        # El número recién reservado queda sin usar (no hay forma de
        # "devolverlo" al contador sin arriesgar que otra emisión lo tome
        # mientras tanto), aceptable frente al riesgo de un dNumDoc repetido.
        return DocumentoElectronico.objects.filter(**{campo: transaccion}).first()

    _generar(documento, transaccion)
    return documento


def intentar_emitir_documento_electronico(transaccion):
    """Wrapper seguro de ``emitir_documento_electronico`` para los puntos de pago.

    Nunca deja escapar ninguna excepción: un fallo al emitir la
    factura no debe poder interrumpir ni revertir un pago ya
    confirmado (criterio 3). Cualquier error no previsto queda
    logueado para que un administrador lo investigue.
    """
    try:
        return emitir_documento_electronico(transaccion)
    except Exception:
        logger.exception(
            'Fallo inesperado al emitir la Factura Electrónica de la transacción #%s.', transaccion.pk,
        )
        return None


def consultar_estado_sifen(documento):
    """Consulta a SIFEN (vía ``get_estado_sifen``) el estado real de un documento ya generado.

    Es una simple lectura: se puede llamar tantas veces como se
    quiera, incluso si la anterior falló por comunicación. No modifica
    nada si la consulta en sí no se pudo completar (queda igual que
    estaba, para volver a consultarse más tarde).

    Args:
        documento (DocumentoElectronico): Debe tener ``cdc`` (solo
            tiene sentido consultar un documento que llegó a generarse).

    Returns:
        bool: ``True`` si se pudo actualizar el estado (sin importar
        cuál quedó), ``False`` si la consulta en sí falló.
    """
    if not documento.cdc:
        return False
    try:
        cuerpo = _solicitar(
            'get_estado_sifen',
            {'dRucEm': settings.FACTURASEGURA_EMISOR_RUC, 'CDC': documento.cdc},
        )
    except (requests.exceptions.RequestException, FacturaSeguraRechazadaError):
        logger.warning('No se pudo consultar el estado SIFEN del documento #%s.', documento.pk)
        return False

    resultados = _primer_resultado(cuerpo)
    estado_sifen = (resultados.get('estado_sifen') or '').upper()
    documento.estado_sifen = estado_sifen
    documento.desc_sifen = resultados.get('desc_sifen', '')
    documento.consultado_en = timezone.now()

    # Valores de "estado_sifen" documentados por Factura Segura y su
    # interpretación oficial. No se miran "estado_can"/"estado_inu" (que
    # tendrían prioridad sobre "estado_sifen" según el manual): esta HU
    # no implementa sol_cancelacion/sol_inutilizacion, así que esos dos
    # campos siempre vienen vacíos para un documento emitido por este
    # módulo.
    if estado_sifen == 'APROBADO':
        documento.estado = DocumentoElectronico.ESTADO_APROBADO
    elif estado_sifen == 'APROBADO CON OBSERVACIÓN':
        documento.estado = DocumentoElectronico.ESTADO_APROBADO_OBS
    elif estado_sifen == 'RECHAZADO':
        documento.estado = DocumentoElectronico.ESTADO_RECHAZADO
        documento.error_sifen = resultados.get('error_sifen', '')
    elif estado_sifen == 'REINGRESADO':
        # El documento fue reingresado a Factura Segura con otro CDC: el
        # CDC actual ya no es válido. No hay, en esta misma consulta,
        # ningún CDC nuevo a seguir, así que queda para revisión manual.
        documento.estado = DocumentoElectronico.ESTADO_ERROR_SIFEN
        documento.error_sifen = 'Reingresado: este CDC ya no es válido, el documento fue reingresado con otro CDC.'
    elif estado_sifen in ('SOL.APROBACION', 'ENVIADO_A_SIFEN', ''):
        pass  # Todavía no hay una respuesta definitiva de SIFEN: se vuelve a consultar más tarde.
    elif estado_sifen in ('ERROR_SIFEN', 'ERROR_ENVIO_LOTE', 'REINTENTAR_LOTE', 'ERROR_CONSULTA_LOTE'):
        documento.estado = DocumentoElectronico.ESTADO_ERROR_SIFEN
        documento.error_sifen = resultados.get('error_sifen', '')
    else:
        # Valor no documentado: se deja visible como error en vez de
        # quedar silenciosamente sin cambios.
        documento.estado = DocumentoElectronico.ESTADO_ERROR_SIFEN
        documento.error_sifen = resultados.get('error_sifen') or f'Estado SIFEN no reconocido: {estado_sifen!r}'

    # Se recorta siempre al límite de cada campo, por si el texto que
    # devuelve Factura Segura (o uno armado acá) lo excediera.
    documento.desc_sifen = documento.desc_sifen[:DocumentoElectronico._meta.get_field('desc_sifen').max_length]
    documento.error_sifen = documento.error_sifen[:DocumentoElectronico._meta.get_field('error_sifen').max_length]
    documento.save(update_fields=['estado', 'estado_sifen', 'desc_sifen', 'error_sifen', 'consultado_en', 'actualizado_en'])
    return True


def reintentar_emision(documento):
    """Reintenta, a pedido explícito de un administrador, un documento en 'Error al generar'.

    Reutiliza el mismo ``numero_documento`` ya reservado (nunca pide
    uno nuevo): si la emisión anterior nunca llegó a crearse del otro
    lado, es seguro reenviarla con ese número. **Antes de llamar a
    esta función**, un administrador debe haber confirmado con soporte
    de Factura Segura que el documento no se generó ya con ese mismo
    número — exactamente la verificación que la propia documentación
    de la API exige antes de reenviar una solicitud incierta (ver el
    docstring del módulo). Esta función no hace esa verificación por
    sí sola, porque no hay ningún mecanismo de consulta por número de
    documento documentado, solo por CDC (que no existe todavía si la
    emisión original nunca llegó a confirmarse).

    Args:
        documento (DocumentoElectronico): Debe estar en
            ``ESTADO_ERROR_GENERACION``.

    Returns:
        bool: ``True`` si quedó generado, ``False`` si no estaba en
        condiciones de reintentarse o si volvió a fallar.
    """
    if documento.estado != DocumentoElectronico.ESTADO_ERROR_GENERACION:
        return False
    _generar(documento, documento.transaccion)
    return documento.estado == DocumentoElectronico.ESTADO_GENERADO


def _descargar_archivo(operation, documento, es_valido):
    """GET genérico para ``dwn_kude``/``dwn_xml``: devuelve el archivo binario, o ``None`` si falla.

    A diferencia de ``_solicitar`` (que envuelve todo en el sobre
    ``code``/``description``/``results``), estas dos operaciones son
    ``GET`` y, según la guía, devuelven el archivo directo en el
    cuerpo de la respuesta (``--output cdc.pdf``/``--output cdc.xml``
    en los ejemplos con ``curl``), no un JSON. Bajo demanda, sin
    guardar nada en el servidor: se vuelve a pedir cada vez que se
    descarga. El contenido se devuelve tal cual llegó, byte por byte:
    nunca se regenera ni se modifica (GE-86, criterio 3).

    Args:
        operation (str): ``'dwn_kude'`` o ``'dwn_xml'``.
        documento (DocumentoElectronico): Documento a descargar.
        es_valido (Callable[[bytes], bool]): Comprueba que lo recibido
            sea realmente el archivo esperado, y no, p. ej., un mensaje
            de error enviado con estado HTTP 200.

    Returns:
        bytes | None: El archivo, o ``None`` si no tiene CDC, la
        descarga falló o el contenido no pasó la validación.
    """
    if not documento.cdc:
        return None
    url = f'{settings.FACTURASEGURA_BASE_URL}/{operation}/{settings.FACTURASEGURA_EMISOR_RUC}/{documento.cdc}'
    try:
        respuesta = requests.get(
            url, headers={'Authentication-Token': settings.FACTURASEGURA_AUTH_TOKEN}, timeout=30,
        )
        respuesta.raise_for_status()
    except requests.exceptions.RequestException:
        logger.warning('No se pudo descargar %s para el documento #%s.', operation, documento.pk)
        return None
    if not es_valido(respuesta.content):
        logger.error('Factura Segura devolvió un archivo inválido en %s para el documento #%s.', operation, documento.pk)
        return None
    return respuesta.content


def descargar_kude(documento):
    """Descarga el KuDE (PDF) de ``documento`` desde Factura Segura, o ``None`` si falla o no tiene CDC.

    Solo comprueba que lo recibido sea un PDF: el texto de un PDF suele
    estar comprimido, así que su CDC no se puede verificar con una
    búsqueda directa, como sí se hace en ``descargar_xml``. El archivo
    se pide a Factura Segura por ese mismo CDC.
    """
    return _descargar_archivo('dwn_kude', documento, lambda contenido: contenido.startswith(b'%PDF'))


def descargar_xml(documento):
    """Descarga el XML firmado de ``documento``, o ``None`` si falla, no tiene CDC o el XML trae otro CDC."""
    return _descargar_archivo('dwn_xml', documento, lambda contenido: documento.cdc.encode() in contenido)
