# Retail POC — Backend Python + Mongo (Event‑Driven, SNS→SQS)

POC para demostrar una **migración progresiva** con arquitectura **orientada a eventos**.  
Este servicio (Python + FastAPI + MongoDB) **consume eventos** de **SQS** (publicados por **SNS**) y expone una **API de lectura**. Incluye un endpoint de **simulación** para probar todo sin AWS.

## ✨ Características
- **Dominios:** `users` y `products` (fácil de extender).
- **Eventos soportados:**  
  - Users: `USER_UPSERT` / `USER_DELETED` *(alias: `user.add`, `user.updated`, `user.remove`)*  
  - Products: `PRODUCT_UPSERT` / `PRODUCT_DELETED` *(alias: `product.add`, `product.updated`, `product.remove`)*
- **Idempotencia por `event_id`** (colección `applied_events`).
- **Soft delete** (`is_deleted=true`), los listados no muestran eliminados.
- **Multi-cola SQS**: consumir 1 o varias colas en paralelo (mediante `SQS_QUEUE_URLS`).

---

## 🧱 Arquitectura (POC)

```
[ API Gateway / Legacy Producers ]
            │ (publican eventos a topics SNS)
            ▼
         [ SNS topics ]  ───────────►  [ otras apps ]
            │
            ├─► [ SQS queue: addproductnew ] ──► [ Backend NEW (este) ] ──► [ MongoDB ]
            ├─► [ SQS queue: removeproductnew ] ─┘
            ├─► [ SQS queue: addusernew ]       ┐   (lee y aplica eventos)
            └─► [ SQS queue: removeusernew ]    ┘
                         ▲
                    (opcional: 1 sola cola para todo)
```

En modo **simulación**, SNS/SQS no se usan: enviás eventos a `POST /_simulate/event` para validar la lógica end‑to‑end.

---

## 📁 Estructura

```
.
├─ app/
│  ├─ __init__.py
│  ├─ main.py          # API + startup del consumidor
│  ├─ consumer.py      # Lógica de consumo SQS (multi-cola) + enrutamiento por tipo
│  └─ repository.py    # Acceso a Mongo + idempotencia + dominios (users/products)
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
└─ requests.http       # (opcional) pegadas para VS Code REST Client
```

> **Datos efímeros:** no hay volumen de Mongo definido en la POC. Si corrés `docker compose down -v` se borra la base. Para no perder datos, usá **pause/unpause** o **stop/start** (ver más abajo).

---

## 🔧 Requisitos
- Docker y Docker Compose
- (Opcional) VS Code + extensión **REST Client**
- (Opcional) AWS CLI si vas a probar contra AWS real

---

## 🚀 Quick Start — **Modo Simulación** (sin AWS)

1) **Levantar stack**
```bash
docker compose up -d --build
```

2) **Healthcheck**
```bash
curl http://localhost:8000/health   # → {"status":"ok","broker":"none"}
```

3) **Probar con `requests.http`** (VS Code → “Send Request”)  
   o con `curl`:
```bash
# crear usuario
curl -X POST http://localhost:8000/_simulate/event -H 'Content-Type: application/json' \
  -d '{"event_id":"e-u-1","type":"USER_UPSERT","occurred_at":"2025-09-21T20:00:00Z","source":"legacy","data":{"user_id":"u-101","email":"u101@poc.com","name":"Usuario 101","status":"ACTIVE"}}'
# leer
curl http://localhost:8000/users/u-101
```

> El endpoint ahora devuelve `{ "applied": true|false }` (false si el evento es duplicado o de tipo desconocido).

---

## 🌐 Pasar a **AWS real** (SNS→SQS)

1) Crear en AWS:
   - **SNS topics** (p.ej. `product.add`, `product.remove`, `user.add`, `user.remove`).
   - **SQS queues** (p.ej. `addproductnew`, `removeproductnew`, `addusernew`, `removeusernew`).  
   - **Suscribir** cada SQS al topic correspondiente con **Raw Message Delivery = ON**.
   - **Access policy** en cada SQS para permitir `sns:Publish` desde su topic.

2) Variables de entorno (en `.env` o en `docker-compose.yml`):
```dotenv
BROKER_MODE=sqs
# Una cola:
# SQS_QUEUE_URL=https://sqs.<REGION>.amazonaws.com/<ACCOUNT>/<QUEUE>
# Varias colas (separadas por coma):
SQS_QUEUE_URLS=https://sqs.<REGION>.amazonaws.com/<ACCOUNT>/addproductnew,https://sqs.<REGION>.amazonaws.com/<ACCOUNT>/removeproductnew,https://sqs.<REGION>.amazonaws.com/<ACCOUNT>/addusernew,https://sqs.<REGION>.amazonaws.com/<ACCOUNT>/removeusernew

AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<key>            # si no usás IAM Role
AWS_SECRET_ACCESS_KEY=<secret>     # si no usás IAM Role
# AWS_SESSION_TOKEN=<token>        # (si aplica)

MONGO_URL=mongodb://mongo:27017
MONGO_DB=retail_poc
```

3) **Rebuild + up**
```bash
docker compose up -d --build
curl http://localhost:8000/health   # → {"status":"ok","broker":"sqs"}
```

> **Alias de tipo**: el backend acepta `user.add|user.updated|user.remove` y `product.add|product.updated|product.remove`, además de los canónicos `USER_*` / `PRODUCT_*`.

---

## 🔌 Endpoints
- `GET /health` → `{status, broker}`
- `GET /users?limit=50` → lista (oculta soft‑deleted)
- `GET /users/{user_id}` → documento (incluye soft‑deleted)
- `GET /products?limit=50` → lista (oculta soft‑deleted)
- `GET /products/{product_id}` → documento (incluye soft‑deleted)
- `POST /_simulate/event` → aplica evento (idempotente). **Devuelve `applied: true|false`.**

### Esquema de evento (ejemplos)
**User upsert**
```json
{
  "event_id": "e-123",
  "type": "USER_UPSERT",
  "occurred_at": "2025-09-21T21:00:00Z",
  "source": "legacy",
  "data": {
    "user_id": "u-123",
    "email": "u123@poc.com",
    "name": "Usuario 123",
    "status": "ACTIVE"
  }
}
```
**Product delete (soft)**  
```json
{
  "event_id": "e-456",
  "type": "product.remove",
  "occurred_at": "2025-09-21T21:10:00Z",
  "source": "legacy",
  "data": { "product_id": "p-456" }
}
```

---

## 🧪 Archivo de pruebas (`requests.http`)
Incluí un `requests.http` para VS Code REST Client con **create/update/delete** de usuario y producto.  
Tip: la variable dinámica es **`{{$guid}}`** (no `{{$uuid}}`).

---

## 🛠️ Troubleshooting
- **`applied=false`** al simular: puede ser **duplicado** (`event_id` ya usado) o **tipo desconocido**.  
- **No veo el doc** tras aplicar: revisá `applied_events` y `users/products` en `mongo-express` (`http://localhost:8081`).  
- **Orden por entidad**: si hace falta, usá **SNS/SQS FIFO** y publica con `MessageGroupId=<entity_id>` y `MessageDeduplicationId=<event_id>` (el consumidor no cambia).  
- **No perder datos**: evitá `docker compose down -v`. Preferí **pause/unpause** o **stop/start**.

---

## 📦 Comandos útiles
```bash
# levantar
docker compose up -d --build

# logs
docker compose logs -f backend

# pausar / reanudar
docker compose pause
docker compose unpause

# detener / arrancar (sin borrar)
docker compose stop
docker compose start

# estado
docker compose ps
```

---

## 📜 Licencia
Uso académico / demostración. Ajustá a las políticas de tu organización.
