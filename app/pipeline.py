from pathlib import Path
from app.report import plain,reason_counts
from app.modules.m1_sessions.rules import apply as stage1
from app.modules.m2_products.rules import apply as stage2
from app.modules.m3_leases.rules import apply as stage3
from app.modules.m4_concurrency.rules import apply as stage4
from app.modules.m5_excess.rules import apply as stage5
from app.modules.m6_purchase.rules import apply as stage6
from app.modules.m7_audit.rules import apply as stage7

def sample_text():
    return (Path(__file__).parent.parent/"sample_data"/"instrument.csv").read_text(encoding="utf-8-sig")

def run(text,confirmed=None,interrupt_after=None,on_confirm=None):
    """按本地事件回放一次许可核验。

    confirmed：上一轮已确认的租约裁决，用于中断后从断点续算；
    interrupt_after：仅测试/演练用，裁决若干条新租约后抛出 RunInterrupted。
    """
    ctx={"text":text,"quarantine":[],"reports":[]}
    if confirmed:ctx["confirmed"]=confirmed
    if interrupt_after is not None:ctx["interrupt_after"]=interrupt_after
    if on_confirm is not None:ctx["on_confirm"]=on_confirm
    ctx["reports"].append(stage1(ctx))
    ctx["reports"].append(stage2(ctx))
    ctx["reports"].append(stage3(ctx))
    ctx["reports"].append(stage4(ctx))
    ctx["reports"].append(stage5(ctx))
    ctx["reports"].append(stage6(ctx))
    ctx["reports"].append(stage7(ctx))
    ctx.pop("text",None)
    ctx.pop("on_confirm",None)
    ctx.pop("interrupt_after",None)
    ctx.pop("confirmed",None)
    ctx["resumed"]=bool(confirmed)
    if confirmed:ctx["resumed_leases"]=len(confirmed)
    ctx["reasons"]=reason_counts(ctx)
    return plain(ctx)
