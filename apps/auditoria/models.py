"""Modelo del registro inmutable de actividades administrativas (GE-71).

Cada fila responde las cuatro preguntas del primer criterio de
aceptación: *quién* realizó la acción (``usuario`` y ``usuario_nombre``),
*cuándo* (``fecha``), *sobre qué registro* (``tipo_recurso``,
``recurso_id`` y ``recurso_descripcion``) y *qué cambió* (``cambios``).
Las filas las crean exclusivamente los receptores de
``apps.auditoria.signals`` y el ``AuditoriaMiddleware``; ninguna vista
las modifica ni las elimina, y el propio modelo lo impide (ver
``RegistroActividad.save`` y ``RegistroActividadQuerySet``).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

MENSAJE_INMUTABLE = 'El registro de actividades es inmutable: no se puede modificar ni eliminar.'


class RegistroActividadQuerySet(models.QuerySet):
    """QuerySet que bloquea las modificaciones y eliminaciones masivas.

    ``Model.save``/``Model.delete`` solo cubren las operaciones sobre una
    instancia; ``QuerySet.update`` y ``QuerySet.delete`` escriben directo
    en la base sin pasar por ellas, así que también se bloquean acá.
    """

    def update(self, **kwargs):
        """Rechaza cualquier actualización masiva, salvo la que hace Django al borrar un usuario.

        La única excepción es poner ``usuario`` en ``NULL``: es lo que
        ejecuta Django por ``on_delete=SET_NULL`` cuando se elimina el
        usuario que realizó la acción. Bloquearla impediría borrar ese
        usuario, y el registro no pierde información porque el nombre
        queda guardado en ``usuario_nombre``.
        """
        if kwargs == {'usuario': None}:
            return super().update(**kwargs)
        raise ValidationError(MENSAJE_INMUTABLE)

    def delete(self):
        """Rechaza siempre la eliminación masiva de registros."""
        raise ValidationError(MENSAJE_INMUTABLE)


class RegistroActividad(models.Model):
    """Una acción administrativa realizada por un usuario del sistema."""

    ACCION_ALTA = 'ALTA'
    ACCION_MODIFICACION = 'MODIFICACION'
    ACCION_BAJA = 'BAJA'
    ACCION_ELIMINACION = 'ELIMINACION'
    ACCION_CHOICES = [
        (ACCION_ALTA, 'Alta'),
        (ACCION_MODIFICACION, 'Modificación'),
        (ACCION_BAJA, 'Baja'),
        (ACCION_ELIMINACION, 'Eliminación'),
    ]

    RECURSO_USUARIO = 'USUARIO'
    RECURSO_ROL = 'ROL'
    RECURSO_DIVISA = 'DIVISA'
    RECURSO_TASA = 'TASA'
    RECURSO_PARAMETRO = 'PARAMETRO'
    RECURSO_CLIENTE = 'CLIENTE'
    RECURSO_CHOICES = [
        (RECURSO_USUARIO, 'Usuario'),
        (RECURSO_ROL, 'Roles de usuario'),
        (RECURSO_CLIENTE, 'Cliente'),
        (RECURSO_DIVISA, 'Divisa'),
        (RECURSO_TASA, 'Tasa de cambio'),
        (RECURSO_PARAMETRO, 'Parámetro de operación'),
    ]

    fecha = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Fecha y hora')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actividades_registradas',
        verbose_name='Usuario',
    )
    # Copia del nombre al momento de la acción: sigue mostrando quién fue
    # aunque después el usuario se renombre o se elimine (SET_NULL).
    usuario_nombre = models.CharField(max_length=255, verbose_name='Nombre del usuario')
    accion = models.CharField(max_length=15, choices=ACCION_CHOICES, verbose_name='Acción')
    tipo_recurso = models.CharField(max_length=15, choices=RECURSO_CHOICES, verbose_name='Tipo de registro')
    recurso_id = models.CharField(max_length=64, verbose_name='Identificador del registro')
    recurso_descripcion = models.CharField(max_length=255, verbose_name='Registro afectado')
    # Lista de {"campo", "etiqueta", "anterior", "nuevo"}, uno por campo cambiado.
    cambios = models.JSONField(default=list, blank=True, verbose_name='Cambios')

    objects = RegistroActividadQuerySet.as_manager()

    class Meta:
        """Ordena el registro de la actividad más reciente a la más antigua."""
        verbose_name = 'Registro de actividad'
        verbose_name_plural = 'Registro de actividades'
        ordering = ['-fecha', '-pk']

    def __str__(self):
        """Resume quién hizo qué acción sobre qué registro."""
        return f'{self.usuario_nombre} · {self.get_accion_display()} · {self.recurso_descripcion}'

    def save(self, *args, **kwargs):
        """Permite crear el registro, pero nunca modificar uno ya guardado."""
        if not self._state.adding:
            raise ValidationError(MENSAJE_INMUTABLE)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Impide eliminar un registro de actividad."""
        raise ValidationError(MENSAJE_INMUTABLE)
