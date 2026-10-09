"""Modelos de caja: apertura de turno y saldo inicial por moneda."""

import uuid

from django.conf import settings
from django.db import models

from apps.divisas.models import Divisa


class Caja(models.Model):
    """Representa el turno de caja abierto por un cajero.

    Implementa la HU "Apertura de Caja": se crea siempre en estado
    "Abierta", asociada al cajero que la abre y a la fecha y hora de
    apertura (``abierta_en``). El cierre, las operaciones, el arqueo y los
    movimientos de una caja son HU futuras que todavía no existen en este
    código; por eso ``estado`` ya contempla "Cerrada" y ``cerrada_en`` desde
    ahora (para no tener que migrar el modelo de nuevo más adelante), pero
    ninguna vista de este archivo los usa todavía.
    """

    ESTADO_ABIERTA = 'ABIERTA'
    ESTADO_CERRADA = 'CERRADA'
    ESTADO_CHOICES = [
        (ESTADO_ABIERTA, 'Abierta'),
        (ESTADO_CERRADA, 'Cerrada'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cajas',
        verbose_name='Cajero',
    )
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_ABIERTA)
    abierta_en = models.DateTimeField(auto_now_add=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Define el orden y las etiquetas administrativas de las cajas."""
        verbose_name = 'Caja'
        verbose_name_plural = 'Cajas'
        ordering = ['-abierta_en']
        constraints = [
            # Un mismo cajero no puede tener dos cajas "Abierta" a la vez
            # (Criterio 2): refuerza a nivel de base lo que la vista ya
            # valida, para que una carrera entre dos pestañas no lo saltee.
            models.UniqueConstraint(
                fields=['usuario'],
                condition=models.Q(estado='ABIERTA'),
                name='una_sola_caja_abierta_por_cajero',
            ),
        ]

    def __str__(self):
        """Identifica la caja por su cajero y su estado."""
        return f'Caja de {self.usuario} ({self.get_estado_display()})'


class SaldoInicialCaja(models.Model):
    """Saldo inicial de una moneda puntual, registrado al abrir una caja.

    Una fila por cada divisa activa que el cajero contó al momento de abrir
    (incluido PYG, si existe como divisa activa): el inventario completo de
    la apertura es la colección de estas filas asociadas a una ``Caja``.
    """

    caja = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name='saldos_iniciales')
    divisa = models.ForeignKey(Divisa, on_delete=models.PROTECT, related_name='+')
    monto = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Saldo inicial')

    class Meta:
        """Define etiquetas administrativas y evita duplicar una divisa por caja."""
        verbose_name = 'Saldo inicial de caja'
        verbose_name_plural = 'Saldos iniciales de caja'
        ordering = ['divisa__codigo']
        constraints = [
            models.UniqueConstraint(
                fields=['caja', 'divisa'],
                name='saldo_inicial_unico_por_caja_y_divisa',
            ),
        ]

    def __str__(self):
        """Muestra el código de la divisa y el monto registrado."""
        return f'{self.divisa.codigo}: {self.monto}'
