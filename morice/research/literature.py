"""Source-anchored citation records and explicit, condition-aware disagreements."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .store import utc_now


class LiteratureEvidence:
    def __init__(self, store):
        self.store=store

    def cite(self, project_id, source_id, claim, *, excerpt, region="", citation=None, finding=None):
        source=next((r for r in self.store.snapshot(project_id)["records"] if r["id"]==source_id and r["kind"]=="source" and not r["stale"]),None)
        if source is None: raise ValueError("A current stored source is required for a citation.")
        text=" ".join(source["payload"].get("text","").split())
        excerpt=" ".join(str(excerpt).split())
        if not 5<=len(excerpt)<=800 or excerpt not in text:
            raise ValueError("The cited excerpt must exist in the actual parsed source.")
        if not claim.strip() or len(claim)>2000: raise ValueError("A bounded claim is required.")
        citation=dict(citation or {})
        if citation.get("url") and urlparse(citation["url"]).scheme not in {"https","http"}:
            raise ValueError("Citation URL must be an HTTP(S) source reference.")
        if citation.get("doi") and not re.fullmatch(r"10\.\d{4,9}/\S{1,200}",citation["doi"],re.I):
            raise ValueError("Malformed DOI.")
        metadata=source["payload"].get("metadata",{})
        payload={"claim":claim,"source_type":"paper" if source["payload"]["format"]==".pdf" else "user file",
                 "source_reference":source_id,"source_hash":source["payload"]["sha256"],"relevant_region":region[:200],
                 "excerpt":excerpt,"citation":{**metadata,**citation},"retrieved_at":utc_now(),
                 "reliability_notes":"Source assertion anchored to parsed bytes; citation metadata and scientific truth are not independently certified.",
                 "finding":finding or {}}
        return self.store.add(project_id,"observation",claim,payload,"CITED",(source_id,))

    def compare(self, project_id, evidence_ids):
        records={r["id"]:r for r in self.store.snapshot(project_id)["records"]}
        if not 2<=len(evidence_ids)<=100: raise ValueError("Compare 2–100 source-anchored findings.")
        findings=[]
        for identifier in dict.fromkeys(evidence_ids):
            record=records.get(identifier)
            if record is None or record["provenance"]!="CITED" or record["stale"]:
                raise ValueError("Every comparison input must be current source-linked evidence.")
            findings.append(record)
        comparisons=[]
        for i,a in enumerate(findings):
            for b in findings[i+1:]:
                x,y=a["payload"].get("finding",{}),b["payload"].get("finding",{})
                same_source=a["payload"]["source_hash"]==b["payload"]["source_hash"]
                ca,cb=a["payload"]["citation"],b["payload"]["citation"]
                same_study=same_source or bool(ca.get("doi") and ca.get("doi")==cb.get("doi"))
                if same_study: state="SAME_STUDY_OR_VERSION"
                elif not x.get("metric") or not x.get("conditions") or not y.get("conditions") or x.get("metric")!=y.get("metric") or x.get("conditions")!=y.get("conditions"): state="NON_COMPARABLE"
                elif x.get("direction") in {"positive","negative","none"} and y.get("direction") in {"positive","negative","none"}:
                    state="CONTRADICTORY" if x["direction"]!=y["direction"] else "CONSISTENT_SOURCE_ASSERTIONS"
                else: state="INCONCLUSIVE"
                comparisons.append({"first":a["id"],"second":b["id"],"state":state,
                                    "conditions_first":x.get("conditions"),"conditions_second":y.get("conditions")})
                if state=="CONTRADICTORY": self.store.relate(project_id,a["id"],b["id"],"contradicted_by")
        return {"comparisons":comparisons,"sources":evidence_ids,
                "limitations":"Explicit user-reviewed endpoints/conditions; no averaging incompatible studies or model-generated consensus."}


def evaluate_hypothesis(store, project_id, hypothesis_id, evidence_ids, *, criterion, actual, provenance, field="result.result.value"):
    if provenance not in {"USER_DATA","MEASURED","CALCULATED","SIMULATED"}:
        raise ValueError("Model prose cannot establish a tested hypothesis.")
    records={r["id"]:r for r in store.snapshot(project_id)["records"]}
    hypothesis=records.get(hypothesis_id)
    if hypothesis is None or hypothesis["kind"]!="hypothesis" or not evidence_ids:
        raise ValueError("A hypothesis and real evidence are required.")
    for identifier in evidence_ids:
        record=records.get(identifier)
        if record is None or record["stale"] or record["provenance"] in {"UNKNOWN","INFERRED","HYPOTHESIS"}:
            raise ValueError("Unverified or stale evidence cannot test a hypothesis.")
    import math
    if (type(actual) not in (int,float) or not math.isfinite(actual) or not criterion or set(criterion)-{"min","max"}
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in criterion.values())
            or criterion.get("min",-math.inf)>criterion.get("max",math.inf)):
        raise ValueError("Finite outcome and explicit numeric bounds are required.")
    # An assertion passed by the caller cannot become a tested scientific result.
    # Bind the threshold to a numeric field in the actual persisted evidence.
    evidence=records[evidence_ids[0]]
    if evidence["provenance"]!=provenance or not re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*){0,12}",field):
        raise ValueError("Evidence provenance and numeric field must match the recorded outcome.")
    observed=evidence["payload"]
    try:
        for key in field.split("."): observed=observed[key]
    except (KeyError,TypeError) as exc:
        raise ValueError("The evidence does not contain the specified outcome field.") from exc
    if type(observed) not in (int,float) or not math.isfinite(observed) or observed!=actual:
        raise ValueError("The supplied outcome differs from the actual stored evidence.")
    if provenance in {"CALCULATED","SIMULATED"} and not evidence["payload"].get("execution",{}).get("success",False):
        raise ValueError("A verified recorded tool outcome is required for a computational hypothesis test.")
    passed=criterion.get("min",-math.inf)<=actual<=criterion.get("max",math.inf)
    payload={**hypothesis["payload"],"status":"SUPPORTED" if passed else "CONTRADICTED",
             "tests":list(evidence_ids),"test_criterion":criterion,"observed_value":actual,"outcome_field":field,
             "scope":provenance,"uncertainty":"Conditional on supplied evidence, design and model assumptions; not a universal fact."}
    store.revise(project_id,hypothesis_id,payload)
    for identifier in evidence_ids:
        store.relate(project_id,hypothesis_id,identifier,"tested_by")
    return payload
