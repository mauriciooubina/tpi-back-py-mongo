import os
import json
import asyncio
from typing import Any, Dict
from . import repository as repo

def normalize_type(t: str) -> str:
    if not t:
        return ""
    key = t.strip().lower()
    aliases = {
        "user_upsert": "USER_UPSERT",
        "user.created": "USER_UPSERT",
        "user.updated": "USER_UPSERT",
        "user.add": "USER_UPSERT",
        "user_deleted": "USER_DELETED",
        "user.remove": "USER_DELETED",
        "product_upsert": "PRODUCT_UPSERT",
        "product.created": "PRODUCT_UPSERT",
        "product.updated": "PRODUCT_UPSERT",
        "product.add": "PRODUCT_UPSERT",
        "product_deleted": "PRODUCT_DELETED",
        "product.remove": "PRODUCT_DELETED",
    }
    return aliases.get(key, t.upper())

async def process_event(evt: Dict[str, Any]) -> bool:
    """Procesa un evento. Devuelve True si aplicó cambios; False si lo ignoró (dup o tipo desconocido)."""
    event_id = evt["event_id"]
    if await repo.is_event_applied(event_id):
        return False

    etype = normalize_type(evt.get("type", ""))
    occurred_at = evt.get("occurred_at")
    data = evt["data"]

    applied = False

    # ----- USERS -----
    if etype == "USER_UPSERT":
        await repo.upsert_user(data, event_id, occurred_at); applied = True
    elif etype == "USER_DELETED":
        await repo.soft_delete_user(data["user_id"], event_id, occurred_at); applied = True

    # ----- PRODUCTS -----
    elif etype == "PRODUCT_UPSERT":
        await repo.upsert_product(data, event_id, occurred_at); applied = True
    elif etype == "PRODUCT_DELETED":
        await repo.soft_delete_product(data["product_id"], event_id, occurred_at); applied = True

    if applied:
        await repo.mark_event_applied(event_id)

    return applied

async def run_sqs_consumer_for(queue_url: str):
    """
    Consumidor SQS (aioboto3) para una cola.
    Si el mensaje viene de SNS sin RawMessageDelivery, desanida outer['Message'].
    """
    import aioboto3
    session = aioboto3.Session()
    region = os.environ.get("AWS_REGION", "us-east-1")

    while True:
        try:
            async with session.client("sqs", region_name=region) as sqs:
                resp = await sqs.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=20,
                )
                for m in resp.get("Messages", []):
                    body = m["Body"]
                    try:
                        outer = json.loads(body)
                        evt = json.loads(outer["Message"]) if isinstance(outer, dict) and "Message" in outer else outer
                    except Exception:
                        evt = json.loads(body)

                    try:
                        await process_event(evt)
                        await sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
                    except Exception:
                        pass
        except Exception:
            await asyncio.sleep(3)

async def run_consumer():
    """
    Lee SQS_QUEUE_URLS (coma-separado) o, si no está, SQS_QUEUE_URL (una sola).
    Crea una tarea por cola en paralelo.
    """
    urls_env = os.getenv("SQS_QUEUE_URLS")
    if urls_env:
        queue_urls = [u.strip() for u in urls_env.split(",") if u.strip()]
    else:
        queue_urls = [os.environ["SQS_QUEUE_URL"]]

    await asyncio.gather(*(run_sqs_consumer_for(u) for u in queue_urls))