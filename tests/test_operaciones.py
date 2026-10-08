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
    Divisa,
    Pago,
    PagoRechazadoError,
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
        # Criterio 4 de "Compra de divisas" (GE-30): tipo, cliente activo y fecha
        # quedan registrados; divisa/monto ya se verifican arriba.
        self.assertEqual(calculo.tipo, CalculoOperacion.TIPO_COMPRA)
        self.assertEqual(calculo.cliente, self.cliente)
        self.assertIsNotNone(calculo.creado_en)

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
        """Prepara un cliente con un método de pago y una compra ya 'Confirmada'."""
        self.usuario, self.cliente = _crear_cliente_logueado(
            self.client, 'cliente-pagar-op', 'PAGAR-OP-001', apellido='Pagar'
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
            estado=CalculoOperacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        self.metodo_pago = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Cliente Pagar',
            entidad_financiera='Banco Test',
            numero_cuenta='111222',
            tipo_cuenta='CORRIENTE',
        )
        self.url = reverse('divisas:pagar_transaccion', kwargs={'pk': self.transaccion.pk})
        self.detalle_url = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.transaccion.pk})

    def test_pantalla_de_pago_muestra_los_metodos_de_pago_del_cliente(self):
        """La pantalla ofrece elegir entre los métodos de pago ya guardados por el cliente."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Banco Test')

    def test_pagar_con_un_metodo_guardado_registra_el_pago_y_marca_pagada(self):
        """Criterios 1 y 2: se registra el pago con todos sus datos y la transacción pasa a 'Pagada'."""
        response = self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)
        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertEqual(pago.medio_pago, MetodoPago.TIPO_TRANSFERENCIA)
        self.assertEqual(pago.metodo_pago, self.metodo_pago)
        self.assertEqual(pago.monto, self.transaccion.monto_final)
        self.assertContains(response, 'El pago se registró correctamente')

    def test_no_ofrece_el_formulario_de_pago_si_la_transaccion_no_esta_confirmada(self):
        """Una transacción pendiente todavía no puede pagarse."""
        self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
        self.transaccion.save(update_fields=['estado'])

        response = self.client.get(self.url)

        self.assertNotContains(response, 'name="metodo_pago"')

    def test_rechaza_pagar_una_transaccion_que_ya_fue_pagada(self):
        """Criterio 3: un segundo intento de pago, por cualquier medio, se rechaza."""
        Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_TRANSFERENCIA,
            proveedor=Pago.PROVEEDOR_MANUAL,
            identificador_externo=str(self.transaccion.pk),
            monto=self.transaccion.monto_final,
        )

        response = self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

        self.assertContains(response, 'ya fue pagada')
        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 1)

    def test_reenviar_el_mismo_pago_no_crea_un_segundo_registro(self):
        """Criterio 4: un doble envío del mismo pago (p. ej. doble clic) no lo duplica."""
        self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk})
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)

        response = self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 1)
        self.assertContains(response, 'ya fue pagada')

    def test_detalle_muestra_el_pago_registrado(self):
        """Criterio 5: el detalle muestra medio, monto, fecha e identificador del pago."""
        self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk})

        response = self.client.get(self.detalle_url)

        self.assertContains(response, 'Transferencia Bancaria')
        self.assertContains(response, formato(self.transaccion.monto_final))
        self.assertContains(response, str(self.transaccion.pk))

    def test_detalle_indica_que_no_hay_pago_registrado_todavia(self):
        """Criterio 5: sin pago, el detalle lo indica explícitamente."""
        response = self.client.get(self.detalle_url)

        self.assertContains(response, 'Todavía no tiene un pago registrado')

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
        """Prepara un cliente con un método de pago y un cambio ya 'Confirmado'."""
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
        self.metodo_pago = MetodoPago.objects.create(
            cliente=self.cliente,
            tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Cliente Cambio',
            entidad_financiera='Visa Test',
            numero_tarjeta='4111111111111111',
        )
        self.url = reverse('divisas:pagar_transaccion_cambio', kwargs={'pk': self.transaccion.pk})
        self.detalle_url = reverse('divisas:detalle_transaccion_cambio', kwargs={'pk': self.transaccion.pk})

    def test_pagar_un_cambio_confirmado_registra_el_pago_y_lo_marca_pagado(self):
        """Criterios 1 y 2, aplicados al cambio entre divisas."""
        response = self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

        self.transaccion.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_PAGADA)
        pago = Pago.objects.get(calculo_triangulacion=self.transaccion)
        self.assertEqual(pago.medio_pago, MetodoPago.TIPO_TARJETA)
        self.assertEqual(pago.monto, self.transaccion.monto_final)

    def test_rechaza_pagar_un_cambio_que_ya_fue_pagado(self):
        """Criterio 3, aplicado al cambio entre divisas."""
        Pago.registrar_pago(
            self.transaccion,
            medio_pago=MetodoPago.TIPO_TARJETA,
            proveedor=Pago.PROVEEDOR_MANUAL,
            identificador_externo=str(self.transaccion.pk),
            monto=self.transaccion.monto_final,
        )

        response = self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

        self.assertContains(response, 'ya fue pagad')
        self.assertEqual(Pago.objects.filter(calculo_triangulacion=self.transaccion).count(), 1)

    def test_detalle_del_cambio_muestra_el_pago_registrado(self):
        """Criterio 5, aplicado al cambio entre divisas."""
        self.client.post(self.url, {'metodo_pago': self.metodo_pago.pk})

        response = self.client.get(self.detalle_url)

        self.assertContains(response, 'Tarjeta de Débito/Crédito')
        self.assertContains(response, str(self.transaccion.pk))
