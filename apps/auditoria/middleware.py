"""Middleware que da contexto a la auditoría y registra los cambios de roles."""
import logging

from django.contrib.auth import get_user_model
from django.urls import Resolver404, resolve

from apps.auditoria.models import RegistroActividad
from apps.auditoria.registro import (
    establecer_request_actual,
    registrar_actividad,
    restablecer_request_actual,
    usuario_responsable,
)

logger = logging.getLogger(__name__)

# Roles que habilitan ``apps.users.views.editar_roles_view`` (ver su
# decorador ``requiere_permiso('gestion_roles')``, que también deja pasar
# a 'admin').
ROLES_GESTION_ROLES = frozenset({'gestion_roles', 'admin'})


class AuditoriaMiddleware:
    """Deja la request en curso disponible para la auditoría y registra los cambios de roles.

    Las señales de ``apps.auditoria.signals`` consultan la request que
    este middleware guarda (ver ``apps.auditoria.registro``) para saber
    qué usuario realizó cada acción.

    Los roles, en cambio, no se guardan en ningún modelo de Django: viven
    en Keycloak y ``apps.users.views.editar_roles_view`` los cambia
    directo por su Admin API, así que no hay ninguna señal que escuchar.
    Para registrarlos sin modificar esa vista, en un POST a ``editar_roles``
    este middleware consulta los roles del usuario antes y después de
    ejecutar la vista, y registra la diferencia si la hay.
    """

    def __init__(self, get_response):
        """Guarda la siguiente aplicación de la cadena de middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Procesa la request con la auditoría habilitada para ella."""
        token = establecer_request_actual(request)
        try:
            usuario_objetivo = self._usuario_objetivo_de_edicion_de_roles(request)
            if usuario_objetivo is None:
                return self.get_response(request)
            return self._procesar_edicion_de_roles(request, usuario_objetivo)
        finally:
            restablecer_request_actual(token)

    def _usuario_objetivo_de_edicion_de_roles(self, request):
        """Devuelve el usuario cuyos roles se editan en esta request, o ``None`` si no es el caso.

        Solo aplica a un POST a ``editar_roles`` de quien tiene permiso de
        gestionar roles: para cualquier otro, la vista rechaza la request
        sin cambiar nada y no hace falta consultar Keycloak.
        """
        if request.method != 'POST' or usuario_responsable() is None:
            return None
        try:
            coincidencia = resolve(request.path_info)
        except Resolver404:
            return None
        if coincidencia.url_name != 'editar_roles':
            return None
        if not ROLES_GESTION_ROLES & set(request.session.get('keycloak_roles', [])):
            return None
        return get_user_model().objects.filter(pk=coincidencia.kwargs.get('user_id')).first()

    def _procesar_edicion_de_roles(self, request, usuario_objetivo):
        """Ejecuta la vista y registra los roles agregados o quitados al usuario."""
        roles_anteriores = self._consultar_roles(usuario_objetivo)
        response = self.get_response(request)
        if roles_anteriores is None:
            return response
        roles_nuevos = self._consultar_roles(usuario_objetivo)
        if roles_nuevos is None or set(roles_nuevos) == set(roles_anteriores):
            return response
        registrar_actividad(
            usuario=request.user,
            accion=RegistroActividad.ACCION_MODIFICACION,
            tipo_recurso=RegistroActividad.RECURSO_ROL,
            recurso_id=usuario_objetivo.pk,
            recurso_descripcion=f'Roles de {usuario_objetivo.get_username()}',
            cambios=[{
                'campo': 'roles',
                'etiqueta': 'Roles',
                'anterior': ', '.join(sorted(roles_anteriores)) or None,
                'nuevo': ', '.join(sorted(roles_nuevos)) or None,
            }],
        )
        return response

    @staticmethod
    def _consultar_roles(usuario):
        """Roles actuales del usuario en Keycloak, o ``None`` si no se pudieron consultar.

        Llama a ``obtener_roles_de_usuario`` a través de ``apps.users.views``,
        la misma referencia que usa la vista, para consultar Keycloak
        exactamente igual que ella. Un error de Keycloak no debe impedir la
        edición de roles: se registra en el log y la auditoría de esa
        request se omite.
        """
        from apps.users import views as users_views
        try:
            return users_views.obtener_roles_de_usuario(usuario.email)
        except Exception:  # noqa: BLE001 - cualquier falla de Keycloak
            logger.warning('No se pudieron consultar los roles de %s para auditarlos.', usuario.email, exc_info=True)
            return None
