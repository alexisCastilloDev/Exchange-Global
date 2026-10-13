"""Modelos de sipap-sim: proveedores de pago, cuentas y transferencias.

Representa, de forma simplificada, la red bancaria y de billeteras
digitales que la HU "Pago por transferencia bancaria vía SIPAP" de Global
Exchange necesita para probarse de punta a punta sin acceso a la API real
de SIPAP (que no tiene un sandbox público).
"""

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone


class ProveedorPago(models.Model):
    """Un banco o una billetera digital: quien emite las cuentas de los clientes de prueba.

    Se modelan con la misma clase a propósito: para la "banca en línea"
    simulada (``core.views.elegir_cuenta_view``) y para Global Exchange,
    pagar desde una cuenta bancaria o desde una billetera es el mismo
    flujo (elegir una cuenta propia y aprobar la transferencia); lo único
    que cambia es qué tipo de proveedor la emitió.
    """

    TIPO_BANCO = 'BANCO'
    TIPO_BILLETERA = 'BILLETERA'
    TIPO_CHOICES = [
        (TIPO_BANCO, 'Banco'),
        (TIPO_BILLETERA, 'Billetera digital'),
    ]

    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)

    class Meta:
        """Ordena por tipo y nombre, para que la 'banca en línea' agrupe bancos y billeteras."""
        ordering = ['tipo', 'nombre']
        verbose_name = 'Proveedor de pago'
        verbose_name_plural = 'Proveedores de pago'

    def __str__(self):
        """Identifica el proveedor por su nombre y tipo."""
        return f'{self.nombre} ({self.get_tipo_display()})'


class Cuenta(models.Model):
    """Una cuenta bancaria o de billetera: de un cliente de prueba, o de la casa de cambio."""

    MONEDA_CHOICES = [('PYG', 'PYG'), ('USD', 'USD')]

    numero = models.CharField(max_length=20, unique=True, verbose_name='Número de cuenta')
    proveedor = models.ForeignKey(
        ProveedorPago, on_delete=models.PROTECT, related_name='cuentas',
    )
    titular = models.CharField(max_length=150)
    documento = models.CharField(max_length=20, verbose_name='CI o RUC del titular')
    moneda = models.CharField(max_length=3, choices=MONEDA_CHOICES)
    saldo = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    es_cuenta_casa_de_cambio = models.BooleanField(
        default=False,
        verbose_name='¿Es la cuenta de la casa de cambio?',
        help_text=(
            'La cuenta destino de cualquier solicitud de cobro: hay una '
            'por moneda, cargada en la migración de datos iniciales.'
        ),
    )

    class Meta:
        """Ordena por proveedor y número, para que la 'banca en línea' se vea prolija."""
        ordering = ['proveedor__nombre', 'numero']
        verbose_name = 'Cuenta'
        verbose_name_plural = 'Cuentas'

    def __str__(self):
        """Identifica la cuenta por su número, proveedor y titular."""
        return f'{self.numero} ({self.proveedor.nombre}, {self.titular})'


def _generar_id_transferencia():
    """Genera un id con el formato que espera Global Exchange (``SPI-AAAAMMDD-XXXXXX``)."""
    return f'SPI-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}'


class Transferencia(models.Model):
    """Una solicitud de cobro y la transferencia en la que se resuelve.

    Nace "Pendiente" al recibir un ``POST /api/solicitudes-cobro/``. Quien
    pide el cobro (Global Exchange) ya sabe, en ese momento, con qué
    cuenta va a pagar el cliente — es el método de pago que eligió en su
    propia pantalla, ya validado contra esta misma base al registrarlo
    (ver ``apps.clientes.validacion_sipap`` del lado de Global Exchange) —
    así que la identifica ahí mismo (``cuenta_sugerida``), en vez de
    dejar que la "banca en línea" (``core.views.elegir_cuenta_view``)
    muestre una lista de todas las cuentas del sistema para elegir. El
    cliente tampoco elige el monto: se acredita siempre el solicitado.
    Recién al aprobar se completa ``cuenta_origen`` (siempre la misma que
    ``cuenta_sugerida``).
    """

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_ACREDITADA = 'acreditada'
    ESTADO_RECHAZADA = 'rechazada'
    ESTADO_VENCIDA = 'vencida'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_ACREDITADA, 'Acreditada'),
        (ESTADO_RECHAZADA, 'Rechazada'),
        (ESTADO_VENCIDA, 'Vencida'),
    ]

    id = models.CharField(max_length=40, primary_key=True, default=_generar_id_transferencia, editable=False)
    cuenta_sugerida = models.ForeignKey(
        Cuenta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='transferencias_sugeridas',
        verbose_name='Cuenta de origen identificada por quien pidió el cobro',
        help_text=(
            'La completa crear_solicitud_cobro a partir de '
            '"cuenta_origen_numero"/"cuenta_origen_documento", si vienen en '
            'la solicitud. La "banca en línea" la usa directamente, en vez '
            'de pedirle al cliente que elija entre todas las cuentas del '
            'sistema.'
        ),
    )
    cuenta_origen = models.ForeignKey(
        Cuenta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='transferencias_enviadas',
        verbose_name='Cuenta de origen (confirmada al aprobar)',
    )
    cuenta_destino = models.ForeignKey(
        Cuenta, on_delete=models.PROTECT, related_name='transferencias_recibidas',
        verbose_name='Cuenta destino (de la casa de cambio)',
    )
    monto_solicitado = models.DecimalField(max_digits=18, decimal_places=2)
    monto_acreditado = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        help_text='El monto que se acreditó al aprobar: siempre igual al solicitado (la "banca en línea" no deja cambiarlo).',
    )
    moneda = models.CharField(max_length=3)
    referencia = models.CharField(max_length=60, db_index=True, help_text='La referencia que mandó Global Exchange.')
    url_retorno = models.URLField(max_length=500, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    creado_en = models.DateTimeField(auto_now_add=True)
    resuelto_en = models.DateTimeField(null=True, blank=True)
    vence_en = models.DateTimeField()

    class Meta:
        """Ordena las transferencias más nuevas primero."""
        ordering = ['-creado_en']
        verbose_name = 'Transferencia'
        verbose_name_plural = 'Transferencias'

    def __str__(self):
        """Identifica la transferencia por su id y su estado."""
        return f'Transferencia {self.id} ({self.get_estado_display()})'

    @property
    def esta_vencida(self):
        """Indica si la transferencia sigue pendiente pero ya pasó su plazo."""
        return self.estado == self.ESTADO_PENDIENTE and timezone.now() >= self.vence_en

    def marcar_vencida_si_corresponde(self):
        """Persiste el paso a 'Vencida' si corresponde (mismo patrón perezoso que Global Exchange)."""
        if self.esta_vencida:
            self.estado = self.ESTADO_VENCIDA
            self.resuelto_en = timezone.now()
            self.save(update_fields=['estado', 'resuelto_en'])
            return True
        return False
