from django.db import models
from django.utils import timezone
from django.conf import settings

class Cliente(models.Model):
    """
    Modelo que representa a un Cliente dentro del sistema.
    
    Gestiona la información de los clientes, diferenciando entre personas
    físicas y jurídicas, y estableciendo la relación con su usuario de acceso.
    
    Historia de Usuario GE-8: Se incorpora el campo `segmento` para clasificar 
    a los clientes en base a las categorías predefinidas por Global Exchange.
    """
    TIPO_FISICA = 'FISICA'
    TIPO_JURIDICA = 'JURIDICA'
    
    TIPO_CLIENTE_CHOICES = [
        (TIPO_FISICA, 'Persona Física'),
        (TIPO_JURIDICA, 'Persona Jurídica'),
    ]

    # Lista predefinida de categorías/segmentos para Global Exchange (Historia GE-8)
    # *Nota: Puedes editar los nombres de estas categorías según las reglas exactas de negocio.
    SEGMENTO_CHOICES = [
        ('ESTANDAR', 'Estándar'),
        ('PREMIUM', 'Premium'),
        ('VIP', 'VIP'),
        ('CORPORATIVO', 'Corporativo'),
    ]

    # Relación uno a uno con el modelo de Usuario
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cliente_profile',
        verbose_name="Usuario del Sistema",
        null=True,
        blank=True
    )

    tipo_cliente = models.CharField(
        max_length=10, 
        choices=TIPO_CLIENTE_CHOICES, 
        default=TIPO_FISICA,
        verbose_name="Tipo de Cliente"
    )
    
    # Se añade null=True para evitar conflictos con registros antiguos
    identificador = models.CharField(
        max_length=20, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Identificador (CI / RUC)"
    )
    
    nombre = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nombre")
    apellido = models.CharField(max_length=100, blank=True, null=True, verbose_name="Apellido")
    razon_social = models.CharField(max_length=150, blank=True, null=True, verbose_name="Razón Social")
    
    # Se añade null=True por si hay clientes antiguos sin email
    email = models.EmailField(unique=True, null=True, blank=True, verbose_name="Correo Electrónico")
    
    # NUEVO CAMPO: Segmentación del cliente (Criterio de aceptación 1 - GE-8)
    segmento = models.CharField(
        max_length=20,
        choices=SEGMENTO_CHOICES,
        default='ESTANDAR',
        verbose_name="Segmento / Categoría",
        help_text="Permite clasificar al cliente para diferenciarlo según características de Global Exchange."
    )

    # Se cambia auto_now_add por default=timezone.now para evitar la pregunta en la consola
    fecha_registro = models.DateTimeField(default=timezone.now)

    def __str__(self):
        """
        Representación en formato de cadena (string) del objeto Cliente.
        
        Returns:
            str: Razón social si es Jurídica, de lo contrario Nombre y Apellido.
                 En ambos casos incluye el identificador en paréntesis.
        """
        if self.tipo_cliente == self.TIPO_JURIDICA:
            return f"{self.razon_social} ({self.identificador})"
        return f"{self.nombre} {self.apellido} ({self.identificador})"