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

