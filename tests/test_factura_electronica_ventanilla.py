"""Pruebas de la Factura Electrónica para operaciones de ventanilla (``apps.divisas.factura_electronica``).

Una ``OperacionVentanilla`` (compra/venta en efectivo, ver
``apps.caja.models.OperacionVentanilla``) se factura igual que una compra o
venta online, pero sin ningún ``Cliente`` del sistema ni ningún ``Pago``
asociado: el receptor sale de sus propios ``cliente_identificador``/
``cliente_nombre``/``cliente_email``, y el medio de pago siempre es
"Efectivo" (``iTiPago='1'``). **Ninguna de estas pruebas llama a la API real
de Factura Segura** (mismo criterio que ``tests/test_factura_electronica.py``):
``requests.post`` está siempre mockeado, y se usa un ``ContadorDocumentoElectronico``
de prueba, nunca el rango real.
"""

from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.caja.models import Caja, OperacionVentanilla, SaldoInicialCaja
from apps.divisas.factura_electronica import (
    _comision_en_pyg,
    _datos_receptor,
    _tipo_transaccion,
    _total_en_pyg,
    emitir_documento_electronico,
)
from apps.divisas.models import Cotizacion, ContadorDocumentoElectronico, Divisa, DocumentoElectronico

User = get_user_model()


def _respuesta(code=0, results=None, operation_id='OP-1'):
    """Misma respuesta falsa de Factura Segura que usa ``tests/test_factura_electronica.py``."""
    respuesta = Mock(status_code=200)
    respuesta.raise_for_status.side_effect = None
    respuesta.json.return_value = {
        'code': code, 'description': '', 'operation_info': {'id': operation_id},
        'results': [results] if results else [],
    }
    return respuesta


def _respuesta_calculo(de=None):
    return _respuesta(code=0, results={'DE': de or {}})


class FacturaVentanillaTestCase(TestCase):
    """Base común: una caja abierta, con una operación de ventanilla ya registrada."""

    def setUp(self):
        """Prepara una compra de USD en ventanilla, lista para facturar, con un rango de prueba chico."""
        self.contador, _ = ContadorDocumentoElectronico.objects.update_or_create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            defaults={'desde': 900, 'hasta': 901, 'ultimo_asignado': None},
        )
        self.cajero = User.objects.create_user(username='cajero-fe', password='password123')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
        self.caja = Caja.objects.create(usuario=self.cajero)
        self.operacion = OperacionVentanilla.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_COMPRA,
            divisa=self.usd, monto_divisa=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'),
            monto_pyg=Decimal('747400.00'), cliente_identificador='4111222',
            cliente_nombre='Cliente Ventanilla', cliente_email='cliente-ventanilla-fe@test.com',
        )


class MontosYReceptorTest(FacturaVentanillaTestCase):
    """``_total_en_pyg``/``_comision_en_pyg``/``_datos_receptor`` con una ``OperacionVentanilla``."""

    def test_el_total_es_el_monto_pyg_ya_calculado_sin_ninguna_conversion(self):
        self.assertEqual(_total_en_pyg(self.operacion), Decimal('747400'))

    def test_la_comision_es_la_propia_de_la_operacion(self):
        self.assertEqual(_comision_en_pyg(self.operacion), Decimal('7400'))

    def test_los_datos_del_receptor_son_los_del_cliente_de_mostrador(self):
        self.assertEqual(
            _datos_receptor(self.operacion),
            ('4111222', 'Cliente Ventanilla', 'cliente-ventanilla-fe@test.com'),
        )


class TipoTransaccionVentanillaTest(FacturaVentanillaTestCase):
    """``_tipo_transaccion`` traduce el tipo de ventanilla a su equivalente de ``CalculoOperacion``.

    Misma inversión que ya usa ``apps.caja.views.RegistrarOperacionVentanillaView``
    para calcular el monto: "Compra" de ventanilla (la casa le compra al
    cliente) equivale a "Venta" de ``CalculoOperacion``, y viceversa — así que
    el código SIFEN que le corresponde es el mismo que ya usa (y ya prueba)
    ``tests.test_factura_electronica.TipoTransaccionTest`` para ese
    equivalente, no uno nuevo inventado para este modelo.
    """

    def test_compra_de_ventanilla_usa_el_mismo_codigo_que_una_venta_online(self):
        self.assertEqual(_tipo_transaccion(self.operacion), ('5', 'Venta de divisas'))

    def test_venta_de_ventanilla_usa_el_mismo_codigo_que_una_compra_online(self):
        venta = OperacionVentanilla.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_VENTA,
            divisa=self.usd, monto_divisa=Decimal('50.00'), tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('3650.00'),
            monto_pyg=Decimal('361350.00'), cliente_identificador='4111222',
            cliente_nombre='Cliente Ventanilla', cliente_email='cliente-ventanilla-fe@test.com',
        )
        self.assertEqual(_tipo_transaccion(venta), ('6', 'Compra de divisas'))


class EmitirDocumentoElectronicoVentanillaTest(FacturaVentanillaTestCase):
    """``emitir_documento_electronico``/``intentar_emitir_documento_electronico`` con una ``OperacionVentanilla``."""

    def test_emite_correctamente_y_queda_vinculado_a_la_operacion(self):
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900'}),
                _respuesta(code=0, results={'CDC': 'CDC-VENTANILLA-1'}),
            ]
            documento = emitir_documento_electronico(self.operacion)

        self.assertEqual(documento.operacion_ventanilla, self.operacion)
        self.assertIsNone(documento.calculo_operacion)
        self.assertIsNone(documento.calculo_triangulacion)
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_GENERADO)
        self.assertEqual(documento.cdc, 'CDC-VENTANILLA-1')
        self.assertEqual(self.operacion.documento_electronico, documento)

    def test_el_resumido_de_manda_los_datos_del_cliente_de_mostrador_y_pago_en_efectivo(self):
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900'}),
                _respuesta(code=0, results={'CDC': 'CDC-VENTANILLA-2'}),
            ]
            emitir_documento_electronico(self.operacion)

        de_resumido = mock_post.call_args_list[0].kwargs['json']['params']['DE']
        self.assertEqual(de_resumido['dNumIDRec'], '4111222')
        self.assertEqual(de_resumido['dNomRec'], 'Cliente Ventanilla')
        self.assertEqual(de_resumido['dEmailRec'], 'cliente-ventanilla-fe@test.com')
        self.assertEqual(de_resumido['gPaConEIni'][0]['iTiPago'], '1')

    def test_es_idempotente_no_vuelve_a_llamar_a_la_api_si_ya_tiene_documento(self):
        DocumentoElectronico.objects.create(
            operacion_ventanilla=self.operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900',
        )
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            documento = emitir_documento_electronico(self.operacion)
        mock_post.assert_not_called()
        self.assertEqual(documento.operacion_ventanilla, self.operacion)

    def test_sin_email_del_cliente_no_llama_a_la_api_y_queda_pendiente(self):
        self.operacion.cliente_email = ''
        self.operacion.save(update_fields=['cliente_email'])
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            documento = emitir_documento_electronico(self.operacion)
        mock_post.assert_not_called()
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_ERROR_GENERACION)


class RegistrarOperacionVentanillaFacturaTest(TestCase):
    """Integración: registrar una operación de ventanilla desde la vista dispara su facturación."""

    def setUp(self):
        self.contador, _ = ContadorDocumentoElectronico.objects.update_or_create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            defaults={'desde': 900, 'hasta': 901, 'ultimo_asignado': None},
        )
        self.cajero = User.objects.create_user(username='cajero-fe-vista', password='password123')
        self.client.login(username='cajero-fe-vista', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
        self.caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=Divisa.objects.get(codigo='PYG'), monto=Decimal('10000000.00'))
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.usd, monto=Decimal('500.00'))

    def test_registrar_la_operacion_genera_su_factura_electronica(self):
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000900'}),
                _respuesta(code=0, results={'CDC': 'CDC-VISTA-1'}),
            ]
            self.client.post(
                reverse('caja:registrar_operacion', kwargs={'tipo': 'compra'}),
                {
                    'divisa': str(self.usd.pk), 'monto': '100.00',
                    'cliente_identificador': '4111222', 'cliente_nombre': 'Cliente Ventanilla',
                    'cliente_email': 'cliente-ventanilla-vista@test.com',
                },
            )

        operacion = OperacionVentanilla.objects.get()
        self.assertEqual(operacion.documento_electronico.cdc, 'CDC-VISTA-1')


class DescargarFacturaVentanillaViewTest(TestCase):
    """``DescargarFacturaVentanillaView``: solo el propio cajero, y solo una factura ya aprobada."""

    def setUp(self):
        self.cajero = User.objects.create_user(username='cajero-descarga', password='password123')
        self.client.login(username='cajero-descarga', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        caja = Caja.objects.create(usuario=self.cajero)
        self.operacion = OperacionVentanilla.objects.create(
            caja=caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_COMPRA,
            divisa=usd, monto_divisa=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_pyg=Decimal('747400.00'),
            cliente_identificador='4111222', cliente_nombre='Cliente Ventanilla',
            cliente_email='cliente-ventanilla-descarga@test.com',
        )
        self.url = reverse('caja:descargar_factura_operacion', kwargs={'pk': self.operacion.pk})

    def test_sin_documento_electronico_informa_el_motivo(self):
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, 'todavía no tiene ninguna factura electrónica')

    def test_factura_aprobada_se_descarga(self):
        documento = DocumentoElectronico.objects.create(
            operacion_ventanilla=self.operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', cdc='CDC-DESCARGA-1', estado=DocumentoElectronico.ESTADO_APROBADO,
        )
        with patch('apps.caja.views.descargar_kude') as mock_descargar:
            mock_descargar.return_value = b'%PDF-contenido-falso'
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'%PDF-contenido-falso')
        self.assertIn('CDC-DESCARGA-1', response['Content-Disposition'])
        mock_descargar.assert_called_once_with(documento)

    def test_factura_pendiente_de_generacion_no_se_descarga(self):
        DocumentoElectronico.objects.create(
            operacion_ventanilla=self.operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', estado=DocumentoElectronico.ESTADO_ERROR_GENERACION,
        )

        response = self.client.get(self.url, follow=True)

        self.assertContains(response, 'pendiente de generación')

    def test_otro_cajero_no_puede_descargar_la_factura_de_esta_operacion(self):
        User.objects.create_user(username='otro-cajero', password='password123')
        self.client.logout()
        self.client.login(username='otro-cajero', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()
        DocumentoElectronico.objects.create(
            operacion_ventanilla=self.operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', cdc='CDC-DESCARGA-3', estado=DocumentoElectronico.ESTADO_APROBADO,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_usuario_sin_rol_cajero_no_puede_acceder(self):
        self.client.logout()
        otro = User.objects.create_user(username='no-cajero', password='password123')
        self.client.login(username='no-cajero', password='password123')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)


class FacturasVentanillaListViewTest(TestCase):
    """``FacturasVentanillaListView``: el listado propio de facturas de ventanilla de un cajero."""

    def setUp(self):
        self.cajero = User.objects.create_user(username='cajero-lista-fe', password='password123')
        self.client.login(username='cajero-lista-fe', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.caja = Caja.objects.create(usuario=self.cajero)
        self.operacion = OperacionVentanilla.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_COMPRA,
            divisa=usd, monto_divisa=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_pyg=Decimal('747400.00'),
            cliente_identificador='4111222', cliente_nombre='Cliente Lista',
            cliente_email='cliente-lista-fe@test.com',
        )
        self.url = reverse('caja:facturas')

    def test_sin_ninguna_factura_muestra_el_mensaje_vacio(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Todavía no generaste ninguna factura electrónica en ventanilla.')

    def test_lista_la_propia_factura_de_ventanilla(self):
        DocumentoElectronico.objects.create(
            operacion_ventanilla=self.operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', cdc='CDC-LISTA-1', estado=DocumentoElectronico.ESTADO_APROBADO,
            emitida_en=timezone.now(),
        )

        response = self.client.get(self.url)

        self.assertContains(response, 'CDC-LISTA-1')
        self.assertContains(response, 'Cliente Lista')
        self.assertContains(response, reverse('caja:descargar_factura_operacion', kwargs={'pk': self.operacion.pk}))

    def test_no_muestra_facturas_de_otro_cajero_ni_de_transacciones_online(self):
        otro_cajero = User.objects.create_user(username='otro-cajero-lista', password='password123')
        otra_caja = Caja.objects.create(usuario=otro_cajero)
        otra_operacion = OperacionVentanilla.objects.create(
            caja=otra_caja, cajero=otro_cajero, tipo=OperacionVentanilla.TIPO_VENTA,
            divisa=self.operacion.divisa, monto_divisa=Decimal('50.00'), tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('3650.00'), monto_pyg=Decimal('361350.00'),
            cliente_identificador='4999999', cliente_nombre='Cliente Ajeno', cliente_email='ajeno@test.com',
        )
        DocumentoElectronico.objects.create(
            operacion_ventanilla=otra_operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', cdc='CDC-AJENO', estado=DocumentoElectronico.ESTADO_APROBADO,
        )

        response = self.client.get(self.url)

        self.assertNotContains(response, 'CDC-AJENO')
        self.assertNotContains(response, 'Cliente Ajeno')

    def test_filtra_por_fecha_de_emision(self):
        DocumentoElectronico.objects.create(
            operacion_ventanilla=self.operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', cdc='CDC-VIEJA', estado=DocumentoElectronico.ESTADO_APROBADO,
            emitida_en=timezone.now() - timezone.timedelta(days=30),
        )

        response = self.client.get(self.url, {'fecha_desde': timezone.now().date().isoformat()})

        self.assertNotContains(response, 'CDC-VIEJA')
        self.assertContains(response, 'No se encontraron facturas para el rango de fechas seleccionado.')

    def test_usuario_sin_rol_cajero_no_puede_acceder(self):
        self.client.logout()
        User.objects.create_user(username='no-cajero-lista', password='password123')
        self.client.login(username='no-cajero-lista', password='password123')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
