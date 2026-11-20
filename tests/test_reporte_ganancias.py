"""Pruebas de la HU 'Reporte de ganancias' (desglose por período, divisa, tipo, canal y caja/turno)."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.caja.models import Caja, OperacionVentanilla
from apps.clientes.models import Cliente
from apps.divisas import ganancias, reporte_ganancias
from apps.divisas.models import CalculoOperacion, CalculoTriangulacion, Cotizacion, Divisa

User = get_user_model()

_SIGUIENTE_IDENTIFICADOR = [1]


def _crear_cliente(username):
    """Crea un usuario con un cliente propio asociado, sin loguearlo."""
    usuario = User.objects.create_user(username=username, password='password123')
    _SIGUIENTE_IDENTIFICADOR[0] += 1
    cliente = Cliente.objects.create(
        identificador=f'RGA-{_SIGUIENTE_IDENTIFICADOR[0]:06d}', nombre='Cliente', apellido='Reporte',
        email=f'{username}@test.com', is_active=True,
    )
    cliente.usuarios.add(usuario)
    return usuario, cliente


def _loguear_con_roles(client, username, roles, is_staff=False):
    """Crea un usuario, lo loguea y fija sus roles de Keycloak en la sesión."""
    usuario = User.objects.create_user(username=username, password='password123', is_staff=is_staff)
    client.login(username=username, password='password123')
    session = client.session
    session['keycloak_roles'] = roles
    session.save()
    return usuario


def _crear_usd():
    usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
    Cotizacion.objects.create(divisa=usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
    return usd


def _crear_eur():
    return Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)


def _pisar_creado_en(objeto, creado_en):
    """``creado_en`` es ``auto_now_add``: se pisa con un ``update`` para fijar la fecha de la prueba."""
    if creado_en is not None:
        type(objeto).objects.filter(pk=objeto.pk).update(creado_en=creado_en)
        objeto.refresh_from_db()
    return objeto


def _operacion(usuario, cliente, divisa, tipo=CalculoOperacion.TIPO_COMPRA,
               estado=CalculoOperacion.ESTADO_ACREDITADA, comision=Decimal('1000.00'), creado_en=None):
    operacion = CalculoOperacion.objects.create(
        usuario=usuario, cliente=cliente, tipo=tipo, divisa=divisa, codigo_divisa=divisa.codigo,
        monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
        comision_porcentaje=Decimal('1.000'), comision=comision, monto_final=Decimal('747400.00'),
        estado=estado, vence_en=timezone.now() + timedelta(seconds=300),
    )
    return _pisar_creado_en(operacion, creado_en)


def _cambio(usuario, cliente, origen, destino, estado=CalculoTriangulacion.ESTADO_ACREDITADA,
            comision=Decimal('0.90'), creado_en=None):
    """Cambio con tasa de venta 10.00: la ganancia en PYG es ``comision * 10``."""
    cambio = CalculoTriangulacion.objects.create(
        usuario=usuario, cliente=cliente, divisa_origen=origen, divisa_destino=destino,
        codigo_divisa_origen=origen.codigo, codigo_divisa_destino=destino.codigo,
        monto_origen=Decimal('100.00'), tasa_compra_aplicada=Decimal('7300.00'),
        tasa_venta_aplicada=Decimal('10.00'), tasa_cruzada=Decimal('730.000000'),
        monto_equivalente_pyg=Decimal('730000.00'), comision_porcentaje=Decimal('1.000'),
        comision=comision, monto_final=Decimal('89.10'), estado=estado,
        vence_en=timezone.now() + timedelta(seconds=300),
    )
    return _pisar_creado_en(cambio, creado_en)


def _ventanilla(caja, divisa, tipo=OperacionVentanilla.TIPO_COMPRA, comision=Decimal('500.00'), creado_en=None):
    operacion = OperacionVentanilla.objects.create(
        caja=caja, cajero=caja.usuario, tipo=tipo, divisa=divisa, monto_divisa=Decimal('50.00'),
        tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'), comision=comision,
        monto_pyg=Decimal('373700.00'), cliente_identificador='4111222', cliente_nombre='Cliente Mostrador',
    )
    return _pisar_creado_en(operacion, creado_en)


def _caja(username, abierta_en=None, cerrada_en=None, first_name='', last_name=''):
    """Crea un cajero y su caja; si se pasa ``cerrada_en``, la deja cerrada en ese momento."""
    cajero = User.objects.create_user(
        username=username, password='password123', first_name=first_name, last_name=last_name,
    )
    caja = Caja.objects.create(usuario=cajero)
    campos = {}
    if abierta_en is not None:
        campos['abierta_en'] = abierta_en
    if cerrada_en is not None:
        campos.update(estado=Caja.ESTADO_CERRADA, cerrada_en=cerrada_en)
    if campos:
        Caja.objects.filter(pk=caja.pk).update(**campos)
        caja.refresh_from_db()
    return caja


def _hoy():
    return timezone.localdate()


def _parametros(desde, hasta, agrupacion=None):
    parametros = {'fecha_desde': desde.isoformat(), 'fecha_hasta': hasta.isoformat()}
    if agrupacion is not None:
        parametros['agrupacion'] = agrupacion
    return parametros


class AgruparGananciasTest(TestCase):
    """``agrupar_ganancias``: ganancia y cantidad por día, mes, divisa, tipo y canal (criterio 1)."""

    def _fila(self, creado_en, divisa='USD', tipo=ganancias.CASA_COMPRA, canal=ganancias.CANAL_ONLINE,
              ganancia=Decimal('100.00')):
        return {'creado_en': creado_en, 'divisa': divisa, 'tipo_codigo': tipo, 'canal': canal, 'ganancia_pyg': ganancia}

    def test_por_dia_queda_en_orden_cronologico(self):
        ahora = timezone.now()
        filas = [
            self._fila(ahora, ganancia=Decimal('10.00')),
            self._fila(ahora - timedelta(days=2), ganancia=Decimal('20.00')),
            self._fila(ahora, ganancia=Decimal('5.00')),
        ]

        grupos = reporte_ganancias.agrupar_ganancias(filas, 'dia')

        self.assertEqual([grupo['clave'] for grupo in grupos], sorted(grupo['clave'] for grupo in grupos))
        self.assertEqual(len(grupos), 2)
        self.assertEqual(grupos[-1]['cantidad'], 2)
        self.assertEqual(grupos[-1]['ganancia_pyg'], Decimal('15.00'))
        self.assertEqual(grupos[-1]['etiqueta'], timezone.localtime(ahora).strftime('%d/%m/%Y'))

    def test_por_mes_agrupa_todos_los_dias_del_mismo_mes(self):
        base = timezone.localtime(timezone.now()).replace(day=15)
        filas = [self._fila(base), self._fila(base.replace(day=1)), self._fila(base - timedelta(days=40))]

        grupos = reporte_ganancias.agrupar_ganancias(filas, 'mes')

        self.assertEqual(len(grupos), 2)
        self.assertEqual(grupos[-1]['clave'], base.strftime('%Y-%m'))
        self.assertEqual(grupos[-1]['etiqueta'], base.strftime('%m/%Y'))
        self.assertEqual(grupos[-1]['cantidad'], 2)

    def test_por_divisa_separa_el_par_de_un_cambio(self):
        ahora = timezone.now()
        filas = [self._fila(ahora, divisa='USD'), self._fila(ahora, divisa='USD → EUR'), self._fila(ahora, divisa='USD')]

        grupos = {grupo['clave']: grupo for grupo in reporte_ganancias.agrupar_ganancias(filas, 'divisa')}

        self.assertEqual(grupos['USD']['cantidad'], 2)
        self.assertEqual(grupos['USD → EUR']['cantidad'], 1)

    def test_por_tipo_respeta_el_orden_y_las_etiquetas_del_tablero(self):
        ahora = timezone.now()
        filas = [
            self._fila(ahora, tipo=ganancias.CAMBIO),
            self._fila(ahora, tipo=ganancias.CASA_VENTA),
            self._fila(ahora, tipo=ganancias.CASA_COMPRA),
        ]

        grupos = reporte_ganancias.agrupar_ganancias(filas, 'tipo')

        self.assertEqual([grupo['etiqueta'] for grupo in grupos], ['Compra', 'Venta', 'Cambio'])

    def test_por_canal_distingue_online_y_ventanilla(self):
        ahora = timezone.now()
        filas = [
            self._fila(ahora, canal=ganancias.CANAL_VENTANILLA, ganancia=Decimal('7.00')),
            self._fila(ahora, canal=ganancias.CANAL_ONLINE, ganancia=Decimal('3.00')),
        ]

        grupos = reporte_ganancias.agrupar_ganancias(filas, 'canal')

        self.assertEqual([grupo['etiqueta'] for grupo in grupos], ['Online', 'Ventanilla'])
        self.assertEqual(grupos[1]['ganancia_pyg'], Decimal('7.00'))

    def test_sin_filas_no_hay_grupos(self):
        self.assertEqual(reporte_ganancias.agrupar_ganancias([], 'divisa'), [])


class GenerarReporteGananciasTest(TestCase):
    """``generar_reporte_ganancias``: validación, total general e integración con los tres orígenes."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente('cliente-reporte-ganancias')
        self.usd = _crear_usd()
        self.eur = _crear_eur()

    def test_sin_fechas_no_genera_el_reporte_ni_informa_error(self):
        resultado = reporte_ganancias.generar_reporte_ganancias({})

        self.assertFalse(resultado['reporte_generado'])
        self.assertIsNone(resultado['error_rango'])
        self.assertIsNone(resultado['total'])

    def test_con_una_sola_fecha_tampoco_se_genera(self):
        resultado = reporte_ganancias.generar_reporte_ganancias({'fecha_desde': _hoy().isoformat()})

        self.assertFalse(resultado['reporte_generado'])

    def test_fecha_ilegible_es_un_error_de_rango(self):
        resultado = reporte_ganancias.generar_reporte_ganancias({'fecha_desde': 'ayer', 'fecha_hasta': 'hoy'})

        self.assertEqual(resultado['error_rango'], 'Ingresá un rango de fechas válido.')
        self.assertFalse(resultado['reporte_generado'])

    def test_rango_invertido_es_invalido(self):
        resultado = reporte_ganancias.generar_reporte_ganancias(_parametros(_hoy(), _hoy() - timedelta(days=1)))

        self.assertEqual(resultado['error_rango'], 'La fecha inicial no puede ser posterior a la fecha final.')

    def test_rango_con_fecha_futura_es_invalido(self):
        manana = _hoy() + timedelta(days=1)

        resultado = reporte_ganancias.generar_reporte_ganancias(_parametros(_hoy(), manana))

        self.assertEqual(resultado['error_rango'], 'No se puede consultar un rango con fechas futuras.')

    def test_agrupacion_desconocida_usa_la_por_defecto(self):
        resultado = reporte_ganancias.generar_reporte_ganancias(_parametros(_hoy(), _hoy(), 'inventada'))

        self.assertEqual(resultado['filtros']['agrupacion'], reporte_ganancias.AGRUPACION_POR_DEFECTO)

    def test_sin_operaciones_en_el_periodo_informa_que_no_hay_datos_sin_error(self):
        """Criterio 6."""
        resultado = reporte_ganancias.generar_reporte_ganancias(_parametros(_hoy() - timedelta(days=7), _hoy()))

        self.assertTrue(resultado['reporte_generado'])
        self.assertTrue(resultado['sin_datos'])
        self.assertIsNone(resultado['error_rango'])
        self.assertEqual(resultado['total']['cantidad'], 0)
        self.assertEqual(resultado['total']['ganancia_pyg'], Decimal('0.00'))

    def test_suma_los_tres_origenes_en_el_total_general(self):
        """Criterio 1: compra/venta online, cambio (reconvertido a PYG) y ventanilla."""
        _operacion(self.usuario, self.cliente, self.usd, comision=Decimal('1000.00'))
        _cambio(self.usuario, self.cliente, self.usd, self.eur, comision=Decimal('0.90'))
        caja = _caja('cajero-total')
        _ventanilla(caja, self.usd, comision=Decimal('500.00'))

        resultado = reporte_ganancias.generar_reporte_ganancias(_parametros(_hoy(), _hoy(), 'canal'))

        self.assertFalse(resultado['sin_datos'])
        self.assertEqual(resultado['total']['cantidad'], 3)
        self.assertEqual(resultado['total']['ganancia_pyg'], Decimal('1509.00'))
        por_canal = {grupo['clave']: grupo for grupo in resultado['grupos']}
        self.assertEqual(por_canal[ganancias.CANAL_ONLINE]['ganancia_pyg'], Decimal('1009.00'))
        self.assertEqual(por_canal[ganancias.CANAL_VENTANILLA]['ganancia_pyg'], Decimal('500.00'))

    def test_solo_cuentan_las_operaciones_online_completadas(self):
        _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PENDIENTE)
        _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)
        _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_CANCELADA)
        _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_RETIRADA, comision=Decimal('250.00'))

        resultado = reporte_ganancias.generar_reporte_ganancias(_parametros(_hoy(), _hoy()))

        self.assertEqual(resultado['total']['cantidad'], 1)
        self.assertEqual(resultado['total']['ganancia_pyg'], Decimal('250.00'))

    def test_operaciones_fuera_del_rango_no_se_cuentan(self):
        _operacion(self.usuario, self.cliente, self.usd, creado_en=timezone.now() - timedelta(days=20))
        _operacion(self.usuario, self.cliente, self.usd, comision=Decimal('300.00'))

        resultado = reporte_ganancias.generar_reporte_ganancias(_parametros(_hoy() - timedelta(days=5), _hoy()))

        self.assertEqual(resultado['total']['cantidad'], 1)
        self.assertEqual(resultado['total']['ganancia_pyg'], Decimal('300.00'))

    def test_la_suma_de_los_grupos_coincide_con_el_total(self):
        _operacion(self.usuario, self.cliente, self.usd, comision=Decimal('100.00'), creado_en=timezone.now() - timedelta(days=3))
        _operacion(self.usuario, self.cliente, self.usd, tipo=CalculoOperacion.TIPO_VENTA, comision=Decimal('200.00'))
        _cambio(self.usuario, self.cliente, self.usd, self.eur, comision=Decimal('1.00'))

        for agrupacion in ('dia', 'mes', 'divisa', 'tipo', 'canal'):
            with self.subTest(agrupacion=agrupacion):
                resultado = reporte_ganancias.generar_reporte_ganancias(
                    _parametros(_hoy() - timedelta(days=6), _hoy(), agrupacion),
                )
                self.assertEqual(sum(g['cantidad'] for g in resultado['grupos']), resultado['total']['cantidad'])
                self.assertEqual(
                    sum((g['ganancia_pyg'] for g in resultado['grupos']), Decimal('0.00')),
                    resultado['total']['ganancia_pyg'],
                )


class CoincidenciaConTableroTest(TestCase):
    """Criterio 4: el reporte y el tablero muestran la misma ganancia total para el mismo período."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente('cliente-coincidencia')
        self.usd = _crear_usd()
        self.eur = _crear_eur()

    def test_misma_ganancia_total_que_el_tablero(self):
        _operacion(self.usuario, self.cliente, self.usd, comision=Decimal('1234.56'))
        _operacion(self.usuario, self.cliente, self.usd, comision=Decimal('99.99'), creado_en=timezone.now() - timedelta(days=4))
        _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)
        _operacion(self.usuario, self.cliente, self.usd, creado_en=timezone.now() - timedelta(days=60))
        _cambio(self.usuario, self.cliente, self.usd, self.eur, comision=Decimal('2.35'))
        _ventanilla(_caja('cajero-coincidencia'), self.usd, comision=Decimal('777.00'))
        parametros = _parametros(_hoy() - timedelta(days=10), _hoy())

        tablero = ganancias.generar_tablero(parametros)

        for agrupacion in reporte_ganancias.AGRUPACIONES:
            with self.subTest(agrupacion=agrupacion):
                reporte = reporte_ganancias.generar_reporte_ganancias({**parametros, 'agrupacion': agrupacion})
                self.assertEqual(reporte['total']['ganancia_pyg'], tablero['indicadores']['ganancia_total'])
                self.assertEqual(reporte['total']['cantidad'], tablero['indicadores']['cantidad_operaciones'])


class DesglosePorCajaTest(TestCase):
    """``desglosar_por_caja`` y la agrupación ``caja`` (criterios 2 y 3)."""

    def setUp(self):
        self.usd = _crear_usd()

    def test_cada_caja_muestra_cajero_apertura_cierre_operaciones_y_ganancia(self):
        apertura = timezone.now() - timedelta(hours=8)
        cierre = timezone.now() - timedelta(hours=1)
        caja = _caja('cajero-cerrado', abierta_en=apertura, cerrada_en=cierre, first_name='Ana', last_name='Gómez')
        _ventanilla(caja, self.usd, comision=Decimal('300.00'))
        _ventanilla(caja, self.usd, tipo=OperacionVentanilla.TIPO_VENTA, comision=Decimal('200.00'))

        filas = reporte_ganancias.desglosar_por_caja(_hoy() - timedelta(days=1), _hoy())

        self.assertEqual(len(filas), 1)
        fila = filas[0]
        self.assertEqual(fila['cajero'], 'Ana Gómez')
        self.assertEqual(fila['abierta_en'], caja.abierta_en)
        self.assertEqual(fila['cerrada_en'], caja.cerrada_en)
        self.assertFalse(fila['en_curso'])
        self.assertEqual(fila['cantidad'], 2)
        self.assertEqual(fila['ganancia_pyg'], Decimal('500.00'))

    def test_sin_nombre_completo_muestra_el_usuario(self):
        _caja('cajero-sin-nombre')

        filas = reporte_ganancias.desglosar_por_caja(_hoy(), _hoy())

        self.assertEqual(filas[0]['cajero'], 'cajero-sin-nombre')

    def test_una_caja_abierta_se_identifica_en_curso(self):
        """Criterio 3: sin cierre, ``en_curso`` y ganancia parcial."""
        caja = _caja('cajero-abierto')
        _ventanilla(caja, self.usd, comision=Decimal('150.00'))

        resultado = reporte_ganancias.generar_reporte_ganancias(_parametros(_hoy(), _hoy(), 'caja'))

        fila = resultado['cajas'][0]
        self.assertTrue(fila['en_curso'])
        self.assertIsNone(fila['cerrada_en'])
        self.assertEqual(fila['ganancia_pyg'], Decimal('150.00'))
        self.assertTrue(resultado['total_cajas']['hay_en_curso'])

    def test_solo_aparecen_las_cajas_que_se_superponen_con_el_periodo(self):
        hace_veinte_dias = timezone.now() - timedelta(days=20)
        _caja('cajero-viejo', abierta_en=hace_veinte_dias, cerrada_en=hace_veinte_dias + timedelta(hours=8))
        _caja('cajero-de-hoy')
        abierta_hace_dias = _caja('cajero-largo', abierta_en=timezone.now() - timedelta(days=15))

        filas = reporte_ganancias.desglosar_por_caja(_hoy() - timedelta(days=2), _hoy())

        cajeros = {fila['cajero'] for fila in filas}
        self.assertEqual(cajeros, {'cajero-de-hoy', 'cajero-largo'})
        self.assertTrue(any(fila['caja_id'] == abierta_hace_dias.pk for fila in filas))

    def test_una_caja_abierta_despues_del_periodo_no_aparece(self):
        _caja('cajero-hoy')

        filas = reporte_ganancias.desglosar_por_caja(_hoy() - timedelta(days=5), _hoy() - timedelta(days=1))

        self.assertEqual(filas, [])

    def test_solo_suma_las_operaciones_de_la_caja_dentro_del_periodo(self):
        caja = _caja('cajero-multi-dia', abierta_en=timezone.now() - timedelta(days=3))
        _ventanilla(caja, self.usd, comision=Decimal('100.00'), creado_en=timezone.now() - timedelta(days=3))
        _ventanilla(caja, self.usd, comision=Decimal('40.00'))

        filas = reporte_ganancias.desglosar_por_caja(_hoy(), _hoy())

        self.assertEqual(filas[0]['cantidad'], 1)
        self.assertEqual(filas[0]['ganancia_pyg'], Decimal('40.00'))

    def test_las_cajas_quedan_ordenadas_por_apertura(self):
        _caja('cajero-tarde', abierta_en=timezone.now() - timedelta(hours=1))
        _caja('cajero-temprano', abierta_en=timezone.now() - timedelta(hours=5))

        filas = reporte_ganancias.desglosar_por_caja(_hoy() - timedelta(days=1), _hoy())

        self.assertEqual([fila['cajero'] for fila in filas], ['cajero-temprano', 'cajero-tarde'])

    def test_total_cajas_suma_solo_la_ventanilla_y_el_total_general_todos_los_canales(self):
        usuario, cliente = _crear_cliente('cliente-cajas')
        _operacion(usuario, cliente, self.usd, comision=Decimal('1000.00'))
        caja_a = _caja('cajero-a', abierta_en=timezone.now() - timedelta(hours=3), cerrada_en=timezone.now() - timedelta(hours=1))
        caja_b = _caja('cajero-b')
        _ventanilla(caja_a, self.usd, comision=Decimal('100.00'))
        _ventanilla(caja_b, self.usd, comision=Decimal('50.00'))

        resultado = reporte_ganancias.generar_reporte_ganancias(
            _parametros(_hoy() - timedelta(days=1), _hoy(), 'caja'),
        )

        self.assertEqual(resultado['total_cajas']['cantidad'], 2)
        self.assertEqual(resultado['total_cajas']['ganancia_pyg'], Decimal('150.00'))
        self.assertEqual(resultado['total']['ganancia_pyg'], Decimal('1150.00'))
        self.assertEqual(resultado['grupos'], [])


class ReporteGananciasViewTest(TestCase):
    """Vista ``ReporteGananciasView``: acceso por rol (criterio 7) y lo que se muestra en pantalla."""

    def setUp(self):
        self.url = reverse('divisas:reporte_ganancias')
        self.usd = _crear_usd()

    def test_un_analista_cambiario_genera_el_reporte(self):
        _loguear_con_roles(self.client, 'analista', ['analista_cambiario'])
        usuario, cliente = _crear_cliente('cliente-vista')
        _operacion(usuario, cliente, self.usd, comision=Decimal('1000.00'))

        response = self.client.get(self.url, _parametros(_hoy(), _hoy(), 'divisa'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total']['ganancia_pyg'], Decimal('1000.00'))
        self.assertContains(response, 'USD')
        self.assertContains(response, 'Total general')
        self.assertContains(response, reverse('divisas:descargar_reporte_ganancias', args=['pdf']))
        self.assertContains(response, reverse('divisas:descargar_reporte_ganancias', args=['excel']))

    def test_un_administrador_tambien_accede(self):
        _loguear_con_roles(self.client, 'admin-reporte', ['admin'], is_staff=True)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_sin_fechas_solo_muestra_el_formulario(self):
        _loguear_con_roles(self.client, 'analista-form', ['analista_cambiario'])

        response = self.client.get(self.url)

        self.assertFalse(response.context['reporte_generado'])
        self.assertContains(response, 'Indicá un rango de fechas')
        self.assertNotContains(response, 'Descargar PDF')

    def test_sin_operaciones_informa_que_no_hay_datos_sin_error(self):
        """Criterio 6."""
        _loguear_con_roles(self.client, 'analista-vacio', ['analista_cambiario'])

        response = self.client.get(self.url, _parametros(_hoy() - timedelta(days=30), _hoy()))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reporte_ganancias.MENSAJE_SIN_DATOS)
        self.assertNotContains(response, 'Descargar PDF')

    def test_rango_invalido_muestra_el_motivo(self):
        _loguear_con_roles(self.client, 'analista-rango', ['analista_cambiario'])

        response = self.client.get(self.url, _parametros(_hoy(), _hoy() - timedelta(days=1)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'La fecha inicial no puede ser posterior a la fecha final.')

    def test_desglose_por_caja_muestra_en_curso_y_ganancia_parcial(self):
        """Criterios 2 y 3 en pantalla."""
        _loguear_con_roles(self.client, 'analista-caja', ['analista_cambiario'])
        caja = _caja('cajero-pantalla', first_name='Luis', last_name='Pérez')
        _ventanilla(caja, self.usd, comision=Decimal('80.00'))

        response = self.client.get(self.url, _parametros(_hoy(), _hoy(), 'caja'))

        self.assertContains(response, 'Luis Pérez')
        self.assertContains(response, 'En curso')
        self.assertContains(response, '(parcial)')

    def test_un_cliente_no_puede_acceder(self):
        _loguear_con_roles(self.client, 'cliente-sin-permiso', ['cliente'])

        response = self.client.get(self.url, _parametros(_hoy(), _hoy()))

        self.assertEqual(response.status_code, 403)

    def test_un_cajero_no_puede_acceder(self):
        _loguear_con_roles(self.client, 'cajero-sin-permiso', ['cajero'])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_un_usuario_sin_roles_no_puede_acceder(self):
        _loguear_con_roles(self.client, 'sin-roles', [])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_un_anonimo_es_redirigido_al_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_el_menu_muestra_el_enlace_al_analista(self):
        _loguear_con_roles(self.client, 'analista-menu', ['analista_cambiario'])

        response = self.client.get(reverse('home'))

        self.assertContains(response, self.url)


class DescargarReporteGananciasViewTest(TestCase):
    """Descargas en PDF y Excel con los mismos datos, filtros y fecha de generación (criterio 5)."""

    def setUp(self):
        self.usd = _crear_usd()
        self.eur = _crear_eur()
        self.usuario, self.cliente = _crear_cliente('cliente-descarga')
        _loguear_con_roles(self.client, 'analista-descarga', ['analista_cambiario'])

    def _url(self, formato):
        return reverse('divisas:descargar_reporte_ganancias', args=[formato])

    def _filas_excel(self, contenido):
        hoja = load_workbook(BytesIO(contenido)).active
        return [list(fila) for fila in hoja.iter_rows(values_only=True)]

    def test_descarga_el_pdf(self):
        _operacion(self.usuario, self.cliente, self.usd)

        response = self.client.get(self._url('pdf'), _parametros(_hoy(), _hoy(), 'divisa'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('.pdf', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_el_excel_tiene_filtros_fecha_de_generacion_grupos_y_total(self):
        _operacion(self.usuario, self.cliente, self.usd, comision=Decimal('1000.00'))
        _cambio(self.usuario, self.cliente, self.usd, self.eur, comision=Decimal('0.50'))
        parametros = _parametros(_hoy(), _hoy(), 'divisa')

        response = self.client.get(self._url('excel'), parametros)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filas = self._filas_excel(response.content)
        self.assertEqual(filas[0][0], 'Reporte de ganancias')
        self.assertIn(_hoy().strftime('%d/%m/%Y'), filas[1][0])
        self.assertIn('Agrupado por: Divisa', filas[1][0])
        self.assertTrue(filas[2][0].startswith('Generado el '))
        self.assertIn(['USD', 1, 1000.0], [fila[:3] for fila in filas])
        self.assertIn(['USD → EUR', 1, 5.0], [fila[:3] for fila in filas])
        self.assertIn(['Total general (todos los canales)', 2, 1005.0], [fila[:3] for fila in filas])

    def test_pdf_y_excel_salen_del_mismo_reporte_que_la_pantalla(self):
        _operacion(self.usuario, self.cliente, self.usd, comision=Decimal('321.00'))
        parametros = _parametros(_hoy(), _hoy(), 'tipo')

        pantalla = self.client.get(reverse('divisas:reporte_ganancias'), parametros)
        excel = self._filas_excel(self.client.get(self._url('excel'), parametros).content)

        total_excel = next(fila for fila in excel if fila[0] == 'Total general (todos los canales)')
        self.assertEqual(Decimal(str(total_excel[2])), pantalla.context['total']['ganancia_pyg'])
        self.assertEqual(total_excel[1], pantalla.context['total']['cantidad'])

    def test_excel_por_caja_marca_en_curso_y_parcial(self):
        caja = _caja('cajero-excel', first_name='Eva', last_name='Ruiz')
        _ventanilla(caja, self.usd, comision=Decimal('60.00'))

        response = self.client.get(self._url('excel'), _parametros(_hoy(), _hoy(), 'caja'))

        filas = self._filas_excel(response.content)
        encabezado = filas.index(['Cajero', 'Apertura', 'Cierre', 'Operaciones', 'Ganancia (PYG)', 'Observación'])
        fila_caja = filas[encabezado + 1]
        self.assertEqual(fila_caja[0], 'Eva Ruiz')
        self.assertEqual(fila_caja[2], 'En curso')
        self.assertEqual(fila_caja[3], 1)
        self.assertEqual(fila_caja[4], 60.0)
        self.assertEqual(fila_caja[5], 'Parcial')
        self.assertTrue(any(fila[0] == 'Total de ventanilla (cajas del período) — parcial' for fila in filas))

    def test_pdf_por_caja_se_genera(self):
        caja = _caja('cajero-pdf', abierta_en=timezone.now() - timedelta(hours=4), cerrada_en=timezone.now())
        _ventanilla(caja, self.usd)

        response = self.client.get(self._url('pdf'), _parametros(_hoy(), _hoy(), 'caja'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_sin_datos_vuelve_a_la_pantalla_sin_descargar(self):
        parametros = _parametros(_hoy() - timedelta(days=3), _hoy())

        response = self.client.get(self._url('pdf'), parametros)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith(reverse('divisas:reporte_ganancias')))

    def test_rango_invalido_vuelve_a_la_pantalla(self):
        response = self.client.get(self._url('excel'), _parametros(_hoy(), _hoy() - timedelta(days=2)))

        self.assertEqual(response.status_code, 302)

    def test_sin_fechas_vuelve_a_la_pantalla(self):
        response = self.client.get(self._url('excel'))

        self.assertEqual(response.status_code, 302)

    def test_formato_desconocido_es_404(self):
        _operacion(self.usuario, self.cliente, self.usd)

        response = self.client.get(self._url('csv'), _parametros(_hoy(), _hoy()))

        self.assertEqual(response.status_code, 404)

    def test_un_cliente_no_puede_descargar(self):
        _operacion(self.usuario, self.cliente, self.usd)
        self.client.logout()
        _loguear_con_roles(self.client, 'cliente-descarga-denegada', ['cliente'])

        response = self.client.get(self._url('pdf'), _parametros(_hoy(), _hoy()))

        self.assertEqual(response.status_code, 403)
