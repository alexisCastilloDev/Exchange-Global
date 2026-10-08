"""Helper de tests para el formato numérico con separador de miles.

Desde que el sistema muestra los números con "." de miles y "," de
decimales (ver ``USE_THOUSAND_SEPARATOR`` y ``FORMAT_MODULE_PATH`` en
``global_exchange.settings.base``), los tests que verifican un monto
renderizado no pueden comparar contra el literal plano (por ejemplo
``'747400.00'``): tienen que comparar contra lo que el template
realmente produce. En vez de repetir a mano la lógica de formateo (y
arriesgarse a que quede desincronizada si el formato cambia), este
helper le pide al propio motor de templates de Django que renderice el
valor con ``|floatformat``, igual que lo hacen las pantallas reales.
"""

from django.template import Context, Template


def formato(valor, decimales=2):
    """Devuelve el valor formateado tal como lo mostraría un template.

    Args:
        valor: Un ``Decimal``, ``int`` o ``float``.
        decimales (int): Cantidad de decimales, igual que el argumento
            de ``|floatformat``.

    Returns:
        str: El valor formateado (por ejemplo ``'747.400,00'``).
    """
    return Template('{{ valor|floatformat:decimales }}').render(
        Context({'valor': valor, 'decimales': decimales})
    )
