"""Pruebas de permisos, validaciones y ciclo de vida de métodos de pago."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from apps.clientes.forms import MetodoPagoForm
from apps.clientes.models import Cliente, MetodoPago
from apps.clientes.validacion_sipap import SipapComunicacionError
from apps.divisas.models import CalculoOperacion, CalculoTriangulacion, Divisa, Pago

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
        self.assertEqual(metodo.moneda.codigo, 'PYG')

    @patch('apps.clientes.forms.validar_cuenta')
    def test_guarda_la_moneda_que_confirma_sipap_sim(self, mock_validar):
        """La moneda de la cuenta la decide sipap-sim, no el formulario (GE-19 extendida)."""
        usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        mock_validar.return_value = {
            'valida': True, 'titular': 'Juan Pérez', 'proveedor': 'Banco Itaú Paraguay', 'moneda': 'USD',
        }

        self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_TRANSFERENCIA,
            'numero_cuenta': '2000000000000102',
            'documento_titular': '3456789',
            'tipo_cuenta': 'AHORRO',
        })

        metodo = MetodoPago.objects.get(cliente=self.cliente)
        self.assertEqual(metodo.moneda, usd)

    @patch('apps.clientes.forms.validar_cuenta')
    def test_rechaza_una_cuenta_en_una_moneda_que_global_exchange_no_tiene_habilitada(self, mock_validar):
        """Si sipap-sim confirma una moneda que no está dada de alta en Global Exchange, no se guarda nada."""
        mock_validar.return_value = {
            'valida': True, 'titular': 'Juan Pérez', 'proveedor': 'Banco Itaú Paraguay', 'moneda': 'JPY',
        }

        response = self.client.post(reverse('clientes:metodo_pago_create'), {
            'tipo_medio': MetodoPago.TIPO_TRANSFERENCIA,
            'numero_cuenta': '2000000000000103',
            'documento_titular': '3456789',
            'tipo_cuenta': 'AHORRO',
        })

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('JPY', form.non_field_errors()[0])
        self.assertEqual(MetodoPago.objects.filter(cliente=self.cliente).count(), 0)

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

    def test_cada_metodo_muestra_la_divisa_a_la_que_pertenece(self):
        """Para que se entienda en qué divisa opera cada cuenta o billetera, se muestra como badge."""
        pyg = Divisa.objects.get(codigo='PYG')
        MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TRANSFERENCIA, nombre_titular='Juan Pérez',
            entidad_financiera='Sudameris', numero_cuenta='987654', tipo_cuenta='CORRIENTE', moneda=pyg,
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertContains(response, '>PYG<')

    def test_avisa_en_la_subdivision_de_la_divisa_sin_ningun_metodo_registrado(self):
        """Sin ningún medio en una divisa activa, no se puede pagar ni recibir en ella; la subdivisión lo marca."""
        Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        pyg = Divisa.objects.get(codigo='PYG')
        MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TRANSFERENCIA, nombre_titular='Juan Pérez',
            entidad_financiera='Sudameris', numero_cuenta='987654', tipo_cuenta='CORRIENTE', moneda=pyg,
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertContains(response, 'Te falta agregar una cuenta bancaria o billetera en')
        self.assertContains(response, '>USD<')

    def test_no_avisa_si_ya_hay_un_metodo_en_cada_divisa_activa(self):
        """Cubiertas todas las divisas activas, ninguna subdivisión debe marcar que falta un medio."""
        pyg = Divisa.objects.get(codigo='PYG')
        MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TRANSFERENCIA, nombre_titular='Juan Pérez',
            entidad_financiera='Sudameris', numero_cuenta='987654', tipo_cuenta='CORRIENTE', moneda=pyg,
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertNotContains(response, 'Te falta agregar una cuenta bancaria o billetera en')

    def test_cada_divisa_activa_tiene_su_propia_subdivision_aunque_este_vacia(self):
        """Cada divisa activa aparece como su propia sección, agrupando solo sus cuentas/billeteras."""
        usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        pyg = Divisa.objects.get(codigo='PYG')
        MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Juan Pérez',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000001111', moneda=usd,
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        grupos = {grupo['divisa'].codigo: grupo['metodos'] for grupo in response.context['grupos_por_divisa']}
        self.assertIn('USD', grupos)
        self.assertIn('PYG', grupos)
        self.assertEqual(len(grupos['USD']), 1)
        self.assertEqual(grupos['PYG'], [])

    def test_las_tarjetas_quedan_en_su_propia_seccion_separada_de_las_divisas(self):
        """Una tarjeta no aparece agrupada dentro de ninguna divisa, sino en su propia sección."""
        MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TARJETA, nombre_titular='Juan Pérez',
            entidad_financiera='Visa', numero_tarjeta='4111', proveedor_externo=MetodoPago.PROVEEDOR_STRIPE,
            moneda=Divisa.objects.get(codigo='PYG'),
        )

        response = self.client.get(reverse('clientes:metodo_pago_list'))

        self.assertEqual(len(response.context['tarjetas']), 1)
        for grupo in response.context['grupos_por_divisa']:
            self.assertFalse(any(m.tipo_medio == MetodoPago.TIPO_TARJETA for m in grupo['metodos']))

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

    def test_predeterminado_es_independiente_por_divisa(self):
        """Criterio 6: puede haber un predeterminado distinto por cada divisa a la vez."""
        pyg = Divisa.objects.get(codigo=Divisa.CODIGO_BASE)
        usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)

        tarjeta = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Visa Bank',
            numero_tarjeta='4111111111111111',
            moneda=pyg,
        )
        cuenta_usd_1 = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco A',
            numero_cuenta='111111',
            moneda=usd,
        )
        cuenta_usd_2 = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Juan Pérez',
            entidad_financiera='Banco B',
            numero_cuenta='222222',
            moneda=usd,
            es_predeterminado=True,
        )

        tarjeta.refresh_from_db()
        cuenta_usd_1.refresh_from_db()
        cuenta_usd_2.refresh_from_db()

        # La tarjeta (primera y única en PYG) sigue siendo predeterminada en PYG:
        # marcar un predeterminado en USD no le tocó el flag.
        self.assertTrue(tarjeta.es_predeterminado)
        # En USD, el flag pasó del primero (predeterminado automático por ser el
        # primero) al segundo, que se marcó explícitamente.
        self.assertFalse(cuenta_usd_1.es_predeterminado)
        self.assertTrue(cuenta_usd_2.es_predeterminado)


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


class MetodoPagoEtiquetaCortaTest(TestCase):
    """Verifica ``MetodoPago.etiqueta_corta``, usada para identificar cada medio en un <select>."""

    def setUp(self):
        self.user = User.objects.create_user(username='cliente-etiqueta', password='password123')
        self.cliente = Cliente.objects.create(
            user=self.user, identificador='CI-ETIQUETA-001', nombre='Ana', apellido='Ríos',
            email='etiqueta@test.com', is_active=True,
        )
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)

    def test_incluye_tipo_entidad_los_ultimos_digitos_y_la_divisa(self):
        metodo = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Ana Ríos',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000001234', moneda=self.usd,
        )

        etiqueta = metodo.etiqueta_corta

        self.assertIn('Billetera Digital', etiqueta)
        self.assertIn('Tigo Money', etiqueta)
        self.assertIn('1234', etiqueta)
        self.assertNotIn('2000000000001234', etiqueta)
        self.assertIn('USD', etiqueta)

    def test_una_tarjeta_usa_el_numero_de_tarjeta_no_el_de_cuenta(self):
        pyg = Divisa.objects.get(codigo='PYG')
        metodo = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TARJETA, nombre_titular='Ana Ríos',
            entidad_financiera='Visa', numero_tarjeta='4111', moneda=pyg,
        )

        etiqueta = metodo.etiqueta_corta

        self.assertIn('4111', etiqueta)
        self.assertIn('PYG', etiqueta)

    def test_sin_numero_ni_divisa_no_rompe(self):
        metodo = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Ana Ríos',
            entidad_financiera='Tigo Money',
        )

        etiqueta = metodo.etiqueta_corta

        self.assertIn('Billetera Digital', etiqueta)
        self.assertIn('Tigo Money', etiqueta)


class MetodoPagoMovimientosTest(TestCase):
    """Verifica la pantalla de movimientos y saldo de un método de pago propio."""

    def setUp(self):
        """Prepara un cliente logueado con una billetera en USD y una tarjeta."""
        self.user = User.objects.create_user(username='cliente-movs', password='password123')
        self.cliente = Cliente.objects.create(
            user=self.user, identificador='CI-MOVS-001', nombre='Ana', apellido='Movs',
            email='cliente-movs@test.com', is_active=True,
        )
        self.user.clientes.add(self.cliente)
        self.client.login(username='cliente-movs', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.billetera = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Ana Movs',
            entidad_financiera='Tigo Money', numero_cuenta='2000000000009999', documento_titular='9998887',
            moneda=self.usd,
        )
        self.tarjeta = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TARJETA, nombre_titular='Ana Movs',
            entidad_financiera='Visa', numero_tarjeta='4242', proveedor_externo=MetodoPago.PROVEEDOR_STRIPE,
            referencia_externa='pm_test_999', moneda=Divisa.objects.get(codigo='PYG'),
        )

    def _crear_compra(self, medio_destino=None):
        return CalculoOperacion.objects.create(
            usuario=self.user, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_ACREDITADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=medio_destino,
        )

    def test_billetera_muestra_pagos_y_entregas_recibidas_y_el_saldo_real(self):
        """Se usó para pagar una compra y para recibir otra: aparecen los dos movimientos, y el saldo real."""
        compra_pagada_con_ella = self._crear_compra()
        Pago.objects.create(
            calculo_operacion=compra_pagada_con_ella, metodo_pago=self.billetera,
            medio_pago=MetodoPago.TIPO_BILLETERA, proveedor='SIPAP', identificador_externo='SPI-1',
            monto=Decimal('747400.00'),
        )
        self._crear_compra(medio_destino=self.billetera)

        with patch('apps.clientes.views.validar_cuenta') as mock_validar:
            mock_validar.return_value = {
                'valida': True, 'moneda': 'USD', 'saldo': '500.00', 'titular': 'Ana Movs', 'proveedor': 'Tigo Money',
            }
            response = self.client.get(reverse('clientes:metodo_pago_movimientos', kwargs={'pk': self.billetera.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pagaste')
        self.assertContains(response, 'Recibiste')
        self.assertContains(response, '500,00 USD')
        mock_validar.assert_called_once_with(self.billetera.numero_cuenta, self.billetera.documento_titular)

    def test_billetera_avisa_si_sipap_sim_no_responde_sin_romper(self):
        with patch('apps.clientes.views.validar_cuenta') as mock_validar:
            mock_validar.side_effect = SipapComunicacionError('no se pudo conectar')
            response = self.client.get(reverse('clientes:metodo_pago_movimientos', kwargs={'pk': self.billetera.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se pudo conectar con sipap-sim')

    def test_tarjeta_solo_muestra_sus_pagos_sin_consultar_sipap_sim_ni_mostrar_saldo(self):
        compra = self._crear_compra()
        Pago.objects.create(
            calculo_operacion=compra, metodo_pago=self.tarjeta, medio_pago=MetodoPago.TIPO_TARJETA,
            proveedor='STRIPE', identificador_externo='pi_test_1', monto=Decimal('747400.00'),
        )

        with patch('apps.clientes.views.validar_cuenta') as mock_validar:
            response = self.client.get(reverse('clientes:metodo_pago_movimientos', kwargs={'pk': self.tarjeta.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pagaste')
        self.assertContains(response, 'no es el banco emisor de la tarjeta')
        mock_validar.assert_not_called()

    def test_una_tarjeta_nunca_aparece_como_medio_de_destino(self):
        """Una tarjeta nunca es medio_destino de nada; solo debe listarse lo que se pagó con ella."""
        compra_propia = self._crear_compra()
        Pago.objects.create(
            calculo_operacion=compra_propia, metodo_pago=self.tarjeta, medio_pago=MetodoPago.TIPO_TARJETA,
            proveedor='STRIPE', identificador_externo='pi_test_2', monto=Decimal('747400.00'),
        )

        response = self.client.get(reverse('clientes:metodo_pago_movimientos', kwargs={'pk': self.tarjeta.pk}))

        self.assertEqual(response.context['movimientos'].__len__(), 1)
        self.assertEqual(response.context['movimientos'][0]['direccion'], 'pagaste')

    def test_sin_ningun_movimiento_muestra_un_mensaje_vacio(self):
        response = self.client.get(reverse('clientes:metodo_pago_movimientos', kwargs={'pk': self.tarjeta.pk}))

        self.assertContains(response, 'Todavía no hay ningún movimiento')

    def test_un_cambio_entre_divisas_recibido_tambien_cuenta_como_movimiento(self):
        """Un cambio (CalculoTriangulacion), no solo una compra/venta, también puede entregarse acá."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        cambio = CalculoTriangulacion.objects.create(
            usuario=self.user, cliente=self.cliente, divisa_origen=eur, divisa_destino=self.usd,
            codigo_divisa_origen='EUR', codigo_divisa_destino='USD', monto_origen=Decimal('100.00'),
            tasa_compra_aplicada=Decimal('7900.00'), tasa_venta_aplicada=Decimal('7400.00'),
            tasa_cruzada=Decimal('1.067568'), monto_equivalente_pyg=Decimal('790000.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('1.00'), monto_final=Decimal('105.77'),
            estado=CalculoTriangulacion.ESTADO_ACREDITADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(), medio_destino=self.billetera,
        )

        with patch('apps.clientes.views.validar_cuenta') as mock_validar:
            mock_validar.return_value = {'valida': True, 'moneda': 'USD', 'saldo': '0.00'}
            response = self.client.get(reverse('clientes:metodo_pago_movimientos', kwargs={'pk': self.billetera.pk}))

        self.assertEqual(response.status_code, 200)
        movimientos = response.context['movimientos']
        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0]['transaccion'], cambio)
        self.assertEqual(movimientos[0]['url_detalle'], reverse('divisas:detalle_transaccion_cambio', kwargs={'pk': cambio.pk}))

    def test_no_puede_ver_movimientos_de_un_metodo_ajeno(self):
        otro_usuario = User.objects.create_user(username='otro-cliente-movs', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario, identificador='CI-MOVS-002', nombre='Otro', apellido='Cliente',
            email='otro-cliente-movs@test.com', is_active=True,
        )
        otro_usuario.clientes.add(otro_cliente)
        ajeno = MetodoPago.objects.create(
            cliente=otro_cliente, tipo_medio=MetodoPago.TIPO_TARJETA, nombre_titular='Otro Cliente',
            entidad_financiera='Visa', numero_tarjeta='9999', moneda=Divisa.objects.get(codigo='PYG'),
        )

        response = self.client.get(reverse('clientes:metodo_pago_movimientos', kwargs={'pk': ajeno.pk}))

        self.assertRedirects(response, reverse('clientes:metodo_pago_list'))

    def test_usuario_sin_rol_cliente_no_puede_ver(self):
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('clientes:metodo_pago_movimientos', kwargs={'pk': self.billetera.pk}))

        self.assertRedirects(response, reverse('home'))
