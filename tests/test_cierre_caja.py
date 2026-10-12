"""Pruebas de la HU 'Cierre de Caja'."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.caja.models import ArqueoCaja, Caja, MovimientoExtraordinario, OperacionVentanilla, SaldoInicialCaja
from apps.divisas.models import Cotizacion, Divisa

User = get_user_model()


class CerrarCajaTest(TestCase):
    """Verifica los criterios de aceptación de la HU 'Cierre de Caja'."""

    def setUp(self):
        """Prepara un cajero logueado, USD cotizado y una caja abierta con saldo.

        PYG ya existe de antemano: la migración de datos
        ``apps.divisas.0014_crear_divisa_pyg`` la garantiza como moneda
        local/base del sistema.
        """
        self.cajero = User.objects.create_user(username='cajero-cierre', password='password123')
        self.client.login(username='cajero-cierre', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))

        self.caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.pyg, monto=Decimal('1000000.00'))
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.usd, monto=Decimal('200.00'))

        self.url_cerrar = reverse('caja:cerrar')
        self.url_panel = reverse('caja:panel')

    def _registrar_arqueo(self):
        """Registra un arqueo cualquiera para la caja de prueba, sin pasar por la vista."""
        return ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)

    # --- Criterio 1 ---

    def test_el_resumen_muestra_saldo_inicial_operaciones_movimientos_y_saldo_final(self):
        """Criterio 1: el resumen del turno muestra saldo inicial, operaciones, movimientos y saldo final."""
        OperacionVentanilla.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_COMPRA,
            divisa=self.usd, monto_divisa=Decimal('50.00'), tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.00'), comision=Decimal('3650.00'), monto_pyg=Decimal('361350.00'),
        )
        MovimientoExtraordinario.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=MovimientoExtraordinario.TIPO_EGRESO,
            divisa=self.usd, monto=Decimal('10.00'), motivo='Pago de un servicio',
        )

        response = self.client.get(self.url_cerrar)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Saldo inicial')
        self.assertContains(response, 'Saldo final')
        self.assertContains(response, '200,00')  # saldo inicial USD (formato "." miles, "," decimales)
        # Saldo final USD: 200.00 + 50.00 (compra) - 10.00 (egreso extraordinario) = 240.00
        self.assertContains(response, '240,00')
        self.assertContains(response, 'Pago de un servicio')
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('240.00'))

    def test_sin_caja_abierta_no_hay_nada_que_cerrar(self):
        """Sin una caja abierta, la vista redirige al panel en vez de mostrar un resumen."""
        self.caja.delete()

        response = self.client.get(self.url_cerrar, follow=True)

        self.assertContains(response, 'No tenés una caja abierta para cerrar')

    # --- Criterio 2 ---

    def test_confirmar_el_cierre_pasa_la_caja_a_cerrada_con_fecha_y_hora(self):
        """Criterio 2: al confirmar, la caja pasa a 'Cerrada' con la fecha y hora de cierre."""
        self._registrar_arqueo()
        antes = self.caja.abierta_en

        response = self.client.post(self.url_cerrar, {}, follow=True)

        self.caja.refresh_from_db()
        self.assertContains(response, 'La caja fue cerrada correctamente')
        self.assertEqual(self.caja.estado, Caja.ESTADO_CERRADA)
        self.assertIsNotNone(self.caja.cerrada_en)
        self.assertGreaterEqual(self.caja.cerrada_en, antes)

    def test_una_caja_cerrada_ya_no_acepta_operaciones_de_ventanilla(self):
        """Criterio 2: tras cerrarse, la caja deja de aceptar operaciones de ventanilla."""
        self._registrar_arqueo()
        self.client.post(self.url_cerrar, {})

        response = self.client.post(
            reverse('caja:registrar_operacion', kwargs={'tipo': 'compra'}),
            {'divisa': str(self.usd.pk), 'monto': '10.00'},
            follow=True,
        )

        self.assertContains(response, 'Necesitás abrir una caja')
        self.assertFalse(OperacionVentanilla.objects.exists())

    def test_una_caja_cerrada_ya_no_acepta_movimientos_extraordinarios(self):
        """Criterio 2: tras cerrarse, la caja deja de aceptar movimientos extraordinarios."""
        self._registrar_arqueo()
        self.client.post(self.url_cerrar, {})

        response = self.client.post(
            reverse('caja:registrar_movimiento_extraordinario', kwargs={'tipo': 'ingreso'}),
            {'divisa': str(self.usd.pk), 'monto': '10.00', 'motivo': 'Refuerzo'},
            follow=True,
        )

        self.assertContains(response, 'Necesitás abrir una caja')
        self.assertFalse(MovimientoExtraordinario.objects.exists())

    def test_una_caja_cerrada_ya_no_acepta_arqueos(self):
        """Criterio 2: tras cerrarse, la caja deja de aceptar arqueos."""
        self._registrar_arqueo()
        self.client.post(self.url_cerrar, {})

        response = self.client.get(reverse('caja:iniciar_arqueo'), follow=True)

        self.assertContains(response, 'Necesitás abrir una caja')

    def test_despues_de_cerrar_se_puede_abrir_una_caja_nueva(self):
        """Tras cerrar, el cajero puede abrir un turno nuevo sin que la restricción única lo bloquee."""
        self._registrar_arqueo()
        self.client.post(self.url_cerrar, {})

        response = self.client.post(
            reverse('caja:abrir'),
            {f'saldo_{self.pyg.pk}': '0.00', f'saldo_{self.usd.pk}': '0.00'},
            follow=True,
        )

        self.assertContains(response, 'La caja fue abierta correctamente')
        self.assertEqual(Caja.objects.filter(usuario=self.cajero, estado=Caja.ESTADO_ABIERTA).count(), 1)

    # --- Criterio 3 ---

    def test_sin_arqueos_el_resumen_muestra_una_advertencia(self):
        """Criterio 3: sin ningún arqueo en el turno, el resumen avisa antes de cerrar."""
        response = self.client.get(self.url_cerrar)

        self.assertContains(response, 'no registraste ningún arqueo')
        self.assertContains(response, 'name="confirmar_sin_arqueo"')

    def test_sin_arqueos_y_sin_confirmar_no_se_cierra_la_caja(self):
        """Criterio 3: sin confirmar explícitamente, el cierre sin arqueo se rechaza."""
        response = self.client.post(self.url_cerrar, {}, follow=True)

        self.caja.refresh_from_db()
        self.assertContains(response, 'no tiene ningún arqueo registrado')
        self.assertEqual(self.caja.estado, Caja.ESTADO_ABIERTA)
        self.assertIsNone(self.caja.cerrada_en)

    def test_sin_arqueos_pero_confirmando_explicitamente_se_cierra_la_caja(self):
        """Criterio 3: confirmando explícitamente, el cierre sin arqueo se procesa igual."""
        response = self.client.post(self.url_cerrar, {'confirmar_sin_arqueo': 'on'}, follow=True)

        self.caja.refresh_from_db()
        self.assertContains(response, 'La caja fue cerrada correctamente')
        self.assertEqual(self.caja.estado, Caja.ESTADO_CERRADA)

    def test_con_al_menos_un_arqueo_no_se_pide_ninguna_confirmacion_extra(self):
        """Con un arqueo ya registrado, el cierre se procesa sin necesitar la casilla."""
        self._registrar_arqueo()

        response = self.client.get(self.url_cerrar)
        self.assertNotContains(response, 'name="confirmar_sin_arqueo"')

        response = self.client.post(self.url_cerrar, {}, follow=True)
        self.caja.refresh_from_db()
        self.assertContains(response, 'La caja fue cerrada correctamente')
        self.assertEqual(self.caja.estado, Caja.ESTADO_CERRADA)

    # --- Criterio 4 ---

    def test_una_caja_cerrada_aparece_en_el_historial_con_balance_final_y_periodo(self):
        """Criterio 4: una caja cerrada aparece en el historial con su balance y período."""
        self._registrar_arqueo()
        self.client.post(self.url_cerrar, {})
        self.caja.refresh_from_db()

        response = self.client.get(reverse('caja:historial_cajas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cerrada')
        self.assertContains(response, self.caja.abierta_en.strftime('%d/%m/%Y'))
        self.assertContains(response, self.caja.cerrada_en.strftime('%d/%m/%Y'))
        self.assertContains(response, '1.000.000,00')  # saldo final PYG (sin movimientos)
        self.assertContains(response, '200,00')  # saldo final USD (sin movimientos)

    def test_el_historial_no_ofrece_ninguna_accion_para_modificar_una_caja(self):
        """Criterio 4: el historial es de solo consulta, sin acciones para editar lo registrado."""
        self._registrar_arqueo()
        self.client.post(self.url_cerrar, {})

        response = self.client.get(reverse('caja:historial_cajas'))

        self.assertNotContains(response, 'Editar')
        self.assertNotContains(response, 'Eliminar')

    def test_una_caja_todavia_abierta_tambien_aparece_en_el_historial_sin_fecha_de_cierre(self):
        """Una caja que sigue abierta aparece en el historial, sin período de cierre."""
        response = self.client.get(reverse('caja:historial_cajas'))

        self.assertContains(response, 'Abierta')
        self.assertContains(response, 'en curso')

    # --- Permisos ---

    def test_usuario_sin_rol_cajero_no_puede_cerrar_la_caja(self):
        """Solo el rol cajero puede cerrar una caja."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_get = self.client.get(self.url_cerrar)
        response_post = self.client.post(self.url_cerrar, {})

        self.assertEqual(response_get.status_code, 403)
        self.assertEqual(response_post.status_code, 403)
        self.caja.refresh_from_db()
        self.assertEqual(self.caja.estado, Caja.ESTADO_ABIERTA)

    def test_usuario_no_autenticado_es_redirigido_al_login(self):
        """Sin sesión iniciada, se redirige al login en vez de cerrar la caja."""
        self.client.logout()

        response = self.client.get(self.url_cerrar)

        self.assertEqual(response.status_code, 302)

    def test_usuario_sin_rol_cajero_no_puede_ver_el_historial_de_cajas(self):
        """Solo el rol cajero puede consultar el historial de cajas."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(reverse('caja:historial_cajas'))

        self.assertEqual(response.status_code, 403)


class CajaCerrarModeloTest(TestCase):
    """Pruebas unitarias de 'Caja.cerrar', directamente contra el modelo."""

    def setUp(self):
        """Prepara un cajero y una caja abierta, sin pasar por ninguna vista."""
        self.cajero = User.objects.create_user(username='cajero-cierre-modelo', password='password123')
        self.caja = Caja.objects.create(usuario=self.cajero)

    def test_cerrar_cambia_el_estado_y_fija_la_fecha_de_cierre(self):
        """'cerrar' deja la caja en estado 'Cerrada' con 'cerrada_en' fijado."""
        self.assertIsNone(self.caja.cerrada_en)

        self.caja.cerrar()

        self.assertEqual(self.caja.estado, Caja.ESTADO_CERRADA)
        self.assertIsNotNone(self.caja.cerrada_en)

    def test_cerrar_persiste_los_cambios_en_la_base(self):
        """Los cambios de 'cerrar' quedan guardados, no solo en memoria."""
        self.caja.cerrar()

        recargada = Caja.objects.get(pk=self.caja.pk)
        self.assertEqual(recargada.estado, Caja.ESTADO_CERRADA)
        self.assertIsNotNone(recargada.cerrada_en)
