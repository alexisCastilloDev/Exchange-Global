"""Modelos de divisas y registro histórico de cotizaciones."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.clientes.models import Cliente

class Divisa(models.Model):
    """Representa una divisa activa o inactiva del sistema."""
    """
    Modelo que representa una divisa disponible en Global Exchange.

    Attributes:
        codigo (str): Código ISO de la divisa (por ejemplo USD, EUR).
        nombre (str): Nombre completo de la divisa.
        simbolo (str): Símbolo de la moneda (por ejemplo $, €).
        activa (bool): Indica si la divisa está habilitada para operar.
    """
    codigo = models.CharField(max_length=3, unique=True, verbose_name="Código")
    nombre = models.CharField(max_length=50, verbose_name="Nombre")
    # --- NUEVO CAMPO AÑADIDO ---
    simbolo = models.CharField(max_length=5, null=True, blank=True, verbose_name="Símbolo") 
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        """Define las etiquetas administrativas del modelo de divisa."""
        verbose_name = "Divisa"
        verbose_name_plural = "Divisas"

    def __str__(self):
        """Retorna la representación en cadena del modelo (el código de la divisa)."""
        return self.codigo

    @property
    def ultima_cotizacion(self):
        """
        Obtiene la cotización más reciente registrada para esta divisa.
        """
        return self.cotizaciones.order_by('-fecha_actualizacion').first()

class Cotizacion(models.Model):
    """Registra una tasa histórica de compra y venta para una divisa."""
    """
    Modelo que almacena las tasas de compra y venta de una divisa específica.

    Attributes:
        divisa (Divisa): Relación a la divisa correspondiente.
        tasa_compra (Decimal): Valor de compra actual.
        tasa_venta (Decimal): Valor de venta actual.
        fecha_actualizacion (datetime): Fecha y hora en la que se registró la tasa.
    """
    divisa = models.ForeignKey(Divisa, on_delete=models.CASCADE, related_name='cotizaciones')
    tasa_compra = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tasa de Compra")
    tasa_venta = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tasa de Venta")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='cotizaciones_actualizadas',
        verbose_name="Usuario actualizador",
        null=True,
        blank=True,
    )
    fecha_actualizacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Actualización")

    class Meta:
        """Define las etiquetas y el orden del historial de cotizaciones."""
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        ordering = ['-fecha_actualizacion']

    def __str__(self):
        """Retorna la representación de la cotización con su fecha."""
        return f"{self.divisa.codigo} - Compra: {self.tasa_compra} / Venta: {self.tasa_venta}"


class CalculoOperacion(models.Model):
    """Representa una transacción de compra o venta iniciada por el cliente.

    El cálculo previo (Paso 1: "Calcular importe") es solo una previsualización
    y no se persiste; el registro se crea cuando el cliente confirma el importe
    (Paso 2: "Confirmar importe", ver ``confirmar_calculo_operacion_view``),
    siempre en estado "Pendiente de confirmación" y con ``vence_en`` fijado a
    ``settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS`` más adelante. Desde
    ahí, en la pantalla de confirmación (ver
    ``ConfirmarTransaccionOperacionView``), el cliente revisa el resumen
    completo y decide si la confirma (si la tasa vigente no cambió, pasa a
    "Confirmada" y se registra ``confirmado_en``) o la cancela manualmente
    (pasa a "Cancelada" y no se procesa más). Si el cliente nunca vuelve a
    esa pantalla (por ejemplo, cierra la pestaña) y se cumple ``vence_en``
    sin que la transacción se haya confirmado ni cancelado, se considera
    "Vencida": ``estado_efectivo`` refleja esto de inmediato para quien la
    consulte, aunque el campo ``estado`` recién se actualice en la base de
    datos la próxima vez que alguien con permiso visite esa transacción.
    """

    TIPO_COMPRA = 'COMPRA'
    TIPO_VENTA = 'VENTA'
    TIPO_CHOICES = [
        (TIPO_COMPRA, 'Compra'),
        (TIPO_VENTA, 'Venta'),
    ]

    ESTADO_PENDIENTE = 'PENDIENTE_CONFIRMACION'
    ESTADO_CONFIRMADA = 'CONFIRMADA'
    ESTADO_CANCELADA = 'CANCELADA'
    ESTADO_VENCIDA = 'VENCIDA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de confirmación'),
        (ESTADO_CONFIRMADA, 'Confirmada'),
        (ESTADO_CANCELADA, 'Cancelada'),
        (ESTADO_VENCIDA, 'Vencida'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calculos_operacion',
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='calculos_operacion',
        verbose_name='Cliente',
    )
    tipo = models.CharField(max_length=7, choices=TIPO_CHOICES)
    divisa = models.ForeignKey(
        Divisa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='calculos_operacion',
    )
    codigo_divisa = models.CharField(max_length=3)
    monto_origen = models.DecimalField(max_digits=18, decimal_places=2)
    tasa_aplicada = models.DecimalField(max_digits=18, decimal_places=6)
    comision_porcentaje = models.DecimalField(max_digits=6, decimal_places=3)
    comision = models.DecimalField(max_digits=18, decimal_places=2)
    monto_final = models.DecimalField(max_digits=18, decimal_places=2)
    estado = models.CharField(max_length=25, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    creado_en = models.DateTimeField(auto_now_add=True)
    vence_en = models.DateTimeField()
    confirmado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Define el orden y etiquetas administrativas de los cálculos."""
        verbose_name = 'Cálculo de operación'
        verbose_name_plural = 'Cálculos de operaciones'
        ordering = ['-creado_en']

    @property
    def esta_vencido(self):
        """Indica si el cálculo ya superó su tiempo de vigencia."""
        return timezone.now() >= self.vence_en

    @property
    def estado_efectivo(self):
        """Devuelve el estado real, aunque el vencimiento todavía no se haya guardado.

        Una transacción "Pendiente de confirmación" cuyo ``vence_en`` ya pasó
        está, en la práctica, vencida (el cliente no la confirmó ni canceló a
        tiempo, por ejemplo porque cerró la pestaña), aunque nadie haya vuelto
        a visitarla todavía para que ``marcar_vencida_si_corresponde`` lo
        persista. Se usa para mostrar el estado correcto en el historial de
        transacciones sin depender de que alguien haya "tocado" el registro.
        """
        if self.estado == self.ESTADO_PENDIENTE and self.esta_vencido:
            return self.ESTADO_VENCIDA
        return self.estado

    def get_estado_efectivo_display(self):
        """Etiqueta legible de ``estado_efectivo`` (equivalente a ``get_estado_display``)."""
        return dict(self.ESTADO_CHOICES).get(self.estado_efectivo, self.estado_efectivo)

    def marcar_vencida_si_corresponde(self):
        """Persiste el paso a "Vencida" si la transacción pendiente ya venció.

        Se llama al acceder a la pantalla de confirmación (GET o POST): es el
        único punto de escritura de este vencimiento, siguiendo el mismo
        patrón perezoso que ya usa ``esta_vencido`` en el resto del sistema
        (nada expira en segundo plano; se resuelve la próxima vez que alguien
        interactúa con el registro).

        Returns:
            bool: ``True`` si la transacción quedó "Vencida" recién ahora.
        """
        if self.estado == self.ESTADO_PENDIENTE and self.esta_vencido:
            self.estado = self.ESTADO_VENCIDA
            self.save(update_fields=['estado'])
            return True
        return False

    @property
    def tasa_vigente_cambio(self):
        """Indica si la tasa vigente de la divisa ya no coincide con la aplicada.

        Se usa al confirmar una transacción pendiente: si la divisa no tiene
        cotización vigente, o la tasa que correspondería aplicar ahora (venta
        para una compra, compra para una venta) es distinta de la que se
        guardó al calcular, la tasa "cambió" y no debe confirmarse.
        """
        cotizacion = self.divisa.ultima_cotizacion if self.divisa else None
        if cotizacion is None:
            return True
        tasa_actual = cotizacion.tasa_venta if self.tipo == self.TIPO_COMPRA else cotizacion.tasa_compra
        return tasa_actual != self.tasa_aplicada


class ConfiguracionComision(models.Model):
    """Define el porcentaje de comisión vigente para un segmento de clientes."""

    segmento = models.CharField(
        max_length=20,
        choices=Cliente.SEGMENTO_CHOICES,
        unique=True,
        verbose_name='Segmento / Categoría',
    )
    porcentaje = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        verbose_name='Porcentaje de comisión (%)',
    )
    actualizado_en = models.DateTimeField(auto_now=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comisiones_actualizadas',
    )

    class Meta:
        """Define las etiquetas administrativas de la configuración de comisión."""
        verbose_name = 'Configuración de comisión'
        verbose_name_plural = 'Configuraciones de comisión'
        ordering = ['segmento']

    def __str__(self):
        """Retorna el segmento y el porcentaje configurado."""
        return f'{self.get_segmento_display()}: {self.porcentaje}%'

    @staticmethod
    def porcentaje_para(cliente):
        """Resuelve el porcentaje de comisión aplicable a un cliente.

        Prioridad: comisión personalizada del cliente > comisión configurada
        para su segmento > porcentaje por defecto de ``settings``.
        """
        if cliente is not None and cliente.comision_personalizada is not None:
            return cliente.comision_personalizada
        if cliente is not None:
            configuracion = ConfiguracionComision.objects.filter(segmento=cliente.segmento).first()
            if configuracion:
                return configuracion.porcentaje
        return Decimal(str(settings.COMISION_OPERACION_PORCENTAJE))


class ConfiguracionVigencia(models.Model):
    """Configura, en segundos, los tiempos de espera de una operación cambiaria.

    Es un registro único (patrón singleton): si el administrador no configuró
    ninguno todavía, se usan los valores por defecto de ``settings``. Controla
    dos tiempos distintos, correspondientes a los pasos 1→2 y 2→3 del flujo de
    compra/venta/cambio (ver ``apps.divisas.views.CalculoOperacionView`` y
    ``ConfirmarTransaccionOperacionView``):

    - ``calculo_vigencia_segundos``: cuánto tiene el cliente, tras calcular el
      importe (Paso 1), para confirmarlo (Paso 2) antes de que la cotización
      usada se considere vencida y deba recalcular.
    - ``confirmacion_vigencia_segundos``: cuánto tiene, ya con la transacción
      creada en "Pendiente de confirmación" (Paso 2), para confirmarla o
      cancelarla (Paso 3) antes de que se considere "Vencida".
    """

    calculo_vigencia_segundos = models.IntegerField(
        verbose_name='Tiempo de espera para confirmar el importe (segundos)',
        help_text='Tiempo entre calcular el importe y confirmarlo, antes de que la cotización venza.',
    )
    confirmacion_vigencia_segundos = models.IntegerField(
        verbose_name='Tiempo de espera para confirmar la operación (segundos)',
        help_text=(
            'Tiempo entre confirmar el importe y confirmar o cancelar la'
            ' operación, antes de que la transacción venza.'
        ),
    )
    actualizado_en = models.DateTimeField(auto_now=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vigencias_actualizadas',
    )

    class Meta:
        """Define las etiquetas administrativas de la configuración de vigencia."""
        verbose_name = 'Configuración de vigencia'
        verbose_name_plural = 'Configuración de vigencia'

    def __str__(self):
        """Resume ambos tiempos configurados."""
        return (
            f'Importe: {self.calculo_vigencia_segundos}s ·'
            f' Operación: {self.confirmacion_vigencia_segundos}s'
        )

    @classmethod
    def vigencia_calculo_segundos(cls):
        """Segundos vigentes para confirmar el importe tras calcularlo (Paso 1 → 2)."""
        configuracion = cls.objects.first()
        if configuracion:
            return configuracion.calculo_vigencia_segundos
        return settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS

    @classmethod
    def vigencia_confirmacion_segundos(cls):
        """Segundos vigentes para confirmar o cancelar la operación (Paso 2 → 3)."""
        configuracion = cls.objects.first()
        if configuracion:
            return configuracion.confirmacion_vigencia_segundos
        return settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS


class CalculoTriangulacion(models.Model):
    """Representa un cambio entre dos divisas extranjeras vía PYG.

    Igual que en ``CalculoOperacion``, el cálculo previo es solo una
    previsualización y no se persiste: el registro se crea cuando el cliente
    confirma el importe (ver ``confirmar_triangulacion_view``), siempre en
    estado "Pendiente de confirmación", a nombre del cliente activo y con
    ``vence_en`` fijado a ``settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS``
    más adelante. Desde ahí, en la pantalla de confirmación (ver
    ``ConfirmarTransaccionCambioView``), el cliente revisa el resumen completo
    y decide si lo confirma (si las tasas vigentes no cambiaron, pasa a
    "Confirmada" y se registra ``confirmado_en``) o lo cancela manualmente
    (pasa a "Cancelada"). Si el cliente nunca vuelve a esa pantalla y se
    cumple ``vence_en`` sin resolución, se considera "Vencida" (ver
    ``estado_efectivo``). Así aparece en el historial de transacciones junto
    con las compras y ventas. ``TIPO_DISPLAY`` es el nombre del tipo de
    operación que muestra el historial.
    """

    TIPO_DISPLAY = 'Cambio'

    ESTADO_PENDIENTE = 'PENDIENTE_CONFIRMACION'
    ESTADO_CONFIRMADA = 'CONFIRMADA'
    ESTADO_CANCELADA = 'CANCELADA'
    ESTADO_VENCIDA = 'VENCIDA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de confirmación'),
        (ESTADO_CONFIRMADA, 'Confirmada'),
        (ESTADO_CANCELADA, 'Cancelada'),
        (ESTADO_VENCIDA, 'Vencida'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='triangulaciones',
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='calculos_triangulacion',
        verbose_name='Cliente',
    )
    estado = models.CharField(max_length=25, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    divisa_origen = models.ForeignKey(
        Divisa,
        on_delete=models.PROTECT,
        related_name='triangulaciones_origen',
    )
    divisa_destino = models.ForeignKey(
        Divisa,
        on_delete=models.PROTECT,
        related_name='triangulaciones_destino',
    )
    codigo_divisa_origen = models.CharField(max_length=3)
    codigo_divisa_destino = models.CharField(max_length=3)
    monto_origen = models.DecimalField(max_digits=18, decimal_places=2)
    tasa_compra_aplicada = models.DecimalField(max_digits=18, decimal_places=6)
    tasa_venta_aplicada = models.DecimalField(max_digits=18, decimal_places=6)
    tasa_cruzada = models.DecimalField(max_digits=18, decimal_places=6)
    monto_equivalente_pyg = models.DecimalField(max_digits=18, decimal_places=2)
    comision_porcentaje = models.DecimalField(max_digits=6, decimal_places=3)
    comision = models.DecimalField(max_digits=18, decimal_places=2)
    monto_final = models.DecimalField(max_digits=18, decimal_places=2)
    creado_en = models.DateTimeField(auto_now_add=True)
    vence_en = models.DateTimeField()
    confirmado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Define el orden y etiquetas administrativas de la triangulación."""
        verbose_name = 'Cálculo de triangulación'
        verbose_name_plural = 'Cálculos de triangulación'
        ordering = ['-creado_en']

    @property
    def esta_vencido(self):
        """Indica si el cálculo ya superó su tiempo de vigencia."""
        return timezone.now() >= self.vence_en

    @property
    def estado_efectivo(self):
        """Devuelve el estado real, aunque el vencimiento todavía no se haya guardado.

        Ver ``CalculoOperacion.estado_efectivo``: mismo criterio, aplicado al
        cambio entre divisas.
        """
        if self.estado == self.ESTADO_PENDIENTE and self.esta_vencido:
            return self.ESTADO_VENCIDA
        return self.estado

    def get_estado_efectivo_display(self):
        """Etiqueta legible de ``estado_efectivo`` (equivalente a ``get_estado_display``)."""
        return dict(self.ESTADO_CHOICES).get(self.estado_efectivo, self.estado_efectivo)

    def marcar_vencida_si_corresponde(self):
        """Persiste el paso a "Vencida" si el cambio pendiente ya venció.

        Ver ``CalculoOperacion.marcar_vencida_si_corresponde``: mismo patrón
        perezoso, aplicado al cambio entre divisas.

        Returns:
            bool: ``True`` si el cambio quedó "Vencida" recién ahora.
        """
        if self.estado == self.ESTADO_PENDIENTE and self.esta_vencido:
            self.estado = self.ESTADO_VENCIDA
            self.save(update_fields=['estado'])
            return True
        return False

    @property
    def tasas_vigentes_cambiaron(self):
        """Indica si alguna cotización usada al calcular ya no está vigente.

        Se usa al confirmar el cambio: si cualquiera de las dos divisas
        (origen o destino) se quedó sin cotización, o la tasa que
        correspondería aplicar ahora es distinta de la que se guardó al
        calcular, las tasas "cambiaron" y no debe confirmarse.
        """
        cotizacion_origen = self.divisa_origen.ultima_cotizacion
        cotizacion_destino = self.divisa_destino.ultima_cotizacion
        if cotizacion_origen is None or cotizacion_destino is None:
            return True
        return (
            cotizacion_origen.tasa_compra != self.tasa_compra_aplicada
            or cotizacion_destino.tasa_venta != self.tasa_venta_aplicada
        )