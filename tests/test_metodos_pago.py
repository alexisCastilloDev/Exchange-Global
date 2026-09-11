from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.clientes.models import Cliente, MetodoPago

User = get_user_model()

class MetodoPagoTestCase(TestCase):
    """
    Pruebas unitarias para validar los criterios de aceptación de la historia GE-19.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='cliente_test',
            email='cliente@test.com',
            password='password123'
        )
        self.cliente = Cliente.objects.create(
            user=self.user,
            identificador='CI-CLIENTE-001',
            nombre='Juan',
            apellido='Pérez',
            email='cliente@test.com',
            is_active=True,
        )
        self.user.clientes.add(self.cliente)
        self.client.login(username='cliente_test', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

    def test_usuario_sin_rol_cliente_no_puede_gestionar_metodos(self):
        session = self.client.session
        session['keycloak_roles'] = ['agente']
        session.save()

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertRedirects(response, reverse('home'))

    def test_administrador_no_puede_gestionar_metodos(self):
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertRedirects(response, reverse('home'))

    def test_cliente_sin_clientes_asignados_no_puede_ver_metodos(self):
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.user.clientes.all().delete()

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertRedirects(response, reverse('home'))

    def test_menu_no_muestra_metodos_sin_rol_cliente(self):
        session = self.client.session
        session['keycloak_roles'] = ['agente']
        session.save()

        response = self.client.get(reverse('home'))

        self.assertNotContains(response, 'Métodos de pago')

    def test_registro_metodo_pago_exitoso(self):
        """Criterio 1: Registro exitoso de método de pago."""
        response = self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_TRANSFERENCIA,
            'nombre_titular': 'Juan Pérez',
            'entidad_financiera': 'Banco Itaú',
            'numero_cuenta': '123456789',
            'tipo_cuenta': 'AHORRO',
            'es_predeterminado': True
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MetodoPago.objects.filter(cliente=self.user).count(), 1)

    def test_validacion_campos_incompletos(self):
        """Criterio 2: Muestra errores de validación si faltan datos requeridos."""
        response = self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_TRANSFERENCIA,
            'nombre_titular': 'Juan Pérez',
            'entidad_financiera': 'Banco Itaú',
            'numero_cuenta': '',  # Incompleto a propósito
            'tipo_cuenta': ''
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertFormError(form, 'numero_cuenta', 'El número de cuenta es obligatorio para transferencias bancarias.')

    def test_listar_metodos_pago(self):
        """Criterio 3: El cliente puede ver sus métodos de pago."""
        MetodoPago.objects.create(
            cliente=self.user,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Sudameris',
            numero_cuenta='987654',
            tipo_cuenta='CORRIENTE'
        )
        response = self.client.get(reverse('clientes:metodo_pago_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sudameris')

    def test_numero_cuenta_censurado_por_defecto_y_revelable_por_su_creador(self):
        metodo = MetodoPago.objects.create(
            cliente=self.user,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Sudameris',
            numero_cuenta='987654',
            tipo_cuenta='CORRIENTE'
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))
        self.assertContains(response, '*****654')
        self.assertNotContains(response, '987654')

        response = self.client.post(
            reverse('clientes:metodo_pago_reveal', args=[metodo.pk]),
            follow=True
        )
        self.assertContains(response, '987654')
        self.assertContains(response, 'Ocultar datos')

        response = self.client.post(
            reverse('clientes:metodo_pago_reveal', args=[metodo.pk]),
            follow=True
        )
        self.assertContains(response, '*****654')
        self.assertNotContains(response, '987654')
        self.assertContains(response, 'Ver datos')

    def test_cada_metodo_mantiene_su_propio_estado_de_visualizacion(self):
        primer_metodo = MetodoPago.objects.create(
            cliente=self.user,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco Uno',
            numero_cuenta='111111111',
            tipo_cuenta='AHORRO'
        )
        segundo_metodo = MetodoPago.objects.create(
            cliente=self.user,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco Dos',
            numero_cuenta='222222222',
            tipo_cuenta='CORRIENTE'
        )

        response = self.client.post(
            reverse('clientes:metodo_pago_reveal', args=[primer_metodo.pk]),
            follow=True
        )
        self.assertContains(response, '111111111')
        self.assertContains(response, '*****222')
        self.assertContains(response, 'Ocultar datos')
        self.assertContains(response, 'Ver datos')

        response = self.client.post(
            reverse('clientes:metodo_pago_reveal', args=[segundo_metodo.pk]),
            follow=True
        )
        self.assertContains(response, '111111111')
        self.assertContains(response, '222222222')

    def test_usuario_asociado_no_puede_revelar_metodo_de_otro_usuario(self):
        titular = User.objects.create_user(
            username='titular_test',
            password='password123'
        )
        cliente = Cliente.objects.create(
            user=titular,
            identificador='CI-TEST-1',
            nombre='Titular',
            email='titular@test.com'
        )
        cliente.usuarios.add(self.user)
        metodo = MetodoPago.objects.create(
            cliente=titular,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Titular',
            entidad_financiera='Banco Seguro',
            numero_cuenta='123456789',
            tipo_cuenta='AHORRO'
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))
        self.assertContains(response, '*****789')
        self.assertNotContains(response, '123456789')

        response = self.client.post(
            reverse('clientes:metodo_pago_reveal', args=[metodo.pk]),
            follow=True
        )
        self.assertNotContains(response, '123456789')

    def test_modificar_metodo_pago(self):
        """Criterio 4: Modificar datos de un método existente."""
        metodo = MetodoPago.objects.create(
            cliente=self.user,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Sudameris',
            numero_cuenta='987654',
            tipo_cuenta='CORRIENTE'
        )
        response = self.client.post(reverse('clientes:metodo_pago_update', args=[metodo.pk]), {
            'tipo_medio': MetodoPago.TIPO_TRANSFERENCIA,
            'nombre_titular': 'Juan Pérez Modificado',
            'entidad_financiera': 'Sudameris',
            'numero_cuenta': '987654',
            'tipo_cuenta': 'CORRIENTE'
        })
        metodo.refresh_from_db()
        self.assertEqual(metodo.nombre_titular, 'Juan Pérez Modificado')

    def test_eliminar_metodo_pago(self):
        """Criterio 5: Eliminar un método de pago."""
        metodo = MetodoPago.objects.create(
            cliente=self.user,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Visa Bank',
            ultimos_4_digitos='1234'
        )
        response = self.client.post(reverse('clientes:metodo_pago_delete', args=[metodo.pk]))
        self.assertEqual(MetodoPago.objects.filter(pk=metodo.pk).count(), 0)

    def test_solo_un_metodo_predeterminado(self):
        """Criterio 6: Solo un método de pago puede estar marcado como predeterminado."""
        metodo1 = MetodoPago.objects.create(
            cliente=self.user,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco A',
            ultimos_4_digitos='1111',
            es_predeterminado=True
        )
        metodo2 = MetodoPago.objects.create(
            cliente=self.user,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco B',
            ultimos_4_digitos='2222',
            es_predeterminado=True
        )

        metodo1.refresh_from_db()
        metodo2.refresh_from_db()

        self.assertFalse(metodo1.es_predeterminado)
        self.assertTrue(metodo2.es_predeterminado)