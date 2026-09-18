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
        self.assertContains(response, 'is not one of the available choices')

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

    def test_triangula_usando_compra_origen_y_venta_destino_con_comision(self):
        """Calcula el importe cruzado desglosando tasas, cruce y comisión."""
        response = self.client.post(
            reverse('divisas:triangulacion'),
            {'divisa_origen': str(self.usd.pk), 'divisa_destino': str(self.eur.pk), 'monto': '100'},
        )

        calculo = CalculoTriangulacion.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calculo.tasa_compra_aplicada, Decimal('7300.00'))
        self.assertEqual(calculo.tasa_venta_aplicada, Decimal('8100.00'))
        self.assertEqual(calculo.tasa_cruzada, Decimal('0.901235'))
        self.assertEqual(calculo.monto_equivalente_pyg, Decimal('730000.00'))
        self.assertEqual(calculo.comision, Decimal('0.90'))
        self.assertEqual(calculo.monto_final, Decimal('89.22'))
        self.assertContains(response, '89.22')

    def test_divisa_destino_sin_cotizacion_impide_triangular(self):
        """Muestra error y no crea el cálculo si falta una cotización."""
        sin_cotizacion = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)
        response = self.client.post(
            reverse('divisas:triangulacion'),
            {'divisa_origen': str(self.usd.pk), 'divisa_destino': str(sin_cotizacion.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoTriangulacion.objects.exists())
        self.assertContains(response, 'no tiene cotización disponible')

    def test_rechaza_la_misma_divisa_en_origen_y_destino(self):
        """No permite triangular una divisa contra sí misma."""
        response = self.client.post(
            reverse('divisas:triangulacion'),
            {'divisa_origen': str(self.usd.pk), 'divisa_destino': str(self.usd.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoTriangulacion.objects.exists())
        self.assertContains(response, 'Debe seleccionar dos divisas distintas')

    def test_calculo_triangulado_vencido_debe_recalcularse_antes_de_confirmar(self):
        """Rechaza confirmación cuando la triangulación ya superó su vigencia."""
        calculo = CalculoTriangulacion.objects.create(
            usuario=self.usuario,
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
            vence_en=timezone.now() - timedelta(seconds=1),
        )

        response = self.client.post(
            reverse('divisas:confirmar_triangulacion', kwargs={'calculo_id': calculo.pk}),
            follow=True,
        )

        calculo.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(calculo.confirmado_en)


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
