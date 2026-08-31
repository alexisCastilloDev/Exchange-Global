"""
Modelo auxiliar para GE-7: permite que cada funcionalidad protegida del
sistema (ej. "panel_admin", "clientes", "usuarios") tenga su propio
Permission de Django, asignable por rol (Group).

Como Django genera permisos por MODELO y no por instancia, no alcanza
con declarar un único permiso fijo en Meta.permissions — se genera un
Permission distinto por cada RecursoProtegido, dinámicamente en save().
"""
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import models


class RecursoProtegido(models.Model):
    codigo = models.SlugField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100)

    def save(self, *args, **kwargs):
        es_nuevo = self._state.adding
        super().save(*args, **kwargs)
        if es_nuevo:
            content_type = ContentType.objects.get_for_model(RecursoProtegido)
            Permission.objects.get_or_create(
                codename=f'acceder_{self.codigo}',
                content_type=content_type,
                defaults={'name': f'Puede acceder a {self.nombre}'},
            )

    def __str__(self):
        return self.nombre