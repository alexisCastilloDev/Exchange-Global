# sipap-sim

Proyecto Django pequeño e independiente que simula la red bancaria
paraguaya (bancos y billeteras digitales), para que Global Exchange
pueda probar la HU "Pago por transferencia bancaria vía SIPAP" sin
acceso a la API real de SIPAP (no existe un sandbox público).

No comparte código, base de datos ni proceso con Global Exchange: se
comunican solo por HTTP, como lo harían con un proveedor real.

## Correrlo en desarrollo

```bash
cd sipap_sim
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8001
```

La base arranca completamente vacía: no hay ninguna migración de datos
que cargue bancos, billeteras ni cuentas (eso fue a propósito: así se
comporta exactamente igual en desarrollo, en los tests y en
producción, sin datos fijos versionados en el código que alguien pueda
olvidarse de actualizar). Todo se carga desde el **panel
administrativo**, en `http://localhost:8001/panel/` (`/ingresar/` para
iniciar sesión), con el usuario creado por `createsuperuser` u otro con
`is_staff=True`. No hay autoregistro: los usuarios del panel se crean
por consola, igual que cualquier superusuario de Django.

Desde el panel se da de alta, en este orden:

1. **Bancos y billeteras** (`/panel/proveedores/`): el nombre y el tipo
   (banco o billetera digital) de cada proveedor que va a emitir cuentas.
2. **Cuentas** (`/panel/cuentas/`): número, titular, documento, moneda y
   saldo de cada cuenta, y a qué proveedor pertenece. Todas se cargan
   igual, incluida la que después va a hacer de "casa de cambio" en su
   moneda: este panel ya no decide eso (`es_cuenta_casa_de_cambio` ni
   siquiera está en el formulario de alta ni en el de edición, a
   propósito). Se ve en la lista como información de solo lectura.

Cuál cuenta es la casa de cambio en cada moneda lo designa **Global
Exchange**, no este panel: desde su propia pantalla de administración
("Fondos propios"), identificando la cuenta por número y documento
(`POST /api/casa-de-cambio/<moneda>/designar/`, más abajo). Hasta que
eso no pasa, `POST /api/solicitudes-cobro/` en esa moneda no tiene a
dónde acreditar y responde 400; el panel administrativo de este
simulador avisa en su pantalla principal si alguna moneda con cuentas
cargadas todavía no tiene ninguna designada.

Una cuenta ya cargada también se puede editar ("Editar": número,
titular, documento, moneda o saldo). Sigue sin poder editarse si es la
cuenta de la casa de cambio desde este panel; eso se designa o se
cambia siempre por la API, nunca a mano acá.

Ambas pantallas también permiten eliminar una fila ("Eliminar", con
confirmación). No se puede eliminar un proveedor que todavía tiene
cuentas a su nombre, ni una cuenta que ya participó en alguna
transferencia; el panel lo informa en vez de romper.

En Global Exchange, configurar (`.env`):

```
SIPAP_BASE_URL=http://localhost:8001
SIPAP_API_KEY=sipap-sim-api-key-de-desarrollo
SIPAP_WEBHOOK_SECRET=sipap-sim-webhook-secret-de-desarrollo
```

(deben coincidir con `SIPAP_API_KEY`/`SIPAP_WEBHOOK_SECRET` de este
proyecto — ver `sipap_sim/settings.py`).

## API

Todas las rutas bajo `/api/` exigen `Authorization: Bearer <SIPAP_API_KEY>`.

| Método y ruta | Para qué |
|---|---|
| `POST /api/solicitudes-cobro/` | La casa de cambio pide que un cliente le transfiera. Recibe `monto`, `moneda`, `referencia`, `url_retorno` y, opcionalmente, `cuenta_origen_numero`/`cuenta_origen_documento` (la cuenta del método de pago que el cliente ya tiene guardado en Global Exchange). Devuelve `id` y `link_pago`. |
| `GET /api/transferencias/<id>/` | Consultar el estado de una transferencia. |
| `POST /api/transferencias/` | La casa de cambio le paga a un cliente. |
| `GET /api/cuentas/validar/?numero=...&documento=...` | Verificar que una cuenta exista y sea del titular indicado. Si es válida, devuelve también `titular`, `proveedor`, `tipo_proveedor` y `moneda`. |
| `GET /api/casa-de-cambio/<moneda>/` | Saldo de la cuenta de la casa de cambio en esa moneda (`moneda`, `saldo`). Global Exchange lleva su propio espejo de este saldo y no depende de este endpoint para operar; queda disponible para verificación externa o reconciliación manual. 404 si esa moneda no tiene ninguna cuenta de la casa de cambio designada. |
| `GET /api/casa-de-cambio/<moneda>/cuenta/` | Qué cuenta real (`numero`, `titular`, `proveedor`) está designada como la casa de cambio en esa moneda. 404 si todavía no hay ninguna. |
| `POST /api/casa-de-cambio/<moneda>/designar/` | Global Exchange designa cuál de sus cuentas en sipap-sim es la casa de cambio en esa moneda, identificándola por `numero` y `documento` (igual que `GET /api/cuentas/validar/`). Si ya había otra designada en esa moneda, se le quita la marca: nunca puede haber dos a la vez. 404 si no existe ninguna cuenta con ese número y documento; 400 si la encontrada es de otra moneda. |
| `GET /api/casa-de-cambio/<moneda>/movimientos/` | Historial de transferencias (entradas y salidas) de la cuenta de la casa de cambio en esa moneda, las más recientes primero (`?limite=`, por defecto 50, tope 200). |

`link_pago` abre la "banca en línea" simulada (`/pagar/<id>/`, sin
autenticación: la usa el cliente desde su navegador, no Global
Exchange). Si la solicitud trajo `cuenta_origen_numero`/`cuenta_origen_documento`,
la reconoce directamente (muestra esa cuenta y su saldo disponible, sin
ofrecer elegir entre todas las cuentas del sistema) y solo deja aprobar
o rechazar; el monto siempre es el solicitado, el cliente no lo puede
cambiar. Si el saldo de la cuenta no alcanza, se informa "Saldo
insuficiente" y no se aprueba nada. Una solicitud sin esos datos no
tiene ninguna cuenta para mostrar
y la "banca en línea" devuelve un error en vez de listar cuentas de
otros clientes de prueba.

Cada cambio de estado se notifica a Global Exchange
(`GLOBAL_EXCHANGE_WEBHOOK_URL`) con un `POST` firmado
(`X-Sipap-Signature`, HMAC-SHA256 sobre el cuerpo con
`SIPAP_WEBHOOK_SECRET`).

## Simular fallas

La variable de entorno `SIM_MODO_FALLA` permite probar, desde Global
Exchange, los casos en que SIPAP no responde:

- `""` (vacío): comportamiento normal.
- `"error"`: la API responde 500.
- `"lento"`: tarda 15 segundos en responder (más que cualquier timeout
  razonable del lado de Global Exchange).

## Tests

```bash
cd sipap_sim
python -m pytest
```
