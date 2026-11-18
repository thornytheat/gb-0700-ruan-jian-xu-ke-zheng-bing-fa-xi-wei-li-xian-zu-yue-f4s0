from app.report import report
from app.attribution import party

def capacity_at(rows,a):
    valid=[r for r in rows if r["a"]<=a<r["b"]]
    if not valid:return 0,False
    version=max(r["rev"] for r in valid);values={r["quantity"] for r in valid if r["rev"]==version}
    return min(values),len(values)>1

def allocate_excess(active,extra):
    """分配超用席位。

    误发补正租约的席位属于发行错误，先承担未覆盖部分，记到补正依据；
    其余按租约开始时间倒序、再按编号倒序记到当时有授权的使用人。
    """
    charged=[]
    ordered=sorted(active,key=lambda r:(bool(r.get("misissue")),r["a"],r["lease_id"]),reverse=True)
    for r in ordered:
        take=min(extra,r["quantity"])
        if take:
            charged.append(dict({"id":r["lease_id"],"seats":take},**party(r)));extra-=take
    return charged

def apply(ctx):
    out=[];capacities=[r for r in ctx["normalized"] if r["kind"]=="capacity"]
    for segment in ctx["segments"]:
        product=segment["product"];caps=[r for r in capacities if r["canonical"]==product]
        cuts=sorted({segment["a"],segment["b"]}|{r[k] for r in caps for k in ("a","b") if segment["a"]<r[k]<segment["b"]})
        for a,b in zip(cuts,cuts[1:]):
            capacity,conflict=capacity_at(caps,a);extra=max(0,segment["count"]-capacity)
            active=[r for r in ctx["leases"] if r["canonical"]==product and r["a"]<=a<r["b"]]
            offenders=allocate_excess(active,extra)
            out.append({"product":product,"a":a,"b":b,"concurrent":segment["count"],"capacity":capacity,
                        "available":max(0,capacity-segment["count"]),
                        "excess":extra,"offenders":offenders,
                        "user_excess":sum(x["seats"] for x in offenders if x["kind"]=="USER"),
                        "misissue_excess":sum(x["seats"] for x in offenders if x["kind"]=="MISISSUE"),
                        "status":"CAPACITY_CONFLICT" if conflict else "OVERUSE" if extra else "PASS"})
    ctx["usage"]=out
    return report(out,超用区间=sum(r["excess"]>0 for r in out),冲突=sum(r["status"]=="CAPACITY_CONFLICT" for r in out),
                  误发补正区间=sum(r["misissue_excess"]>0 for r in out))
