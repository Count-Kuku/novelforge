"""Evaluation metrics and pending-review conversion for web research."""

from __future__ import annotations

import hashlib
from collections import Counter
from urllib.parse import urlsplit

from novelforge.core.schemas import (
    VerifiedWebResearchClaim,
    WebResearchEvaluation,
    WebResearchPlan,
)


SOURCE_KINDS = {"official", "secondary", "community", "fanon", "general"}


def evaluate_web_research_state(task: dict) -> WebResearchEvaluation:
    result = dict(task.get("result") or {})
    plan = WebResearchPlan.model_validate(
        result.get("plan") or {"topic": task.get("topic") or "未命名", "branches": []}
    )
    branch_results = result.get("branch_results", []) if isinstance(result.get("branch_results"), list) else []
    raw_hit_count = 0
    covered = 0
    for item in branch_results:
        search_result = item.get("search_result", {}) if isinstance(item, dict) else {}
        rows = search_result.get("results", []) if isinstance(search_result, dict) else []
        raw_hit_count += len(rows) if isinstance(rows, list) else 0
        if rows:
            covered += 1
    hits = result.get("search_hits", []) if isinstance(result.get("search_hits"), list) else []
    selected = result.get("selected_hits", []) if isinstance(result.get("selected_hits"), list) else []
    sources = result.get("fetched_sources", []) if isinstance(result.get("fetched_sources"), list) else []
    claims = result.get("claims", []) if isinstance(result.get("claims"), list) else []
    extractions = result.get("page_extractions", []) if isinstance(result.get("page_extractions"), list) else []
    verified = result.get("verified_claims", []) if isinstance(result.get("verified_claims"), list) else []
    unique_domains = {
        str(urlsplit(str(item.get("url") or "")).hostname or "").lower()
        for item in hits
    }
    requested_kinds = {branch.source_kind for branch in plan.branches}
    found_kinds = {
        kind
        for item in hits
        for kind in (item.get("source_kinds") or [])
        if kind in SOURCE_KINDS
    }
    authority_distribution = Counter(str(item.get("authority") or "unknown") for item in verified)
    candidate_claim_count = sum(int(item.get("candidate_claim_count") or 0) for item in extractions)
    rejected_claim_count = sum(int(item.get("rejected_claim_count") or 0) for item in extractions)
    valid_claims = len(claims)
    supported = sum(1 for item in verified if item.get("verification_status") == "supported")
    contested = sum(1 for item in verified if item.get("verification_status") == "contested")
    return WebResearchEvaluation(
        planned_branch_count=len(plan.branches),
        covered_branch_count=covered,
        branch_coverage=covered / len(plan.branches) if plan.branches else 0.0,
        raw_hit_count=raw_hit_count,
        unique_hit_count=len(hits),
        duplicate_rate=max(raw_hit_count - len(hits), 0) / raw_hit_count if raw_hit_count else 0.0,
        unique_domain_count=len(unique_domains),
        source_kind_coverage=len(found_kinds & requested_kinds) / len(requested_kinds) if requested_kinds else 0.0,
        fetch_success_rate=min(len(sources) / len(selected), 1.0) if selected else 0.0,
        candidate_claim_count=candidate_claim_count,
        rejected_claim_count=rejected_claim_count,
        evidence_valid_rate=min(valid_claims / candidate_claim_count, 1.0) if candidate_claim_count else 0.0,
        corroboration_rate=supported / len(verified) if verified else 0.0,
        conflict_rate=contested / len(verified) if verified else 0.0,
        authority_distribution=dict(authority_distribution),
    )


def verified_claim_to_pending_item(
    claim: VerifiedWebResearchClaim | dict,
    task_id: str,
    *,
    story_id: str = "",
) -> dict:
    item = claim if isinstance(claim, VerifiedWebResearchClaim) else VerifiedWebResearchClaim.model_validate(claim)
    pending_seed = f"{task_id}|{item.claim_id}"
    evidence = [
        {
            "source_title": evidence.source_title,
            "quote": evidence.quote,
            "note": evidence.source_url,
            "source_url": evidence.source_url,
            "source_kind": evidence.source_kind,
            "authority": evidence.authority,
            "content_hash": evidence.content_hash,
            "source_relative_path": evidence.source_relative_path,
            "claim_id": evidence.claim_id,
            "stance": evidence.stance,
        }
        for evidence in item.evidence
    ]
    return {
        "pending_id": f"pending_web_{hashlib.sha256(pending_seed.encode('utf-8')).hexdigest()[:24]}",
        "category": item.category,
        "story_id": str(story_id or ""),
        "name": item.name,
        "summary": item.summary,
        "details": item.details,
        "evidence": evidence,
        "confidence": item.confidence,
        "importance": item.importance,
        "evidence_strength": item.evidence_strength,
        "canon_status": (
            "canon"
            if item.authority == "official" and item.verification_status != "contested"
            else "unknown"
        ),
        "extraction_mode": "web_research",
        "tags": item.tags,
        "research_task_id": task_id,
        "web_claim_id": item.claim_id,
        "verification_status": item.verification_status,
        "verification_rationale": item.verification_rationale,
        "supporting_claim_ids": item.supporting_claim_ids,
        "contradicting_claim_ids": item.contradicting_claim_ids,
        "source_urls": item.source_urls,
        "source_kinds": item.source_kinds,
        "risk_label": "high" if item.verification_status == "contested" else "medium",
        "risk_reasons": [item.verification_rationale] if item.verification_rationale else [],
    }
