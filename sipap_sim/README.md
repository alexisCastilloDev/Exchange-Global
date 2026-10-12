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
python manage.py runserver 8001
```

La migración `0002_datos_iniciales` carga, automáticamente:

- Bancos: Itaú, Continental, Ueno, Familiar.
- Billeteras digitales: Tigo Money, Billetera Personal, Zimple.
- Dos cuentas de la casa de cambio (`es_cuenta_casa_de_cambio=True`),
  una en PYG y otra en USD: el destino de cualquier solicitud de cobro.
- Varias cuentas de clientes de prueba, repartidas entre bancos y
  billeteras, en ambas monedas, para poder probar la "banca en línea" y
  el alta de un método de pago en Global Exchange (que valida contra
  `GET /api/cuentas/validar/`):

  | Proveedor | Número de cuenta | Titular | CI/RUC | Moneda | Saldo |
  |---|---|---|---|---|---|
  | Banco Itaú Paraguay | `2000000000000101` | Juan Pérez | `3456789` | PYG | 15.000.000 |
  | Banco Itaú Paraguay | `2000000000000102` | Juan Pérez | `3456789` | USD | 2.000 |
  | Banco Continental | `2000000000000201` | María Gómez | `4567890` | PYG | 8.000.000 |
  | Banco Ueno | `2000000000000301` | Carlos Ruiz | `5678901` | PYG | 500.000 |
  | Banco Familiar | `2000000000000401` | Ana Benítez | `6789012` | USD | 500 |
  | Tigo Money | `2000000000000501` | Juan Pérez | `3456789` | PYG | 1.200.000 |
  | Billetera Personal | `2000000000000601` | María Gómez | `4567890` | PYG | 300.000 |
  | Zimple | `2000000000000701` | Carlos Ruiz | `5678901` | USD | 150 |

  Para agregar más cuentas de prueba (otro banco, otro titular, otro
  saldo), hay dos formas:

  1. **Admin de sipap-sim** (`http://localhost:8001/admin/`, creando antes
     un superusuario con `python manage.py createsuperuser`): entrar a
     "Cuentas" y agregar una fila a mano, elegible al toque.
  2. **Una migración de datos nueva** (para que quede versionada y la
     tengan todos los que clonen el repo): copiar el patrón de
     `core/migrations/0002_datos_iniciales.py` en un archivo
     `0003_mas_cuentas_de_prueba.py`, con `dependencies = [('core', '0002_datos_iniciales')]`,
     y correr `python manage.py migrate` de nuevo.

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
| `POST /api/transferencias/` | La casa de cambio le paga a un cliente (Sprint 5; todavía no la usa Global Exchange). |
| `GET /api/cuentas/validar/?numero=...&documento=...` | Verificar que una cuenta exista y sea del titular indicado. Si es válida, devuelve también `titular`, `proveedor`, `tipo_proveedor` y `moneda`. |

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
