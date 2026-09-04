"""
Data migration de GE-7: carga los RecursoProtegido base del sistema y
le asigna al Group "admin" los permisos correspondientes.
"""
from django.db import migrations


RECURSOS_INICIALES = [
    ('panel_admin', 'Panel de administración'),
    ('gestion_roles', 'Gestión de roles'),
]


def cargar_recursos(apps, schema_editor):
    RecursoProtegido = apps.get_model('authentication', 'RecursoProtegido')
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    content_type = ContentType.objects.get_for_model(RecursoProtegido)
    grupo_admin, _ = Group.objects.get_or_create(name='admin')

    for codigo, nombre in RECURSOS_INICIALES:
        recurso, creado = RecursoProtegido.objects.get_or_create(
            codigo=codigo, defaults={'nombre': nombre}
        )
        permiso, _ = Permission.objects.get_or_create(
            codename=f'acceder_{codigo}',
            content_type=content_type,
            defaults={'name': f'Puede acceder a {nombre}'},
        )
        grupo_admin.permissions.add(permiso)


def revertir_carga(apps, schema_editor):
    RecursoProtegido = apps.get_model('authentication', 'RecursoProtegido')
    RecursoProtegido.objects.filter(
        codigo__in=[codigo for codigo, _ in RECURSOS_INICIALES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(cargar_recursos, revertir_carga),
    ]