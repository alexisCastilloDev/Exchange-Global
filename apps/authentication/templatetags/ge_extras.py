"""
Utilidades de template para la UI del back-office (sidebar, estados
activos). Nada de esto participa en la autorización real: solo decide
qué ítem de navegación se ve resaltado.
"""
from django import template

register = template.Library()


@register.filter
def en_lista(valor, lista_csv):
    """
    Uso: {% if request.resolver_match.url_name|en_lista:"a,b,c" %}
    Permite marcar como "activa" una entrada del sidebar cuando la URL
    actual corresponde a cualquiera de varias vistas relacionadas
    (ej. crear/editar/asociar usuarios de un mismo módulo).
    """
    if not valor:
        return False
    return valor in [item.strip() for item in lista_csv.split(',')]


@register.filter
def iniciales(nombre_completo):
    """Devuelve hasta 2 iniciales en mayúscula para el avatar del usuario."""
    if not nombre_completo:
        return '?'
    partes = [p for p in nombre_completo.strip().split() if p]
    if not partes:
        return '?'
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()
