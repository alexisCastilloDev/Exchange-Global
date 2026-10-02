"""Pruebas del cliente activo y su persistencia en la sesión."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.divisas.models import CalculoOperacion, Cotizacion, Divisa


User = get_user_model()


def crear_cliente(nombre, identificador):
    """Crea un cliente físico mínimo para los escenarios de selección."""
    return Cliente.objects.create(
        tipo_cliente=Cliente.TIPO_FISICA,
        nombre=nombre,
        apellido='Prueba',
        identificador=identificador,
    )


@pytest.mark.django_db
class TestSeleccionClienteActivo:
    """Verifica selección inicial, cambio y aislamiento entre usuarios."""

    def test_usuario_con_multiples_clientes_debe_seleccionar_al_iniciar(self, client):
        """Solicita selección cuando el usuario tiene varios clientes."""
        usuario = User.objects.create_user(username='operador-multiple')
        cliente_uno = crear_cliente('Cliente Uno', '1001')
        cliente_dos = crear_cliente('Cliente Dos', '1002')
        usuario.clientes.add(cliente_uno, cliente_dos)
        client.force_login(usuario)

        response = client.get(reverse('home'))

        assert response.status_code == 302
        assert response.url == reverse('seleccionar_cliente')
        assert 'cliente_activo_id' not in client.session

    def test_selector_muestra_nombre_completo_documento_segmento_y_estado(self, client):
        """Muestra los datos relevantes de cada cliente seleccionable."""
        usuario = User.objects.create_user(username='selector-detalle')
        cliente = crear_cliente('Cliente Visible', 'SEG-100')
        cliente.segmento = 'VIP'
        cliente.save()
        usuario.clientes.add(cliente, crear_cliente('Segundo Cliente', 'SEG-200'))
        client.force_login(usuario)

        response = client.get(reverse('seleccionar_cliente'))

        assert response.status_code == 200
        contenido = response.content.decode()
        assert 'Cliente Visible' in contenido
        assert 'Persona física' in contenido
        assert 'Segmento: VIP' in contenido
        assert 'Activo' in contenido
        assert 'Prueba' in contenido
        assert 'CI/RUC: SEG-100' in contenido

    def test_seleccion_de_cliente_persiste_y_se_expone_en_las_vistas(self, client):
        """Persiste el cliente elegido y lo expone en el perfil."""
        usuario = User.objects.create_user(username='operador-seleccion')
        cliente_uno = crear_cliente('Cliente Uno', '2001')
        cliente_dos = crear_cliente('Cliente Dos', '2002')
        usuario.clientes.add(cliente_uno, cliente_dos)
        client.force_login(usuario)

        response = client.post(
            reverse('seleccionar_cliente'),
            {'cliente_id': cliente_dos.pk},
        )

        assert response.status_code == 302
        assert client.session['cliente_activo_id'] == cliente_dos.pk

        response = client.get(reverse('perfil'))

        assert response.status_code == 200
        assert response.context['cliente_activo'] == cliente_dos

    def test_usuario_puede_cambiar_de_cliente_sin_cerrar_sesion(self, client):
        """Permite cambiar de cliente sin invalidar la sesión."""
        usuario = User.objects.create_user(username='operador-cambio')
        cliente_uno = crear_cliente('Cliente Uno', '3001')
        cliente_dos = crear_cliente('Cliente Dos', '3002')
        usuario.clientes.add(cliente_uno, cliente_dos)
        client.force_login(usuario)
        client.post(reverse('seleccionar_cliente'), {'cliente_id': cliente_uno.pk})

        response = client.get(
            reverse('cambiar_cliente', kwargs={'cliente_id': cliente_dos.pk}),
            HTTP_REFERER=reverse('perfil'),
        )

        assert response.status_code == 302
        assert response.url == reverse('perfil')
        assert client.session['cliente_activo_id'] == cliente_dos.pk
        assert client.session.get('_auth_user_id') == str(usuario.pk)

    def test_usuario_con_un_cliente_lo_selecciona_automaticamente(self, client):
        """Selecciona automáticamente el único cliente asociado."""
        usuario = User.objects.create_user(username='operador-unico')
        cliente = crear_cliente('Cliente Único', '4001')
        usuario.clientes.add(cliente)
        client.force_login(usuario)

        response = client.get(reverse('home'))

        assert response.status_code == 200
        assert client.session['cliente_activo_id'] == cliente.pk
        assert cliente.nombre.encode() in response.content
        assert cliente.apellido.encode() in response.content
        assert cliente.identificador.encode() in response.content

    def test_sesion_no_puede_activar_cliente_de_otro_usuario(self, client):
        """Impide activar desde sesión un cliente ajeno."""
        usuario = User.objects.create_user(username='operador-seguro')
        cliente_propio = crear_cliente('Cliente Propio', '5001')
        cliente_propio_dos = crear_cliente('Cliente Propio Dos', '5002')
        cliente_ajeno = crear_cliente('Cliente Ajeno', '5003')
        usuario.clientes.add(cliente_propio, cliente_propio_dos)
        client.force_login(usuario)

        session = client.session
        session['cliente_activo_id'] = cliente_ajeno.pk
        session.save()

        response = client.get(reverse('perfil'))

        assert response.status_code == 302
        assert response.url == reverse('seleccionar_cliente')

    def test_cambiar_cliente_desde_el_detalle_de_una_transaccion_vuelve_al_historial(self, client):
        """Cambiar de cliente desde el detalle de una transacción no repite esa URL (404)."""
        usuario = User.objects.create_user(username='operador-detalle-transaccion')
        cliente_uno = crear_cliente('Cliente Uno', '6001')
        cliente_dos = crear_cliente('Cliente Dos', '6002')
        usuario.clientes.add(cliente_uno, cliente_dos)
        client.force_login(usuario)
        client.post(reverse('seleccionar_cliente'), {'cliente_id': cliente_uno.pk})

        usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
        transaccion = CalculoOperacion.objects.create(
            usuario=usuario,
            cliente=cliente_uno,
            tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=usd,
            codigo_divisa='USD',
            monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'),
            monto_final=Decimal('747400.00'),
            vence_en=timezone.now() + timedelta(seconds=300),
        )
        referer = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': transaccion.pk})

        response = client.get(
            reverse('cambiar_cliente', kwargs={'cliente_id': cliente_dos.pk}),
            HTTP_REFERER=referer,
        )

        assert response.status_code == 302
        assert response.url == reverse('divisas:mis_transacciones')
        assert client.session['cliente_activo_id'] == cliente_dos.pk

    def test_cambiar_cliente_desde_una_pantalla_sin_registro_propio_vuelve_ahi(self, client):
        """Cambiar de cliente desde una pantalla que no depende del cliente anterior vuelve ahí."""
        usuario = User.objects.create_user(username='operador-cambio-generico')
        cliente_uno = crear_cliente('Cliente Uno', '6003')
        cliente_dos = crear_cliente('Cliente Dos', '6004')
        usuario.clientes.add(cliente_uno, cliente_dos)
        client.force_login(usuario)
        client.post(reverse('seleccionar_cliente'), {'cliente_id': cliente_uno.pk})

        response = client.get(
            reverse('cambiar_cliente', kwargs={'cliente_id': cliente_dos.pk}),
            HTTP_REFERER=reverse('divisas:mis_transacciones'),
        )

        assert response.status_code == 302
        assert response.url == reverse('divisas:mis_transacciones')

    def test_dropdown_de_cambio_de_cliente_muestra_la_razon_social_sin_none(self, client):
        """El selector de cambio de cliente muestra la razón social de un cliente jurídico, sin 'None'."""
        usuario = User.objects.create_user(username='operador-juridico')
        cliente_fisico = crear_cliente('Cliente Fisico', '7001')
        cliente_juridico = Cliente.objects.create(
            tipo_cliente=Cliente.TIPO_JURIDICA,
            razon_social='Comercial Sur S.A.',
            identificador='7002',
        )
        usuario.clientes.add(cliente_fisico, cliente_juridico)
        client.force_login(usuario)
        client.post(reverse('seleccionar_cliente'), {'cliente_id': cliente_fisico.pk})

        response = client.get(reverse('perfil'))

        contenido = response.content.decode()
        assert 'Comercial Sur S.A.' in contenido
        assert 'None Comercial Sur S.A.' not in contenido
