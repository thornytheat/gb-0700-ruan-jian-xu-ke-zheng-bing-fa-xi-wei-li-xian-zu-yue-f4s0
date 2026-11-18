from app.timeops import instant
from app.report import report,quarantine
from app.errors import BusinessError
from app.numbers import number
ALIASES={"CAD-Pro":"CAD","cad":"CAD","CAD":"CAD","Render":"RENDER","RENDER":"RENDER"}
KIND_ALIASES={"online":"online","offline":"offline","heartbeat":"heartbeat","release":"release","capacity":"capacity",
              "claim":"claim","领取":"claim","collect":"claim","activate":"claim",
              "correct":"correct","correction":"correct","withdraw":"correct","revoke":"correct","void":"correct",
              "补正":"correct","撤回":"correct","作废":"correct"}
def product(text):
    if text not in ALIASES:raise BusinessError("PRODUCT","产品未登记")
    return ALIASES[text]

def seats(text):
    value=number(text)
    if value<=0 or value!=value.to_integral_value():raise BusinessError("SEATS","席位须为正整数")
    return int(value)

def kind(text):
    if text not in KIND_ALIASES:raise BusinessError("KIND","事件类型无效")
    return KIND_ALIASES[text]

def apply(ctx):
    out=[]
    for r in ctx["raw"]:
        try:
            x=dict(r);x["canonical"]=product(r["product"]);x["a"]=instant(r["start"]);x["b"]=instant(r["end"]) if r["end"] else x["a"];x["rev"]=int(r["version"]);x["quantity"]=seats(r["seats"]);x["kind_text"]=r["kind"]
            x["kind"]=kind(r["kind"])
            if x["rev"]<1:raise BusinessError("VERSION","版本须为正")
            if x["kind"] in {"online","offline","capacity"} and x["b"]<=x["a"]:raise BusinessError("INTERVAL","租约区间无效")
            out.append(x)
        except (BusinessError,ValueError) as e:quarantine(ctx,r,getattr(e,"code","VERSION"))
    ctx["normalized"]=out;return report(out,产品=len({r["canonical"] for r in out}),有效事件=len(out))
