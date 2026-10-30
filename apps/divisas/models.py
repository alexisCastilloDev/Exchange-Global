"""Modelos de divisas y registro histórico de cotizaciones."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
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

    # PYG es la moneda base del sistema (ver moneda_a_pagar más abajo):
    # implícita en cualquier operación, 1:1 consigo misma, sin cotización
    # propia que cargar. Se identifica siempre por este código, nunca por
    # su clave primaria — un id autoincremental no es portable entre
    # instalaciones (depende del orden en que se hayan creado las demás
    # divisas), mientras que "PYG" sí lo es: es el mismo valor en
    # cualquier base. Por eso cada protección de este modelo (y las de
    # los formularios/vistas que lo administran) compara contra
    # ``CODIGO_BASE``/``es_base``, no contra un número de fila.
    CODIGO_BASE = 'PYG'
    NOMBRE_BASE = 'Guaraní'
    SIMBOLO_BASE = 'Gs.'

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
    def es_base(self):
        """Indica si esta es PYG, la moneda base del sistema (implícita, no administrable)."""
        return self.codigo == self.CODIGO_BASE

    def save(self, *args, **kwargs):
        """Impide modificar PYG, sin importar qué código llame a ``save`` (vista, shell, admin).

        Si la fila ya existía como PYG, cualquier intento de cambiarle el
        código se rechaza; cualquier otro dato (nombre, símbolo, si está
        activa) se fuerza siempre a su valor canónico, en vez de guardar
        lo que se le haya asignado — así una modificación no declarada
        como error simplemente no tiene efecto, nunca llega a persistir.
        La única fila que se crea libremente es la primera (la que carga
        la migración ``0017_asegurar_divisa_pyg``): antes de que exista,
        no hay nada que proteger todavía.
        """
        if self.pk:
            codigo_anterior = Divisa.objects.filter(pk=self.pk).values_list('codigo', flat=True).first()
            if codigo_anterior == self.CODIGO_BASE:
                if self.codigo != self.CODIGO_BASE:
                    raise ValidationError('PYG es la divisa base del sistema: no se puede modificar.')
                self.nombre = self.NOMBRE_BASE
                self.simbolo = self.SIMBOLO_BASE
                self.activa = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Impide eliminar PYG: el sistema la necesita siempre presente y activa."""
        if self.es_base:
            raise ValidationError('PYG es la divisa base del sistema: no se puede eliminar.')
        return super().delete(*args, **kwargs)

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

    def save(self, *args, **kwargs):
        """Guarda la cotización y notifica a los clientes si cambió alguna tasa.

        Implementa la HU "Notificaciones sobre tasas de cambio" (GE-51).
        Cada actualización de tasas se registra como una cotización *nueva*
        (el historial nunca se pisa, ver ``ActualizarCotizacionView``), así
        que "la tasa anterior" es la última cotización de la divisa que ya
        existía antes de esta. Solo al crear una cotización se compara contra
        esa anterior y, por cada tasa (compra o venta) cuyo valor sea
        distinto, se genera una notificación para cada usuario cliente (ver
        ``NotificacionTasa.notificar_cambios``). Si la tasa se guarda con el
        mismo valor que ya tenía no se notifica nada, y tampoco en la primera
        cotización de una divisa, porque no hay una tasa anterior con la que
        comparar ni que informar.

        La cotización y sus notificaciones se guardan en una única
        transacción de base de datos: o quedan ambas registradas, o ninguna.
        """
        es_nueva = self._state.adding
        anterior = None
        if es_nueva and self.divisa_id:
            anterior = (
                Cotizacion.objects.filter(divisa_id=self.divisa_id)
                .order_by('-fecha_actualizacion', '-pk')
                .first()
            )
        with db_transaction.atomic():
            super().save(*args, **kwargs)
            if anterior is not None:
                NotificacionTasa.notificar_cambios(anterior, self)


class SaldoInsuficienteError(Exception):
    """Global Exchange no tiene saldo propio suficiente para entregar en esa moneda."""


class CuentaPropiaInexistenteError(Exception):
    """Global Exchange no tiene una cuenta propia configurada en esa moneda."""


class CuentaPropia(models.Model):
    """Saldo propio de Global Exchange en una moneda, espejado contra la cuenta real en sipap-sim.

    Una fila por ``Divisa``, incluida PYG — a diferencia del catálogo
    administrable de divisas (donde PYG está prohibida, ver
    ``DivisaUpdateView``), acá es al revés: PYG también tiene su propia
    cuenta, porque esto es Global Exchange llevando su propia tenencia,
    no el catálogo de qué monedas existen.

    La cuenta bancaria o billetera real (adónde entra y de dónde sale
    la plata de verdad) se administra en sipap-sim, no acá: este
    modelo nunca se edita a mano. Se mantiene en espejo de dos formas:

    1. En cada entrega (``apps.divisas.entrega.realizar_entrega``): se
       acredita la moneda que el cliente pagó y se debita la que
       Global Exchange le transfirió a cambio, recién después de que
       esa transferencia se confirma de verdad contra sipap-sim.
    2. Al visitar el panel de administración ("Fondos propios",
       ``CuentaPropiaListView``): se vuelve a consultar el saldo real a
       sipap-sim y se corrige cualquier diferencia (por ejemplo, si un
       administrador fondeó la cuenta directamente en sipap-sim), ver
       ``apps.divisas.casa_de_cambio``.

    Antes de confirmar una operación, un chequeo rápido contra esta
    misma fila (sin red, sin depender de que sipap-sim esté arriba en
    ese instante) decide si Global Exchange puede llegar a entregarla;
    por eso conviene que el espejo exista en esta base, en vez de
    consultar a sipap-sim en ese momento tan sensible al tiempo.
    """

    divisa = models.OneToOneField(Divisa, on_delete=models.PROTECT, related_name='cuenta_propia')
    # 30 dígitos en total, igual que ``sipap_sim.core.models.Cuenta.saldo``
    # (ver ese modelo): tienen que poder representar exactamente el mismo
    # saldo, sin que un número grande se trunque de un lado y no del otro.
    saldo = models.DecimalField(max_digits=30, decimal_places=2, default=Decimal('0.00'))
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        """Ordena por código de divisa y define las etiquetas administrativas."""
        verbose_name = 'Cuenta propia'
        verbose_name_plural = 'Cuentas propias'
        ordering = ['divisa__codigo']

    def __str__(self):
        """Identifica la cuenta propia por la divisa y su saldo actual."""
        return f'{self.divisa.codigo}: {self.saldo}'

    @classmethod
    def ajustar_saldos(cls, *, divisa_recibir, monto_recibir, divisa_entregar, monto_entregar):
        """Acredita lo recibido y debita lo entregado, las dos piernas juntas y atómicas.

        Única operación que mueve saldo propio por una entrega: nunca
        se edita ``saldo`` directamente fuera de acá (la otra forma en
        que cambia es la sincronización con sipap-sim, ver
        ``CuentaPropiaListView``), para que las dos piernas de cada
        entrega siempre se muevan juntas.

        Bloquea las dos filas con ``select_for_update()`` en una sola
        consulta ordenada por ``divisa_id`` (nunca dos ``.get()``
        separados): así, sin importar en qué orden una compra y una
        venta de las mismas dos monedas tomen los locks, siempre se
        adquieren en el mismo orden global y no hay deadlock.

        Args:
            divisa_recibir (Divisa): La moneda que el cliente pagó.
            monto_recibir (Decimal): Cuánto se acredita en esa moneda.
            divisa_entregar (Divisa): La moneda que Global Exchange le
                transfirió al cliente a cambio.
            monto_entregar (Decimal): Cuánto se debita en esa moneda.

        Raises:
            CuentaPropiaInexistenteError: Si falta la fila de alguna de
                las dos monedas (no debería pasar: se crea sola al dar
                de alta la divisa, ver ``DivisaCreateView``).
            SaldoInsuficienteError: Si no hay saldo suficiente en la
                moneda a entregar. No se modifica nada en ese caso.
        """
        with db_transaction.atomic():
            cuentas = {
                cuenta.divisa_id: cuenta for cuenta in
                cls.objects.select_for_update()
                    .filter(divisa_id__in=[divisa_recibir.pk, divisa_entregar.pk])
                    .order_by('divisa_id')
            }
            for divisa in (divisa_recibir, divisa_entregar):
                if divisa.pk not in cuentas:
                    raise CuentaPropiaInexistenteError(
                        f'Global Exchange no tiene una cuenta propia en {divisa.codigo}.'
                    )
            cuenta_entregar = cuentas[divisa_entregar.pk]
            if cuenta_entregar.saldo < monto_entregar:
                raise SaldoInsuficienteError(
                    f'Global Exchange no tiene saldo suficiente en {divisa_entregar.codigo} '
                    f'(disponible: {cuenta_entregar.saldo}, necesario: {monto_entregar}).'
                )
            cuenta_entregar.saldo -= monto_entregar
            cuenta_entregar.save(update_fields=['saldo'])
            cuentas[divisa_recibir.pk].saldo += monto_recibir
            cuentas[divisa_recibir.pk].save(update_fields=['saldo'])


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
    ESTADO_CANCELADA_SALDO_INSUFICIENTE = 'CANCELADA_SALDO_INSUFICIENTE'
    ESTADO_CANCELADA_FONDOS_CLIENTE = 'CANCELADA_FONDOS_CLIENTE'
    ESTADO_PAGADA = 'PAGADA'
    ESTADO_ENTREGA_FALLIDA = 'ENTREGA_FALLIDA'
    ESTADO_PAGO_EXPIRADO = 'PAGO_EXPIRADO'
    ESTADO_ACREDITADA = 'ACREDITADA'
    # A diferencia de todos los demás estados de esta lista, este no se
    # espejea en CalculoTriangulacion: un cambio entre divisas nunca es una
    # venta, así que nunca podría llegar a "Retirada" — espejarlo ahí solo
    # agregaría una columna y una opción muertas, sin ningún caso que las
    # use. Ver HU "Retiro de fondos" (GE-24).
    ESTADO_RETIRADA = 'RETIRADA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de confirmación'),
        (ESTADO_CONFIRMADA, 'Confirmada'),
        (ESTADO_CANCELADA, 'Cancelada'),
        (ESTADO_VENCIDA, 'Vencida'),
        (ESTADO_CANCELADA_COTIZACION, 'Cancelada por cambio de cotización'),
        (ESTADO_CANCELADA_SALDO_INSUFICIENTE, 'Cancelada por saldo insuficiente de Global Exchange'),
        (ESTADO_CANCELADA_FONDOS_CLIENTE, 'Cancelada por fondos insuficientes del cliente'),
        (ESTADO_PAGADA, 'Pagada'),
        (ESTADO_ENTREGA_FALLIDA, 'Pagada, pero la entrega al cliente falló'),
        (ESTADO_PAGO_EXPIRADO, 'Pago fuera de plazo'),
        (ESTADO_ACREDITADA, 'Acreditada'),
        (ESTADO_RETIRADA, 'Retirada'),
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
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    medio_destino = models.ForeignKey(
        MetodoPago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Medio al que se entrega',
        help_text=(
            'La cuenta o billetera propia del cliente a la que Global '
            'Exchange le transfiere lo que corresponda (la divisa comprada, '
            'o los guaraníes de una venta). Se elige en el paso de pago, '
            'nunca una tarjeta (Stripe no puede depositarle a una).'
        ),
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    vence_en = models.DateTimeField()
    confirmado_en = models.DateTimeField(null=True, blank=True)
    tasa_vence_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='La tasa fijada vence en',
        help_text=(
            'Se fija al confirmar, sumándole a ese momento '
            'ConfiguracionVigencia.vigencia_pago_segundos(). Campo separado '
            'de "vence_en" (que gobierna solo Pendiente → Confirmar/Cancelar) '
            'para no interferir con ese mecanismo ya existente.'
        ),
    )
    acreditado_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Acreditado en',
        help_text=(
            'Fecha y hora en que la entrega de una compra se completó con '
            'éxito (ver ``apps.divisas.entrega.realizar_entrega``). Una '
            'venta no usa este campo: lo que deja una venta no se entrega '
            'sola, el cliente lo retira explícitamente (ver '
            '``retirado_en``, HU "Retiro de fondos", GE-24).'
        ),
    )
    referencia_acreditacion = models.CharField(
        max_length=60,
        blank=True,
        verbose_name='Referencia de la acreditación',
        help_text='La misma referencia con la que se le pidió la transferencia a sipap-sim.',
    )
    retirado_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Retirado en',
        help_text=(
            'Fecha y hora en que el retiro de una venta se completó con '
            'éxito (ver ``apps.divisas.entrega.realizar_entrega``, HU '
            '"Retiro de fondos", GE-24). Una compra no usa este campo: su '
            'entrega es automática y usa ``acreditado_en``.'
        ),
    )
    referencia_retiro = models.CharField(
        max_length=60,
        blank=True,
        verbose_name='Referencia del retiro',
        help_text='La misma referencia con la que se le pidió la transferencia a sipap-sim.',
    )

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
    def tasa_vencida(self):
        """Indica si la tasa fijada al confirmar ya venció sin que se haya pagado.

        Solo aplica a una transacción "Confirmada": una vez pagada (o
        cancelada, por cualquier motivo), la tasa ya no está "vigente o
        vencida" — ya se usó o ya no corresponde. Se usa para bloquear un
        cobro nuevo (``apps.divisas.pagos_stripe``/``pagos_sipap``) antes
        de intentarlo, y como red de seguridad en
        ``Pago.registrar_pago`` si de todos modos llega una confirmación
        tardía.
        """
        return (
            self.estado == self.ESTADO_CONFIRMADA
            and self.tasa_vence_en is not None
            and timezone.now() >= self.tasa_vence_en
        )

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
    tres tiempos distintos, correspondientes a los pasos 1→2, 2→3 y "ya
    confirmada, falta pagar" del flujo de compra/venta/cambio (ver
    ``apps.divisas.views.CalculoOperacionView`` y ``ConfirmarTransaccionOperacionView``):

    - ``calculo_vigencia_segundos``: cuánto tiene el cliente, tras calcular el
      importe (Paso 1), para confirmarlo (Paso 2) antes de que la cotización
      usada se considere vencida y deba recalcular.
    - ``confirmacion_vigencia_segundos``: cuánto tiene, ya con la transacción
      creada en "Pendiente de confirmación" (Paso 2), para confirmarla o
      cancelarla (Paso 3) antes de que se considere "Vencida".
    - ``pago_vigencia_segundos``: cuánto dura fija la tasa una vez confirmada
      la operación (Paso 3), antes de que un pago que llegue ya no pueda
      liquidarse a esa tasa (ver ``CalculoOperacion.tasa_vencida``). El
      mínimo recomendado es 1800 segundos (30 minutos): es el mínimo real
      que admite ``expires_at`` en una sesión de Stripe Checkout, así que
      con un valor menor la sesión de Stripe puede seguir activa después de
      que la tasa ya venció del lado de Global Exchange — no es un error,
      ``Pago.registrar_pago`` sigue siendo la autoridad final en cualquier
      caso y un pago así llega registrado como "fuera de plazo", nunca se
      pierde.
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
    pago_vigencia_segundos = models.IntegerField(
        default=1800,
        verbose_name='Tiempo de espera para pagar con la tasa fijada (segundos)',
        help_text=(
            'Tiempo entre confirmar la operación y pagarla, antes de que la '
            'tasa fijada venza. Mínimo recomendado: 1800 (el mínimo real de '
            'Stripe Checkout).'
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

    @classmethod
    def vigencia_pago_segundos(cls):
        """Segundos que la tasa fijada al confirmar sigue vigente para pagar."""
        configuracion = cls.objects.first()
        if configuracion:
            return configuracion.pago_vigencia_segundos
        return settings.PAGO_OPERACION_VIGENCIA_SEGUNDOS


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
    ESTADO_CANCELADA_SALDO_INSUFICIENTE = 'CANCELADA_SALDO_INSUFICIENTE'
    ESTADO_CANCELADA_FONDOS_CLIENTE = 'CANCELADA_FONDOS_CLIENTE'
    ESTADO_PAGADA = 'PAGADA'
    ESTADO_ENTREGA_FALLIDA = 'ENTREGA_FALLIDA'
    ESTADO_PAGO_EXPIRADO = 'PAGO_EXPIRADO'
    ESTADO_ACREDITADA = 'ACREDITADA'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de confirmación'),
        (ESTADO_CONFIRMADA, 'Confirmada'),
        (ESTADO_CANCELADA, 'Cancelada'),
        (ESTADO_VENCIDA, 'Vencida'),
        (ESTADO_CANCELADA_COTIZACION, 'Cancelada por cambio de cotización'),
        (ESTADO_CANCELADA_SALDO_INSUFICIENTE, 'Cancelada por saldo insuficiente de Global Exchange'),
        (ESTADO_CANCELADA_FONDOS_CLIENTE, 'Cancelada por fondos insuficientes del cliente'),
        (ESTADO_PAGADA, 'Pagada'),
        (ESTADO_ENTREGA_FALLIDA, 'Pagada, pero la entrega al cliente falló'),
        (ESTADO_PAGO_EXPIRADO, 'Pago fuera de plazo'),
        (ESTADO_ACREDITADA, 'Acreditada'),
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
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
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
    medio_destino = models.ForeignKey(
        MetodoPago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Medio al que se entrega',
        help_text=(
            'La cuenta o billetera propia del cliente, en la divisa de '
            'destino, a la que Global Exchange le transfiere el resultado '
            'del cambio. Se elige en el paso de pago, nunca una tarjeta.'
        ),
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    vence_en = models.DateTimeField()
    confirmado_en = models.DateTimeField(null=True, blank=True)
    tasa_vence_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='La tasa fijada vence en',
        help_text=(
            'Ver CalculoOperacion.tasa_vence_en: mismo criterio, aplicado '
            'al cambio entre divisas.'
        ),
    )
    acreditado_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Acreditado en',
        help_text='Ver CalculoOperacion.acreditado_en: mismo criterio, aplicado al cambio entre divisas.',
    )
    referencia_acreditacion = models.CharField(
        max_length=60,
        blank=True,
        verbose_name='Referencia de la acreditación',
        help_text='La misma referencia con la que se le pidió la transferencia a sipap-sim.',
    )

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
    def tasa_vencida(self):
        """Ver ``CalculoOperacion.tasa_vencida``: mismo criterio, aplicado al cambio entre divisas."""
        return (
            self.estado == self.ESTADO_CONFIRMADA
            and self.tasa_vence_en is not None
            and timezone.now() >= self.tasa_vence_en
        )

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


def monto_a_pagar(transaccion):
    """Devuelve lo que el cliente entrega de verdad para esta transacción.

    Una **compra** se paga en PYG: ``monto_final`` es lo que el cliente
    entrega a cambio de la divisa que compra. Una **venta** se paga
    entregando la propia divisa vendida, no PYG: ahí lo que el cliente
    entrega es ``monto_origen``, en ``codigo_divisa`` — ``monto_final``
    es lo que *recibe* en guaraníes, no lo que paga. Un **cambio** entre
    divisas (``CalculoTriangulacion``) usa PYG solo como paso intermedio
    de la triangulación, nunca lo toca el cliente: lo que entrega de
    verdad es ``monto_origen``, en su propia divisa de origen.

    Ver ``monto_a_entregar`` para el lado contrario (lo que Global
    Exchange le transfiere al cliente a cambio).
    """
    if isinstance(transaccion, CalculoTriangulacion):
        return transaccion.monto_origen
    if transaccion.tipo == CalculoOperacion.TIPO_VENTA:
        return transaccion.monto_origen
    return transaccion.monto_final


def moneda_a_pagar(transaccion):
    """Devuelve el código de la moneda en la que el cliente paga esta transacción.

    Ver ``monto_a_pagar``: una compra se paga en PYG; una venta se paga
    en la propia divisa vendida (``codigo_divisa``), nunca en PYG; un
    cambio se paga en su divisa de origen, no en la de destino.
    """
    if isinstance(transaccion, CalculoTriangulacion):
        return transaccion.codigo_divisa_origen
    if transaccion.tipo == CalculoOperacion.TIPO_VENTA:
        return transaccion.codigo_divisa
    return 'PYG'


def monto_a_entregar(transaccion):
    """Devuelve lo que Global Exchange le transfiere al cliente a cambio.

    Simétrico de ``monto_a_pagar``: en una compra, lo que se entrega es
    la divisa comprada (``monto_origen``); en una venta, los guaraníes
    resultantes (``monto_final``); en un cambio, el monto ya convertido
    a la divisa de destino (``monto_final``).
    """
    if isinstance(transaccion, CalculoTriangulacion):
        return transaccion.monto_final
    if transaccion.tipo == CalculoOperacion.TIPO_VENTA:
        return transaccion.monto_final
    return transaccion.monto_origen


def moneda_a_entregar(transaccion):
    """Devuelve el código de la moneda en la que Global Exchange entrega esta transacción.

    Ver ``monto_a_entregar``: una compra entrega la divisa comprada
    (``codigo_divisa``); una venta entrega PYG; un cambio entrega la
    divisa de destino (``codigo_divisa_destino``), nunca la de origen ni
    PYG.
    """
    if isinstance(transaccion, CalculoTriangulacion):
        return transaccion.codigo_divisa_destino
    if transaccion.tipo == CalculoOperacion.TIPO_VENTA:
        return 'PYG'
    return transaccion.codigo_divisa


def divisa_a_pagar(transaccion):
    """Devuelve la ``Divisa`` (no solo el código) en la que el cliente paga esta transacción.

    Mismo criterio que ``moneda_a_pagar``, pero como objeto: lo que
    necesita ``CuentaPropia.ajustar_saldos`` para acreditar la moneda
    correcta, en vez de buscarla de nuevo por código.
    """
    if isinstance(transaccion, CalculoTriangulacion):
        return transaccion.divisa_origen
    if transaccion.tipo == CalculoOperacion.TIPO_VENTA:
        return transaccion.divisa
    return Divisa.objects.get(codigo=Divisa.CODIGO_BASE)


def divisa_a_entregar(transaccion):
    """Devuelve la ``Divisa`` (no solo el código) en la que Global Exchange entrega esta transacción.

    Ver ``divisa_a_pagar``.
    """
    if isinstance(transaccion, CalculoTriangulacion):
        return transaccion.divisa_destino
    if transaccion.tipo == CalculoOperacion.TIPO_VENTA:
        return Divisa.objects.get(codigo=Divisa.CODIGO_BASE)
    return transaccion.divisa


def estados_con_pago_ya_registrado(modelo):
    """Devuelve los estados de ``modelo`` que implican que ya existe un pago vinculado.

    Se usa para armar el mensaje "ya fue pagada" sin repetir, en cada
    lugar que lo necesita (``apps.divisas.views``/``pagos_stripe``/
    ``pagos_sipap``), la lista exacta de estados — que no es la misma
    para los dos modelos: ``ESTADO_RETIRADA`` (HU "Retiro de fondos",
    GE-24) solo existe en ``CalculoOperacion``, nunca en
    ``CalculoTriangulacion`` (ver su ``ESTADO_CHOICES``), así que
    acceder a él sin este chequeo rompería con un cambio entre divisas.
    """
    estados = [modelo.ESTADO_PAGADA, modelo.ESTADO_ACREDITADA]
    if hasattr(modelo, 'ESTADO_RETIRADA'):
        estados.append(modelo.ESTADO_RETIRADA)
    return tuple(estados)


class PagoRechazadoError(Exception):
    """Señala que un pago no puede registrarse para una transacción dada.

    La cubren, por ejemplo, una transacción que no está "Confirmada", una
    que ya tiene un pago exitoso, o la ausencia de una transacción válida
    (ver ``Pago.registrar_pago``). Las vistas la capturan para mostrar el
    mensaje al usuario en vez de dejarla propagarse como error 500.
    """


class Pago(models.Model):
    """Registra el pago de una única transacción ya "Confirmada".

    Implementa la HU "Asociación de pagos a transacciones" (GE-25), pensada
    explícitamente como base de dos HU de pago real que ya están
    implementadas sobre esta misma base: pago con tarjeta vía Stripe
    (``apps.divisas.pagos_stripe``) y pago por transferencia vía SIPAP
    (``apps.divisas.pagos_sipap``). Por eso ``medio_pago``, ``proveedor`` e
    ``identificador_externo`` son genéricos en vez de modelar un único
    medio: cada integración (verificación de firma incluida, que no es
    responsabilidad de este modelo) arma esos mismos datos a partir de su
    propio webhook y llama a ``registrar_pago`` (o, si el monto confirmado
    no coincide con el esperado, a ``registrar_pago_observado``), los
    únicos puntos de entrada para tocar una transacción por un pago.

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
    observado = models.BooleanField(
        default=False,
        verbose_name='Observado',
        help_text=(
            'El proveedor confirmó un pago, pero por un monto distinto '
            'del esperado (ver `diferencia`): queda registrado para '
            'revisión manual, sin marcar la transacción como "Pagada".'
        ),
    )
    diferencia = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Diferencia (monto recibido − monto esperado)',
        help_text='Solo tiene valor cuando `observado` es verdadero.',
    )
    fuera_de_plazo = models.BooleanField(
        default=False,
        verbose_name='Fuera de plazo',
        help_text=(
            'El pago llegó después de que venció la tasa fijada al '
            'confirmar (ver CalculoOperacion.tasa_vencida): se registra '
            'igual, nunca se pierde, pero la transacción pasa a "Pago '
            'fuera de plazo" en vez de "Pagada", porque ya no corresponde '
            'liquidarla a esa tasa.'
        ),
    )
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

        Nota:
            Si la tasa fijada al confirmar ya venció (``tasa_vencida``) en
            el momento en que llega el pago, el pago NUNCA se pierde ni se
            rechaza: se registra igual, con ``fuera_de_plazo=True``, pero
            la transacción pasa a "Pago fuera de plazo"
            (``ESTADO_PAGO_EXPIRADO``) en vez de "Pagada", porque ya no
            corresponde liquidarla a esa tasa.
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

        fuera_de_plazo = transaccion.tasa_vencida
        nuevo_estado = transaccion.ESTADO_PAGO_EXPIRADO if fuera_de_plazo else transaccion.ESTADO_PAGADA

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
                    fuera_de_plazo=fuera_de_plazo,
                    **{campo_transaccion: transaccion},
                )
                transaccion.estado = nuevo_estado
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

    @classmethod
    def registrar_pago_observado(cls, transaccion, medio_pago, proveedor, identificador_externo, monto, diferencia, metodo_pago=None):
        """Registra, de forma idempotente, un pago cuyo monto no coincide con el esperado.

        Pensado para SIPAP (``apps.divisas.pagos_sipap``): a diferencia de
        Stripe, donde el monto que se cobra lo fija el propio sistema, una
        transferencia bancaria la hace el cliente a mano, así que el banco
        puede confirmar un monto distinto del que correspondía. En ese
        caso no corresponde marcar la transacción como "Pagada" — el pago
        queda igual registrado (``observado=True``, con la ``diferencia``)
        para que alguien lo revise, pero la transacción sigue "Confirmada"
        y el cliente puede reintentar el pago.

        Misma idempotencia que ``registrar_pago`` por
        ``(proveedor, identificador_externo)``: repetir la misma
        confirmación no crea un segundo registro.

        Args:
            transaccion: Una ``CalculoOperacion`` o ``CalculoTriangulacion``
                ya existente.
            medio_pago (str): Uno de ``MetodoPago.TIPO_MEDIO_CHOICES``.
            proveedor (str): Quién confirma el pago.
            identificador_externo (str): Identificador del pago para ese
                proveedor; junto con ``proveedor``, la clave de
                idempotencia.
            monto (Decimal): Monto que el proveedor confirmó haber
                recibido (no necesariamente el esperado).
            diferencia (Decimal): ``monto`` menos el monto que se esperaba
                recibir; se guarda con signo, para saber de un vistazo si
                sobró o faltó plata.
            metodo_pago: El ``MetodoPago`` guardado del cliente que se usó,
                si corresponde.

        Returns:
            tuple[Pago, bool]: El pago (nuevo o preexistente) y si se creó
            recién en esta llamada.

        Raises:
            PagoRechazadoError: Mismos casos que ``registrar_pago`` (sin
                transacción válida, ya pagada, o no "Confirmada"), salvo
                que sea una repetición idempotente del mismo pago.
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
            pago = cls.objects.create(
                medio_pago=medio_pago,
                proveedor=proveedor,
                identificador_externo=identificador_externo,
                monto=monto,
                observado=True,
                diferencia=diferencia,
                metodo_pago=metodo_pago,
                **{campo_transaccion: transaccion},
            )
            # Deliberadamente no se toca transaccion.estado: un pago
            # observado no confirma la transacción, queda pendiente de
            # revisión (criterio 3 de "Pago por transferencia vía SIPAP").
        except IntegrityError:
            pago_existente = cls.objects.filter(
                proveedor=proveedor, identificador_externo=identificador_externo,
            ).first()
            if pago_existente is not None:
                return pago_existente, False
            raise PagoRechazadoError('La transacción ya fue pagada.') from None
        return pago, True


class SolicitudPagoSipap(models.Model):
    """Solicitud de pago por transferencia bancaria vía SIPAP de una transacción "Confirmada".

    Implementa la HU "Pago por transferencia bancaria vía SIPAP". A
    diferencia de Stripe (donde el cobro es inmediato, por API o en una
    página de pago), una transferencia bancaria real tarda: el cliente
    tiene que salir del sistema, transferir desde su banco, y recién
    después llega la confirmación. Por eso esta HU necesita algo que
    ``apps.divisas.pagos_stripe`` no necesitó — un registro propio de "este
    pago está pendiente, con esta referencia, hasta esta fecha" — que
    ``apps.divisas.pagos_sipap`` crea al iniciar el pago
    (``IniciarPagoSipapOperacionView``/``IniciarPagoSipapCambioView``) y
    actualiza al llegar la confirmación (``sipap_webhook_view``).

    Igual que ``Pago``, se asocia a una compra/venta o a un cambio entre
    divisas, exactamente uno de los dos (ver ``clean``), con un
    ``OneToOneField`` en cada caso: no pueden coexistir dos solicitudes
    para la misma transacción (si la primera vence o es rechazada, se
    reutiliza la misma fila en vez de crear otra — ver
    ``apps.divisas.pagos_sipap._obtener_o_crear_solicitud``).
    """

    ESTADO_PENDIENTE = 'PENDIENTE'
    ESTADO_ACREDITADA = 'ACREDITADA'
    ESTADO_OBSERVADA = 'OBSERVADA'
    ESTADO_RECHAZADA = 'RECHAZADA'
    ESTADO_VENCIDA = 'VENCIDA'
    ESTADO_SALDO_INSUFICIENTE = 'SALDO_INSUFICIENTE'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_ACREDITADA, 'Acreditada'),
        (ESTADO_OBSERVADA, 'Observada'),
        (ESTADO_RECHAZADA, 'Rechazada'),
        (ESTADO_VENCIDA, 'Vencida'),
        (ESTADO_SALDO_INSUFICIENTE, 'Saldo insuficiente del cliente'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calculo_operacion = models.OneToOneField(
        CalculoOperacion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='solicitud_sipap',
        verbose_name='Compra o venta a pagar',
    )
    calculo_triangulacion = models.OneToOneField(
        CalculoTriangulacion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='solicitud_sipap',
        verbose_name='Cambio de divisas a pagar',
    )
    pago = models.OneToOneField(
        Pago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitud_sipap',
        verbose_name='Pago resultante (exitoso u observado)',
    )
    referencia = models.CharField(
        max_length=40,
        unique=True,
        verbose_name='Referencia única',
        help_text='El cliente la usa como concepto/referencia al transferir; SIPAP la devuelve en la confirmación.',
    )
    monto = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Monto esperado')
    moneda = models.CharField(max_length=3, verbose_name='Moneda esperada')
    medio_pago = models.CharField(
        max_length=20,
        choices=[
            (MetodoPago.TIPO_TRANSFERENCIA, 'Transferencia Bancaria'),
            (MetodoPago.TIPO_BILLETERA, 'Billetera Digital'),
        ],
        default=MetodoPago.TIPO_TRANSFERENCIA,
        verbose_name='Medio de pago',
        help_text='Transferencia bancaria o billetera digital: ambas se resuelven con sipap-sim, pero se muestran distinto en el historial de pagos.',
    )
    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitudes_sipap',
        verbose_name='Método de pago elegido',
        help_text=(
            'La cuenta bancaria o billetera guardada que el cliente eligió '
            'para pagar; su número y CI/RUC se le mandan a sipap-sim para '
            'que la "banca en línea" la reconozca directamente, en vez de '
            'ofrecer todas las cuentas del sistema para elegir.'
        ),
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    banco_origen = models.CharField(max_length=100, blank=True, null=True, verbose_name='Banco de origen')
    id_externo = models.CharField(
        max_length=60, blank=True, null=True, verbose_name='ID de la transferencia en SIPAP',
        help_text='El id que devuelve sipap-sim al crear la solicitud de cobro.',
    )
    link_pago = models.URLField(
        max_length=500, blank=True, verbose_name='Link de pago',
        help_text='La "banca en línea" de sipap-sim a la que se redirige al cliente para completar la transferencia.',
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    vence_en = models.DateTimeField()

    class Meta:
        """Define etiquetas administrativas y el orden por defecto."""
        verbose_name = 'Solicitud de pago SIPAP'
        verbose_name_plural = 'Solicitudes de pago SIPAP'
        ordering = ['-creado_en']

    def __str__(self):
        """Identifica la solicitud por su referencia y su estado."""
        return f'Solicitud SIPAP {self.referencia} ({self.get_estado_display()})'

    def clean(self):
        """Valida que la solicitud pertenezca a exactamente una transacción."""
        from django.core.exceptions import ValidationError
        if bool(self.calculo_operacion_id) == bool(self.calculo_triangulacion_id):
            raise ValidationError('Una solicitud debe pertenecer a exactamente una transacción.')

    @property
    def transaccion(self):
        """Devuelve la compra/venta o el cambio al que pertenece esta solicitud."""
        return self.calculo_operacion or self.calculo_triangulacion

    @property
    def esta_vencida(self):
        """Indica si la solicitud ya superó su plazo sin resolverse."""
        return self.estado == self.ESTADO_PENDIENTE and timezone.now() >= self.vence_en

    def marcar_vencida_si_corresponde(self):
        """Persiste el paso a "Vencida" si la solicitud pendiente ya venció.

        Mismo patrón perezoso que ``CalculoOperacion.marcar_vencida_si_corresponde``:
        nada expira en segundo plano, se resuelve la próxima vez que
        alguien visita la pantalla de pago o el webhook la procesa.

        Returns:
            bool: ``True`` si la solicitud quedó "Vencida" recién ahora.
        """
        if self.esta_vencida:
            self.estado = self.ESTADO_VENCIDA
            self.save(update_fields=['estado'])
            return True
        return False


def _a_tasa(valor):
    """Normaliza una tasa a ``Decimal`` con los dos decimales de ``Cotizacion``.

    Permite comparar sin falsos positivos una tasa recién cargada (que puede
    llegar como ``float``, ``int`` o ``str``, por ejemplo ``7400``) con la
    guardada en base de datos (``Decimal('7400.00')``).
    """
    return Decimal(str(valor)).quantize(Decimal('0.01'))


class NotificacionTasa(models.Model):
    """Aviso a un usuario cliente de que cambió una tasa de cambio.

    Implementa la HU "Notificaciones sobre tasas de cambio" (GE-51). Cada
    registro informa un único cambio: una divisa, un tipo de tasa (compra o
    venta), la tasa anterior y la nueva. Si en una misma actualización
    cambian la compra y la venta, cada usuario recibe dos notificaciones,
    una por tipo de tasa. Se generan automáticamente al guardar una nueva
    ``Cotizacion`` (ver ``Cotizacion.save`` y ``notificar_cambios``).

    Cada usuario solo ve sus propias notificaciones, de la más reciente a la
    más antigua (ver ``MisNotificacionesView``), y puede marcarlas como
    leídas (ver ``marcar_como_leida``); las no leídas se cuentan en el
    indicador de la barra superior (ver
    ``apps.divisas.context_processors.notificaciones_context``).

    Campos principales:

    - ``usuario``: usuario cliente destinatario de la notificación.
    - ``divisa``: divisa cuya tasa cambió.
    - ``cotizacion``: cotización que introdujo el cambio.
    - ``tipo_tasa``: ``COMPRA`` o ``VENTA``.
    - ``tasa_anterior`` / ``tasa_nueva``: valor de la tasa antes y después del cambio.
    - ``creada_en``: momento en que se generó la notificación.
    - ``leida`` / ``leida_en``: si el usuario ya la marcó como leída, y cuándo.
    """

    TIPO_COMPRA = 'COMPRA'
    TIPO_VENTA = 'VENTA'
    TIPO_TASA_CHOICES = [
        (TIPO_COMPRA, 'Compra'),
        (TIPO_VENTA, 'Venta'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notificaciones_tasa',
        verbose_name='Usuario destinatario',
    )
    divisa = models.ForeignKey(
        Divisa,
        on_delete=models.CASCADE,
        related_name='notificaciones_tasa',
        verbose_name='Divisa',
    )
    cotizacion = models.ForeignKey(
        Cotizacion,
        on_delete=models.CASCADE,
        related_name='notificaciones',
        verbose_name='Cotización que generó el cambio',
    )
    tipo_tasa = models.CharField(max_length=6, choices=TIPO_TASA_CHOICES, verbose_name='Tipo de tasa')
    tasa_anterior = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Tasa anterior')
    tasa_nueva = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Tasa nueva')
    creada_en = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de notificación')
    leida = models.BooleanField(default=False, verbose_name='Leída')
    leida_en = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de lectura')

    class Meta:
        """Ordena de la más reciente a la más antigua e indexa las no leídas."""
        verbose_name = 'Notificación de tasa'
        verbose_name_plural = 'Notificaciones de tasas'
        ordering = ['-creada_en', '-pk']
        indexes = [
            models.Index(fields=['usuario', 'leida'], name='notif_tasa_usuario_leida_idx'),
        ]

    def __str__(self):
        """Resume la notificación con su divisa, tipo de tasa y valores."""
        return (
            f'{self.divisa.codigo} {self.get_tipo_tasa_display()}: '
            f'{self.tasa_anterior} -> {self.tasa_nueva}'
        )

    @property
    def variacion(self):
        """Diferencia entre la tasa nueva y la anterior (negativa si bajó)."""
        return self.tasa_nueva - self.tasa_anterior

    @property
    def subio(self):
        """Indica si la tasa aumentó respecto de la anterior."""
        return self.variacion > 0

    @property
    def mensaje(self):
        """Texto legible de la notificación, listo para mostrar al usuario."""
        return (
            f'La tasa de {self.get_tipo_tasa_display().lower()} de {self.divisa.codigo} '
            f'cambió de {self.tasa_anterior} a {self.tasa_nueva}.'
        )

    def marcar_como_leida(self):
        """Marca la notificación como leída y registra cuándo.

        Es idempotente: si ya estaba leída no se vuelve a guardar ni se pisa
        la fecha de lectura original.

        Returns:
            bool: ``True`` si la notificación pasó a leída recién ahora.
        """
        if self.leida:
            return False
        self.leida = True
        self.leida_en = timezone.now()
        self.save(update_fields=['leida', 'leida_en'])
        return True

    @staticmethod
    def usuarios_clientes():
        """Devuelve los usuarios que deben recibir notificaciones de tasas.

        El rol ``cliente`` vive solo en la sesión de Keycloak (ver
        ``apps.authentication.backends``), así que no puede consultarse para
        usuarios que no están conectados. Por eso se considera "usuario
        cliente" a todo usuario activo asociado a al menos un ``Cliente``
        activo, ya sea como usuario del sistema asociado (``usuarios``) o
        como titular (``user``): son justamente los usuarios que pueden
        operar en nombre de un cliente.

        Returns:
            QuerySet: Usuarios activos, sin repetidos.
        """
        from django.contrib.auth import get_user_model

        return (
            get_user_model().objects.filter(is_active=True)
            .filter(
                models.Q(clientes__is_active=True)
                | models.Q(cliente_perfil__is_active=True)
            )
            .distinct()
        )

    @classmethod
    def notificar_cambios(cls, anterior, nueva):
        """Genera las notificaciones por los cambios entre dos cotizaciones.

        Compara por separado la tasa de compra y la de venta. Por cada una
        cuyo valor sea distinto, crea una notificación para cada usuario
        cliente (ver ``usuarios_clientes``), con la divisa afectada, el tipo
        de tasa, la tasa anterior y la nueva. Si ninguna tasa cambió, no se
        crea nada.

        Args:
            anterior (Cotizacion): Última cotización vigente antes del cambio.
            nueva (Cotizacion): Cotización recién guardada.

        Returns:
            list[NotificacionTasa]: Las notificaciones creadas (vacía si no
            hubo cambios o no hay usuarios clientes).
        """
        cambios = []
        for tipo, campo in ((cls.TIPO_COMPRA, 'tasa_compra'), (cls.TIPO_VENTA, 'tasa_venta')):
            valor_anterior = _a_tasa(getattr(anterior, campo))
            valor_nuevo = _a_tasa(getattr(nueva, campo))
            if valor_anterior != valor_nuevo:
                cambios.append((tipo, valor_anterior, valor_nuevo))
        if not cambios:
            return []

        notificaciones = [
            cls(
                usuario_id=usuario_id,
                divisa_id=nueva.divisa_id,
                cotizacion=nueva,
                tipo_tasa=tipo,
                tasa_anterior=valor_anterior,
                tasa_nueva=valor_nuevo,
            )
            for usuario_id in cls.usuarios_clientes().values_list('pk', flat=True)
            for tipo, valor_anterior, valor_nuevo in cambios
        ]
        return cls.objects.bulk_create(notificaciones)


class RangoDocumentosAgotadoError(Exception):
    """No quedan números disponibles en el rango de documento electrónico habilitado para este tipo."""


class ContadorDocumentoElectronico(models.Model):
    """Lleva, para cada tipo de documento, el próximo número a asignar dentro del rango habilitado.

    Factura Segura (HU "Integración con API de facturación electrónica",
    ver ``apps.divisas.factura_electronica``) no asigna el número de
    documento (``dNumDoc``) por sí sola: lo elige quien emite, dentro
    del rango que el administrador de Factura Segura habilitó para este
    ESI (un establecimiento y punto de expedición fijos — ver
    ``settings.FACTURASEGURA_ESTABLECIMIENTO``/``FACTURASEGURA_PUNTO_EXPEDICION``
    — con un rango de números por tipo de documento). Ese rango es
    finito y real: a diferencia de SIPAP o Stripe, acá no hay ningún
    sandbox que lo reponga solo, así que este modelo es el único lugar
    donde se decide el próximo número (``siguiente_numero``), nunca se
    calcula "al vuelo" al armar el JSON — eso permitiría que dos
    emisiones simultáneas eligieran el mismo número.
    """

    TIPO_FACTURA = '1'
    TIPO_NOTA_CREDITO = '5'
    TIPO_DOCUMENTO_CHOICES = [
        (TIPO_FACTURA, 'Factura electrónica'),
        (TIPO_NOTA_CREDITO, 'Nota de crédito electrónica'),
    ]

    tipo_documento = models.CharField(max_length=1, choices=TIPO_DOCUMENTO_CHOICES, unique=True)
    desde = models.PositiveIntegerField(verbose_name='Primer número habilitado')
    hasta = models.PositiveIntegerField(verbose_name='Último número habilitado')
    ultimo_asignado = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Último número asignado',
        help_text='Vacío si todavía no se asignó ninguno: el próximo a usar es "desde".',
    )

    class Meta:
        """Etiquetas administrativas del contador."""
        verbose_name = 'Contador de documento electrónico'
        verbose_name_plural = 'Contadores de documento electrónico'

    def __str__(self):
        """Identifica el contador por tipo de documento y su rango habilitado."""
        return f'{self.get_tipo_documento_display()} ({self.desde:07d}-{self.hasta:07d})'

    @classmethod
    def siguiente_numero(cls, tipo_documento):
        """Reserva y devuelve, de forma atómica, el próximo número disponible para ese tipo.

        Bloquea la fila del contador con ``select_for_update()`` para
        que dos emisiones concurrentes nunca reciban el mismo número,
        ni siquiera si llegan en el mismo instante. El número se marca
        como asignado acá, antes de llamar a Factura Segura: si la
        emisión después falla, ese número queda "quemado" (nunca se
        reutiliza para un documento distinto) — es preferible perder un
        número del rango a arriesgarse a emitir dos documentos con el
        mismo ``dNumDoc``.

        Args:
            tipo_documento (str): Uno de ``TIPO_DOCUMENTO_CHOICES``.

        Returns:
            str: El número de 7 dígitos, con ceros a la izquierda
            (p. ej. ``"0000623"``), listo para usar como ``dNumDoc``.

        Raises:
            RangoDocumentosAgotadoError: Si ya se asignó el último
                número del rango habilitado para ese tipo.
        """
        with db_transaction.atomic():
            contador = cls.objects.select_for_update().get(tipo_documento=tipo_documento)
            siguiente = contador.desde if contador.ultimo_asignado is None else contador.ultimo_asignado + 1
            if siguiente > contador.hasta:
                raise RangoDocumentosAgotadoError(
                    f'Se agotó el rango habilitado de {contador.get_tipo_documento_display()} '
                    f'({contador.desde:07d}-{contador.hasta:07d}). Hay que pedir un rango nuevo a '
                    'Factura Segura.'
                )
            contador.ultimo_asignado = siguiente
            contador.save(update_fields=['ultimo_asignado'])
            return f'{siguiente:07d}'


class DocumentoElectronico(models.Model):
    """Documento tributario electrónico (Factura) emitido ante SIFEN por una transacción pagada.

    Implementa la HU "Integración con API de facturación electrónica":
    apenas una compra, venta o cambio queda "Pagada", Global Exchange le
    emite una Factura Electrónica al cliente a través de Factura Segura
    (ESI de SIFEN) — ver
    ``apps.divisas.factura_electronica.generar_documento_electronico``,
    llamada desde los mismos puntos que ya disparan
    ``apps.divisas.entrega.realizar_entrega``. Es un proceso
    independiente de la entrega del dinero: una falla acá nunca bloquea
    ni revierte el pago ya confirmado, y viceversa (criterio 3).

    Puede asociarse tanto a una compra/venta (``calculo_operacion``)
    como a un cambio entre divisas (``calculo_triangulacion``):
    exactamente una de las dos, nunca ambas ni ninguna (mismo patrón
    que ``Pago`` — ver ``clean``). Cada una es un ``OneToOneField``, así
    que la base de datos garantiza por sí sola que una transacción no
    puede tener más de un documento (criterio 5: nunca se duplica).
    """

    ESTADO_GENERADO = 'GENERADO'
    ESTADO_APROBADO = 'APROBADO'
    ESTADO_APROBADO_OBS = 'APROBADO_OBS'
    ESTADO_RECHAZADO = 'RECHAZADO'
    ESTADO_ERROR_SIFEN = 'ERROR_SIFEN'
    ESTADO_ERROR_GENERACION = 'ERROR_GENERACION'
    ESTADO_CHOICES = [
        (ESTADO_GENERADO, 'Generado, esperando aprobación de SIFEN'),
        (ESTADO_APROBADO, 'Aprobado'),
        (ESTADO_APROBADO_OBS, 'Aprobado con observación'),
        (ESTADO_RECHAZADO, 'Rechazado por SIFEN'),
        (ESTADO_ERROR_SIFEN, 'Error de SIFEN al procesarlo'),
        (ESTADO_ERROR_GENERACION, 'No se pudo generar (Factura Segura no respondió, o lo rechazó)'),
    ]

    calculo_operacion = models.OneToOneField(
        CalculoOperacion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='documento_electronico',
        verbose_name='Compra o venta facturada',
    )
    calculo_triangulacion = models.OneToOneField(
        CalculoTriangulacion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='documento_electronico',
        verbose_name='Cambio de divisas facturado',
    )
    tipo_documento = models.CharField(
        max_length=1,
        choices=ContadorDocumentoElectronico.TIPO_DOCUMENTO_CHOICES,
        default=ContadorDocumentoElectronico.TIPO_FACTURA,
    )
    numero_documento = models.CharField(
        max_length=7,
        verbose_name='Número de documento (dNumDoc)',
        help_text='Reservado de ContadorDocumentoElectronico.siguiente_numero, nunca se reutiliza.',
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_GENERADO)
    cdc = models.CharField(max_length=44, blank=True, verbose_name='CDC (Código de Control)')
    estado_sifen = models.CharField(
        max_length=50, blank=True, help_text='Valor crudo de "estado_sifen" devuelto por get_estado_sifen.',
    )
    desc_sifen = models.CharField(max_length=255, blank=True, verbose_name='Descripción del estado en SIFEN')
    error_sifen = models.CharField(max_length=255, blank=True, verbose_name='Error de SIFEN')
    operation_id = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Id de operación de Factura Segura',
        help_text='Para referencia de soporte (log/debug/auditoría); no tiene ningún uso funcional acá.',
    )
    error_generacion = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Error al generar',
        help_text=(
            'Motivo si "generar_de" nunca llegó a confirmarse (criterios 3 y 4): no se reintenta '
            'solo, requiere una acción explícita de un administrador, que primero debe verificar '
            'con soporte de Factura Segura si el documento ya se había generado del otro lado.'
        ),
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    consultado_en = models.DateTimeField(
        null=True, blank=True, verbose_name='Último estado consultado a SIFEN',
    )

    class Meta:
        """Ordena por fecha de creación y define las etiquetas administrativas."""
        verbose_name = 'Documento electrónico'
        verbose_name_plural = 'Documentos electrónicos'
        ordering = ['-creado_en']

    def __str__(self):
        """Identifica el documento por tipo, número y estado actual."""
        return f'{self.get_tipo_documento_display()} {self.numero_documento} ({self.get_estado_display()})'

    def clean(self):
        """Valida que el documento pertenezca a exactamente una transacción."""
        if bool(self.calculo_operacion_id) == bool(self.calculo_triangulacion_id):
            raise ValidationError('Un documento electrónico debe pertenecer a exactamente una transacción.')

    @property
    def transaccion(self):
        """Devuelve la compra/venta o el cambio al que pertenece este documento."""
        return self.calculo_operacion or self.calculo_triangulacion

    @property
    def es_definitivo(self):
        """Indica si ya no hace falta volver a consultar su estado a SIFEN (llegó a un estado terminal)."""
        return self.estado in (self.ESTADO_APROBADO, self.ESTADO_APROBADO_OBS, self.ESTADO_RECHAZADO)
