"""Vistas de sipap-sim: la API que consume Global Exchange y la "banca en línea" simulada.

La API (``crear_solicitud_cobro``, ``consultar_transferencia``,
``crear_transferencia_saliente``, ``validar_cuenta``) exige
``Authorization: Bearer <SIPAP_API_KEY>``, como lo haría un proveedor
real. La "banca en línea" (``elegir_cuenta_view``) no: es la pantalla que
ve el cliente en su navegador, no Global Exchange. El panel
administrativo (``panel_view``, ``proveedores_view``, ``cuentas_view``)
tampoco usa esa API key: exige haber iniciado sesión con un usuario de
staff, como cualquier pantalla pensada para un operador humano.
"""

import json
import time
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import CuentaForm, ProveedorPagoForm
from .models import Cuenta, ProveedorPago, Transferencia
from .webhooks import enviar_confirmacion

VIGENCIA_SOLICITUD_SEGUNDOS = 3600


def _autorizado(request):
    """Verifica el encabezado ``Authorization: Bearer <SIPAP_API_KEY>``."""
    return request.META.get('HTTP_AUTHORIZATION') == f'Bearer {settings.SIPAP_API_KEY}'


def _simular_falla_si_corresponde():
    """Aplica ``SIM_MODO_FALLA`` para poder probar errores de comunicación desde Global Exchange.

    Con ``"lento"``, duerme más de lo que cualquier cliente HTTP razonable
    esperaría (Global Exchange usa 10 segundos de timeout), para que la
    llamada termine en un error de conexión igual que si este servicio
    estuviera caído. Con ``"error"``, el llamador debe responder 500.

    Returns:
        bool: ``True`` si corresponde responder con un error simulado.
    """
    if settings.SIM_MODO_FALLA == 'lento':
        time.sleep(15)
    return settings.SIM_MODO_FALLA == 'error'


@csrf_exempt
@require_http_methods(['POST'])
def crear_solicitud_cobro(request):
    """``POST /api/solicitudes-cobro/``: la casa de cambio pide que un cliente le transfiera.

    Body esperado: ``{"monto": ..., "moneda": "PYG"|"USD", "referencia": "...",
    "url_retorno": "...", "cuenta_origen_numero": "...", "cuenta_origen_documento": "..."}``.
    Los dos últimos son opcionales, pero Global Exchange los manda
    siempre: son el número de cuenta y el CI/RUC del método de pago que
    el cliente ya tiene guardado y eligió para pagar (ya validado contra
    ``GET /api/cuentas/validar/`` al registrarlo). Con ellos, la "banca en
    línea" (``elegir_cuenta_view``) reconoce esa cuenta directamente, sin
    pedirle al cliente que elija entre todas las cuentas del sistema.

    Returns:
        JsonResponse: ``{"id": ..., "link_pago": ...}`` (201) si todo sale
        bien; 401 sin autorización, 400 con un payload inválido, sin
        cuenta de la casa de cambio en esa moneda, o si se mandó una
        cuenta de origen que no existe; 500 si ``SIM_MODO_FALLA=error``.
    """
    if not _autorizado(request):
        return JsonResponse({'detalle': 'No autorizado.'}, status=401)
    if _simular_falla_si_corresponde():
        return JsonResponse({'detalle': 'Error simulado (SIM_MODO_FALLA=error).'}, status=500)

    try:
        datos = json.loads(request.body)
        monto = Decimal(str(datos['monto']))
        moneda = datos['moneda']
        referencia = datos['referencia']
    except (KeyError, ValueError, InvalidOperation, TypeError):
        return JsonResponse({'detalle': 'Payload inválido.'}, status=400)

    cuenta_destino = Cuenta.objects.filter(es_cuenta_casa_de_cambio=True, moneda=moneda).first()
    if cuenta_destino is None:
        return JsonResponse({'detalle': f'No hay cuenta de la casa de cambio en {moneda}.'}, status=400)

    cuenta_sugerida = None
    numero_origen = datos.get('cuenta_origen_numero')
    documento_origen = datos.get('cuenta_origen_documento')
    if numero_origen or documento_origen:
        cuenta_sugerida = Cuenta.objects.filter(numero=numero_origen, documento=documento_origen).first()
        if cuenta_sugerida is None:
            return JsonResponse({'detalle': 'La cuenta de origen indicada no existe.'}, status=400)

    transferencia = Transferencia.objects.create(
        cuenta_sugerida=cuenta_sugerida,
        cuenta_destino=cuenta_destino,
        monto_solicitado=monto,
        moneda=moneda,
        referencia=referencia,
        url_retorno=datos.get('url_retorno', ''),
        vence_en=timezone.now() + timedelta(seconds=VIGENCIA_SOLICITUD_SEGUNDOS),
    )

    link_pago = request.build_absolute_uri(reverse('elegir_cuenta', args=[transferencia.id]))
    return JsonResponse({'id': transferencia.id, 'link_pago': link_pago}, status=201)


@require_http_methods(['GET'])
def consultar_transferencia(request, id_transferencia):
    """``GET /api/transferencias/<id>/``: consulta el estado de una transferencia."""
    if not _autorizado(request):
        return JsonResponse({'detalle': 'No autorizado.'}, status=401)

    transferencia = get_object_or_404(Transferencia, pk=id_transferencia)
    transferencia.marcar_vencida_si_corresponde()
    return JsonResponse({
        'id': transferencia.id,
        'estado': transferencia.estado,
        'monto_solicitado': str(transferencia.monto_solicitado),
        'monto_acreditado': (
            str(transferencia.monto_acreditado) if transferencia.monto_acreditado is not None else None
        ),
        'moneda': transferencia.moneda,
        'referencia': transferencia.referencia,
    })


@csrf_exempt
@require_http_methods(['POST'])
def crear_transferencia_saliente(request):
    """``POST /api/transferencias/``: la casa de cambio le paga a un cliente.

    Preparado para la HU de Sprint 5 (acreditación/retiro de fondos);
    Global Exchange todavía no la usa. Acredita de inmediato, sin pasar
    por la "banca en línea" (no hace falta que el cliente apruebe algo
    que le están depositando).

    Body esperado: ``{"cuenta_destino": "<número>", "documento": "<CI o RUC>", "monto": ..., "referencia": "..."}``.
    """
    if not _autorizado(request):
        return JsonResponse({'detalle': 'No autorizado.'}, status=401)
    if _simular_falla_si_corresponde():
        return JsonResponse({'detalle': 'Error simulado (SIM_MODO_FALLA=error).'}, status=500)

    try:
        datos = json.loads(request.body)
        numero_cuenta_destino = datos['cuenta_destino']
        documento = datos['documento']
        monto = Decimal(str(datos['monto']))
        referencia = datos['referencia']
    except (KeyError, ValueError, InvalidOperation, TypeError):
        return JsonResponse({'detalle': 'Payload inválido.'}, status=400)

    cuenta_destino = Cuenta.objects.filter(numero=numero_cuenta_destino, documento=documento).first()
    if cuenta_destino is None:
        return JsonResponse({'detalle': 'No se encontró una cuenta con ese número y documento.'}, status=404)

    cuenta_origen = Cuenta.objects.filter(es_cuenta_casa_de_cambio=True, moneda=cuenta_destino.moneda).first()
    if cuenta_origen is None:
        return JsonResponse({'detalle': f'No hay cuenta de la casa de cambio en {cuenta_destino.moneda}.'}, status=400)

    ahora = timezone.now()
    transferencia = Transferencia.objects.create(
        cuenta_origen=cuenta_origen,
        cuenta_destino=cuenta_destino,
        monto_solicitado=monto,
        monto_acreditado=monto,
        moneda=cuenta_destino.moneda,
        referencia=referencia,
        estado=Transferencia.ESTADO_ACREDITADA,
        resuelto_en=ahora,
        vence_en=ahora,
    )
    cuenta_origen.saldo -= monto
    cuenta_origen.save(update_fields=['saldo'])
    cuenta_destino.saldo += monto
    cuenta_destino.save(update_fields=['saldo'])

    return JsonResponse({'id': transferencia.id, 'estado': transferencia.estado}, status=201)


@require_http_methods(['GET'])
def validar_cuenta(request):
    """``GET /api/cuentas/validar/?numero=...&documento=...``: existe y es del titular indicado.

    Devuelve también el titular, el proveedor (banco o billetera) y la
    moneda cuando la cuenta es válida: Global Exchange los usa para
    completar un método de pago con datos reales (HU "Métodos de pago"),
    en vez de confiar en lo que escriba el cliente — quién es el banco o
    la billetera, y a nombre de quién está la cuenta, lo decide esta
    respuesta, no el formulario.
    """
    if not _autorizado(request):
        return JsonResponse({'detalle': 'No autorizado.'}, status=401)

    cuenta = Cuenta.objects.filter(
        numero=request.GET.get('numero', ''), documento=request.GET.get('documento', ''),
    ).select_related('proveedor').first()
    if cuenta is None:
        return JsonResponse({'valida': False})

    return JsonResponse({
        'valida': True,
        'titular': cuenta.titular,
        'proveedor': cuenta.proveedor.nombre,
        'tipo_proveedor': cuenta.proveedor.tipo,
        'moneda': cuenta.moneda,
    })


def _volver(request, transferencia):
    """Redirige a la URL de retorno que mandó Global Exchange, o muestra un resultado simple si no hay."""
    if transferencia.url_retorno:
        return redirect(transferencia.url_retorno)
    return render(request, 'core/resuelta.html', {'transferencia': transferencia})


def elegir_cuenta_view(request, id_transferencia):
    """"Banca en línea" simulada: aprobar o rechazar con la cuenta ya identificada.

    No deja elegir entre todas las cuentas del sistema (eso filtraría
    datos de otros clientes de prueba): usa directamente
    ``transferencia.cuenta_sugerida``, la que Global Exchange identificó
    al pedir el cobro a partir del método de pago que el cliente ya tiene
    guardado. Si una solicitud no trae ninguna (por ejemplo, llamada a
    mano a la API sin esos datos), no hay nada para mostrarle al cliente:
    se informa el error en vez de ofrecerle una lista para elegir.

    El cliente no elige ni escribe ningún monto: se transfiere siempre el
    monto solicitado, tal cual lo pidió Global Exchange. Solo decide si
    aprueba o rechaza. Al resolverse, envía la confirmación firmada a
    Global Exchange y redirige a la URL de retorno.
    """
    transferencia = get_object_or_404(Transferencia, pk=id_transferencia)
    transferencia.marcar_vencida_si_corresponde()

    if transferencia.estado != Transferencia.ESTADO_PENDIENTE:
        return render(request, 'core/resuelta.html', {'transferencia': transferencia})

    cuenta_origen = transferencia.cuenta_sugerida
    if cuenta_origen is None:
        return render(request, 'core/sin_cuenta.html', {'transferencia': transferencia}, status=409)

    if request.method != 'POST':
        return render(request, 'core/elegir_cuenta.html', {'transferencia': transferencia, 'cuenta': cuenta_origen})

    if request.POST.get('accion') == 'rechazar':
        transferencia.estado = Transferencia.ESTADO_RECHAZADA
        transferencia.resuelto_en = timezone.now()
        transferencia.save(update_fields=['estado', 'resuelto_en'])
        enviar_confirmacion(transferencia)
        return _volver(request, transferencia)

    monto_a_acreditar = transferencia.monto_solicitado

    if cuenta_origen.saldo < monto_a_acreditar:
        return render(request, 'core/elegir_cuenta.html', {
            'transferencia': transferencia, 'cuenta': cuenta_origen,
            'error': f'Saldo insuficiente en {cuenta_origen.numero} (disponible: {cuenta_origen.saldo} {cuenta_origen.moneda}).',
        })

    transferencia.cuenta_origen = cuenta_origen
    transferencia.monto_acreditado = monto_a_acreditar
    transferencia.estado = Transferencia.ESTADO_ACREDITADA
    transferencia.resuelto_en = timezone.now()
    transferencia.save(update_fields=['cuenta_origen', 'monto_acreditado', 'estado', 'resuelto_en'])

    cuenta_origen.saldo -= monto_a_acreditar
    cuenta_origen.save(update_fields=['saldo'])
    transferencia.cuenta_destino.saldo += monto_a_acreditar
    transferencia.cuenta_destino.save(update_fields=['saldo'])

    enviar_confirmacion(transferencia)
    return _volver(request, transferencia)


@staff_member_required(login_url='login')
def panel_view(request):
    """Panel administrativo: punto de entrada para cargar proveedores y cuentas.

    Reemplaza a la migración de datos iniciales como forma de poblar
    este simulador: antes, los bancos, billeteras y cuentas (incluidas
    las de la casa de cambio) venían ya cargados por
    ``core.migrations.0002_datos_iniciales``; ahora se dan de alta desde
    acá, en cualquier entorno, detrás del inicio de sesión.
    """
    moneda_sin_cuenta_casa_de_cambio = [
        codigo for codigo, _ in Cuenta.MONEDA_CHOICES
        if not Cuenta.objects.filter(es_cuenta_casa_de_cambio=True, moneda=codigo).exists()
    ]
    return render(request, 'core/panel.html', {
        'cantidad_proveedores': ProveedorPago.objects.count(),
        'cantidad_cuentas': Cuenta.objects.count(),
        'moneda_sin_cuenta_casa_de_cambio': moneda_sin_cuenta_casa_de_cambio,
    })


@staff_member_required(login_url='login')
def proveedores_view(request):
    """Lista los bancos y billeteras digitales cargados, y permite agregar uno nuevo."""
    if request.method == 'POST':
        form = ProveedorPagoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('proveedores')
    else:
        form = ProveedorPagoForm()
    return render(request, 'core/proveedores.html', {
        'form': form,
        'proveedores': ProveedorPago.objects.all(),
    })


@staff_member_required(login_url='login')
def eliminar_proveedor_view(request, pk):
    """Elimina un banco o billetera, si no tiene ninguna cuenta cargada a su nombre.

    ``Cuenta.proveedor`` usa ``on_delete=PROTECT``: si todavía hay
    cuentas de ese proveedor, Django rechaza el borrado con
    ``ProtectedError`` en vez de arrastrarlas o dejarlas huérfanas; acá
    se lo convierte en un mensaje claro en vez de un error 500.
    """
    proveedor = get_object_or_404(ProveedorPago, pk=pk)
    if request.method == 'POST':
        try:
            proveedor.delete()
            messages.success(request, f'Se eliminó "{proveedor.nombre}".')
        except ProtectedError:
            messages.error(
                request,
                f'No se pudo eliminar "{proveedor.nombre}": todavía tiene cuentas cargadas a su nombre.',
            )
    return redirect('proveedores')


@staff_member_required(login_url='login')
def cuentas_view(request):
    """Lista las cuentas cargadas (de clientes y de la casa de cambio), y permite agregar una nueva."""
    if request.method == 'POST':
        form = CuentaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('cuentas')
    else:
        form = CuentaForm()
    return render(request, 'core/cuentas.html', {
        'form': form,
        'cuentas': Cuenta.objects.select_related('proveedor').all(),
    })


@staff_member_required(login_url='login')
def eliminar_cuenta_view(request, pk):
    """Elimina una cuenta, si no tiene ninguna transferencia asociada (recibida, enviada o sugerida).

    Mismo motivo que ``eliminar_proveedor_view``: las relaciones desde
    ``Transferencia`` hacia ``Cuenta`` también son ``PROTECT``.
    """
    cuenta = get_object_or_404(Cuenta, pk=pk)
    if request.method == 'POST':
        try:
            cuenta.delete()
            messages.success(request, f'Se eliminó la cuenta {cuenta.numero}.')
        except ProtectedError:
            messages.error(
                request,
                f'No se pudo eliminar la cuenta {cuenta.numero}: tiene transferencias asociadas.',
            )
    return redirect('cuentas')
