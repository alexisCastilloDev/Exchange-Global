"""Pruebas de la HU 'Notificaciones sobre transacciones y facturas'."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente, MetodoPago
from apps.divisas.factura_electronica import consultar_estado_sifen
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    ContadorDocumentoElectronico,
    Cotizacion,
    Divisa,
    DocumentoElectronico,
    NotificacionCliente,
    NotificacionTasa,
    Pago,
)

User = get_user_model()

_SIGUIENTE_IDENTIFICADOR = [1]


def _crear_cliente(*usuarios, nombre='Cliente'):
    """Crea un cliente activo y le asocia los usuarios dados (los que pueden tenerlo como cliente activo)."""
    _SIGUIENTE_IDENTIFICADOR[0] += 1
    cliente = Cliente.objects.create(
        identificador=f'NOT-{_SIGUIENTE_IDENTIFICADOR[0]:06d}', nombre=nombre, apellido='Notificado',
        email=f'cliente{_SIGUIENTE_IDENTIFICADOR[0]}@test.com', is_active=True,
    )
    cliente.usuarios.add(*usuarios)
    return cliente


def _crear_divisas():
    usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
    eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
    return usd, eur


def _operacion(usuario, cliente, divisa, estado=CalculoOperacion.ESTADO_CONFIRMADA, **extra):
    return CalculoOperacion.objects.create(
        usuario=usuario, cliente=cliente, tipo=CalculoOperacion.TIPO_COMPRA, divisa=divisa,
        codigo_divisa=divisa.codigo, monto_origen=Decimal('100.00'), tasa_aplicada=Decimal('7400.00'),
        comision_porcentaje=Decimal('1.000'), comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
        estado=estado, vence_en=timezone.now() + timedelta(seconds=300), **extra,
    )


def _cambio(usuario, cliente, origen, destino, estado=CalculoTriangulacion.ESTADO_CONFIRMADA):
    return CalculoTriangulacion.objects.create(
        usuario=usuario, cliente=cliente, divisa_origen=origen, divisa_destino=destino,
        codigo_divisa_origen=origen.codigo, codigo_divisa_destino=destino.codigo,
        monto_origen=Decimal('100.00'), tasa_compra_aplicada=Decimal('7300.00'),
        tasa_venta_aplicada=Decimal('10.00'), tasa_cruzada=Decimal('730.000000'),
        monto_equivalente_pyg=Decimal('730000.00'), comision_porcentaje=Decimal('1.000'),
        comision=Decimal('0.90'), monto_final=Decimal('89.10'), estado=estado,
        vence_en=timezone.now() + timedelta(seconds=300),
    )


def _factura(transaccion, estado=DocumentoElectronico.ESTADO_GENERADO, cdc='01800000000000000000000000000000000000000001'):
    campo = 'calculo_operacion' if isinstance(transaccion, CalculoOperacion) else 'calculo_triangulacion'
    return DocumentoElectronico.objects.create(
        tipo_documento=ContadorDocumentoElectronico.TIPO_FACTURA, numero_documento='0000900',
        estado=estado, cdc=cdc, **{campo: transaccion},
    )


def _cambiar_estado(objeto, estado):
    """Cambia el estado como lo hace el sistema: con ``save(update_fields=['estado'])``."""
    objeto.estado = estado
    objeto.save(update_fields=['estado'])
    return objeto


def _respuesta_sifen(estado_sifen, **resultados):
    """Respuesta falsa de ``get_estado_sifen`` de Factura Segura, con el sobre ``code``/``results``."""
    respuesta = Mock(status_code=200)
    respuesta.raise_for_status.side_effect = None
    respuesta.json.return_value = {
        'code': 0, 'description': '', 'operation_info': {'id': 'OP-1'},
        'results': [{'estado_sifen': estado_sifen, 'desc_sifen': estado_sifen, **resultados}],
    }
    return respuesta


class NotificacionesTransaccionTest(TestCase):
    """Criterio 1: un cambio de estado guardado notifica el número de la transacción y su nuevo estado."""

    def setUp(self):
        self.usuario = User.objects.create_user(username='cliente-notif', password='password123')
        self.cliente = _crear_cliente(self.usuario)
        self.usd, self.eur = _crear_divisas()

    def test_pasar_a_pagada_notifica_numero_y_estado(self):
        operacion = _operacion(self.usuario, self.cliente, self.usd)

        _cambiar_estado(operacion, CalculoOperacion.ESTADO_PAGADA)

        notificacion = NotificacionCliente.objects.get()
        self.assertEqual(notificacion.usuario, self.usuario)
        self.assertEqual(notificacion.cliente, self.cliente)
        self.assertEqual(notificacion.tipo, NotificacionCliente.TIPO_TRANSACCION)
        self.assertEqual(notificacion.referencia, str(operacion.pk))
        self.assertEqual(notificacion.estado, CalculoOperacion.ESTADO_PAGADA)
        self.assertEqual(notificacion.estado_display, 'Pagada')
        self.assertEqual(notificacion.categoria, NotificacionCliente.CATEGORIA_PAGADA)
        self.assertIn(str(operacion.pk), notificacion.mensaje)
        self.assertIn('Pagada', notificacion.mensaje)
        self.assertFalse(notificacion.leida)

    def test_estados_notificables_y_su_categoria(self):
        casos = [
            (CalculoOperacion.ESTADO_ACREDITADA, NotificacionCliente.CATEGORIA_COMPLETADA),
            (CalculoOperacion.ESTADO_RETIRADA, NotificacionCliente.CATEGORIA_COMPLETADA),
            (CalculoOperacion.ESTADO_CANCELADA, NotificacionCliente.CATEGORIA_CANCELADA),
            (CalculoOperacion.ESTADO_CANCELADA_COTIZACION, NotificacionCliente.CATEGORIA_CANCELADA),
            (CalculoOperacion.ESTADO_CANCELADA_SALDO_INSUFICIENTE, NotificacionCliente.CATEGORIA_CANCELADA),
            (CalculoOperacion.ESTADO_CANCELADA_FONDOS_CLIENTE, NotificacionCliente.CATEGORIA_CANCELADA),
            (CalculoOperacion.ESTADO_ENTREGA_FALLIDA, NotificacionCliente.CATEGORIA_ATENCION),
            (CalculoOperacion.ESTADO_PAGO_EXPIRADO, NotificacionCliente.CATEGORIA_ATENCION),
        ]
        for estado, categoria in casos:
            with self.subTest(estado=estado):
                operacion = _operacion(self.usuario, self.cliente, self.usd)

                _cambiar_estado(operacion, estado)

                notificacion = NotificacionCliente.objects.get(calculo_operacion=operacion)
                self.assertEqual(notificacion.estado, estado)
                self.assertEqual(notificacion.categoria, categoria)

    def test_estados_que_no_se_notifican(self):
        for estado in (
            CalculoOperacion.ESTADO_CONFIRMADA,
            CalculoOperacion.ESTADO_VENCIDA,
        ):
            with self.subTest(estado=estado):
                operacion = _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PENDIENTE)

                _cambiar_estado(operacion, estado)

                self.assertFalse(NotificacionCliente.objects.filter(calculo_operacion=operacion).exists())

    def test_crear_una_transaccion_no_notifica(self):
        """Crear el registro no es un cambio de estado, aunque ya nazca en un estado notificable."""
        _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)

        self.assertFalse(NotificacionCliente.objects.exists())

    def test_guardar_sin_cambiar_el_estado_no_notifica(self):
        operacion = _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)
        operacion = CalculoOperacion.objects.get(pk=operacion.pk)

        operacion.save()
        operacion.save(update_fields=['estado'])

        self.assertFalse(NotificacionCliente.objects.exists())

    def test_guardar_otros_campos_no_notifica_aunque_el_estado_en_memoria_cambie(self):
        """Con ``update_fields`` sin ``estado`` no se persiste ningún estado nuevo."""
        operacion = _operacion(self.usuario, self.cliente, self.usd)
        operacion.estado = CalculoOperacion.ESTADO_PAGADA
        operacion.confirmado_en = timezone.now()

        operacion.save(update_fields=['confirmado_en'])

        self.assertFalse(NotificacionCliente.objects.exists())

    def test_cambio_desde_una_instancia_leida_de_la_base(self):
        operacion = _operacion(self.usuario, self.cliente, self.usd)
        leida = CalculoOperacion.objects.get(pk=operacion.pk)

        _cambiar_estado(leida, CalculoOperacion.ESTADO_CANCELADA)

        self.assertEqual(NotificacionCliente.objects.get().estado, CalculoOperacion.ESTADO_CANCELADA)

    def test_cada_cambio_sucesivo_genera_su_propia_notificacion(self):
        operacion = _operacion(self.usuario, self.cliente, self.usd)

        _cambiar_estado(operacion, CalculoOperacion.ESTADO_PAGADA)
        _cambiar_estado(operacion, CalculoOperacion.ESTADO_ENTREGA_FALLIDA)
        _cambiar_estado(operacion, CalculoOperacion.ESTADO_ACREDITADA)

        estados = list(
            NotificacionCliente.objects.filter(calculo_operacion=operacion)
            .order_by('pk').values_list('estado', flat=True)
        )
        self.assertEqual(estados, [
            CalculoOperacion.ESTADO_PAGADA,
            CalculoOperacion.ESTADO_ENTREGA_FALLIDA,
            CalculoOperacion.ESTADO_ACREDITADA,
        ])

    def test_un_cambio_entre_divisas_tambien_notifica(self):
        cambio = _cambio(self.usuario, self.cliente, self.usd, self.eur)

        _cambiar_estado(cambio, CalculoTriangulacion.ESTADO_ACREDITADA)

        notificacion = NotificacionCliente.objects.get()
        self.assertEqual(notificacion.calculo_triangulacion, cambio)
        self.assertEqual(notificacion.referencia, str(cambio.pk))
        self.assertEqual(notificacion.categoria, NotificacionCliente.CATEGORIA_COMPLETADA)

    def test_notifica_a_cada_usuario_asociado_al_cliente_y_a_nadie_mas(self):
        otro_usuario = User.objects.create_user(username='cliente-notif-2', password='password123')
        inactivo = User.objects.create_user(username='cliente-notif-inactivo', password='password123', is_active=False)
        ajeno = User.objects.create_user(username='ajeno', password='password123')
        self.cliente.usuarios.add(otro_usuario, inactivo)
        _crear_cliente(ajeno, nombre='Ajeno')
        operacion = _operacion(self.usuario, self.cliente, self.usd)

        _cambiar_estado(operacion, CalculoOperacion.ESTADO_PAGADA)

        destinatarios = set(NotificacionCliente.objects.values_list('usuario__username', flat=True))
        self.assertEqual(destinatarios, {'cliente-notif', 'cliente-notif-2'})

    def test_un_pago_registrado_por_el_flujo_real_notifica(self):
        """Integración con ``Pago.registrar_pago``: la transacción pasa a "Pagada" y se notifica."""
        operacion = _operacion(
            self.usuario, self.cliente, self.usd, confirmado_en=timezone.now(),
            tasa_vence_en=timezone.now() + timedelta(minutes=10),
        )

        Pago.registrar_pago(
            operacion, MetodoPago.TIPO_TARJETA, Pago.PROVEEDOR_MANUAL, 'pago-notif-1', operacion.monto_final,
        )

        notificacion = NotificacionCliente.objects.get()
        self.assertEqual(notificacion.estado, CalculoOperacion.ESTADO_PAGADA)
        self.assertEqual(notificacion.referencia, str(operacion.pk))


class NotificacionesFacturaTest(TestCase):
    """Criterio 2: aprobación, rechazo o cancelación por SIFEN notifica el CDC y el nuevo estado."""

    def setUp(self):
        self.usuario = User.objects.create_user(username='cliente-factura', password='password123')
        self.cliente = _crear_cliente(self.usuario)
        self.usd, self.eur = _crear_divisas()
        self.operacion = _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)

    def test_aprobada_notifica_cdc_y_estado(self):
        factura = _factura(self.operacion)

        _cambiar_estado(factura, DocumentoElectronico.ESTADO_APROBADO)

        notificacion = NotificacionCliente.objects.get()
        self.assertEqual(notificacion.tipo, NotificacionCliente.TIPO_FACTURA)
        self.assertEqual(notificacion.documento_electronico, factura)
        self.assertEqual(notificacion.calculo_operacion, self.operacion)
        self.assertEqual(notificacion.referencia, factura.cdc)
        self.assertEqual(notificacion.estado_display, 'Aprobado')
        self.assertEqual(notificacion.categoria, NotificacionCliente.CATEGORIA_APROBADA)
        self.assertIn(factura.cdc, notificacion.mensaje)

    def test_aprobada_con_observacion_rechazada_y_anulada_notifican(self):
        casos = [
            (DocumentoElectronico.ESTADO_APROBADO_OBS, NotificacionCliente.CATEGORIA_APROBADA),
            (DocumentoElectronico.ESTADO_RECHAZADO, NotificacionCliente.CATEGORIA_RECHAZADA),
            (DocumentoElectronico.ESTADO_ANULADA, NotificacionCliente.CATEGORIA_ANULADA),
        ]
        for estado, categoria in casos:
            with self.subTest(estado=estado):
                operacion = _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)
                factura = _factura(operacion)

                _cambiar_estado(factura, estado)

                notificacion = NotificacionCliente.objects.get(documento_electronico=factura)
                self.assertEqual(notificacion.categoria, categoria)

    def test_estados_tecnicos_no_notifican(self):
        for estado in (DocumentoElectronico.ESTADO_ERROR_SIFEN, DocumentoElectronico.ESTADO_ERROR_GENERACION):
            with self.subTest(estado=estado):
                operacion = _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)
                factura = _factura(operacion)

                _cambiar_estado(factura, estado)

                self.assertFalse(NotificacionCliente.objects.filter(documento_electronico=factura).exists())

    def test_factura_de_un_cambio_entre_divisas(self):
        cambio = _cambio(self.usuario, self.cliente, self.usd, self.eur, estado=CalculoTriangulacion.ESTADO_PAGADA)
        factura = _factura(cambio)

        _cambiar_estado(factura, DocumentoElectronico.ESTADO_APROBADO)

        notificacion = NotificacionCliente.objects.get()
        self.assertEqual(notificacion.calculo_triangulacion, cambio)

    def test_sin_cdc_usa_el_numero_de_documento(self):
        factura = _factura(self.operacion, cdc='')

        _cambiar_estado(factura, DocumentoElectronico.ESTADO_RECHAZADO)

        self.assertEqual(NotificacionCliente.objects.get().referencia, '0000900')

    def test_una_nota_de_credito_no_notifica_por_si_misma(self):
        factura = _factura(self.operacion, estado=DocumentoElectronico.ESTADO_APROBADO)
        nota = DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000001',
            factura_anulada=factura, motivo_emision=DocumentoElectronico.MOTIVO_OTRO, cdc='CDC-NC',
        )

        _cambiar_estado(nota, DocumentoElectronico.ESTADO_APROBADO)

        self.assertFalse(NotificacionCliente.objects.exists())

    def test_consulta_real_a_sifen_aprobada_notifica(self):
        """Integración con ``consultar_estado_sifen``: el estado que registra el sistema dispara la notificación."""
        factura = _factura(self.operacion)

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta_sifen('Aprobado')
            consultar_estado_sifen(factura)

        notificacion = NotificacionCliente.objects.get()
        self.assertEqual(notificacion.estado, DocumentoElectronico.ESTADO_APROBADO)
        self.assertEqual(notificacion.referencia, factura.cdc)

    def test_nota_de_credito_aprobada_notifica_la_cancelacion_de_la_factura(self):
        """Al aprobarse la nota de crédito, la factura pasa a "Anulada" y eso sí se notifica."""
        factura = _factura(self.operacion, estado=DocumentoElectronico.ESTADO_APROBADO)
        nota = DocumentoElectronico.objects.create(
            tipo_documento=ContadorDocumentoElectronico.TIPO_NOTA_CREDITO, numero_documento='0000001',
            factura_anulada=factura, motivo_emision=DocumentoElectronico.MOTIVO_OTRO, cdc='CDC-NC',
        )

        with patch('apps.divisas.factura_electronica.requests.post') as mock_post:
            mock_post.return_value = _respuesta_sifen('Aprobado')
            consultar_estado_sifen(nota)

        notificacion = NotificacionCliente.objects.get()
        self.assertEqual(notificacion.documento_electronico, factura)
        self.assertEqual(notificacion.estado, DocumentoElectronico.ESTADO_ANULADA)
        self.assertEqual(notificacion.categoria, NotificacionCliente.CATEGORIA_ANULADA)


class NotificacionClienteModeloTest(TestCase):
    """``url_detalle`` (criterio 3) y ``marcar_como_leida``."""

    def setUp(self):
        self.usuario = User.objects.create_user(username='cliente-modelo', password='password123')
        self.cliente = _crear_cliente(self.usuario)
        self.usd, self.eur = _crear_divisas()

    def test_url_de_una_compra_o_venta(self):
        operacion = _operacion(self.usuario, self.cliente, self.usd)
        _cambiar_estado(operacion, CalculoOperacion.ESTADO_PAGADA)

        notificacion = NotificacionCliente.objects.get()

        self.assertEqual(notificacion.url_detalle, reverse('divisas:detalle_transaccion_operacion', args=[operacion.pk]))

    def test_url_de_un_cambio(self):
        cambio = _cambio(self.usuario, self.cliente, self.usd, self.eur)
        _cambiar_estado(cambio, CalculoTriangulacion.ESTADO_PAGADA)

        notificacion = NotificacionCliente.objects.get()

        self.assertEqual(notificacion.url_detalle, reverse('divisas:detalle_transaccion_cambio', args=[cambio.pk]))

    def test_url_de_una_factura_lleva_a_su_seccion_del_detalle(self):
        operacion = _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)
        _cambiar_estado(_factura(operacion), DocumentoElectronico.ESTADO_APROBADO)

        notificacion = NotificacionCliente.objects.get()

        self.assertEqual(
            notificacion.url_detalle,
            reverse('divisas:detalle_transaccion_operacion', args=[operacion.pk]) + '#factura-electronica',
        )

    def test_marcar_como_leida_es_idempotente(self):
        operacion = _operacion(self.usuario, self.cliente, self.usd)
        _cambiar_estado(operacion, CalculoOperacion.ESTADO_PAGADA)
        notificacion = NotificacionCliente.objects.get()

        self.assertTrue(notificacion.marcar_como_leida())
        primera_lectura = notificacion.leida_en
        self.assertFalse(notificacion.marcar_como_leida())

        notificacion.refresh_from_db()
        self.assertTrue(notificacion.leida)
        self.assertEqual(notificacion.leida_en, primera_lectura)


class NotificacionesClienteVistasTest(TestCase):
    """Listado, apertura (criterio 3), indicador (criterio 4) y aislamiento entre clientes (criterio 5)."""

    def setUp(self):
        self.usuario = User.objects.create_user(username='cliente-vistas', password='password123')
        self.cliente = _crear_cliente(self.usuario, nombre='Propio')
        self.usd, self.eur = _crear_divisas()
        self.operacion = _operacion(self.usuario, self.cliente, self.usd)
        _cambiar_estado(self.operacion, CalculoOperacion.ESTADO_PAGADA)
        self.notificacion = NotificacionCliente.objects.get()
        self.url = reverse('divisas:mis_notificaciones')

    def _login(self, usuario=None, roles=('cliente',), cliente_activo=None):
        usuario = usuario or self.usuario
        self.client.force_login(usuario)
        session = self.client.session
        session['keycloak_roles'] = list(roles)
        if cliente_activo is not None:
            session['cliente_activo_id'] = cliente_activo.pk
        session.save()

    def _url_abrir(self, notificacion):
        return reverse('divisas:abrir_notificacion_cliente', args=[notificacion.pk])

    def test_el_listado_muestra_la_notificacion_con_numero_y_estado(self):
        self._login()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.notificacion, response.context['notificaciones_operaciones'])
        self.assertContains(response, str(self.operacion.pk))
        self.assertContains(response, 'Pagada')
        self.assertContains(response, self._url_abrir(self.notificacion))

    def test_el_listado_muestra_el_cdc_de_una_factura(self):
        factura = _factura(_operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA))
        _cambiar_estado(factura, DocumentoElectronico.ESTADO_RECHAZADO)
        self._login()

        response = self.client.get(self.url)

        self.assertContains(response, factura.cdc)
        self.assertContains(response, 'Rechazado por SIFEN')
        self.assertContains(response, 'Ver factura')

    def test_listado_vacio_lo_informa(self):
        NotificacionCliente.objects.all().delete()
        self._login()

        response = self.client.get(self.url)

        self.assertContains(response, 'Todavía no tenés notificaciones sobre tus transacciones ni tus facturas.')

    def test_abrir_marca_como_leida_y_lleva_al_detalle_de_la_transaccion(self):
        self._login()

        response = self.client.post(self._url_abrir(self.notificacion))

        self.assertRedirects(
            response, reverse('divisas:detalle_transaccion_operacion', args=[self.operacion.pk]),
            fetch_redirect_response=False,
        )
        self.notificacion.refresh_from_db()
        self.assertTrue(self.notificacion.leida)

    def test_el_detalle_al_que_lleva_se_puede_abrir(self):
        self._login()

        response = self.client.post(self._url_abrir(self.notificacion), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['transaccion'], self.operacion)

    def test_abrir_una_factura_lleva_a_su_seccion_en_el_detalle(self):
        operacion = _operacion(self.usuario, self.cliente, self.usd, estado=CalculoOperacion.ESTADO_PAGADA)
        factura = _factura(operacion)
        _cambiar_estado(factura, DocumentoElectronico.ESTADO_APROBADO)
        notificacion = NotificacionCliente.objects.get(documento_electronico=factura)
        self._login()

        response = self.client.post(self._url_abrir(notificacion))

        self.assertEqual(
            response['Location'],
            reverse('divisas:detalle_transaccion_operacion', args=[operacion.pk]) + '#factura-electronica',
        )
        detalle = self.client.get(response['Location'])
        self.assertContains(detalle, 'id="factura-electronica"')
        self.assertContains(detalle, factura.cdc)

    def test_abrir_por_get_no_esta_permitido(self):
        self._login()

        response = self.client.get(self._url_abrir(self.notificacion))

        self.assertEqual(response.status_code, 405)

    def test_abrir_una_notificacion_inexistente_es_404(self):
        self._login()

        response = self.client.post(reverse('divisas:abrir_notificacion_cliente', args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_las_no_leidas_se_suman_al_indicador_junto_con_las_de_tasas(self):
        """Criterio 4: el indicador suma las de transacciones/facturas y las de tasas."""
        _cambiar_estado(self.operacion, CalculoOperacion.ESTADO_ACREDITADA)
        cotizacion = Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300'), tasa_venta=Decimal('7400'))
        NotificacionTasa.objects.create(
            usuario=self.usuario, divisa=self.usd, cotizacion=cotizacion, tipo_tasa=NotificacionTasa.TIPO_COMPRA,
            tasa_anterior=Decimal('7200'), tasa_nueva=Decimal('7300'),
        )
        self._login()

        response = self.client.get(reverse('home'))

        self.assertEqual(response.context['notificaciones_operaciones_no_leidas'], 2)
        self.assertEqual(response.context['notificaciones_tasa_no_leidas'], 1)
        self.assertEqual(response.context['notificaciones_no_leidas'], 3)
        self.assertContains(response, 'data-no-leidas="3"')

    def test_abrir_descuenta_del_indicador(self):
        self._login()
        antes = self.client.get(reverse('home')).context['notificaciones_no_leidas']

        self.client.post(self._url_abrir(self.notificacion))

        despues = self.client.get(reverse('home')).context['notificaciones_no_leidas']
        self.assertEqual(antes - despues, 1)

    def test_no_se_ve_ni_se_abre_la_notificacion_de_otro_usuario(self):
        """Criterio 5 entre usuarios distintos."""
        ajeno = User.objects.create_user(username='otro-cliente', password='password123')
        _crear_cliente(ajeno, nombre='Ajeno')
        self._login(usuario=ajeno)

        listado = self.client.get(self.url)
        apertura = self.client.post(self._url_abrir(self.notificacion))

        self.assertNotIn(self.notificacion, listado.context['notificaciones_operaciones'])
        self.assertNotContains(listado, str(self.operacion.pk))
        self.assertEqual(listado.context['notificaciones_no_leidas'], 0)
        self.assertEqual(apertura.status_code, 404)
        self.notificacion.refresh_from_db()
        self.assertFalse(self.notificacion.leida)

    def test_con_otro_cliente_activo_no_se_ve_la_notificacion_del_primero(self):
        """Criterio 5 para un mismo usuario con dos clientes: solo cuenta el cliente activo."""
        segundo_cliente = _crear_cliente(self.usuario, nombre='Segundo')
        self._login(cliente_activo=segundo_cliente)

        listado = self.client.get(self.url)
        apertura = self.client.post(self._url_abrir(self.notificacion))

        self.assertEqual(list(listado.context['notificaciones_operaciones']), [])
        self.assertEqual(listado.context['notificaciones_operaciones_no_leidas'], 0)
        self.assertEqual(apertura.status_code, 404)

    def test_al_volver_al_primer_cliente_vuelve_a_verla(self):
        _crear_cliente(self.usuario, nombre='Segundo')
        self._login(cliente_activo=self.cliente)

        listado = self.client.get(self.url)

        self.assertIn(self.notificacion, listado.context['notificaciones_operaciones'])
        self.assertEqual(listado.context['notificaciones_operaciones_no_leidas'], 1)

    def test_sin_rol_cliente_no_accede_ni_ve_indicador(self):
        self._login(roles=('analista_cambiario',))

        listado = self.client.get(self.url)
        apertura = self.client.post(self._url_abrir(self.notificacion))

        self.assertEqual(listado.status_code, 403)
        self.assertEqual(apertura.status_code, 403)

    def test_un_anonimo_es_redirigido_al_login(self):
        response = self.client.post(self._url_abrir(self.notificacion))

        self.assertEqual(response.status_code, 302)
        self.assertNotIn(reverse('divisas:detalle_transaccion_operacion', args=[self.operacion.pk]), response['Location'])

    def test_las_notificaciones_de_tasas_se_siguen_listando(self):
        cotizacion = Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300'), tasa_venta=Decimal('7400'))
        tasa = NotificacionTasa.objects.create(
            usuario=self.usuario, divisa=self.usd, cotizacion=cotizacion, tipo_tasa=NotificacionTasa.TIPO_VENTA,
            tasa_anterior=Decimal('7400'), tasa_nueva=Decimal('7450'),
        )
        self._login()

        response = self.client.get(self.url)

        self.assertIn(tasa, response.context['notificaciones'])
        self.assertIn(self.notificacion, response.context['notificaciones_operaciones'])
