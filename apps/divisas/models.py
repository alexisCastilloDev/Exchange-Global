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
    """Conserva el importe calculado y la tasa vigente hasta su vencimiento."""

    TIPO_COMPRA = 'COMPRA'
    TIPO_VENTA = 'VENTA'
    TIPO_CHOICES = [
        (TIPO_COMPRA, 'Compra'),
        (TIPO_VENTA, 'Venta'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calculos_operacion',
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


class CalculoTriangulacion(models.Model):
    """Conserva el resultado de un cambio entre dos divisas extranjeras vía PYG."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='triangulaciones',
    )
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