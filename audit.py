"""audit — verify a source-of-truth project against many mirror copies.

Thin layer over verify(): point it at one source summary and N target summaries (e.g. the same project
copied to several trackers) and get a per-target report plus a roll-up of what has drifted. Read-only.
Ideal on a schedule ("are my mirrors still faithful to the master?").
"""
from verify import verify


def audit(source: dict, targets: list, strict: bool = False) -> dict:
    """Verify `source` (source-of-truth summary) against each summary in `targets`. Returns
    {summary, reports}. The summary lists which mirrors are in sync and, for those that drifted,
    the headline deltas (tasks, status/casting mismatches, missing entities)."""
    reports = [verify(source, t, strict=strict) for t in targets]
    drifted = []
    for r in reports:
        if r["verdict"] == "match":
            continue
        drifted.append({
            "target": "%s:%s" % (r["target"], r["target_project"]),
            "task_delta": r["counts"].get("tasks", {}).get("delta"),
            "status_mismatches": r["status"]["mismatches"],
            "casting_mismatches": r["casting"]["mismatches"],
            "missing": {k: v["missing_on_target"] for k, v in r["presence"].items() if v["missing_on_target"]},
            "extra": {k: v["extra_on_target"] for k, v in r["presence"].items() if v["extra_on_target"]},
        })
    return {"summary": {"source": "%s:%s" % (source.get("tracker"), (source.get("project") or {}).get("name")),
                        "mirrors": len(targets),
                        "in_sync": sum(1 for r in reports if r["verdict"] == "match"),
                        "drifted": drifted},
            "reports": reports}
