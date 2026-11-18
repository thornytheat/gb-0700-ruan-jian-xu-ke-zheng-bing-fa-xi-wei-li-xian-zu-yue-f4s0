import os, shutil
import pytest
from decimal import Decimal

from app.pipeline import run
from app import store
from app.checkpoint import RunInterrupted, hydrate, pack

HEADER="lease_id,product,user,start,end,kind,version,seats\n"

def text(*rows):
    return HEADER+"\n".join(rows)+"\n"

CAP="CAP1,CAD,,2026-11-18T00:00:00+00:00,2026-11-20T00:00:00+00:00,capacity,1,2"

def lease(lease_id,kind="offline",start="00",end="10",rev=1,user=None):
    return f"{lease_id},CAD,{user or 'u'+lease_id},{'2026-11-18T'+start+':00:00+00:00'},{'2026-11-18T'+end+':00:00+00:00' if end else ''},{kind},{rev},1"

def at(hour): return f"2026-11-18T{hour}:00:00+00:00"

def event(lease_id,kind,hour,rev=1,user=None):
    return f"{lease_id},CAD,{user or 'u'+lease_id},{at(hour)},,{kind},{rev},1"


def test_claim_before_correction_keeps_lease_until_expiry():
    r=run(text(CAP,lease("L1"),event("L1","claim","01"),event("L1","correct","02",rev=2)))
    item=r["leases"][0]
    assert item["status"]=="CLAIMED_CONTINUE"
    assert item["b"]==item["original_end"]          # 领取后继续到到期
    assert item["claim_line"]==4 and item["correction_line"]==5
    assert r["withdrawn_leases"]==[]                # 不进入已撤回


def test_claim_after_correction_is_withdrawn():
    r=run(text(CAP,lease("L1"),event("L1","correct","02",rev=2),event("L1","claim","03",rev=2)))
    item=r["leases"][0]
    assert item["status"]=="WITHDRAWN"
    assert Decimal(item["b"])==Decimal(item["a"])+Decimal(7200)
    assert any(x["reason"]=="CLAIM_AFTER_WITHDRAW" for x in r["lease_audit"])
    assert [x["lease_id"] for x in r["withdrawn_leases"]]==["L1"]


def test_unclaimed_correction_retracts_and_frees_capacity():
    r=run(text(CAP,lease("L1"),lease("L2"),lease("L3"),
               event("L3","correct","05",rev=2)))
    assert [x["lease_id"] for x in r["withdrawn_leases"]]==["L3"]
    first=r["usage"][0]
    assert first["concurrent"]==3 and first["capacity"]==2 and first["excess"]==1
    # 撤回后采购覆盖释放：05:00 之后并发 2，可用 0；10:00 到期后可用 2
    assert r["usage"][-1]["available"]==0
    assert r["purchase"][0]["available_seats"]==0


def test_misissue_excess_not_charged_to_user():
    r=run(text(CAP,lease("L1"),lease("L2"),lease("L3"),event("L3","correct","05",rev=2)))
    over=[u for u in r["usage"] if u["excess"]]
    assert over and over[0]["user_excess"]==0 and over[0]["misissue_excess"]==1
    blamed=[x for u in over for x in u["offenders"] if x["kind"]=="USER"]
    assert blamed==[]
    mis=[x for u in over for x in u["offenders"] if x["kind"]=="MISISSUE"]
    assert mis and mis[0]["user"] is None and mis[0]["correction_line"]==6
    assert r["purchase"][0]["user_excess_seat_hours"]=="0"
    assert Decimal(str(r["purchase"][0]["misissue_excess_seat_hours"]))>0


def test_identical_correction_retry_deduped_at_input():
    base=[CAP,lease("L1"),lease("L2"),lease("L3"),event("L3","correct","05",rev=2)]
    once=run(text(*base))
    twice=run(text(*(base+[event("L3","correct","05",rev=2)])))
    assert len(twice["corrections"])==len(once["corrections"])==1
    assert twice["purchase"]==once["purchase"]
    assert twice["usage"]==once["usage"]
    assert any(q["reason"]=="DUPLICATE_EVENT" for q in twice["quarantine"])


def test_same_correction_retry_under_other_kind_alias_adds_no_responsibility():
    base=[CAP,lease("L1"),lease("L2"),lease("L3"),event("L3","correct","05",rev=2)]
    once=run(text(*base))
    retried=run(text(*(base+[event("L3","withdraw","05",rev=2)])))
    assert len(retried["corrections"])==len(once["corrections"])==1
    assert retried["purchase"]==once["purchase"]
    assert retried["usage"]==once["usage"]
    assert retried["withdrawn_leases"]==once["withdrawn_leases"]
    assert any(x["reason"]=="CORRECTION_RETRY" for x in retried["lease_audit"])
    assert not any(x["reason"]=="CORRECTION_RETRY" for x in once["lease_audit"])


def test_same_version_conflicting_correction_keeps_previous_result():
    baseline=run(text(CAP,lease("L1"),event("L1","correct","02",rev=2)))
    conflicted=run(text(CAP,lease("L1"),event("L1","correct","02",rev=2),
                        event("L1","correct","07",rev=2)))
    assert conflicted["leases"][0]==baseline["leases"][0]
    assert conflicted["usage"]==baseline["usage"]
    assert any(x["reason"]=="CORRECTION_CONFLICT" for x in conflicted["quarantine"])
    assert [x["lease_id"] for x in conflicted["withdrawn_leases"]]==["L1"]


def test_resume_from_confirmed_leases_matches_full_run(tmp_path):
    os.environ["DATA_DIR"]=str(tmp_path)
    store.DATA_DIR=tmp_path
    body=text(CAP,lease("L1"),event("L1","claim","01"),event("L1","correct","02",rev=2),
              lease("L2"),event("L2","correct","03",rev=2),lease("L3"))
    full=store.execute(body)
    shutil.rmtree(tmp_path); tmp_path.mkdir()
    with pytest.raises(RunInterrupted):
        store.execute(body,interrupt_after=2)
    state=store.checkpoint_by_digest(store.digest_for(body))
    assert state["count"]==2
    resumed=store.execute(body,resume=True)
    assert resumed["id"]==full["id"]
    for key in ("leases","usage","purchase","claims","corrections","withdrawn_leases","final","blocked"):
        assert resumed["result"][key]==full["result"][key]
    assert resumed["result"]["resumed"] is True and resumed["result"]["resumed_leases"]==2
    assert store.checkpoint_by_digest(store.digest_for(body)) is None


def test_failed_switch_keeps_previous_saved_result(tmp_path):
    os.environ["DATA_DIR"]=str(tmp_path); store.DATA_DIR=tmp_path
    body=text(CAP,lease("L1"))
    previous=store.execute(body)
    with pytest.raises(RunInterrupted):
        store.execute(text(CAP,lease("L1"),lease("L2")),interrupt_after=0)
    assert store.get(previous["id"])["result"]==previous["result"]


def test_checkpoint_hydrate_roundtrip():
    record={"a":Decimal(10),"b":Decimal(20),"original_end":Decimal(30),"lease_id":"L1","quantity":1}
    packed=pack({("CAD","L1"):record})
    restored=hydrate({k:{"a":str(v["a"]),"b":str(v["b"]),"original_end":str(v["original_end"]),"lease_id":"L1","quantity":1} for k,v in packed.items()})
    assert restored[("CAD","L1")]["b"]==Decimal(20)


def test_invalid_higher_version_switch_keeps_last_valid_correction():
    # 版本 3 的补正席位无效，在归一化隔离；裁决保留版本 2 的上一条结果。
    bad="L1,CAD,uL1,2026-11-18T09:00:00+00:00,,correct,3,N/A"
    r=run(text(CAP,lease("L1"),event("L1","correct","02",rev=2),bad))
    item=r["leases"][0]
    assert item["status"]=="WITHDRAWN" and item["correction_version"]==2
    assert any(q["reason"]=="MISSING" for q in r["quarantine"])
    assert [x["lease_id"] for x in r["withdrawn_leases"]]==["L1"]


def test_withdrawn_does_not_block_review_but_overuse_does():
    clean=run(text(CAP,lease("L1"),event("L1","correct","02",rev=2)))
    assert clean["withdrawn_leases"] and clean["blocked"] is False
    over=run(text(CAP,lease("L1"),lease("L2"),lease("L3")))
    assert over["blocked"] is True


def test_available_seats_and_attribution_share_evidence():
    from pathlib import Path
    from app.exporter import evidence_csv
    from app import store
    body=Path("sample_data/instrument-corrections.csv").read_text(encoding="utf-8")
    a=store.execute(body)
    lines=evidence_csv(a).splitlines()
    kinds={line.split(",")[3] for line in lines[1:]}
    assert {"manifest","result","attribution","claim","correction","withdrawn_unclaimed"}<=kinds
    assert "available_seats" in lines[1]
