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

    def test_usa_los_valores_configurados_por_el_administrador(self):
        """Con una configuración guardada, se usan esos valores en vez de los de settings."""
        ConfiguracionVigencia.objects.create(
            calculo_vigencia_segundos=120,
            confirmacion_vigencia_segundos=900,
        )

        self.assertEqual(ConfiguracionVigencia.vigencia_calculo_segundos(), 120)
        self.assertEqual(ConfiguracionVigencia.vigencia_confirmacion_segundos(), 900)


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

    def test_administrador_configura_los_tiempos_de_espera(self):
        """El administrador puede guardar ambos tiempos de espera."""
        response = self.client.post(
            reverse('divisas:configuracion_vigencia'),
            {'calculo_vigencia_segundos': '120', 'confirmacion_vigencia_segundos': '900'},
        )

        self.assertRedirects(response, reverse('divisas:configuracion_vigencia'))
        configuracion = ConfiguracionVigencia.objects.get()
        self.assertEqual(configuracion.calculo_vigencia_segundos, 120)
        self.assertEqual(configuracion.confirmacion_vigencia_segundos, 900)
        self.assertEqual(configuracion.actualizado_por, self.admin)

    def test_editar_de_nuevo_actualiza_la_misma_configuracion_sin_duplicar(self):
        """Guardar la configuración una segunda vez actualiza el único registro existente."""
        self.client.post(
            reverse('divisas:configuracion_vigencia'),
            {'calculo_vigencia_segundos': '120', 'confirmacion_vigencia_segundos': '900'},
        )

        self.client.post(
            reverse('divisas:configuracion_vigencia'),
            {'calculo_vigencia_segundos': '180', 'confirmacion_vigencia_segundos': '600'},
        )

        self.assertEqual(ConfiguracionVigencia.objects.count(), 1)
        configuracion = ConfiguracionVigencia.objects.get()
        self.assertEqual(configuracion.calculo_vigencia_segundos, 180)
        self.assertEqual(configuracion.confirmacion_vigencia_segundos, 600)

    def test_analista_cambiario_no_puede_acceder(self):
        """A diferencia de las comisiones, esta configuración es exclusiva de admin."""
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

        response = self.client.get(reverse('divisas:configuracion_vigencia'))

        self.assertEqual(response.status_code, 403)

    def test_cliente_no_puede_acceder(self):
        """Un rol cliente no puede ver ni editar los tiempos de espera."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(reverse('divisas:configuracion_vigencia'))

        self.assertEqual(response.status_code, 403)

    def test_rechaza_tiempo_de_espera_del_importe_no_positivo(self):
        """No permite configurar un tiempo de espera del importe en cero o negativo."""
        response = self.client.post(
            reverse('divisas:configuracion_vigencia'),
            {'calculo_vigencia_segundos': '0', 'confirmacion_vigencia_segundos': '300'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ConfiguracionVigencia.objects.exists())
        self.assertContains(response, 'debe ser mayor que cero')

    def test_rechaza_tiempo_de_espera_de_la_operacion_no_positivo(self):
        """No permite configurar un tiempo de espera de la operación en cero o negativo."""
        response = self.client.post(
            reverse('divisas:configuracion_vigencia'),
            {'calculo_vigencia_segundos': '300', 'confirmacion_vigencia_segundos': '-5'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ConfiguracionVigencia.objects.exists())
        self.assertContains(response, 'debe ser mayor que cero')
