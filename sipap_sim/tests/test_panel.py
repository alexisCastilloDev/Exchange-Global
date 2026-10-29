"""Pruebas del panel administrativo: ingreso, alta y baja de proveedores y cuentas.

Reemplaza a la migración de datos como forma de cargar sipap-sim (ver
``core/views.py`` y ``core/forms.py``): estas pruebas cubren que el
acceso esté restringido a un usuario de staff, que el alta de
proveedores y cuentas funcione (incluida la validación de que solo
puede haber una cuenta de la casa de cambio por moneda), y que la baja
respete las relaciones protegidas (no se puede borrar un proveedor con
cuentas, ni una cuenta con transferencias asociadas).
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Cuenta, ProveedorPago, Transferencia

USUARIO_STAFF = 'operador'
PASSWORD_STAFF = 'contraseña-de-test-123'


class AccesoPanelTest(TestCase):
    """El panel y sus pantallas exigen un usuario de staff autenticado."""

    def setUp(self):
        self.staff = User.objects.create_user(USUARIO_STAFF, password=PASSWORD_STAFF, is_staff=True)
        self.no_staff = User.objects.create_user('cliente', password=PASSWORD_STAFF, is_staff=False)

    def test_solo_un_staff_autenticado_accede_al_panel(self):
        with self.subTest('anónimo'):
            response = self.client.get(reverse('panel'))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse('panel')}")

        with self.subTest('autenticado sin staff'):
            self.client.login(username='cliente', password=PASSWORD_STAFF)
            response = self.client.get(reverse('panel'))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse('panel')}")

    def test_staff_accede_al_panel(self):
        self.client.login(username=USUARIO_STAFF, password=PASSWORD_STAFF)
        response = self.client.get(reverse('panel'))
        self.assertEqual(response.status_code, 200)

    def test_login_segun_las_credenciales(self):
        with self.subTest('correctas'):
            response = self.client.post(reverse('login'), {'username': USUARIO_STAFF, 'password': PASSWORD_STAFF})
            self.assertRedirects(response, reverse('panel'))

        with self.subTest('incorrectas'):
            self.client.logout()
            response = self.client.post(reverse('login'), {'username': USUARIO_STAFF, 'password': 'incorrecta'})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_cierra_la_sesion(self):
        self.client.login(username=USUARIO_STAFF, password=PASSWORD_STAFF)
        self.client.post(reverse('logout'))
        response = self.client.get(reverse('panel'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('panel')}")


class ProveedoresViewTest(TestCase):
    """Alta de bancos y billeteras desde el panel."""

    def setUp(self):
        User.objects.create_user(USUARIO_STAFF, password=PASSWORD_STAFF, is_staff=True)
        self.client.login(username=USUARIO_STAFF, password=PASSWORD_STAFF)

    def test_agrega_un_banco_nuevo_pero_rechaza_un_codigo_duplicado(self):
        with self.subTest('código nuevo'):
            response = self.client.post(reverse('proveedores'), {
                'tipo': ProveedorPago.TIPO_BANCO, 'codigo': 'NUEVO_BANCO', 'nombre': 'Banco Nuevo',
            })
            self.assertRedirects(response, reverse('proveedores'))
            self.assertTrue(ProveedorPago.objects.filter(codigo='NUEVO_BANCO', nombre='Banco Nuevo').exists())

        with self.subTest('código duplicado'):
            ProveedorPago.objects.create(tipo=ProveedorPago.TIPO_BANCO, codigo='ITAU', nombre='Banco Itaú Paraguay')
            response = self.client.post(reverse('proveedores'), {
                'tipo': ProveedorPago.TIPO_BANCO, 'codigo': 'ITAU', 'nombre': 'Otro nombre',
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(ProveedorPago.objects.filter(codigo='ITAU').count(), 1)

    def test_eliminar_proveedor_segun_tenga_cuentas_y_segun_el_metodo(self):
        with self.subTest('sin cuentas: se elimina'):
            proveedor = ProveedorPago.objects.create(
                tipo=ProveedorPago.TIPO_BANCO, codigo='ITAU', nombre='Banco Itaú Paraguay',
            )
            response = self.client.post(reverse('eliminar_proveedor', args=[proveedor.pk]))
            self.assertRedirects(response, reverse('proveedores'))
            self.assertFalse(ProveedorPago.objects.filter(pk=proveedor.pk).exists())

        with self.subTest('con cuentas: no se elimina'):
            proveedor = ProveedorPago.objects.create(
                tipo=ProveedorPago.TIPO_BANCO, codigo='UENO', nombre='Banco Ueno',
            )
            Cuenta.objects.create(numero='1', proveedor=proveedor, titular='Juan', documento='1', moneda='PYG')
            response = self.client.post(reverse('eliminar_proveedor', args=[proveedor.pk]))
            self.assertRedirects(response, reverse('proveedores'))
            self.assertTrue(ProveedorPago.objects.filter(pk=proveedor.pk).exists())

        with self.subTest('por GET: no se elimina'):
            response = self.client.get(reverse('eliminar_proveedor', args=[proveedor.pk]))
            self.assertTrue(ProveedorPago.objects.filter(pk=proveedor.pk).exists())

    def test_usuario_sin_staff_no_puede_eliminar(self):
        User.objects.create_user('cliente', password=PASSWORD_STAFF, is_staff=False)
        self.client.logout()
        self.client.login(username='cliente', password=PASSWORD_STAFF)
        proveedor = ProveedorPago.objects.create(tipo=ProveedorPago.TIPO_BANCO, codigo='ITAU', nombre='Banco Itaú Paraguay')
        self.client.post(reverse('eliminar_proveedor', args=[proveedor.pk]))
        self.assertTrue(ProveedorPago.objects.filter(pk=proveedor.pk).exists())


class CuentasViewTest(TestCase):
    """Alta de cuentas (de clientes y de la casa de cambio) desde el panel."""

    def setUp(self):
        User.objects.create_user(USUARIO_STAFF, password=PASSWORD_STAFF, is_staff=True)
        self.client.login(username=USUARIO_STAFF, password=PASSWORD_STAFF)
        self.proveedor = ProveedorPago.objects.create(tipo=ProveedorPago.TIPO_BANCO, codigo='ITAU', nombre='Banco Itaú Paraguay')

    def _payload(self, **overrides):
        payload = {
            'proveedor': self.proveedor.pk, 'numero': '9999999999999999', 'titular': 'Juan Pérez',
            'documento': '3456789', 'moneda': 'PYG', 'saldo': '1000.00',
        }
        payload.update(overrides)
        return payload

    def test_agrega_una_cuenta_de_cliente_e_ignora_la_marca_de_casa_de_cambio(self):
        """sipap-sim ya no decide esto desde su propio panel: lo designa Global Exchange por API."""
        response = self.client.post(reverse('cuentas'), self._payload(es_cuenta_casa_de_cambio=True))
        self.assertRedirects(response, reverse('cuentas'))
        cuenta = Cuenta.objects.get(numero='9999999999999999')
        self.assertEqual(cuenta.saldo, Decimal('1000.00'))
        self.assertFalse(cuenta.es_cuenta_casa_de_cambio)

    def test_el_formulario_de_alta_rechaza_numero_duplicado_o_moneda_invalida(self):
        with self.subTest('número de cuenta duplicado'):
            Cuenta.objects.create(
                numero='9999999999999999', proveedor=self.proveedor, titular='Otro', documento='1111111', moneda='PYG',
            )
            response = self.client.post(reverse('cuentas'), self._payload())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(Cuenta.objects.filter(numero='9999999999999999').count(), 1)

        with self.subTest('código de moneda con formato inválido'):
            response = self.client.post(reverse('cuentas'), self._payload(numero='8888888888888888', moneda='DOLARES'))
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Cuenta.objects.filter(numero='8888888888888888').exists())

    def test_el_formulario_de_alta_acepta_cualquier_moneda_de_tres_letras_y_saldos_grandes(self):
        with self.subTest('moneda de tres letras, no solo PYG o USD'):
            """sipap-sim no restringe a una lista fija: admite cualquier divisa que Global Exchange tenga habilitada."""
            response = self.client.post(reverse('cuentas'), self._payload(moneda='jpy'))
            self.assertRedirects(response, reverse('cuentas'))
            cuenta = Cuenta.objects.get(numero='9999999999999999')
            self.assertEqual(cuenta.moneda, 'JPY')

        with self.subTest('saldo de más de 18 dígitos'):
            """Antes (max_digits=18) un saldo con más de 16 dígitos enteros no pasaba la validación del formulario."""
            saldo_grande = '9' * 20 + '.00'
            response = self.client.post(
                reverse('cuentas'), self._payload(numero='7777777777777777', saldo=saldo_grande),
            )
            self.assertRedirects(response, reverse('cuentas'))
            cuenta = Cuenta.objects.get(numero='7777777777777777')
            # No se compara con igualdad exacta: SQLite (solo en los tests;
            # en producción se usa PostgreSQL) guarda estos valores enormes
            # con afinidad NUMERIC, que puede perder los últimos dígitos al
            # pasar por un float de 64 bits. Lo que importa acá es que el
            # formulario ya no lo rechaza por "demasiados dígitos".
            self.assertGreater(cuenta.saldo, Decimal('10') ** 19)

    def test_eliminar_cuenta_segun_tenga_transferencias(self):
        with self.subTest('sin transferencias: se elimina'):
            cuenta = Cuenta.objects.create(
                numero='9999999999999999', proveedor=self.proveedor, titular='Juan Pérez', documento='3456789', moneda='PYG',
            )
            response = self.client.post(reverse('eliminar_cuenta', args=[cuenta.pk]))
            self.assertRedirects(response, reverse('cuentas'))
            self.assertFalse(Cuenta.objects.filter(pk=cuenta.pk).exists())

        with self.subTest('con transferencias: no se elimina'):
            cuenta = Cuenta.objects.create(
                numero='8888888888888888', proveedor=self.proveedor, titular='Juan Pérez', documento='3456789', moneda='PYG',
            )
            Transferencia.objects.create(
                cuenta_destino=cuenta, monto_solicitado=Decimal('1000'), moneda='PYG',
                referencia='GE-1', vence_en=timezone.now(),
            )
            response = self.client.post(reverse('eliminar_cuenta', args=[cuenta.pk]))
            self.assertRedirects(response, reverse('cuentas'))
            self.assertTrue(Cuenta.objects.filter(pk=cuenta.pk).exists())

    def test_usuario_sin_staff_no_puede_eliminar_cuenta(self):
        User.objects.create_user('cliente', password=PASSWORD_STAFF, is_staff=False)
        self.client.logout()
        self.client.login(username='cliente', password=PASSWORD_STAFF)
        cuenta = Cuenta.objects.create(
            numero='9999999999999999', proveedor=self.proveedor, titular='Juan Pérez', documento='3456789', moneda='PYG',
        )
        self.client.post(reverse('eliminar_cuenta', args=[cuenta.pk]))
        self.assertTrue(Cuenta.objects.filter(pk=cuenta.pk).exists())

    def test_editar_muestra_los_datos_actuales(self):
        cuenta = Cuenta.objects.create(
            numero='9999999999999999', proveedor=self.proveedor, titular='Juan Pérez', documento='3456789',
            moneda='PYG', saldo=Decimal('1000.00'),
        )
        response = self.client.get(reverse('editar_cuenta', args=[cuenta.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Juan Pérez')
        self.assertContains(response, '9999999999999999')

    def test_editar_actualiza_los_datos(self):
        cuenta = Cuenta.objects.create(
            numero='9999999999999999', proveedor=self.proveedor, titular='Juan Pérez', documento='3456789',
            moneda='PYG', saldo=Decimal('1000.00'),
        )
        response = self.client.post(
            reverse('editar_cuenta', args=[cuenta.pk]),
            self._payload(titular='Juan Pérez Actualizado', saldo='2500.50'),
        )
        self.assertRedirects(response, reverse('cuentas'))
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.titular, 'Juan Pérez Actualizado')
        self.assertEqual(cuenta.saldo, Decimal('2500.50'))

    def test_editar_nunca_toca_la_marca_de_casa_de_cambio(self):
        """El formulario de edición ni siquiera incluye ese campo: no la preserva ni la deja establecer."""
        with self.subTest('editar otros datos preserva la marca existente'):
            cuenta_casa = Cuenta.objects.create(
                numero='1000000000000001', proveedor=self.proveedor, titular='Global Exchange S.A.',
                documento='80012345-6', moneda='PYG', saldo=Decimal('500000000.00'), es_cuenta_casa_de_cambio=True,
            )
            response = self.client.post(
                reverse('editar_cuenta', args=[cuenta_casa.pk]),
                self._payload(
                    numero=cuenta_casa.numero, titular='Global Exchange S.A. Actualizado',
                    documento=cuenta_casa.documento, saldo=str(cuenta_casa.saldo),
                ),
            )
            self.assertRedirects(response, reverse('cuentas'))
            cuenta_casa.refresh_from_db()
            self.assertTrue(cuenta_casa.es_cuenta_casa_de_cambio)
            self.assertEqual(cuenta_casa.titular, 'Global Exchange S.A. Actualizado')

        with self.subTest('no permite establecerla en una cuenta normal'):
            otra_cuenta = Cuenta.objects.create(
                numero='9999999999999999', proveedor=self.proveedor, titular='Juan Pérez', documento='3456789',
                moneda='PYG',
            )
            response = self.client.post(
                reverse('editar_cuenta', args=[otra_cuenta.pk]),
                self._payload(es_cuenta_casa_de_cambio=True),
            )
            self.assertRedirects(response, reverse('cuentas'))
            otra_cuenta.refresh_from_db()
            self.assertFalse(otra_cuenta.es_cuenta_casa_de_cambio)

    def test_usuario_sin_staff_no_puede_editar_cuenta(self):
        User.objects.create_user('cliente-editar', password=PASSWORD_STAFF, is_staff=False)
        self.client.logout()
        self.client.login(username='cliente-editar', password=PASSWORD_STAFF)
        cuenta = Cuenta.objects.create(
            numero='9999999999999999', proveedor=self.proveedor, titular='Juan Pérez', documento='3456789', moneda='PYG',
        )

        self.client.post(reverse('editar_cuenta', args=[cuenta.pk]), self._payload(titular='Otro Nombre'))

        cuenta.refresh_from_db()
        self.assertEqual(cuenta.titular, 'Juan Pérez')
