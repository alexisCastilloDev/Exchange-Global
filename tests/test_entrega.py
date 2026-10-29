"""Pruebas de la entrega al cliente (lo que recibe a cambio de un pago ya confirmado).

Cubre ``CuentaPropia`` (el saldo propio de Global Exchange, llevado en
esta misma base), ``apps.divisas.entrega`` (la transferencia saliente a
sipap-sim, seguida del ajuste del saldo propio y, para una compra o un
cambio entre divisas, el paso a "Acreditada" — HU "Acreditación de
fondos", GE-23 — o, para una venta, a "Retirada" — HU "Retiro de
fondos", GE-24, mismo mecanismo automático que una compra: se paga y se
recibe, sin ninguna acción extra del cliente), y las pantallas desde
las que se puede reintentar una entrega fallida: la administrativa
("Entregas pendientes") y el detalle de la propia transacción, para el
cliente.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente, MetodoPago
from apps.divisas.entrega import realizar_entrega, reintentar_entrega
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    CuentaPropia,
    CuentaPropiaInexistenteError,
    Divisa,
    SaldoInsuficienteError,
)

User = get_user_model()


def _respuesta(status_code, json_data=None):
    """Arma una respuesta de ``requests`` falsa, con ``raise_for_status`` funcionando de verdad."""
    respuesta = Mock(status_code=status_code)
    respuesta.json.return_value = json_data or {}
    if status_code >= 400:
        respuesta.raise_for_status.side_effect = requests.exceptions.HTTPError(response=respuesta)
    else:
        respuesta.raise_for_status.side_effect = None
    return respuesta


class AjustarSaldosTest(TestCase):
    """``CuentaPropia.ajustar_saldos``."""

    def setUp(self):
        """Prepara cuentas propias en PYG y USD."""
        # PYG ya tiene su cuenta propia creada por la migración de datos
        # (0021_cuenta_propia_por_divisa_existente): se actualiza en vez
        # de crearla de nuevo, para no chocar con esa fila.
        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.cuenta_pyg = CuentaPropia.objects.get(divisa=self.pyg)
        self.cuenta_pyg.saldo = Decimal('1000000.00')
        self.cuenta_pyg.save(update_fields=['saldo'])
        self.cuenta_usd = CuentaPropia.objects.create(divisa=self.usd, saldo=Decimal('500.00'))

    def test_acredita_lo_recibido_y_debita_lo_entregado(self):
        CuentaPropia.ajustar_saldos(
            divisa_recibir=self.pyg, monto_recibir=Decimal('747400.00'),
            divisa_entregar=self.usd, monto_entregar=Decimal('100.00'),
        )

        self.cuenta_pyg.refresh_from_db()
        self.cuenta_usd.refresh_from_db()
        self.assertEqual(self.cuenta_pyg.saldo, Decimal('1747400.00'))
        self.assertEqual(self.cuenta_usd.saldo, Decimal('400.00'))

    def test_rechaza_si_no_hay_saldo_suficiente_para_entregar_sin_tocar_nada(self):
        with self.assertRaises(SaldoInsuficienteError):
            CuentaPropia.ajustar_saldos(
                divisa_recibir=self.pyg, monto_recibir=Decimal('747400.00'),
                divisa_entregar=self.usd, monto_entregar=Decimal('1000.00'),
            )

        self.cuenta_pyg.refresh_from_db()
        self.cuenta_usd.refresh_from_db()
        self.assertEqual(self.cuenta_pyg.saldo, Decimal('1000000.00'))
        self.assertEqual(self.cuenta_usd.saldo, Decimal('500.00'))

    def test_rechaza_con_mensaje_claro_si_falta_la_cuenta_propia_de_una_divisa(self):
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        with self.assertRaises(CuentaPropiaInexistenteError):
            CuentaPropia.ajustar_saldos(
                divisa_recibir=self.pyg, monto_recibir=Decimal('100.00'),
                divisa_entregar=eur, monto_entregar=Decimal('10.00'),
            )


class RealizarEntregaTest(TestCase):
    """``apps.divisas.entrega.realizar_entrega``."""

    def setUp(self):
        """Prepara un cliente, una compra 'Pagada', un medio de destino en USD y las cuentas propias."""
        usuario = User.objects.create_user(username='cliente-entrega', password='password123')
        self.cliente = Cliente.objects.create(
            user=usuario, identificador='ENTREGA-001', nombre='Cliente', apellido='Entrega',
            email='cliente-entrega@test.com', is_active=True,
        )
        # Ver AjustarSaldosTest.setUp: PYG ya tiene cuenta propia creada
        # por la migración de datos, se actualiza en vez de crearla.
        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.cuenta_pyg = CuentaPropia.objects.get(divisa=self.pyg)
        self.cuenta_pyg.saldo = Decimal('10000000.00')
        self.cuenta_pyg.save(update_fields=['saldo'])
        self.cuenta_usd = CuentaPropia.objects.create(divisa=self.usd, saldo=Decimal('1000.00'))
        self.medio_destino = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Cliente Entrega',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000000999', documento_titular='1234567',
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

    def test_entrega_exitosa_segun_el_tipo_de_transaccion(self):
        """Una compra o un cambio quedan 'Acreditada' (GE-23); una venta, 'Retirada' (GE-24)."""
        with self.subTest('compra'):
            antes = timezone.now()
            with patch('apps.divisas.entrega.requests.post') as mock_post:
                mock_post.return_value = _respuesta(201, {'id': 'SPI-1', 'estado': 'acreditada'})
                resultado = realizar_entrega(self.transaccion)
                kwargs = mock_post.call_args.kwargs

            self.assertTrue(resultado)
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ACREDITADA)
            self.assertIsNotNone(self.transaccion.acreditado_en)
            self.assertGreaterEqual(self.transaccion.acreditado_en, antes)
            self.assertEqual(self.transaccion.referencia_acreditacion, f'ENTREGA-OPERACION-{self.transaccion.pk}')
            self.cuenta_pyg.refresh_from_db()
            self.cuenta_usd.refresh_from_db()
            self.assertEqual(self.cuenta_pyg.saldo, Decimal('10747400.00'))
            self.assertEqual(self.cuenta_usd.saldo, Decimal('900.00'))
            self.assertEqual(kwargs['json']['cuenta_destino'], self.medio_destino.numero_cuenta)
            self.assertEqual(kwargs['json']['documento'], self.medio_destino.documento_titular)
            self.assertEqual(kwargs['json']['monto'], '100.00')
            self.assertEqual(kwargs['json']['referencia'], f'ENTREGA-OPERACION-{self.transaccion.pk}')

        with self.subTest('venta'):
            medio_destino_pyg = MetodoPago.objects.create(
                cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TRANSFERENCIA, nombre_titular='Cliente Entrega',
                entidad_financiera='Banco Itaú', numero_cuenta='2000000000000111', documento_titular='1234567',
                moneda=self.pyg,
            )
            venta = CalculoOperacion.objects.create(
                usuario=self.transaccion.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_VENTA,
                divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
                tasa_aplicada=Decimal('7300.00'), comision_porcentaje=Decimal('1.000'),
                comision=Decimal('73.00'), monto_final=Decimal('747400.00'), estado=CalculoOperacion.ESTADO_PAGADA,
                vence_en=timezone.now() + timedelta(seconds=300), confirmado_en=timezone.now(),
                medio_destino=medio_destino_pyg,
            )
            antes = timezone.now()
            with patch('apps.divisas.entrega.requests.post') as mock_post:
                mock_post.return_value = _respuesta(201, {'id': 'SPI-VENTA', 'estado': 'acreditada'})
                resultado = realizar_entrega(venta)

            self.assertTrue(resultado)
            venta.refresh_from_db()
            self.assertEqual(venta.estado, CalculoOperacion.ESTADO_RETIRADA)
            self.assertIsNotNone(venta.retirado_en)
            self.assertGreaterEqual(venta.retirado_en, antes)
            self.assertEqual(venta.referencia_retiro, f'ENTREGA-OPERACION-{venta.pk}')
            self.assertIsNone(venta.acreditado_en)
            self.assertEqual(venta.referencia_acreditacion, '')

        with self.subTest('cambio'):
            eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
            CuentaPropia.objects.create(divisa=eur, saldo=Decimal('500.00'))
            cambio = CalculoTriangulacion.objects.create(
                usuario=self.transaccion.usuario, cliente=self.cliente,
                divisa_origen=self.usd, divisa_destino=eur, codigo_divisa_origen='USD', codigo_divisa_destino='EUR',
                monto_origen=Decimal('100.00'), tasa_compra_aplicada=Decimal('7300.00'),
                tasa_venta_aplicada=Decimal('8100.00'), tasa_cruzada=Decimal('0.901235'),
                monto_equivalente_pyg=Decimal('730000.00'), comision_porcentaje=Decimal('1.000'),
                comision=Decimal('0.90'), monto_final=Decimal('89.22'), estado=CalculoTriangulacion.ESTADO_PAGADA,
                vence_en=timezone.now() + timedelta(seconds=300), confirmado_en=timezone.now(),
                medio_destino=self.medio_destino,
            )
            with patch('apps.divisas.entrega.requests.post') as mock_post:
                mock_post.return_value = _respuesta(201, {'id': 'SPI-CAMBIO', 'estado': 'acreditada'})
                resultado = realizar_entrega(cambio)

            self.assertTrue(resultado)
            cambio.refresh_from_db()
            self.assertEqual(cambio.estado, CalculoTriangulacion.ESTADO_ACREDITADA)
            self.assertIsNotNone(cambio.acreditado_en)
            self.assertEqual(cambio.referencia_acreditacion, f'ENTREGA-CAMBIO-{cambio.pk}')

    def test_fallas_en_la_entrega_pasan_a_entrega_fallida_sin_tocar_el_saldo(self):
        """Sin medio de destino, sipap-sim caído, rechazando, o sin saldo propio: siempre 'Entrega fallida'."""
        with self.subTest('sin medio de destino'):
            self.transaccion.medio_destino = None
            self.transaccion.save(update_fields=['medio_destino'])
            with patch('apps.divisas.entrega.requests.post') as mock_post:
                resultado = realizar_entrega(self.transaccion)
                mock_post.assert_not_called()

            self.assertFalse(resultado)
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)
            self.cuenta_usd.refresh_from_db()
            self.assertEqual(self.cuenta_usd.saldo, Decimal('1000.00'))
            # Se restaura para los casos siguientes, que sí necesitan un medio de destino.
            self.transaccion.medio_destino = self.medio_destino
            self.transaccion.save(update_fields=['medio_destino'])

        with self.subTest('sipap-sim no responde'):
            with patch('apps.divisas.entrega.requests.post') as mock_post:
                mock_post.side_effect = requests.exceptions.ConnectionError('sipap-sim caído')
                resultado = realizar_entrega(self.transaccion)

            self.assertFalse(resultado)
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)
            self.cuenta_usd.refresh_from_db()
            self.assertEqual(self.cuenta_usd.saldo, Decimal('1000.00'))

        with self.subTest('sipap-sim rechaza la transferencia'):
            with patch('apps.divisas.entrega.requests.post') as mock_post:
                mock_post.return_value = _respuesta(
                    404, {'detalle': 'No se encontró una cuenta con ese número y documento.'},
                )
                resultado = realizar_entrega(self.transaccion)

            self.assertFalse(resultado)
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)
            self.cuenta_usd.refresh_from_db()
            self.assertEqual(self.cuenta_usd.saldo, Decimal('1000.00'))

        with self.subTest('la transferencia ya salió pero no hay saldo propio'):
            # La transferencia a sipap-sim ya ocurrió (es real); lo que falla es solo el espejo interno.
            self.cuenta_usd.saldo = Decimal('1.00')
            self.cuenta_usd.save(update_fields=['saldo'])
            with patch('apps.divisas.entrega.requests.post') as mock_post:
                mock_post.return_value = _respuesta(201, {'id': 'SPI-1', 'estado': 'acreditada'})
                resultado = realizar_entrega(self.transaccion)
                mock_post.assert_called_once()

            self.assertFalse(resultado)
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)

    @patch('apps.divisas.entrega.requests.post')
    def test_la_referencia_es_siempre_la_misma_entre_llamadas(self, mock_post):
        """La idempotencia del lado de sipap-sim depende de que la referencia nunca cambie entre reintentos."""
        mock_post.return_value = _respuesta(201, {'id': 'SPI-1', 'estado': 'acreditada'})

        realizar_entrega(self.transaccion)
        primera_referencia = mock_post.call_args.kwargs['json']['referencia']

        self.transaccion.estado = CalculoOperacion.ESTADO_PAGADA
        self.transaccion.save(update_fields=['estado'])
        realizar_entrega(self.transaccion)
        segunda_referencia = mock_post.call_args.kwargs['json']['referencia']

        self.assertEqual(primera_referencia, segunda_referencia)


class EntregasPendientesListViewTest(TestCase):
    """Verifica la pantalla administrativa de entregas fallidas pendientes de reintentar."""

    def setUp(self):
        """Prepara un administrador y una compra en 'Entrega fallida'."""
        self.admin = User.objects.create_user(username='admin-entregas', password='password123')
        self.client.login(username='admin-entregas', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        usuario = User.objects.create_user(username='cliente-entregas-pend', password='password123')
        self.cliente = Cliente.objects.create(
            user=usuario, identificador='ENTREGA-PEND-001', nombre='Cliente', apellido='Pendiente',
            email='cliente-entregas-pend@test.com', is_active=True,
        )
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.medio_destino = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Cliente Pendiente',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000000888', documento_titular='7654321',
            moneda=self.usd,
        )
        self.transaccion = CalculoOperacion.objects.create(
            usuario=usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_ENTREGA_FALLIDA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=self.medio_destino,
        )
        self.url = reverse('divisas:entregas_pendientes')

    def test_la_lista_muestra_solo_las_entregas_fallidas(self):
        """Una entrega fallida aparece con su botón de reintentar; una ya resuelta, no."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.cliente))
        self.assertContains(response, 'Reintentar')

        self.transaccion.estado = CalculoOperacion.ESTADO_PAGADA
        self.transaccion.save(update_fields=['estado'])
        response = self.client.get(self.url)
        self.assertNotContains(response, str(self.cliente))

    def test_un_cliente_no_puede_acceder(self):
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)


class ReintentarEntregaViewTest(TestCase):
    """Verifica el reintento administrativo de una entrega fallida."""

    def setUp(self):
        """Prepara un administrador y una compra en 'Entrega fallida'."""
        self.admin = User.objects.create_user(username='admin-reintento', password='password123')
        self.client.login(username='admin-reintento', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        usuario = User.objects.create_user(username='cliente-reintento', password='password123')
        self.cliente = Cliente.objects.create(
            user=usuario, identificador='REINTENTO-001', nombre='Cliente', apellido='Reintento',
            email='cliente-reintento@test.com', is_active=True,
        )
        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.cuenta_pyg = CuentaPropia.objects.get(divisa=self.pyg)
        self.cuenta_pyg.saldo = Decimal('10000000.00')
        self.cuenta_pyg.save(update_fields=['saldo'])
        self.cuenta_usd = CuentaPropia.objects.create(divisa=self.usd, saldo=Decimal('1000.00'))
        self.medio_destino = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Cliente Reintento',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000000777', documento_titular='1112223',
            moneda=self.usd,
        )
        self.transaccion = CalculoOperacion.objects.create(
            usuario=usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_ENTREGA_FALLIDA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=self.medio_destino,
        )
        self.url = reverse('divisas:reintentar_entrega', kwargs={'tipo': 'operacion', 'pk': self.transaccion.pk})

    @patch('apps.divisas.entrega.requests.post')
    def test_reintentar_con_exito_completa_la_entrega_y_mantiene_la_misma_referencia(self, mock_post):
        mock_post.return_value = _respuesta(201, {'id': 'SPI-REINTENTO', 'estado': 'acreditada'})

        response = self.client.post(self.url, follow=True)

        self.assertContains(response, 'se reintentó con éxito')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ACREDITADA)
        self.assertIsNotNone(self.transaccion.acreditado_en)
        primera_referencia = mock_post.call_args.kwargs['json']['referencia']

        # Un segundo reintento (doble clic, o una entrega fallida posterior) nunca
        # genera una referencia distinta: sipap-sim la reconoce como la misma.
        self.transaccion.estado = CalculoOperacion.ESTADO_ENTREGA_FALLIDA
        self.transaccion.save(update_fields=['estado'])
        mock_post.return_value = _respuesta(201, {'id': 'SPI-REINTENTO-2', 'estado': 'acreditada'})
        self.client.post(self.url)
        segunda_referencia = mock_post.call_args.kwargs['json']['referencia']

        self.assertEqual(primera_referencia, segunda_referencia)

    @patch('apps.divisas.entrega.requests.post')
    def test_reintentar_que_vuelve_a_fallar_queda_igual(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError('sipap-sim caído')

        response = self.client.post(self.url, follow=True)

        self.assertContains(response, 'volvió a fallar')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)

    def test_un_cliente_no_puede_reintentar(self):
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)


class ReintentarEntregaHelperTest(TestCase):
    """Verifica directamente ``apps.divisas.entrega.reintentar_entrega``."""

    def setUp(self):
        """Prepara una compra ya 'Pagada' (sin entrega fallida)."""
        usuario = User.objects.create_user(username='cliente-helper-reintento', password='password123')
        self.cliente = Cliente.objects.create(
            user=usuario, identificador='HELPER-REINTENTO-001', nombre='Cliente', apellido='Helper',
            email='cliente-helper-reintento@test.com', is_active=True,
        )
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.medio_destino = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Cliente Helper',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000000444', documento_titular='4445556',
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

    def test_devuelve_none_si_la_transaccion_no_esta_en_entrega_fallida(self):
        """Nada que reintentar: no debe tocar el estado ni llamar a sipap-sim."""
        with patch('apps.divisas.entrega.requests.post') as mock_post:
            resultado = reintentar_entrega(self.transaccion)

        self.assertIsNone(resultado)
        mock_post.assert_not_called()
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)


class ReintentarEntregaClienteTest(TestCase):
    """Verifica que el propio cliente pueda reintentar la entrega desde el detalle de su transacción."""

    def setUp(self):
        """Prepara un cliente logueado, dueño de una compra en 'Entrega fallida'."""
        self.usuario = User.objects.create_user(username='cliente-detalle-reintento', password='password123')
        self.cliente = Cliente.objects.create(
            user=self.usuario, identificador='DETALLE-REINT-001', nombre='Cliente', apellido='Detalle',
            email='cliente-detalle-reintento@test.com', is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.client.login(username='cliente-detalle-reintento', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.cuenta_pyg = CuentaPropia.objects.get(divisa=self.pyg)
        self.cuenta_pyg.saldo = Decimal('10000000.00')
        self.cuenta_pyg.save(update_fields=['saldo'])
        self.cuenta_usd = CuentaPropia.objects.create(divisa=self.usd, saldo=Decimal('1000.00'))
        self.medio_destino = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Cliente Detalle',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000000333', documento_titular='3334445',
            moneda=self.usd,
        )
        self.transaccion = CalculoOperacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_ENTREGA_FALLIDA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=self.medio_destino,
        )
        self.url = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.transaccion.pk})

    @patch('apps.divisas.entrega.requests.post')
    def test_el_cliente_puede_reintentar_su_propia_entrega_fallida(self, mock_post):
        mock_post.return_value = _respuesta(201, {'id': 'SPI-CLIENTE', 'estado': 'acreditada'})

        response = self.client.post(self.url, follow=True)

        self.assertContains(response, 'se reintentó con éxito')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ACREDITADA)

    @patch('apps.divisas.entrega.requests.post')
    def test_si_vuelve_a_fallar_queda_igual_y_se_informa(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError('sipap-sim caído')

        response = self.client.post(self.url, follow=True)

        self.assertContains(response, 'volvió a fallar')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)

    def test_no_puede_reintentar_una_transaccion_de_otro_cliente(self):
        """Ownership real: ni siquiera puede verla, mucho menos reintentarla."""
        otro_usuario = User.objects.create_user(username='otro-cliente-detalle', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario, identificador='OTRO-DETALLE-001', nombre='Otro', apellido='Cliente',
            email='otro-cliente-detalle@test.com', is_active=True,
        )
        otro_usuario.clientes.add(otro_cliente)
        self.client.logout()
        self.client.login(username='otro-cliente-detalle', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 404)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)
