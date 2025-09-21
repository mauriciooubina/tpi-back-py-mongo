import os
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from . import repository as repo
from .consumer import run_consumer, process_event

BROKER_MODE = os.getenv("BROKER_MODE", "none").lower()  # "none" | "sqs"

app = FastAPI(title="Retail POC - Python + Mongo (SNS→SQS, multi-cola)")

@app.on_event("startup")
async def startup():
    await repo.init_mongo()
    if BROKER_MODE != "none":
        app.state.consumer_task = asyncio.create_task(run_consumer())
    else:
        app.state.consumer_task = None

@app.on_event("shutdown")
async def shutdown():
    task = getattr(app.state, "consumer_task", None)
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass
    await repo.close_mongo()

@app.get("/health")
async def health():
    return {"status": "ok", "broker": BROKER_MODE}

# ---------- USERS ----------
@app.get("/users")
async def list_users(limit: int = 50):
    return await repo.list_users(limit)

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    u = await repo.get_user(user_id)
    if not u:
        raise HTTPException(404, "not found")
    return u

# ---------- PRODUCTS ----------
@app.get("/products")
async def list_products(limit: int = 50):
    return await repo.list_products(limit)

@app.get("/products/{product_id}")
async def get_product(product_id: str):
    p = await repo.get_product(product_id)
    if not p:
        raise HTTPException(404, "not found")
    return p

# ---------- Endpoint para simular eventos (sin AWS) ----------

class Event(BaseModel):
    event_id: str
    type: str
    occurred_at: str
    source: str
    data: dict

@app.post("/_simulate/event")
async def simulate_event(evt: Event):
    applied = await process_event(evt.model_dump())
    return {"applied": applied}