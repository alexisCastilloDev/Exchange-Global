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
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.static import serve as static_serve

from apps.divisas.models import Divisa

DOCUMENTACION_ROOT = settings.BASE_DIR / 'docs' / 'build'


def home(request):
    """
    Vista pública de bienvenida.

    Para visitantes sin sesión iniciada, muestra las tasas vigentes de las
    divisas activas del sistema en lugar de valores de ejemplo.
    """
    divisas_publicas = [
        divisa
        for divisa in Divisa.objects.filter(activa=True).order_by('codigo')
        if divisa.ultima_cotizacion
    ]
    return render(request, 'home.html', {'divisas_publicas': divisas_publicas})


@login_required
def panel_protegido(request):
    """
    Vista de prueba para demostrar que el acceso está protegido
    por sesión/token válido (GE-3).
    """
    return render(request, 'panel.html')


@login_required
def perfil(request):
    """
    Perfil del usuario autenticado: datos básicos, roles efectivos
    (sesión Keycloak) y, si corresponde, el cliente en cuyo nombre
    está operando.
    """
    roles = request.session.get('keycloak_roles', [])
    return render(request, 'perfil.html', {'roles': roles})


@login_required
def documentacion(request, path='index.html'):
    """
    Sirve la documentación técnica (Sphinx) ya compilada en
    ``docs/build/html``, exclusiva de administración, para no exponer
    detalles internos de implementación a clientes ni a roles operativos.
    """
    roles = request.session.get('keycloak_roles', [])
    es_admin = 'admin' in roles or request.user.is_staff or request.user.is_superuser
    if not es_admin:
        raise PermissionDenied
    return static_serve(request, path, document_root=DOCUMENTACION_ROOT)