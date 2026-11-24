import hashlib, json
from datetime import datetime, timezone
from app.redis_client import redis_client

async def write_audit_event(event_type: str, payload: dict) -> str:
    last = await redis_client.lindex("audit_chain", 0)
    prev_hash = json.loads(last)["hash"] if last else "GENESIS"
    entry = {
        "type": event_type,
        "payload": payload,
        "prev_hash": prev_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entry_str = json.dumps(entry, sort_keys=True)
    entry["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
    await redis_client.lpush("audit_chain", json.dumps(entry))
    return entry["hash"]
