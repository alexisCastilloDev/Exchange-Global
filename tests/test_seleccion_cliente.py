import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.clientes.models import Cliente


User = get_user_model()


def crear_cliente(nombre, identificador):
    return Cliente.objects.create(
        tipo_cliente=Cliente.TIPO_FISICA,
        nombre=nombre,
        apellido='Prueba',
        identificador=identificador,
    )


@pytest.mark.django_db
class TestSeleccionClienteActivo:

    def test_usuario_con_multiples_clientes_debe_seleccionar_al_iniciar(self, client):
        usuario = User.objects.create_user(username='operador-multiple')
        cliente_uno = crear_cliente('Cliente Uno', '1001')
        cliente_dos = crear_cliente('Cliente Dos', '1002')
        usuario.clientes.add(cliente_uno, cliente_dos)
        client.force_login(usuario)

        response = client.get(reverse('home'))

        assert response.status_code == 302
        assert response.url == reverse('seleccionar_cliente')
        assert 'cliente_activo_id' not in client.session

    def test_seleccion_de_cliente_persiste_y_se_expone_en_las_vistas(self, client):
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
        usuario = User.objects.create_user(username='operador-unico')
        cliente = crear_cliente('Cliente Único', '4001')
        usuario.clientes.add(cliente)
        client.force_login(usuario)

        response = client.get(reverse('home'))

        assert response.status_code == 200
        assert client.session['cliente_activo_id'] == cliente.pk
        assert cliente.nombre.encode() in response.content

    def test_sesion_no_puede_activar_cliente_de_otro_usuario(self, client):
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