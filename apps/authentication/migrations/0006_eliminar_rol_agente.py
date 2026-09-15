"""Elimina el rol local legado agente sin modificar usuarios ni clientes."""

from django.db import migrations


def eliminar_rol_agente(apps, schema_editor):
    """Borra el grupo agente y sus relaciones locales si todavía existe."""
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='agente').delete()


class Migration(migrations.Migration):
    """Limpia el rol duplicado que fue reemplazado por analista_cambiario."""

    dependencies = [
        ('authentication', '0005_historial_baja'),
    ]

    operations = [
        migrations.RunPython(eliminar_rol_agente, migrations.RunPython.noop),
    ]