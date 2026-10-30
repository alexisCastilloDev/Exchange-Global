"""Pruebas de la configuración de los tiempos de espera de las operaciones."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.divisas.models import ConfiguracionVigencia

User = get_user_model()


class ConfiguracionVigenciaResolucionTest(TestCase):
    """Verifica la resolución de los tiempos de espera vigentes."""

    def test_usa_los_valores_por_defecto_sin_configuracion(self):
        """Sin ninguna fila configurada, se usan los valores por defecto de settings."""
        self.assertEqual(
            ConfiguracionVigencia.vigencia_calculo_segundos(),
            settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS,
        )
        self.assertEqual(
            ConfiguracionVigencia.vigencia_confirmacion_segundos(),
            settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS,
        )
        self.assertEqual(
            ConfiguracionVigencia.vigencia_pago_segundos(),
            settings.PAGO_OPERACION_VIGENCIA_SEGUNDOS,
        )

    def test_usa_los_valores_configurados_por_el_administrador(self):
        """Con una configuración guardada, se usan esos valores en vez de los de settings."""
        ConfiguracionVigencia.objects.create(
            calculo_vigencia_segundos=120,
            confirmacion_vigencia_segundos=900,
            pago_vigencia_segundos=3600,
        )

        self.assertEqual(ConfiguracionVigencia.vigencia_calculo_segundos(), 120)
        self.assertEqual(ConfiguracionVigencia.vigencia_confirmacion_segundos(), 900)
        self.assertEqual(ConfiguracionVigencia.vigencia_pago_segundos(), 3600)


class ConfiguracionVigenciaVistaTest(TestCase):
    """Verifica el acceso y la edición de los tiempos de espera."""

    def setUp(self):
        """Prepara un usuario administrador."""
        self.admin = User.objects.create_user(username='admin-vigencia', password='password123')
        self.client.login(username='admin-vigencia', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

    def test_administrador_ve_el_formulario_con_los_valores_por_defecto(self):
        """Sin configuración previa, el formulario se prellena con los valores de settings."""
        response = self.client.get(reverse('divisas:configuracion_vigencia'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS))
        self.assertContains(response, str(settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS))
        self.assertContains(response, str(settings.PAGO_OPERACION_VIGENCIA_SEGUNDOS))

    def test_administrador_configura_los_tiempos_de_espera(self):
        """El administrador puede guardar los tres tiempos de espera."""
        response = self.client.post(
            reverse('divisas:configuracion_vigencia'),
            {
                'calculo_vigencia_segundos': '120',
                'confirmacion_vigencia_segundos': '900',
                'pago_vigencia_segundos': '1800',
            },
        )

        self.assertRedirects(response, reverse('divisas:configuracion_vigencia'))
        configuracion = ConfiguracionVigencia.objects.get()
        self.assertEqual(configuracion.calculo_vigencia_segundos, 120)
        self.assertEqual(configuracion.confirmacion_vigencia_segundos, 900)
        self.assertEqual(configuracion.pago_vigencia_segundos, 1800)
        self.assertEqual(configuracion.actualizado_por, self.admin)

    def test_editar_de_nuevo_actualiza_la_misma_configuracion_sin_duplicar(self):
        """Guardar la configuración una segunda vez actualiza el único registro existente."""
        self.client.post(
            reverse('divisas:configuracion_vigencia'),
            {
                'calculo_vigencia_segundos': '120',
                'confirmacion_vigencia_segundos': '900',
                'pago_vigencia_segundos': '1800',
            },
        )

        self.client.post(
            reverse('divisas:configuracion_vigencia'),
            {
                'calculo_vigencia_segundos': '180',
                'confirmacion_vigencia_segundos': '600',
                'pago_vigencia_segundos': '3600',
            },
        )

        self.assertEqual(ConfiguracionVigencia.objects.count(), 1)
        configuracion = ConfiguracionVigencia.objects.get()
        self.assertEqual(configuracion.calculo_vigencia_segundos, 180)
        self.assertEqual(configuracion.confirmacion_vigencia_segundos, 600)
        self.assertEqual(configuracion.pago_vigencia_segundos, 3600)

    def test_solo_el_admin_puede_acceder(self):
        """A diferencia de las comisiones, esta configuración es exclusiva de admin."""
        for rol in ('analista_cambiario', 'cliente'):
            with self.subTest(rol=rol):
                session = self.client.session
                session['keycloak_roles'] = [rol]
                session.save()

                response = self.client.get(reverse('divisas:configuracion_vigencia'))

                self.assertEqual(response.status_code, 403)

    def test_rechaza_cualquier_tiempo_de_espera_no_positivo(self):
        """No permite configurar en cero o negativo el tiempo de espera del importe, la operación o el pago."""
        valores_base = {
            'calculo_vigencia_segundos': '300',
            'confirmacion_vigencia_segundos': '300',
            'pago_vigencia_segundos': '1800',
        }
        casos = {
            'importe': {**valores_base, 'calculo_vigencia_segundos': '0'},
            'operación': {**valores_base, 'confirmacion_vigencia_segundos': '-5'},
            'pago': {**valores_base, 'pago_vigencia_segundos': '0'},
        }
        for etiqueta, datos in casos.items():
            with self.subTest(campo=etiqueta):
                response = self.client.post(reverse('divisas:configuracion_vigencia'), datos)

                self.assertEqual(response.status_code, 200)
                self.assertFalse(ConfiguracionVigencia.objects.exists())
                self.assertContains(response, 'debe ser mayor que cero')
