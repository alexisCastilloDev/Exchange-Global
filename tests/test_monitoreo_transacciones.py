"""Pruebas de la HU 'Monitoreo de transacciones y reportes' (epic GE-14)."""

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
from apps.divisas import monitoreo
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    ContadorDocumentoElectronico,
    Divisa,
    DocumentoElectronico,
    Pago,
)

User = get_user_model()

_SIGUIENTE = [1]


def _crear_cliente(nombre='Ana', apellido='Gómez'):
    """Crea un usuario con un cliente propio asociado, sin loguearlo."""
    _SIGUIENTE[0] += 1
    usuario = User.objects.create_user(username=f'mon-{_SIGUIENTE[0]}', password='password123')
    cliente = Cliente.objects.create(
        identificador=f'MON-{_SIGUIENTE[0]:06d}', nombre=nombre, apellido=apellido,
        email=f'mon-{_SIGUIENTE[0]}@test.com', is_active=True,
    )
    cliente.usuarios.add(usuario)
    return usuario, cliente


def _loguear(client, roles, username='monitor'):
    """Loguea un usuario con los roles de Keycloak indicados."""
    User.objects.create_user(username=username, password='password123', is_staff='admin' in roles)
    client.login(username=username, password='password123')
    session = client.session
    session['keycloak_roles'] = roles
    session.save()


def _divisa(codigo):
    return Divisa.objects.get_or_create(codigo=codigo, defaults={'nombre': codigo, 'simbolo': codigo, 'activa': True})[0]


def _operacion(usuario, cliente, tipo=CalculoOperacion.TIPO_COMPRA, estado=CalculoOperacion.ESTADO_ACREDITADA,
               codigo='USD', creado_en=None):
    operacion = CalculoOperacion.objects.create(
        usuario=usuario, cliente=cliente, tipo=tipo, divisa=_divisa(codigo), codigo_divisa=codigo,
        monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
        comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
        estado=estado, vence_en=timezone.now() + timedelta(seconds=300),
    )
    if creado_en is not None:
        operacion.creado_en = creado_en
        operacion.save(update_fields=['creado_en'])
    return operacion


def _cambio(usuario, cliente, estado=CalculoTriangulacion.ESTADO_ACREDITADA, origen='USD', destino='EUR'):
    return CalculoTriangulacion.objects.create(
        usuario=usuario, cliente=cliente, divisa_origen=_divisa(origen), divisa_destino=_divisa(destino),
        codigo_divisa_origen=origen, codigo_divisa_destino=destino,
        monto_origen=Decimal('100.00'), tasa_compra_aplicada=Decimal('7300.00'),
        tasa_venta_aplicada=Decimal('7900.00'), tasa_cruzada=Decimal('0.924050'),
        monto_equivalente_pyg=Decimal('730000.00'), comision_porcentaje=Decimal('1.000'),
        comision=Decimal('0.90'), monto_final=Decimal('91.50'), estado=estado,
        vence_en=timezone.now() + timedelta(seconds=300),
    )


def _ventanilla(tipo=OperacionVentanilla.TIPO_COMPRA, codigo='USD', nombre='Cliente Mostrador'):
    cajero = User.objects.create_user(username=f'cajero-{_SIGUIENTE[0]}-{tipo}-{codigo}', password='password123')
    _SIGUIENTE[0] += 1
    caja = Caja.objects.create(usuario=cajero)
    return OperacionVentanilla.objects.create(
        caja=caja, cajero=cajero, tipo=tipo, divisa=_divisa(codigo), monto_divisa=Decimal('50.00'),
        tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'), comision=Decimal('3700.00'),
        monto_pyg=Decimal('373700.00'), cliente_identificador='4111222', cliente_nombre=nombre,
    )


class FilasNormalizadasTest(TestCase):
    """Cada modelo se normaliza con tipo en perspectiva de la casa, canal y estado."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente()

    def test_tipo_online_se_invierte_a_la_perspectiva_de_la_casa(self):
        compra_cliente = _operacion(self.usuario, self.cliente, tipo=CalculoOperacion.TIPO_COMPRA)
        venta_cliente = _operacion(self.usuario, self.cliente, tipo=CalculoOperacion.TIPO_VENTA)
        self.assertEqual(monitoreo._fila_operacion(compra_cliente)['tipo_codigo'], monitoreo.CASA_VENTA)
        self.assertEqual(monitoreo._fila_operacion(venta_cliente)['tipo_codigo'], monitoreo.CASA_COMPRA)

    def test_ventanilla_conserva_su_tipo_y_siempre_esta_completada(self):
        fila = monitoreo._fila_ventanilla(_ventanilla(tipo=OperacionVentanilla.TIPO_COMPRA))
        self.assertEqual(fila['tipo_codigo'], monitoreo.CASA_COMPRA)
        self.assertEqual(fila['canal'], monitoreo.CANAL_VENTANILLA)
        self.assertEqual(fila['estado_codigo'], monitoreo.ESTADO_COMPLETADA)
        self.assertIn('Cliente Mostrador', fila['cliente'])
        self.assertEqual(fila['atencion'], '')

    def test_cambio_incluye_ambas_divisas(self):
        fila = monitoreo._fila_cambio(_cambio(self.usuario, self.cliente))
        self.assertEqual(fila['divisas'], ['USD', 'EUR'])
        self.assertEqual(fila['tipo_codigo'], monitoreo.CAMBIO)
        self.assertEqual(fila['monto_pyg'], Decimal('730000.00'))


class ListadoYAccesoTest(TestCase):
    """Criterios 1 y 6: listado de todos los clientes y control de acceso por rol."""

    def setUp(self):
        self.url = reverse('divisas:monitoreo_transacciones')
        self.usuario_a, self.cliente_a = _crear_cliente('Ana', 'Gómez')
        self.usuario_b, self.cliente_b = _crear_cliente('Beto', 'Núñez')

    def test_analista_ve_transacciones_de_todos_los_clientes_y_canales(self):
        _operacion(self.usuario_a, self.cliente_a)
        _cambio(self.usuario_b, self.cliente_b)
        _ventanilla()
        _loguear(self.client, ['analista_cambiario'])
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['totales']['cantidad'], 3)
        contenido = respuesta.content.decode()
        self.assertIn('Gómez', contenido)
        self.assertIn('Núñez', contenido)
        self.assertIn('Cliente Mostrador', contenido)

    def test_administrador_tambien_accede(self):
        _loguear(self.client, ['admin'])
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_listado_paginado(self):
        for _ in range(25):
            _operacion(self.usuario_a, self.cliente_a)
        _loguear(self.client, ['admin'])
        pagina_1 = self.client.get(self.url)
        self.assertEqual(len(pagina_1.context['transacciones']), 20)
        self.assertTrue(pagina_1.context['is_paginated'])
        pagina_2 = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(pagina_2.context['transacciones']), 5)

    def test_cliente_recibe_403(self):
        _loguear(self.client, ['cliente'])
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_cajero_recibe_403(self):
        _loguear(self.client, ['cajero'])
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_sin_roles_recibe_403(self):
        _loguear(self.client, [])
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonimo_es_redirigido_al_login(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 302)

    def test_descarga_y_detalle_tambien_deniegan_a_un_cliente(self):
        operacion = _operacion(self.usuario_a, self.cliente_a)
        _loguear(self.client, ['cliente'])
        self.assertEqual(self.client.get(reverse('divisas:descargar_monitoreo', args=['pdf'])).status_code, 403)
        detalle = reverse('divisas:monitoreo_detalle', kwargs={'tipo': 'operacion', 'pk': operacion.pk})
        self.assertEqual(self.client.get(detalle).status_code, 403)


class FiltrosTest(TestCase):
    """Criterio 2: cada filtro deja solo las transacciones que coinciden."""

    def setUp(self):
        self.usuario_a, self.cliente_a = _crear_cliente('Ana', 'Gómez')
        self.usuario_b, self.cliente_b = _crear_cliente('Beto', 'Núñez')
        self.hoy = timezone.now()
        self.vieja = _operacion(
            self.usuario_a, self.cliente_a, creado_en=self.hoy - timedelta(days=30),
            estado=CalculoOperacion.ESTADO_CANCELADA,
        )
        self.compra_usd = _operacion(self.usuario_a, self.cliente_a, tipo=CalculoOperacion.TIPO_COMPRA, codigo='USD')
        self.venta_brl = _operacion(
            self.usuario_b, self.cliente_b, tipo=CalculoOperacion.TIPO_VENTA, codigo='BRL',
            estado=CalculoOperacion.ESTADO_RETIRADA,
        )
        self.cambio = _cambio(self.usuario_b, self.cliente_b)
        self.mostrador = _ventanilla(codigo='USD')

    def _ids(self, **parametros):
        return {fila['id'] for fila in monitoreo.generar_monitoreo(parametros)['filas']}

    def test_sin_filtros_trae_todo(self):
        self.assertEqual(len(self._ids()), 5)

    def test_rango_de_fechas(self):
        desde = (self.hoy - timedelta(days=1)).strftime('%Y-%m-%d')
        hasta = (self.hoy + timedelta(days=1)).strftime('%Y-%m-%d')
        ids = self._ids(fecha_desde=desde, fecha_hasta=hasta)
        self.assertNotIn(self.vieja.pk, ids)
        self.assertEqual(len(ids), 4)

    def test_solo_fecha_desde(self):
        antes = (self.hoy - timedelta(days=40)).strftime('%Y-%m-%d')
        self.assertEqual(len(self._ids(fecha_desde=antes)), 5)

    def test_cliente_por_nombre_sin_distinguir_mayusculas(self):
        ids = self._ids(cliente='gómez')
        self.assertEqual(ids, {self.vieja.pk, self.compra_usd.pk})

    def test_cliente_por_identificador(self):
        self.assertEqual(self._ids(cliente=self.cliente_b.identificador), {self.venta_brl.pk, self.cambio.pk})

    def test_cliente_de_mostrador_por_documento(self):
        self.assertEqual(self._ids(cliente='4111222'), {self.mostrador.pk})

    def test_tipo_en_perspectiva_de_la_casa(self):
        # El cliente compra USD -> la casa vende; la ventanilla compra -> la casa compra.
        self.assertIn(self.compra_usd.pk, self._ids(tipo=monitoreo.CASA_VENTA))
        self.assertEqual(self._ids(tipo=monitoreo.CAMBIO), {self.cambio.pk})
        self.assertIn(self.mostrador.pk, self._ids(tipo=monitoreo.CASA_COMPRA))

    def test_divisa_coincide_con_origen_o_destino_de_un_cambio(self):
        self.assertIn(self.cambio.pk, self._ids(divisa='EUR'))
        self.assertIn(self.cambio.pk, self._ids(divisa='usd'))
        self.assertEqual(self._ids(divisa='BRL'), {self.venta_brl.pk})

    def test_estado(self):
        self.assertEqual(self._ids(estado=CalculoOperacion.ESTADO_RETIRADA), {self.venta_brl.pk})
        self.assertEqual(self._ids(estado=monitoreo.ESTADO_COMPLETADA), {self.mostrador.pk})

    def test_canal(self):
        self.assertEqual(self._ids(canal=monitoreo.CANAL_VENTANILLA), {self.mostrador.pk})
        self.assertEqual(len(self._ids(canal=monitoreo.CANAL_ONLINE)), 4)

    def test_filtros_combinados(self):
        self.assertEqual(self._ids(cliente='Núñez', divisa='BRL', canal='online'), {self.venta_brl.pk})
        self.assertEqual(self._ids(cliente='Gómez', divisa='BRL'), set())

    def test_rango_con_inicio_posterior_al_fin_es_un_error(self):
        resultado = monitoreo.generar_monitoreo({'fecha_desde': '2026-02-01', 'fecha_hasta': '2026-01-01'})
        self.assertIn('posterior', resultado['error_rango'])
        self.assertEqual(resultado['filas'], [])

    def test_fecha_invalida_es_un_error(self):
        resultado = monitoreo.generar_monitoreo({'fecha_desde': 'no-es-fecha'})
        self.assertIsNotNone(resultado['error_rango'])

    def test_pantalla_aplica_los_filtros_y_muestra_el_error(self):
        _loguear(self.client, ['analista_cambiario'])
        respuesta = self.client.get(reverse('divisas:monitoreo_transacciones'), {'divisa': 'BRL'})
        self.assertEqual(respuesta.context['totales']['cantidad'], 1)
        invalida = self.client.get(
            reverse('divisas:monitoreo_transacciones'), {'fecha_desde': '2026-02-01', 'fecha_hasta': '2026-01-01'},
        )
        self.assertContains(invalida, 'La fecha inicial no puede ser posterior')

    def test_paginacion_conserva_los_filtros(self):
        for _ in range(25):
            _operacion(self.usuario_b, self.cliente_b, codigo='BRL')
        _loguear(self.client, ['admin'])
        respuesta = self.client.get(reverse('divisas:monitoreo_transacciones'), {'divisa': 'BRL'})
        self.assertContains(respuesta, 'divisa=BRL&page=2')


class AtencionTest(TestCase):
    """Criterio 3: entrega pendiente, entrega incierta y pago fuera de plazo se destacan y filtran."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente()
        self.pendiente = _operacion(self.usuario, self.cliente, estado=CalculoOperacion.ESTADO_PAGADA)
        self.incierta = _operacion(self.usuario, self.cliente, estado=CalculoOperacion.ESTADO_ENTREGA_FALLIDA)
        self.fuera_de_plazo = _cambio(self.usuario, self.cliente, estado=CalculoTriangulacion.ESTADO_PAGO_EXPIRADO)
        self.normal = _operacion(self.usuario, self.cliente, estado=CalculoOperacion.ESTADO_ACREDITADA)
        _ventanilla()

    def test_motivos_de_atencion(self):
        filas = {f['id']: f for f in monitoreo.generar_monitoreo({})['filas']}
        self.assertEqual(filas[self.pendiente.pk]['atencion'], 'Entrega pendiente')
        self.assertEqual(filas[self.incierta.pk]['atencion'], 'Entrega incierta')
        self.assertEqual(filas[self.fuera_de_plazo.pk]['atencion'], 'Pago fuera de plazo')
        self.assertEqual(filas[self.normal.pk]['atencion'], '')

    def test_filtro_solo_atencion(self):
        ids = {f['id'] for f in monitoreo.generar_monitoreo({'atencion': '1'})['filas']}
        self.assertEqual(ids, {self.pendiente.pk, self.incierta.pk, self.fuera_de_plazo.pk})

    def test_se_destacan_en_pantalla(self):
        _loguear(self.client, ['admin'])
        respuesta = self.client.get(reverse('divisas:monitoreo_transacciones'))
        self.assertContains(respuesta, 'table-warning', count=3)
        self.assertContains(respuesta, 'Entrega incierta')
        self.assertContains(respuesta, 'Pago fuera de plazo')

    def test_pantalla_con_filtro_de_atencion(self):
        _loguear(self.client, ['admin'])
        respuesta = self.client.get(reverse('divisas:monitoreo_transacciones'), {'atencion': '1'})
        self.assertEqual(respuesta.context['totales']['cantidad'], 3)


class DetalleTest(TestCase):
    """Criterio 4 y 7: detalle con pago, medios y factura, y solo de lectura."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente()
        _loguear(self.client, ['analista_cambiario'])

    def _url(self, tipo, transaccion):
        return reverse('divisas:monitoreo_detalle', kwargs={'tipo': tipo, 'pk': transaccion.pk})

    def test_detalle_con_pago_y_factura(self):
        operacion = _operacion(self.usuario, self.cliente)
        Pago.objects.create(
            calculo_operacion=operacion, medio_pago='TARJETA', proveedor='STRIPE',
            identificador_externo='pi_123', monto=Decimal('747400.00'),
        )
        DocumentoElectronico.objects.create(
            calculo_operacion=operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000123', cdc='CDC-MON-1', estado=DocumentoElectronico.ESTADO_APROBADO,
        )
        respuesta = self.client.get(self._url('operacion', operacion))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['pago'].identificador_externo, 'pi_123')
        self.assertEqual(respuesta.context['medio_origen'], 'Tarjeta de Débito/Crédito')
        self.assertEqual(respuesta.context['factura'].cdc, 'CDC-MON-1')
        self.assertContains(respuesta, 'pi_123')
        self.assertContains(respuesta, 'CDC-MON-1')

    def test_detalle_sin_pago_ni_factura(self):
        operacion = _operacion(self.usuario, self.cliente, estado=CalculoOperacion.ESTADO_CONFIRMADA)
        respuesta = self.client.get(self._url('operacion', operacion))
        self.assertIsNone(respuesta.context['pago'])
        self.assertIsNone(respuesta.context['factura'])
        self.assertContains(respuesta, 'Todavía no tiene un pago registrado')
        self.assertContains(respuesta, 'Todavía no tiene una factura electrónica')

    def test_detalle_de_cambio_con_pago(self):
        cambio = _cambio(self.usuario, self.cliente)
        Pago.objects.create(
            calculo_triangulacion=cambio, medio_pago='TRANSFERENCIA', proveedor='SIPAP',
            identificador_externo='sipap-9', monto=Decimal('730000.00'),
        )
        respuesta = self.client.get(self._url('cambio', cambio))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['pago'].proveedor, 'SIPAP')

    def test_detalle_de_ventanilla_es_en_efectivo(self):
        operacion = _ventanilla()
        DocumentoElectronico.objects.create(
            operacion_ventanilla=operacion, tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA,
            numero_documento='0000124',
        )
        respuesta = self.client.get(self._url('ventanilla', operacion))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['medio_origen'], 'Efectivo en ventanilla')
        self.assertIsNone(respuesta.context['pago'])
        self.assertEqual(respuesta.context['factura'].numero_documento, '0000124')

    def test_transaccion_inexistente_es_404(self):
        import uuid
        url = reverse('divisas:monitoreo_detalle', kwargs={'tipo': 'operacion', 'pk': uuid.uuid4()})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_tipo_desconocido_es_404(self):
        import uuid
        url = reverse('divisas:monitoreo_detalle', kwargs={'tipo': 'otro', 'pk': uuid.uuid4()})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_no_se_puede_modificar_el_estado_desde_el_monitoreo(self):
        operacion = _operacion(self.usuario, self.cliente, estado=CalculoOperacion.ESTADO_ENTREGA_FALLIDA)
        for url in (self._url('operacion', operacion), reverse('divisas:monitoreo_transacciones')):
            respuesta = self.client.post(url, {'estado': CalculoOperacion.ESTADO_ACREDITADA})
            self.assertEqual(respuesta.status_code, 405)
        operacion.refresh_from_db()
        self.assertEqual(operacion.estado, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)

    def test_pantallas_sin_formularios_ni_acciones_de_cambio_de_estado(self):
        operacion = _operacion(self.usuario, self.cliente, estado=CalculoOperacion.ESTADO_ENTREGA_FALLIDA)
        for url in (self._url('operacion', operacion), reverse('divisas:monitoreo_transacciones')):
            contenido = self.client.get(url).content.decode()
            # El único formulario POST de la página es el de cerrar sesión del menú lateral.
            self.assertEqual(contenido.lower().count('method="post"'), 1)
            self.assertIn('/oidc/logout/', contenido)
            self.assertNotIn('Reintentar', contenido)


class TotalesYDescargasTest(TestCase):
    """Criterio 5: PDF y Excel con el listado filtrado y totales por tipo, divisa y estado."""

    def setUp(self):
        self.usuario, self.cliente = _crear_cliente()
        _operacion(self.usuario, self.cliente, tipo=CalculoOperacion.TIPO_COMPRA, codigo='USD')
        _operacion(self.usuario, self.cliente, tipo=CalculoOperacion.TIPO_COMPRA, codigo='USD',
                   estado=CalculoOperacion.ESTADO_CANCELADA)
        _operacion(self.usuario, self.cliente, tipo=CalculoOperacion.TIPO_VENTA, codigo='BRL')
        _cambio(self.usuario, self.cliente)
        _ventanilla()
        _loguear(self.client, ['analista_cambiario'])

    def test_totales_por_tipo_divisa_y_estado(self):
        totales = monitoreo.generar_monitoreo({})['totales']
        self.assertEqual(totales['cantidad'], 5)
        # Compras del cliente (x2) = ventas de la casa; venta del cliente y compra en ventanilla = compras de la casa.
        self.assertEqual(totales['por_tipo'][monitoreo.CASA_VENTA]['cantidad'], 2)
        self.assertEqual(totales['por_tipo'][monitoreo.CASA_COMPRA]['cantidad'], 2)
        self.assertEqual(totales['por_tipo'][monitoreo.CAMBIO]['cantidad'], 1)
        self.assertEqual(totales['por_divisa']['USD']['cantidad'], 3)  # 2 online + 1 ventanilla
        self.assertEqual(totales['por_divisa']['USD']['monto'], Decimal('250.00'))
        self.assertEqual(totales['por_divisa']['USD → EUR']['cantidad'], 1)
        self.assertEqual(totales['por_estado'][CalculoOperacion.ESTADO_CANCELADA]['cantidad'], 1)
        self.assertEqual(totales['por_estado'][CalculoOperacion.ESTADO_ACREDITADA]['cantidad'], 3)
        self.assertEqual(totales['por_estado'][monitoreo.ESTADO_COMPLETADA]['cantidad'], 1)

    def test_totales_de_un_listado_vacio(self):
        totales = monitoreo.generar_monitoreo({'divisa': 'JPY'})['totales']
        self.assertEqual(totales['cantidad'], 0)
        self.assertEqual(totales['por_divisa'], {})
        self.assertEqual(totales['por_tipo'][monitoreo.CAMBIO]['cantidad'], 0)

    def test_pdf_filtrado(self):
        respuesta = self.client.get(reverse('divisas:descargar_monitoreo', args=['pdf']), {'divisa': 'BRL'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF'))
        self.assertIn('attachment', respuesta['Content-Disposition'])

    def test_excel_filtrado_con_sus_totales(self):
        respuesta = self.client.get(reverse('divisas:descargar_monitoreo', args=['excel']), {'divisa': 'BRL'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('spreadsheetml', respuesta['Content-Type'])
        hoja = load_workbook(BytesIO(respuesta.content)).active
        celdas = [fila[0] for fila in hoja.iter_rows(values_only=True)]
        self.assertIn('Divisa: BRL', hoja['A2'].value)
        self.assertIn('Totales por tipo de operación', celdas)
        self.assertIn('Totales por divisa', celdas)
        self.assertIn('Totales por estado', celdas)
        filas_datos = [f for f in hoja.iter_rows(min_row=6, values_only=True) if f[4] == 'BRL']
        self.assertEqual(len(filas_datos), 1)
        self.assertEqual(sum(1 for f in hoja.iter_rows(min_row=6, values_only=True) if f[4] == 'USD'), 0)

    def test_excel_contiene_el_listado_completo_sin_filtros(self):
        respuesta = self.client.get(reverse('divisas:descargar_monitoreo', args=['excel']))
        hoja = load_workbook(BytesIO(respuesta.content)).active
        self.assertEqual(hoja['A2'].value, 'Sin filtros (todas las transacciones)')
        datos = [f for f in hoja.iter_rows(min_row=6, max_row=10, values_only=True) if f[0]]
        self.assertEqual(len(datos), 5)

    def test_descarga_sin_resultados_vuelve_a_la_pantalla(self):
        respuesta = self.client.get(reverse('divisas:descargar_monitoreo', args=['pdf']), {'divisa': 'JPY'})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('divisas:monitoreo_transacciones'), respuesta['Location'])

    def test_descarga_con_rango_invalido_vuelve_a_la_pantalla(self):
        respuesta = self.client.get(
            reverse('divisas:descargar_monitoreo', args=['excel']),
            {'fecha_desde': '2026-02-01', 'fecha_hasta': '2026-01-01'},
        )
        self.assertEqual(respuesta.status_code, 302)

    def test_formato_desconocido_es_404(self):
        self.assertEqual(self.client.get(reverse('divisas:descargar_monitoreo', args=['csv'])).status_code, 404)

    def test_pantalla_ofrece_las_descargas_con_los_filtros(self):
        respuesta = self.client.get(reverse('divisas:monitoreo_transacciones'), {'divisa': 'BRL'})
        self.assertContains(respuesta, '/descargar/pdf/?divisa=BRL')
        self.assertContains(respuesta, '/descargar/excel/?divisa=BRL')
