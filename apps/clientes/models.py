"""
Módulo de modelos para la gestión de clientes.
Incluye las implementaciones de las historias de usuario GE-8 (Segmentación)
y GE-63 (Baja lógica y trazabilidad).
"""
from django.db import models
from django.utils import timezone
from django.conf import settings

class ClienteActiveManager(models.Manager):
    """
    Manager personalizado que filtra por defecto únicamente los clientes activos.
    Permite cumplir con el criterio de no mostrar clientes dados de baja
    en los listados generales por defecto.
    """
    def get_queryset(self):
        """
        Retorna el QuerySet excluyendo registros con baja lógica (is_active=False).
        """
        return super().get_queryset().filter(is_active=True)


class Cliente(models.Model):
    """
    Modelo que representa a un Cliente dentro del sistema.
    
    Gestiona la información de los clientes, diferenciando entre personas
    físicas y jurídicas, y estableciendo la relación con su usuario de acceso.
    
    Historia de Usuario GE-8: Se incorpora el campo `segmento` para clasificar 
    a los clientes en base a las categorías predefinidas por Global Exchange.
    
    Historia de Usuario GE-63: Se incorpora el campo `is_active` para permitir
    bajas lógicas sin borrado físico, manteniendo la trazabilidad histórica.
    """
    TIPO_FISICA = 'FISICA'
    TIPO_JURIDICA = 'JURIDICA'
    
    TIPO_CLIENTE_CHOICES = [
        (TIPO_FISICA, 'Persona Física'),
        (TIPO_JURIDICA, 'Persona Jurídica'),
    ]

    # Lista predefinida de categorías/segmentos para Global Exchange (Historia GE-8)
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
    
    # GE-8: Segmentación del cliente
    segmento = models.CharField(
        max_length=20,
        choices=SEGMENTO_CHOICES,
        default='ESTANDAR',
        verbose_name="Segmento / Categoría",
        help_text="Permite clasificar al cliente para diferenciarlo según características de Global Exchange."
    )

    # GE-63: Campo para controlar la baja lógica
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Baja lógica: False indica que el cliente está inactivo sin eliminar sus datos físicamente."
    )

    # Se cambia auto_now_add por default=timezone.now para evitar la pregunta en la consola
    fecha_registro = models.DateTimeField(default=timezone.now)

    # MANAGERS (GE-63)
    objects = models.Manager()          # Manager general: trae TODOS los registros (incluyendo inactivos para historial)
    activos = ClienteActiveManager()    # Manager filtrado: trae SOLO los activos (para vistas públicas y listados)

    def soft_delete(self):
        """
        Ejecuta la baja lógica del cliente (GE-63).

        Cambia el estado del atributo `is_active` a False y guarda el cambio
        en la base de datos sin borrar físicamente el registro.
        """
        self.is_active = False
        self.save()

    def __str__(self):
        """
        Representación en formato de cadena (string) del objeto Cliente.
        
        Returns:
            str: Razón social si es Jurídica, de lo contrario Nombre y Apellido.
                 En ambos casos incluye el identificador en paréntesis y su estado lógico.
        """
        estado = "Activo" if self.is_active else "Inactivo"
        
        if self.tipo_cliente == self.TIPO_JURIDICA:
            return f"{self.razon_social} ({self.identificador}) - [{estado}]"
        
        # En caso de ser persona física maneja posibles valores nulos
        nombre_str = self.nombre if self.nombre else ""
        apellido_str = self.apellido if self.apellido else ""
        return f"{nombre_str} {apellido_str}".strip() + f" ({self.identificador}) - [{estado}]"