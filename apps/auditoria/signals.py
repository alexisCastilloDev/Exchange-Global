"""Receptores que registran las altas, modificaciones y bajas de los modelos administrativos.

Implementa el primer criterio de aceptación de GE-71 sin tocar ninguna
vista ni modelo existente: en vez de agregar una llamada de auditoría en
cada lugar que guarda un usuario, una divisa, una tasa o un parámetro,
se escuchan las señales ``pre_save``/``post_save``/``post_delete`` de esos
modelos. ``pre_save`` toma una instantánea del registro tal como está en
la base antes de guardar y ``post_save`` la compara con lo guardado, para
dejar constancia de cada campo que cambió con su valor anterior y nuevo.

Solo se registra lo que hace un usuario autenticado en una request que
modifica datos (ver ``apps.auditoria.registro.usuario_responsable``), y
solo si cambió al menos un campo auditado: guardar un formulario sin
modificar nada no deja ningún registro.

Los cambios de roles no pasan por ningún modelo (viven en Keycloak) y se
registran aparte, en ``apps.auditoria.middleware.AuditoriaMiddleware``.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils.text import capfirst

from apps.auditoria.models import RegistroActividad
from apps.auditoria.registro import registrar_actividad, usuario_responsable


@dataclass(frozen=True)
class ModeloAuditado:
    """Describe cómo auditar un modelo.

    Campos de la configuración:

    - ``modelo``: etiqueta ``"app_label.NombreModelo"`` del modelo auditado.
    - ``tipo_recurso``: una de ``RegistroActividad.RECURSO_CHOICES``.
    - ``campos``: campos cuyo cambio se registra. Se listan explícitamente
      para dejar afuera datos técnicos (contraseñas, último acceso, marcas
      de tiempo, "actualizado por") que no son parte de la acción y solo
      llenarían el registro de ruido.
    - ``describir``: función que recibe la instancia y devuelve el texto con
      el que se identifica el registro afectado.
    - ``campo_activo``: campo booleano de la baja lógica; si pasa de
      verdadero a falso, la acción se registra como "Baja".
    - ``anterior_de``: solo para modelos históricos, donde cada
      actualización crea una fila nueva en vez de modificar la existente
      (``Cotizacion``). Recibe la instancia nueva y devuelve la fila que
      reemplaza, para registrar qué valores cambiaron respecto de ella.
    - ``etiquetas``: nombres legibles que reemplazan al ``verbose_name`` de
      algunos campos. Hace falta para ``User``, cuyos ``verbose_name`` son
      los de Django, en inglés (el proyecto usa ``LANGUAGE_CODE = 'en-us'``).
    """

    modelo: str
    tipo_recurso: str
    campos: tuple
    describir: Callable
    campo_activo: Optional[str] = None
    anterior_de: Optional[Callable] = None
    etiquetas: Optional[dict] = None


def _cotizacion_anterior(cotizacion):
    """Devuelve la cotización vigente de la divisa antes de registrar ``cotizacion``."""
    if not cotizacion.divisa_id:
        return None
    return (
        type(cotizacion)._base_manager
        .filter(divisa_id=cotizacion.divisa_id)
        .order_by('-fecha_actualizacion', '-pk')
        .first()
    )


MODELOS_AUDITADOS = (
    ModeloAuditado(
        modelo=settings.AUTH_USER_MODEL,
        tipo_recurso=RegistroActividad.RECURSO_USUARIO,
        campos=('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser'),
        describir=lambda usuario: usuario.get_username(),
        campo_activo='is_active',
        etiquetas={
            'username': 'Nombre de usuario',
            'email': 'Correo electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'is_active': 'Activo',
            'is_staff': 'Acceso al panel de Django',
            'is_superuser': 'Superusuario',
        },
    ),
    ModeloAuditado(
        modelo='clientes.Cliente',
        tipo_recurso=RegistroActividad.RECURSO_CLIENTE,
        # stripe_customer_id queda afuera: lo escribe el sistema al pagar
        # con tarjeta (apps.divisas.pagos_stripe), no un administrador.
        campos=(
            'tipo_cliente', 'identificador', 'nombre', 'apellido', 'razon_social',
            'email', 'segmento', 'comision_personalizada', 'is_active',
        ),
        describir=lambda cliente: f'{cliente.nombre_completo or "Sin nombre"} ({cliente.identificador})',
        campo_activo='is_active',
    ),
    ModeloAuditado(
        modelo='divisas.Divisa',
        tipo_recurso=RegistroActividad.RECURSO_DIVISA,
        campos=('codigo', 'nombre', 'simbolo', 'activa'),
        describir=lambda divisa: f'{divisa.codigo} - {divisa.nombre}',
        campo_activo='activa',
    ),
    ModeloAuditado(
        modelo='divisas.Cotizacion',
        tipo_recurso=RegistroActividad.RECURSO_TASA,
        campos=('tasa_compra', 'tasa_venta'),
        describir=lambda cotizacion: f'Tasa de cambio {cotizacion.divisa.codigo}',
        anterior_de=_cotizacion_anterior,
    ),
    ModeloAuditado(
        modelo='divisas.ConfiguracionComision',
        tipo_recurso=RegistroActividad.RECURSO_PARAMETRO,
        campos=('segmento', 'porcentaje'),
        describir=lambda comision: f'Comisión del segmento {comision.get_segmento_display()}',
    ),
    ModeloAuditado(
        modelo='divisas.ConfiguracionVigencia',
        tipo_recurso=RegistroActividad.RECURSO_PARAMETRO,
        campos=('calculo_vigencia_segundos', 'confirmacion_vigencia_segundos', 'pago_vigencia_segundos'),
        describir=lambda configuracion: 'Tiempos de espera de las operaciones',
    ),
)


def _valor_legible(instancia, campo):
    """Convierte el valor de un campo en el texto que se muestra en el registro.

    Usa la etiqueta de las opciones (``choices``) en vez del valor interno,
    "Sí"/"No" para los booleanos y ``None`` para un valor vacío.
    """
    valor = getattr(instancia, campo.attname)
    if valor is None:
        return None
    if campo.choices:
        return getattr(instancia, f'get_{campo.name}_display')()
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    return str(valor)


def _instantanea(instancia, config):
    """Toma los valores actuales de los campos auditados de una instancia.

    Returns:
        dict: ``{nombre_campo: (valor_crudo, valor_legible)}``. El valor
        crudo se usa para comparar y el legible para guardar en el registro.
    """
    opciones = instancia._meta
    return {
        nombre: (
            getattr(instancia, opciones.get_field(nombre).attname),
            _valor_legible(instancia, opciones.get_field(nombre)),
        )
        for nombre in config.campos
    }


def _etiqueta(config, modelo, nombre_campo):
    """Nombre legible de un campo: el de ``config.etiquetas`` o su ``verbose_name``."""
    if config.etiquetas and nombre_campo in config.etiquetas:
        return config.etiquetas[nombre_campo]
    return capfirst(str(modelo._meta.get_field(nombre_campo).verbose_name))


def _calcular_cambios(config, modelo, anterior, nuevo, campos):
    """Arma la lista de campos que cambiaron entre dos instantáneas.

    Si no hay instantánea anterior (un alta), se listan los campos que
    quedaron con algún valor. Si no hay nueva (una eliminación), los que
    tenían algún valor antes de eliminar.
    """
    cambios = []
    for nombre in campos:
        crudo_anterior, legible_anterior = anterior[nombre] if anterior else (None, None)
        crudo_nuevo, legible_nuevo = nuevo[nombre] if nuevo else (None, None)
        if crudo_anterior == crudo_nuevo or (anterior is None and crudo_nuevo in (None, '')):
            continue
        cambios.append({
            'campo': nombre,
            'etiqueta': _etiqueta(config, modelo, nombre),
            'anterior': legible_anterior,
            'nuevo': legible_nuevo,
        })
    return cambios


def _determinar_accion(config, anterior, nuevo):
    """Clasifica un guardado como alta, baja lógica o modificación."""
    if anterior is None:
        return RegistroActividad.ACCION_ALTA
    if config.campo_activo and anterior[config.campo_activo][0] and not nuevo[config.campo_activo][0]:
        return RegistroActividad.ACCION_BAJA
    return RegistroActividad.ACCION_MODIFICACION


def _crear_receptores(config):
    """Construye los receptores ``pre_save``, ``post_save`` y ``post_delete`` de un modelo."""

    def antes_de_guardar(sender, instance, raw=False, **kwargs):
        """Guarda en la instancia cómo estaba el registro en la base antes de este guardado."""
        instance._auditoria_preparada = False
        if raw or usuario_responsable() is None:
            return
        if config.anterior_de is not None:
            anterior = config.anterior_de(instance) if instance._state.adding else None
        elif instance._state.adding or instance.pk is None:
            anterior = None
        else:
            anterior = sender._base_manager.filter(pk=instance.pk).first()
        instance._auditoria_anterior = _instantanea(anterior, config) if anterior is not None else None
        instance._auditoria_preparada = True

    def despues_de_guardar(sender, instance, created, raw=False, update_fields=None, **kwargs):
        """Registra el alta, modificación o baja si cambió algún campo auditado."""
        if raw or not getattr(instance, '_auditoria_preparada', False):
            return
        instance._auditoria_preparada = False
        usuario = usuario_responsable()
        if usuario is None:
            return
        anterior = instance._auditoria_anterior
        nuevo = _instantanea(instance, config)
        # Con update_fields, Django solo escribe esos campos: cualquier otro
        # valor distinto en memoria no llegó a la base y no es un cambio real.
        campos = config.campos if update_fields is None else [c for c in config.campos if c in update_fields]
        cambios = _calcular_cambios(config, sender, anterior, nuevo, campos)
        if not cambios:
            return
        registrar_actividad(
            usuario=usuario,
            accion=_determinar_accion(config, anterior, nuevo),
            tipo_recurso=config.tipo_recurso,
            recurso_id=instance.pk,
            recurso_descripcion=config.describir(instance),
            cambios=cambios,
        )

    def despues_de_eliminar(sender, instance, **kwargs):
        """Registra la eliminación física de un registro con los valores que tenía."""
        usuario = usuario_responsable()
        if usuario is None:
            return
        cambios = _calcular_cambios(config, sender, _instantanea(instance, config), None, config.campos)
        registrar_actividad(
            usuario=usuario,
            accion=RegistroActividad.ACCION_ELIMINACION,
            tipo_recurso=config.tipo_recurso,
            recurso_id=instance.pk,
            recurso_descripcion=config.describir(instance),
            cambios=cambios,
        )

    return antes_de_guardar, despues_de_guardar, despues_de_eliminar


def conectar_senales():
    """Conecta los receptores de auditoría a cada modelo de ``MODELOS_AUDITADOS``.

    Se conectan con ``weak=False`` porque los receptores son funciones
    creadas en ``_crear_receptores``: sin una referencia fuerte, el
    recolector de basura las eliminaría apenas termina esta función. El
    ``dispatch_uid`` evita conectarlas dos veces si ``ready`` se ejecuta
    más de una vez.
    """
    for config in MODELOS_AUDITADOS:
        modelo = apps.get_model(config.modelo)
        antes, despues, eliminar = _crear_receptores(config)
        uid = f'auditoria_{config.modelo}'
        pre_save.connect(antes, sender=modelo, weak=False, dispatch_uid=f'{uid}_pre_save')
        post_save.connect(despues, sender=modelo, weak=False, dispatch_uid=f'{uid}_post_save')
        post_delete.connect(eliminar, sender=modelo, weak=False, dispatch_uid=f'{uid}_post_delete')
