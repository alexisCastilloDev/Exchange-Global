"""
Vistas generales del proyecto: pantalla de bienvenida y panel
protegido de demostración por rol de Keycloak (sesión).

El panel de administración (listado de clientes) y la gestión de
roles ya no viven acá: son responsabilidad de
``apps.clientes.views.PanelAdminView`` y ``apps.users.views``
respectivamente. Antes había acá dos vistas "stub" (``panel_admin`` y
``user_roles``) registradas en las URLs pero que renderizaban sus
templates sin ningún contexto — quedaban siempre vacías/rotas porque
la lógica real vivía en otro lado y nunca se enrutaba. Se eliminaron
para no tener dos implementaciones compitiendo por la misma URL.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def home(request):
    """
    Vista pública de bienvenida.
    """
    return render(request, 'home.html')


@login_required
def panel_protegido(request):
    """
    Vista de prueba para demostrar que el acceso está protegido
    por sesión/token válido (GE-3).
    """
    return render(request, 'panel.html')