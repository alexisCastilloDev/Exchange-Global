"""Pruebas del cálculo de importes para compra y venta de divisas."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    ConfiguracionVigencia,
    Cotizacion,
    Divisa,
)


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

    def test_la_vigencia_configurada_por_el_administrador_se_usa_al_calcular_y_confirmar(self):
        """Los tiempos configurados en ConfiguracionVigencia reemplazan a los de settings."""
        ConfiguracionVigencia.objects.create(
            calculo_vigencia_segundos=120,
            confirmacion_vigencia_segundos=900,
        )

        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )
        resultado = response.context['resultado']
        esperado_calculo = (timezone.now() + timedelta(seconds=120)).timestamp()
        self.assertAlmostEqual(resultado['vence_en_timestamp'], esperado_calculo, delta=5)

        self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'tipo': 'compra'}),
            self._datos_confirmacion(resultado),
        )

        calculo = CalculoOperacion.objects.get()
        esperado_confirmacion = (timezone.now() + timedelta(seconds=900)).timestamp()
        self.assertAlmostEqual(calculo.vence_en.timestamp(), esperado_confirmacion, delta=5)


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
        self.assertContains(response, 'Importe a recibir')
        self.assertContains(response, '722700.00')

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
        self.assertContains(response, 'Importe a recibir')
        self.assertContains(response, '89.22')

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
        self.assertContains(response, timezone.localtime(self.transaccion.creado_en).strftime('%d/%m/%Y'))

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


class MiHistorialTransaccionesTest(TestCase):
    """Verifica la HU 'Consultar el historial de transacciones' para el cliente activo."""

    def setUp(self):
        """Prepara un cliente activo, una divisa cotizada y dos transacciones propias."""
        self.usuario = User.objects.create_user(
            username='cliente-mi-historial',
            password='password123',
        )
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='MIHIST-001',
            nombre='Cliente',
            apellido='Propio',
            email='cliente-mi-historial@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7300.00'),
            tasa_venta=Decimal('7400.00'),
        )
        self.client.login(username='cliente-mi-historial', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.compra = CalculoOperacion.objects.create(
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
            estado=CalculoOperacion.ESTADO_CONFIRMADA,
            confirmado_en=timezone.now(),
            vence_en=timezone.now() + timedelta(seconds=300),
        )
        self.venta = CalculoOperacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            tipo=CalculoOperacion.TIPO_VENTA,
            divisa=self.usd,
            codigo_divisa='USD',
            monto_origen=Decimal('50.00'),
            tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('365.00'),
            monto_final=Decimal('364635.00'),
            estado=CalculoOperacion.ESTADO_CANCELADA,
            vence_en=timezone.now() + timedelta(seconds=300),
        )

    def test_ve_listado_paginado_de_sus_transacciones(self):
        """Criterio 1: el cliente activo ve un listado paginado de sus transacciones."""
        response = self.client.get(reverse('divisas:mis_transacciones'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('page_obj', response.context)
        self.assertEqual(len(response.context['transacciones']), 2)

    def test_historial_pagina_de_a_veinte_transacciones(self):
        """Criterio 1: con más de 20 transacciones propias, el listado pagina de a 20."""
        for _ in range(25):
            CalculoOperacion.objects.create(
                usuario=self.usuario,
                cliente=self.cliente,
                tipo=CalculoOperacion.TIPO_COMPRA,
                divisa=self.usd,
                codigo_divisa='USD',
                monto_origen=Decimal('5.00'),
                tasa_aplicada=Decimal('7400.00'),
                comision_porcentaje=Decimal('1.000'),
                comision=Decimal('37.00'),
                monto_final=Decimal('37037.00'),
                vence_en=timezone.now() + timedelta(seconds=300),
            )

        response = self.client.get(reverse('divisas:mis_transacciones'))

        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['transacciones']), 20)

        response_pagina_2 = self.client.get(reverse('divisas:mis_transacciones'), {'page': 2})
        self.assertEqual(response_pagina_2.status_code, 200)

    def test_no_incluye_transacciones_de_otro_cliente(self):
        """Criterio 1: solo se listan las transacciones del cliente activo, no las de otros."""
        otro_usuario = User.objects.create_user(username='otro-cliente-mi-historial', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario,
            identificador='MIHIST-002',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente-mi-historial@test.com',
            is_active=True,
        )
        CalculoOperacion.objects.create(
            usuario=otro_usuario,
            cliente=otro_cliente,
            tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd,
            codigo_divisa='USD',
            monto_origen=Decimal('10.00'),
            tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('74.00'),
            monto_final=Decimal('74074.00'),
            vence_en=timezone.now() + timedelta(seconds=300),
        )

        response = self.client.get(reverse('divisas:mis_transacciones'))

        self.assertEqual(len(response.context['transacciones']), 2)
        self.assertNotContains(response, 'Otro Cliente')

    def test_cada_fila_muestra_tipo_divisa_monto_tasa_estado_y_fecha(self):
        """Criterio 2: cada fila incluye tipo, divisa, monto, tasa aplicada, estado y fecha."""
        response = self.client.get(reverse('divisas:mis_transacciones'))

        self.assertContains(response, 'Compra')
        self.assertContains(response, 'Confirmada')
        self.assertContains(response, 'USD')
        self.assertContains(response, '100.00')
        self.assertContains(response, '7400.00')
        self.assertContains(response, timezone.localtime(self.compra.creado_en).strftime('%d/%m/%Y'))

    def test_filtro_por_estado_actualiza_el_listado(self):
        """Criterio 3: filtrar por estado deja solo las transacciones que coinciden."""
        response = self.client.get(
            reverse('divisas:mis_transacciones'), {'estado': CalculoOperacion.ESTADO_CANCELADA}
        )

        transacciones = response.context['transacciones']
        self.assertEqual(len(transacciones), 1)
        self.assertEqual(transacciones[0]['id'], self.venta.pk)

    def test_filtro_por_rango_de_fechas_actualiza_el_listado(self):
        """Criterio 3: filtrar por rango de fechas deja solo las transacciones que coinciden."""
        antigua = CalculoOperacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd,
            codigo_divisa='USD',
            monto_origen=Decimal('20.00'),
            tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('148.00'),
            monto_final=Decimal('148148.00'),
            vence_en=timezone.now() + timedelta(seconds=300),
        )
        antigua.creado_en = timezone.now() - timedelta(days=30)
        antigua.save(update_fields=['creado_en'])
        hoy = timezone.localdate().isoformat()

        response = self.client.get(reverse('divisas:mis_transacciones'), {'fecha_desde': hoy})

        ids = [fila['id'] for fila in response.context['transacciones']]
        self.assertNotIn(antigua.pk, ids)
        self.assertIn(self.compra.pk, ids)

    def test_click_en_una_transaccion_lleva_al_detalle_completo(self):
        """Criterio 4: cada fila enlaza al detalle completo de esa transacción."""
        response = self.client.get(reverse('divisas:mis_transacciones'))
        url_detalle = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.compra.pk})

        self.assertContains(response, url_detalle)

        detalle = self.client.get(url_detalle)

        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, 'Compra')
        self.assertContains(detalle, '100.00')
        self.assertContains(detalle, 'Confirmada')

    def test_detalle_de_cambio_entre_divisas_muestra_sus_datos(self):
        """Criterio 4: el detalle de un cambio entre divisas también es accesible y completo."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        Cotizacion.objects.create(divisa=eur, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))
        cambio = CalculoTriangulacion.objects.create(
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

        response = self.client.get(reverse('divisas:detalle_transaccion_cambio', kwargs={'pk': cambio.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'USD')
        self.assertContains(response, 'EUR')
        self.assertContains(response, '250.00')
        self.assertContains(response, '223.06')

    def test_otro_cliente_no_puede_ver_el_detalle_de_una_transaccion_ajena(self):
        """El detalle de una transacción solo es visible para su dueño (404 en caso contrario)."""
        otro_usuario = User.objects.create_user(username='otro-detalle-mi-historial', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario,
            identificador='MIHIST-003',
            nombre='Otro',
            apellido='Detalle',
            email='otro-detalle-mi-historial@test.com',
            is_active=True,
        )
        otro_usuario.clientes.add(otro_cliente)
        self.client.logout()
        self.client.login(username='otro-detalle-mi-historial', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(
            reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.compra.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_cliente_sin_transacciones_ve_mensaje_sin_error(self):
        """Criterio 5: sin transacciones registradas, se muestra un mensaje, no un error."""
        self.compra.delete()
        self.venta.delete()

        response = self.client.get(reverse('divisas:mis_transacciones'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Todavía no tenés transacciones registradas.')

    def test_no_ofrece_acciones_de_edicion_cancelacion_ni_reproceso(self):
        """La HU es de solo consulta: no hay formularios para confirmar, cancelar ni reprocesar."""
        response_listado = self.client.get(reverse('divisas:mis_transacciones'))
        response_detalle = self.client.get(
            reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.compra.pk})
        )

        self.assertNotContains(response_listado, 'name="accion"')
        self.assertNotContains(response_detalle, 'name="accion"')
        self.assertNotContains(response_detalle, 'Confirmar')
        self.assertNotContains(response_detalle, 'Cancelar')

    def test_admin_no_puede_ver_el_historial_propio_de_un_cliente(self):
        """El rol admin, sin cliente propio, no puede acceder a esta pantalla (403)."""
        User.objects.create_user(username='admin-mi-historial', password='password123', is_staff=True)
        self.client.logout()
        self.client.login(username='admin-mi-historial', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('divisas:mis_transacciones'))

        self.assertEqual(response.status_code, 403)


class ConfirmacionOperacionCambiariaTest(TestCase):
    """Verifica la HU 'Confirmación de operación cambiaria' para compra y venta."""

    def setUp(self):
        """Prepara un cliente activo, una divisa cotizada y una compra pendiente."""
        self.usuario = User.objects.create_user(
            username='cliente-confirmacion',
            password='password123',
        )
        self.client.login(username='cliente-confirmacion', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='CONFIRMACION-001',
            nombre='Cliente',
            apellido='Confirmación',
            email='cliente-confirmacion@test.com',
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
            estado=CalculoOperacion.ESTADO_PENDIENTE,
            vence_en=timezone.now() + timedelta(seconds=300),
        )
        self.url = reverse('divisas:confirmar_transaccion', kwargs={'pk': self.transaccion.pk})

    def test_pantalla_de_confirmacion_muestra_el_resumen_completo(self):
        """Criterio 1: la pantalla muestra tipo, divisa, monto, tasa, comisión y monto final."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Compra')
        self.assertContains(response, 'USD')
        self.assertContains(response, '100.00')
        self.assertContains(response, '7400.00')
        self.assertContains(response, 'Comisión')
        self.assertContains(response, '747400.00')
        self.assertContains(response, 'Pendiente de confirmación')

    def test_confirmar_con_tasa_vigente_sin_cambios_marca_confirmada(self):
        """Criterio 2: si la tasa vigente no cambió, la transacción pasa a 'Confirmada'."""
        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertContains(response, 'La operación fue confirmada')
        self.assertContains(response, 'Confirmada')

    def test_confirmar_cancela_automaticamente_si_la_tasa_vigente_cambio(self):
        """Criterio 1 (GE-76): si la tasa vigente cambió, la transacción se cancela por cotización."""
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7350.00'),
            tasa_venta=Decimal('7450.00'),
        )

        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CANCELADA_COTIZACION)
        self.assertIsNone(self.transaccion.confirmado_en)
        self.assertContains(response, 'La tasa vigente cambió')

    def test_confirmar_por_cambio_de_cotizacion_notifica_y_ofrece_recalcular(self):
        """Criterio 2: al cancelarse por cambio de cotización, se explica el motivo y se ofrece recalcular."""
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7350.00'),
            tasa_venta=Decimal('7450.00'),
        )

        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.assertContains(response, 'fue cancelad')
        self.assertContains(response, 'Recalcular')

    def test_cancelada_por_cotizacion_es_distinguible_de_la_cancelacion_manual_en_el_historial(self):
        """Criterio 4: en el historial, la cancelación por cotización se ve distinta de la manual."""
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7350.00'),
            tasa_venta=Decimal('7450.00'),
        )
        self.client.post(self.url, {'accion': 'confirmar'})
        User.objects.create_user(username='admin-cancelada-cotizacion', password='password123')
        self.client.logout()
        self.client.login(username='admin-cancelada-cotizacion', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CANCELADA_COTIZACION)
        self.assertContains(response, 'Cancelada por cambio de cotización')

    def test_el_boton_recalcular_lleva_los_mismos_datos_de_la_transaccion_cancelada(self):
        """Criterio 3: el botón "Recalcular" no es un formulario vacío, ya trae la divisa y el monto."""
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7350.00'),
            tasa_venta=Decimal('7450.00'),
        )
        self.client.post(self.url, {'accion': 'confirmar'})

        response = self.client.get(self.url)

        self.assertContains(response, reverse('divisas:operar', kwargs={'tipo': 'compra'}))
        self.assertContains(response, f'name="divisa" value="{self.usd.pk}"')
        self.assertContains(response, 'name="monto" value="100.00"')

    def test_recalcular_tras_cancelacion_por_cotizacion_usa_la_tasa_vigente(self):
        """Criterio 3: al enviar el formulario de "Recalcular", se genera un cálculo nuevo con la tasa vigente."""
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7350.00'),
            tasa_venta=Decimal('7450.00'),
        )
        self.client.post(self.url, {'accion': 'confirmar'})
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CANCELADA_COTIZACION)

        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {
                'tipo': self.transaccion.tipo,
                'divisa': str(self.transaccion.divisa_id),
                'monto': str(self.transaccion.monto_origen),
            },
        )

        self.assertEqual(response.status_code, 200)
        resultado = response.context['resultado']
        self.assertEqual(resultado['tasa_aplicada'], Decimal('7450.00'))
        self.assertNotEqual(resultado['tasa_aplicada'], self.transaccion.tasa_aplicada)

    def test_cancelar_manualmente_marca_cancelada_y_no_se_procesa(self):
        """Criterio 3: al cancelar manualmente, la transacción pasa a 'Cancelada'."""
        response = self.client.post(self.url, {'accion': 'cancelar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CANCELADA)
        self.assertIsNone(self.transaccion.confirmado_en)
        self.assertContains(response, 'La operación fue cancelada')
        self.assertContains(response, 'Cancelada')

    def test_confirmar_registra_fecha_y_hora_de_confirmacion(self):
        """Criterio 4: al confirmarse, se registra la fecha y hora de confirmación."""
        antes = timezone.now()

        self.client.post(self.url, {'accion': 'confirmar'})

        self.transaccion.refresh_from_db()
        self.assertIsNotNone(self.transaccion.confirmado_en)
        self.assertGreaterEqual(self.transaccion.confirmado_en, antes)

    def test_no_se_puede_reprocesar_una_transaccion_ya_confirmada(self):
        """Una transacción ya confirmada no puede volver a confirmarse o cancelarse."""
        self.transaccion.estado = CalculoOperacion.ESTADO_CONFIRMADA
        self.transaccion.confirmado_en = timezone.now()
        self.transaccion.save(update_fields=['estado', 'confirmado_en'])
        confirmado_en_original = self.transaccion.confirmado_en

        response = self.client.post(self.url, {'accion': 'cancelar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertContains(response, 'ya fue procesada')
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertEqual(self.transaccion.confirmado_en, confirmado_en_original)

    def test_otro_cliente_no_puede_ver_ni_confirmar_la_transaccion(self):
        """Solo el cliente dueño de la transacción puede verla o accionarla."""
        otro_usuario = User.objects.create_user(username='otro-usuario', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario,
            identificador='CONFIRMACION-002',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente-confirmacion@test.com',
            is_active=True,
        )
        otro_usuario.clientes.add(otro_cliente)
        self.client.logout()
        self.client.login(username='otro-usuario', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_get = self.client.get(self.url)
        response_post = self.client.post(self.url, {'accion': 'confirmar'})

        self.assertEqual(response_get.status_code, 404)
        self.assertEqual(response_post.status_code, 404)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PENDIENTE)

    def test_administrador_no_puede_acceder_a_la_pantalla_de_confirmacion(self):
        """Solo clientes con rol y cliente activo pueden usar esta pantalla."""
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_visitar_la_pantalla_marca_vencida_una_transaccion_que_nunca_se_resolvio(self):
        """Si el cliente cerró la pestaña y nunca decidió nada, vencido el plazo pasa a 'Vencida'."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])

        response = self.client.get(self.url)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_VENCIDA)
        self.assertContains(response, 'venció')
        self.assertContains(response, 'Recalcular')

    def test_confirmar_una_transaccion_vencida_no_la_confirma(self):
        """Una transacción vencida no puede confirmarse, aunque la tasa siga igual."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])

        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_VENCIDA)
        self.assertIsNone(self.transaccion.confirmado_en)
        self.assertContains(response, 'El tiempo para confirmar esta operación venció')

    def test_cancelar_una_transaccion_vencida_no_la_cancela(self):
        """Cancelar una transacción ya vencida no tiene efecto: queda 'Vencida', no 'Cancelada'."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])

        response = self.client.post(self.url, {'accion': 'cancelar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_VENCIDA)

    def test_estado_efectivo_no_persiste_por_si_solo(self):
        """Leer el estado efectivo no escribe nada: la base sigue diciendo 'Pendiente'."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])

        self.assertEqual(self.transaccion.estado_efectivo, CalculoOperacion.ESTADO_VENCIDA)

        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PENDIENTE)

    def test_historial_muestra_vencida_sin_que_nadie_haya_visitado_la_transaccion(self):
        """El historial de administración ve 'Vencida' aunque la base siga en 'Pendiente'."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])
        User.objects.create_user(username='admin-vencida', password='password123')
        self.client.logout()
        self.client.login(username='admin-vencida', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertContains(response, 'Vencida')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PENDIENTE)


class ConfirmacionCambioDivisasTest(TestCase):
    """Verifica la HU 'Confirmación de operación cambiaria' para el cambio entre divisas."""

    def setUp(self):
        """Prepara un cliente activo, dos divisas cotizadas y un cambio pendiente."""
        self.usuario = User.objects.create_user(
            username='cliente-confirmacion-cambio',
            password='password123',
        )
        self.client.login(username='cliente-confirmacion-cambio', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='CONF-CAMBIO-001',
            nombre='Cliente',
            apellido='Cambio',
            email='cliente-confirmacion-cambio@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))
        self.transaccion = CalculoTriangulacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            divisa_origen=self.usd,
            divisa_destino=self.eur,
            codigo_divisa_origen='USD',
            codigo_divisa_destino='EUR',
            monto_origen=Decimal('100.00'),
            tasa_compra_aplicada=Decimal('7300.00'),
            tasa_venta_aplicada=Decimal('8100.00'),
            tasa_cruzada=Decimal('0.901235'),
            monto_equivalente_pyg=Decimal('730000.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('0.90'),
            monto_final=Decimal('89.22'),
            estado=CalculoTriangulacion.ESTADO_PENDIENTE,
            vence_en=timezone.now() + timedelta(seconds=300),
        )
        self.url = reverse('divisas:confirmar_transaccion_cambio', kwargs={'pk': self.transaccion.pk})

    def test_pantalla_de_confirmacion_muestra_el_resumen_completo(self):
        """Criterio 1: la pantalla muestra ambas divisas, monto, tasas, comisión y monto final."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'USD')
        self.assertContains(response, 'EUR')
        self.assertContains(response, '100.00')
        self.assertContains(response, 'Comisión')
        self.assertContains(response, '89.22')
        self.assertContains(response, 'Pendiente de confirmación')

    def test_confirmar_con_tasas_vigentes_sin_cambios_marca_confirmada(self):
        """Criterio 2: si las tasas vigentes no cambiaron, el cambio pasa a 'Confirmada'."""
        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CONFIRMADA)
        self.assertContains(response, 'El cambio fue confirmado')

    def test_confirmar_cancela_automaticamente_si_alguna_tasa_vigente_cambio(self):
        """Criterio 1 (GE-76): si cambió la cotización de alguna divisa, el cambio se cancela por cotización."""
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7950.00'), tasa_venta=Decimal('8150.00'))

        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CANCELADA_COTIZACION)
        self.assertIsNone(self.transaccion.confirmado_en)
        self.assertContains(response, 'Las tasas vigentes cambiaron')

    def test_confirmar_por_cambio_de_cotizacion_notifica_y_ofrece_recalcular(self):
        """Criterio 2: al cancelarse por cambio de cotización, se explica el motivo y se ofrece recalcular."""
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7950.00'), tasa_venta=Decimal('8150.00'))

        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.assertContains(response, 'fue cancelad')
        self.assertContains(response, 'Recalcular')

    def test_cancelada_por_cotizacion_es_distinguible_de_la_cancelacion_manual_en_el_historial(self):
        """Criterio 4: en el historial, la cancelación por cotización se ve distinta de la manual."""
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7950.00'), tasa_venta=Decimal('8150.00'))
        self.client.post(self.url, {'accion': 'confirmar'})
        User.objects.create_user(username='admin-cancelada-cotizacion-cambio', password='password123')
        self.client.logout()
        self.client.login(username='admin-cancelada-cotizacion-cambio', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CANCELADA_COTIZACION)
        self.assertContains(response, 'Cancelada por cambio de cotización')

    def test_el_boton_recalcular_lleva_los_mismos_datos_del_cambio_cancelado(self):
        """Criterio 3: el botón "Recalcular" no es un formulario vacío, ya trae ambas divisas y el monto."""
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7950.00'), tasa_venta=Decimal('8150.00'))
        self.client.post(self.url, {'accion': 'confirmar'})

        response = self.client.get(self.url)

        self.assertContains(response, reverse('divisas:triangulacion'))
        self.assertContains(response, f'name="divisa_origen" value="{self.usd.pk}"')
        self.assertContains(response, f'name="divisa_destino" value="{self.eur.pk}"')
        self.assertContains(response, 'name="monto" value="100.00"')

    def test_recalcular_tras_cancelacion_por_cotizacion_usa_las_tasas_vigentes(self):
        """Criterio 3: al enviar el formulario de "Recalcular", se genera un cálculo nuevo con las tasas vigentes."""
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7950.00'), tasa_venta=Decimal('8150.00'))
        self.client.post(self.url, {'accion': 'confirmar'})
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CANCELADA_COTIZACION)

        response = self.client.post(
            reverse('divisas:triangulacion'),
            {
                'divisa_origen': str(self.transaccion.divisa_origen_id),
                'divisa_destino': str(self.transaccion.divisa_destino_id),
                'monto': str(self.transaccion.monto_origen),
            },
        )

        self.assertEqual(response.status_code, 200)
        resultado = response.context['resultado']
        self.assertEqual(resultado['tasa_venta_aplicada'], Decimal('8150.00'))
        self.assertNotEqual(resultado['tasa_venta_aplicada'], self.transaccion.tasa_venta_aplicada)

    def test_cancelar_manualmente_marca_cancelada(self):
        """Criterio 3: al cancelar manualmente, el cambio pasa a 'Cancelada' y no se procesa."""
        response = self.client.post(self.url, {'accion': 'cancelar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CANCELADA)
        self.assertIsNone(self.transaccion.confirmado_en)
        self.assertContains(response, 'El cambio fue cancelado')

    def test_confirmar_registra_fecha_y_hora_de_confirmacion(self):
        """Criterio 4: al confirmarse, se registra la fecha y hora de confirmación."""
        antes = timezone.now()

        self.client.post(self.url, {'accion': 'confirmar'})

        self.transaccion.refresh_from_db()
        self.assertIsNotNone(self.transaccion.confirmado_en)
        self.assertGreaterEqual(self.transaccion.confirmado_en, antes)

    def test_otro_cliente_no_puede_ver_ni_confirmar_el_cambio(self):
        """Solo el cliente dueño del cambio puede verlo o accionarlo."""
        otro_usuario = User.objects.create_user(username='otro-usuario-cambio', password='password123')
        otro_cliente = Cliente.objects.create(
            user=otro_usuario,
            identificador='CONF-CAMBIO-002',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente-confirmacion-cambio@test.com',
            is_active=True,
        )
        otro_usuario.clientes.add(otro_cliente)
        self.client.logout()
        self.client.login(username='otro-usuario-cambio', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_get = self.client.get(self.url)
        response_post = self.client.post(self.url, {'accion': 'confirmar'})

        self.assertEqual(response_get.status_code, 404)
        self.assertEqual(response_post.status_code, 404)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_PENDIENTE)

    def test_visitar_la_pantalla_marca_vencida_un_cambio_que_nunca_se_resolvio(self):
        """Si el cliente cerró la pestaña y nunca decidió nada, vencido el plazo pasa a 'Vencida'."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])

        response = self.client.get(self.url)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_VENCIDA)
        self.assertContains(response, 'venció')
        self.assertContains(response, 'Recalcular')

    def test_confirmar_un_cambio_vencido_no_lo_confirma(self):
        """Un cambio vencido no puede confirmarse, aunque las tasas sigan iguales."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])

        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_VENCIDA)
        self.assertIsNone(self.transaccion.confirmado_en)
        self.assertContains(response, 'El tiempo para confirmar este cambio venció')

    def test_cancelar_un_cambio_vencido_no_lo_cancela(self):
        """Cancelar un cambio ya vencido no tiene efecto: queda 'Vencida', no 'Cancelada'."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])

        response = self.client.post(self.url, {'accion': 'cancelar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_VENCIDA)

    def test_historial_muestra_vencida_sin_que_nadie_haya_visitado_el_cambio(self):
        """El historial de administración ve 'Vencida' aunque la base siga en 'Pendiente'."""
        self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['vence_en'])
        User.objects.create_user(username='admin-vencida-cambio', password='password123')
        self.client.logout()
        self.client.login(username='admin-vencida-cambio', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertContains(response, 'Vencida')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_PENDIENTE)
