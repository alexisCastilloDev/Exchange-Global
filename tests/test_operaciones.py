"""Pruebas del cálculo de importes para compra y venta de divisas."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.divisas.models import CalculoOperacion, CalculoTriangulacion, Cotizacion, Divisa


User = get_user_model()


class CalculoOperacionTest(TestCase):
    """Verifica tasas, comisión, errores de cotización y vencimiento."""

    def setUp(self):
        """Prepara un cliente asociado y una divisa cotizada."""
        self.usuario = User.objects.create_user(
            username='cliente-operaciones',
            password='password123',
        )
        self.client.login(username='cliente-operaciones', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='OPERACION-001',
            nombre='Cliente',
            apellido='Operación',
            email='cliente-operaciones@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.usd = Divisa.objects.create(
            codigo='USD',
            nombre='Dólar',
            simbolo='$',
            activa=True,
        )
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7300.00'),
            tasa_venta=Decimal('7400.00'),
        )

    def _datos_confirmacion(self, resultado):
        """Arma los campos ocultos que el Paso 2 necesita para confirmar."""
        return {
            'tipo': resultado['tipo'],
            'divisa': str(resultado['divisa'].pk),
            'monto': str(resultado['monto_origen']),
            'cotizacion_id': str(resultado['cotizacion_id']),
            'vence_en_timestamp': str(resultado['vence_en_timestamp']),
        }

    def test_calcular_compra_no_crea_ninguna_transaccion_todavia(self):
        """El Paso 1 solo previsualiza: no persiste nada hasta confirmar."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertContains(response, '747400.00')
        self.assertContains(response, '7400.00')

    def test_confirmar_compra_usa_tasa_venta_y_suma_comision(self):
        """Al confirmar, crea la transacción usando la tasa de venta y sumando la comisión."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )
        resultado = response.context['resultado']

        self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'tipo': 'compra'}),
            self._datos_confirmacion(resultado),
        )

        calculo = CalculoOperacion.objects.get()
        self.assertEqual(calculo.estado, CalculoOperacion.ESTADO_PENDIENTE)
        self.assertEqual(calculo.tasa_aplicada, Decimal('7400.00'))
        self.assertEqual(calculo.comision, Decimal('7400.00'))
        self.assertEqual(calculo.monto_final, Decimal('747400.00'))

    def test_confirmar_venta_usa_tasa_compra_y_resta_comision(self):
        """Al confirmar, crea la transacción usando la tasa de compra y descontando la comisión."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'venta'}),
            {'tipo': 'VENTA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )
        resultado = response.context['resultado']
        self.assertContains(response, 'Importe a recibir')

        response = self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'tipo': 'venta'}),
            self._datos_confirmacion(resultado),
            follow=True,
        )

        calculo = CalculoOperacion.objects.get()
        self.assertEqual(calculo.estado, CalculoOperacion.ESTADO_PENDIENTE)
        self.assertEqual(calculo.tasa_aplicada, Decimal('7300.00'))
        self.assertEqual(calculo.comision, Decimal('7300.00'))
        self.assertEqual(calculo.monto_final, Decimal('722700.00'))

    def test_divisa_sin_cotizacion_impide_calcular(self):
        """Muestra error y no crea cálculo cuando falta una cotización."""
        sin_cotizacion = Divisa.objects.create(
            codigo='BRL',
            nombre='Real',
            simbolo='R$',
            activa=True,
        )
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(sin_cotizacion.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertContains(response, 'no tiene cotización disponible')

    def test_calculo_vencido_debe_recalcularse_antes_de_confirmar(self):
        """Rechaza la confirmación cuando pasó el tiempo de vigencia del cálculo."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )
        resultado = response.context['resultado']
        datos = self._datos_confirmacion(resultado)
        datos['vence_en_timestamp'] = str((timezone.now() - timedelta(seconds=1)).timestamp())

        response = self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'tipo': 'compra'}),
            datos,
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertContains(response, 'El cálculo venció')

    def test_confirmar_rechaza_si_la_cotizacion_cambio_desde_que_se_calculo(self):
        """Si la cotización cambió después de calcular, exige recalcular al confirmar."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )
        resultado = response.context['resultado']

        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7350.00'),
            tasa_venta=Decimal('7450.00'),
        )

        response = self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'tipo': 'compra'}),
            self._datos_confirmacion(resultado),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertContains(response, 'El cálculo venció')

    def test_menu_expone_compra_y_venta(self):
        """Muestra ambos accesos operativos en el menú autenticado."""
        response = self.client.get(reverse('home'))

        self.assertContains(response, reverse('divisas:operar', kwargs={'tipo': 'compra'}))
        self.assertContains(response, reverse('divisas:operar', kwargs={'tipo': 'venta'}))

    def test_menu_no_expone_compra_venta_a_un_analista(self):
        """Oculta compra y venta para usuarios analistas."""
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

        response = self.client.get(reverse('home'))

        self.assertNotContains(response, reverse('divisas:operar', kwargs={'tipo': 'compra'}))
        self.assertNotContains(response, reverse('divisas:operar', kwargs={'tipo': 'venta'}))

    def test_cliente_no_ve_auditoria_de_ultima_actualizacion(self):
        """Oculta fecha y usuario de actualización en tasas para clientes."""
        response = self.client.get(reverse('divisas:tasas_vigentes'))

        self.assertNotContains(response, 'Última actualización')


class CompraDeDivisasTest(TestCase):
    """Verifica los criterios de aceptación de la HU 'Compra de divisas'."""

    def setUp(self):
        """Prepara un cliente activo y una divisa con cotización vigente."""
        self.usuario = User.objects.create_user(
            username='cliente-compra',
            password='password123',
        )
        self.client.login(username='cliente-compra', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='COMPRA-001',
            nombre='Cliente',
            apellido='Compra',
            email='cliente-compra@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.usd = Divisa.objects.create(
            codigo='USD',
            nombre='Dólar',
            simbolo='$',
            activa=True,
        )
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7300.00'),
            tasa_venta=Decimal('7400.00'),
        )

    def _datos_confirmacion(self, resultado):
        """Arma los campos ocultos que el Paso 2 necesita para confirmar."""
        return {
            'tipo': resultado['tipo'],
            'divisa': str(resultado['divisa'].pk),
            'monto': str(resultado['monto_origen']),
            'cotizacion_id': str(resultado['cotizacion_id']),
            'vence_en_timestamp': str(resultado['vence_en_timestamp']),
        }

    def test_compra_valida_calcula_el_importe_y_al_confirmar_crea_transaccion_pendiente(self):
        """Criterio 1: al confirmar, crea la transacción en estado 'Pendiente de confirmación'."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )
        resultado = response.context['resultado']
        self.assertFalse(CalculoOperacion.objects.exists())

        response = self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'tipo': 'compra'}),
            self._datos_confirmacion(resultado),
            follow=True,
        )

        calculo = CalculoOperacion.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calculo.estado, CalculoOperacion.ESTADO_PENDIENTE)
        self.assertEqual(calculo.tasa_aplicada, Decimal('7400.00'))
        self.assertEqual(calculo.monto_final, Decimal('747400.00'))
        self.assertContains(response, 'Pendiente de confirmación')

    def test_monto_negativo_no_crea_transaccion(self):
        """Criterio 2: un monto negativo se rechaza sin crear la transacción."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '-100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())

    def test_monto_cero_no_crea_transaccion(self):
        """Criterio 2: un monto en cero se rechaza sin crear la transacción."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '0'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())

    def test_monto_no_numerico_no_crea_transaccion(self):
        """Criterio 2: un monto no numérico se rechaza sin crear la transacción."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': 'abc'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())

    def test_divisa_inactiva_rechaza_la_operacion(self):
        """Criterio 3: una divisa inactiva no puede usarse para comprar."""
        inactiva = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=False)
        Cotizacion.objects.create(divisa=inactiva, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))

        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(inactiva.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertContains(response, 'inactiva o no está disponible para operar')

    def test_divisa_sin_tasa_vigente_rechaza_la_operacion(self):
        """Criterio 3: una divisa sin cotización vigente se rechaza con mensaje claro."""
        sin_cotizacion = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)

        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(sin_cotizacion.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertContains(response, 'no tiene cotización disponible')

    def test_transaccion_registra_tipo_cliente_divisa_monto_y_fecha(self):
        """Criterio 4: la transacción guarda tipo, cliente activo, divisa, monto y fecha."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )
        resultado = response.context['resultado']

        self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'tipo': 'compra'}),
            self._datos_confirmacion(resultado),
        )

        calculo = CalculoOperacion.objects.get()
        self.assertEqual(calculo.tipo, CalculoOperacion.TIPO_COMPRA)
        self.assertEqual(calculo.cliente, self.cliente)
        self.assertEqual(calculo.divisa, self.usd)
        self.assertEqual(calculo.monto_origen, Decimal('100.00'))
        self.assertIsNotNone(calculo.creado_en)


class VentaDeDivisasTest(TestCase):
    """Verifica los criterios de aceptación de la HU 'Venta de divisas'."""

    def setUp(self):
        """Prepara un cliente activo y una divisa con cotización vigente."""
        self.usuario = User.objects.create_user(
            username='cliente-venta',
            password='password123',
        )
        self.client.login(username='cliente-venta', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='VENTA-001',
            nombre='Cliente',
            apellido='Venta',
            email='cliente-venta@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.usd = Divisa.objects.create(
            codigo='USD',
            nombre='Dólar',
            simbolo='$',
            activa=True,
        )
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7300.00'),
            tasa_venta=Decimal('7400.00'),
        )
        self.url_operar = reverse('divisas:operar', kwargs={'tipo': 'venta'})
        self.url_confirmar = reverse('divisas:confirmar_operacion', kwargs={'tipo': 'venta'})

    def _calcular(self, monto='100', divisa=None):
        """Ejecuta el Paso 1 de una venta y devuelve la respuesta."""
        divisa = divisa or self.usd
        return self.client.post(
            self.url_operar,
            {'tipo': 'VENTA', 'divisa': str(divisa.pk), 'monto': monto},
        )

    def _datos_confirmacion(self, resultado):
        """Arma los campos ocultos que el Paso 2 necesita para confirmar."""
        return {
            'tipo': resultado['tipo'],
            'divisa': str(resultado['divisa'].pk),
            'monto': str(resultado['monto_origen']),
            'cotizacion_id': str(resultado['cotizacion_id']),
            'vence_en_timestamp': str(resultado['vence_en_timestamp']),
        }

    def test_venta_valida_calcula_el_importe_y_al_confirmar_crea_transaccion_pendiente(self):
        """Criterio 1: calcula con la tasa de compra y crea la transacción 'Pendiente de confirmación'."""
        response = self._calcular()
        resultado = response.context['resultado']

        self.assertEqual(response.status_code, 200)
        self.assertEqual(resultado['tasa_aplicada'], Decimal('7300.00'))
        self.assertEqual(resultado['comision'], Decimal('7300.00'))
        self.assertEqual(resultado['monto_final'], Decimal('722700.00'))
        self.assertContains(response, 'Importe a recibir')
        self.assertFalse(CalculoOperacion.objects.exists())

        response = self.client.post(
            self.url_confirmar,
            self._datos_confirmacion(resultado),
            follow=True,
        )

        calculo = CalculoOperacion.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calculo.estado, CalculoOperacion.ESTADO_PENDIENTE)
        self.assertEqual(calculo.tasa_aplicada, Decimal('7300.00'))
        self.assertEqual(calculo.monto_final, Decimal('722700.00'))
        self.assertContains(response, 'Pendiente de confirmación')
        self.assertContains(response, 'Importe a recibir: 722700.00 PYG')

    def test_venta_usa_la_comision_del_cliente_activo(self):
        """Criterio 1: la comisión del cliente activo se descuenta del importe a recibir."""
        self.cliente.comision_personalizada = Decimal('2.000')
        self.cliente.save(update_fields=['comision_personalizada'])

        resultado = self._calcular().context['resultado']

        self.assertEqual(resultado['comision_porcentaje'], Decimal('2.000'))
        self.assertEqual(resultado['comision'], Decimal('14600.00'))
        self.assertEqual(resultado['monto_final'], Decimal('715400.00'))

    def test_monto_negativo_no_crea_transaccion(self):
        """Criterio 2: un monto negativo muestra un error de validación sin crear la transacción."""
        response = self._calcular(monto='-100')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertIsNone(response.context['resultado'])
        self.assertContains(response, 'El monto debe ser mayor que cero.')

    def test_monto_cero_no_crea_transaccion(self):
        """Criterio 2: un monto en cero muestra un error de validación sin crear la transacción."""
        response = self._calcular(monto='0')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertIsNone(response.context['resultado'])
        self.assertContains(response, 'El monto debe ser mayor que cero.')

    def test_monto_no_numerico_no_crea_transaccion(self):
        """Criterio 2: un monto no numérico muestra un error de validación sin crear la transacción."""
        response = self._calcular(monto='abc')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertIsNone(response.context['resultado'])
        self.assertContains(response, 'El monto debe ser un número válido.')

    def test_monto_invalido_en_la_confirmacion_no_crea_transaccion(self):
        """Criterio 2: aunque se manipulen los campos ocultos, un monto inválido no crea nada."""
        datos = self._datos_confirmacion(self._calcular().context['resultado'])
        for monto in ('-5', '0', 'abc'):
            datos['monto'] = monto

            self.client.post(self.url_confirmar, datos)

        self.assertFalse(CalculoOperacion.objects.exists())

    def test_divisa_inactiva_rechaza_la_operacion(self):
        """Criterio 3: una divisa inactiva se rechaza con un mensaje claro."""
        inactiva = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=False)
        Cotizacion.objects.create(divisa=inactiva, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))

        response = self._calcular(divisa=inactiva)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertIsNone(response.context['resultado'])
        self.assertContains(response, 'inactiva o no está disponible para operar')

    def test_divisa_dada_de_baja_antes_de_confirmar_rechaza_la_operacion(self):
        """Criterio 3: si la divisa se desactiva entre el cálculo y la confirmación, no se crea nada."""
        resultado = self._calcular().context['resultado']
        self.usd.activa = False
        self.usd.save(update_fields=['activa'])

        response = self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())

    def test_divisa_sin_tasa_vigente_rechaza_la_operacion(self):
        """Criterio 3: una divisa sin cotización vigente se rechaza con un mensaje claro."""
        sin_cotizacion = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)

        response = self._calcular(divisa=sin_cotizacion)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertIsNone(response.context['resultado'])
        self.assertContains(response, 'no tiene cotización disponible')

    def test_divisa_sin_tasa_vigente_en_la_confirmacion_rechaza_la_operacion(self):
        """Criterio 3: sin cotización al confirmar, avisa que no hay tasa y no crea la transacción."""
        resultado = self._calcular().context['resultado']
        Cotizacion.objects.filter(divisa=self.usd).delete()

        response = self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertContains(response, 'no tiene cotización disponible')

    def test_transaccion_registra_tipo_cliente_divisa_monto_y_fecha(self):
        """Criterio 4: la transacción guarda tipo 'Venta', cliente activo, divisa, monto y fecha."""
        resultado = self._calcular().context['resultado']

        self.client.post(self.url_confirmar, self._datos_confirmacion(resultado))

        calculo = CalculoOperacion.objects.get()
        self.assertEqual(calculo.tipo, CalculoOperacion.TIPO_VENTA)
        self.assertEqual(calculo.get_tipo_display(), 'Venta')
        self.assertEqual(calculo.cliente, self.cliente)
        self.assertEqual(calculo.usuario, self.usuario)
        self.assertEqual(calculo.divisa, self.usd)
        self.assertEqual(calculo.codigo_divisa, 'USD')
        self.assertEqual(calculo.monto_origen, Decimal('100.00'))
        self.assertIsNotNone(calculo.creado_en)

    def test_transaccion_se_registra_para_el_cliente_activo_seleccionado(self):
        """Criterio 4: con varios clientes asociados, queda a nombre del cliente activo elegido."""
        otro_cliente = Cliente.objects.create(
            identificador='VENTA-002',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente-venta@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(otro_cliente)
        session = self.client.session
        session['cliente_activo_id'] = otro_cliente.pk
        session.save()

        resultado = self._calcular().context['resultado']
        self.client.post(self.url_confirmar, self._datos_confirmacion(resultado))

        self.assertEqual(CalculoOperacion.objects.get().cliente, otro_cliente)

    def test_usuario_con_varios_clientes_sin_seleccionar_ninguno_no_puede_vender(self):
        """Sin cliente activo seleccionado se le pide elegir uno y no se crea la transacción."""
        otro_cliente = Cliente.objects.create(
            identificador='VENTA-003',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente-venta-3@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(otro_cliente)

        response = self._calcular()

        self.assertRedirects(response, reverse('seleccionar_cliente'), fetch_redirect_response=False)
        self.assertFalse(CalculoOperacion.objects.exists())

    def test_un_administrador_no_puede_vender_divisas(self):
        """Solo un cliente asociado puede operar: el staff recibe 403 y no se crea nada."""
        self.usuario.is_staff = True
        self.usuario.save(update_fields=['is_staff'])

        response = self._calcular()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(CalculoOperacion.objects.exists())

    def test_confirmar_con_get_no_crea_transaccion(self):
        """La confirmación solo acepta POST."""
        response = self.client.get(self.url_confirmar)

        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.assertFalse(CalculoOperacion.objects.exists())

    def test_tipo_de_operacion_desconocido_responde_404_sin_crear_transaccion(self):
        """Un tipo distinto de compra o venta no puede registrar transacciones."""
        resultado = self._calcular().context['resultado']

        response = self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'tipo': 'canje'}),
            self._datos_confirmacion(resultado),
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertEqual(
            self.client.get(reverse('divisas:operar', kwargs={'tipo': 'canje'})).status_code,
            404,
        )

    def test_la_venta_confirmada_aparece_en_el_historial_de_transacciones(self):
        """La venta registrada se ve como 'Venta' para administración y análisis."""
        resultado = self._calcular().context['resultado']
        self.client.post(self.url_confirmar, self._datos_confirmacion(resultado))
        User.objects.create_user(username='admin-venta', password='password123')
        self.client.login(username='admin-venta', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertContains(response, 'Venta')
        self.assertContains(response, 'Cliente Venta')
        self.assertContains(response, 'Pendiente de confirmación')


class TriangulacionOperacionTest(TestCase):
    """Verifica el cambio entre divisas extranjeras triangulando por PYG."""

    def setUp(self):
        """Prepara un cliente asociado y dos divisas extranjeras cotizadas."""
        self.usuario = User.objects.create_user(
            username='cliente-triangulacion',
            password='password123',
        )
        self.client.login(username='cliente-triangulacion', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='TRIANGULACION-001',
            nombre='Cliente',
            apellido='Triangulación',
            email='cliente-triangulacion@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))
        self.url_cambio = reverse('divisas:triangulacion')
        self.url_confirmar = reverse('divisas:confirmar_triangulacion')

    def _calcular(self, origen=None, destino=None, monto='100'):
        """Ejecuta el Paso 1 del cambio y devuelve la respuesta."""
        return self.client.post(
            self.url_cambio,
            {
                'divisa_origen': str((origen or self.usd).pk),
                'divisa_destino': str((destino or self.eur).pk),
                'monto': monto,
            },
        )

    def _datos_confirmacion(self, resultado):
        """Arma los campos ocultos que la confirmación necesita."""
        return {
            'divisa_origen': str(resultado['divisa_origen'].pk),
            'divisa_destino': str(resultado['divisa_destino'].pk),
            'monto': str(resultado['monto_origen']),
            'cotizacion_origen_id': str(resultado['cotizacion_origen_id']),
            'cotizacion_destino_id': str(resultado['cotizacion_destino_id']),
            'vence_en_timestamp': str(resultado['vence_en_timestamp']),
        }

    def test_calcular_desglosa_tasas_cruce_y_comision_sin_crear_transaccion(self):
        """El Paso 1 solo previsualiza: desglosa el importe y no persiste nada."""
        response = self._calcular()
        resultado = response.context['resultado']

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoTriangulacion.objects.exists())
        self.assertEqual(resultado['tasa_compra_aplicada'], Decimal('7300.00'))
        self.assertEqual(resultado['tasa_venta_aplicada'], Decimal('8100.00'))
        self.assertEqual(resultado['tasa_cruzada'], Decimal('0.901235'))
        self.assertEqual(resultado['monto_equivalente_pyg'], Decimal('730000.00'))
        self.assertEqual(resultado['comision'], Decimal('0.90'))
        self.assertEqual(resultado['monto_final'], Decimal('89.22'))
        self.assertContains(response, '89.22')

    def test_confirmar_registra_el_cambio_con_todos_sus_datos(self):
        """Al confirmar se crea la transacción con cliente, estado, tasas, comisión e importe."""
        resultado = self._calcular().context['resultado']

        response = self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

        calculo = CalculoTriangulacion.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calculo.cliente, self.cliente)
        self.assertEqual(calculo.usuario, self.usuario)
        self.assertEqual(calculo.estado, CalculoTriangulacion.ESTADO_PENDIENTE)
        self.assertEqual(calculo.divisa_origen, self.usd)
        self.assertEqual(calculo.divisa_destino, self.eur)
        self.assertEqual(calculo.codigo_divisa_origen, 'USD')
        self.assertEqual(calculo.codigo_divisa_destino, 'EUR')
        self.assertEqual(calculo.monto_origen, Decimal('100.00'))
        self.assertEqual(calculo.tasa_compra_aplicada, Decimal('7300.00'))
        self.assertEqual(calculo.tasa_venta_aplicada, Decimal('8100.00'))
        self.assertEqual(calculo.tasa_cruzada, Decimal('0.901235'))
        self.assertEqual(calculo.monto_equivalente_pyg, Decimal('730000.00'))
        self.assertEqual(calculo.comision, Decimal('0.90'))
        self.assertEqual(calculo.monto_final, Decimal('89.22'))
        self.assertIsNotNone(calculo.creado_en)
        self.assertContains(response, 'Pendiente de confirmación')
        self.assertContains(response, 'Importe a recibir: 89.22 EUR')

    def test_confirmar_recalcula_con_datos_del_servidor_y_no_con_los_del_navegador(self):
        """Los importes no viajan desde el navegador: se recalculan al confirmar."""
        resultado = self._calcular().context['resultado']
        datos = self._datos_confirmacion(resultado)
        datos['monto_final'] = '999999.00'
        datos['comision'] = '0.00'

        self.client.post(self.url_confirmar, datos)

        calculo = CalculoTriangulacion.objects.get()
        self.assertEqual(calculo.monto_final, Decimal('89.22'))
        self.assertEqual(calculo.comision, Decimal('0.90'))

    def test_divisa_destino_sin_cotizacion_impide_triangular(self):
        """Muestra error y no permite continuar si falta una cotización."""
        sin_cotizacion = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)

        response = self._calcular(destino=sin_cotizacion)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['resultado'])
        self.assertFalse(CalculoTriangulacion.objects.exists())
        self.assertContains(response, 'no tiene cotización disponible')

    def test_rechaza_la_misma_divisa_en_origen_y_destino(self):
        """No permite triangular una divisa contra sí misma."""
        response = self._calcular(destino=self.usd)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoTriangulacion.objects.exists())
        self.assertContains(response, 'Debe seleccionar dos divisas distintas')

    def test_calculo_triangulado_vencido_debe_recalcularse_antes_de_confirmar(self):
        """Rechaza la confirmación cuando el cálculo ya superó su vigencia."""
        datos = self._datos_confirmacion(self._calcular().context['resultado'])
        datos['vence_en_timestamp'] = str((timezone.now() - timedelta(seconds=1)).timestamp())

        response = self.client.post(self.url_confirmar, datos, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoTriangulacion.objects.exists())
        self.assertContains(response, 'El cálculo venció')

    def test_confirmar_rechaza_si_una_cotizacion_cambio_desde_que_se_calculo(self):
        """Si cambia la cotización de cualquiera de las dos divisas, exige recalcular."""
        resultado = self._calcular().context['resultado']
        Cotizacion.objects.create(
            divisa=self.eur,
            tasa_compra=Decimal('7950.00'),
            tasa_venta=Decimal('8150.00'),
        )

        response = self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

        self.assertFalse(CalculoTriangulacion.objects.exists())
        self.assertContains(response, 'El cálculo venció')

    def test_confirmar_sin_cotizacion_vigente_no_crea_transaccion(self):
        """Si una divisa pierde su cotización antes de confirmar, informa y no registra nada."""
        resultado = self._calcular().context['resultado']
        Cotizacion.objects.filter(divisa=self.eur).delete()

        response = self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

        self.assertFalse(CalculoTriangulacion.objects.exists())
        self.assertContains(response, 'no tiene cotización disponible')

    def test_confirmar_con_divisa_inactiva_no_crea_transaccion(self):
        """Una divisa dada de baja entre el cálculo y la confirmación impide registrar el cambio."""
        resultado = self._calcular().context['resultado']
        self.eur.activa = False
        self.eur.save(update_fields=['activa'])

        self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

        self.assertFalse(CalculoTriangulacion.objects.exists())

    def test_confirmar_con_monto_invalido_no_crea_transaccion(self):
        """Montos negativos, en cero o no numéricos en los campos ocultos no registran nada."""
        datos = self._datos_confirmacion(self._calcular().context['resultado'])
        for monto in ('-5', '0', 'abc'):
            datos['monto'] = monto

            self.client.post(self.url_confirmar, datos)

        self.assertFalse(CalculoTriangulacion.objects.exists())

    def test_cambio_se_registra_para_el_cliente_activo_seleccionado(self):
        """Con varios clientes asociados, queda a nombre del cliente activo elegido."""
        otro_cliente = Cliente.objects.create(
            identificador='TRIANGULACION-002',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente-triangulacion@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(otro_cliente)
        session = self.client.session
        session['cliente_activo_id'] = otro_cliente.pk
        session.save()

        resultado = self._calcular().context['resultado']
        self.client.post(self.url_confirmar, self._datos_confirmacion(resultado))

        self.assertEqual(CalculoTriangulacion.objects.get().cliente, otro_cliente)

    def test_confirmar_con_get_no_crea_transaccion(self):
        """La confirmación solo acepta POST."""
        response = self.client.get(self.url_confirmar)

        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.assertFalse(CalculoTriangulacion.objects.exists())

    def test_un_administrador_no_puede_confirmar_un_cambio(self):
        """Solo un cliente asociado puede confirmar: el staff no registra nada."""
        resultado = self._calcular().context['resultado']
        self.usuario.is_staff = True
        self.usuario.save(update_fields=['is_staff'])

        self.client.post(self.url_confirmar, self._datos_confirmacion(resultado))

        self.assertFalse(CalculoTriangulacion.objects.exists())


class HistorialTransaccionesTest(TestCase):
    """Verifica el historial de transacciones para administración y análisis."""

    def setUp(self):
        """Prepara un cliente, una divisa cotizada y una transacción registrada."""
        self.usuario = User.objects.create_user(
            username='cliente-historial',
            password='password123',
        )
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='HISTORIAL-001',
            nombre='Cliente',
            apellido='Historial',
            email='cliente-historial@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7300.00'),
            tasa_venta=Decimal('7400.00'),
        )
        self.transaccion = CalculoOperacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd,
            codigo_divisa='USD',
            monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'),
            monto_final=Decimal('747400.00'),
            vence_en=timezone.now() + timedelta(seconds=300),
        )

    def _login_como(self, rol):
        """Autentica un usuario de staff con el rol de Keycloak indicado."""
        staff = User.objects.create_user(username=f'staff-{rol}', password='password123')
        self.client.login(username=f'staff-{rol}', password='password123')
        session = self.client.session
        session['keycloak_roles'] = [rol]
        session.save()
        return staff

    def test_administrador_puede_ver_el_historial(self):
        """El rol admin accede al historial de transacciones."""
        self._login_como('admin')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertEqual(response.status_code, 200)

    def test_analista_cambiario_puede_ver_el_historial(self):
        """El rol analista_cambiario accede al historial de transacciones."""
        self._login_como('analista_cambiario')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertEqual(response.status_code, 200)

    def test_cliente_no_puede_ver_el_historial(self):
        """Un rol cliente no puede acceder al historial administrativo."""
        self._login_como('cliente')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertEqual(response.status_code, 403)

    def test_historial_muestra_tipo_estado_cliente_divisa_monto_y_fecha(self):
        """Cada fila expone tipo, estado, cliente activo, divisa, monto y fecha."""
        self._login_como('admin')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertContains(response, 'Compra')
        self.assertContains(response, 'Pendiente de confirmación')
        self.assertContains(response, 'Cliente Historial')
        self.assertContains(response, 'USD')
        self.assertContains(response, '100.00')
        self.assertContains(response, self.transaccion.creado_en.strftime('%d/%m/%Y'))

    def test_historial_incluye_transacciones_de_todos_los_clientes(self):
        """El historial no se limita a un único cliente, a diferencia de las vistas del cliente."""
        otro_usuario = User.objects.create_user(username='cliente-historial-2', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario,
            identificador='HISTORIAL-002',
            nombre='Otro',
            apellido='Cliente',
            email='cliente-historial-2@test.com',
            is_active=True,
        )
        CalculoOperacion.objects.create(
            usuario=otro_usuario,
            cliente=otro_cliente,
            tipo=CalculoOperacion.TIPO_VENTA,
            divisa=self.usd,
            codigo_divisa='USD',
            monto_origen=Decimal('50.00'),
            tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('365.00'),
            monto_final=Decimal('364635.00'),
            vence_en=timezone.now() + timedelta(seconds=300),
        )
        self._login_como('admin')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertContains(response, 'Cliente Historial')
        self.assertContains(response, 'Otro Cliente')

    def test_historial_incluye_los_cambios_entre_divisas_con_sus_datos(self):
        """El cambio figura como 'Cambio' con cliente, divisas, monto, tasa, comisión e importe."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        Cotizacion.objects.create(divisa=eur, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))
        CalculoTriangulacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            divisa_origen=self.usd,
            divisa_destino=eur,
            codigo_divisa_origen='USD',
            codigo_divisa_destino='EUR',
            monto_origen=Decimal('250.00'),
            tasa_compra_aplicada=Decimal('7300.00'),
            tasa_venta_aplicada=Decimal('8100.00'),
            tasa_cruzada=Decimal('0.901235'),
            monto_equivalente_pyg=Decimal('1825000.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('2.25'),
            monto_final=Decimal('223.06'),
            vence_en=timezone.now() + timedelta(seconds=300),
        )
        self._login_como('admin')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertContains(response, 'Cambio')
        self.assertContains(response, 'USD → EUR')
        self.assertContains(response, '250.00')
        self.assertContains(response, '0.901235')
        self.assertContains(response, '2.25 EUR')
        self.assertContains(response, '223.06 EUR')
        self.assertContains(response, 'Pendiente de confirmación')
        self.assertContains(response, 'Cliente Historial')
        self.assertEqual(len(response.context['transacciones']), 2)

    def test_cambio_confirmado_por_el_cliente_aparece_en_el_historial(self):
        """Flujo completo: calcular y confirmar un cambio lo deja visible para el analista."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        Cotizacion.objects.create(divisa=eur, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))
        self.client.login(username='cliente-historial', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        resultado = self.client.post(
            reverse('divisas:triangulacion'),
            {'divisa_origen': str(self.usd.pk), 'divisa_destino': str(eur.pk), 'monto': '100'},
        ).context['resultado']
        self.client.post(
            reverse('divisas:confirmar_triangulacion'),
            {
                'divisa_origen': str(self.usd.pk),
                'divisa_destino': str(eur.pk),
                'monto': '100.00',
                'cotizacion_origen_id': str(resultado['cotizacion_origen_id']),
                'cotizacion_destino_id': str(resultado['cotizacion_destino_id']),
                'vence_en_timestamp': str(resultado['vence_en_timestamp']),
            },
        )
        self._login_como('analista_cambiario')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertContains(response, 'USD → EUR')
        self.assertContains(response, '89.22 EUR')

    def test_historial_ordena_compras_ventas_y_cambios_del_mas_reciente_al_mas_antiguo(self):
        """Las tres clases de transacción se mezclan en una única lista ordenada por fecha."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        cambio = CalculoTriangulacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            divisa_origen=self.usd,
            divisa_destino=eur,
            codigo_divisa_origen='USD',
            codigo_divisa_destino='EUR',
            monto_origen=Decimal('10.00'),
            tasa_compra_aplicada=Decimal('7300.00'),
            tasa_venta_aplicada=Decimal('8100.00'),
            tasa_cruzada=Decimal('0.901235'),
            monto_equivalente_pyg=Decimal('73000.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('0.09'),
            monto_final=Decimal('8.92'),
            vence_en=timezone.now() + timedelta(seconds=300),
        )
        self._login_como('admin')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        tipos = [fila['tipo'] for fila in response.context['transacciones']]
        self.assertEqual(tipos, ['Cambio', 'Compra'])
        self.assertGreater(cambio.creado_en, self.transaccion.creado_en)
