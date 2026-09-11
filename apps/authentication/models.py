"""
Modelo auxiliar para GE-7: permite que cada funcionalidad protegida del
sistema (ej. "panel_admin", "clientes", "usuarios") tenga su propio
Permission de Django, asignable por rol (Group).

Como Django genera permisos por MODELO y no por instancia, no alcanza
con declarar un único permiso fijo en Meta.permissions — se genera un
Permission distinto por cada RecursoProtegido, dinámicamente en save().
"""
from django.conf import settings
from django.db import models


class HistorialBaja(models.Model):
    """Auditoría inmutable de las bajas lógicas del sistema."""

    TIPO_USUARIO = 'USUARIO'
    TIPO_DIVISA = 'DIVISA'
    TIPO_CLIENTE = 'CLIENTE'
    TIPO_RECURSO_CHOICES = [
        (TIPO_USUARIO, 'Usuario'),
        (TIPO_DIVISA, 'Divisa'),
        (TIPO_CLIENTE, 'Cliente'),
    ]

    tipo_recurso = models.CharField(max_length=10, choices=TIPO_RECURSO_CHOICES)
    recurso_id = models.PositiveBigIntegerField()
    recurso_nombre = models.CharField(max_length=255)
    causa = models.TextField()
    realizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bajas_realizadas',
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Historial de baja'
        verbose_name_plural = 'Historial de bajas'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.get_tipo_recurso_display()}: {self.recurso_nombre}'
