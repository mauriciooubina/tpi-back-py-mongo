import os
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

_client = None
_db = None

async def init_mongo():
    """Inicializa la conexión a Mongo y crea índices básicos."""
    global _client, _db
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB", "retail_poc")
    _client = AsyncIOMotorClient(mongo_url)
    _db = _client[db_name]
    await _db.users.create_index("email", unique=False)
    await _db.products.create_index("sku", unique=False)

async def close_mongo():
    """Cierra la conexión a Mongo."""
    global _client
    if _client is not None:
        _client.close()

def db():
    """Devuelve el handler de la BD actual."""
    return _db

# ---------- Idempotencia común ----------

async def is_event_applied(event_id: str) -> bool:
    doc = await db().applied_events.find_one({"_id": event_id})
    return doc is not None

async def mark_event_applied(event_id: str):
    try:
        await db().applied_events.insert_one(
            {"_id": event_id, "applied_at": datetime.utcnow().isoformat()}
        )
    except Exception:
        pass

# ---------- USERS ----------

async def upsert_user(data: dict, event_id: str, occurred_at: str):
    user_id = data["user_id"]
    doc = {
        "_id": user_id,
        "email": data.get("email"),
        "name": data.get("name"),
        "status": data.get("status", "ACTIVE"),
        "is_deleted": data.get("is_deleted", False),
        "updated_at": occurred_at,
        "last_event_id": event_id,
    }
    await db().users.update_one({"_id": user_id}, {"$set": doc}, upsert=True)

async def soft_delete_user(user_id: str, event_id: str, occurred_at: str):
    await db().users.update_one(
        {"_id": user_id},
        {"$set": {"is_deleted": True, "deleted_at": occurred_at, "last_event_id": event_id}},
        upsert=True,
    )

async def list_users(limit: int = 50):
    cursor = db().users.find({"is_deleted": {"$ne": True}}).limit(limit)
    return [doc async for doc in cursor]

async def get_user(user_id: str):
    return await db().users.find_one({"_id": user_id})

# ---------- PRODUCTS ----------

async def upsert_product(data: dict, event_id: str, occurred_at: str):
    product_id = data["product_id"]
    doc = {
        "_id": product_id,
        "sku": data.get("sku"),
        "name": data.get("name"),
        "price": data.get("price"),
        "currency": data.get("currency", "USD"),
        "status": data.get("status", "ACTIVE"),
        "is_deleted": data.get("is_deleted", False),
        "updated_at": occurred_at,
        "last_event_id": event_id,
    }
    await db().products.update_one({"_id": product_id}, {"$set": doc}, upsert=True)

async def soft_delete_product(product_id: str, event_id: str, occurred_at: str):
    await db().products.update_one(
        {"_id": product_id},
        {"$set": {"is_deleted": True, "deleted_at": occurred_at, "last_event_id": event_id}},
        upsert=True,
    )

async def list_products(limit: int = 50):
    cursor = db().products.find({"is_deleted": {"$ne": True}}).limit(limit)
    return [doc async for doc in cursor]

async def get_product(product_id: str):
    return await db().products.find_one({"_id": product_id})