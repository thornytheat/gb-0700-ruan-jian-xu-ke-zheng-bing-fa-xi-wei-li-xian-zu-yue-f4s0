import sqlite3, json, hashlib
from datetime import datetime, timezone
from app.config import DATA_DIR, RULE_VERSION
from app.errors import BusinessError
from app.report import plain
from app import checkpoint
from app.checkpoint import RunInterrupted

def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"runs.sqlite", timeout=15)
    db.row_factory=sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, decision TEXT NOT NULL DEFAULT '待复核', created TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS checkpoints (digest TEXT PRIMARY KEY, state TEXT NOT NULL, updated TEXT NOT NULL)")
    return db

def digest_for(text):
    return hashlib.sha256((RULE_VERSION+"\n"+text).encode()).hexdigest()

def save(text, result, replace=False):
    digest=digest_for(text)
    ident=digest[:16]
    payload=json.dumps(dict(result,rule_version=RULE_VERSION),ensure_ascii=False)
    with connect() as db:
        if replace:
            db.execute("INSERT INTO runs(id,digest,result,created) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET result=excluded.result",(ident,digest,payload,datetime.now(timezone.utc).isoformat()))
        else:
            db.execute("INSERT OR IGNORE INTO runs(id,digest,result,created) VALUES(?,?,?,?)",(ident,digest,payload,datetime.now(timezone.utc).isoformat()))
    return get(ident)

def execute(text, resume=False, interrupt_after=None):
    """保存一次运行；支持从上次已确认租约续算，失败时保留上一版许可结果。

    - resume=True 时读取同一输入的已确认租约断点；
    - 每次确认一条租约即落盘，中断可续；
    - 成功完成后清除断点，旧结果只在本次完整结果落库后才被替换。
    """
    from app.pipeline import run
    digest=digest_for(text)
    confirmed=None
    if resume:
        state=checkpoint.load(digest)
        if state:confirmed=checkpoint.hydrate(state.get("leases"))
    def on_confirm(cm):
        checkpoint.save(digest,{"leases":plain(checkpoint.pack(cm)),"count":len(cm)})
    try:
        result=run(text,confirmed=confirmed,interrupt_after=interrupt_after,on_confirm=on_confirm)
    except RunInterrupted as exc:
        state=dict(exc.state)
        checkpoint.save(digest,{"leases":plain(state["leases"]),"count":state["confirmed"],"anchor":state.get("anchor")})
        raise
    saved=save(text,result,replace=True)
    checkpoint.clear(digest)
    return saved

def get(ident):
    with connect() as db:
        row=db.execute("SELECT * FROM runs WHERE id=?",(ident,)).fetchone()
    if row is None: raise BusinessError("NOT_FOUND","批次不存在",404)
    item=dict(row);item["result"]=json.loads(item["result"]);item["rule_version"]=item["result"].get("rule_version","2026.11.18.1")
    return item

def history():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT id,revision,decision,created FROM runs ORDER BY created DESC LIMIT 40")]

def checkpoint_state(ident):
    with connect() as db:
        row=db.execute("SELECT digest FROM runs WHERE id=?",(ident,)).fetchone()
        digest=row["digest"] if row else ident
        state=db.execute("SELECT state FROM checkpoints WHERE digest=?",(digest,)).fetchone()
    return json.loads(state["state"]) if state else None

def checkpoint_by_digest(digest):
    return checkpoint.load(digest)

def review(ident,revision,decision):
    if not isinstance(decision,str) or decision not in {"通过","退回"}: raise BusinessError("DECISION","复核决定无效")
    current=get(ident)
    if decision=="通过" and current["result"].get("blocked"):
        raise BusinessError("BLOCKED","存在阻断项，请先修正数据",409)
    with connect() as db:
        changed=db.execute("UPDATE runs SET revision=revision+1,decision=? WHERE id=? AND revision=?",(decision,ident,revision)).rowcount
        if not changed: raise BusinessError("STALE","版本已更新，请刷新",409)
    return get(ident)
