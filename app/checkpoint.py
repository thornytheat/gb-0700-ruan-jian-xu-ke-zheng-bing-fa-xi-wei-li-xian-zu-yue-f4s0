import json
from datetime import datetime, timezone
from decimal import Decimal

TIME_FIELDS=("a","b","original_end","claim_at","correction_at")
KEY_SEP="\x1f"


class RunInterrupted(Exception):
    """租约裁决中断：携带已确认的租约结果，供后续从断点续算。"""

    def __init__(self,state):
        super().__init__("租约裁决已中断，已保留确认结果")
        self.code="INTERRUPTED"
        self.state=state


def _key(text):
    product,_,lease=text.partition(KEY_SEP)
    return (product,lease)


def pack(confirmed):
    """把按产品+租约号索引的确认结果转成可持久化的 JSON 结构。"""
    return {f"{k[0]}{KEY_SEP}{k[1]}":v for k,v in confirmed.items()}


def hydrate(packed):
    """把持久化（JSON字符串时间、字符串键）的断点恢复成可计算记录。"""
    out={}
    for key,record in (packed or {}).items():
        item=dict(record)
        for field in TIME_FIELDS:
            value=item.get(field)
            if value is None or isinstance(value,Decimal):continue
            item[field]=Decimal(str(value))
        out[_key(key)]=item
    return out


def load(digest):
    from app.store import connect
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS checkpoints (digest TEXT PRIMARY KEY, state TEXT NOT NULL, updated TEXT NOT NULL)")
        row=db.execute("SELECT state FROM checkpoints WHERE digest=?",(digest,)).fetchone()
    if row is None:return None
    return json.loads(row["state"])


def save(digest,state):
    from app.store import connect
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS checkpoints (digest TEXT PRIMARY KEY, state TEXT NOT NULL, updated TEXT NOT NULL)")
        db.execute("INSERT INTO checkpoints(digest,state,updated) VALUES(?,?,?) ON CONFLICT(digest) DO UPDATE SET state=excluded.state,updated=excluded.updated",
                   (digest,json.dumps(state,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))


def clear(digest):
    from app.store import connect
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS checkpoints (digest TEXT PRIMARY KEY, state TEXT NOT NULL, updated TEXT NOT NULL)")
        db.execute("DELETE FROM checkpoints WHERE digest=?",(digest,))
