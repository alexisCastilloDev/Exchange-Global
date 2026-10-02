"""Agrega la comisión personalizada del cliente y ancla los métodos de pago
al perfil de Cliente en lugar del usuario que autentica.

El cambio de FK se hace en varios pasos para remapear los datos existentes:
antes, ``MetodoPago.cliente`` apuntaba al usuario de Keycloak: ahora apunta
al ``Cliente`` que ese usuario tiene como titular (o, si no es titular de
ninguno, al primer cliente al que está asociado como operador).
"""

import django.db.models.deletion
from django.db import migrations, models


def remapear_metodos_pago_a_cliente(apps, schema_editor):
    """Reasigna cada método de pago del usuario titular a su perfil de Cliente."""
    MetodoPago = apps.get_model('clientes', 'MetodoPago')
    Cliente = apps.get_model('clientes', 'Cliente')

    for metodo in MetodoPago.objects.all():
        usuario_id = metodo.cliente_id
        cliente = Cliente.objects.filter(user_id=usuario_id).first()
        if cliente is None:
            cliente = Cliente.objects.filter(usuarios__id=usuario_id).first()
        if cliente is not None:
            metodo.cliente_nuevo_id = cliente.pk
            metodo.save(update_fields=['cliente_nuevo'])
        else:
            metodo.delete()


def remapear_metodos_pago_a_usuario(apps, schema_editor):
    """Revierte el remapeo: vuelve a apuntar al usuario titular del cliente."""
    MetodoPago = apps.get_model('clientes', 'MetodoPago')

    for metodo in MetodoPago.objects.all():
        cliente = metodo.cliente_nuevo
        usuario_id = cliente.user_id if cliente else None
        if usuario_id is not None:
            metodo.cliente_id = usuario_id
            metodo.save(update_fields=['cliente'])
        else:
            metodo.delete()


class Migration(migrations.Migration):
    """Agrega la comisión personalizada y migra los métodos de pago a Cliente."""

    dependencies = [
        ('clientes', '0012_merge_metodopago_normalizar_segmentos'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='comision_personalizada',
            field=models.DecimalField(blank=True, decimal_places=3, help_text='Opcional. Si se define, sobrescribe la comisión de la categoría para dar un trato preferencial único a este cliente.', max_digits=6, null=True, verbose_name='Comisión personalizada (%)'),
        ),
        migrations.AddField(
            model_name='metodopago',
            name='cliente_nuevo',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='metodos_pago_nuevo', to='clientes.cliente'),
        ),
        migrations.RunPython(remapear_metodos_pago_a_cliente, remapear_metodos_pago_a_usuario),
        migrations.RemoveField(
            model_name='metodopago',
            name='cliente',
        ),
        migrations.RenameField(
            model_name='metodopago',
            old_name='cliente_nuevo',
            new_name='cliente',
        ),
        migrations.AlterField(
            model_name='metodopago',
            name='cliente',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='metodos_pago', to='clientes.cliente', verbose_name='Cliente'),
        ),
    ]
