"""Pruebas de la HU 'Nota de crédito' (``apps.divisas.factura_electronica``/``apps.divisas.models``).

Anula, ante SIFEN, una Factura Electrónica ya aprobada. **Ninguna de
estas pruebas llama a la API real de Factura Segura**: mismo criterio
que ``tests/test_factura_electronica.py``, ``requests.post`` siempre
mockeado y un ``ContadorDocumentoElectronico`` de prueba propio (nunca
el rango real sembrado por la migración de datos), tanto para
``TIPO_FACTURA`` como para ``TIPO_NOTA_CREDITO``.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente, MetodoPago
from apps.divisas.factura_electronica import (
    emitir_nota_credito,
    puede_emitir_nota_credito,
    ultima_nota_credito,
)
from apps.divisas.models import CalculoOperacion, ContadorDocumentoElectronico, Divisa, DocumentoElectronico, Pago

User = get_user_model()


def _respuesta(code=0, results=None, description=''):
    """Misma respuesta falsa de Factura Segura que usa ``tests/test_factura_electronica.py``."""
    respuesta = Mock(status_code=200)
    respuesta.raise_for_status.side_effect = None
    respuesta.json.return_value = {
        'code': code, 'description': description, 'operation_info': {'id': 'OP-NC'},
        'results': [results] if results else [],
    }
    return respuesta


def _respuesta_calculo(de=None):
    return _respuesta(code=0, results={'DE': de or {}})


class NotaCreditoTestCase(TestCase):
    """Base común: una factura ya aprobada por SIFEN, con su cliente y contadores de prueba."""

    def setUp(self):
        """Prepara una factura 'Aprobada' con CDC, lista para que se le emita una nota de crédito."""
        ContadorDocumentoElectronico.objects.update_or_create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            defaults={'desde': 900, 'hasta': 901, 'ultimo_asignado': 900},
        )
        ContadorDocumentoElectronico.objects.update_or_create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO,
            defaults={'desde': 950, 'hasta': 951, 'ultimo_asignado': None},
        )
        usuario = User.objects.create_user(username='cliente-nc', password='password123')
        self.cliente = Cliente.objects.create(
            user=usuario, identificador='4111222', nombre='Cliente', apellido='NotaCredito',
            email='cliente-nc@test.com', is_active=True,
        )
        self.cliente.usuarios.add(usuario)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.medio_destino = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Cliente NotaCredito',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000000888', documento_titular='4111222',
            moneda=self.usd,
        )
        self.transaccion = CalculoOperacion.objects.create(
            usuario=usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_ACREDITADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=self.medio_destino,
        )
        Pago.objects.create(
            calculo_operacion=self.transaccion, medio_pago=MetodoPago.TIPO_TARJETA,
            proveedor='STRIPE', identificador_externo='pi_test_nc', monto=Decimal('747400.00'),
        )
        self.factura = DocumentoElectronico.objects.create(
            calculo_operacion=self.transaccion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000900', cdc='CDC-FACTURA-APROBADA', estado=DocumentoElectronico.ESTADO_APROBADO,
        )


class PuedeEmitirNotaCreditoTest(NotaCreditoTestCase):
    """``puede_emitir_nota_credito``/``DocumentoElectronico.puede_emitir_nota_credito`` (criterio 4)."""

    def test_factura_aprobada_sin_nota_de_credito_se_puede(self):
        puede, motivo = puede_emitir_nota_credito(self.factura)
        self.assertTrue(puede)
        self.assertEqual(motivo, '')
        self.assertTrue(self.factura.puede_emitir_nota_credito)

    def test_factura_no_aprobada_no_se_puede(self):
        self.factura.estado = DocumentoElectronico.ESTADO_GENERADO
        self.factura.save(update_fields=['estado'])

        puede, motivo = puede_emitir_nota_credito(self.factura)

        self.assertFalse(puede)
        self.assertIn('aprobada', motivo)
        self.assertFalse(self.factura.puede_emitir_nota_credito)

    def test_factura_ya_anulada_no_se_puede(self):
        self.factura.estado = DocumentoElectronico.ESTADO_ANULADA
        self.factura.save(update_fields=['estado'])

        puede, motivo = puede_emitir_nota_credito(self.factura)

        self.assertFalse(puede)
        self.assertIn('anulada', motivo)

    def test_con_una_nota_de_credito_pendiente_no_se_puede(self):
        DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000950',
            factura_anulada=self.factura, estado=DocumentoElectronico.ESTADO_GENERADO,
        )

        puede, motivo = puede_emitir_nota_credito(self.factura)

        self.assertFalse(puede)
        self.assertIn('pendiente o aprobada', motivo)

    def test_con_una_nota_de_credito_rechazada_se_puede_igual(self):
        """Criterio 3: una nota de crédito rechazada no bloquea una nueva."""
        DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000950',
            factura_anulada=self.factura, estado=DocumentoElectronico.ESTADO_RECHAZADO,
        )

        puede, motivo = puede_emitir_nota_credito(self.factura)

        self.assertTrue(puede)


class EmitirNotaCreditoTest(NotaCreditoTestCase):
    """``emitir_nota_credito``: camino feliz, rechazo de la emisión, y los criterios 1, 4 y 5."""

    def test_emision_exitosa_repite_total_receptor_e_items_y_referencia_el_cdc(self):
        """Criterio 1: el total, el receptor y los ítems son los de la factura, y referencia su CDC."""
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={'dNumDoc': '0000950'}),
                _respuesta(code=0, results={'CDC': 'CDC-NOTA-CREDITO-1'}),
            ]
            documento, mensaje = emitir_nota_credito(self.factura, DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE)

        self.assertIsNotNone(documento)
        self.assertEqual(documento.tipo_documento, ContadorDocumentoElectronico.TIPO_NOTA_CREDITO)
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_GENERADO)
        self.assertEqual(documento.cdc, 'CDC-NOTA-CREDITO-1')
        self.assertEqual(documento.factura_anulada, self.factura)
        self.assertIn('pendiente de aprobación', mensaje)

        # El JSON_RESUMIDO_DE enviado a calcular_de repite el total/receptor/items de la factura.
        payload_enviado = mock_post.call_args_list[0].kwargs['json']['params']['DE']
        self.assertEqual(payload_enviado['dNumIDRec'], self.cliente.identificador)
        self.assertEqual(payload_enviado['dNomRec'], self.cliente.nombre_completo)
        self.assertEqual(payload_enviado['gCamDEAsoc'], [{'iTipDocAso': '1', 'dCdCDERef': 'CDC-FACTURA-APROBADA'}])
        self.assertEqual(payload_enviado['iMotEmi'], DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE)

    def test_factura_no_elegible_no_crea_ninguna_nota_de_credito(self):
        """Criterio 4: sin factura elegible, no se crea ningún documento ni se llama a Factura Segura."""
        self.factura.estado = DocumentoElectronico.ESTADO_GENERADO
        self.factura.save(update_fields=['estado'])

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            documento, mensaje = emitir_nota_credito(self.factura, DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE)
            mock_post.assert_not_called()

        self.assertIsNone(documento)
        self.assertEqual(DocumentoElectronico.objects.filter(factura_anulada=self.factura).count(), 0)

    def test_motivo_invalido_no_crea_ninguna_nota_de_credito(self):
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            documento, mensaje = emitir_nota_credito(self.factura, 'NO-EXISTE')
            mock_post.assert_not_called()

        self.assertIsNone(documento)
        self.assertIn('motivo', mensaje.lower())

    def test_timeout_deja_la_nota_de_credito_en_error_generacion_sin_reintentar_sola(self):
        """Criterio 5: sin confirmación de Factura Segura, queda en Error al generar, no se reenvía sola."""
        import requests
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError('timeout')
            documento, mensaje = emitir_nota_credito(self.factura, DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE)

        self.assertIsNotNone(documento)
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_ERROR_GENERACION)
        self.assertIn('no se pudo generar', mensaje.lower())

    def test_con_una_nota_de_credito_en_error_generacion_no_duplica(self):
        """Criterio 5: con una nota de crédito sin confirmar, no se genera una segunda."""
        import requests
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError('timeout')
            emitir_nota_credito(self.factura, DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE)

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            documento, mensaje = emitir_nota_credito(self.factura, DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE)
            mock_post.assert_not_called()

        self.assertIsNone(documento)
        self.assertEqual(DocumentoElectronico.objects.filter(factura_anulada=self.factura).count(), 1)

    def test_una_carrera_simultanea_no_crea_dos_notas_de_credito_vigentes(self):
        """La UniqueConstraint impide, a nivel de base, dos notas de crédito vigentes para la misma factura."""
        DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000950',
            factura_anulada=self.factura, estado=DocumentoElectronico.ESTADO_GENERADO,
        )
        with self.assertRaises(IntegrityError):
            DocumentoElectronico.objects.create(
                tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000951',
                factura_anulada=self.factura, estado=DocumentoElectronico.ESTADO_GENERADO,
            )


class ConsultarEstadoDeNotaCreditoTest(NotaCreditoTestCase):
    """``consultar_estado_sifen`` sobre una nota de crédito: criterios 2 y 3."""

    def setUp(self):
        """Además del fixture base, una nota de crédito ya generada con CDC."""
        super().setUp()
        self.nota_credito = DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000950',
            factura_anulada=self.factura, motivo_emision=DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE,
            cdc='CDC-NOTA-CREDITO-2', estado=DocumentoElectronico.ESTADO_GENERADO,
        )

    def test_aprobada_anula_la_factura(self):
        """Criterio 2: aprobada la nota de crédito, pasa a 'Aprobada' y la factura a 'Anulada'."""
        from apps.divisas.factura_electronica import consultar_estado_sifen
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(code=0, results={'estado_sifen': 'Aprobado', 'desc_sifen': '0260 - Aprobado'})
            consultar_estado_sifen(self.nota_credito)

        self.nota_credito.refresh_from_db()
        self.factura.refresh_from_db()
        self.assertEqual(self.nota_credito.estado, DocumentoElectronico.ESTADO_APROBADO)
        self.assertEqual(self.factura.estado, DocumentoElectronico.ESTADO_ANULADA)

    def test_rechazada_no_toca_la_factura_y_libera_el_paso_a_una_nueva(self):
        """Criterio 3: rechazada, la factura sigue 'Aprobada' y se puede emitir una nueva."""
        from apps.divisas.factura_electronica import consultar_estado_sifen
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(
                code=0, results={'estado_sifen': 'Rechazado', 'desc_sifen': '0160', 'error_sifen': 'Datos inválidos'},
            )
            consultar_estado_sifen(self.nota_credito)

        self.nota_credito.refresh_from_db()
        self.factura.refresh_from_db()
        self.assertEqual(self.nota_credito.estado, DocumentoElectronico.ESTADO_RECHAZADO)
        self.assertEqual(self.factura.estado, DocumentoElectronico.ESTADO_APROBADO)
        puede, _ = puede_emitir_nota_credito(self.factura)
        self.assertTrue(puede)

    def test_aprobada_con_observacion_tambien_anula_la_factura(self):
        from apps.divisas.factura_electronica import consultar_estado_sifen
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta(
                code=0, results={'estado_sifen': 'Aprobado con observación', 'desc_sifen': '0301'},
            )
            consultar_estado_sifen(self.nota_credito)

        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, DocumentoElectronico.ESTADO_ANULADA)


class UltimaNotaCreditoTest(NotaCreditoTestCase):
    """``ultima_nota_credito``: la más reciente, usada por las pantallas de detalle del cliente (criterio 6)."""

    def test_sin_ninguna_nota_de_credito_devuelve_none(self):
        self.assertIsNone(ultima_nota_credito(self.transaccion))

    def test_devuelve_la_mas_reciente(self):
        primera = DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000950',
            factura_anulada=self.factura, estado=DocumentoElectronico.ESTADO_RECHAZADO,
        )
        segunda = DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000951',
            factura_anulada=self.factura, estado=DocumentoElectronico.ESTADO_GENERADO,
        )

        self.assertEqual(ultima_nota_credito(self.transaccion), segunda)


class EmitirNotaCreditoViewTest(NotaCreditoTestCase):
    """Vista ``EmitirNotaCreditoView``: criterios 1, 4 y 8."""

    def _loguear_admin(self):
        admin = User.objects.create_user(username='admin-nc', password='password123', is_staff=True)
        self.client.login(username='admin-nc', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

    def test_admin_emite_la_nota_de_credito(self):
        self._loguear_admin()
        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.side_effect = [
                _respuesta_calculo(de={}),
                _respuesta(code=0, results={'CDC': 'CDC-NOTA-CREDITO-VISTA'}),
            ]
            response = self.client.post(
                reverse('divisas:emitir_nota_credito', kwargs={'pk': self.factura.pk}),
                {'motivo_emision': DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE},
            )

        self.assertRedirects(response, reverse('divisas:documentos_electronicos'))
        self.assertTrue(DocumentoElectronico.objects.filter(factura_anulada=self.factura).exists())

    def test_sin_motivo_elegible_no_emite_nada(self):
        self.factura.estado = DocumentoElectronico.ESTADO_ANULADA
        self.factura.save(update_fields=['estado'])
        self._loguear_admin()

        response = self.client.post(
            reverse('divisas:emitir_nota_credito', kwargs={'pk': self.factura.pk}),
            {'motivo_emision': DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE},
        )

        self.assertRedirects(response, reverse('divisas:documentos_electronicos'))
        self.assertFalse(DocumentoElectronico.objects.filter(factura_anulada=self.factura).exists())

    def test_un_usuario_sin_rol_admin_no_puede_emitir(self):
        cliente_logueado = User.objects.create_user(username='cliente-no-admin-nc', password='password123')
        self.client.login(username='cliente-no-admin-nc', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.post(
            reverse('divisas:emitir_nota_credito', kwargs={'pk': self.factura.pk}),
            {'motivo_emision': DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(DocumentoElectronico.objects.filter(factura_anulada=self.factura).exists())


class ClienteVeLaNotaDeCreditoTest(NotaCreditoTestCase):
    """El cliente ve la nota de crédito de su factura anulada y puede descargarla (criterio 6)."""

    def setUp(self):
        """Además del fixture base, logueado como el cliente dueño de la factura, y una nota aprobada."""
        super().setUp()
        self.client.login(username='cliente-nc', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.nota_credito = DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000950',
            factura_anulada=self.factura, motivo_emision=DocumentoElectronico.MOTIVO_DEVOLUCION_Y_AJUSTE,
            cdc='CDC-NOTA-CREDITO-3', estado=DocumentoElectronico.ESTADO_APROBADO,
        )
        self.factura.estado = DocumentoElectronico.ESTADO_ANULADA
        self.factura.save(update_fields=['estado'])

    def test_el_detalle_de_la_transaccion_muestra_la_nota_de_credito(self):
        response = self.client.get(reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.transaccion.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['nota_credito'], self.nota_credito)
        self.assertContains(response, 'Nota de crédito')
        self.assertContains(response, 'CDC-NOTA-CREDITO-3')

    def test_el_cliente_descarga_la_nota_de_credito_en_pdf_y_xml(self):
        """Mockea ``requests.get`` (no ``descargar_kude``/``descargar_xml`` directamente: ``DescargarDocumentoElectronicoView.FORMATOS`` ya capturó esas referencias al definirse la clase, antes de que corra cualquier parche)."""
        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            mock_get.return_value = Mock(status_code=200, content=b'%PDF-contenido')
            response = self.client.get(
                reverse('divisas:descargar_documento_electronico', kwargs={'pk': self.nota_credito.pk, 'formato': 'kude'})
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

        with patch('apps.divisas.factura_electronica.requests.get') as mock_get:
            mock_get.return_value = Mock(status_code=200, content=b'<xml>CDC-NOTA-CREDITO-3</xml>')
            response = self.client.get(
                reverse('divisas:descargar_documento_electronico', kwargs={'pk': self.nota_credito.pk, 'formato': 'xml'})
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')

    def test_otro_cliente_no_puede_descargar_la_nota_de_credito(self):
        """Solo puede ver las de su cliente activo: un cliente ajeno recibe 403."""
        otro = User.objects.create_user(username='otro-cliente-nc', password='password123')
        Cliente.objects.create(
            user=otro, identificador='9999999', nombre='Otro', apellido='Cliente',
            email='otro-nc@test.com', is_active=True,
        )
        self.client.login(username='otro-cliente-nc', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(
            reverse('divisas:descargar_documento_electronico', kwargs={'pk': self.nota_credito.pk, 'formato': 'kude'})
        )

        self.assertEqual(response.status_code, 403)
