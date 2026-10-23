"""Pruebas de tasas, administración, historial y simulación de divisas."""

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.shortcuts import resolve_url
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from decimal import Decimal
from unittest.mock import patch

from apps.authentication.models import HistorialBaja
from apps.clientes.models import Cliente
from apps.divisas.casa_de_cambio import DesignacionCuentaPropiaError, SipapComunicacionError
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    Cotizacion,
    CuentaPropia,
    Divisa,
    moneda_a_entregar,
    moneda_a_pagar,
    monto_a_entregar,
    monto_a_pagar,
)
from tests.utils_formato import formato


@pytest.mark.django_db
class TasasVigentesTest(TestCase):
    """Verifica permisos y contenido de las tasas vigentes."""
    """
    Suite de pruebas para la Historia de Usuario: "Consulta de tasas vigentes".
    Verifica:
    - Seguridad: acceso restringido a usuarios con rol autorizado.
    - CA1: Visualización de tasas de compra y venta.
    - CA2: Indicador de "sin cotización".
    - CA3: Fecha de última actualización.
    - CA4: Ocultamiento de divisas inactivas.
    """

    def setUp(self):
        """Prepara usuarios, divisas y cotizaciones de consulta."""
        self.analista = User.objects.create_user(username='analista01', password='password123')
        self.usuario_sin_rol = User.objects.create_user(username='invitado', password='password123')

        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', activa=True)
        self.cotizacion_usd = Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=7300.50,
            tasa_venta=7400.00,
        )

        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', activa=True)
        self.ars = Divisa.objects.create(codigo='ARS', nombre='Peso Argentino', activa=False)

        self.url = reverse('divisas:tasas_vigentes')

    def _login_analista_con_sesion(self):
        """Inicia sesión de prueba con el rol de analista cambiario."""
        self.client.login(username='analista01', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

    def test_acceso_denegado_usuarios_no_autenticados(self):
        """Redirige al login a usuarios sin autenticación."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        ruta_login = resolve_url(settings.LOGIN_URL)
        self.assertTrue(ruta_login in response.url)

    def test_acceso_denegado_usuarios_sin_rol(self):
        """Deniega tasas a usuarios sin rol operativo."""
        self.client.login(username='invitado', password='password123')
        session = self.client.session
        session['keycloak_roles'] = []
        session.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_analista_ve_solo_el_acceso_a_actualizar_tasas_en_inicio(self):
        """Muestra al analista el acceso operativo correspondiente."""
        self._login_analista_con_sesion()
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Actualizar tasas')
        self.assertNotContains(response, 'Gestión de divisas')
        self.assertContains(response, self.url)

    def test_ca4_divisas_inactivas_no_se_muestran(self):
        """Oculta divisas inactivas de las tasas vigentes."""
        self._login_analista_con_sesion()
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        divisas_en_contexto = response.context['divisas']
        self.assertIn(self.usd, divisas_en_contexto)
        self.assertIn(self.eur, divisas_en_contexto)
        self.assertNotIn(self.ars, divisas_en_contexto, 'La divisa inactiva ARS no debería estar en el contexto.')

    def test_pyg_no_aparece_en_tasas_vigentes_ni_se_puede_actualizar_por_url_directa(self):
        """PYG es la moneda base: no tiene cotización propia que mostrar ni actualizar."""
        pyg = Divisa.objects.get(codigo='PYG')
        self._login_analista_con_sesion()

        response = self.client.get(self.url)
        self.assertNotIn(pyg, response.context['divisas'])

        response = self.client.get(
            reverse('divisas:actualizar_cotizacion', kwargs={'divisa_id': pyg.pk}), follow=True,
        )
        self.assertContains(response, 'no tiene una cotización para actualizar')
        self.assertEqual(response.redirect_chain[-1][0], reverse('divisas:tasas_vigentes'))

        response = self.client.post(
            reverse('divisas:actualizar_cotizacion', kwargs={'divisa_id': pyg.pk}),
            {'tasa_compra': '1', 'tasa_venta': '1'}, follow=True,
        )
        self.assertContains(response, 'no tiene una cotización para actualizar')
        self.assertFalse(Cotizacion.objects.filter(divisa=pyg).exists())

    def test_ca1_y_ca3_muestra_tasas_y_fecha(self):
        """Muestra tasas actuales y fecha de actualización."""
        self._login_analista_con_sesion()
        response = self.client.get(self.url)

        self.assertContains(response, formato(7300.50))
        self.assertContains(response, formato(7400.00))
        self.assertContains(response, 'USD')
        self.assertContains(
            response,
            self.cotizacion_usd.fecha_actualizacion.astimezone(
                timezone.get_current_timezone()
            ).strftime('%d/%m/%Y %H:%M'),
        )

    def test_ca2_divisa_sin_cotizacion_muestra_mensaje(self):
        """Informa cuando una divisa aún no tiene cotización."""
        self._login_analista_con_sesion()
        response = self.client.get(self.url)

        self.assertContains(response, 'EUR')
        self.assertContains(response, 'sin cotización')

    def test_admin_ve_el_boton_nueva_divisa_en_tasas_vigentes(self):
        """Muestra la acción de alta únicamente al administrador."""
        self.client.logout()
        User.objects.create_user(username='admin-tasas', password='password123')
        self.client.login(username='admin-tasas', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nueva divisa')
        self.assertContains(response, reverse('divisas:crear_divisa'))


@pytest.mark.django_db
class AdministracionDivisasTest(TestCase):
    """Verifica altas, ediciones, bajas y listado administrativo."""
    def setUp(self):
        """Prepara un administrador y una divisa editable."""
        self.admin = User.objects.create_user(
            username='admin-divisas', password='password123'
        )
        self.client.login(username='admin-divisas', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

    def test_admin_registra_divisa_activa_con_datos_obligatorios(self):
        """Registra una divisa activa con datos válidos.

        Usa JPY como ejemplo en vez de PYG: PYG ya existe de antemano (la
        migración de datos ``apps.divisas.0014_crear_divisa_pyg`` la
        garantiza como moneda local/base del sistema), así que intentar
        crearla de nuevo acá chocaría con la unicidad del código ISO — y
        el propósito de este test no depende de qué divisa se use.
        """
        response = self.client.post(
            reverse('divisas:crear_divisa'),
            {'codigo': 'JPY', 'nombre': 'Yen', 'simbolo': '¥'},
        )

        self.assertEqual(response.status_code, 302)
        divisa = Divisa.objects.get(codigo='JPY')
        self.assertEqual(divisa.nombre, 'Yen')
        self.assertEqual(divisa.simbolo, '¥')
        self.assertTrue(divisa.activa)
        cuenta_propia = CuentaPropia.objects.get(divisa=divisa)
        self.assertEqual(cuenta_propia.saldo, Decimal('0.00'))

    def test_rechaza_crear_una_divisa_con_codigo_pyg(self):
        """PYG es la divisa base del sistema: no se puede crear desde el catálogo."""
        response = self.client.post(
            reverse('divisas:crear_divisa'),
            {'codigo': 'PYG', 'nombre': 'Guaraní', 'simbolo': '₲'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'codigo',
            'PYG es la divisa base del sistema: no se gestiona desde este catálogo.',
        )

    def test_no_permite_editar_la_divisa_pyg(self):
        """La pantalla de edición de PYG ni se muestra: redirige con un error."""
        pyg = Divisa.objects.get(codigo='PYG')

        response = self.client.get(
            reverse('divisas:editar_divisa', kwargs={'pk': pyg.pk}), follow=True,
        )

        self.assertContains(response, 'no se puede editar')
        self.assertEqual(response.redirect_chain[-1][0], reverse('divisas:lista_divisas'))

        response = self.client.post(
            reverse('divisas:editar_divisa', kwargs={'pk': pyg.pk}),
            {'codigo': 'PYG', 'nombre': 'Otro nombre', 'simbolo': '₲'},
            follow=True,
        )
        pyg.refresh_from_db()
        self.assertEqual(pyg.nombre, 'Guaraní')

    def test_no_permite_dar_de_baja_la_divisa_pyg(self):
        """PYG tiene que seguir siempre activa: no se puede dar de baja."""
        pyg = Divisa.objects.get(codigo='PYG')

        response = self.client.post(
            reverse('divisas:baja_divisa', kwargs={'pk': pyg.pk}),
            {'causa': 'Intento de baja'},
            follow=True,
        )

        self.assertContains(response, 'no se puede dar de baja')
        pyg.refresh_from_db()
        self.assertTrue(pyg.activa)

    def test_listado_no_muestra_acciones_de_editar_o_dar_de_baja_para_pyg(self):
        """El catálogo marca a PYG como protegida, sin botones de editar ni dar de baja."""
        pyg = Divisa.objects.get(codigo='PYG')

        response = self.client.get(reverse('divisas:lista_divisas'))

        self.assertContains(response, 'Divisa base del sistema')
        self.assertNotContains(response, reverse('divisas:editar_divisa', kwargs={'pk': pyg.pk}))
        self.assertNotContains(response, reverse('divisas:baja_divisa', kwargs={'pk': pyg.pk}))

    def test_registro_rechaza_codigo_iso_duplicado(self):
        """Rechaza códigos ISO ya existentes."""
        Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$')

        response = self.client.post(
            reverse('divisas:crear_divisa'),
            {'codigo': 'USD', 'nombre': 'Dólar duplicado', 'simbolo': '$'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'codigo',
            'Ya existe una divisa con este código ISO.',
        )

    def test_registro_rechaza_campos_vacios_y_codigo_invalido(self):
        """Rechaza datos obligatorios vacíos o códigos inválidos."""
        response = self.client.post(
            reverse('divisas:crear_divisa'),
            {'codigo': 'us', 'nombre': '', 'simbolo': ''},
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('codigo', form.errors)
        self.assertIn('nombre', form.errors)
        self.assertIn('simbolo', form.errors)

    def test_admin_edita_datos_de_una_divisa(self):
        """Permite actualizar los datos de una divisa."""
        divisa = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        response = self.client.post(
            reverse('divisas:editar_divisa', kwargs={'pk': divisa.pk}),
            {
                'codigo': 'EUR',
                'nombre': 'Euro actualizado',
                'simbolo': '€',
                'activa': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        divisa.refresh_from_db()
        self.assertEqual(divisa.nombre, 'Euro actualizado')

    def test_inactivar_conserva_historial_y_no_aparece_en_tasas(self):
        """Conserva historial al inactivar una divisa y la oculta de tasas."""
        divisa = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)
        cotizacion = Cotizacion.objects.create(divisa=divisa, tasa_compra=100, tasa_venta=110)

        response = self.client.post(
            reverse('divisas:baja_divisa', kwargs={'pk': divisa.pk}),
            {'causa': 'Moneda fuera de operacion'},
        )

        self.assertEqual(response.status_code, 302)
        divisa.refresh_from_db()
        self.assertFalse(divisa.activa)
        self.assertTrue(Cotizacion.objects.filter(pk=cotizacion.pk).exists())
        registro = HistorialBaja.objects.get(
            tipo_recurso=HistorialBaja.TIPO_DIVISA,
            recurso_id=divisa.pk,
        )
        self.assertEqual(registro.causa, 'Moneda fuera de operacion')

        historial = self.client.get(reverse('divisas:historial_bajas'))
        self.assertEqual(historial.status_code, 200)
        self.assertContains(historial, 'Moneda fuera de operacion')

        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()
        tasas = self.client.get(reverse('divisas:tasas_vigentes'))
        self.assertNotIn(divisa, tasas.context['divisas'])

    def test_listado_admin_muestra_codigo_nombre_simbolo_y_estado(self):
        """Muestra los datos principales y estado en el catálogo."""
        activa = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        inactiva = Divisa.objects.create(codigo='ARS', nombre='Peso Argentino', simbolo='$', activa=False)

        response = self.client.get(reverse('divisas:lista_divisas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, activa.codigo)
        self.assertContains(response, activa.nombre)
        self.assertContains(response, activa.simbolo)
        self.assertContains(response, 'Activo')
        self.assertContains(response, inactiva.codigo)
        self.assertContains(response, inactiva.nombre)
        self.assertContains(response, 'Inactivo')


class CuentaPropiaAdminTest(TestCase):
    """Verifica la pantalla administrativa de fondos propios (``CuentaPropia``), sincronizada con sipap-sim."""

    def setUp(self):
        """Prepara un administrador y una divisa con su cuenta propia."""
        self.admin = User.objects.create_user(username='admin-fondos', password='password123')
        self.client.login(username='admin-fondos', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.cuenta_usd = CuentaPropia.objects.create(divisa=self.usd, saldo=Decimal('0.00'))

    @patch('apps.divisas.views.consultar_cuenta_casa_de_cambio')
    @patch('apps.divisas.views.consultar_saldo_casa_de_cambio')
    def test_lista_muestra_el_saldo_de_cada_moneda_incluida_pyg(self, mock_saldo, mock_cuenta):
        """A diferencia del catálogo de divisas, PYG sí aparece acá."""
        mock_saldo.return_value = Decimal('0.00')
        mock_cuenta.return_value = None

        response = self.client.get(reverse('divisas:lista_cuentas_propias'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'USD')
        self.assertContains(response, 'PYG')

    @patch('apps.divisas.views.consultar_cuenta_casa_de_cambio')
    @patch('apps.divisas.views.consultar_saldo_casa_de_cambio')
    def test_cada_divisa_enlaza_a_su_propia_pantalla_de_historial(self, mock_saldo, mock_cuenta):
        """El botón "Historial" lleva a una pantalla propia del sistema, no al admin de sipap-sim."""
        mock_saldo.return_value = Decimal('0.00')
        mock_cuenta.return_value = None

        response = self.client.get(reverse('divisas:lista_cuentas_propias'))

        self.assertContains(response, reverse('divisas:historial_cuenta_propia', kwargs={'codigo': 'USD'}))
        self.assertContains(response, reverse('divisas:historial_cuenta_propia', kwargs={'codigo': 'PYG'}))
        self.assertNotContains(response, f'{settings.SIPAP_BASE_URL}/admin/')

    @patch('apps.divisas.views.consultar_cuenta_casa_de_cambio')
    @patch('apps.divisas.views.consultar_saldo_casa_de_cambio')
    def test_sincroniza_el_saldo_con_el_que_informa_sipap_sim(self, mock_saldo, mock_cuenta):
        """El saldo mostrado y guardado es el real de sipap-sim, no el que ya tenía guardado."""
        mock_saldo.return_value = Decimal('15000.50')
        mock_cuenta.return_value = None

        response = self.client.get(reverse('divisas:lista_cuentas_propias'))

        self.assertContains(response, '15.000,50')
        self.cuenta_usd.refresh_from_db()
        self.assertEqual(self.cuenta_usd.saldo, Decimal('15000.50'))

    @patch('apps.divisas.views.consultar_cuenta_casa_de_cambio')
    @patch('apps.divisas.views.consultar_saldo_casa_de_cambio')
    def test_muestra_la_cuenta_designada_cuando_hay_una(self, mock_saldo, mock_cuenta):
        """Además del saldo, se muestra qué cuenta real de sipap-sim está designada en esa divisa."""
        mock_saldo.return_value = Decimal('15000.50')
        mock_cuenta.return_value = {
            'numero': '2000000000000999', 'titular': 'Global Exchange S.A.', 'proveedor': 'Banco Itaú Paraguay',
        }

        response = self.client.get(reverse('divisas:lista_cuentas_propias'))

        self.assertContains(response, '2000000000000999')
        self.assertContains(response, 'Banco Itaú Paraguay')
        self.assertNotContains(response, 'Sin designar')

    @patch('apps.divisas.views.consultar_cuenta_casa_de_cambio')
    @patch('apps.divisas.views.consultar_saldo_casa_de_cambio')
    def test_avisa_si_una_moneda_no_tiene_cuenta_designada_como_la_casa_de_cambio(self, mock_saldo, mock_cuenta):
        mock_saldo.return_value = None

        response = self.client.get(reverse('divisas:lista_cuentas_propias'))

        self.assertContains(response, 'Todavía no hay ninguna cuenta designada como la casa de cambio')
        self.assertContains(response, 'USD')
        self.assertContains(response, 'Sin designar')
        self.cuenta_usd.refresh_from_db()
        self.assertEqual(self.cuenta_usd.saldo, Decimal('0.00'))
        mock_cuenta.assert_not_called()

    @patch('apps.divisas.views.consultar_cuenta_casa_de_cambio')
    @patch('apps.divisas.views.consultar_saldo_casa_de_cambio')
    def test_si_sipap_sim_no_responde_muestra_el_ultimo_valor_conocido(self, mock_saldo, mock_cuenta):
        mock_saldo.side_effect = SipapComunicacionError('no se pudo conectar')
        self.cuenta_usd.saldo = Decimal('500.00')
        self.cuenta_usd.save(update_fields=['saldo'])

        response = self.client.get(reverse('divisas:lista_cuentas_propias'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se pudo conectar con sipap-sim')
        self.cuenta_usd.refresh_from_db()
        self.assertEqual(self.cuenta_usd.saldo, Decimal('500.00'))
        mock_cuenta.assert_not_called()

    @patch('apps.divisas.views.consultar_saldo_casa_de_cambio')
    def test_usuario_sin_rol_admin_no_puede_ver(self, mock_consultar):
        self.client.logout()
        User.objects.create_user(username='cliente-fondos', password='password123')
        self.client.login(username='cliente-fondos', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_list = self.client.get(reverse('divisas:lista_cuentas_propias'))

        self.assertEqual(response_list.status_code, 403)
        mock_consultar.assert_not_called()


class DesignarCuentaPropiaViewTest(TestCase):
    """Verifica la designación, desde Global Exchange, de cuál cuenta de sipap-sim es la casa de cambio."""

    def setUp(self):
        """Prepara un administrador y una divisa."""
        self.admin = User.objects.create_user(username='admin-designar', password='password123')
        self.client.login(username='admin-designar', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.url = reverse('divisas:designar_cuenta_propia', kwargs={'codigo': 'USD'})

    @patch('apps.divisas.views.designar_cuenta_casa_de_cambio')
    def test_designa_la_cuenta_indicada(self, mock_designar):
        mock_designar.return_value = {
            'numero': '2000000000000999', 'titular': 'Global Exchange S.A.', 'proveedor': 'Tigo Money',
        }

        response = self.client.post(
            self.url, {'numero_cuenta': '2000000000000999', 'documento_titular': '80012345-6'}, follow=True,
        )

        self.assertContains(response, 'queda designada como la')
        mock_designar.assert_called_once_with('USD', '2000000000000999', '80012345-6')

    @patch('apps.divisas.views.designar_cuenta_casa_de_cambio')
    def test_informa_si_sipap_sim_rechaza_la_designacion(self, mock_designar):
        mock_designar.side_effect = DesignacionCuentaPropiaError('Esa cuenta es de PYG, no de USD.')

        response = self.client.post(
            self.url, {'numero_cuenta': '1000000000000001', 'documento_titular': '80012345-6'}, follow=True,
        )

        self.assertContains(response, 'Esa cuenta es de PYG, no de USD.')

    @patch('apps.divisas.views.designar_cuenta_casa_de_cambio')
    def test_informa_si_sipap_sim_no_responde(self, mock_designar):
        mock_designar.side_effect = SipapComunicacionError('no se pudo conectar')

        response = self.client.post(
            self.url, {'numero_cuenta': '2000000000000999', 'documento_titular': '80012345-6'}, follow=True,
        )

        self.assertContains(response, 'No se pudo conectar con sipap-sim')

    def test_rechaza_datos_incompletos_sin_llamar_a_sipap_sim(self):
        with patch('apps.divisas.views.designar_cuenta_casa_de_cambio') as mock_designar:
            response = self.client.post(self.url, {'numero_cuenta': '', 'documento_titular': ''}, follow=True)

        self.assertContains(response, 'Ingresá el número de cuenta')
        mock_designar.assert_not_called()

    def test_un_cliente_no_puede_designar(self):
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.post(
            self.url, {'numero_cuenta': '2000000000000999', 'documento_titular': '80012345-6'},
        )

        self.assertEqual(response.status_code, 403)


class HistorialCuentaPropiaViewTest(TestCase):
    """Verifica la pantalla propia de historial de movimientos de una divisa (traído de sipap-sim por API)."""

    def setUp(self):
        """Prepara un administrador y una divisa."""
        self.admin = User.objects.create_user(username='admin-historial', password='password123')
        self.client.login(username='admin-historial', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.url = reverse('divisas:historial_cuenta_propia', kwargs={'codigo': 'USD'})

    @patch('apps.divisas.views.consultar_movimientos_casa_de_cambio')
    def test_muestra_los_movimientos_reales_de_sipap_sim(self, mock_consultar):
        mock_consultar.return_value = [{
            'id': 'SPI-1', 'direccion': 'entrada', 'estado': 'acreditada', 'estado_display': 'Acreditada',
            'contraparte': 'Juan Pérez', 'monto_solicitado': Decimal('100.00'), 'monto_acreditado': Decimal('100.00'),
            'moneda': 'USD', 'referencia': 'GE-1', 'creado_en': timezone.now(), 'resuelto_en': timezone.now(),
        }]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Juan Pérez')
        self.assertContains(response, 'GE-1')
        mock_consultar.assert_called_once_with('USD')

    @patch('apps.divisas.views.consultar_movimientos_casa_de_cambio')
    def test_si_sipap_sim_no_responde_muestra_un_aviso_sin_romper(self, mock_consultar):
        mock_consultar.side_effect = SipapComunicacionError('no se pudo conectar')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se pudo conectar con sipap-sim')

    def test_404_si_la_divisa_no_existe(self):
        response = self.client.get(reverse('divisas:historial_cuenta_propia', kwargs={'codigo': 'XYZ'}))

        self.assertEqual(response.status_code, 404)

    @patch('apps.divisas.views.consultar_movimientos_casa_de_cambio')
    def test_un_cliente_no_puede_acceder(self, mock_consultar):
        self.client.logout()
        User.objects.create_user(username='cliente-historial', password='password123')
        self.client.login(username='cliente-historial', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        mock_consultar.assert_not_called()


@pytest.mark.django_db
class DivisaPygProtegidaEnElModeloTest(TestCase):
    """Verifica que PYG quede protegida a nivel de modelo, no solo en las vistas.

    Se identifica siempre por ``codigo`` (``Divisa.CODIGO_BASE``), nunca
    por su clave primaria: un id autoincremental no es el mismo en todas
    las instalaciones, pero "PYG" sí.
    """

    def test_es_base_identifica_pyg_por_codigo(self):
        """``es_base`` es verdadero solo para la fila con codigo='PYG'."""
        pyg = Divisa.objects.get(codigo='PYG')
        usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)

        self.assertTrue(pyg.es_base)
        self.assertFalse(usd.es_base)

    def test_guardar_pyg_con_otros_datos_los_fuerza_a_los_canonicos(self):
        """Cualquier intento de cambiarle nombre, símbolo o estado a PYG no tiene efecto."""
        pyg = Divisa.objects.get(codigo='PYG')

        pyg.nombre = 'Otro nombre'
        pyg.simbolo = '$$$'
        pyg.activa = False
        pyg.save()

        pyg.refresh_from_db()
        self.assertEqual(pyg.nombre, Divisa.NOMBRE_BASE)
        self.assertEqual(pyg.simbolo, Divisa.SIMBOLO_BASE)
        self.assertTrue(pyg.activa)

    def test_no_se_le_puede_cambiar_el_codigo_a_pyg(self):
        """Intentar renombrar el código de PYG se rechaza, no se guarda en silencio."""
        pyg = Divisa.objects.get(codigo='PYG')
        pyg.codigo = 'ZZZ'

        with self.assertRaises(ValidationError):
            pyg.save()

        self.assertTrue(Divisa.objects.filter(codigo='PYG').exists())
        self.assertFalse(Divisa.objects.filter(codigo='ZZZ').exists())

    def test_no_se_puede_eliminar_pyg(self):
        """Borrar PYG se rechaza: el sistema la necesita siempre presente."""
        pyg = Divisa.objects.get(codigo='PYG')

        with self.assertRaises(ValidationError):
            pyg.delete()

        self.assertTrue(Divisa.objects.filter(codigo='PYG').exists())

    def test_otras_divisas_se_guardan_y_eliminan_sin_restricciones(self):
        """La protección es exclusiva de PYG: cualquier otra divisa funciona como siempre."""
        usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)

        usd.nombre = 'Dólar estadounidense'
        usd.save()
        usd.refresh_from_db()
        self.assertEqual(usd.nombre, 'Dólar estadounidense')

        usd.delete()
        self.assertFalse(Divisa.objects.filter(codigo='USD').exists())


@pytest.mark.django_db
class ActualizacionCotizacionesTest(TestCase):
    """Verifica actualización y trazabilidad de cotizaciones."""
    def setUp(self):
        """Prepara una divisa y usuarios con roles operativos."""
        self.analista = User.objects.create_user(username='analista-cambiario', password='password123')
        self.divisa = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.url = reverse('divisas:actualizar_cotizacion', kwargs={'divisa_id': self.divisa.pk})
        self.client.login(username='analista-cambiario', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

    def test_analista_ve_el_menu_de_actualizar_tasas(self):
        """Muestra actualización de tasas al analista autorizado."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Actualizar tasas')
        self.assertContains(response, reverse('divisas:tasas_vigentes'))

    def test_analista_tiene_acceso_operativo(self):
        """Verifica el acceso operativo exclusivo del analista cambiario."""
        response = self.client.get(reverse('divisas:tasas_vigentes'))
        self.assertEqual(response.status_code, 200)

    def test_analista_actualiza_compra_y_venta(self):
        """Guarda tasas de compra y venta válidas."""
        response = self.client.post(self.url, {'tasa_compra': '7300.50', 'tasa_venta': '7400.00'})
        self.assertEqual(response.status_code, 302)
        cotizacion = Cotizacion.objects.get(divisa=self.divisa)
        self.assertEqual(cotizacion.tasa_compra, 7300.50)
        self.assertEqual(cotizacion.tasa_venta, 7400.00)

    def test_actualizacion_registra_usuario_y_fecha(self):
        """Registra el usuario y momento de cada cotización."""
        response = self.client.post(self.url, {'tasa_compra': '7300', 'tasa_venta': '7400'})
        self.assertEqual(response.status_code, 302)
        cotizacion = Cotizacion.objects.get(divisa=self.divisa)
        self.assertEqual(cotizacion.usuario, self.analista)
        self.assertIsNotNone(cotizacion.fecha_actualizacion)

    def test_rechaza_compra_mayor_y_valores_no_validos(self):
        """Rechaza tasas negativas o una compra mayor que la venta."""
        for datos in [
            {'tasa_compra': '7500', 'tasa_venta': '7400'},
            {'tasa_compra': '-1', 'tasa_venta': '7400'},
            {'tasa_compra': '7300', 'tasa_venta': '0'},
        ]:
            response = self.client.post(self.url, datos)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context['form'].is_valid())
        self.assertEqual(Cotizacion.objects.filter(divisa=self.divisa).count(), 0)

    def test_nueva_actualizacion_conserva_la_anterior_en_historial(self):
        """Conserva la cotización anterior al registrar otra."""
        anterior = Cotizacion.objects.create(
            divisa=self.divisa,
            tasa_compra=7000,
            tasa_venta=7100,
            usuario=self.analista,
        )

        response = self.client.post(self.url, {'tasa_compra': '7300', 'tasa_venta': '7400'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Cotizacion.objects.filter(divisa=self.divisa).count(), 2)
        anterior.refresh_from_db()
        self.assertEqual(anterior.tasa_compra, 7000)
        self.assertEqual(anterior.tasa_venta, 7100)

    def test_historial_muestra_todas_las_actualizaciones_de_la_divisa(self):
        """Lista todas las cotizaciones históricas de la divisa."""
        primera = Cotizacion.objects.create(
            divisa=self.divisa,
            tasa_compra=7000,
            tasa_venta=7100,
            usuario=self.analista,
        )
        segunda = Cotizacion.objects.create(
            divisa=self.divisa,
            tasa_compra=7300,
            tasa_venta=7400,
            usuario=self.analista,
        )

        response = self.client.get(
            reverse('divisas:historial_cotizaciones', kwargs={'divisa_id': self.divisa.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['cotizaciones']), [segunda, primera])
        self.assertContains(response, formato(7300))
        self.assertContains(response, formato(7000))

    def test_usuario_sin_rol_no_puede_actualizar(self):
        """Deniega actualización a usuarios sin rol autorizado."""
        session = self.client.session
        session['keycloak_roles'] = []
        session.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


@pytest.mark.django_db
class ConsultaTasasClienteTest(TestCase):
    """Verifica la consulta de tasas por un cliente."""
    def test_cliente_visualiza_tasas_actuales_sin_acciones_de_actualizacion(self):
        """Permite consultar tasas al cliente sin acciones administrativas."""
        cliente = User.objects.create_user(username='cliente-tasas', password='password123')
        divisa = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        Cotizacion.objects.create(divisa=divisa, tasa_compra=7800, tasa_venta=8000)
        self.client.login(username='cliente-tasas', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(reverse('divisas:tasas_vigentes'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tasas actuales')
        self.assertContains(response, formato(7800))
        self.assertNotContains(
            response,
            reverse('divisas:actualizar_cotizacion', kwargs={'divisa_id': divisa.pk}),
        )


@pytest.mark.django_db
class SimuladorDivisasTest(TestCase):
    """Verifica la simulación de compra, venta y cambio entre divisas."""
    def setUp(self):
        """Prepara divisas y tasas para las conversiones."""
        self.analista = User.objects.create_user(username='analista-sim', password='password123')
        self.client.login(username='analista-sim', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        Cotizacion.objects.create(divisa=self.usd, tasa_compra=7300.00, tasa_venta=7400.00)
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=7900.00, tasa_venta=8100.00)

    def test_simulacion_compra_usa_tasa_venta_y_suma_comision(self):
        """Simula una compra aplicando la tasa de venta y sumando la comisión."""
        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Monto final')
        self.assertContains(response, formato(747400.00))

    def test_simulacion_venta_usa_tasa_compra_y_resta_comision(self):
        """Simula una venta aplicando la tasa de compra y descontando la comisión."""
        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {'tipo': 'VENTA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, formato(722700.00))

    def test_simulacion_cambio_triangula_por_pyg_con_comision(self):
        """Simula un cambio entre divisas triangulando por PYG."""
        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {
                'tipo': 'CAMBIO',
                'divisa_origen': str(self.usd.pk),
                'divisa_destino': str(self.eur.pk),
                'monto': '100',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tasa cruzada implícita')
        self.assertContains(response, formato(89.22))

    def test_simulacion_incluye_placeholder_para_no_repetir_divisa(self):
        """Incluye la opción 'Seleccionar divisa' para no preseleccionar ninguna."""
        response = self.client.get(reverse('divisas:simulacion_divisas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Seleccionar divisa')

    def test_simulacion_rechaza_divisa_sin_cotizacion(self):
        """Informa cuando una divisa no tiene una cotización vigente."""
        divisa_sin_tasa = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)

        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {'tipo': 'COMPRA', 'divisa': str(divisa_sin_tasa.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no tiene cotización disponible')

    def test_simulacion_rechaza_monto_invalido(self):
        """Rechaza montos nulos o negativos en la simulación."""
        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '0'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'greater than or equal to 0.01')

    def test_simulacion_cambio_rechaza_misma_divisa(self):
        """No permite cambiar una divisa contra sí misma."""
        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {
                'tipo': 'CAMBIO',
                'divisa_origen': str(self.usd.pk),
                'divisa_destino': str(self.usd.pk),
                'monto': '100',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Debe seleccionar dos divisas distintas')


class MontoYMonedaAPagarYAEntregarTest(TestCase):
    """Verifica qué paga y qué recibe el cliente en cada tipo de operación.

    Una compra se paga en PYG y entrega la divisa comprada; una venta
    entrega la propia divisa vendida (nunca PYG) y recibe PYG a cambio;
    un cambio entrega la divisa de origen y recibe la de destino,
    triangulando por PYG solo internamente (ver
    ``apps.divisas.models.monto_a_pagar``/``monto_a_entregar``).
    """

    def setUp(self):
        """Prepara un cliente y dos divisas cotizadas."""
        usuario = User.objects.create_user(username='cliente-montos', password='password123')
        self.cliente = Cliente.objects.create(
            user=usuario, identificador='MONTOS-001', nombre='Cliente', apellido='Montos',
            email='cliente-montos@test.com', is_active=True,
        )
        self.usuario = usuario
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

    def _compra_o_venta(self, tipo):
        return CalculoOperacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, tipo=tipo, divisa=self.usd, codigo_divisa='USD',
            monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_CONFIRMADA, vence_en=timezone.now(),
        )

    def _cambio(self):
        return CalculoTriangulacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, divisa_origen=self.usd, divisa_destino=self.eur,
            codigo_divisa_origen='USD', codigo_divisa_destino='EUR', monto_origen=Decimal('100.00'),
            tasa_compra_aplicada=Decimal('7300.00'), tasa_venta_aplicada=Decimal('8100.00'),
            tasa_cruzada=Decimal('0.901235'), monto_equivalente_pyg=Decimal('730000.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('0.90'), monto_final=Decimal('89.22'),
            estado=CalculoTriangulacion.ESTADO_CONFIRMADA, vence_en=timezone.now(),
        )

    def test_compra_paga_en_pyg_y_entrega_la_divisa_comprada(self):
        compra = self._compra_o_venta(CalculoOperacion.TIPO_COMPRA)

        self.assertEqual(moneda_a_pagar(compra), 'PYG')
        self.assertEqual(monto_a_pagar(compra), compra.monto_final)
        self.assertEqual(moneda_a_entregar(compra), 'USD')
        self.assertEqual(monto_a_entregar(compra), compra.monto_origen)

    def test_venta_entrega_la_divisa_vendida_y_recibe_pyg(self):
        """La venta nunca se paga en PYG: el cliente entrega la divisa que vende, no guaraníes."""
        venta = self._compra_o_venta(CalculoOperacion.TIPO_VENTA)

        self.assertEqual(moneda_a_pagar(venta), 'USD')
        self.assertEqual(monto_a_pagar(venta), venta.monto_origen)
        self.assertEqual(moneda_a_entregar(venta), 'PYG')
        self.assertEqual(monto_a_entregar(venta), venta.monto_final)

    def test_cambio_entrega_la_divisa_origen_y_recibe_la_de_destino(self):
        """El cambio nunca toca PYG desde la perspectiva del cliente: es solo un paso interno de la triangulación."""
        cambio = self._cambio()

        self.assertEqual(moneda_a_pagar(cambio), 'USD')
        self.assertEqual(monto_a_pagar(cambio), cambio.monto_origen)
        self.assertEqual(moneda_a_entregar(cambio), 'EUR')
        self.assertEqual(monto_a_entregar(cambio), cambio.monto_final)
