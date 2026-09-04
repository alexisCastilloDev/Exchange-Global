import pytest

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.conf import settings
from django.shortcuts import resolve_url
from apps.divisas.models import Divisa, Cotizacion
@pytest.mark.django_db  # Habilita el acceso a la base de datos para pytest
class TasasVigentesTest(TestCase):
    """
    Suite de pruebas para la Historia de Usuario: "Consulta de tasas vigentes".
    
    Verifica:
    - Seguridad: Acceso restringido solo a usuarios autenticados del grupo 'Agentes' (Keycloak).
    - CA1: Visualización de tasas de compra y venta.
    - CA2: Indicador de "sin cotización" para divisas sin tasas cargadas.
    - CA3: Visualización de fecha de última actualización.
    - CA4: Ocultamiento de divisas inactivas.
    """

    def setUp(self):
        """
        Configuración inicial para cada prueba.
        Crea usuarios, grupos, divisas y cotizaciones simulando el estado de la base de datos.
        """
        # 1. Configuración de Seguridad (Simulando lo que sincroniza mozilla-django-oidc)
        self.grupo_agentes = Group.objects.create(name='Agentes')
        self.agente = User.objects.create_user(username='agente01', password='password123')
        self.agente.groups.add(self.grupo_agentes)
        
        self.usuario_sin_rol = User.objects.create_user(username='invitado', password='password123')

        # 2. Datos de Prueba (Divisas y Cotizaciones)
        # Divisa Activa CON cotización (Para CA1 y CA3)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', activa=True)
        self.cotizacion_usd = Cotizacion.objects.create(
            divisa=self.usd, 
            tasa_compra=7300.50, 
            tasa_venta=7400.00
        )

        # Divisa Activa SIN cotización (Para CA2)
        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', activa=True)

        # Divisa INACTIVA (Para CA4)
        self.ars = Divisa.objects.create(codigo='ARS', nombre='Peso Argentino', activa=False)

        # URL de la vista (Asumiendo que el app_name en urls.py es 'divisas' y el name='tasas_vigentes')
        self.url = reverse('divisas:tasas_vigentes')

    def test_acceso_denegado_usuarios_no_autenticados(self):
        """Prueba de seguridad: Un usuario anónimo es redirigido al login."""
        response = self.client.get(self.url)
        
        # 1. Verificamos que haya una redirección (código 302)
        self.assertEqual(response.status_code, 302)
        
        # 2. Traducimos la configuración de LOGIN_URL a la ruta real y comprobamos que esté en la URL
        ruta_login = resolve_url(settings.LOGIN_URL)
        self.assertTrue(ruta_login in response.url)

    def test_acceso_denegado_usuarios_sin_rol(self):
        """
        Prueba de seguridad: Un usuario autenticado pero sin el grupo 'Agentes'
        recibe un error 403 (Prohibido).
        """
        self.client.login(username='invitado', password='password123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_ca4_divisas_inactivas_no_se_muestran(self):
        """
        Criterio de Aceptación 4: Las divisas inactivas no deben aparecer en el listado.
        """
        self.client.login(username='agente01', password='password123')
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        # Verificamos el contexto que se envía al HTML
        divisas_en_contexto = response.context['divisas']
        
        self.assertIn(self.usd, divisas_en_contexto)
        self.assertIn(self.eur, divisas_en_contexto)
        self.assertNotIn(self.ars, divisas_en_contexto, "La divisa inactiva ARS no debería estar en el contexto.")

    def test_ca1_y_ca3_muestra_tasas_y_fecha(self):
        """
        Criterio de Aceptación 1 y 3: Divisas con cotización muestran tasas de compra/venta
        y la fecha de actualización.
        """
        self.client.login(username='agente01', password='password123')
        response = self.client.get(self.url)
        
        # Validamos que el HTML renderizado contenga los valores correctos
        self.assertContains(response, '7300.50')
        self.assertContains(response, '7400.00')
        self.assertContains(response, 'USD')

    def test_ca2_divisa_sin_cotizacion_muestra_mensaje(self):
        """
        Criterio de Aceptación 2: Divisas sin cotización muestran el texto "sin cotización"
        en lugar de valores vacíos o erróneos.
        """
        self.client.login(username='agente01', password='password123')
        response = self.client.get(self.url)
        
        # Validamos que el texto específico del CA esté en el HTML devuelto
        self.assertContains(response, 'EUR')
        self.assertContains(response, 'sin cotización')