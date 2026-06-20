"""rollup — aggregate many project summaries into a cross-tracker dashboard.

Given a list of project_summary snapshots (from any trackers), produce totals, per-project rows, a status
distribution, and thumbnail coverage — the data behind a "state of all productions" view. Read-only.
"""


def rollup(summaries: list) -> dict:
    """Aggregate counts, status distribution, and coverage across many project summaries."""
    agg = {"projects": len(summaries), "by_project": [],
           "totals": {"sequences": 0, "assets": 0, "shots": 0, "tasks": 0},
           "status_distribution": {}, "thumbnail_coverage": {"shots_with": 0, "shots_total": 0}}
    for s in summaries:
        agg["by_project"].append({"tracker": s.get("tracker"),
                                  "project": (s.get("project") or {}).get("name"),
                                  "counts": s.get("counts", {})})
        for k, v in s.get("counts", {}).items():
            agg["totals"][k] = agg["totals"].get(k, 0) + v
        for sh in s.get("shots", {}).values():
            agg["thumbnail_coverage"]["shots_total"] += 1
            if sh.get("thumbnail"):
                agg["thumbnail_coverage"]["shots_with"] += 1
            for st in sh.get("tasks", {}).values():
                agg["status_distribution"][st] = agg["status_distribution"].get(st, 0) + 1
    return agg
