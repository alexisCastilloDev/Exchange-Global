"""Pruebas de permisos, validaciones y ciclo de vida de métodos de pago."""

from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse
from apps.clientes.forms import MetodoPagoForm
from apps.clientes.models import Cliente, MetodoPago
from apps.clientes.validacion_sipap import SipapComunicacionError

User = get_user_model()

RESPUESTA_SIPAP_VALIDA = {
    'valida': True, 'titular': 'Juan Pérez', 'proveedor': 'Banco Itaú Paraguay', 'moneda': 'PYG',
}

class MetodoPagoTestCase(TestCase):
    """Verifica la gestión segura de métodos de pago del cliente activo."""
    """
    Pruebas unitarias para validar los criterios de aceptación de la historia GE-19.
    """

    def setUp(self):
        """Prepara usuario cliente, asociación y datos bancarios."""
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
        """Deniega métodos de pago a quien no tiene rol cliente."""
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertRedirects(response, reverse('home'))

    def test_administrador_no_puede_gestionar_metodos(self):
        """Mantiene separado el acceso administrativo del acceso cliente."""
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertRedirects(response, reverse('home'))

    def test_cliente_sin_clientes_asignados_no_puede_ver_metodos(self):
        """Deniega métodos de pago sin clientes asociados."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.user.clientes.all().delete()

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertRedirects(response, reverse('home'))

    def test_menu_no_muestra_metodos_sin_rol_cliente(self):
        """Oculta el acceso de métodos de pago a roles no clientes."""
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

        response = self.client.get(reverse('home'))

        self.assertNotContains(response, 'Métodos de pago')

    @patch('apps.clientes.forms.validar_cuenta')
    def test_registro_metodo_pago_exitoso(self, mock_validar):
        """Criterio 1: Registro exitoso de método de pago, anclado al cliente activo.

        El titular y el banco no los manda el formulario: los completa
        sipap-sim al confirmar que la cuenta existe (ver
        ``apps.clientes.validacion_sipap.validar_cuenta``).
        """
        mock_validar.return_value = RESPUESTA_SIPAP_VALIDA

        response = self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_TRANSFERENCIA,
            'numero_cuenta': '2000000000000101',
            'documento_titular': '3456789',
            'tipo_cuenta': 'AHORRO',
            'es_predeterminado': True
        })
        self.assertEqual(response.status_code, 302)
        mock_validar.assert_called_once_with('2000000000000101', '3456789')
        metodo = MetodoPago.objects.get(cliente=self.cliente)
        self.assertEqual(metodo.nombre_titular, 'Juan Pérez')
        self.assertEqual(metodo.entidad_financiera, 'Banco Itaú Paraguay')
        self.assertEqual(metodo.documento_titular, '3456789')

    def test_validacion_campos_incompletos(self):
        """Criterio 2: Muestra errores de validación si faltan datos requeridos."""
        response = self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_TRANSFERENCIA,
            'numero_cuenta': '',  # Incompleto a propósito
            'documento_titular': '',
            'tipo_cuenta': ''
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertFormError(form, 'numero_cuenta', 'El número de cuenta es obligatorio.')
        self.assertFormError(form, 'documento_titular', 'El CI o RUC del titular es obligatorio.')
        self.assertFormError(form, 'tipo_cuenta', 'Debe seleccionar el tipo de cuenta.')
        self.assertEqual(MetodoPago.objects.filter(cliente=self.cliente).count(), 0)

    @patch('apps.clientes.forms.validar_cuenta')
    def test_rechaza_una_cuenta_que_no_existe_en_sipap(self, mock_validar):
        """No se guarda nada si sipap-sim no encuentra la cuenta con ese número y documento."""
        mock_validar.return_value = {'valida': False}

        response = self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_TRANSFERENCIA,
            'numero_cuenta': '0000000000000000',
            'documento_titular': '0000000',
            'tipo_cuenta': 'AHORRO',
        })

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertFormError(form, 'numero_cuenta', 'No encontramos ninguna cuenta con ese número y ese documento. Verificá los datos.')
        self.assertEqual(MetodoPago.objects.filter(cliente=self.cliente).count(), 0)

    @patch('apps.clientes.forms.validar_cuenta')
    def test_no_guarda_nada_si_sipap_sim_no_responde(self, mock_validar):
        """Sin forma de verificar la cuenta, se rechaza el alta en vez de guardarla a ciegas."""
        mock_validar.side_effect = SipapComunicacionError('no se pudo conectar')

        response = self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_BILLETERA,
            'numero_cuenta': '2000000000000501',
            'documento_titular': '3456789',
        })

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('No se pudo verificar la cuenta', form.non_field_errors()[0])
        self.assertEqual(MetodoPago.objects.filter(cliente=self.cliente).count(), 0)

    @patch('apps.clientes.forms.validar_cuenta')
    def test_billetera_no_exige_tipo_de_cuenta(self, mock_validar):
        """Una billetera digital no tiene 'caja de ahorro' ni 'cuenta corriente': no se le pide."""
        mock_validar.return_value = {
            'valida': True, 'titular': 'Juan Pérez', 'proveedor': 'Tigo Money', 'moneda': 'PYG',
        }

        response = self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_BILLETERA,
            'numero_cuenta': '2000000000000501',
            'documento_titular': '3456789',
        })

        self.assertEqual(response.status_code, 302)
        metodo = MetodoPago.objects.get(cliente=self.cliente)
        self.assertEqual(metodo.entidad_financiera, 'Tigo Money')
        self.assertIsNone(metodo.tipo_cuenta)

    def test_listar_metodos_pago(self):
        """Criterio 3: El cliente puede ver los métodos del cliente activo."""
        MetodoPago.objects.create(
            cliente=self.cliente,
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
        """Comprueba censura inicial y revelación por el titular."""
        metodo = MetodoPago.objects.create(
            cliente=self.cliente,
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
        """Verifica que revelar un método no revele los demás."""
        primer_metodo = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco Uno',
            numero_cuenta='111111111',
            tipo_cuenta='AHORRO'
        )
        segundo_metodo = MetodoPago.objects.create(
            cliente=self.cliente,
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

    def test_usuario_no_puede_revelar_metodo_de_otro_cliente(self):
        """Impide revelar métodos que no pertenecen al cliente activo."""
        titular = User.objects.create_user(
            username='titular_test',
            password='password123'
        )
        otro_cliente = Cliente.objects.create(
            user=titular,
            identificador='CI-TEST-1',
            nombre='Titular',
            email='titular@test.com'
        )
        metodo = MetodoPago.objects.create(
            cliente=otro_cliente,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Titular',
            entidad_financiera='Banco Seguro',
            numero_cuenta='123456789',
            tipo_cuenta='AHORRO'
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))
        self.assertNotContains(response, '*****789')
        self.assertNotContains(response, '123456789')

        response = self.client.post(
            reverse('clientes:metodo_pago_reveal', args=[metodo.pk]),
            follow=True
        )
        self.assertNotContains(response, '123456789')

    def test_cambiar_cliente_activo_cambia_los_metodos_visibles(self):
        """Un operador con varios clientes ve solo los métodos del cliente activo."""
        # Con un único cliente asociado, la sesión ya lo deja seleccionado
        # como activo antes de asociar un segundo cliente.
        self.client.get(reverse('clientes:metodo_pago_list'))

        otro_cliente = Cliente.objects.create(
            identificador='CI-TEST-2',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente@test.com',
            is_active=True,
        )
        otro_cliente.usuarios.add(self.user)

        MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco Propio',
            numero_tarjeta='4111111111111111',
        )
        MetodoPago.objects.create(
            cliente=otro_cliente,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Otro Cliente',
            entidad_financiera='Banco Ajeno',
            numero_tarjeta='4222222222222222',
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))
        self.assertContains(response, 'Banco Propio')
        self.assertNotContains(response, 'Banco Ajeno')

        self.client.post(reverse('cambiar_cliente', args=[otro_cliente.pk]))
        response = self.client.get(reverse('clientes:metodo_pago_list'))
        self.assertContains(response, 'Banco Ajeno')
        self.assertNotContains(response, 'Banco Propio')

    def test_no_existe_ninguna_opcion_para_editar_un_metodo_de_pago(self):
        """Criterio 4 (adaptado): un método de pago ya no se edita, solo se elimina.

        Para cambiar algo, el flujo esperado es eliminar el método y crear
        uno nuevo; no hay ninguna URL de edición expuesta.
        """
        metodo = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Sudameris',
            numero_cuenta='987654',
            tipo_cuenta='CORRIENTE'
        )

        with self.assertRaises(NoReverseMatch):
            reverse('clientes:metodo_pago_update', args=[metodo.pk])

        response = self.client.get(reverse('clientes:metodo_pago_list'))
        self.assertNotContains(response, 'Editar')

    def test_eliminar_metodo_pago(self):
        """Criterio 5: Eliminar un método de pago."""
        metodo = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Visa Bank',
            numero_tarjeta='4123412341234123'
        )
        response = self.client.post(reverse('clientes:metodo_pago_delete', args=[metodo.pk]))
        self.assertEqual(MetodoPago.objects.filter(pk=metodo.pk).count(), 0)

    def test_solo_un_metodo_predeterminado(self):
        """Criterio 6: Solo un método de pago puede estar marcado como predeterminado."""
        metodo1 = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco A',
            numero_tarjeta='4111111111111111',
            es_predeterminado=True
        )
        metodo2 = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco B',
            numero_tarjeta='4222222222222222',
            es_predeterminado=True
        )

        metodo1.refresh_from_db()
        metodo2.refresh_from_db()

        self.assertFalse(metodo1.es_predeterminado)
        self.assertTrue(metodo2.es_predeterminado)


class MetodoPagoFormStripeTest(TestCase):
    """Verifica que 'Tarjeta' quede reservada al alta vía Stripe (HU 'Pago con tarjeta vía Stripe')."""

    def setUp(self):
        """Prepara un cliente con una tarjeta ya vinculada a Stripe."""
        self.user = User.objects.create_user(
            username='cliente-form-stripe', email='form-stripe@test.com', password='password123',
        )
        self.cliente = Cliente.objects.create(
            user=self.user, identificador='CI-FORM-STRIPE-001', nombre='Lucía', apellido='Gómez',
            email='form-stripe@test.com', is_active=True,
        )

    def test_el_formulario_de_alta_no_ofrece_tarjeta_como_opcion(self):
        """Al crear, 'Tarjeta' no aparece: esa alta pasa siempre por Stripe."""
        form = MetodoPagoForm()

        valores = [valor for valor, _ in form.fields['tipo_medio'].choices]

        self.assertNotIn(MetodoPago.TIPO_TARJETA, valores)
        self.assertIn(MetodoPago.TIPO_TRANSFERENCIA, valores)
        self.assertIn(MetodoPago.TIPO_BILLETERA, valores)

    def test_el_formulario_rechaza_crear_una_tarjeta_directamente(self):
        """Ni mandando 'TARJETA' a mano se puede crear una tarjeta por este formulario."""
        form = MetodoPagoForm(data={
            'tipo_medio': MetodoPago.TIPO_TARJETA,
            'nombre_titular': 'Lucía Gómez',
            'entidad_financiera': 'Visa',
            'numero_tarjeta': '4111111111111111',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('tipo_medio', form.errors)
