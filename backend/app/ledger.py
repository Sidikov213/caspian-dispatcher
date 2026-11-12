"""Реестр — hash-chain: каждый блок хранит хэш предыдущего. Блокчейном не называем.

Уже работает: хэш блока, добавление блока, проверка цепочки (ими же построены моки).
TODO: хранение в state, эндпоинт подделки на настоящем состоянии.
"""
import hashlib
import json

GENESIS_PREV = "0" * 64
HASH_FIELDS = ("index", "ts", "event", "shipment_id", "checkpoint_node", "doc_hash", "prev_hash")


def block_hash(block: dict) -> str:
    payload = {k: block[k] for k in HASH_FIELDS}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def append_block(chain: list[dict], ts: str, event: str, shipment_id: str,
                 checkpoint_node: str, doc_hash: str) -> dict:
    block = {
        "index": len(chain),
        "ts": ts,
        "event": event,
        "shipment_id": shipment_id,
        "checkpoint_node": checkpoint_node,
        "doc_hash": doc_hash,
        "prev_hash": chain[-1]["hash"] if chain else GENESIS_PREV,
    }
    block["hash"] = block_hash(block)
    chain.append(block)
    return block


def verify_chain(chain: list[dict]) -> int | None:
    """Индекс первого испорченного блока или None, если цепочка цела."""
    prev = GENESIS_PREV
    for b in chain:
        if b["prev_hash"] != prev or block_hash(b) != b["hash"]:
            return b["index"]
        prev = b["hash"]
    return None
