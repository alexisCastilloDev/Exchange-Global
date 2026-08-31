from django.db import models
from django.utils import timezone

class Cliente(models.Model):
    TIPO_FISICA = 'FISICA'
    TIPO_JURIDICA = 'JURIDICA'
    
    TIPO_CLIENTE_CHOICES = [
        (TIPO_FISICA, 'Persona Física'),
        (TIPO_JURIDICA, 'Persona Jurídica'),
    ]

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
    
    # Se cambia auto_now_add por default=timezone.now para evitar la pregunta en la consola
    fecha_registro = models.DateTimeField(default=timezone.now)

    def __str__(self):
        if self.tipo_cliente == self.TIPO_JURIDICA:
            return f"{self.razon_social} ({self.identificador})"
        return f"{self.nombre} {self.apellido} ({self.identificador})"