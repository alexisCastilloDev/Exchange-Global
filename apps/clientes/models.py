"""
Módulo de modelos para la gestión de clientes.
Incluye las implementaciones de las historias de usuario GE-8 (Segmentación),
GE-63 (Baja lógica) y soporte para asociación Muchos a Muchos con usuarios del sistema.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class ClienteActiveManager(models.Manager):
    """
    Manager personalizado que filtra por defecto únicamente los clientes activos.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class Cliente(models.Model):
    """Modelo que representa a un Cliente dentro del sistema.

    Soporta un usuario titular directo (user) para compatibilidad con formularios y autenticación,
    además de múltiples usuarios del sistema asociados (usuarios) para acceso de operadores.
    """

    TIPO_FISICA = 'FISICA'
    TIPO_JURIDICA = 'JURIDICA'

    TIPO_CLIENTE_CHOICES = [
        (TIPO_FISICA, 'Persona Física'),
        (TIPO_JURIDICA, 'Persona Jurídica'),
    ]

    SEGMENTO_CHOICES = [
        ('ESTANDAR', 'Estándar'),
        ('PREMIUM', 'Premium'),
        ('VIP', 'VIP'),
        ('CORPORATIVO', 'Corporativo'),
    ]

    # CAMBIO 1: Agregado el usuario titular ('user') requerido por los tests y el ClienteForm
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cliente_perfil',
        null=True,
        blank=True,
        verbose_name='Usuario Titular',
        help_text='Usuario propietario o principal vinculado a este perfil de cliente.'
    )

    # Relación Many-to-Many para operadores y usuarios secundarios
    usuarios = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='clientes',
        blank=True,
        verbose_name='Usuarios del Sistema Asociados',
        help_text=(
            'Usuarios que tienen acceso a gestionar o representar a este'
            ' cliente.'
        ),
    )

    tipo_cliente = models.CharField(
        max_length=10,
        choices=TIPO_CLIENTE_CHOICES,
        default=TIPO_FISICA,
        verbose_name='Tipo de Cliente',
    )

    identificador = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Identificador (CI / RUC)',
    )

    nombre = models.CharField(
        max_length=100, blank=True, null=True, verbose_name='Nombre'
    )
    apellido = models.CharField(
        max_length=100, blank=True, null=True, verbose_name='Apellido'
    )
    razon_social = models.CharField(
        max_length=150, blank=True, null=True, verbose_name='Razón Social'
    )

    email = models.EmailField(
        unique=True, null=True, blank=True, verbose_name='Correo Electrónico'
    )

    segmento = models.CharField(
        max_length=20,
        choices=SEGMENTO_CHOICES,
        default='ESTANDAR',
        verbose_name='Segmento / Categoría',
        help_text='Permite clasificar al cliente.',
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='Baja lógica del cliente.',
    )

    fecha_registro = models.DateTimeField(default=timezone.now)

    # MANAGERS
    objects = models.Manager()
    activos = ClienteActiveManager()

    def soft_delete(self):
        self.is_active = False
        self.save()

    @property
    def primer_usuario(self):
        """Retorna el usuario titular o el primer usuario de la relación M2M."""
        return self.user or self.usuarios.first()

    def __str__(self):
        estado = 'Activo' if self.is_active else 'Inactivo'

        if self.tipo_cliente == self.TIPO_JURIDICA:
            return f'{self.razon_social} ({self.identificador}) - [{estado}]'

        nombre_str = self.nombre if self.nombre else ''
        apellido_str = self.apellido if self.apellido else ''
        nombre_completo = f'{nombre_str} {apellido_str}'.strip()
        return f'{nombre_completo} ({self.identificador}) - [{estado}]'
