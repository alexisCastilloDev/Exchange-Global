"""Creación de los registros de actividad y contexto de la request en curso.

Los receptores de señales (``apps.auditoria.signals``) no reciben la
request, así que no saben quién está guardando un modelo. El
``AuditoriaMiddleware`` deja la request en curso en una ``ContextVar``
(``_request_actual``) y este módulo la consulta para resolver al usuario
responsable. Una ``ContextVar`` (y no una variable global) aísla cada
request aunque el servidor atienda varias en paralelo, en hilos o en
tareas asíncronas distintas.
"""
from contextvars import ContextVar

from apps.auditoria.models import RegistroActividad

_request_actual = ContextVar('auditoria_request_actual', default=None)

# Métodos HTTP que no son una acción del usuario. Una request GET puede
# igual guardar modelos (``apps.users.views.lista_usuarios_view`` sincroniza
# los usuarios con Keycloak en cada visita), pero eso no es una acción
# administrativa que alguien haya enviado: solo se audita lo que llega por
# POST/PUT/PATCH/DELETE, que es como se envía cada formulario de alta,
# modificación o baja del sistema.
METODOS_SEGUROS = frozenset({'GET', 'HEAD', 'OPTIONS', 'TRACE'})


def establecer_request_actual(request):
    """Guarda la request en curso y devuelve el token para restaurar el valor anterior."""
    return _request_actual.set(request)


def restablecer_request_actual(token):
    """Restaura el valor que tenía la request en curso antes de ``establecer_request_actual``."""
    _request_actual.reset(token)


def usuario_responsable():
    """Devuelve el usuario que está realizando una acción auditable, o ``None`` si no la hay.

    Hay una acción auditable solo si hay una request en curso, enviada con
    un método que modifica datos (ver ``METODOS_SEGUROS``) y por un usuario
    autenticado. Fuera de una request (migraciones, comandos, shell) o en
    una request anónima, no hay ningún usuario a quien atribuirle la acción
    y no se registra nada.
    """
    request = _request_actual.get()
    if request is None or request.method in METODOS_SEGUROS:
        return None
    usuario = getattr(request, 'user', None)
    if usuario is None or not usuario.is_authenticated:
        return None
    return usuario


def nombre_de_usuario(usuario):
    """Nombre legible de un usuario para guardar como copia en el registro."""
    return usuario.get_full_name().strip() or usuario.get_username()


def registrar_actividad(usuario, accion, tipo_recurso, recurso_id, recurso_descripcion, cambios):
    """Crea un ``RegistroActividad`` con los datos de la acción realizada.

    Args:
        usuario: usuario que realizó la acción.
        accion: una de ``RegistroActividad.ACCION_CHOICES``.
        tipo_recurso: una de ``RegistroActividad.RECURSO_CHOICES``.
        recurso_id: identificador del registro afectado.
        recurso_descripcion: texto legible que identifica al registro afectado.
        cambios: lista de ``{"campo", "etiqueta", "anterior", "nuevo"}``.

    Returns:
        RegistroActividad: el registro creado.
    """
    return RegistroActividad.objects.create(
        usuario=usuario,
        usuario_nombre=nombre_de_usuario(usuario)[:255],
        accion=accion,
        tipo_recurso=tipo_recurso,
        recurso_id=str(recurso_id)[:64],
        recurso_descripcion=str(recurso_descripcion)[:255],
        cambios=cambios,
    )
