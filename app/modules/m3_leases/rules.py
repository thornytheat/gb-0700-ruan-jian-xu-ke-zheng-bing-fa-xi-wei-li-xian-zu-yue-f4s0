from app.report import report,quarantine
from app.checkpoint import RunInterrupted

CORRECTION_KINDS={"withdraw","correct"}

def close_time(kind,start,end,releases):
    if kind=="offline":return end
    times=[t for t in releases if start<=t<end]
    return min(times) if times else end

def _note(audit,row,reason):
    audit.append({"id":row["lease_id"],"reason":reason,"line":row["line"]})

def _claims_for(events,key,lease,end):
    valid=[];audit=[]
    for c in events:
        if c["kind"]!="claim" or (c["canonical"],c["lease_id"])!=key:continue
        if c["rev"]<lease["rev"]:audit.append((c,"STALE_CLAIM"))
        elif not lease["a"]<=c["a"]<end:audit.append((c,"CLAIM_OUTSIDE"))
        else:valid.append(c)
    valid.sort(key=lambda c:(c["a"],c["line"]))
    for c in valid[1:]:audit.append((c,"DUPLICATE_CLAIM"))
    return (valid[0] if valid else None),valid[1:],audit

def _correction_for(events,key,lease):
    """按版本取一条生效补正。

    - 同版本、同内容再次到达：重试，沿用首次依据，不新增责任；
    - 同版本、不同内容：切换冲突，保留上一版许可结果，冲突记录隔离；
    - 低于租约版本：陈旧补正，忽略，保留上一版许可结果。
    """
    chosen=None;audit=[];retry=[];conflict=[]
    for r in events:
        if r["kind"] not in CORRECTION_KINDS or (r["canonical"],r["lease_id"])!=key:continue
        if r["rev"]<lease["rev"]:audit.append((r,"CORRECTION_STALE"));continue
        if chosen is None or r["rev"]>chosen["rev"]:
            if chosen is not None:audit.append((chosen,"CORRECTION_SUPERSEDED"))
            chosen=r;continue
        same=all(chosen[f]==r[f] for f in ("kind","a","b","quantity"))
        (retry if same else conflict).append((r,"CORRECTION_RETRY" if same else "CORRECTION_CONFLICT"))
    return chosen,audit,retry,conflict

def adjudicate(ctx,lease,events,audit):
    """把使用资格（租约）、领取证据和误发补正裁决成一条许可记录。

    - 领取早于补正：租约是当时有效的使用资格，继续可查到原到期；
      该段占席若未被采购覆盖，归误发补正责任，不记使用人。
    - 未领取或领取不早于补正：撤回生效，占席止于补正时刻，
      租约进入"未领取的已撤回租约"，采购覆盖随即释放。
    - 同一补正重试（同版本再次出现）只保留一条依据，不新增责任。
    - 补正版本未递增（切换失败）时忽略该补正，保留上一版许可结果。
    """
    key=(lease["canonical"],lease["lease_id"])
    releases=[x["a"] for x in events if x["kind"]=="release" and x["canonical"]==key[0] and x["lease_id"]==key[1] and x["rev"]==lease["rev"]]
    end=close_time(lease["kind"],lease["a"],lease["b"],releases)
    claim,_later,_claim_audit=_claims_for(events,key,lease,end)
    correction,correction_audit,correction_retry,correction_conflict=_correction_for(events,key,lease)
    for row,reason in _claim_audit+correction_audit:_note(audit,row,reason)
    for row,reason in correction_retry:_note(audit,row,reason)
    for row,reason in correction_conflict:quarantine(ctx,row,reason)
    if lease["kind"]=="offline" and releases:
        audit.append({"id":lease["lease_id"],"reason":"OFFLINE_UNTIL_EXPIRY","line":lease["line"]})

    status="CLAIMED" if claim else "ACTIVE";b=end;withdrawn=False;misissue=False
    if correction is not None:
        misissue=True
        if claim is not None and claim["a"]<correction["a"]:
            status="CLAIMED_CONTINUE";_note(audit,correction,"CLAIMED_CONTINUE")
        else:
            if claim is not None:
                _note(audit,claim,"CLAIM_AFTER_WITHDRAW");claim=None
            status="WITHDRAWN";withdrawn=True;b=max(lease["a"],min(end,correction["a"]))
            _note(audit,correction,"WITHDRAWN_BEFORE_CLAIM")

    record=dict(lease,original_end=end,b=b,status=status,misissue=misissue,withdrawn=withdrawn,
                claimed=claim is not None,claim_at=(claim["a"] if claim else None),
                claim_line=(claim["line"] if claim else None),claim_rev=(claim["rev"] if claim else None),
                correction_version=(correction["rev"] if correction else None),
                correction_line=(correction["line"] if correction else None),
                correction_kind=(correction["kind"] if correction else None),
                correction_at=(correction["a"] if correction else None))
    return record

def apply(ctx):
    chosen={};audit=[]
    for r in ctx["normalized"]:
        if r["kind"] not in {"online","offline"}:continue
        key=(r["canonical"],r["lease_id"])
        if key not in chosen or r["rev"]>chosen[key]["rev"]:
            if key in chosen:audit.append({"id":chosen[key]["lease_id"],"reason":"SUPERSEDED","line":chosen[key]["line"]})
            chosen[key]=r
        elif r["rev"]==chosen[key]["rev"]:
            quarantine(ctx,r,"LEASE_CONFLICT")
        else:audit.append({"id":r["lease_id"],"reason":"SUPERSEDED","line":r["line"]})

    confirmed=dict(ctx.get("confirmed") or {})
    on_confirm=ctx.get("on_confirm")
    out=[];fresh=0
    limit=ctx.get("interrupt_after")
    for key in sorted(chosen):
        # 已确认租约沿用原裁决结果；仍重放其领取/补正依据，保证中断续算后证据完整。
        record=adjudicate(ctx,chosen[key],ctx["normalized"],audit)
        if key in confirmed:
            out.append(confirmed[key]);continue
        out.append(record)
        confirmed[key]=record
        if on_confirm:on_confirm(confirmed)
        fresh+=1
        if limit is not None and fresh>=limit:
            raise RunInterrupted({"leases":{f"{k[0]}\x1f{k[1]}":v for k,v in confirmed.items()},
                                  "confirmed":len(confirmed),"anchor":record["lease_id"]})

    for r in ctx["normalized"]:
        if r["kind"]=="heartbeat":audit.append({"id":r["lease_id"],"reason":"HEARTBEAT_NO_SEAT","line":r["line"]})

    claims=[];corrections=[]
    for r in out:
        if r["claimed"]:
            claims.append({"id":r["lease_id"],"product":r["canonical"],"user":r["user"],
                           "at":r["claim_at"],"line":r["claim_line"],"rev":r["claim_rev"],"status":r["status"]})
        if r["misissue"]:
            corrections.append({"id":r["lease_id"],"product":r["canonical"],"user":r["user"],
                                "at":r["correction_at"],"line":r["correction_line"],"rev":r["correction_version"],
                                "kind":r["correction_kind"],"outcome":r["status"]})

    ctx["leases"]=out;ctx["lease_audit"]=audit
    ctx["confirmed_leases"]={f"{k[0]}\x1f{k[1]}":v for k,v in confirmed.items()}
    ctx["claims"]=claims;ctx["corrections"]=corrections
    ctx["withdrawn_leases"]=[r for r in out if r["withdrawn"] and not r["claimed"]]
    ctx["claimed_leases"]=[r for r in out if r["claimed"]]
    ctx["misissue_leases"]=[r for r in out if r["misissue"]]
    return report(out,在线=sum(r["kind"]=="online" for r in out),离线=sum(r["kind"]=="offline" for r in out),
                  已领取=len(ctx["claimed_leases"]),已撤回未领取=len(ctx["withdrawn_leases"]),误发补正=len(ctx["misissue_leases"]))
