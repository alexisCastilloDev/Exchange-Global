"""Pruebas de la emisión de Facturas Electrónicas ante SIFEN (``apps.divisas.factura_electronica``).

Cubre la HU "Integración con API de facturación electrónica": emisión
exitosa con almacenamiento del CDC (criterios 1 y 2), un rechazo claro
de Factura Segura y una falla de comunicación incierta, ambas sin
reintento automático (criterios 3 y 4), la idempotencia contra una
segunda emisión para la misma transacción ya facturada (criterio 5), y
el agotamiento del rango de numeración.

**Ninguna de estas pruebas llama a la API real de Factura Segura**: la
única función que le habla por HTTP (``_solicitar``, que usa
``requests.post``) está siempre mockeada — una emisión exitosa hace
dos llamadas (``calcular_de`` seguido de ``generar_de``, ver
``_generar``), así que los tests que ejercitan el camino feliz
mockean ambas respuestas en orden. El rango de numeración real
de Facturas Electrónicas es un recurso escaso y finito (ver la
migración de datos ``0028_seed_contador_documento_electronico``), así
que estas pruebas usan siempre un ``ContadorDocumentoElectronico``
propio, con un rango chico separado del real (p. ej. ``900``-``901``),
nunca el rango sembrado para TEST.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction as db_transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente, MetodoPago
from apps.divisas.factura_electronica import (
    _comision_en_pyg,
    _grupos_item_resumido,
    _tipo_transaccion,
    _total_en_pyg,
    consultar_estado_sifen,
    descargar_kude,
    descargar_xml,
    emitir_documento_electronico,
    factura_pendiente_de_generacion,
    intentar_emitir_documento_electronico,
    reintentar_emision,
)
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    ContadorDocumentoElectronico,
    Divisa,
    DocumentoElectronico,
    Pago,
)

User = get_user_model()


def _respuesta(code=0, results=None, description='', operation_id='OP-1'):
    """Arma una respuesta de Factura Segura falsa, con el sobre ``code``/``description``/``results``.

    ``results`` se recibe como un único dict (por comodidad al llamar
    desde los tests) pero se envía dentro de una lista, tal como lo
    exige el protocolo real documentado por Factura Segura.
    """
    respuesta = Mock(status_code=200)
    respuesta.raise_for_status.side_effect = None
    respuesta.json.return_value = {
        'code': code,
        'description': description,
        'operation_info': {'id': operation_id},
        'results': [results] if results else [],
    }
    return respuesta


def _respuesta_calculo(de=None):
    """Respuesta falsa de ``calcular_de``: envuelve el ``DE`` ya calculado en ``results``."""
    return _respuesta(code=0, results={'DE': de or {}})


class FacturaElectronicaTestCase(TestCase):
    """Base común: un cliente, una compra 'Pagada' con su ``Pago``, y un contador de prueba chico."""

    def setUp(self):
        """Prepara una compra pagada con tarjeta, lista para facturar, y un rango de numeración de prueba."""
        # La migración de datos 0028 ya siembra una fila para este tipo de
        # documento con el rango real de TEST: se reemplaza por un rango de
        # prueba chico y separado (900-901), nunca se usa el real acá.
        self.contador, _ = ContadorDocumentoElectronico.objects.update_or_create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            defaults={'desde': 900, 'hasta': 901, 'ultimo_asignado': None},
        )
        usuario = User.objects.create_user(username='cliente-fe', password='password123')
        self.cliente = Cliente.objects.create(
            user=usuario, identificador='4111222', nombre='Cliente', apellido='Factura',
            email='cliente-fe@test.com', is_active=True,
        )
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.medio_destino = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Cliente Factura',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000000777', documento_titular='4111222',
            moneda=self.usd,
        )
        self.transaccion = CalculoOperacion.objects.create(
            usuario=usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_PAGADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=self.medio_destino,
        )
        Pago.objects.create(
            calculo_operacion=self.transaccion, medio_pago=MetodoPago.TIPO_TARJETA,
            proveedor='STRIPE', identificador_externo='pi_test_1', monto=Decimal('747400.00'),
        )


class EmitirDocumentoElectronicoTest(FacturaElectronicaTestCase):
    """``emitir_documento_electronico``: camino feliz, rechazo, comunicación incierta e idempotencia."""

    def test_emision_exitosa_reserva_numero_y_guarda_el_cdc(self):
        """Criterios 1 y 2: al emitirse, reserva el próximo número, pasa por calcular_de y guarda el CDC."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900', 'dTotGralOpe': '747400'}),
                _respuesta(code=0, results={'CDC': '01234567890123456789012345678901234567890123'}),
            ]
            documento = emitir_documento_electronico(self.transaccion)

        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(mock_post.call_args_list[0].kwargs['json']['operation'], 'calcular_de')
        self.assertEqual(mock_post.call_args_list[1].kwargs['json']['operation'], 'generar_de')
        # El DE que se le manda a generar_de es, tal cual, el que devolvió calcular_de.
        self.assertEqual(mock_post.call_args_list[1].kwargs['json']['params']['DE']['dNumDoc'], '0000900')
        self.assertEqual(documento.numero_documento, '0000900')
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_GENERADO)
        self.assertEqual(documento.cdc, '01234567890123456789012345678901234567890123')
        self.assertEqual(documento.operation_id, 'OP-1')
        self.assertEqual(documento.error_generacion, '')
        self.contador.refresh_from_db()
        self.assertEqual(self.contador.ultimo_asignado, 900)

    def test_rechazo_de_factura_segura_deja_error_generacion_sin_reintentar_solo(self):
        """Criterio 3: un rechazo claro (code negativo) nunca bloquea el pago, pero sí queda registrado."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(code=-5, description='dNumIDRec inválido')
            documento = emitir_documento_electronico(self.transaccion)

        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_ERROR_GENERACION)
        self.assertIn('dNumIDRec inválido', documento.error_generacion)
        # El número ya reservado queda "quemado": nunca se libera ni se reutiliza.
        self.contador.refresh_from_db()
        self.assertEqual(self.contador.ultimo_asignado, 900)

    def test_cliente_sin_email_no_llama_a_la_api(self):
        """dEmailRec es obligatorio para Factura Segura: sin email, ni se intenta la llamada."""
        self.cliente.email = ''
        self.cliente.save(update_fields=['email'])

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            documento = emitir_documento_electronico(self.transaccion)
            mock_post.assert_not_called()

        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_ERROR_GENERACION)
        self.assertIn('email', documento.error_generacion.lower())
        # El número queda reservado igual (es un dato que nunca cambia solo
        # reintentando), pero al menos no se gastó ningún intento real.
        self.contador.refresh_from_db()
        self.assertEqual(self.contador.ultimo_asignado, 900)

    def test_timeout_deja_error_generacion_sin_reintentar_automaticamente(self):
        """Criterio 4: un timeout no se reintenta solo (no se sabe si Factura Segura la procesó)."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout('sin respuesta')
            documento = emitir_documento_electronico(self.transaccion)
            mock_post.assert_called_once()

        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_ERROR_GENERACION)
        self.assertIn('timeout', documento.error_generacion.lower())

    def test_una_transaccion_ya_facturada_nunca_se_vuelve_a_emitir(self):
        """Criterio 5: si ya existe un documento para esta transacción, se devuelve ese, sin llamar a la API."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [_respuesta_calculo(), _respuesta(code=0, results={'CDC': 'CDC-1'})]
            primero = emitir_documento_electronico(self.transaccion)

        self.transaccion.refresh_from_db()
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            segundo = emitir_documento_electronico(self.transaccion)
            mock_post.assert_not_called()

        self.assertEqual(primero.pk, segundo.pk)
        self.assertEqual(DocumentoElectronico.objects.filter(calculo_operacion=self.transaccion).count(), 1)

    def test_rango_agotado_no_crea_documento_ni_rompe_el_flujo(self):
        """Si no queda ningún número disponible, no se crea ningún documento (y no se relanza la excepción)."""
        self.contador.ultimo_asignado = 901  # Ya se asignó el último número del rango de prueba (900-901).
        self.contador.save(update_fields=['ultimo_asignado'])

        documento = emitir_documento_electronico(self.transaccion)

        self.assertIsNone(documento)
        self.assertFalse(DocumentoElectronico.objects.filter(calculo_operacion=self.transaccion).exists())

    def test_el_resumido_de_incluye_la_tasa_aplicada(self):
        """Criterio 1: la tasa aplicada viaja en dInfAdic (SIFEN no tiene un campo estructurado para esto)."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900'}),
                _respuesta(code=0, results={'CDC': 'CDC-1'}),
            ]
            emitir_documento_electronico(self.transaccion)

        de_resumido = mock_post.call_args_list[0].kwargs['json']['params']['DE']
        self.assertEqual(de_resumido['dInfAdic'], 'Tasa aplicada: 7400.00 (USD/PYG)')

    def test_el_email_del_usuario_titular_tiene_prioridad_sobre_el_campo_legado(self):
        """dEmailRec usa Cliente.user.email (Keycloak) antes que el campo Cliente.email, legado."""
        self.cliente.user.email = 'titular-keycloak@test.com'
        self.cliente.user.save(update_fields=['email'])
        # self.cliente.email sigue siendo 'cliente-fe@test.com' (el legado del fixture base).

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900'}),
                _respuesta(code=0, results={'CDC': 'CDC-1'}),
            ]
            emitir_documento_electronico(self.transaccion)

        de_resumido = mock_post.call_args_list[0].kwargs['json']['params']['DE']
        self.assertEqual(de_resumido['dEmailRec'], 'titular-keycloak@test.com')

    def test_sin_titular_usa_el_email_de_un_usuario_asociado(self):
        """Caso real: Cliente.user en None, pero Cliente.usuarios (M2M) sí tiene un email de Keycloak."""
        self.cliente.user = None
        self.cliente.email = None  # tampoco hay campo legado cargado, caso real encontrado en vivo.
        self.cliente.save(update_fields=['user', 'email'])
        operador = User.objects.create_user(username='operador-fe', email='operador@test.com', password='password123')
        self.cliente.usuarios.add(operador)

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900'}),
                _respuesta(code=0, results={'CDC': 'CDC-1'}),
            ]
            emitir_documento_electronico(self.transaccion)

        de_resumido = mock_post.call_args_list[0].kwargs['json']['params']['DE']
        self.assertEqual(de_resumido['dEmailRec'], 'operador@test.com')

    def test_intentar_emitir_nunca_relanza_un_error_inesperado(self):
        """Criterio 3: cualquier falla no prevista queda contenida, nunca interrumpe el pago ya confirmado."""
        with patch('apps.divisas.factura_electronica.emitir_documento_electronico') as mock_emitir:
            mock_emitir.side_effect = RuntimeError('fallo inesperado')
            resultado = intentar_emitir_documento_electronico(self.transaccion)

        self.assertIsNone(resultado)


class ComisionGravadaAl10PorCientoTest(FacturaElectronicaTestCase):
    """La comisión se factura como ítem separado, gravado al 10% de IVA, en compra, venta y cambio.

    Confirmado con el usuario: la comisión de Global Exchange es un
    servicio propio (no el cambio de divisa en sí, que sigue exento).
    También cubre el bug ya corregido en un cambio: el total facturado
    debe reflejar el monto ya neto de comisión (``monto_final``), no el
    bruto triangulado del Paso A (``monto_equivalente_pyg``).
    """

    def test_compra_separa_la_comision_del_resto_exento(self):
        """La compra del fixture: bruto=740000, comisión=7400, total=747400 (monto_final sin cambios)."""
        total = _total_en_pyg(self.transaccion)
        self.assertEqual(total, Decimal('747400'))
        self.assertEqual(_comision_en_pyg(self.transaccion), Decimal('7400'))

        items = _grupos_item_resumido(self.transaccion, total)
        self.assertEqual(len(items), 2)
        exento, gravado = items
        self.assertEqual(exento['iAfecIVA'], '3')
        self.assertEqual(exento['dPUniProSer'], '740000')
        self.assertEqual(gravado['iAfecIVA'], '1')
        self.assertEqual(gravado['dTasaIVA'], '10')
        self.assertEqual(gravado['dPUniProSer'], '7400')

    def test_venta_separa_la_comision_del_resto_exento(self):
        """En una venta, monto_final=bruto-comisión: el total facturado sigue siendo monto_final."""
        usuario = User.objects.create_user(username='cliente-fe-venta', password='password123')
        venta = CalculoOperacion.objects.create(
            usuario=usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_VENTA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'), monto_final=Decimal('732600.00'),
            estado=CalculoOperacion.ESTADO_PAGADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=self.medio_destino,
        )

        total = _total_en_pyg(venta)
        self.assertEqual(total, Decimal('732600'))
        self.assertEqual(_comision_en_pyg(venta), Decimal('7400'))

        items = _grupos_item_resumido(venta, total)
        exento, gravado = items
        self.assertEqual(exento['dPUniProSer'], '725200')
        self.assertEqual(gravado['dPUniProSer'], '7400')

    def test_cambio_usa_el_monto_neto_de_comision_no_el_bruto_triangulado(self):
        """Bug corregido: el total de un cambio debe salir de monto_final, no de monto_equivalente_pyg."""
        usuario = User.objects.create_user(username='cliente-fe-cambio', password='password123')
        ars = Divisa.objects.create(codigo='ARS', nombre='Peso argentino', simbolo='$', activa=True)
        cambio = CalculoTriangulacion.objects.create(
            usuario=usuario, cliente=self.cliente, divisa_origen=self.usd, divisa_destino=ars,
            codigo_divisa_origen='USD', codigo_divisa_destino='ARS', monto_origen=Decimal('100.00'),
            tasa_compra_aplicada=Decimal('7400.00'), tasa_venta_aplicada=Decimal('20.00'),
            tasa_cruzada=Decimal('370.000000'), monto_equivalente_pyg=Decimal('740000.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('370.00'),
            monto_final=Decimal('36630.00'), estado=CalculoTriangulacion.ESTADO_PAGADA,
            vence_en=timezone.now() + timedelta(seconds=300), confirmado_en=timezone.now(),
        )

        # El total correcto (732600) es menor que el bruto triangulado del
        # Paso A (740000, monto_equivalente_pyg): ignorar la comisión en un
        # cambio facturaba de más, exactamente el bug que esto corrige.
        total = _total_en_pyg(cambio)
        self.assertEqual(total, Decimal('732600'))
        self.assertNotEqual(total, cambio.monto_equivalente_pyg.to_integral_value())
        self.assertEqual(_comision_en_pyg(cambio), Decimal('7400'))

        items = _grupos_item_resumido(cambio, total)
        exento, gravado = items
        self.assertEqual(exento['dPUniProSer'], '725200')
        self.assertEqual(gravado['iAfecIVA'], '1')
        self.assertEqual(gravado['dPUniProSer'], '7400')

    def test_sin_comision_queda_un_unico_item_exento(self):
        """Un cliente con 0% de comisión (ConfiguracionComision) sigue facturando con un único ítem."""
        self.transaccion.comision = Decimal('0.00')
        self.transaccion.monto_final = Decimal('740000.00')
        self.transaccion.save(update_fields=['comision', 'monto_final'])

        total = _total_en_pyg(self.transaccion)
        items = _grupos_item_resumido(self.transaccion, total)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['iAfecIVA'], '3')
        self.assertEqual(items[0]['dPUniProSer'], '740000')


class TipoTransaccionTest(FacturaElectronicaTestCase):
    """``iTipTra``/``dDesTipTra``: códigos propios de una casa de cambio, no 'Venta de mercadería'.

    Bug corregido: el código se mandaba fijo en ``'1'`` ("Venta de
    mercadería", sin verificar contra el manual) y ``dDesTipTra`` ni
    siquiera se mandaba, pese a ser obligatorio junto con ``iTipTra``.
    """

    def test_compra_usa_el_codigo_de_compra_de_divisas(self):
        self.assertEqual(_tipo_transaccion(self.transaccion), ('6', 'Compra de divisas'))

    def test_venta_usa_el_codigo_de_venta_de_divisas(self):
        usuario = User.objects.create_user(username='cliente-fe-venta-tipotra', password='password123')
        venta = CalculoOperacion.objects.create(
            usuario=usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_VENTA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'), monto_final=Decimal('732600.00'),
            estado=CalculoOperacion.ESTADO_PAGADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=self.medio_destino,
        )
        self.assertEqual(_tipo_transaccion(venta), ('5', 'Venta de divisas'))

    def test_cambio_usa_el_codigo_de_venta_de_divisas(self):
        """Decisión tomada con el usuario: un cambio se factura como lo que Global Exchange entrega."""
        usuario = User.objects.create_user(username='cliente-fe-cambio-tipotra', password='password123')
        ars = Divisa.objects.create(codigo='ARS', nombre='Peso argentino', simbolo='$', activa=True)
        cambio = CalculoTriangulacion.objects.create(
            usuario=usuario, cliente=self.cliente, divisa_origen=self.usd, divisa_destino=ars,
            codigo_divisa_origen='USD', codigo_divisa_destino='ARS', monto_origen=Decimal('100.00'),
            tasa_compra_aplicada=Decimal('7400.00'), tasa_venta_aplicada=Decimal('20.00'),
            tasa_cruzada=Decimal('370.000000'), monto_equivalente_pyg=Decimal('740000.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('370.00'),
            monto_final=Decimal('36630.00'), estado=CalculoTriangulacion.ESTADO_PAGADA,
            vence_en=timezone.now() + timedelta(seconds=300), confirmado_en=timezone.now(),
        )
        self.assertEqual(_tipo_transaccion(cambio), ('5', 'Venta de divisas'))

    def test_el_resumido_de_manda_itiptra_y_su_descripcion(self):
        """Integración: el ``DE`` real enviado a calcular_de lleva ambos campos, no solo el código."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900'}),
                _respuesta(code=0, results={'CDC': 'CDC-1'}),
            ]
            emitir_documento_electronico(self.transaccion)

        de_resumido = mock_post.call_args_list[0].kwargs['json']['params']['DE']
        self.assertEqual(de_resumido['iTipTra'], '6')
        self.assertEqual(de_resumido['dDesTipTra'], 'Compra de divisas')


class ConsultarEstadoSifenTest(FacturaElectronicaTestCase):
    """``consultar_estado_sifen``: poll de estado contra ``get_estado_sifen``."""

    def setUp(self):
        """Además del fixture base, un documento ya generado con CDC."""
        super().setUp()
        self.documento = DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', cdc='CDC-DE-PRUEBA',
        )

    def test_aprobado_actualiza_el_estado(self):
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(code=0, results={'estado_sifen': 'Aprobado', 'desc_sifen': '0260 - Aprobado'})
            resultado = consultar_estado_sifen(self.documento)

        self.assertTrue(resultado)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, DocumentoElectronico.ESTADO_APROBADO)
        self.assertIsNotNone(self.documento.consultado_en)

    def test_rechazado_actualiza_el_estado_y_guarda_el_motivo(self):
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(
                code=0, results={'estado_sifen': 'Rechazado', 'desc_sifen': '0160 - Rechazado', 'error_sifen': 'CDC duplicado'},
            )
            resultado = consultar_estado_sifen(self.documento)

        self.assertTrue(resultado)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, DocumentoElectronico.ESTADO_RECHAZADO)
        self.assertEqual(self.documento.error_sifen, 'CDC duplicado')

    def test_estado_intermedio_no_se_marca_como_error(self):
        """'SOL.APROBACION'/'ENVIADO_A_SIFEN' son intermedios, no errores: no hay que resolverlos todavía."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(code=0, results={'estado_sifen': 'ENVIADO_A_SIFEN', 'desc_sifen': ''})
            resultado = consultar_estado_sifen(self.documento)

        self.assertTrue(resultado)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, DocumentoElectronico.ESTADO_GENERADO)
        self.assertEqual(self.documento.estado_sifen, 'ENVIADO_A_SIFEN')

    def test_sin_respuesta_no_modifica_nada(self):
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError('sin conexión')
            resultado = consultar_estado_sifen(self.documento)

        self.assertFalse(resultado)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, DocumentoElectronico.ESTADO_GENERADO)

    def test_sin_cdc_no_consulta_nada(self):
        self.documento.cdc = ''
        self.documento.save(update_fields=['cdc'])
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            resultado = consultar_estado_sifen(self.documento)
            mock_post.assert_not_called()

        self.assertFalse(resultado)


class DescargarArchivosTest(FacturaElectronicaTestCase):
    """``descargar_kude``/``descargar_xml``: descarga bajo demanda, sin guardar nada."""

    def setUp(self):
        """Además del fixture base, un documento ya generado con CDC."""
        super().setUp()
        self.documento = DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', cdc='CDC-DE-PRUEBA',
        )

    def test_descarga_el_kude_exitosamente(self):
        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            mock_get.return_value = Mock(status_code=200, content=b'%PDF-contenido-falso')
            mock_get.return_value.raise_for_status.side_effect = None
            contenido = descargar_kude(self.documento)

        self.assertEqual(contenido, b'%PDF-contenido-falso')
        url_pedida = mock_get.call_args.args[0]
        self.assertIn('dwn_kude', url_pedida)
        self.assertIn('CDC-DE-PRUEBA', url_pedida)

    def test_descarga_el_xml_exitosamente(self):
        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            mock_get.return_value = Mock(status_code=200, content=b'<xml-falso/>')
            mock_get.return_value.raise_for_status.side_effect = None
            contenido = descargar_xml(self.documento)

        self.assertEqual(contenido, b'<xml-falso/>')

    def test_sin_cdc_no_descarga_nada(self):
        self.documento.cdc = ''
        self.documento.save(update_fields=['cdc'])
        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            contenido = descargar_kude(self.documento)
            mock_get.assert_not_called()

        self.assertIsNone(contenido)

    def test_falla_de_comunicacion_devuelve_none(self):
        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError('sin conexión')
            contenido = descargar_kude(self.documento)

        self.assertIsNone(contenido)


class ReintentarEmisionTest(FacturaElectronicaTestCase):
    """``reintentar_emision``: reintento manual de un documento en 'Error al generar'."""

    def setUp(self):
        """Documento ya en Error al generar, listo para reintentarse."""
        super().setUp()
        self.documento = DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', estado=DocumentoElectronico.ESTADO_ERROR_GENERACION,
            error_generacion='timeout anterior',
        )

    def test_reintento_exitoso_reutiliza_el_mismo_numero(self):
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900'}),
                _respuesta(code=0, results={'CDC': 'CDC-REINTENTO'}),
            ]
            resultado = reintentar_emision(self.documento)
            kwargs = mock_post.call_args.kwargs  # La última llamada: generar_de.

        self.assertTrue(resultado)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, DocumentoElectronico.ESTADO_GENERADO)
        self.assertEqual(self.documento.cdc, 'CDC-REINTENTO')
        self.assertEqual(kwargs['json']['params']['DE']['dNumDoc'], '0000900')
        # Nunca se reservó un segundo número por el reintento.
        self.contador.refresh_from_db()
        self.assertEqual(self.contador.ultimo_asignado, None)

    def test_no_reintenta_un_documento_que_no_esta_en_error(self):
        self.documento.estado = DocumentoElectronico.ESTADO_GENERADO
        self.documento.save(update_fields=['estado'])

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            resultado = reintentar_emision(self.documento)
            mock_post.assert_not_called()

        self.assertFalse(resultado)


class DocumentosElectronicosListViewTest(FacturaElectronicaTestCase):
    """Verifica la pantalla administrativa de documentos electrónicos y su reintento."""

    def setUp(self):
        """Además del fixture base, un administrador autenticado y un documento fallido."""
        super().setUp()
        self.admin = User.objects.create_user(username='admin-fe', password='password123')
        self.client.login(username='admin-fe', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()
        self.documento = DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', estado=DocumentoElectronico.ESTADO_ERROR_GENERACION,
            error_generacion='timeout anterior',
        )

    def test_la_lista_muestra_el_documento_con_boton_de_reintentar(self):
        response = self.client.get(reverse('divisas:documentos_electronicos'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '0000900')
        self.assertContains(response, 'Reintentar')
        # El cliente se muestra como texto simple: no hay ningún enlace a una
        # pantalla de detalle que, para un administrador, siempre da 403
        # (esas vistas son exclusivas del propio cliente).
        self.assertContains(response, 'Cliente Factura')
        self.assertNotContains(response, 'detalle_transaccion_operacion')

    def test_un_cliente_no_puede_acceder(self):
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(reverse('divisas:documentos_electronicos'))

        self.assertEqual(response.status_code, 403)

    def test_reintentar_desde_la_vista_actualiza_el_documento(self):
        url = reverse('divisas:reintentar_emision_documento_electronico', kwargs={'pk': self.documento.pk})
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [_respuesta_calculo(), _respuesta(code=0, results={'CDC': 'CDC-VISTA'})]
            response = self.client.post(url)

        self.assertRedirects(response, reverse('divisas:documentos_electronicos'))
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, DocumentoElectronico.ESTADO_GENERADO)

    def test_consultar_estado_sifen_desde_la_vista_actualiza_el_documento(self):
        """Criterios 2 y 3: la única forma de que el documento reciba la aprobación/rechazo real de SIFEN."""
        self.documento.estado = DocumentoElectronico.ESTADO_GENERADO
        self.documento.cdc = 'CDC-DE-PRUEBA'
        self.documento.error_generacion = ''
        self.documento.save(update_fields=['estado', 'cdc', 'error_generacion'])
        url = reverse('divisas:consultar_estado_sifen_documento_electronico', kwargs={'pk': self.documento.pk})

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(code=0, results={'estado_sifen': 'Aprobado', 'desc_sifen': '0260 - Aprobado'})
            response = self.client.post(url)

        self.assertRedirects(response, reverse('divisas:documentos_electronicos'))
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, DocumentoElectronico.ESTADO_APROBADO)

    def test_consultar_estado_sifen_sin_cdc_no_llama_a_la_api(self):
        url = reverse('divisas:consultar_estado_sifen_documento_electronico', kwargs={'pk': self.documento.pk})

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            response = self.client.post(url)
            mock_post.assert_not_called()

        self.assertRedirects(response, reverse('divisas:documentos_electronicos'))


class MisFacturasElectronicasListViewTest(FacturaElectronicaTestCase):
    """Verifica la pantalla de solo lectura donde el propio cliente ve sus facturas electrónicas."""

    def setUp(self):
        """Además del fixture base, logueado como el cliente (no admin), con un documento emitido."""
        super().setUp()
        # El test_func de la vista exige user.clientes (el M2M `usuarios` de
        # Cliente), no solo el OneToOneField `user` que ya fija el fixture
        # base: sin este `add`, el propio cliente queda sin acceso (403).
        self.cliente.usuarios.add(self.cliente.user)
        self.client.login(username='cliente-fe', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.documento = DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', estado=DocumentoElectronico.ESTADO_GENERADO, cdc='CDC-PROPIA',
        )
        self.url = reverse('divisas:mis_facturas_electronicas')

    def _transaccion_propia(self, monto_final=Decimal('100.00')):
        """Crea, para el mismo cliente, una compra 'Pagada' adicional lista para facturar."""
        usuario = self.cliente.user
        return CalculoOperacion.objects.create(
            usuario=usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('10.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('740.00'), monto_final=monto_final,
            estado=CalculoOperacion.ESTADO_PAGADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )

    def test_el_cliente_ve_su_propia_factura(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '0000900')
        self.assertContains(response, 'CDC-PROPIA')

    def test_criterio_2_el_listado_muestra_numero_cdc_transaccion_fecha_de_emision_y_monto(self):
        """Criterio 2: cada factura muestra número/CDC, transacción asociada, fecha de emisión, monto y estado."""
        self.documento.estado = DocumentoElectronico.ESTADO_APROBADO
        self.documento.emitida_en = timezone.make_aware(datetime(2026, 10, 15, 9, 30))
        self.documento.save(update_fields=['estado', 'emitida_en'])

        response = self.client.get(self.url)

        self.assertContains(response, '0000900')  # número
        self.assertContains(response, 'CDC-PROPIA')  # CDC
        self.assertContains(response, 'Compra USD')  # transacción asociada
        self.assertContains(response, '15/10/2026 09:30')  # fecha de emisión
        self.assertContains(response, '747.400,00')  # monto (de la transacción, no del documento)
        self.assertContains(response, 'Aprobado')  # estado

    def test_criterio_4_hacer_clic_en_una_factura_lleva_al_detalle_completo_del_comprobante(self):
        """Criterio 4: el listado enlaza al detalle de la transacción, que incluye el comprobante completo."""
        url_detalle = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.transaccion.pk})

        response = self.client.get(self.url)
        self.assertContains(response, url_detalle)

        detalle = self.client.get(url_detalle)
        self.assertContains(detalle, '0000900')
        self.assertContains(detalle, 'CDC-PROPIA')

    def test_criterio_5_sin_facturas_emitidas_muestra_un_mensaje_sin_error(self):
        """Criterio 5: sin ninguna factura, se muestra un mensaje explícito en vez de un error."""
        self.documento.delete()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Todavía no tenés ninguna factura electrónica emitida.')

    def test_criterio_1_el_listado_esta_paginado(self):
        """Criterio 1: con más de 20 facturas, el listado se pagina en vez de mostrarlas todas juntas."""
        for indice in range(25):
            transaccion = self._transaccion_propia()
            DocumentoElectronico.objects.create(
                calculo_operacion=transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
                numero_documento=f'{910 + indice:07d}', estado=DocumentoElectronico.ESTADO_APROBADO,
                cdc=f'CDC-{indice}',
            )

        response = self.client.get(self.url)

        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['documentos']), 20)
        self.assertContains(response, 'Página 1 de')

    def test_criterio_3_filtra_por_rango_de_fechas_de_emision(self):
        """Criterio 3: filtrar por rango de fechas actualiza el listado mostrando solo las que coinciden."""
        transaccion_vieja = self._transaccion_propia()
        documento_viejo = DocumentoElectronico.objects.create(
            calculo_operacion=transaccion_vieja, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000911', estado=DocumentoElectronico.ESTADO_APROBADO, cdc='CDC-VIEJA',
            emitida_en=timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
        )
        transaccion_reciente = self._transaccion_propia()
        documento_reciente = DocumentoElectronico.objects.create(
            calculo_operacion=transaccion_reciente, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000912', estado=DocumentoElectronico.ESTADO_APROBADO, cdc='CDC-RECIENTE',
            emitida_en=timezone.make_aware(datetime(2026, 10, 20, 12, 0)),
        )

        response = self.client.get(self.url, {'fecha_desde': '2026-10-01', 'fecha_hasta': '2026-10-31'})

        documentos = list(response.context['documentos'])
        self.assertIn(documento_reciente, documentos)
        self.assertNotIn(documento_viejo, documentos)
        self.assertNotIn(self.documento, documentos)  # sin emitida_en: tampoco coincide con el rango
        self.assertContains(response, 'CDC-RECIENTE')
        self.assertNotContains(response, 'CDC-VIEJA')

    def test_criterio_3_un_rango_sin_coincidencias_informa_sin_romper(self):
        """Un filtro de fechas sin ninguna factura que coincida no es un error: muestra un mensaje aparte."""
        response = self.client.get(self.url, {'fecha_desde': '2020-01-01', 'fecha_hasta': '2020-01-31'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se encontraron facturas para el rango de fechas seleccionado.')

    def test_criterio_3_limpiar_filtros_vuelve_a_mostrar_todo(self):
        """Sin ningún filtro en la URL, vuelve a verse la factura que el filtro anterior había ocultado."""
        response = self.client.get(self.url)

        self.assertContains(response, 'CDC-PROPIA')

    def test_no_ve_la_factura_de_otro_cliente(self):
        otro_usuario = User.objects.create_user(username='otro-cliente-fe', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario, identificador='9999999', nombre='Otro', apellido='Cliente',
            email='otro@test.com', is_active=True,
        )
        otra_transaccion = CalculoOperacion.objects.create(
            usuario=otro_usuario, cliente=otro_cliente, tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('10.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('740.00'), monto_final=Decimal('74740.00'),
            estado=CalculoOperacion.ESTADO_PAGADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        DocumentoElectronico.objects.create(
            calculo_operacion=otra_transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000901', estado=DocumentoElectronico.ESTADO_GENERADO, cdc='CDC-AJENA',
        )

        response = self.client.get(reverse('divisas:mis_facturas_electronicas'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['documentos']), 1)
        self.assertNotContains(response, 'CDC-AJENA')

    def test_un_administrador_no_puede_acceder(self):
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('divisas:mis_facturas_electronicas'))

        self.assertEqual(response.status_code, 403)


class DescargarDocumentoElectronicoViewTest(FacturaElectronicaTestCase):
    """Verifica permisos y respuesta de la descarga compartida (KuDE/XML)."""

    def setUp(self):
        """Además del fixture base, un documento con CDC propio del cliente."""
        super().setUp()
        self.cliente.usuarios.add(self.cliente.user)
        self.documento = DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', estado=DocumentoElectronico.ESTADO_GENERADO, cdc='CDC-DESCARGA',
        )

    def _url(self, formato='kude'):
        return reverse('divisas:descargar_documento_electronico', kwargs={'pk': self.documento.pk, 'formato': formato})

    def test_un_administrador_puede_descargar(self):
        admin = User.objects.create_user(username='admin-descarga', password='password123')
        self.client.login(username='admin-descarga', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            mock_get.return_value = Mock(status_code=200, content=b'%PDF-contenido-falso')
            mock_get.return_value.raise_for_status.side_effect = None
            response = self.client.get(self._url('kude'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'%PDF-contenido-falso')
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])

    def test_el_propio_cliente_puede_descargar_su_xml(self):
        self.client.login(username='cliente-fe', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            mock_get.return_value = Mock(status_code=200, content=b'<xml-falso/>')
            mock_get.return_value.raise_for_status.side_effect = None
            response = self.client.get(self._url('xml'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')

    def test_otro_cliente_no_puede_descargar(self):
        otro_usuario = User.objects.create_user(username='otro-descarga', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario, identificador='8888888', nombre='Otro', apellido='Ajeno',
            email='ajeno@test.com', is_active=True,
        )
        otro_cliente.usuarios.add(otro_usuario)
        self.client.login(username='otro-descarga', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(self._url('kude'))

        self.assertEqual(response.status_code, 403)

    def test_sin_cdc_devuelve_400(self):
        self.documento.cdc = ''
        self.documento.save(update_fields=['cdc'])
        admin = User.objects.create_user(username='admin-sin-cdc', password='password123')
        self.client.login(username='admin-sin-cdc', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(self._url('kude'))

        self.assertEqual(response.status_code, 400)

    def test_fallo_de_factura_segura_devuelve_502(self):
        admin = User.objects.create_user(username='admin-502', password='password123')
        self.client.login(username='admin-502', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError('sin conexión')
            response = self.client.get(self._url('kude'))

        self.assertEqual(response.status_code, 502)

    def test_formato_desconocido_devuelve_404(self):
        admin = User.objects.create_user(username='admin-404', password='password123')
        self.client.login(username='admin-404', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(self._url('docx'))

        self.assertEqual(response.status_code, 404)


class FechaEmisionTest(FacturaElectronicaTestCase):
    """Criterio 4: la fecha y hora de emisión se registra solo cuando la factura se genera bien."""

    def test_emision_exitosa_registra_fecha_y_hora(self):
        """Una emisión exitosa deja ``emitida_en`` con el momento de la generación."""
        antes = timezone.now()
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [_respuesta_calculo(), _respuesta(code=0, results={'CDC': 'CDC-FECHA'})]
            documento = emitir_documento_electronico(self.transaccion)

        documento.refresh_from_db()
        self.assertIsNotNone(documento.emitida_en)
        self.assertGreaterEqual(documento.emitida_en, antes)

    def test_una_falla_no_registra_fecha_de_emision(self):
        """Si Factura Segura rechaza la emisión, ``emitida_en`` queda vacía."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(code=-5, description='rechazo')
            documento = emitir_documento_electronico(self.transaccion)

        self.assertIsNone(documento.emitida_en)

    def test_un_reintento_exitoso_registra_la_fecha(self):
        """Un reintento manual que sale bien también registra la fecha de emisión."""
        documento = DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', estado=DocumentoElectronico.ESTADO_ERROR_GENERACION,
        )
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [_respuesta_calculo(), _respuesta(code=0, results={'CDC': 'CDC-R'})]
            reintentar_emision(documento)

        documento.refresh_from_db()
        self.assertIsNotNone(documento.emitida_en)


class VinculoUnicoConLaTransaccionTest(FacturaElectronicaTestCase):
    """Criterio 2: cada factura queda ligada a una sola transacción, y viceversa."""

    def test_una_transaccion_no_puede_tener_dos_facturas(self):
        """El ``OneToOneField`` impide una segunda factura vigente para la misma transacción."""
        DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900',
        )
        with self.assertRaises(IntegrityError), db_transaction.atomic():
            DocumentoElectronico.objects.create(
                calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
                numero_documento='0000901',
            )

    def test_la_base_rechaza_una_factura_sin_transaccion(self):
        """La restricción de base de datos exige una transacción de origen."""
        with self.assertRaises(IntegrityError), db_transaction.atomic():
            DocumentoElectronico.objects.create(
                tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA, numero_documento='0000900',
            )

    def test_la_base_rechaza_una_factura_con_dos_transacciones(self):
        """La restricción de base de datos impide asociar la misma factura a una compra y a un cambio."""
        ars = Divisa.objects.create(codigo='ARS', nombre='Peso argentino', simbolo='$', activa=True)
        cambio = CalculoTriangulacion.objects.create(
            usuario=self.cliente.user, cliente=self.cliente, divisa_origen=self.usd, divisa_destino=ars,
            codigo_divisa_origen='USD', codigo_divisa_destino='ARS', monto_origen=Decimal('100.00'),
            tasa_compra_aplicada=Decimal('7400.00'), tasa_venta_aplicada=Decimal('20.00'),
            tasa_cruzada=Decimal('370.000000'), monto_equivalente_pyg=Decimal('740000.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('370.00'),
            monto_final=Decimal('36630.00'), estado=CalculoTriangulacion.ESTADO_PAGADA,
            vence_en=timezone.now() + timedelta(seconds=300), confirmado_en=timezone.now(),
        )
        with self.assertRaises(IntegrityError), db_transaction.atomic():
            DocumentoElectronico.objects.create(
                calculo_operacion=self.transaccion, calculo_triangulacion=cambio,
                tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA, numero_documento='0000900',
            )


class FacturaPendienteParaElClienteTest(FacturaElectronicaTestCase):
    """Criterio 3: ante un rechazo, el cliente ve "pendiente de generación" sin perder el resto del detalle."""

    def setUp(self):
        """Además del fixture base, logueado como el cliente propietario de la transacción."""
        super().setUp()
        self.cliente.usuarios.add(self.cliente.user)
        self.client.login(username='cliente-fe', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.url = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.transaccion.pk})

    def _documento(self, **campos):
        """Crea el documento de la transacción base con los campos indicados."""
        return DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', **campos,
        )

    def _transaccion_fresca(self):
        """Recarga la transacción para descartar el documento cacheado en la relación inversa."""
        return CalculoOperacion.objects.get(pk=self.transaccion.pk)

    def test_helper_pendiente_con_cada_estado_fallido(self):
        """Fallo al generar, rechazo de SIFEN y error de SIFEN cuentan como pendientes."""
        for estado in DocumentoElectronico.ESTADOS_PENDIENTES:
            with self.subTest(estado=estado):
                DocumentoElectronico.objects.filter(calculo_operacion=self.transaccion).delete()
                self._documento(estado=estado)
                self.assertTrue(factura_pendiente_de_generacion(self._transaccion_fresca()))

    def test_helper_no_pendiente_si_la_factura_se_genero(self):
        """Una factura aprobada no se informa como pendiente."""
        self._documento(estado=DocumentoElectronico.ESTADO_APROBADO, cdc='CDC-OK')
        self.assertFalse(factura_pendiente_de_generacion(self._transaccion_fresca()))

    def test_helper_pendiente_si_pagada_y_sin_documento(self):
        """Pagada pero sin documento (p. ej. rango agotado) también es "pendiente de generación"."""
        self.assertTrue(factura_pendiente_de_generacion(self.transaccion))

    def test_helper_no_pendiente_si_aun_no_se_pago(self):
        """Una transacción todavía no pagada no corresponde facturarla, así que no es pendiente."""
        self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
        self.assertFalse(factura_pendiente_de_generacion(self.transaccion))

    def test_detalle_rechazado_informa_pendiente_y_muestra_el_resto(self):
        """El detalle informa la factura pendiente, no filtra el error técnico y conserva los datos."""
        self._documento(
            estado=DocumentoElectronico.ESTADO_ERROR_GENERACION, error_generacion='detalle tecnico interno',
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pendiente de generación')
        self.assertNotContains(response, 'detalle tecnico interno')
        self.assertContains(response, '747.400')

    def test_detalle_sifen_rechazo_informa_pendiente(self):
        """Un rechazo posterior de SIFEN también se informa como pendiente, sin mostrar su CDC."""
        self._documento(estado=DocumentoElectronico.ESTADO_RECHAZADO, cdc='CDC-RECHAZADO')

        response = self.client.get(self.url)

        self.assertContains(response, 'pendiente de generación')
        self.assertNotContains(response, 'CDC-RECHAZADO')

    def test_detalle_factura_generada_muestra_cdc_y_fecha_de_emision(self):
        """Con la factura generada, el detalle muestra su CDC y la fecha y hora de emisión."""
        emitida = timezone.make_aware(datetime(2026, 10, 30, 14, 5))
        self._documento(estado=DocumentoElectronico.ESTADO_APROBADO, cdc='CDC-VISIBLE', emitida_en=emitida)

        response = self.client.get(self.url)

        self.assertContains(response, 'CDC-VISIBLE')
        self.assertContains(response, '30/10/2026 14:05')
        self.assertNotContains(response, 'pendiente de generación')

    def test_listado_marca_pendiente_las_facturas_fallidas(self):
        """El listado del cliente rotula como "Pendiente de generación" las facturas fallidas."""
        self._documento(estado=DocumentoElectronico.ESTADO_RECHAZADO)

        response = self.client.get(reverse('divisas:mis_facturas_electronicas'))

        self.assertContains(response, 'Pendiente de generación')
