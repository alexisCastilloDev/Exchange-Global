"""Modelos de divisas y registro histórico de cotizaciones."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, models, transaction as db_transaction
from django.utils import timezone

from apps.clientes.models import Cliente, MetodoPago

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
    (pasa a "Cancelada" y no se procesa más). Si al intentar confirmarla la
    tasa vigente ya cambió respecto de ``tasa_aplicada`` (ver
    ``tasa_vigente_cambio``), la confirmación se rechaza y la transacción se
    cancela automáticamente como "Cancelada por cambio de cotización", un
    estado distinto de la cancelación manual para que el historial pueda
    diferenciarlas; el cliente puede recalcular con la tasa nueva desde esa
    misma pantalla. Si el cliente nunca vuelve a esa pantalla (por ejemplo,
    cierra la pestaña) y se cumple ``vence_en`` sin que la transacción se
    haya confirmado ni cancelado, se considera "Vencida": ``estado_efectivo``
    refleja esto de inmediato para quien la consulte, aunque el campo
    ``estado`` recién se actualice en la base de datos la próxima vez que
    alguien con permiso visite esa transacción.
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
    ESTADO_CANCELADA_COTIZACION = 'CANCELADA_COTIZACION'
    ESTADO_PAGADA = 'PAGADA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de confirmación'),
        (ESTADO_CONFIRMADA, 'Confirmada'),
        (ESTADO_CANCELADA, 'Cancelada'),
        (ESTADO_VENCIDA, 'Vencida'),
        (ESTADO_CANCELADA_COTIZACION, 'Cancelada por cambio de cotización'),
        (ESTADO_PAGADA, 'Pagada'),
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
    (pasa a "Cancelada"). Si al intentar confirmarlo alguna de las tasas
    vigentes ya cambió (ver ``tasas_vigentes_cambiaron``), la confirmación se
    rechaza y el cambio se cancela automáticamente como "Cancelada por
    cambio de cotización", distinguible de la cancelación manual en el
    historial; el cliente puede recalcular con las tasas nuevas desde esa
    misma pantalla. Si el cliente nunca vuelve a esa pantalla y se cumple
    ``vence_en`` sin resolución, se considera "Vencida" (ver
    ``estado_efectivo``). Así aparece en el historial de transacciones junto
    con las compras y ventas. ``TIPO_DISPLAY`` es el nombre del tipo de
    operación que muestra el historial.
    """

    TIPO_DISPLAY = 'Cambio'

    ESTADO_PENDIENTE = 'PENDIENTE_CONFIRMACION'
    ESTADO_CONFIRMADA = 'CONFIRMADA'
    ESTADO_CANCELADA = 'CANCELADA'
    ESTADO_VENCIDA = 'VENCIDA'
    ESTADO_CANCELADA_COTIZACION = 'CANCELADA_COTIZACION'
    ESTADO_PAGADA = 'PAGADA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de confirmación'),
        (ESTADO_CONFIRMADA, 'Confirmada'),
        (ESTADO_CANCELADA, 'Cancelada'),
        (ESTADO_VENCIDA, 'Vencida'),
        (ESTADO_CANCELADA_COTIZACION, 'Cancelada por cambio de cotización'),
        (ESTADO_PAGADA, 'Pagada'),
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


class PagoRechazadoError(Exception):
    """Señala que un pago no puede registrarse para una transacción dada.

    La cubren, por ejemplo, una transacción que no está "Confirmada", una
    que ya tiene un pago exitoso, o la ausencia de una transacción válida
    (ver ``Pago.registrar_pago``). Las vistas la capturan para mostrar el
    mensaje al usuario en vez de dejarla propagarse como error 500.
    """


class Pago(models.Model):
    """Registra el pago exitoso de una única transacción ya "Confirmada".

    Implementa la HU "Asociación de pagos a transacciones" (GE-25), pensada
    explícitamente como base de dos HU futuras que todavía no existen en
    este código: pago con tarjeta vía Stripe y pago por transferencia vía
    SIPAP. Por eso ``medio_pago``, ``proveedor`` e ``identificador_externo``
    son genéricos en vez de modelar un único medio: cuando esas HU se
    implementen, sus webhooks (verificación de firma incluida, que no es
    responsabilidad de este modelo) solo necesitan armar esos mismos datos
    a partir de su propio payload y llamar a ``registrar_pago``, el único
    punto de entrada para marcar una transacción como pagada.

    Puede asociarse tanto a una compra/venta (``calculo_operacion``) como a
    un cambio entre divisas (``calculo_triangulacion``): exactamente una de
    las dos, nunca ambas ni ninguna (ver ``clean``). Cada una es un
    ``OneToOneField``, así que la base de datos garantiza por sí sola que
    una transacción no puede tener más de un pago, sin importar el medio
    con el que se intente el segundo.
    """

    PROVEEDOR_MANUAL = 'MANUAL'

    calculo_operacion = models.OneToOneField(
        CalculoOperacion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pago',
        verbose_name='Compra o venta pagada',
    )
    calculo_triangulacion = models.OneToOneField(
        CalculoTriangulacion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pago',
        verbose_name='Cambio de divisas pagado',
    )
    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pagos',
        verbose_name='Método de pago guardado utilizado',
    )
    medio_pago = models.CharField(max_length=20, choices=MetodoPago.TIPO_MEDIO_CHOICES)
    proveedor = models.CharField(
        max_length=30,
        help_text='Quién confirmó el pago: MANUAL (esta HU), o un proveedor real como STRIPE/SIPAP.',
    )
    identificador_externo = models.CharField(
        max_length=100,
        help_text='Identificador del pago para ese proveedor (p. ej. el id de un PaymentIntent de Stripe).',
    )
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Define etiquetas administrativas y la invariante de idempotencia."""
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-creado_en']
        constraints = [
            models.UniqueConstraint(
                fields=['proveedor', 'identificador_externo'],
                name='pago_unico_por_proveedor_e_identificador',
            ),
        ]

    def __str__(self):
        """Identifica el pago por su proveedor e identificador externo."""
        return f'Pago {self.proveedor}:{self.identificador_externo} ({self.monto})'

    def clean(self):
        """Valida que el pago pertenezca a exactamente una transacción."""
        from django.core.exceptions import ValidationError
        if bool(self.calculo_operacion_id) == bool(self.calculo_triangulacion_id):
            raise ValidationError('Un pago debe pertenecer a exactamente una transacción.')

    @property
    def transaccion(self):
        """Devuelve la compra/venta o el cambio al que pertenece este pago."""
        return self.calculo_operacion or self.calculo_triangulacion

    @classmethod
    def registrar_pago(cls, transaccion, medio_pago, proveedor, identificador_externo, monto, metodo_pago=None):
        """Registra, de forma idempotente, el pago exitoso de una transacción.

        Es el único punto de entrada para marcar una transacción como
        "Pagada": tanto el flujo manual de esta HU como, más adelante, los
        webhooks de Stripe y SIPAP deben construir sus propios datos
        (medio, proveedor, identificador externo, monto) y llamar acá, en
        vez de tocar ``transaccion.estado`` directamente.

        Args:
            transaccion: Una ``CalculoOperacion`` o ``CalculoTriangulacion``
                ya existente.
            medio_pago (str): Uno de ``MetodoPago.TIPO_MEDIO_CHOICES``.
            proveedor (str): Quién confirma el pago (``PROVEEDOR_MANUAL`` o
                un proveedor real).
            identificador_externo (str): Identificador del pago para ese
                proveedor. Junto con ``proveedor``, es la clave de
                idempotencia: una segunda llamada con el mismo par no crea
                un segundo pago ni vuelve a tocar la transacción.
            monto (Decimal): Monto efectivamente pagado.
            metodo_pago: El ``MetodoPago`` guardado del cliente que se usó,
                si corresponde.

        Returns:
            tuple[Pago, bool]: El pago (nuevo o preexistente) y si se creó
            recién en esta llamada.

        Raises:
            PagoRechazadoError: Si no hay una transacción válida, si no
                está en estado "Confirmada" (por ejemplo porque está
                pendiente, vencida, cancelada, o ya "Pagada"), siempre que
                no se trate de una repetición idempotente del mismo pago
                ya registrado.
        """
        if transaccion is None:
            raise PagoRechazadoError('No hay una transacción válida para registrar el pago.')

        pago_existente = cls.objects.filter(
            proveedor=proveedor, identificador_externo=identificador_externo,
        ).first()
        if pago_existente is not None:
            return pago_existente, False

        if transaccion.estado_efectivo == transaccion.ESTADO_PAGADA:
            raise PagoRechazadoError('La transacción ya fue pagada.')
        if transaccion.estado_efectivo != transaccion.ESTADO_CONFIRMADA:
            raise PagoRechazadoError(
                'La transacción debe estar "Confirmada" para poder registrar un pago.'
            )

        campo_transaccion = (
            'calculo_operacion' if isinstance(transaccion, CalculoOperacion) else 'calculo_triangulacion'
        )
        try:
            with db_transaction.atomic():
                pago = cls.objects.create(
                    medio_pago=medio_pago,
                    proveedor=proveedor,
                    identificador_externo=identificador_externo,
                    monto=monto,
                    metodo_pago=metodo_pago,
                    **{campo_transaccion: transaccion},
                )
                transaccion.estado = transaccion.ESTADO_PAGADA
                transaccion.save(update_fields=['estado'])
        except IntegrityError:
            # Carrera entre dos llamadas simultáneas: o bien la otra ya
            # registró este mismo pago (mismo proveedor+identificador, caso
            # idempotente), o bien ya le ganó de mano con un pago distinto a
            # la misma transacción (el OneToOneField es lo que lo impide "por
            # cualquier medio", sin importar si el identificador difiere).
            pago_existente = cls.objects.filter(
                proveedor=proveedor, identificador_externo=identificador_externo,
            ).first()
            if pago_existente is not None:
                return pago_existente, False
            raise PagoRechazadoError('La transacción ya fue pagada.') from None
        return pago, True