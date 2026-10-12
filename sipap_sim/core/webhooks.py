"""Envío de confirmaciones a Global Exchange cuando una transferencia se resuelve."""

import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def enviar_confirmacion(transferencia):
    """Firma y envía a Global Exchange el cambio de estado de una transferencia.

    El cuerpo y el encabezado ``X-Sipap-Signature`` siguen exactamente el
    formato que espera ``apps.divisas.pagos_sipap._procesar_confirmacion_sipap``
    del lado de Global Exchange. Si la entrega falla (Global Exchange caído,
    red cortada), no se reintenta: es el mismo riesgo que correría un banco
    real, y Global Exchange ya maneja el caso vía expiración por vencimiento.
    """
    monto = transferencia.monto_acreditado if transferencia.monto_acreditado is not None else transferencia.monto_solicitado
    payload = {
        'id_operacion': transferencia.id,
        'referencia': transferencia.referencia,
        'estado': transferencia.estado,
        'monto': float(monto),
        'moneda': transferencia.moneda,
        'banco_origen': transferencia.cuenta_origen.proveedor.nombre if transferencia.cuenta_origen else None,
        'fecha': (transferencia.resuelto_en or transferencia.creado_en).isoformat(),
    }
    cuerpo = json.dumps(payload).encode('utf-8')
    firma = hmac.new(settings.SIPAP_WEBHOOK_SECRET.encode('utf-8'), cuerpo, hashlib.sha256).hexdigest()

    try:
        requests.post(
            settings.GLOBAL_EXCHANGE_WEBHOOK_URL,
            data=cuerpo,
            headers={'Content-Type': 'application/json', 'X-Sipap-Signature': firma},
            timeout=10,
        )
    except requests.exceptions.RequestException:
        logger.warning('No se pudo notificar a Global Exchange la transferencia %s', transferencia.id)
