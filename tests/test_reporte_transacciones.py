"""Pruebas de la HU 'Reporte de transacciones del cliente' (GE-39)."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.clientes.models import Cliente
from apps.divisas import reportes
from apps.divisas.models import CalculoOperacion, CalculoTriangulacion, Cotizacion, Divisa
from tests.utils_formato import formato

User = get_user_model()


def _crear_cliente(username, identificador, nombre='Cliente', apellido='Test'):
    """Crea un usuario con un cliente asociado (vía la M2M ``usuarios``), sin loguearlo."""
    usuario = User.objects.create_user(username=username, password='password123')
    cliente = Cliente.objects.create(
        identificador=identificador, nombre=nombre, apellido=apellido,
        email=f'{username}@test.com', is_active=True,
    )
    cliente.usuarios.add(usuario)
    return usuario, cliente


def _crear_cliente_logueado(client, username, identificador, apellido='Test', roles=('cliente',)):
    """Crea un usuario con un cliente asociado, lo loguea y fija sus roles de Keycloak."""
    usuario, cliente = _crear_cliente(username, identificador, apellido=apellido)
    client.login(username=username, password='password123')
    session = client.session
    session['keycloak_roles'] = list(roles)
    session.save()
    return usuario, cliente


def _crear_usd_cotizado():
    """Crea la divisa USD activa con una cotización vigente."""
    usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
    Cotizacion.objects.create(divisa=usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
    return usd


def _crear_eur():
    return Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)


class CalcularTotalesTest(TestCase):
    """Unidad: ``apps.divisas.reportes.calcular_totales`` (criterio 2)."""

    def setUp(self):
        """Prepara un cliente, USD/EUR y una base de filas reutilizable por los tests."""
        self.usuario, self.cliente = _crear_cliente('cliente-totales', 'TOT-001')
        self.usd = _crear_usd_cotizado()
        self.eur = _crear_eur()

    def _operacion(self, tipo, estado, monto_final=Decimal('747400.00')):
        return CalculoOperacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, tipo=tipo, divisa=self.usd, codigo_divisa='USD',
            monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_final=monto_final,
            estado=estado, vence_en=timezone.now() + timedelta(seconds=300),
        )

    def _cambio(self, estado):
        return CalculoTriangulacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, divisa_origen=self.usd, divisa_destino=self.eur,
            codigo_divisa_origen='USD', codigo_divisa_destino='EUR', monto_origen=Decimal('100.00'),
            tasa_compra_aplicada=Decimal('7300.00'), tasa_venta_aplicada=Decimal('8100.00'),
            tasa_cruzada=Decimal('0.901235'), monto_equivalente_pyg=Decimal('730000.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('0.90'), monto_final=Decimal('89.22'),
            estado=estado, vence_en=timezone.now() + timedelta(seconds=300),
        )

    def test_solo_cuenta_transacciones_completadas(self):
        """Una pendiente o cancelada no aporta ni a la cantidad ni al monto de ningún total."""
        self._operacion(CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_PENDIENTE)
        self._operacion(CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_CANCELADA)
        acreditada = self._operacion(CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA)

        filas = reportes._transacciones_cliente(self.cliente)
        totales = reportes.calcular_totales(filas)

        self.assertEqual(totales['cantidad_completadas'], 1)
        self.assertEqual(totales['por_tipo'][reportes.TIPO_COMPRA]['cantidad'], 1)
        self.assertEqual(totales['por_tipo'][reportes.TIPO_COMPRA]['monto_pyg'], acreditada.monto_final)

    def test_retirada_tambien_cuenta_como_completada(self):
        """ESTADO_RETIRADA (venta con entrega en efectivo) es tan 'completada' como ACREDITADA."""
        self._operacion(CalculoOperacion.TIPO_VENTA, CalculoOperacion.ESTADO_RETIRADA)

        totales = reportes.calcular_totales(reportes._transacciones_cliente(self.cliente))

        self.assertEqual(totales['cantidad_completadas'], 1)
        self.assertEqual(totales['por_tipo'][reportes.TIPO_VENTA]['cantidad'], 1)

    def test_totales_por_tipo_separan_compra_venta_y_cambio_en_pyg(self):
        """El total por tipo usa el equivalente en PYG, común entre compra/venta y cambio."""
        self._operacion(CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA, monto_final=Decimal('100000.00'))
        self._operacion(CalculoOperacion.TIPO_VENTA, CalculoOperacion.ESTADO_ACREDITADA, monto_final=Decimal('200000.00'))
        self._cambio(CalculoTriangulacion.ESTADO_ACREDITADA)

        totales = reportes.calcular_totales(reportes._transacciones_cliente(self.cliente))

        self.assertEqual(totales['por_tipo'][reportes.TIPO_COMPRA]['monto_pyg'], Decimal('100000.00'))
        self.assertEqual(totales['por_tipo'][reportes.TIPO_VENTA]['monto_pyg'], Decimal('200000.00'))
        self.assertEqual(totales['por_tipo'][reportes.TIPO_CAMBIO]['monto_pyg'], Decimal('730000.00'))

    def test_totales_por_divisa_agrupan_por_codigo_de_divisa(self):
        """Dos compras en USD se agrupan en una sola entrada 'por divisa'."""
        self._operacion(CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA)
        self._operacion(CalculoOperacion.TIPO_COMPRA, CalculoOperacion.ESTADO_ACREDITADA)

        totales = reportes.calcular_totales(reportes._transacciones_cliente(self.cliente))

        self.assertEqual(totales['por_divisa']['USD']['cantidad'], 2)
        self.assertEqual(totales['por_divisa']['USD']['monto'], Decimal('200.00'))


class GenerarReporteTest(TestCase):
    """Unidad: ``apps.divisas.reportes.generar_reporte`` (criterios 1 y 5)."""

    def setUp(self):
        """Prepara un cliente con una transacción confirmada hoy."""
        self.usuario, self.cliente = _crear_cliente('cliente-generar', 'GEN-001')
        self.usd = _crear_usd_cotizado()
        self.operacion = CalculoOperacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA, divisa=self.usd,
            codigo_divisa='USD', monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_ACREDITADA, vence_en=timezone.now() + timedelta(seconds=300),
        )

    def test_sin_rango_no_genera_nada_y_no_es_un_error(self):
        """Sin fecha_desde/fecha_hasta, el reporte no se genera, pero tampoco hay error de validación."""
        resultado = reportes.generar_reporte(self.cliente, {})

        self.assertFalse(resultado['reporte_generado'])
        self.assertIsNone(resultado['error_rango'])
        self.assertEqual(resultado['filas'], [])

    def test_rango_invalido_informa_el_error_sin_listar_nada(self):
        """Criterio 5: fecha inicial posterior a la final es un rango inválido."""
        hoy = timezone.localdate().isoformat()
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()

        resultado = reportes.generar_reporte(self.cliente, {'fecha_desde': hoy, 'fecha_hasta': ayer})

        self.assertFalse(resultado['reporte_generado'])
        self.assertIsNotNone(resultado['error_rango'])
        self.assertEqual(resultado['filas'], [])

    def test_rango_con_fechas_futuras_es_invalido(self):
        """Criterio 5: ninguna de las dos fechas puede estar en el futuro."""
        mañana = (timezone.localdate() + timedelta(days=1)).isoformat()

        resultado = reportes.generar_reporte(self.cliente, {'fecha_desde': mañana, 'fecha_hasta': mañana})

        self.assertFalse(resultado['reporte_generado'])
        self.assertIsNotNone(resultado['error_rango'])

    def test_rango_valido_sin_coincidencias_genera_reporte_vacio(self):
        """Criterio 4: un rango válido sin transacciones genera el reporte, pero sin filas."""
        hace_un_mes = (timezone.localdate() - timedelta(days=60)).isoformat()
        hace_dos_semanas = (timezone.localdate() - timedelta(days=45)).isoformat()

        resultado = reportes.generar_reporte(
            self.cliente, {'fecha_desde': hace_un_mes, 'fecha_hasta': hace_dos_semanas}
        )

        self.assertTrue(resultado['reporte_generado'])
        self.assertEqual(resultado['filas'], [])

    def test_filtro_por_tipo_de_operacion(self):
        """Criterio 1: el tipo de operación filtra entre compra/venta/cambio."""
        hoy = timezone.localdate().isoformat()

        resultado = reportes.generar_reporte(
            self.cliente, {'fecha_desde': hoy, 'fecha_hasta': hoy, 'tipo': reportes.TIPO_VENTA}
        )

        self.assertTrue(resultado['reporte_generado'])
        self.assertEqual(resultado['filas'], [])

    def test_filtro_por_estado(self):
        """Criterio 1: el estado también filtra el listado."""
        hoy = timezone.localdate().isoformat()

        resultado = reportes.generar_reporte(
            self.cliente, {'fecha_desde': hoy, 'fecha_hasta': hoy, 'estado': CalculoOperacion.ESTADO_CANCELADA}
        )

        self.assertEqual(resultado['filas'], [])

        resultado_correcto = reportes.generar_reporte(
            self.cliente, {'fecha_desde': hoy, 'fecha_hasta': hoy, 'estado': CalculoOperacion.ESTADO_ACREDITADA}
        )
        self.assertEqual(len(resultado_correcto['filas']), 1)


class ReporteTransaccionesClienteViewTest(TestCase):
    """Pantalla del reporte: ``ReporteTransaccionesClienteView`` (criterios 1, 2, 4, 5 y 6)."""

    def setUp(self):
        """Prepara un cliente activo logueado con una transacción completada hoy."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-reporte', 'REP-001')
        self.usd = _crear_usd_cotizado()
        self.operacion = CalculoOperacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA, divisa=self.usd,
            codigo_divisa='USD', monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_ACREDITADA, vence_en=timezone.now() + timedelta(seconds=300),
        )
        self.url = reverse('divisas:reporte_transacciones', kwargs={'cliente_pk': self.cliente.pk})

    def test_sin_filtros_muestra_solo_el_formulario(self):
        """Sin rango de fechas, se ve la pantalla con el formulario, sin error ni tabla."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['reporte_generado'])
        self.assertIsNone(response.context['error_rango'])

    def test_rango_valido_muestra_listado_y_totales(self):
        """Criterios 1 y 2: con un rango válido se ve la transacción y sus totales."""
        hoy = timezone.localdate().isoformat()

        response = self.client.get(self.url, {'fecha_desde': hoy, 'fecha_hasta': hoy})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['reporte_generado'])
        self.assertEqual(len(response.context['filas']), 1)
        self.assertContains(response, 'Compra')
        self.assertContains(response, formato(self.operacion.monto_origen))
        self.assertContains(response, 'Descargar PDF')
        self.assertContains(response, 'Descargar Excel')

    def test_rango_invalido_muestra_error_de_validacion(self):
        """Criterio 5: un rango invertido se informa como error, sin listar nada."""
        hoy = timezone.localdate().isoformat()
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()

        response = self.client.get(self.url, {'fecha_desde': hoy, 'fecha_hasta': ayer})

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['error_rango'])
        self.assertNotContains(response, 'Descargar PDF')

    def test_sin_resultados_no_ofrece_descarga(self):
        """Criterio 4: un rango sin transacciones avisa que no hay datos y no ofrece ninguna descarga."""
        hace_un_mes = (timezone.localdate() - timedelta(days=60)).isoformat()
        hace_dos_semanas = (timezone.localdate() - timedelta(days=45)).isoformat()

        response = self.client.get(self.url, {'fecha_desde': hace_un_mes, 'fecha_hasta': hace_dos_semanas})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['filas'], [])
        self.assertNotContains(response, 'Descargar PDF')
        self.assertNotContains(response, 'Descargar Excel')

    def test_cliente_no_asociado_al_usuario_deniega_el_acceso(self):
        """Criterio 6: pedir el reporte de un cliente ajeno devuelve 403, aunque exista."""
        _, otro_cliente = _crear_cliente('otro-cliente-reporte', 'REP-002')

        url_ajena = reverse('divisas:reporte_transacciones', kwargs={'cliente_pk': otro_cliente.pk})
        response = self.client.get(url_ajena)

        self.assertEqual(response.status_code, 403)

    def test_cliente_inexistente_da_404(self):
        """Un ``cliente_pk`` que no corresponde a ningún cliente da 404, no 403."""
        url_inexistente = reverse('divisas:reporte_transacciones', kwargs={'cliente_pk': 999999})

        response = self.client.get(url_inexistente)

        self.assertEqual(response.status_code, 404)

    def test_un_administrador_no_puede_acceder(self):
        """La pantalla es exclusiva de clientes: un administrador no la ve, aunque conozca la URL."""
        admin = User.objects.create_user(username='admin-reporte', password='password123', is_staff=True)
        self.client.login(username='admin-reporte', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)


class DescargarReporteTransaccionesViewTest(TestCase):
    """Descargas PDF/Excel: ``DescargarReporteTransaccionesView`` (criterios 3, 4, 5 y 6)."""

    def setUp(self):
        """Prepara un cliente activo logueado con una transacción completada hoy."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-descarga', 'DESC-001')
        self.usd = _crear_usd_cotizado()
        self.operacion = CalculoOperacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA, divisa=self.usd,
            codigo_divisa='USD', monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_ACREDITADA, vence_en=timezone.now() + timedelta(seconds=300),
        )
        self.hoy = timezone.localdate().isoformat()

    def _url(self, formato_):
        return reverse(
            'divisas:descargar_reporte_transacciones',
            kwargs={'cliente_pk': self.cliente.pk, 'formato': formato_},
        )

    def test_descarga_pdf_con_filtros_validos(self):
        """Criterio 3: con filtros válidos y datos, el PDF se descarga como adjunto."""
        response = self.client.get(self._url('pdf'), {'fecha_desde': self.hoy, 'fecha_hasta': self.hoy})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_descarga_excel_con_filtros_validos_y_mismos_datos_que_el_pdf(self):
        """Criterio 3: el Excel tiene los mismos datos, filtros y fecha de generación."""
        response = self.client.get(self._url('excel'), {'fecha_desde': self.hoy, 'fecha_hasta': self.hoy})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        libro = load_workbook(BytesIO(response.content))
        hoja = libro.active
        contenido = '\n'.join(
            ' '.join(str(celda) for celda in fila if celda is not None) for fila in hoja.iter_rows(values_only=True)
        )
        self.assertIn('Generado el', contenido)
        self.assertIn(f'Del {timezone.localdate():%d/%m/%Y}', contenido)
        valores_fila_datos = [celda.value for celda in hoja[6]]
        self.assertIn(100, valores_fila_datos)

    def test_sin_resultados_no_descarga_nada(self):
        """Criterio 4: sin transacciones en el rango, no se genera ningún archivo."""
        hace_un_mes = (timezone.localdate() - timedelta(days=60)).isoformat()
        hace_dos_semanas = (timezone.localdate() - timedelta(days=45)).isoformat()

        response = self.client.get(
            self._url('pdf'), {'fecha_desde': hace_un_mes, 'fecha_hasta': hace_dos_semanas}
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.get('Content-Type'), 'application/pdf')

    def test_rango_invalido_no_descarga_nada(self):
        """Criterio 5: un rango inválido redirige con el error, sin generar ningún archivo."""
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()

        response = self.client.get(self._url('pdf'), {'fecha_desde': self.hoy, 'fecha_hasta': ayer})

        self.assertEqual(response.status_code, 302)

    def test_sin_rango_no_descarga_nada(self):
        """Sin fecha_desde/fecha_hasta, tampoco se genera ningún archivo."""
        response = self.client.get(self._url('pdf'))

        self.assertEqual(response.status_code, 302)

    def test_cliente_no_asociado_al_usuario_deniega_el_acceso(self):
        """Criterio 6: descargar el reporte de un cliente ajeno devuelve 403."""
        _, otro_cliente = _crear_cliente('otro-cliente-descarga', 'DESC-002')
        url_ajena = reverse(
            'divisas:descargar_reporte_transacciones',
            kwargs={'cliente_pk': otro_cliente.pk, 'formato': 'pdf'},
        )

        response = self.client.get(url_ajena, {'fecha_desde': self.hoy, 'fecha_hasta': self.hoy})

        self.assertEqual(response.status_code, 403)

    def test_formato_desconocido_da_404(self):
        """Un formato que no es 'pdf' ni 'excel' da 404."""
        url_invalida = reverse(
            'divisas:descargar_reporte_transacciones',
            kwargs={'cliente_pk': self.cliente.pk, 'formato': 'csv'},
        )

        response = self.client.get(url_invalida, {'fecha_desde': self.hoy, 'fecha_hasta': self.hoy})

        self.assertEqual(response.status_code, 404)
