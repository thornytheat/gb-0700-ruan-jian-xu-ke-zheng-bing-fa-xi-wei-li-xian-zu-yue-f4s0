import csv,io,json

def _row(run,kind,line,reason,evidence):
    return [run["id"],run["digest"],run["rule_version"],kind,line,reason,json.dumps(evidence,ensure_ascii=False,sort_keys=True)]

def evidence_csv(run):
    out=io.StringIO();writer=csv.writer(out);result=run["result"]
    writer.writerow(["run_id","sha256","rule_version","kind","line","reason","evidence"])
    manifest={"balance":result.get("balance",{}),"decision":run["decision"],"revision":run["revision"],
              "available_seats":result.get("result_available",{}),
              "summary":result.get("result_summary",{}),
              "resumed":result.get("resumed",False),"resumed_leases":result.get("resumed_leases",0)}
    writer.writerow([run["id"],run["digest"],run["rule_version"],"manifest","","",json.dumps(manifest,ensure_ascii=False,sort_keys=True)])
    for row in result.get("final",[]):
        writer.writerow(_row(run,"result",row.get("claim_line") or row.get("correction_line") or "",row.get("status",""),row))
    for row in result.get("quarantine",[]):
        writer.writerow(_row(run,"quarantine",row.get("line",""),row.get("reason",""),row))
    for row in result.get("claim_evidence",[]):
        writer.writerow(_row(run,"claim",row.get("line",""),row.get("status",""),row))
    for row in result.get("correction_evidence",[]):
        writer.writerow(_row(run,"correction",row.get("line",""),row.get("outcome",""),row))
    for row in result.get("withdrawn_evidence",[]):
        writer.writerow(_row(run,"withdrawn_unclaimed",row.get("correction_line",""),"WITHDRAWN_UNCLAIMED",row))
    for row in result.get("usage",[]):
        if row.get("status")=="PASS":continue
        writer.writerow(_row(run,"attribution",row.get("claim_line") or "","",{
            "product":row.get("product"),"a":row.get("a"),"b":row.get("b"),
            "available":row.get("available"),"excess":row.get("excess"),
            "user_excess":row.get("user_excess"),"misissue_excess":row.get("misissue_excess"),
            "offenders":row.get("offenders",[])}))
    return "﻿"+out.getvalue()
