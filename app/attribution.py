def party(r):
    """责任主体：误发补正租约不记使用人，记到领取与补正依据。"""
    if r.get("misissue"):
        return {"kind":"MISISSUE","user":None,"claim_line":r.get("claim_line"),
                "correction_line":r.get("correction_line"),"correction_version":r.get("correction_version")}
    return {"kind":"USER","user":r.get("user"),"claim_line":None,"correction_line":None,"correction_version":None}


def describe(offenders):
    """把责任分配压成一行可读证据：使用人席位与误发补正席位分开。"""
    parts=[]
    for x in offenders:
        if x["kind"]=="MISISSUE":
            basis="/".join(str(v) for v in (x.get("claim_line"),x.get("correction_line")) if v is not None)
            parts.append(f"误发补正 {x['id']}×{x['seats']}（领取/补正行 {basis or '—'}）")
        else:
            parts.append(f"使用人 {x['user'] or '—'} {x['id']}×{x['seats']}")
    return "；".join(parts) or "—"
