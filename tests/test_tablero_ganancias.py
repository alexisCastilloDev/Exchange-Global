"""Pruebas de la HU 'Tablero de control de ganancias' (epic GE-14)."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.caja.models import Caja, OperacionVentanilla
from apps.clientes.models import Cliente
from apps.divisas import ganancias
from apps.divisas.models import CalculoOperacion, CalculoTriangulacion, Cotizacion, Divisa

User = get_user_model()


_SIGUIENTE_IDENTIFICADOR = [1]


def _crear_cliente(username):
    """Crea un usuario con un cliente propio asociado, sin loguearlo."""
    usuario = User.objects.create_user(username=username, password='password123')
    _SIGUIENTE_IDENTIFICADOR[0] += 1
    cliente = Cliente.objects.create(
        identificador=f'GAN-{_SIGUIENTE_IDENTIFICADOR[0]:06d}', nombre='Cliente', apellido='Test',
        email=f'{username}@test.com', is_active=True,
    )
    cliente.usuarios.add(usuario)
    return usuario, cliente


def _crear_admin_logueado(client, username='admin-ganancias'):
    """Crea un usuario con rol 'admin' en Keycloak, logueado."""
    usuario = User.objects.create_user(username=username, password='password123', is_staff=True)
    client.login(username=username, password='password123')
    session = client.session
    session['keycloak_roles'] = ['admin']
    session.save()
    return usuario


def _crear_usd_cotizado():
    usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
    Cotizacion.objects.create(divisa=usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
    return usd


def _crear_eur():
    return Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)


def _operacion(usuario, cliente, divisa, tipo, estado, comision=Decimal('7400.00'), creado_en=None):
    """Crea una ``CalculoOperacion``; si se pasa ``creado_en``, lo pisa después (``auto_now_add``)."""
    operacion = CalculoOperacion.objects.create(
        usuario=usuario, cliente=cliente, tipo=tipo, divisa=divisa, codigo_divisa=divisa.codigo,
        monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
        comision_porcentaje=Decimal('1.000'), comision=comision, monto_final=Decimal('747400.00'),
        estado=estado, vence_en=timezone.now() + timedelta(seconds=300),
    )
    if creado_en is not None:
        operacion.creado_en = creado_en
        operacion.save(update_fields=['creado_en'])
    return operacion


def _cambio(usuario, cliente, origen, destino, estado, comision=Decimal('0.90'), creado_en=None):
    """Crea una ``CalculoTriangulacion`` con una tasa de venta aplicada fácil de verificar (10.00)."""
    cambio = CalculoTriangulacion.objects.create(
        usuario=usuario, cliente=cliente, divisa_origen=origen, divisa_destino=destino,
        codigo_divisa_origen=origen.codigo, codigo_divisa_destino=destino.codigo,
        monto_origen=Decimal('100.00'), tasa_compra_aplicada=Decimal('7300.00'),
        tasa_venta_aplicada=Decimal('10.00'), tasa_cruzada=Decimal('730.000000'),
        monto_equivalente_pyg=Decimal('730000.00'), comision_porcentaje=Decimal('1.000'),
        comision=comision, monto_final=Decimal('89.10'), estado=estado,
        vence_en=timezone.now() + timedelta(seconds=300),
    )
    if creado_en is not None:
        cambio.creado_en = creado_en
        cambio.save(update_fields=['creado_en'])
    return cambio


def _ventanilla(cajero, caja, divisa, tipo, comision=Decimal('3700.00'), creado_en=None):
    operacion = OperacionVentanilla.objects.create(
        caja=caja, cajero=cajero, tipo=tipo, divisa=divisa, monto_divisa=Decimal('50.00'),
        tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'), comision=comision,
        monto_pyg=Decimal('373700.00'), cliente_identificador='4111222', cliente_nombre='Cliente Mostrador',
    )
    if creado_en is not None:
        operacion.creado_en = creado_en
        operacion.save(update_fields=['creado_en'])
    return operacion


class FilaNormalizadaTest(TestCase):
    """``_fila_operacion``/``_fila_cambio``/``_fila_ventanilla``: la ganancia siempre normalizada a PYG."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente('cliente-filas')
        self.usd = _crear_usd_cotizado()
        self.eur = _crear_eur()

    def test_tipo_de_operacion_online_se_invierte_a_la_perspectiva_de_la_casa(self):
        """CalculoOperacion.TIPO_COMPRA (cliente compra) es, para la casa, una venta."""
        compra_cliente = _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA)
        venta_cliente = _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_VENTA, CalculoOperacion.ESTADO_ACREDITADA)

        self.assertEqual(ganancias._fila_operacion(compra_cliente)['tipo_codigo'], ganancias.CASA_VENTA)
        self.assertEqual(ganancias._fila_operacion(venta_cliente)['tipo_codigo'], ganancias.CASA_COMPRA)

    def test_tipo_de_operacion_de_ventanilla_no_se_invierte(self):
        """OperacionVentanilla.TIPO_COMPRA ya está en la perspectiva de la casa."""
        cajero = User.objects.create_user(username='cajero-filas', password='password123')
        caja = Caja.objects.create(usuario=cajero)
        casa_compra = _ventanilla(cajero, caja, self.usd, OperacionVentanilla.TIPO_COMPRA)
        casa_venta = _ventanilla(cajero, caja, self.usd, OperacionVentanilla.TIPO_VENTA)

        self.assertEqual(ganancias._fila_ventanilla(casa_compra)['tipo_codigo'], ganancias.CASA_COMPRA)
        self.assertEqual(ganancias._fila_ventanilla(casa_venta)['tipo_codigo'], ganancias.CASA_VENTA)

    def test_ganancia_de_un_cambio_se_reconvierte_de_la_divisa_destino_a_pyg(self):
        """La comisión de un cambio está en destino (no PYG): se multiplica por la tasa de venta aplicada."""
        cambio = _cambio(self.usuario, self.cliente, self.usd, self.eur, CalculoTriangulacion.ESTADO_ACREDITADA, comision=Decimal('0.90'))

        fila = ganancias._fila_cambio(cambio)

        self.assertEqual(fila['ganancia_pyg'], Decimal('9.00'))
        self.assertEqual(fila['tipo_codigo'], ganancias.CAMBIO)
        self.assertEqual(fila['canal'], ganancias.CANAL_ONLINE)


class CalcularIndicadoresTest(TestCase):
    """``calcular_indicadores`` (criterio 1)."""

    def test_sin_filas_todo_queda_en_cero(self):
        indicadores = ganancias.calcular_indicadores([])

        self.assertEqual(indicadores['ganancia_total'], Decimal('0.00'))
        self.assertEqual(indicadores['cantidad_operaciones'], 0)
        self.assertEqual(indicadores['ganancia_promedio'], Decimal('0.00'))

    def test_promedio_es_la_ganancia_total_sobre_la_cantidad(self):
        filas = [
            {'ganancia_pyg': Decimal('1000.00'), 'monto_pyg': Decimal('10000.00')},
            {'ganancia_pyg': Decimal('3000.00'), 'monto_pyg': Decimal('30000.00')},
        ]

        indicadores = ganancias.calcular_indicadores(filas)

        self.assertEqual(indicadores['ganancia_total'], Decimal('4000.00'))
        self.assertEqual(indicadores['monto_total_operado'], Decimal('40000.00'))
        self.assertEqual(indicadores['cantidad_operaciones'], 2)
        self.assertEqual(indicadores['ganancia_promedio'], Decimal('2000.00'))


class CalcularVariacionTest(TestCase):
    """``calcular_variacion`` (criterio 5)."""

    def test_sin_ganancia_anterior_la_variacion_es_indefinida(self):
        self.assertIsNone(ganancias.calcular_variacion(Decimal('100.00'), Decimal('0.00')))

    def test_aumento_da_un_porcentaje_positivo(self):
        variacion = ganancias.calcular_variacion(Decimal('150.00'), Decimal('100.00'))
        self.assertEqual(variacion, Decimal('50.00'))

    def test_caida_da_un_porcentaje_negativo(self):
        variacion = ganancias.calcular_variacion(Decimal('50.00'), Decimal('100.00'))
        self.assertEqual(variacion, Decimal('-50.00'))


class ResolverPeriodoTest(TestCase):
    """``resolver_periodo`` (criterio 2 y la validación de rango)."""

    def test_sin_parametros_usa_el_periodo_por_defecto(self):
        desde, hasta, periodo, error = ganancias.resolver_periodo({})

        self.assertIsNone(error)
        self.assertEqual(periodo, ganancias.PERIODO_POR_DEFECTO)
        self.assertEqual(hasta, timezone.localdate())

    def test_periodo_semana_cubre_siete_dias(self):
        desde, hasta, periodo, error = ganancias.resolver_periodo({'periodo': 'semana'})

        self.assertEqual(periodo, 'semana')
        self.assertEqual((hasta - desde).days, 6)

    def test_rango_propio_completo_tiene_prioridad_sobre_periodo(self):
        hoy = timezone.localdate().isoformat()
        desde, hasta, periodo, error = ganancias.resolver_periodo(
            {'periodo': 'anio', 'fecha_desde': hoy, 'fecha_hasta': hoy}
        )

        self.assertEqual(periodo, 'custom')
        self.assertIsNone(error)

    def test_rango_invertido_es_invalido(self):
        hoy = timezone.localdate().isoformat()
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()

        _, _, _, error = ganancias.resolver_periodo({'fecha_desde': hoy, 'fecha_hasta': ayer})

        self.assertIsNotNone(error)

    def test_rango_con_fecha_futura_es_invalido(self):
        mañana = (timezone.localdate() + timedelta(days=1)).isoformat()

        _, _, _, error = ganancias.resolver_periodo({'fecha_desde': mañana, 'fecha_hasta': mañana})

        self.assertIsNotNone(error)


class AgrupacionYEvolucionTest(TestCase):
    """``_agrupacion_segun_duracion``/``calcular_evolucion`` (criterio 3)."""

    def test_rango_corto_agrupa_por_dia(self):
        hoy = timezone.localdate()
        self.assertEqual(ganancias._agrupacion_segun_duracion(hoy - timedelta(days=6), hoy), 'dia')

    def test_rango_medio_agrupa_por_semana(self):
        hoy = timezone.localdate()
        self.assertEqual(ganancias._agrupacion_segun_duracion(hoy - timedelta(days=90), hoy), 'semana')

    def test_rango_largo_agrupa_por_mes(self):
        hoy = timezone.localdate()
        self.assertEqual(ganancias._agrupacion_segun_duracion(hoy - timedelta(days=365), hoy), 'mes')

    def test_evolucion_queda_en_orden_cronologico(self):
        hoy = timezone.localdate()
        filas = [
            {'creado_en': timezone.now(), 'ganancia_pyg': Decimal('100.00')},
            {'creado_en': timezone.now() - timedelta(days=2), 'ganancia_pyg': Decimal('50.00')},
        ]

        evolucion = ganancias.calcular_evolucion(filas, hoy - timedelta(days=6), hoy)

        periodos = [punto['periodo'] for punto in evolucion['puntos']]
        self.assertEqual(periodos, sorted(periodos))
        self.assertEqual(evolucion['agrupacion'], 'dia')


class CalcularDistribucionTest(TestCase):
    """``calcular_distribucion`` (criterio 4)."""

    def test_agrupa_por_tipo_canal_y_divisa(self):
        filas = [
            {'tipo_codigo': ganancias.CASA_COMPRA, 'canal': ganancias.CANAL_ONLINE, 'divisa': 'USD', 'ganancia_pyg': Decimal('100.00')},
            {'tipo_codigo': ganancias.CASA_COMPRA, 'canal': ganancias.CANAL_VENTANILLA, 'divisa': 'USD', 'ganancia_pyg': Decimal('200.00')},
            {'tipo_codigo': ganancias.CAMBIO, 'canal': ganancias.CANAL_ONLINE, 'divisa': 'USD → EUR', 'ganancia_pyg': Decimal('9.00')},
        ]

        distribucion = ganancias.calcular_distribucion(filas)

        self.assertEqual(distribucion['por_tipo'][ganancias.CASA_COMPRA]['cantidad'], 2)
        self.assertEqual(distribucion['por_tipo'][ganancias.CASA_COMPRA]['ganancia_pyg'], Decimal('300.00'))
        self.assertEqual(distribucion['por_tipo'][ganancias.CASA_VENTA]['cantidad'], 0)
        self.assertEqual(distribucion['por_canal'][ganancias.CANAL_VENTANILLA]['cantidad'], 1)
        self.assertEqual(distribucion['por_divisa']['USD']['cantidad'], 2)
        self.assertEqual(distribucion['por_divisa']['USD → EUR']['ganancia_pyg'], Decimal('9.00'))


class GenerarTableroIntegracionTest(TestCase):
    """``generar_tablero``/``_todas_las_ganancias``: integra los tres orígenes y el criterio 6."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente('cliente-tablero')
        self.usd = _crear_usd_cotizado()
        self.cajero = User.objects.create_user(username='cajero-tablero', password='password123')
        self.caja = Caja.objects.create(usuario=self.cajero)

    def test_solo_cuentan_las_transacciones_completadas_online(self):
        """Criterio 6: pendiente, cancelada, vencida y pagada (entrega pendiente) no suman ganancia."""
        _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_PENDIENTE)
        _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_CANCELADA)
        _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_VENCIDA)
        _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_PAGO_EXPIRADO)
        _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_PAGADA)
        acreditada = _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA)

        resultado = ganancias.generar_tablero({'periodo': 'anio'})

        self.assertEqual(resultado['indicadores']['cantidad_operaciones'], 1)
        self.assertEqual(resultado['indicadores']['ganancia_total'], acreditada.comision)

    def test_una_operacion_de_ventanilla_siempre_cuenta(self):
        """Una OperacionVentanilla no tiene estado propio: siempre está completada."""
        _ventanilla(self.cajero, self.caja, self.usd, OperacionVentanilla.TIPO_COMPRA, comision=Decimal('1000.00'))

        resultado = ganancias.generar_tablero({'periodo': 'anio'})

        self.assertEqual(resultado['indicadores']['cantidad_operaciones'], 1)
        self.assertEqual(resultado['indicadores']['ganancia_total'], Decimal('1000.00'))

    def test_transaccion_fuera_del_periodo_no_se_cuenta(self):
        _operacion(
            self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA,
            creado_en=timezone.now() - timedelta(days=400),
        )

        resultado = ganancias.generar_tablero({'periodo': 'anio'})

        self.assertEqual(resultado['indicadores']['cantidad_operaciones'], 0)

    def test_rango_invalido_no_calcula_ningun_indicador(self):
        hoy = timezone.localdate().isoformat()
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()

        resultado = ganancias.generar_tablero({'fecha_desde': hoy, 'fecha_hasta': ayer})

        self.assertIsNotNone(resultado['error_rango'])
        self.assertIsNone(resultado['indicadores'])

    def test_variacion_compara_contra_el_rango_anterior_equivalente(self):
        """Una ganancia del doble que el período anterior equivalente da +100%."""
        hoy = timezone.localdate()
        _operacion(
            self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA,
            comision=Decimal('100.00'), creado_en=timezone.now() - timedelta(days=10),
        )
        _operacion(
            self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA,
            comision=Decimal('200.00'), creado_en=timezone.now() - timedelta(days=2),
        )

        resultado = ganancias.generar_tablero({'fecha_desde': (hoy - timedelta(days=6)).isoformat(), 'fecha_hasta': hoy.isoformat()})

        self.assertEqual(resultado['indicadores']['ganancia_total'], Decimal('200.00'))
        self.assertEqual(resultado['variacion_ganancia'], Decimal('100.00'))


class TableroGananciasViewTest(TestCase):
    """Vista ``TableroGananciasView`` (criterios 1, 2, 7 y 8)."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente('cliente-vista-tablero')
        self.usd = _crear_usd_cotizado()
        self.url = reverse('divisas:tablero_ganancias')

    def test_un_administrador_ve_el_tablero(self):
        _crear_admin_logueado(self.client)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['indicadores'])

    def test_un_usuario_sin_rol_admin_no_puede_acceder(self):
        cliente = User.objects.create_user(username='cliente-sin-admin', password='password123')
        self.client.login(username='cliente-sin-admin', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_sin_operaciones_completadas_muestra_cero_sin_error(self):
        _crear_admin_logueado(self.client)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['error_rango'])
        self.assertEqual(response.context['indicadores']['cantidad_operaciones'], 0)
        self.assertContains(response, 'No hay operaciones completadas')

    def test_rango_invalido_muestra_el_error_de_validacion(self):
        _crear_admin_logueado(self.client)
        hoy = timezone.localdate().isoformat()
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()

        response = self.client.get(self.url, {'fecha_desde': hoy, 'fecha_hasta': ayer})

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['error_rango'])

    def test_con_operaciones_completadas_se_ven_los_indicadores_y_el_grafico(self):
        _crear_admin_logueado(self.client)
        _operacion(self.usuario, self.cliente, self.usd, CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA)

        response = self.client.get(self.url, {'periodo': 'anio'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['indicadores']['cantidad_operaciones'], 1)
        self.assertContains(response, 'graficoGanancias')
