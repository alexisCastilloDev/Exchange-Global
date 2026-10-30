"""Pruebas del cálculo de importes para compra y venta de divisas."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente, MetodoPago
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    ConfiguracionVigencia,
    Cotizacion,
    CuentaPropia,
    Divisa,
    Pago,
    PagoRechazadoError,
    moneda_a_pagar,
    monto_a_pagar,
)
from tests.utils_formato import formato


User = get_user_model()


def _crear_cliente(username, identificador, nombre='Cliente', apellido='Test'):
    """Crea un usuario con un cliente asociado, sin loguearlo todavía.

    Returns:
        tuple[User, Cliente]: el usuario y el cliente recién creados.
    """
    usuario = User.objects.create_user(username=username, password='password123')
    cliente = Cliente.objects.create(
        user=usuario,
        identificador=identificador,
        nombre=nombre,
        apellido=apellido,
        email=f'{username}@test.com',
        is_active=True,
    )
    usuario.clientes.add(cliente)
    return usuario, cliente


def _crear_cliente_logueado(client, username, identificador, apellido='Test', roles=('cliente',)):
    """Crea un usuario con un cliente asociado y lo loguea con los roles de Keycloak dados.

    Boilerplate repetido al inicio de casi todos los ``setUp`` de este archivo
    (crear usuario, crear su ``Cliente`` y asociarlo, loguearlo y fijar
    ``keycloak_roles`` en la sesión). Se factoriza acá para no repetirlo clase
    por clase; cada test sigue pudiendo pisar lo que necesite (otro rol, otro
    cliente activo, etc.) después de llamarlo.

    Returns:
        tuple[User, Cliente]: el usuario y el cliente recién creados.
    """
    usuario, cliente = _crear_cliente(username, identificador, apellido=apellido)
    client.login(username=username, password='password123')
    session = client.session
    session['keycloak_roles'] = list(roles)
    session.save()
    return usuario, cliente


def _crear_usd_cotizado(tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00')):
    """Crea la divisa USD activa con una cotización vigente (7300.00/7400.00 por defecto)."""
    usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
    Cotizacion.objects.create(divisa=usd, tasa_compra=tasa_compra, tasa_venta=tasa_venta)
    return usd


def _crear_eur_cotizado(tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00')):
    """Crea la divisa EUR activa con una cotización vigente (7900.00/8100.00 por defecto)."""
    eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
    Cotizacion.objects.create(divisa=eur, tasa_compra=tasa_compra, tasa_venta=tasa_venta)
    return eur


class CalculoOperacionTest(TestCase):
    """Verifica tasas, comisión, errores de cotización y vencimiento."""

    def setUp(self):
        """Prepara un cliente asociado y una divisa cotizada."""
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-operaciones', 'OPERACION-001', apellido='Operación'
        )
        self.usd = _crear_usd_cotizado()

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
        self.assertContains(response, formato(Decimal('747400.00')))
        self.assertContains(response, formato(Decimal('7400.00')))

    def test_confirmar_usa_la_tasa_y_comision_segun_el_tipo_de_operacion(self):
        """Al confirmar, una compra usa la tasa de venta y suma la comisión; una venta, al revés."""
        with self.subTest('compra'):
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
            # Criterio 4 de "Compra de divisas" (GE-30): tipo, cliente activo y fecha
            # quedan registrados; divisa/monto ya se verifican arriba.
            self.assertEqual(calculo.tipo, CalculoOperacion.TIPO_COMPRA)
            self.assertEqual(calculo.cliente, self.cliente)
            self.assertIsNotNone(calculo.creado_en)
            calculo.delete()

        with self.subTest('venta'):
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

    def test_confirmar_rechaza_si_el_calculo_vencio_o_si_cambio_la_cotizacion(self):
        """Rechaza la confirmación tanto si venció el cálculo como si cambió la cotización entre medio."""
        with self.subTest('cálculo vencido'):
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

        with self.subTest('cotización cambió'):
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

    def test_menu_expone_compra_venta_segun_el_rol(self):
        """Muestra ambos accesos operativos a un cliente, pero los oculta para un analista."""
        with self.subTest('cliente'):
            response = self.client.get(reverse('home'))

            self.assertContains(response, reverse('divisas:operar', kwargs={'tipo': 'compra'}))
            self.assertContains(response, reverse('divisas:operar', kwargs={'tipo': 'venta'}))

        with self.subTest('analista'):
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


class VentaDeDivisasTest(TestCase):
    """Verifica los criterios de aceptación de la HU 'Venta de divisas'.

    La validación de monto y de divisa (criterios 2 y 3) no depende del tipo
    de operación: ``CalculoOperacionForm``/``CalculoOperacionView`` corren el
    mismo código para compra y venta. Por eso esos criterios se prueban una
    sola vez acá (antes había una clase ``CompraDeDivisasTest`` que los
    repetía con el mismo resultado); lo que sí es específico de la compra
    (usar la tasa de venta y sumar la comisión, y que el ``tipo`` guardado
    sea ``COMPRA``) está cubierto en ``CalculoOperacionTest``.
    """

    def setUp(self):
        """Prepara un cliente activo y una divisa con cotización vigente."""
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-venta', 'VENTA-001', apellido='Venta'
        )
        self.usd = _crear_usd_cotizado()
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
        self.assertContains(response, formato(calculo.monto_final))

    def test_venta_usa_la_comision_del_cliente_activo(self):
        """Criterio 1: la comisión del cliente activo se descuenta del importe a recibir."""
        self.cliente.comision_personalizada = Decimal('2.000')
        self.cliente.save(update_fields=['comision_personalizada'])

        resultado = self._calcular().context['resultado']

        self.assertEqual(resultado['comision_porcentaje'], Decimal('2.000'))
        self.assertEqual(resultado['comision'], Decimal('14600.00'))
        self.assertEqual(resultado['monto_final'], Decimal('715400.00'))

    def test_montos_invalidos_no_crean_transaccion(self):
        """Criterio 2: un monto negativo, en cero o no numérico se rechaza sin crear la transacción."""
        casos = [
            ('-100', 'El monto debe ser mayor que cero.'),
            ('0', 'El monto debe ser mayor que cero.'),
            ('abc', 'El monto debe ser un número válido.'),
        ]
        for monto, mensaje in casos:
            with self.subTest(monto=monto):
                response = self._calcular(monto=monto)

                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context['resultado'])
                self.assertContains(response, mensaje)
        self.assertFalse(CalculoOperacion.objects.exists())

    def test_monto_invalido_en_la_confirmacion_no_crea_transaccion(self):
        """Criterio 2: aunque se manipulen los campos ocultos, un monto inválido no crea nada."""
        datos = self._datos_confirmacion(self._calcular().context['resultado'])
        for monto in ('-5', '0', 'abc'):
            datos['monto'] = monto

            self.client.post(self.url_confirmar, datos)

        self.assertFalse(CalculoOperacion.objects.exists())

    def test_una_divisa_invalida_rechaza_la_operacion_al_calcular(self):
        """Criterio 3: una divisa inactiva o sin cotización vigente se rechaza con un mensaje claro."""
        with self.subTest('inactiva'):
            inactiva = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=False)
            Cotizacion.objects.create(divisa=inactiva, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))

            response = self._calcular(divisa=inactiva)

            self.assertEqual(response.status_code, 200)
            self.assertFalse(CalculoOperacion.objects.exists())
            self.assertIsNone(response.context['resultado'])
            self.assertContains(response, 'inactiva o no está disponible para operar')

        with self.subTest('sin cotización vigente'):
            sin_cotizacion = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)

            response = self._calcular(divisa=sin_cotizacion)

            self.assertEqual(response.status_code, 200)
            self.assertFalse(CalculoOperacion.objects.exists())
            self.assertIsNone(response.context['resultado'])
            self.assertContains(response, 'no tiene cotización disponible')

    def test_una_divisa_invalidada_entre_el_calculo_y_la_confirmacion_rechaza_la_operacion(self):
        """Criterio 3: si la divisa se desactiva, o pierde su cotización, antes de confirmar, no se crea nada."""
        with self.subTest('se desactiva'):
            resultado = self._calcular().context['resultado']
            self.usd.activa = False
            self.usd.save(update_fields=['activa'])

            response = self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

            self.assertEqual(response.status_code, 200)
            self.assertFalse(CalculoOperacion.objects.exists())
            self.usd.activa = True
            self.usd.save(update_fields=['activa'])

        with self.subTest('pierde la cotización'):
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
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-triangulacion', 'TRIANGULACION-001', apellido='Triangulación'
        )
        self.usd = _crear_usd_cotizado()
        self.eur = _crear_eur_cotizado()
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
        self.assertContains(response, formato(resultado['monto_final']))

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
        self.assertContains(response, formato(calculo.monto_final))

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

    def test_confirmar_rechaza_si_el_calculo_vencio_o_si_cambio_una_cotizacion(self):
        """Rechaza la confirmación tanto si venció el cálculo como si cambió la cotización de cualquier divisa."""
        with self.subTest('cálculo vencido'):
            datos = self._datos_confirmacion(self._calcular().context['resultado'])
            datos['vence_en_timestamp'] = str((timezone.now() - timedelta(seconds=1)).timestamp())

            response = self.client.post(self.url_confirmar, datos, follow=True)

            self.assertEqual(response.status_code, 200)
            self.assertFalse(CalculoTriangulacion.objects.exists())
            self.assertContains(response, 'El cálculo venció')

        with self.subTest('cotización cambió'):
            resultado = self._calcular().context['resultado']
            Cotizacion.objects.create(
                divisa=self.eur,
                tasa_compra=Decimal('7950.00'),
                tasa_venta=Decimal('8150.00'),
            )

            response = self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

            self.assertFalse(CalculoTriangulacion.objects.exists())
            self.assertContains(response, 'El cálculo venció')

    def test_una_divisa_invalidada_entre_el_calculo_y_la_confirmacion_no_crea_transaccion(self):
        """Si una divisa pierde su cotización, o se desactiva, antes de confirmar, no se registra nada."""
        with self.subTest('pierde la cotización'):
            resultado = self._calcular().context['resultado']
            Cotizacion.objects.filter(divisa=self.eur).delete()

            response = self.client.post(self.url_confirmar, self._datos_confirmacion(resultado), follow=True)

            self.assertFalse(CalculoTriangulacion.objects.exists())
            self.assertContains(response, 'no tiene cotización disponible')
            Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7900.00'), tasa_venta=Decimal('8100.00'))

        with self.subTest('se desactiva'):
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
        self.usuario, self.cliente = _crear_cliente('cliente-historial', 'HISTORIAL-001', apellido='Historial')
        self.usd = _crear_usd_cotizado()
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

    def test_acceso_al_historial_segun_el_rol(self):
        """Admin y analista_cambiario acceden; un cliente no puede ver el historial administrativo."""
        for rol, esperado in (('admin', 200), ('analista_cambiario', 200), ('cliente', 403)):
            with self.subTest(rol=rol):
                self._login_como(rol)

                response = self.client.get(reverse('divisas:historial_transacciones'))

                self.assertEqual(response.status_code, esperado)
                self.client.logout()

    def test_historial_muestra_tipo_estado_cliente_divisa_monto_y_fecha(self):
        """Cada fila expone tipo, estado, cliente activo, divisa, monto y fecha."""
        self._login_como('admin')

        response = self.client.get(reverse('divisas:historial_transacciones'))

        self.assertContains(response, 'Compra')
        self.assertContains(response, 'Pendiente de confirmación')
        self.assertContains(response, 'Cliente Historial')
        self.assertContains(response, 'USD')
        self.assertContains(response, formato(self.transaccion.monto_origen))
        self.assertContains(response, timezone.localtime(self.transaccion.creado_en).strftime('%d/%m/%Y'))

    def test_historial_incluye_transacciones_de_todos_los_clientes(self):
        """El historial no se limita a un único cliente, a diferencia de las vistas del cliente."""
        otro_usuario, otro_cliente = _crear_cliente(
            'cliente-historial-2', 'HISTORIAL-002', nombre='Otro', apellido='Cliente'
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
        self.assertContains(response, formato(Decimal('250.00')))
        self.assertContains(response, formato(Decimal('0.901235'), 6))
        self.assertContains(response, f"{formato(Decimal('2.25'))} EUR")
        self.assertContains(response, f"{formato(Decimal('223.06'))} EUR")
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
        self.assertContains(response, f"{formato(Decimal('89.22'))} EUR")

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
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-mi-historial', 'MIHIST-001', apellido='Propio'
        )
        self.usd = _crear_usd_cotizado()
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
        otro_usuario, otro_cliente = _crear_cliente(
            'otro-cliente-mi-historial', 'MIHIST-002', nombre='Otro', apellido='Cliente'
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
        self.assertContains(response, formato(self.compra.monto_origen))
        self.assertContains(response, formato(self.compra.tasa_aplicada))
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
        self.assertContains(detalle, formato(self.compra.monto_origen))
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
        self.assertContains(response, formato(cambio.monto_origen))
        self.assertContains(response, formato(cambio.monto_final))

    def test_otro_cliente_no_puede_ver_el_detalle_de_una_transaccion_ajena(self):
        """El detalle de una transacción solo es visible para su dueño (404 en caso contrario)."""
        otro_usuario, otro_cliente = _crear_cliente(
            'otro-detalle-mi-historial', 'MIHIST-003', nombre='Otro', apellido='Detalle'
        )
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
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-confirmacion', 'CONFIRMACION-001', apellido='Confirmación'
        )
        self.usd = _crear_usd_cotizado()
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

        # Al confirmar, se verifica que Global Exchange tenga saldo
        # propio suficiente en la divisa a entregar (ver CuentaPropia):
        # estos tests cubren la confirmación en sí, así que se arranca
        # con saldo siempre suficiente en USD.
        CuentaPropia.objects.create(divisa=self.usd, saldo=Decimal('1000000.00'))

    def test_pantalla_de_confirmacion_muestra_el_resumen_completo(self):
        """Criterio 1: la pantalla muestra tipo, divisa, monto, tasa, comisión y monto final."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Compra')
        self.assertContains(response, 'USD')
        self.assertContains(response, formato(self.transaccion.monto_origen))
        self.assertContains(response, formato(self.transaccion.tasa_aplicada))
        self.assertContains(response, 'Comisión')
        self.assertContains(response, formato(self.transaccion.monto_final))
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
        """Criterios 1 y 2 (GE-76): si la tasa vigente cambió, se cancela por cotización y se explica por qué."""
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
        self.assertContains(response, 'fue cancelad')

    def test_confirmar_se_cancela_si_global_exchange_no_puede_entregar(self):
        """Sin saldo suficiente, o sin ninguna cuenta propia cargada en esa moneda, no se puede confirmar."""
        with self.subTest('saldo insuficiente'):
            cuenta_usd = CuentaPropia.objects.get(divisa=self.usd)
            cuenta_usd.saldo = Decimal('1.00')
            cuenta_usd.save(update_fields=['saldo'])

            response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CANCELADA_SALDO_INSUFICIENTE)
            self.assertIsNone(self.transaccion.confirmado_en)
            self.assertContains(response, 'no dispone de fondos suficientes')

        with self.subTest('sin cuenta propia en esa moneda'):
            self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
            self.transaccion.save(update_fields=['estado'])
            CuentaPropia.objects.filter(divisa=self.usd).delete()

            response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CANCELADA_SALDO_INSUFICIENTE)
            self.assertContains(response, 'no dispone de fondos suficientes')

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

    def test_confirmar_fija_el_vencimiento_de_la_tasa_segun_la_vigencia_configurada(self):
        """Al confirmar, la tasa fijada queda con su propio vencimiento (``tasa_vence_en``)."""
        self.client.post(self.url, {'accion': 'confirmar'})

        self.transaccion.refresh_from_db()
        self.assertIsNotNone(self.transaccion.tasa_vence_en)
        self.assertEqual(
            self.transaccion.tasa_vence_en,
            self.transaccion.confirmado_en + timedelta(seconds=ConfiguracionVigencia.vigencia_pago_segundos()),
        )
        self.assertFalse(self.transaccion.tasa_vencida)

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
        otro_usuario, otro_cliente = _crear_cliente(
            'otro-usuario', 'CONFIRMACION-002', nombre='Otro', apellido='Cliente'
        )
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

    def test_cambiar_de_cliente_activo_avisa_en_vez_de_dar_un_error(self):
        """Si cambia el cliente activo (otro cliente propio) mientras la pantalla está abierta, avisa."""
        otro_cliente = Cliente.objects.create(
            identificador='CONFIRMACION-003',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente-propio-confirmacion@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(otro_cliente)
        session = self.client.session
        session['cliente_activo_id'] = otro_cliente.pk
        session.save()

        response_get = self.client.get(self.url, follow=True)
        response_post = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.assertEqual(response_get.status_code, 200)
        self.assertEqual(response_post.status_code, 200)
        self.assertContains(response_get, 'no corresponde al cliente activo')
        self.assertContains(response_post, 'no corresponde al cliente activo')
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

    def test_una_transaccion_vencida_no_puede_confirmarse_ni_cancelarse(self):
        """Una transacción vencida rechaza tanto 'confirmar' como 'cancelar': queda 'Vencida'."""
        for accion in ('confirmar', 'cancelar'):
            with self.subTest(accion=accion):
                # Se reinicia a 'Pendiente' + vencida en cada vuelta para que ambas acciones
                # se prueben sobre el mismo escenario (detección perezosa recién al postear).
                self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
                self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
                self.transaccion.save(update_fields=['estado', 'vence_en'])

                response = self.client.post(self.url, {'accion': accion}, follow=True)

                self.transaccion.refresh_from_db()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_VENCIDA)
                self.assertIsNone(self.transaccion.confirmado_en)
                self.assertContains(response, 'El tiempo para confirmar esta operación venció')

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
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-confirmacion-cambio', 'CONF-CAMBIO-001', apellido='Cambio'
        )
        self.usd = _crear_usd_cotizado()
        self.eur = _crear_eur_cotizado()
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

        # Ver ConfirmacionOperacionCambiariaTest.setUp: saldo propio
        # suficiente en la divisa de destino (EUR), lo que entrega el cambio.
        CuentaPropia.objects.create(divisa=self.eur, saldo=Decimal('1000000.00'))

    def test_pantalla_de_confirmacion_muestra_el_resumen_completo(self):
        """Criterio 1: la pantalla muestra ambas divisas, monto, tasas, comisión y monto final."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'USD')
        self.assertContains(response, 'EUR')
        self.assertContains(response, formato(self.transaccion.monto_origen))
        self.assertContains(response, 'Comisión')
        self.assertContains(response, formato(self.transaccion.monto_final))
        self.assertContains(response, 'Pendiente de confirmación')

    def test_confirmar_con_tasas_vigentes_sin_cambios_marca_confirmada(self):
        """Criterio 2: si las tasas vigentes no cambiaron, el cambio pasa a 'Confirmada'."""
        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CONFIRMADA)
        self.assertContains(response, 'El cambio fue confirmado')

    def test_confirmar_cancela_automaticamente_si_alguna_tasa_vigente_cambio(self):
        """Criterios 1 y 2 (GE-76): si cambió alguna cotización, se cancela por cotización y se explica por qué."""
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=Decimal('7950.00'), tasa_venta=Decimal('8150.00'))

        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CANCELADA_COTIZACION)
        self.assertIsNone(self.transaccion.confirmado_en)
        self.assertContains(response, 'Las tasas vigentes cambiaron')
        self.assertContains(response, 'fue cancelad')
        self.assertContains(response, 'Recalcular')

    def test_confirmar_se_cancela_si_global_exchange_no_tiene_saldo_suficiente_en_la_divisa_de_destino(self):
        """Un cambio tampoco se confirma si Global Exchange no puede entregar la divisa de destino."""
        cuenta_eur = CuentaPropia.objects.get(divisa=self.eur)
        cuenta_eur.saldo = Decimal('1.00')
        cuenta_eur.save(update_fields=['saldo'])

        response = self.client.post(self.url, {'accion': 'confirmar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CANCELADA_SALDO_INSUFICIENTE)
        self.assertIsNone(self.transaccion.confirmado_en)
        self.assertContains(response, 'no dispone de fondos suficientes')

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

    def test_confirmar_fija_el_vencimiento_de_la_tasa_segun_la_vigencia_configurada(self):
        """Al confirmar, la tasa fijada queda con su propio vencimiento (``tasa_vence_en``)."""
        self.client.post(self.url, {'accion': 'confirmar'})

        self.transaccion.refresh_from_db()
        self.assertIsNotNone(self.transaccion.tasa_vence_en)
        self.assertEqual(
            self.transaccion.tasa_vence_en,
            self.transaccion.confirmado_en + timedelta(seconds=ConfiguracionVigencia.vigencia_pago_segundos()),
        )
        self.assertFalse(self.transaccion.tasa_vencida)

    def test_otro_cliente_no_puede_ver_ni_confirmar_el_cambio(self):
        """Solo el cliente dueño del cambio puede verlo o accionarlo."""
        otro_usuario, otro_cliente = _crear_cliente(
            'otro-usuario-cambio', 'CONF-CAMBIO-002', nombre='Otro', apellido='Cliente'
        )
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

    def test_un_cambio_vencido_no_puede_confirmarse_ni_cancelarse(self):
        """Un cambio vencido rechaza tanto 'confirmar' como 'cancelar': queda 'Vencida'."""
        for accion in ('confirmar', 'cancelar'):
            with self.subTest(accion=accion):
                # Se reinicia a 'Pendiente' + vencido en cada vuelta para que ambas acciones
                # se prueben sobre el mismo escenario (detección perezosa recién al postear).
                self.transaccion.estado = CalculoTriangulacion.ESTADO_PENDIENTE
                self.transaccion.vence_en = timezone.now() - timedelta(seconds=1)
                self.transaccion.save(update_fields=['estado', 'vence_en'])

                response = self.client.post(self.url, {'accion': accion}, follow=True)

                self.transaccion.refresh_from_db()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_VENCIDA)
                self.assertIsNone(self.transaccion.confirmado_en)
                self.assertContains(response, 'El tiempo para confirmar este cambio venció')

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


class MontoAPagarTest(TestCase):
    """Verifica qué monto y moneda paga de verdad el cliente en cada tipo de transacción.

    Para una compra/venta es ``monto_final`` en PYG; para un cambio entre
    divisas es ``monto_origen`` en la divisa de origen — lo que el cliente
    entrega, no ``monto_final`` (lo que recibe a cambio).
    """

    def test_monto_a_pagar_segun_el_tipo_de_transaccion(self):
        """Una compra/venta siempre se paga en PYG con monto_final; un cambio, con monto_origen en su divisa."""
        with self.subTest('operación'):
            operacion = CalculoOperacion(codigo_divisa='USD', monto_final=Decimal('747400.00'))

            self.assertEqual(monto_a_pagar(operacion), Decimal('747400.00'))
            self.assertEqual(moneda_a_pagar(operacion), 'PYG')

        with self.subTest('cambio'):
            cambio = CalculoTriangulacion(
                codigo_divisa_origen='EUR', codigo_divisa_destino='USD',
                monto_origen=Decimal('500.00'), monto_final=Decimal('559.16'),
            )

            self.assertEqual(monto_a_pagar(cambio), Decimal('500.00'))
            self.assertEqual(moneda_a_pagar(cambio), 'EUR')


class PagoRegistrarPagoTest(TestCase):
    """Verifica ``Pago.registrar_pago``, el punto de entrada de la HU

    "Asociación de pagos a transacciones" (GE-25), independientemente de
    cualquier vista: estas pruebas ejercitan directamente la lógica de
    asociación, el cambio de estado y la idempotencia.
    """

    def setUp(self):
        """Prepara un cliente, una divisa cotizada y una compra ya 'Confirmada'."""
        self.usuario, self.cliente = _crear_cliente('cliente-pago-modelo', 'PAGO-MODELO-001', apellido='Pago')
        self.usd = _crear_usd_cotizado()
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
            estado=CalculoOperacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )

    def test_no_se_puede_registrar_un_pago_sin_transaccion_valida(self):
        """Criterio 1: un pago no puede registrarse sin una transacción válida."""
        with self.assertRaises(PagoRechazadoError):
            Pago.registrar_pago(
                None,
                medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
                proveedor='MANUAL',
                identificador_externo='sin-transaccion',
                monto=Decimal('1.00'),
            )

    def test_pago_exitoso_queda_asociado_con_todos_sus_datos(self):
        """Criterio 1: el pago registrado queda asociado a la transacción con medio, proveedor, identificador, monto y fecha."""
        pago, creado = Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
            proveedor='MANUAL',
            identificador_externo=str(self.transaccion.pk),
            monto=self.transaccion.monto_final,
        )

        self.assertTrue(creado)
        self.assertEqual(pago.transaccion, self.transaccion)
        self.assertEqual(pago.medio_pago, MetodoPago.TIPO_TRANSFERENCIA)
        self.assertEqual(pago.proveedor, 'MANUAL')
        self.assertEqual(pago.identificador_externo, str(self.transaccion.pk))
        self.assertEqual(pago.monto, self.transaccion.monto_final)
        self.assertIsNotNone(pago.creado_en)

    def test_pago_exitoso_sobre_confirmada_la_marca_pagada(self):
        """Criterio 2: un pago exitoso sobre una transacción 'Confirmada' la pasa a 'Pagada'."""
        Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
            proveedor='MANUAL',
            identificador_externo=str(self.transaccion.pk),
            monto=self.transaccion.monto_final,
        )

        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)

    def test_pago_fuera_de_plazo_segun_si_la_tasa_ya_vencio(self):
        """Un pago tardío nunca se rechaza: queda 'Pago fuera de plazo'; a tiempo, queda 'Pagada' como siempre."""
        with self.subTest('tasa ya vencida'):
            self.transaccion.tasa_vence_en = timezone.now() - timedelta(seconds=1)
            self.transaccion.save(update_fields=['tasa_vence_en'])

            pago, creado = Pago.registrar_pago(
                self.transaccion,
                medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
                proveedor='MANUAL',
                identificador_externo='pago-tardio',
                monto=self.transaccion.monto_final,
            )

            self.assertTrue(creado)
            self.assertTrue(pago.fuera_de_plazo)
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGO_EXPIRADO)

        with self.subTest('tasa vigente'):
            # El pago del caso anterior ya ocupa el OneToOneField con esta
            # transacción: hay que sacarlo antes de poder registrar otro.
            Pago.objects.filter(calculo_operacion=self.transaccion).delete()
            self.transaccion.estado = CalculoOperacion.ESTADO_CONFIRMADA
            self.transaccion.tasa_vence_en = timezone.now() + timedelta(seconds=300)
            self.transaccion.save(update_fields=['estado', 'tasa_vence_en'])

            pago, creado = Pago.registrar_pago(
                self.transaccion,
                medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
                proveedor='MANUAL',
                identificador_externo='pago-a-tiempo',
                monto=self.transaccion.monto_final,
            )

            self.assertTrue(creado)
            self.assertFalse(pago.fuera_de_plazo)
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)

    def test_rechaza_un_pago_sobre_una_transaccion_que_no_esta_confirmada(self):
        """Solo puede pagarse una transacción 'Confirmada' (no pendiente, cancelada ni vencida)."""
        self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
        self.transaccion.save(update_fields=['estado'])

        with self.assertRaises(PagoRechazadoError):
            Pago.registrar_pago(
                self.transaccion,
                medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
                proveedor='MANUAL',
                identificador_externo=str(self.transaccion.pk),
                monto=self.transaccion.monto_final,
            )
        self.assertEqual(Pago.objects.count(), 0)

    def test_rechaza_un_segundo_pago_por_cualquier_medio_si_ya_tiene_uno_exitoso(self):
        """Criterio 3: con un pago exitoso ya registrado, se rechaza cualquier otro, sea cual sea el medio."""
        Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
            proveedor='MANUAL',
            identificador_externo='primer-pago',
            monto=self.transaccion.monto_final,
        )

        with self.assertRaises(PagoRechazadoError):
            Pago.registrar_pago(
                self.transaccion,
                medio_pago=MetodoPago.TIPO_TARJETA,
                proveedor='STRIPE',
                identificador_externo='un-identificador-distinto',
                monto=self.transaccion.monto_final,
            )
        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 1)

    def test_una_confirmacion_duplicada_del_mismo_pago_no_crea_otro_ni_altera_la_transaccion(self):
        """Criterio 4: repetir la misma confirmación (proveedor + identificador externo) no duplica nada."""
        pago_1, creado_1 = Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
            proveedor='SIPAP',
            identificador_externo='sipap-op-123',
            monto=self.transaccion.monto_final,
        )

        pago_2, creado_2 = Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
            proveedor='SIPAP',
            identificador_externo='sipap-op-123',
            monto=self.transaccion.monto_final,
        )

        self.assertTrue(creado_1)
        self.assertFalse(creado_2)
        self.assertEqual(pago_1.pk, pago_2.pk)
        self.assertEqual(Pago.objects.count(), 1)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)

    def test_funciona_igual_para_un_cambio_entre_divisas(self):
        """``registrar_pago`` también aplica a ``CalculoTriangulacion``, no solo a compra/venta."""
        eur = _crear_eur_cotizado()
        cambio = CalculoTriangulacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            divisa_origen=self.usd,
            divisa_destino=eur,
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
            estado=CalculoTriangulacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )

        pago, creado = Pago.registrar_pago(
            cambio,
            medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
            proveedor='MANUAL',
            identificador_externo=str(cambio.pk),
            monto=cambio.monto_final,
        )

        self.assertTrue(creado)
        self.assertEqual(pago.transaccion, cambio)
        cambio.refresh_from_db()
        self.assertEqual(cambio.estado, CalculoTriangulacion.ESTADO_PAGADA)


class PagarTransaccionOperacionTest(TestCase):
    """Verifica la pantalla de pago de una compra/venta (HU "Asociación de pagos a transacciones")."""

    def setUp(self):
        """Prepara un cliente con medios de pago (origen y destino) y una compra ya 'Confirmada'."""
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-pagar-op', 'PAGAR-OP-001', apellido='Pagar'
        )
        self.usd = _crear_usd_cotizado()
        self.pyg = Divisa.objects.get(codigo='PYG')
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
            estado=CalculoOperacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        # Un método guardado de billetera digital en PYG, para pagar la
        # compra (medio de origen): igual que transferencia, se paga vía
        # SIPAP, nunca de forma manual (ver
        # test_pagar_con_un_metodo_de_billetera_redirige_a_sipap_en_vez_de_registrar_el_pago).
        self.metodo_pago = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_BILLETERA,
            nombre_titular='Cliente Pagar',
            entidad_financiera='Banco Test',
            moneda=self.pyg,
        )
        # Y uno en USD, para recibir la divisa comprada (medio de destino):
        # la pantalla de pago exige elegir ambos, cada uno en la moneda que
        # corresponde a esta compra.
        self.metodo_destino = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_BILLETERA,
            nombre_titular='Cliente Pagar',
            entidad_financiera='Banco Destino',
            moneda=self.usd,
        )
        self.url = reverse('divisas:pagar_transaccion', kwargs={'pk': self.transaccion.pk})
        self.detalle_url = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.transaccion.pk})

    def test_pantalla_de_pago_muestra_los_metodos_de_pago_del_cliente(self):
        """La pantalla ofrece elegir entre los métodos de pago ya guardados por el cliente."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Banco Test')

    def test_cada_opcion_del_formulario_muestra_el_tipo_de_medio_y_la_divisa(self):
        """Para distinguir cuentas y billeteras entre sí, cada opción indica tipo, entidad y divisa."""
        response = self.client.get(self.url)

        form = response.context['form']
        etiqueta_origen = form.fields['medio_origen'].label_from_instance(self.metodo_pago)
        etiqueta_destino = form.fields['medio_destino'].label_from_instance(self.metodo_destino)
        self.assertIn('Billetera Digital', etiqueta_origen)
        self.assertIn('PYG', etiqueta_origen)
        self.assertIn('Billetera Digital', etiqueta_destino)
        self.assertIn('USD', etiqueta_destino)
        self.assertContains(response, etiqueta_origen)
        self.assertContains(response, etiqueta_destino)

    def test_pagar_redirige_al_proveedor_externo_segun_el_tipo_de_medio_en_vez_de_registrar_el_pago(self):
        """Billetera y transferencia redirigen a SIPAP; tarjeta, a Stripe. Ninguna registra el pago acá."""
        with self.subTest('billetera → SIPAP'):
            response = self.client.post(self.url, {
                'medio_origen': self.metodo_pago.pk, 'medio_destino': self.metodo_destino.pk,
            })

            url_sipap = reverse('divisas:pagar_transaccion_sipap', kwargs={'pk': self.transaccion.pk})
            self.assertRedirects(
                response, f'{url_sipap}?metodo_pago={self.metodo_pago.pk}', fetch_redirect_response=False,
            )
            self.assertFalse(Pago.objects.filter(calculo_operacion=self.transaccion).exists())
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.medio_destino, self.metodo_destino)

        with self.subTest('tarjeta → Stripe'):
            tarjeta = MetodoPago.objects.create(
                cliente=self.cliente,
                tipo_medio=MetodoPago.TIPO_TARJETA,
                nombre_titular='Cliente Pagar',
                entidad_financiera='Visa Test',
                numero_tarjeta='4111111111111111',
                moneda=self.pyg,
            )

            response = self.client.post(self.url, {
                'medio_origen': tarjeta.pk, 'medio_destino': self.metodo_destino.pk,
            })

            url_stripe = reverse('divisas:pagar_transaccion_stripe', kwargs={'pk': self.transaccion.pk})
            self.assertRedirects(
                response, f'{url_stripe}?metodo_pago={tarjeta.pk}', fetch_redirect_response=False,
            )
            self.assertFalse(Pago.objects.filter(calculo_operacion=self.transaccion).exists())

        with self.subTest('transferencia → SIPAP'):
            transferencia = MetodoPago.objects.create(
                cliente=self.cliente,
                tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
                nombre_titular='Cliente Pagar',
                entidad_financiera='Banco Itaú',
                numero_cuenta='555666',
                tipo_cuenta='CORRIENTE',
                moneda=self.pyg,
            )

            response = self.client.post(self.url, {
                'medio_origen': transferencia.pk, 'medio_destino': self.metodo_destino.pk,
            })

            url_sipap = reverse('divisas:pagar_transaccion_sipap', kwargs={'pk': self.transaccion.pk})
            self.assertRedirects(
                response, f'{url_sipap}?metodo_pago={transferencia.pk}', fetch_redirect_response=False,
            )
            self.assertFalse(Pago.objects.filter(calculo_operacion=self.transaccion).exists())

    def test_medio_de_origen_solo_ofrece_medios_en_la_moneda_que_corresponde_pagar(self):
        """Una cuenta en una moneda que no es la que hay que pagar no aparece como opción de origen.

        (Sí puede aparecer como opción de destino, si coincide con la
        moneda que Global Exchange entrega — acá, la compra entrega USD,
        así que esta misma cuenta en USD es válida ahí.)
        """
        billetera_usd = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA,
            nombre_titular='Cliente Pagar', entidad_financiera='Billetera en USD', moneda=self.usd,
        )

        response = self.client.get(self.url)

        form = response.context['form']
        self.assertIn(self.metodo_pago, form.fields['medio_origen'].queryset)
        self.assertNotIn(billetera_usd, form.fields['medio_origen'].queryset)

    def test_medio_de_destino_nunca_ofrece_una_tarjeta(self):
        """Stripe no puede depositarle a una tarjeta: nunca aparece como destino, aunque esté en la moneda correcta."""
        tarjeta = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Cliente Pagar', entidad_financiera='Visa Test',
            numero_tarjeta='4111111111111111', moneda=self.usd,
        )

        response = self.client.post(self.url, {
            'medio_origen': self.metodo_pago.pk, 'medio_destino': tarjeta.pk,
        })

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertFormError(form, 'medio_destino', 'El medio de destino elegido no es válido para esta transacción.')

    def test_no_ofrece_el_formulario_de_pago_si_no_corresponde(self):
        """Ni una transacción pendiente ni una con la tasa fijada ya vencida pueden pagarse."""
        with self.subTest('no confirmada'):
            self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
            self.transaccion.save(update_fields=['estado'])

            response = self.client.get(self.url)

            self.assertNotContains(response, 'name="medio_origen"')

        with self.subTest('tasa vencida'):
            self.transaccion.estado = CalculoOperacion.ESTADO_CONFIRMADA
            self.transaccion.tasa_vence_en = timezone.now() - timedelta(seconds=1)
            self.transaccion.save(update_fields=['estado', 'tasa_vence_en'])

            response = self.client.get(self.url)

            self.assertNotContains(response, 'name="medio_origen"')

    def test_rechaza_pagar_si_la_tasa_fijada_ya_vencio(self):
        """Al intentar pagar con la tasa ya vencida, se informa y no se registra ningún pago."""
        self.transaccion.tasa_vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['tasa_vence_en'])

        response = self.client.post(self.url, {
            'medio_origen': self.metodo_pago.pk, 'medio_destino': self.metodo_destino.pk,
        }, follow=True)

        self.assertContains(response, 'ya venció')
        self.assertFalse(Pago.objects.filter(calculo_operacion=self.transaccion).exists())

    def test_cancelar_desde_la_pantalla_de_pago_cancela_la_operacion(self):
        """Una vez confirmada, el cliente también puede cancelarla desde la pantalla de pago."""
        response = self.client.post(self.url, {'accion': 'cancelar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CANCELADA)
        self.assertContains(response, 'La operación fue cancelada')
        self.assertFalse(Pago.objects.filter(calculo_operacion=self.transaccion).exists())

    def test_rechaza_pagar_una_transaccion_que_ya_fue_pagada(self):
        """Criterio 3: un segundo intento de pago, por cualquier medio, se rechaza."""
        Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
            proveedor=Pago.PROVEEDOR_MANUAL,
            identificador_externo=str(self.transaccion.pk),
            monto=self.transaccion.monto_final,
        )

        response = self.client.post(self.url, {
            'medio_origen': self.metodo_pago.pk, 'medio_destino': self.metodo_destino.pk,
        }, follow=True)

        self.assertContains(response, 'ya fue pagada')
        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 1)

    def test_detalle_muestra_el_pago_registrado_o_su_ausencia(self):
        """Criterio 5: sin pago lo indica explícitamente; con uno, muestra medio, monto, fecha e identificador.

        El pago llega siempre por confirmación asíncrona (Stripe o el
        webhook de SIPAP), nunca registrado por esta vista: se simula acá
        registrándolo directamente, igual que lo haría esa confirmación.
        """
        with self.subTest('sin pago'):
            response = self.client.get(self.detalle_url)

            self.assertContains(response, 'Todavía no tiene un pago registrado')

        with self.subTest('con pago'):
            Pago.registrar_pago(
                self.transaccion, medio_pago=MetodoPago.TIPO_BILLETERA, proveedor='SIPAP',
                identificador_externo='SPI-TEST-001', monto=self.transaccion.monto_final,
            )

            response = self.client.get(self.detalle_url)

            self.assertContains(response, 'Billetera Digital')
            self.assertContains(response, formato(self.transaccion.monto_final))
            self.assertContains(response, 'SPI-TEST-001')

    def test_otro_cliente_no_puede_ver_ni_pagar_la_transaccion_ajena(self):
        """Criterio 6: otro cliente no puede ver el pago ni la transacción, ni iniciar un pago sobre ella."""
        otro_usuario, otro_cliente = _crear_cliente(
            'otro-cliente-pagar', 'PAGAR-OP-002', nombre='Otro', apellido='Cliente'
        )
        self.client.logout()
        self.client.login(username='otro-cliente-pagar', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_get = self.client.get(self.url)
        response_post = self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk})
        response_detalle = self.client.get(self.detalle_url)

        self.assertEqual(response_get.status_code, 404)
        self.assertEqual(response_post.status_code, 404)
        self.assertEqual(response_detalle.status_code, 404)
        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 0)

    def test_pagar_una_venta_pide_y_guarda_el_medio_destino_igual_que_una_compra(self):
        """HU "Retiro de fondos" (GE-24): a qué cuenta se transfiere se elige al pagar, no al retirar.

        Simétrico con una compra: ambos campos (de dónde sale el pago, a
        dónde se transfiere el resultado) se piden en la misma pantalla y
        en el mismo momento. Más adelante, pedir el retiro de esta venta
        va a usar esta misma cuenta ya guardada, sin volver a preguntarla.
        """
        venta = CalculoOperacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_VENTA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7300.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('73.00'), monto_final=Decimal('729700.00'),
            estado=CalculoOperacion.ESTADO_CONFIRMADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        medio_origen_usd = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA, nombre_titular='Cliente Pagar',
            entidad_financiera='Banco Origen Venta', moneda=self.usd,
        )
        medio_destino_pyg = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TRANSFERENCIA, nombre_titular='Cliente Pagar',
            entidad_financiera='Banco Destino Venta', moneda=self.pyg,
        )
        url = reverse('divisas:pagar_transaccion', kwargs={'pk': venta.pk})

        response = self.client.get(url)
        self.assertContains(response, 'Recibís en')

        response = self.client.post(
            url, {'medio_origen': medio_origen_usd.pk, 'medio_destino': medio_destino_pyg.pk},
        )

        self.assertEqual(response.status_code, 302)
        venta.refresh_from_db()
        self.assertEqual(venta.medio_destino, medio_destino_pyg)

    def test_cambiar_de_cliente_activo_avisa_en_vez_de_dar_un_error(self):
        """Si cambia el cliente activo (otro cliente propio), avisa en vez de dar 404 al pagar o ver el detalle."""
        otro_cliente = Cliente.objects.create(
            identificador='PAGAR-OP-003',
            nombre='Otro',
            apellido='Cliente',
            email='otro-cliente-propio-pagar@test.com',
            is_active=True,
        )
        self.usuario.clientes.add(otro_cliente)
        session = self.client.session
        session['cliente_activo_id'] = otro_cliente.pk
        session.save()

        response_get = self.client.get(self.url, follow=True)
        response_post = self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)
        response_detalle = self.client.get(self.detalle_url, follow=True)

        self.assertEqual(response_get.status_code, 200)
        self.assertEqual(response_post.status_code, 200)
        self.assertEqual(response_detalle.status_code, 200)
        self.assertContains(response_get, 'no corresponde al cliente activo')
        self.assertContains(response_post, 'no corresponde al cliente activo')
        self.assertContains(response_detalle, 'no corresponde al cliente activo')
        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 0)


class PagarTransaccionCambioTest(TestCase):
    """Verifica la pantalla de pago de un cambio entre divisas: mismo flujo que compra/venta."""

    def setUp(self):
        """Prepara un cliente con medios de pago (origen en USD, destino en EUR) y un cambio ya 'Confirmado'."""
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-pagar-cambio', 'PAGAR-CAMBIO-001', apellido='Cambio'
        )
        self.usd = _crear_usd_cotizado()
        self.eur = _crear_eur_cotizado()
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
            estado=CalculoTriangulacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        # Un método guardado de billetera digital en USD, para pagar el
        # cambio (medio de origen): igual que transferencia, se paga vía
        # SIPAP, nunca de forma manual.
        self.metodo_pago = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_BILLETERA,
            nombre_titular='Cliente Cambio',
            entidad_financiera='Banco Test',
            moneda=self.usd,
        )
        # Y uno en EUR, para recibir el resultado del cambio (medio de
        # destino): la pantalla de pago exige elegir ambos.
        self.metodo_destino = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_BILLETERA,
            nombre_titular='Cliente Cambio',
            entidad_financiera='Banco Destino',
            moneda=self.eur,
        )
        self.url = reverse('divisas:pagar_transaccion_cambio', kwargs={'pk': self.transaccion.pk})
        self.detalle_url = reverse('divisas:detalle_transaccion_cambio', kwargs={'pk': self.transaccion.pk})

    def test_pagar_con_billetera_o_transferencia_redirige_a_sipap_en_vez_de_registrar_el_pago(self):
        """Tanto una billetera digital como una transferencia se pagan vía SIPAP, no de forma manual."""
        with self.subTest('billetera'):
            response = self.client.post(self.url, {
                'medio_origen': self.metodo_pago.pk, 'medio_destino': self.metodo_destino.pk,
            })

            url_sipap = reverse('divisas:pagar_transaccion_cambio_sipap', kwargs={'pk': self.transaccion.pk})
            self.assertRedirects(
                response, f'{url_sipap}?metodo_pago={self.metodo_pago.pk}', fetch_redirect_response=False,
            )
            self.assertFalse(Pago.objects.filter(calculo_triangulacion=self.transaccion).exists())
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.medio_destino, self.metodo_destino)

        with self.subTest('transferencia'):
            transferencia = MetodoPago.objects.create(
                cliente=self.cliente,
                tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
                nombre_titular='Cliente Cambio',
                entidad_financiera='Banco Itaú',
                numero_cuenta='777888',
                tipo_cuenta='AHORRO',
                moneda=self.usd,
            )

            response = self.client.post(self.url, {
                'medio_origen': transferencia.pk, 'medio_destino': self.metodo_destino.pk,
            })

            url_sipap = reverse('divisas:pagar_transaccion_cambio_sipap', kwargs={'pk': self.transaccion.pk})
            self.assertRedirects(
                response, f'{url_sipap}?metodo_pago={transferencia.pk}', fetch_redirect_response=False,
            )
            self.assertFalse(Pago.objects.filter(calculo_triangulacion=self.transaccion).exists())

    def test_una_tarjeta_nunca_es_una_opcion_para_pagar_un_cambio(self):
        """Una tarjeta solo existe en PYG, y un cambio nunca se paga en PYG: nunca es una opción válida."""
        tarjeta = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Cliente Cambio',
            entidad_financiera='Visa Test',
            numero_tarjeta='4111111111111111',
            moneda=Divisa.objects.get(codigo='PYG'),
        )

        response = self.client.post(self.url, {
            'medio_origen': tarjeta.pk, 'medio_destino': self.metodo_destino.pk,
        })

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertFormError(form, 'medio_origen', 'El medio de pago elegido no es válido para esta transacción.')
        self.assertFalse(Pago.objects.filter(calculo_triangulacion=self.transaccion).exists())

    def test_cancelar_desde_la_pantalla_de_pago_cancela_el_cambio(self):
        """Una vez confirmado, el cliente también puede cancelarlo desde la pantalla de pago."""
        response = self.client.post(self.url, {'accion': 'cancelar'}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_CANCELADA)
        self.assertContains(response, 'El cambio fue cancelado')
        self.assertFalse(Pago.objects.filter(calculo_triangulacion=self.transaccion).exists())

    def test_rechaza_pagar_un_cambio_que_ya_fue_pagado(self):
        """Criterio 3, aplicado al cambio entre divisas."""
        Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_BILLETERA,
            proveedor=Pago.PROVEEDOR_MANUAL,
            identificador_externo=str(self.transaccion.pk),
            monto=self.transaccion.monto_origen,
        )

        response = self.client.post(self.url, {
            'medio_origen': self.metodo_pago.pk, 'medio_destino': self.metodo_destino.pk,
        }, follow=True)

        self.assertContains(response, 'ya fue pagad')
        self.assertEqual(Pago.objects.filter(calculo_triangulacion=self.transaccion).count(), 1)

    def test_detalle_del_cambio_muestra_el_pago_registrado(self):
        """Criterio 5, aplicado al cambio entre divisas.

        El pago llega siempre por confirmación asíncrona (Stripe o el
        webhook de SIPAP), nunca registrado por esta vista: se simula acá
        registrándolo directamente, igual que lo haría esa confirmación.
        """
        Pago.registrar_pago(
            self.transaccion, medio_pago=MetodoPago.TIPO_BILLETERA, proveedor='SIPAP',
            identificador_externo='SPI-TEST-002', monto=self.transaccion.monto_origen,
        )

        response = self.client.get(self.detalle_url)

        self.assertContains(response, 'Billetera Digital')
        self.assertContains(response, 'SPI-TEST-002')
