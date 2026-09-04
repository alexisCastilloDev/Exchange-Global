"""
Migración para la Historia de Usuario: asociación de Cliente con Usuarios
a través de email (relación muchos a muchos) en vez del vínculo 1 a 1
por documento que existía antes (campo `user`).

Pasos, en orden:
1. Agrega el nuevo campo `usuarios` (ManyToMany).
2. Copia los datos: para cada Cliente que tenía `user` asignado,
   agrega ese mismo usuario a la nueva relación `usuarios` (para no
   perder los vínculos ya existentes).
3. Elimina el campo `user` (OneToOne), ya obsoleto.
"""
from django.conf import settings
from django.db import migrations, models


def migrar_user_a_usuarios(apps, schema_editor):
    Cliente = apps.get_model('clientes', 'Cliente')
    for cliente in Cliente.objects.exclude(user__isnull=True):
        cliente.usuarios.add(cliente.user_id)


def revertir_usuarios_a_user(apps, schema_editor):
    # No se puede reconstruir un OneToOne a partir de un M2M con
    # posibles múltiples usuarios por cliente, así que no se revierte
    # el dato (solo queda disponible el rollback de esquema).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0006_cliente_is_active'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='usuarios',
            field=models.ManyToManyField(
                blank=True,
                related_name='clientes_asociados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuarios Autorizados',
            ),
        ),
        migrations.RunPython(migrar_user_a_usuarios, revertir_usuarios_a_user),
        migrations.RemoveField(
            model_name='cliente',
            name='user',
        ),
    ]