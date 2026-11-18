from decimal import Decimal
from app.report import report

def seat_hours(rows):
    return sum((r["b"]-r["a"])*r["excess"]/Decimal(3600) for r in rows)

def _split(rows,seats):
    return sum(((r["b"]-r["a"])*r[seats]/Decimal(3600) for r in rows if r[seats]),Decimal(0))

def apply(ctx):
    out=[]
    for p in sorted({r["product"] for r in ctx["usage"]}):
        rows=[r for r in ctx["usage"] if r["product"]==p]
        out.append({"product":p,"peak":max(r["concurrent"] for r in rows),
                    "available_seats":min(r["available"] for r in rows),
                    "excess_seat_hours":seat_hours(rows),
                    "user_excess_seat_hours":_split(rows,"user_excess"),
                    "misissue_excess_seat_hours":_split(rows,"misissue_excess"),
                    "overuse_segments":sum(r["excess"]>0 for r in rows)})
    ctx["purchase"]=out
    ctx["balance"]={"input":ctx["input_count"],"accepted":ctx["input_count"]-len(ctx["quarantine"])-ctx["blank_rows"],"quarantined":len(ctx["quarantine"]),"blank":ctx["blank_rows"]}
    return report(out,产品=len(out),超用席位小时=sum((r["excess_seat_hours"] for r in out),Decimal(0)),
                  使用人席位小时=sum((r["user_excess_seat_hours"] for r in out),Decimal(0)),
                  误发补正席位小时=sum((r["misissue_excess_seat_hours"] for r in out),Decimal(0)),
                  已撤回未领取=len(ctx.get("withdrawn_leases",[])))
