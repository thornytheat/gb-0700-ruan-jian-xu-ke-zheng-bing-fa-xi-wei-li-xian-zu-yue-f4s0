from app.report import report
from app.timeops import display
from app.attribution import describe

def reject_stale(current,proposed):
    if proposed<=current:raise ValueError("补传版本须递增")
    return proposed

def _usage_row(r):
    return {"kind":"EXCESS","product":r["product"],"start":display(r["a"]),"end":display(r["b"]),
            "concurrent":r["concurrent"],"capacity":r["capacity"],"available":r["available"],
            "excess":r["excess"],"user_excess":r["user_excess"],"misissue_excess":r["misissue_excess"],
            "status":r["status"],"attribution":describe(r["offenders"]),
            "claim_line":None,"correction_line":None}

def _withdrawn_row(r):
    return {"kind":"WITHDRAWN_UNCLAIMED","product":r["canonical"],"lease_id":r["lease_id"],
            "start":display(r["a"]),"end":display(r["b"]),"expires":display(r["original_end"]),
            "quantity":r["quantity"],"status":r["status"],
            "attribution":"已撤回，未领取，不记使用人",
            "claim_line":None,"correction_line":r.get("correction_line"),
            "correction_version":r.get("correction_version")}

def apply(ctx):
    usage=[_usage_row(r) for r in ctx["usage"] if r["status"]!="PASS"]
    withdrawn=[_withdrawn_row(r) for r in ctx["withdrawn_leases"]]
    ctx["final"]=usage+withdrawn
    # 阻断只看真实超用/采购冲突；未领取撤回是已办结的补正，只展示与留证。
    ctx["blocked"]=bool(usage)
    ctx["result_available"]={r["product"]:r["available_seats"] for r in ctx["purchase"]}
    ctx["result_summary"]={
        "available_seats":ctx["result_available"],
        "user_excess_seat_hours":{r["product"]:str(r["user_excess_seat_hours"]) for r in ctx["purchase"]},
        "misissue_excess_seat_hours":{r["product"]:str(r["misissue_excess_seat_hours"]) for r in ctx["purchase"]},
        "claimed_leases":len(ctx["claimed_leases"]),
        "withdrawn_unclaimed":len(ctx["withdrawn_leases"]),
        "misissue_leases":len(ctx["misissue_leases"]),
    }
    ctx["withdrawn_evidence"]=withdrawn
    ctx["claim_evidence"]=ctx["claims"]
    ctx["correction_evidence"]=ctx["corrections"]
    return report(ctx["lease_audit"],
                  忽略心跳=sum(r["reason"]=="HEARTBEAT_NO_SEAT" for r in ctx["lease_audit"]),
                  离线释放保留=sum(r["reason"]=="OFFLINE_UNTIL_EXPIRY" for r in ctx["lease_audit"]),
                  领取依据=len(ctx["claims"]),补正依据=len(ctx["corrections"]),
                  已领取租约=len(ctx["claimed_leases"]),已撤回未领取=len(withdrawn),
                  可用席位=ctx["result_available"])
