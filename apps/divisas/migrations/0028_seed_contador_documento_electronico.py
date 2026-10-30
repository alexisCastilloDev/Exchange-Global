"""Siembra los contadores de numeración de Factura Segura con los rangos reales habilitados.

Esta migración NO asigna ningún número (``ultimo_asignado`` queda en
``None``, "nada usado todavía"): solo registra, una vez, cuál es el
rango que Factura Segura habilitó para este ESI en el ambiente de
TEST, tal como fue comunicado por su equipo de soporte. Los números
en sí son un recurso real y finito (no hay forma de "reponerlos"), así
que el rango se guarda acá para que ``ContadorDocumentoElectronico.
siguiente_numero`` sea la única fuente de verdad sobre qué número sigue.

Antes de cualquier emisión real, un administrador debe confirmar con
Factura Segura cuántos números del rango de Facturas ya se consumieron
fuera de este sistema (en las pruebas manuales que llevaron a esta
integración, se reportaron 11 números disponibles sobre un rango
nominal de 12 — ``0000623`` a ``0000634`` — por lo que es posible que
``0000623`` ya esté usado) y ajustar ``ultimo_asignado`` manualmente
si corresponde, en vez de confiar a ciegas en que el rango completo
está intacto.
"""
from django.db import migrations


FACTURA = '1'
NOTA_CREDITO = '5'

RANGOS = [
    (FACTURA, 623, 634),
    (NOTA_CREDITO, 241, 252),
]


def sembrar_contadores(apps, schema_editor):
    ContadorDocumentoElectronico = apps.get_model('divisas', 'ContadorDocumentoElectronico')
    for tipo_documento, desde, hasta in RANGOS:
        ContadorDocumentoElectronico.objects.update_or_create(
            tipo_documento=tipo_documento,
            defaults={'desde': desde, 'hasta': hasta},
        )


def eliminar_contadores(apps, schema_editor):
    ContadorDocumentoElectronico = apps.get_model('divisas', 'ContadorDocumentoElectronico')
    ContadorDocumentoElectronico.objects.filter(
        tipo_documento__in=[tipo for tipo, _, _ in RANGOS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0027_contadordocumentoelectronico_documentoelectronico'),
    ]

    operations = [
        migrations.RunPython(sembrar_contadores, eliminar_contadores),
    ]
