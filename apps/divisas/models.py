from django.db import models

class Divisa(models.Model):
    """
    Modelo que representa una divisa disponible en Global Exchange.
    
    Atributos:
        codigo (str): Código ISO de la divisa (ej. USD, EUR).
        nombre (str): Nombre completo de la divisa.
        activa (bool): Indica si la divisa está habilitada para operar. 
                       Cumple con el criterio de aceptación de ocultar divisas inactivas.
    """
    codigo = models.CharField(max_length=3, unique=True, verbose_name="Código")
    nombre = models.CharField(max_length=50, verbose_name="Nombre")
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Divisa"
        verbose_name_plural = "Divisas"

    def __str__(self):
        """Retorna la representación en cadena del modelo (el código de la divisa)."""
        return self.codigo

    @property
    def ultima_cotizacion(self):
        """
        Obtiene la cotización más reciente registrada para esta divisa.
        
        Retorna:
            Cotizacion: El objeto de cotización más reciente, o None si no tiene cotizaciones.
        """
        return self.cotizaciones.order_by('-fecha_actualizacion').first()


class Cotizacion(models.Model):
    """
    Modelo que almacena las tasas de compra y venta de una divisa específica.
    
    Atributos:
        divisa (Divisa): Relación a la divisa correspondiente.
        tasa_compra (Decimal): Valor de compra actual.
        tasa_venta (Decimal): Valor de venta actual.
        fecha_actualizacion (datetime): Fecha y hora en la que se registró la tasa.
                                        Cumple con el criterio de mostrar la última actualización.
    """
    divisa = models.ForeignKey(Divisa, on_delete=models.CASCADE, related_name='cotizaciones')
    tasa_compra = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tasa de Compra")
    tasa_venta = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tasa de Venta")
    fecha_actualizacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Actualización")

    class Meta:
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        ordering = ['-fecha_actualizacion']

    def __str__(self):
        """Retorna la representación de la cotización con su fecha."""
        return f"{self.divisa.codigo} - Compra: {self.tasa_compra} / Venta: {self.tasa_venta}"