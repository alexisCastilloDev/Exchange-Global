# Conversación con IA — Cálculo de importes de operaciones

**Fecha:** 15/09/2026  
**Herramienta:** GitHub Copilot  
**Proyecto:** Global Exchange

## Contexto

El sistema tenía un simulador de conversión entre divisas, pero no contaba con
un flujo separado de compra y venta, comisión aplicable ni una forma de
invalidar un cálculo cuando pasaba demasiado tiempo.

## Conversación simulada

**Desarrollador:** El usuario cliente debe conocer cuánto pagará o recibirá
antes de confirmar una operación.

**IA:** Se implementó un flujo específico para comprar y vender divisas. Cada
operación permite elegir una divisa y un monto, utiliza la cotización vigente,
calcula la comisión y presenta el desglose antes de confirmar.

**Desarrollador:** ¿Cómo se diferencia la tasa de compra de la de venta?

**IA:** En una compra se aplica la tasa de venta y la comisión se suma al monto
bruto. En una venta se aplica la tasa de compra y la comisión se descuenta del
monto bruto. La comisión está configurada actualmente en `1.00%`.

**Desarrollador:** ¿Qué ocurre si la cotización no existe o cambia mientras el
usuario espera?

**IA:** Si la divisa no tiene cotización vigente, el cálculo no se crea y se
muestra un error. Cuando sí existe, el cálculo se guarda con UUID, tasa,
comisión, importe final y fecha de vencimiento. La vigencia configurada es de
300 segundos. La confirmación se rechaza después de ese momento y obliga a
recalcular.

## Cambios implementados

- Nuevo modelo `CalculoOperacion` con tasa, comisión, monto final, usuario y
  vencimiento.
- Nueva migración `0003_calculooperacion`.
- Nuevo `CalculoOperacionForm`.
- Vistas para `/divisas/operar/compra/` y `/divisas/operar/venta/`.
- Confirmación protegida por usuario y por vigencia.
- Menús visibles de Comprar divisas y Vender divisas.
- Desglose visual de monto origen, tasa, comisión e importe final.
- Parámetros configurables `COMISION_OPERACION_PORCENTAJE` y
  `CALCULO_OPERACION_VIGENCIA_SEGUNDOS`.
- Cinco pruebas específicas y suite completa actualizada.

## Verificación

La suite completa terminó con `102 passed, 0 failed`. Las pruebas nuevas
cubren compra, venta, comisión, divisa sin cotización, vencimiento y presencia
de ambos accesos en el menú.