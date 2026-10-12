"""Modelos de caja: apertura de turno, saldo inicial y operaciones de ventanilla."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.divisas.models import Divisa


class Caja(models.Model):
    """Representa el turno de caja abierto por un cajero.

    Implementa la HU "Apertura de Caja": se crea siempre en estado
    "Abierta", asociada al cajero que la abre y a la fecha y hora de
    apertura (``abierta_en``). El cierre de una caja es una HU futura que
    todavía no existe en este código; por eso ``estado`` ya contempla
    "Cerrada" y ``cerrada_en`` desde ahora (para no tener que migrar el
    modelo de nuevo más adelante), pero ninguna vista de este archivo los
    usa todavía.
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

    def saldo_actual(self, divisa):
        """Calcula el saldo actual de una moneda en esta caja.

        No se guarda como un campo mutable que haya que mantener
        sincronizado en cada operación: se deriva, de forma perezosa, del
        saldo inicial registrado al abrir (``SaldoInicialCaja``) más los
        ingresos y menos los egresos de esa moneda, tanto en las
        operaciones de ventanilla (``OperacionVentanilla``) como en los
        movimientos extraordinarios (``MovimientoExtraordinario``) ya
        registrados — el mismo patrón de estado computado que ya usan
        ``CalculoOperacion.estado_efectivo``/``Divisa.ultima_cotizacion`` en
        vez de columnas que haya que ir actualizando a mano.

        Args:
            divisa (apps.divisas.models.Divisa): La moneda a consultar
                (incluye PYG).

        Returns:
            decimal.Decimal: El saldo actual de esa moneda en esta caja.
        """
        saldo_inicial = self.saldos_iniciales.filter(divisa=divisa).first()
        saldo = saldo_inicial.monto if saldo_inicial else Decimal('0.00')

        if divisa.codigo == 'PYG':
            # En una "Venta" (la casa le vende divisa al cliente) el cliente
            # entrega guaraníes: ingreso. En una "Compra" (la casa le compra
            # divisa al cliente) es el cajero quien entrega guaraníes: egreso.
            ingresos = self.operaciones.filter(tipo=OperacionVentanilla.TIPO_VENTA)
            egresos = self.operaciones.filter(tipo=OperacionVentanilla.TIPO_COMPRA)
            campo = 'monto_pyg'
        else:
            # En una "Compra" el cliente entrega la divisa: ingreso. En una
            # "Venta" es el cajero quien la entrega: egreso.
            ingresos = self.operaciones.filter(tipo=OperacionVentanilla.TIPO_COMPRA, divisa=divisa)
            egresos = self.operaciones.filter(tipo=OperacionVentanilla.TIPO_VENTA, divisa=divisa)
            campo = 'monto_divisa'

        total_ingresos = ingresos.aggregate(total=models.Sum(campo))['total'] or Decimal('0.00')
        total_egresos = egresos.aggregate(total=models.Sum(campo))['total'] or Decimal('0.00')

        movimientos_extraordinarios = self.movimientos_extraordinarios.filter(divisa=divisa)
        total_ingresos_extra = movimientos_extraordinarios.filter(
            tipo=MovimientoExtraordinario.TIPO_INGRESO,
        ).aggregate(total=models.Sum('monto'))['total'] or Decimal('0.00')
        total_egresos_extra = movimientos_extraordinarios.filter(
            tipo=MovimientoExtraordinario.TIPO_EGRESO,
        ).aggregate(total=models.Sum('monto'))['total'] or Decimal('0.00')

        return saldo + total_ingresos - total_egresos + total_ingresos_extra - total_egresos_extra


class SaldoInicialCaja(models.Model):
    """Saldo inicial de una moneda puntual, registrado al abrir una caja.

    Una fila por cada divisa activa que el cajero contó al momento de abrir,
    incluido PYG (su existencia en el catálogo está garantizada por la
    migración de datos ``apps.divisas.0014_crear_divisa_pyg``, ya que es la
    moneda local/base del sistema): el inventario completo de la apertura
    es la colección de estas filas asociadas a una ``Caja``.
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


class OperacionVentanilla(models.Model):
    """Registra una compra o venta de divisas en efectivo realizada en ventanilla.

    Implementa la HU "Gestión de operaciones en ventanilla": reutiliza el
    mismo cálculo de cotización que ya usa el flujo online del cliente
    (``apps.divisas.views._calcular_importe_operacion``, ver
    ``apps.caja.views.RegistrarOperacionVentanillaView``) en vez de
    duplicarlo, pero ``TIPO_COMPRA``/``TIPO_VENTA`` acá significan lo
    *opuesto* a ``apps.divisas.models.CalculoOperacion.TIPO_COMPRA``/
    ``TIPO_VENTA``, que están escritos desde la perspectiva del cliente. En
    esta HU los nombres son desde la perspectiva de la casa de cambio:

    - "Compra": la casa le compra divisa al cliente. El cliente entrega la
      divisa (ingresa a la caja) y el cajero entrega guaraníes (egresa).
      Equivale a una "Venta" para ``_calcular_importe_operacion``.
    - "Venta": la casa le vende divisa al cliente. El cliente entrega
      guaraníes (ingresa) y el cajero entrega la divisa (egresa). Equivale
      a una "Compra" para ``_calcular_importe_operacion``.

    Es exactamente la lectura que usa el Criterio 3 de la HU al describir
    qué moneda debe entregar el cajero en cada caso ("la divisa en una
    venta, guaraníes en una compra").
    """

    TIPO_COMPRA = 'COMPRA'
    TIPO_VENTA = 'VENTA'
    TIPO_CHOICES = [
        (TIPO_COMPRA, 'Compra de divisas (la casa compra)'),
        (TIPO_VENTA, 'Venta de divisas (la casa vende)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caja = models.ForeignKey(
        Caja,
        on_delete=models.PROTECT,
        related_name='operaciones',
        verbose_name='Caja',
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='operaciones_ventanilla',
        verbose_name='Cajero',
    )
    tipo = models.CharField(max_length=6, choices=TIPO_CHOICES, verbose_name='Tipo de operación')
    divisa = models.ForeignKey(
        Divisa,
        on_delete=models.PROTECT,
        related_name='operaciones_ventanilla',
        verbose_name='Divisa operada',
    )
    monto_divisa = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Monto en divisa')
    tasa_aplicada = models.DecimalField(max_digits=18, decimal_places=6, verbose_name='Tasa aplicada')
    comision_porcentaje = models.DecimalField(max_digits=6, decimal_places=3, verbose_name='Comisión (%)')
    comision = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Comisión')
    monto_pyg = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Monto en guaraníes')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Define el orden y las etiquetas administrativas de las operaciones."""
        verbose_name = 'Operación de ventanilla'
        verbose_name_plural = 'Operaciones de ventanilla'
        ordering = ['-creado_en']

    def __str__(self):
        """Describe el tipo, el monto en divisa y la caja de la operación."""
        return f'{self.get_tipo_display()}: {self.monto_divisa} {self.divisa.codigo} ({self.caja})'


class MovimientoExtraordinario(models.Model):
    """Registra un ingreso o egreso de caja que no proviene de una operación cambiaria.

    Implementa la HU "Gestión de movimientos extraordinarios de Caja": a
    diferencia de ``OperacionVentanilla`` (que siempre representa una
    compra o venta de divisas con tasa y comisión calculadas), un
    movimiento extraordinario no triangula ninguna cotización — es un
    ingreso o egreso de efectivo puntual, con su ``motivo`` como único dato
    que lo explica (por ejemplo, un retiro para gastos de oficina, o un
    refuerzo de caja). Por eso no excluye PYG ni ninguna divisa sin
    cotización vigente como sí hace ``OperacionVentanillaForm``: no hace
    falta ninguna tasa para registrar un monto en una moneda puntual.

    ``Caja.saldo_actual`` suma los ingresos y resta los egresos de este
    modelo exactamente igual que ya hace con ``OperacionVentanilla``
    (Criterio 1), y ``apps.caja.views.RegistrarMovimientoExtraordinarioView``
    rechaza un egreso mayor al saldo disponible de esa moneda (Criterio 2)
    con el mismo criterio que ya usa ``RegistrarOperacionVentanillaView``
    para una compra o venta. El campo ``motivo`` es obligatorio a nivel de
    modelo y de formulario (Criterio 3). En cualquier listado o reporte de
    la caja, un movimiento extraordinario se distingue de una operación
    cambiaria por aparecer en su propia sección/tabla, nunca mezclado en el
    listado de ``OperacionVentanilla`` (Criterio 4; ver
    ``apps.caja.views.PanelCajaView`` y la plantilla ``panel_caja.html``).
    """

    TIPO_INGRESO = 'INGRESO'
    TIPO_EGRESO = 'EGRESO'
    TIPO_CHOICES = [
        (TIPO_INGRESO, 'Ingreso extraordinario'),
        (TIPO_EGRESO, 'Egreso extraordinario'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caja = models.ForeignKey(
        Caja,
        on_delete=models.PROTECT,
        related_name='movimientos_extraordinarios',
        verbose_name='Caja',
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='movimientos_extraordinarios_caja',
        verbose_name='Cajero',
    )
    tipo = models.CharField(max_length=7, choices=TIPO_CHOICES, verbose_name='Tipo de movimiento')
    divisa = models.ForeignKey(
        Divisa,
        on_delete=models.PROTECT,
        related_name='movimientos_extraordinarios',
        verbose_name='Divisa',
    )
    monto = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Monto')
    motivo = models.TextField(verbose_name='Motivo')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Define el orden y las etiquetas administrativas de los movimientos extraordinarios."""
        verbose_name = 'Movimiento extraordinario de caja'
        verbose_name_plural = 'Movimientos extraordinarios de caja'
        ordering = ['-creado_en']

    def __str__(self):
        """Describe el tipo, el monto y la divisa del movimiento."""
        return f'{self.get_tipo_display()}: {self.monto} {self.divisa.codigo} ({self.caja})'


class ArqueoCaja(models.Model):
    """Registra la comparación, en un momento puntual, entre el saldo del sistema y lo contado a mano.

    Implementa la HU "Arqueo de Caja": el cajero cuenta físicamente cuánto
    tiene de cada moneda y el sistema lo compara contra
    ``Caja.saldo_actual`` en ese instante (ver
    ``apps.caja.views.IniciarArqueoCajaView``). Ambos valores quedan
    congelados por divisa en ``DetalleArqueoCaja`` — no se recalculan
    después — para que el registro sea fiel a lo que realmente se comparó
    ese día, aunque el saldo de la caja siga cambiando con operaciones
    posteriores (Criterio 3: "disponible para consulta posterior").

    Una diferencia distinta de cero en cualquier divisa (sobrante o
    faltante) nunca impide registrar el arqueo ni sigue bloqueando la caja
    después: solo queda constancia de ella (Criterio 2).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caja = models.ForeignKey(
        Caja,
        on_delete=models.PROTECT,
        related_name='arqueos',
        verbose_name='Caja',
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='arqueos_caja',
        verbose_name='Cajero',
    )
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name='Fecha y hora del arqueo')

    class Meta:
        """Define el orden y las etiquetas administrativas de los arqueos."""
        verbose_name = 'Arqueo de caja'
        verbose_name_plural = 'Arqueos de caja'
        ordering = ['-creado_en']

    def __str__(self):
        """Identifica el arqueo por su caja y la fecha/hora en que se realizó."""
        return f'Arqueo de {self.caja} el {self.creado_en:%d/%m/%Y %H:%M}'

    @property
    def tiene_diferencias(self):
        """Indica si algún detalle de este arqueo tiene una diferencia distinta de cero."""
        return any(detalle.diferencia != Decimal('0.00') for detalle in self.detalles.all())


class DetalleArqueoCaja(models.Model):
    """Compara, para una moneda puntual, el saldo del sistema contra lo contado en un arqueo.

    Una fila por cada divisa activa incluida en un ``ArqueoCaja``.
    ``saldo_sistema`` y ``monto_contado`` quedan congelados en el momento
    del arqueo; ``diferencia`` se deriva de esos dos valores (positiva:
    sobrante; negativa: faltante; cero: coincide exacto), sin necesidad de
    guardarla por separado.
    """

    arqueo = models.ForeignKey(
        ArqueoCaja,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name='Arqueo',
    )
    divisa = models.ForeignKey(Divisa, on_delete=models.PROTECT, related_name='+')
    saldo_sistema = models.DecimalField(
        max_digits=18, decimal_places=2, verbose_name='Saldo según el sistema',
    )
    monto_contado = models.DecimalField(
        max_digits=18, decimal_places=2, verbose_name='Monto contado físicamente',
    )

    class Meta:
        """Define el orden, las etiquetas administrativas y evita duplicar una divisa por arqueo."""
        verbose_name = 'Detalle de arqueo de caja'
        verbose_name_plural = 'Detalles de arqueo de caja'
        ordering = ['divisa__codigo']
        constraints = [
            models.UniqueConstraint(
                fields=['arqueo', 'divisa'],
                name='detalle_arqueo_unico_por_divisa',
            ),
        ]

    def __str__(self):
        """Muestra la divisa, lo contado y el saldo del sistema en ese momento."""
        return f'{self.divisa.codigo}: contado {self.monto_contado}, sistema {self.saldo_sistema}'

    @property
    def diferencia(self):
        """Diferencia entre lo contado y el saldo del sistema.

        Positiva indica un sobrante (hay más de lo que el sistema esperaba);
        negativa, un faltante; cero, que coinciden exactamente.
        """
        return self.monto_contado - self.saldo_sistema
