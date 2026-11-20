"""Pruebas del registro y auditoría de actividades (GE-71).

Cada clase corresponde a uno de los criterios de aceptación de la HU:

1. ``RegistroDeAccionesTest``: cada acción administrativa queda registrada
   con quién, cuándo, sobre qué registro y qué cambió.
2. ``ListadoTest``: listado paginado, de la más reciente a la más antigua.
3. ``FiltrosTest``: filtro por usuario, tipo de acción y rango de fechas.
4. ``InmutabilidadTest``: un registro no se puede modificar ni eliminar.
5. ``AccesoTest``: solo un administrador accede al registro.
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroActividad
from apps.auditoria.registro import registrar_actividad
from apps.divisas.models import ConfiguracionComision, ConfiguracionVigencia, Cotizacion, Divisa

User = get_user_model()


def _loguear(client, usuario, roles):
    """Inicia sesión con ``usuario`` y le asigna los roles de Keycloak indicados."""
    client.force_login(usuario)
    session = client.session
    session['keycloak_roles'] = roles
    session.save()


def _cambios(registro):
    """Devuelve los cambios de un registro como ``{campo: (anterior, nuevo)}``."""
    return {cambio['campo']: (cambio['anterior'], cambio['nuevo']) for cambio in registro.cambios}


class RegistroDeAccionesTest(TestCase):
    """Criterio 1: cada alta, modificación o baja administrativa queda registrada."""

    def setUp(self):
        """Prepara un administrador logueado y una divisa con su cotización."""
        self.admin = User.objects.create_user(
            username='admin-auditoria', password='x', first_name='Ana', last_name='Admin', email='ana@ge.com',
        )
        _loguear(self.client, self.admin, ['admin'])
        self.divisa = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$')
        Cotizacion.objects.create(divisa=self.divisa, tasa_compra=Decimal('7300'), tasa_venta=Decimal('7400'))

    def _unico_registro(self, **filtros):
        """Devuelve el único registro que cumple ``filtros``, fallando si no hay exactamente uno."""
        registros = RegistroActividad.objects.filter(**filtros)
        self.assertEqual(registros.count(), 1, list(registros))
        return registros.get()

    def test_alta_de_divisa_registra_quien_cuando_que_registro_y_valores(self):
        """El alta registra usuario, fecha, registro afectado y los valores cargados."""
        antes = timezone.now()
        self.client.post(reverse('divisas:crear_divisa'), {'codigo': 'EUR', 'nombre': 'Euro', 'simbolo': '€'})

        divisa = Divisa.objects.get(codigo='EUR')
        registro = self._unico_registro(tipo_recurso=RegistroActividad.RECURSO_DIVISA)
        self.assertEqual(registro.accion, RegistroActividad.ACCION_ALTA)
        self.assertEqual(registro.usuario, self.admin)
        self.assertEqual(registro.usuario_nombre, 'Ana Admin')
        self.assertGreaterEqual(registro.fecha, antes)
        self.assertEqual(registro.recurso_id, str(divisa.pk))
        self.assertEqual(registro.recurso_descripcion, 'EUR - Euro')
        self.assertEqual(
            _cambios(registro),
            {'codigo': (None, 'EUR'), 'nombre': (None, 'Euro'), 'simbolo': (None, '€'), 'activa': (None, 'Sí')},
        )

    def test_modificacion_de_divisa_registra_solo_los_campos_que_cambiaron(self):
        """Una modificación lista cada campo cambiado con su valor anterior y nuevo."""
        self.client.post(
            reverse('divisas:editar_divisa', args=[self.divisa.pk]),
            {'codigo': 'USD', 'nombre': 'Dólar estadounidense', 'simbolo': '$'},
        )

        registro = self._unico_registro(tipo_recurso=RegistroActividad.RECURSO_DIVISA)
        self.assertEqual(registro.accion, RegistroActividad.ACCION_MODIFICACION)
        self.assertEqual(_cambios(registro), {'nombre': ('Dólar', 'Dólar estadounidense')})

    def test_guardar_sin_cambios_no_registra_nada(self):
        """Enviar el formulario sin modificar ningún dato no es un cambio que auditar."""
        self.client.post(
            reverse('divisas:editar_divisa', args=[self.divisa.pk]),
            {'codigo': 'USD', 'nombre': 'Dólar', 'simbolo': '$'},
        )

        self.assertFalse(RegistroActividad.objects.exists())

    def test_baja_logica_de_divisa_se_registra_como_baja(self):
        """Desactivar una divisa se registra como "Baja", no como una modificación cualquiera."""
        self.client.post(reverse('divisas:baja_divisa', args=[self.divisa.pk]), {'causa': 'Sin operaciones'})

        registro = self._unico_registro(tipo_recurso=RegistroActividad.RECURSO_DIVISA)
        self.assertEqual(registro.accion, RegistroActividad.ACCION_BAJA)
        self.assertEqual(_cambios(registro), {'activa': ('Sí', 'No')})

    def test_actualizar_tasa_registra_la_tasa_anterior_y_la_nueva(self):
        """Cada actualización de tasas se compara con la cotización que reemplaza."""
        self.client.post(
            reverse('divisas:actualizar_cotizacion', args=[self.divisa.pk]),
            {'tasa_compra': '7350.00', 'tasa_venta': '7400.00'},
        )

        registro = self._unico_registro(tipo_recurso=RegistroActividad.RECURSO_TASA)
        self.assertEqual(registro.accion, RegistroActividad.ACCION_MODIFICACION)
        self.assertEqual(registro.recurso_descripcion, 'Tasa de cambio USD')
        self.assertEqual(_cambios(registro), {'tasa_compra': ('7300.00', '7350.00')})

    def test_configurar_parametros_de_operacion_registra_alta_y_modificacion(self):
        """La primera configuración de vigencia es un alta; las siguientes, modificaciones."""
        url = reverse('divisas:configuracion_vigencia')
        self.client.post(url, {
            'calculo_vigencia_segundos': '120', 'confirmacion_vigencia_segundos': '900', 'pago_vigencia_segundos': '1800',
        })
        self.client.post(url, {
            'calculo_vigencia_segundos': '300', 'confirmacion_vigencia_segundos': '900', 'pago_vigencia_segundos': '1800',
        })

        alta, modificacion = RegistroActividad.objects.filter(
            tipo_recurso=RegistroActividad.RECURSO_PARAMETRO,
        ).order_by('pk')
        self.assertEqual(alta.accion, RegistroActividad.ACCION_ALTA)
        self.assertEqual(alta.recurso_id, str(ConfiguracionVigencia.objects.get().pk))
        self.assertEqual(modificacion.accion, RegistroActividad.ACCION_MODIFICACION)
        self.assertEqual(_cambios(modificacion), {'calculo_vigencia_segundos': ('120', '300')})

    def test_modificar_comision_registra_el_porcentaje_anterior(self):
        """La comisión de un segmento también es un parámetro de operación auditado."""
        ConfiguracionComision.objects.create(segmento='VIP', porcentaje=Decimal('1.500'))

        self.client.post(reverse('divisas:actualizar_comision', args=['VIP']), {'porcentaje': '2.000'})

        registro = self._unico_registro(tipo_recurso=RegistroActividad.RECURSO_PARAMETRO)
        self.assertEqual(registro.recurso_descripcion, 'Comisión del segmento VIP')
        self.assertEqual(_cambios(registro), {'porcentaje': ('1.500', '2.000')})

    @patch('apps.users.views.actualizar_usuario_en_keycloak')
    def test_modificar_y_dar_de_baja_un_usuario(self, _mock_keycloak):
        """Editar los datos de un usuario y darlo de baja quedan registrados por separado."""
        objetivo = User.objects.create_user(username='operador', first_name='Op', email='op@ge.com')

        self.client.post(reverse('editar_usuario', args=[objetivo.pk]), {'first_name': 'Oscar', 'last_name': 'Pérez'})
        self.client.post(reverse('baja_usuario', args=[objetivo.pk]), {'causa': 'Ya no trabaja acá'})

        modificacion, baja = RegistroActividad.objects.filter(
            tipo_recurso=RegistroActividad.RECURSO_USUARIO,
        ).order_by('pk')
        self.assertEqual(modificacion.accion, RegistroActividad.ACCION_MODIFICACION)
        self.assertEqual(modificacion.recurso_descripcion, 'operador')
        self.assertEqual(_cambios(modificacion), {'first_name': ('Op', 'Oscar'), 'last_name': ('', 'Pérez')})
        self.assertEqual(modificacion.cambios[0]['etiqueta'], 'Nombre')
        self.assertEqual(baja.accion, RegistroActividad.ACCION_BAJA)
        self.assertEqual(_cambios(baja), {'is_active': ('Sí', 'No')})

    def test_editar_roles_registra_los_roles_anteriores_y_nuevos(self):
        """Los roles viven en Keycloak: se registran comparando los roles antes y después de la vista."""
        objetivo = User.objects.create_user(username='cajero1', email='cajero1@ge.com')
        # Orden de las consultas: auditoría (antes), vista, auditoría (después).
        roles = [['cajero'], ['cajero'], ['admin', 'cajero']]

        with patch('apps.users.views.obtener_roles_disponibles', return_value=['admin', 'cajero']), \
                patch('apps.users.views.obtener_roles_de_usuario', side_effect=roles), \
                patch('apps.users.views.actualizar_roles_de_usuario'):
            response = self.client.post(reverse('editar_roles', args=[objetivo.pk]), {'roles': ['admin', 'cajero']})

        self.assertRedirects(response, reverse('lista_usuarios'), fetch_redirect_response=False)
        registro = self._unico_registro(tipo_recurso=RegistroActividad.RECURSO_ROL)
        self.assertEqual(registro.accion, RegistroActividad.ACCION_MODIFICACION)
        self.assertEqual(registro.recurso_id, str(objetivo.pk))
        self.assertEqual(registro.recurso_descripcion, 'Roles de cajero1')
        self.assertEqual(_cambios(registro), {'roles': ('cajero', 'admin, cajero')})

    def test_falla_de_keycloak_al_auditar_roles_no_interrumpe_la_edicion(self):
        """Si Keycloak no responde a la auditoría, la vista sigue su curso igual que sin ella."""
        objetivo = User.objects.create_user(username='cajero2', email='cajero2@ge.com')

        with patch('apps.users.views.obtener_roles_de_usuario', side_effect=Exception('timeout')):
            response = self.client.post(reverse('editar_roles', args=[objetivo.pk]), {'roles': ['admin']})

        self.assertRedirects(response, reverse('lista_usuarios'), fetch_redirect_response=False)
        self.assertFalse(RegistroActividad.objects.exists())

    def test_sincronizacion_de_usuarios_al_listar_no_es_una_accion(self):
        """Los guardados durante un GET (sincronizar con Keycloak al listar) no se registran."""
        objetivo = User.objects.create_user(username='sincronizado', first_name='Viejo')

        def sincronizar():
            """Simula que la sincronización trae un nombre distinto desde Keycloak."""
            objetivo.first_name = 'Nuevo'
            objetivo.save()
            return {}

        with patch('apps.users.views.sincronizar_usuarios_desde_keycloak', side_effect=sincronizar):
            self.client.get(reverse('lista_usuarios'))

        objetivo.refresh_from_db()
        self.assertEqual(objetivo.first_name, 'Nuevo')
        self.assertFalse(RegistroActividad.objects.exists())

    def test_cambios_fuera_de_una_request_no_se_registran(self):
        """Sin un usuario que realice la acción (shell, migraciones, comandos), no hay nada que auditar."""
        self.divisa.nombre = 'Dólar americano'
        self.divisa.save()

        self.assertFalse(RegistroActividad.objects.exists())

    def test_post_anonimo_no_se_registra(self):
        """Una request sin usuario autenticado no tiene a quién atribuirle la acción."""
        self.client.logout()

        self.client.post(reverse('divisas:crear_divisa'), {'codigo': 'BRL', 'nombre': 'Real', 'simbolo': 'R$'})

        self.assertFalse(Divisa.objects.filter(codigo='BRL').exists())
        self.assertFalse(RegistroActividad.objects.exists())


def _crear_registro(usuario, accion=RegistroActividad.ACCION_MODIFICACION, fecha=None, descripcion='USD - Dólar'):
    """Crea un registro de actividad, opcionalmente con una fecha determinada."""
    if fecha is None:
        return registrar_actividad(usuario, accion, RegistroActividad.RECURSO_DIVISA, 1, descripcion, [])
    with patch('django.utils.timezone.now', return_value=fecha):
        return registrar_actividad(usuario, accion, RegistroActividad.RECURSO_DIVISA, 1, descripcion, [])


class ListadoTest(TestCase):
    """Criterio 2: listado paginado, de la actividad más reciente a la más antigua."""

    def setUp(self):
        """Prepara un administrador logueado."""
        self.admin = User.objects.create_user(username='admin-listado')
        _loguear(self.client, self.admin, ['admin'])
        self.url = reverse('auditoria:registro_actividades')

    def test_lista_de_la_mas_reciente_a_la_mas_antigua(self):
        """La primera fila es la actividad más reciente."""
        tz = timezone.get_current_timezone()
        vieja = _crear_registro(self.admin, fecha=datetime(2026, 1, 1, 10, 0, tzinfo=tz), descripcion='Vieja')
        nueva = _crear_registro(self.admin, fecha=datetime(2026, 6, 1, 10, 0, tzinfo=tz), descripcion='Nueva')

        response = self.client.get(self.url)

        self.assertEqual(list(response.context['registros']), [nueva, vieja])
        self.assertContains(response, 'Nueva')

    def test_pagina_de_a_veinte_registros(self):
        """Con 25 registros, la primera página muestra 20 y la segunda los 5 restantes."""
        for _ in range(25):
            _crear_registro(self.admin)

        primera = self.client.get(self.url)
        segunda = self.client.get(self.url, {'page': 2})

        self.assertTrue(primera.context['is_paginated'])
        self.assertEqual(len(primera.context['registros']), 20)
        self.assertEqual(len(segunda.context['registros']), 5)
        self.assertContains(primera, 'Página 1 de 2')

    def test_muestra_quien_que_registro_y_que_cambio(self):
        """Cada fila muestra el usuario, la acción, el registro y los valores anterior y nuevo."""
        registrar_actividad(
            self.admin, RegistroActividad.ACCION_MODIFICACION, RegistroActividad.RECURSO_DIVISA, 1, 'USD - Dólar',
            [{'campo': 'nombre', 'etiqueta': 'Nombre', 'anterior': 'Dólar', 'nuevo': 'Dólar estadounidense'}],
        )

        response = self.client.get(self.url)

        self.assertContains(response, 'admin-listado')
        self.assertContains(response, 'Modificación')
        self.assertContains(response, 'USD - Dólar')
        self.assertContains(response, 'Dólar estadounidense')


class FiltrosTest(TestCase):
    """Criterio 3: filtro por usuario, tipo de acción y rango de fechas."""

    def setUp(self):
        """Prepara dos usuarios con actividades de distintos tipos y fechas."""
        tz = timezone.get_current_timezone()
        self.admin = User.objects.create_user(username='admin-filtros')
        self.otro = User.objects.create_user(username='otro-admin')
        _loguear(self.client, self.admin, ['admin'])
        self.url = reverse('auditoria:registro_actividades')
        self.alta_enero = _crear_registro(
            self.admin, RegistroActividad.ACCION_ALTA, datetime(2026, 1, 15, 9, 0, tzinfo=tz),
        )
        self.baja_marzo = _crear_registro(
            self.otro, RegistroActividad.ACCION_BAJA, datetime(2026, 3, 10, 9, 0, tzinfo=tz),
        )
        # 23:30 local del 31/05 es 1/06 en UTC: el filtro debe usar el día local.
        self.modificacion_mayo = _crear_registro(
            self.otro, RegistroActividad.ACCION_MODIFICACION, datetime(2026, 5, 31, 23, 30, tzinfo=tz),
        )

    def _filtrar(self, **parametros):
        """Devuelve los registros que lista la vista con los parámetros dados."""
        return list(self.client.get(self.url, parametros).context['registros'])

    def test_filtra_por_usuario(self):
        """Solo muestra las actividades del usuario elegido."""
        self.assertEqual(self._filtrar(usuario=self.otro.pk), [self.modificacion_mayo, self.baja_marzo])

    def test_filtra_por_tipo_de_accion(self):
        """Solo muestra las actividades del tipo de acción elegido."""
        self.assertEqual(self._filtrar(accion=RegistroActividad.ACCION_BAJA), [self.baja_marzo])

    def test_filtra_por_rango_de_fechas_inclusive(self):
        """El rango incluye ambos extremos y se compara contra el día local."""
        self.assertEqual(
            self._filtrar(fecha_desde='2026-03-10', fecha_hasta='2026-05-31'),
            [self.modificacion_mayo, self.baja_marzo],
        )
        self.assertEqual(self._filtrar(fecha_hasta='2026-01-15'), [self.alta_enero])

    def test_combina_filtros(self):
        """Los filtros se aplican todos juntos."""
        self.assertEqual(
            self._filtrar(usuario=self.otro.pk, accion=RegistroActividad.ACCION_BAJA, fecha_desde='2026-04-01'),
            [],
        )

    def test_rango_invertido_muestra_error_y_ningun_resultado(self):
        """Un rango que termina antes de empezar se explica en vez de mostrar resultados que no se pidieron."""
        response = self.client.get(self.url, {'fecha_desde': '2026-06-01', 'fecha_hasta': '2026-01-01'})

        self.assertEqual(list(response.context['registros']), [])
        self.assertContains(response, 'no puede ser posterior')

    def test_el_selector_ofrece_solo_usuarios_con_actividad(self):
        """Un usuario sin ninguna actividad no aparece como opción del filtro."""
        User.objects.create_user(username='sin-actividad')

        opciones = self.client.get(self.url).context['filtros'].fields['usuario'].queryset

        self.assertEqual(set(opciones), {self.admin, self.otro})


class InmutabilidadTest(TestCase):
    """Criterio 4: un registro de actividad no se puede modificar ni eliminar."""

    def setUp(self):
        """Prepara un administrador y un registro de actividad suyo."""
        self.admin = User.objects.create_user(username='admin-inmutable', first_name='Ines', last_name='Mutable')
        self.registro = _crear_registro(self.admin)

    def test_no_se_puede_modificar_una_instancia(self):
        """Volver a guardar un registro existente se rechaza y la base no cambia."""
        self.registro.recurso_descripcion = 'Alterado'

        with self.assertRaises(ValidationError):
            self.registro.save()

        self.registro.refresh_from_db()
        self.assertEqual(self.registro.recurso_descripcion, 'USD - Dólar')

    def test_no_se_puede_eliminar_una_instancia(self):
        """Eliminar un registro se rechaza."""
        with self.assertRaises(ValidationError):
            self.registro.delete()

        self.assertTrue(RegistroActividad.objects.filter(pk=self.registro.pk).exists())

    def test_no_se_puede_modificar_ni_eliminar_en_forma_masiva(self):
        """``QuerySet.update`` y ``QuerySet.delete`` tampoco pueden alterar el registro."""
        with self.assertRaises(ValidationError):
            RegistroActividad.objects.update(recurso_descripcion='Alterado')
        with self.assertRaises(ValidationError):
            RegistroActividad.objects.all().delete()

        self.assertEqual(RegistroActividad.objects.get().recurso_descripcion, 'USD - Dólar')

    def test_la_vista_no_acepta_metodos_que_modifiquen(self):
        """Ni siquiera un administrador puede enviar un POST, PUT o DELETE al registro."""
        _loguear(self.client, self.admin, ['admin'])
        url = reverse('auditoria:registro_actividades')

        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(self.client.put(url).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertTrue(RegistroActividad.objects.filter(pk=self.registro.pk).exists())

    def test_eliminar_al_usuario_conserva_el_registro_con_su_nombre(self):
        """Si se elimina el usuario que realizó la acción, el registro queda con el nombre que tenía."""
        self.admin.delete()

        self.registro.refresh_from_db()
        self.assertIsNone(self.registro.usuario)
        self.assertEqual(self.registro.usuario_nombre, 'Ines Mutable')


class AccesoTest(TestCase):
    """Criterio 5: solo un administrador accede al registro de actividades."""

    def setUp(self):
        """Prepara un usuario logueado y la URL del registro."""
        self.usuario = User.objects.create_user(username='usuario-acceso')
        self.url = reverse('auditoria:registro_actividades')

    def test_administrador_accede_y_ve_el_enlace_en_el_menu(self):
        """Un administrador ve el registro y su acceso en el menú lateral."""
        _loguear(self.client, self.usuario, ['admin'])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{self.url}"')

    def test_usuarios_sin_rol_de_administrador_reciben_acceso_denegado(self):
        """Cualquier rol que no sea 'admin', incluso los de gestión, recibe un 403."""
        for roles in (['analista_cambiario'], ['cajero'], ['cliente'], ['gestion_roles', 'usuarios'], []):
            with self.subTest(roles=roles):
                _loguear(self.client, self.usuario, roles)

                self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_usuario_anonimo_es_redirigido_al_login(self):
        """Sin sesión iniciada, se redirige al login en vez de mostrar el registro."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('oidc_authentication_init'), response['Location'])
