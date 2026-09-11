"""
Elimina RecursoProtegido y sus Permission asociados: la autorización
pasa a controlarse 100% por rol de Keycloak (Django Group), sin capa
intermedia de permisos manuales.
"""
from django.db import migrations


def eliminar_permisos_generados(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    RecursoProtegido = apps.get_model('authentication', 'RecursoProtegido')

    content_type = ContentType.objects.filter(
        app_label='authentication', model='recursoprotegido'
    ).first()
    if content_type:
        Permission.objects.filter(content_type=content_type).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0003_agregar_recurso_usuarios'),
    ]

    operations = [
        migrations.RunPython(eliminar_permisos_generados, noop),
        migrations.DeleteModel(name='RecursoProtegido'),
    ]