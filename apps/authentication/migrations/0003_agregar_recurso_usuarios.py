"""
Agrega el RecursoProtegido "usuarios" para poder proteger
/usuarios/ con @requiere_permiso('usuarios').
"""
from django.db import migrations


def cargar_recurso_usuarios(apps, schema_editor):
    RecursoProtegido = apps.get_model('authentication', 'RecursoProtegido')
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    content_type = ContentType.objects.get_for_model(RecursoProtegido)
    grupo_admin, _ = Group.objects.get_or_create(name='admin')

    recurso, _ = RecursoProtegido.objects.get_or_create(
        codigo='usuarios', defaults={'nombre': 'Gestión de usuarios'}
    )
    permiso, _ = Permission.objects.get_or_create(
        codename='acceder_usuarios',
        content_type=content_type,
        defaults={'name': 'Puede acceder a Gestión de usuarios'},
    )
    grupo_admin.permissions.add(permiso)


def revertir(apps, schema_editor):
    RecursoProtegido = apps.get_model('authentication', 'RecursoProtegido')
    RecursoProtegido.objects.filter(codigo='usuarios').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_cargar_recursos_iniciales'),
    ]

    operations = [
        migrations.RunPython(cargar_recurso_usuarios, revertir),
    ]