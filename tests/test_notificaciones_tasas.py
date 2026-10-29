"""Pruebas de la HU GE-51: notificaciones sobre cambios en las tasas de cambio.

Cada clase cubre uno de los criterios de aceptación de la historia:

- CA1: un cambio de tasa de compra o de venta notifica a todos los usuarios clientes.
- CA2: guardar una tasa con el mismo valor no genera notificaciones.
- CA3: la notificación incluye divisa, tipo de tasa, tasa anterior y tasa nueva.
- CA4: el cliente ve sus notificaciones de la más reciente a la más antigua.
- CA5: hay un indicador con la cantidad de notificaciones no leídas.
- CA6: marcar una notificación como leída cambia su estado y la descuenta del indicador.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.shortcuts import resolve_url
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.divisas.models import Cotizacion, Divisa, NotificacionTasa
from tests.utils_formato import formato


class NotificacionesTasasBaseTest(TestCase):
    """Datos comunes: una divisa con cotización vigente y usuarios de distintos tipos."""

    def setUp(self):
        """Crea la divisa USD con una cotización inicial y los usuarios de prueba.

        - ``cliente_asociado``: usuario del sistema asociado a un cliente activo.
        - ``cliente_titular``: titular (``Cliente.user``) de otro cliente activo.
        - ``sin_cliente``: usuario sin ningún cliente asociado (p. ej. un analista).
        - ``cliente_dado_de_baja``: asociado solo a un cliente inactivo.
        - ``usuario_inactivo``: usuario deshabilitado aunque tenga cliente activo.
        """
        self.divisa = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.cotizacion_inicial = Cotizacion.objects.create(
            divisa=self.divisa, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'),
        )

        self.cliente_asociado = User.objects.create_user(username='cliente1', password='password123')
        cliente_a = Cliente.objects.create(nombre='Ana', apellido='Pérez', identificador='1001', email='ana@ge.com')
        cliente_a.usuarios.add(self.cliente_asociado)

        self.cliente_titular = User.objects.create_user(username='cliente2', password='password123')
        Cliente.objects.create(
            nombre='Beto', apellido='Gómez', identificador='1002', email='beto@ge.com', user=self.cliente_titular,
        )

        self.sin_cliente = User.objects.create_user(username='analista', password='password123')

        self.cliente_dado_de_baja = User.objects.create_user(username='cliente3', password='password123')
        cliente_inactivo = Cliente.objects.create(
            nombre='Caro', identificador='1003', email='caro@ge.com', is_active=False,
        )
        cliente_inactivo.usuarios.add(self.cliente_dado_de_baja)

        self.usuario_inactivo = User.objects.create_user(
            username='cliente4', password='password123', is_active=False,
        )
        cliente_d = Cliente.objects.create(nombre='Dani', identificador='1004', email='dani@ge.com')
        cliente_d.usuarios.add(self.usuario_inactivo)

    def _login(self, username, roles):
        """Inicia sesión con los roles de Keycloak indicados."""
        self.client.login(username=username, password='password123')
        session = self.client.session
        session['keycloak_roles'] = roles
        session.save()

    def _crear_notificacion(self, usuario, tipo=NotificacionTasa.TIPO_COMPRA, anterior='7300', nueva='7350', **extra):
        """Crea directamente una notificación para pruebas de pantalla."""
        return NotificacionTasa.objects.create(
            usuario=usuario,
            divisa=self.divisa,
            cotizacion=self.cotizacion_inicial,
            tipo_tasa=tipo,
            tasa_anterior=Decimal(anterior),
            tasa_nueva=Decimal(nueva),
            **extra,
        )


@pytest.mark.django_db
class GeneracionNotificacionesTest(NotificacionesTasasBaseTest):
    """CA1: un cambio en la tasa de compra o de venta notifica a todos los usuarios clientes."""

    def test_cambio_de_tasa_de_compra_notifica_a_todos_los_clientes(self):
        """Un cambio en la tasa de compra genera una notificación para cada usuario cliente."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7350.00'), tasa_venta=Decimal('7400.00'))

        destinatarios = set(NotificacionTasa.objects.values_list('usuario', flat=True))
        self.assertEqual(destinatarios, {self.cliente_asociado.pk, self.cliente_titular.pk})
        self.assertEqual(NotificacionTasa.objects.count(), 2)
        self.assertTrue(all(
            n.tipo_tasa == NotificacionTasa.TIPO_COMPRA for n in NotificacionTasa.objects.all()
        ))

    def test_cambio_de_tasa_de_venta_notifica_a_todos_los_clientes(self):
        """Un cambio en la tasa de venta genera una notificación para cada usuario cliente."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7450.00'))

        self.assertEqual(NotificacionTasa.objects.count(), 2)
        self.assertEqual(
            set(NotificacionTasa.objects.values_list('tipo_tasa', flat=True)), {NotificacionTasa.TIPO_VENTA},
        )

    def test_cambio_de_ambas_tasas_genera_una_notificacion_por_tipo(self):
        """Si cambian compra y venta, cada cliente recibe una notificación por cada tipo de tasa."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7310.00'), tasa_venta=Decimal('7410.00'))

        for usuario in (self.cliente_asociado, self.cliente_titular):
            tipos = set(usuario.notificaciones_tasa.values_list('tipo_tasa', flat=True))
            self.assertEqual(tipos, {NotificacionTasa.TIPO_COMPRA, NotificacionTasa.TIPO_VENTA})
        self.assertEqual(NotificacionTasa.objects.count(), 4)

    def test_no_notifica_a_usuarios_que_no_son_clientes(self):
        """Usuarios sin cliente, con cliente dado de baja o inactivos no reciben notificaciones."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7350.00'), tasa_venta=Decimal('7400.00'))

        for usuario in (self.sin_cliente, self.cliente_dado_de_baja, self.usuario_inactivo):
            self.assertFalse(usuario.notificaciones_tasa.exists())

    def test_usuario_con_varios_clientes_recibe_una_sola_notificacion(self):
        """Un usuario asociado a varios clientes no recibe notificaciones duplicadas."""
        otro_cliente = Cliente.objects.create(nombre='Eva', identificador='1005', email='eva@ge.com')
        otro_cliente.usuarios.add(self.cliente_asociado)

        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7350.00'), tasa_venta=Decimal('7400.00'))

        self.assertEqual(self.cliente_asociado.notificaciones_tasa.count(), 1)

    def test_actualizacion_desde_la_pantalla_del_analista_genera_notificaciones(self):
        """Guardar el cambio desde el formulario de actualización de tasas notifica a los clientes."""
        self._login('analista', ['analista_cambiario'])

        response = self.client.post(
            reverse('divisas:actualizar_cotizacion', kwargs={'divisa_id': self.divisa.pk}),
            {'tasa_compra': '7320', 'tasa_venta': '7400'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.cliente_asociado.notificaciones_tasa.count(), 1)
        self.assertEqual(self.cliente_titular.notificaciones_tasa.count(), 1)

    def test_las_notificaciones_se_asocian_a_la_cotizacion_que_genero_el_cambio(self):
        """Cada notificación referencia la cotización nueva y la divisa afectada."""
        nueva = Cotizacion.objects.create(
            divisa=self.divisa, tasa_compra=Decimal('7350.00'), tasa_venta=Decimal('7400.00'),
        )

        self.assertTrue(all(n.cotizacion_id == nueva.pk for n in NotificacionTasa.objects.all()))

    def test_compara_contra_la_ultima_cotizacion_de_la_misma_divisa(self):
        """La tasa anterior es la última de esa divisa, no la de otra divisa."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', activa=True)
        Cotizacion.objects.create(divisa=eur, tasa_compra=Decimal('8000.00'), tasa_venta=Decimal('8100.00'))
        self.assertFalse(NotificacionTasa.objects.exists())

        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7350.00'), tasa_venta=Decimal('7400.00'))

        notificacion = self.cliente_asociado.notificaciones_tasa.get()
        self.assertEqual(notificacion.divisa, self.divisa)
        self.assertEqual(notificacion.tasa_anterior, Decimal('7300.00'))


@pytest.mark.django_db
class SinCambioNoNotificaTest(NotificacionesTasasBaseTest):
    """CA2: guardar una tasa con el mismo valor que ya tenía no genera notificaciones."""

    def test_mismos_valores_no_generan_notificaciones(self):
        """Una cotización idéntica a la anterior no genera ninguna notificación."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))

        self.assertFalse(NotificacionTasa.objects.exists())

    def test_mismo_valor_con_distinto_formato_no_notifica(self):
        """``7300`` y ``7300.00`` son el mismo valor y no cuentan como cambio."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=7300, tasa_venta='7400.0')

        self.assertFalse(NotificacionTasa.objects.exists())

    def test_mismos_valores_desde_la_pantalla_del_analista_no_notifican(self):
        """Reenviar las mismas tasas desde el formulario guarda el historial pero no notifica."""
        self._login('analista', ['analista_cambiario'])

        response = self.client.post(
            reverse('divisas:actualizar_cotizacion', kwargs={'divisa_id': self.divisa.pk}),
            {'tasa_compra': '7300.00', 'tasa_venta': '7400.00'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Cotizacion.objects.filter(divisa=self.divisa).count(), 2)
        self.assertFalse(NotificacionTasa.objects.exists())

    def test_solo_se_notifica_la_tasa_que_cambio(self):
        """Si solo cambia la venta, no se genera notificación de la compra (que quedó igual)."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7420.00'))

        self.assertFalse(NotificacionTasa.objects.filter(tipo_tasa=NotificacionTasa.TIPO_COMPRA).exists())
        self.assertTrue(NotificacionTasa.objects.filter(tipo_tasa=NotificacionTasa.TIPO_VENTA).exists())

    def test_primera_cotizacion_de_una_divisa_no_notifica(self):
        """La primera cotización de una divisa no tiene tasa anterior con la que comparar."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', activa=True)

        Cotizacion.objects.create(divisa=eur, tasa_compra=Decimal('8000.00'), tasa_venta=Decimal('8100.00'))

        self.assertFalse(NotificacionTasa.objects.exists())

    def test_volver_a_guardar_una_cotizacion_existente_no_notifica(self):
        """Editar y volver a guardar una cotización ya registrada no se considera una actualización."""
        self.cotizacion_inicial.tasa_compra = Decimal('7999.00')
        self.cotizacion_inicial.save()

        self.assertFalse(NotificacionTasa.objects.exists())


@pytest.mark.django_db
class ContenidoNotificacionTest(NotificacionesTasasBaseTest):
    """CA3: la notificación incluye divisa, tipo de tasa, tasa anterior y tasa nueva."""

    def test_notificacion_de_compra_incluye_todos_los_datos(self):
        """Se guardan la divisa, el tipo COMPRA y las tasas anterior y nueva."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7350.50'), tasa_venta=Decimal('7400.00'))

        notificacion = self.cliente_asociado.notificaciones_tasa.get()
        self.assertEqual(notificacion.divisa, self.divisa)
        self.assertEqual(notificacion.tipo_tasa, NotificacionTasa.TIPO_COMPRA)
        self.assertEqual(notificacion.get_tipo_tasa_display(), 'Compra')
        self.assertEqual(notificacion.tasa_anterior, Decimal('7300.00'))
        self.assertEqual(notificacion.tasa_nueva, Decimal('7350.50'))

    def test_notificacion_de_venta_incluye_todos_los_datos(self):
        """Se guardan la divisa, el tipo VENTA y las tasas anterior y nueva."""
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7380.00'))

        notificacion = self.cliente_titular.notificaciones_tasa.get()
        self.assertEqual(notificacion.tipo_tasa, NotificacionTasa.TIPO_VENTA)
        self.assertEqual(notificacion.get_tipo_tasa_display(), 'Venta')
        self.assertEqual(notificacion.tasa_anterior, Decimal('7400.00'))
        self.assertEqual(notificacion.tasa_nueva, Decimal('7380.00'))

    def test_mensaje_y_variacion(self):
        """El mensaje legible y la variación reflejan el cambio de la tasa."""
        notificacion = self._crear_notificacion(self.cliente_asociado, anterior='7300.00', nueva='7280.00')

        self.assertEqual(notificacion.mensaje, 'La tasa de compra de USD cambió de 7300.00 a 7280.00.')
        self.assertEqual(notificacion.variacion, Decimal('-20.00'))
        self.assertFalse(notificacion.subio)
        self.assertIn('USD', str(notificacion))

    def test_la_pantalla_muestra_divisa_tipo_y_ambas_tasas(self):
        """El listado muestra la divisa, el tipo de tasa y los valores anterior y nuevo."""
        self._crear_notificacion(
            self.cliente_asociado, tipo=NotificacionTasa.TIPO_VENTA, anterior='7400.00', nueva='7455.25',
        )
        self._login('cliente1', ['cliente'])

        response = self.client.get(reverse('divisas:mis_notificaciones'))

        self.assertContains(response, 'USD')
        self.assertContains(response, 'Venta')
        self.assertContains(response, formato(Decimal('7400.00')))
        self.assertContains(response, formato(Decimal('7455.25')))


@pytest.mark.django_db
class ListadoNotificacionesTest(NotificacionesTasasBaseTest):
    """CA4: el cliente ve sus notificaciones ordenadas de la más reciente a la más antigua."""

    def setUp(self):
        """Crea tres notificaciones propias con fechas distintas y una ajena."""
        super().setUp()
        ahora = timezone.now()
        self.antigua = self._crear_notificacion(self.cliente_asociado, nueva='7310')
        self.intermedia = self._crear_notificacion(self.cliente_asociado, nueva='7320')
        self.reciente = self._crear_notificacion(self.cliente_asociado, nueva='7330')
        NotificacionTasa.objects.filter(pk=self.antigua.pk).update(creada_en=ahora - timedelta(days=2))
        NotificacionTasa.objects.filter(pk=self.intermedia.pk).update(creada_en=ahora - timedelta(days=1))
        NotificacionTasa.objects.filter(pk=self.reciente.pk).update(creada_en=ahora)
        self.ajena = self._crear_notificacion(self.cliente_titular, nueva='7999')
        self.url = reverse('divisas:mis_notificaciones')

    def test_listado_ordenado_de_la_mas_reciente_a_la_mas_antigua(self):
        """Las notificaciones aparecen de la más nueva a la más vieja."""
        self._login('cliente1', ['cliente'])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [n.pk for n in response.context['notificaciones']],
            [self.reciente.pk, self.intermedia.pk, self.antigua.pk],
        )

    def test_solo_muestra_las_notificaciones_propias(self):
        """Un cliente no ve las notificaciones de otro usuario."""
        self._login('cliente1', ['cliente'])

        response = self.client.get(self.url)

        self.assertNotIn(self.ajena, response.context['notificaciones'])
        self.assertNotContains(response, formato(Decimal('7999')))

    def test_listado_vacio_muestra_mensaje(self):
        """Sin notificaciones se informa que todavía no hay ninguna."""
        NotificacionTasa.objects.filter(usuario=self.cliente_asociado).delete()
        self._login('cliente1', ['cliente'])

        response = self.client.get(self.url)

        self.assertContains(response, 'Todavía no tenés notificaciones.')

    def test_requiere_autenticacion_y_rol_cliente(self):
        """Un anónimo es redirigido al login; un autenticado sin rol de cliente, rechazado."""
        with self.subTest('anónimo'):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(resolve_url(settings.LOGIN_URL), response.url)

        with self.subTest('sin rol de cliente'):
            self._login('analista', ['analista_cambiario'])
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 403)


@pytest.mark.django_db
class IndicadorNoLeidasTest(NotificacionesTasasBaseTest):
    """CA5: mientras navega, el cliente ve un indicador con la cantidad de notificaciones no leídas."""

    def test_indicador_muestra_la_cantidad_de_no_leidas(self):
        """El contexto expone la cantidad de no leídas, sin contar las ya leídas."""
        self._crear_notificacion(self.cliente_asociado)
        self._crear_notificacion(self.cliente_asociado)
        self._crear_notificacion(self.cliente_asociado, leida=True, leida_en=timezone.now())
        self._login('cliente1', ['cliente'])

        response = self.client.get(reverse('divisas:tasas_vigentes'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['puede_ver_notificaciones'])
        self.assertEqual(response.context['notificaciones_no_leidas'], 2)
        self.assertContains(response, 'id="geIndicadorNotificaciones"')
        self.assertContains(response, 'data-no-leidas="2"')

    def test_indicador_visible_en_distintas_pantallas(self):
        """El indicador aparece en cualquier pantalla que herede de la plantilla base."""
        self._crear_notificacion(self.cliente_asociado)
        self._login('cliente1', ['cliente'])

        for url in (reverse('home'), reverse('divisas:tasas_vigentes'), reverse('divisas:mis_notificaciones')):
            response = self.client.get(url)
            self.assertContains(response, 'data-no-leidas="1"', msg_prefix=url)

    def test_indicador_no_cuenta_notificaciones_ajenas(self):
        """Solo se cuentan las notificaciones del usuario autenticado."""
        self._crear_notificacion(self.cliente_titular)
        self._login('cliente1', ['cliente'])

        response = self.client.get(reverse('divisas:tasas_vigentes'))

        self.assertEqual(response.context['notificaciones_no_leidas'], 0)
        self.assertNotContains(response, 'data-no-leidas=')

    def test_indicador_se_actualiza_al_llegar_un_cambio_de_tasa(self):
        """Un cambio de tasa nuevo aumenta el contador del cliente."""
        self._login('cliente1', ['cliente'])
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7310.00'), tasa_venta=Decimal('7410.00'))

        response = self.client.get(reverse('divisas:tasas_vigentes'))

        self.assertEqual(response.context['notificaciones_no_leidas'], 2)

    def test_indicador_oculto_para_usuarios_sin_rol_cliente(self):
        """Quien no es cliente no ve el indicador de notificaciones."""
        self._login('analista', ['analista_cambiario'])

        response = self.client.get(reverse('divisas:tasas_vigentes'))

        self.assertFalse(response.context['puede_ver_notificaciones'])
        self.assertNotContains(response, 'id="geIndicadorNotificaciones"')


@pytest.mark.django_db
class MarcarComoLeidaTest(NotificacionesTasasBaseTest):
    """CA6: al marcar una notificación como leída cambia su estado y deja de contarse."""

    def setUp(self):
        """Crea dos notificaciones no leídas para el cliente y una ajena."""
        super().setUp()
        self.notificacion = self._crear_notificacion(self.cliente_asociado)
        self.otra = self._crear_notificacion(self.cliente_asociado, nueva='7360')
        self.ajena = self._crear_notificacion(self.cliente_titular)
        self._login('cliente1', ['cliente'])

    def _url(self, notificacion):
        """URL para marcar como leída la notificación indicada."""
        return reverse('divisas:marcar_notificacion_leida', kwargs={'pk': notificacion.pk})

    def test_marcar_como_leida_cambia_el_estado(self):
        """La notificación queda leída y registra la fecha de lectura."""
        response = self.client.post(self._url(self.notificacion))

        self.assertRedirects(response, reverse('divisas:mis_notificaciones'))
        self.notificacion.refresh_from_db()
        self.assertTrue(self.notificacion.leida)
        self.assertIsNotNone(self.notificacion.leida_en)

    def test_leida_deja_de_contarse_en_el_indicador(self):
        """Tras marcarla, el contador de no leídas disminuye en uno."""
        antes = self.client.get(reverse('divisas:tasas_vigentes')).context['notificaciones_no_leidas']

        self.client.post(self._url(self.notificacion))
        despues = self.client.get(reverse('divisas:tasas_vigentes')).context['notificaciones_no_leidas']

        self.assertEqual(antes, 2)
        self.assertEqual(despues, 1)

    def test_listado_muestra_el_estado_leida(self):
        """En el listado, la notificación marcada aparece como leída y sin el botón de acción."""
        self.client.post(self._url(self.notificacion))

        response = self.client.get(reverse('divisas:mis_notificaciones'))

        self.assertContains(response, 'Leída')
        self.assertNotContains(response, self._url(self.notificacion))
        self.assertContains(response, self._url(self.otra))

    def test_no_puede_marcar_notificaciones_ajenas(self):
        """Intentar marcar una notificación de otro usuario responde 404 y no la modifica."""
        response = self.client.post(self._url(self.ajena))

        self.assertEqual(response.status_code, 404)
        self.ajena.refresh_from_db()
        self.assertFalse(self.ajena.leida)

    def test_solo_acepta_post(self):
        """Un GET no marca la notificación como leída."""
        response = self.client.get(self._url(self.notificacion))

        self.assertEqual(response.status_code, 405)
        self.notificacion.refresh_from_db()
        self.assertFalse(self.notificacion.leida)

    def test_marcar_dos_veces_es_idempotente(self):
        """Volver a marcarla no cambia la fecha de lectura original."""
        self.assertTrue(self.notificacion.marcar_como_leida())
        primera_lectura = self.notificacion.leida_en

        self.assertFalse(self.notificacion.marcar_como_leida())
        self.notificacion.refresh_from_db()
        self.assertEqual(self.notificacion.leida_en, primera_lectura)

    def test_redirige_segun_el_next_recibido(self):
        """Respeta un 'next' propio y seguro; ignora uno hacia otro dominio para evitar redirecciones abiertas."""
        with self.subTest('next propio y seguro'):
            destino = reverse('divisas:mis_notificaciones') + '?page=2'
            response = self.client.post(self._url(self.notificacion), {'next': destino})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, destino)

        with self.subTest('next externo, se ignora'):
            response = self.client.post(self._url(self.otra), {'next': 'https://malicioso.example/'})
            self.assertRedirects(response, reverse('divisas:mis_notificaciones'))

    def test_requiere_rol_cliente(self):
        """Un usuario sin rol de cliente no puede marcar notificaciones."""
        self._login('analista', ['analista_cambiario'])

        response = self.client.post(self._url(self.notificacion))

        self.assertEqual(response.status_code, 403)
