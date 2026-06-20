"""verify — cross-tracker project verification.

Diffs two normalized `project_summary` snapshots (each emitted by a tracker MCP — shotgrid/ftrack/kitsu)
into a report. **Tracker-agnostic**: it operates purely on the normalized JSON, so it never needs a tracker
SDK and works for any source→target pair. The symmetric "after" companion to the dry-run plan log.
"""


def verify(source: dict, target: dict, strict: bool = False, examples: int = 5) -> dict:
    """Compare two project_summary snapshots. `strict=True` makes media/thumbnail coverage a hard fail.
    Returns a scale-friendly report: count deltas, presence (missing/extra) totals + examples, casting and
    per-task status mismatch totals + examples, coverage, and a `verdict` of match / discrepancies."""
    r = {"source": source.get("tracker"), "source_project": (source.get("project") or {}).get("name"),
         "target": target.get("tracker"), "target_project": (target.get("project") or {}).get("name"),
         "counts": {}, "presence": {}, "casting": {}, "status": {}, "coverage": {}, "verdict": None}

    for k in source.get("counts", {}):
        s = source["counts"][k]
        t = target.get("counts", {}).get(k, 0)
        r["counts"][k] = {"source": s, "target": t, "delta": t - s, "ok": s == t}

    for kind in ("shots", "assets"):
        sset, tset = set(source.get(kind, {})), set(target.get(kind, {}))
        miss, extra = sorted(sset - tset), sorted(tset - sset)
        r["presence"][kind] = {"missing_on_target": len(miss), "extra_on_target": len(extra),
                               "missing_examples": miss[:examples], "extra_examples": extra[:examples]}

    cast_mm, stat_mm = [], []
    for n, ss in source.get("shots", {}).items():
        ts = target.get("shots", {}).get(n)
        if not ts:
            continue
        if ss.get("cast", []) != ts.get("cast", []):
            cast_mm.append({"shot": n, "source": ss.get("cast"), "target": ts.get("cast")})
        for tk, sv in ss.get("tasks", {}).items():
            tv = ts.get("tasks", {}).get(tk)
            if tv != sv:
                stat_mm.append({"shot": n, "task": tk, "source": sv, "target": tv})
    r["casting"] = {"mismatches": len(cast_mm), "examples": cast_mm[:examples]}
    r["status"] = {"mismatches": len(stat_mm), "examples": stat_mm[:examples]}

    def thumbs(snap):
        return sum(1 for v in snap.get("shots", {}).values() if v.get("thumbnail"))
    r["coverage"] = {"shot_thumbnails": {"source": thumbs(source), "target": thumbs(target)}}

    hard = (any(not c["ok"] for c in r["counts"].values())
            or any(p["missing_on_target"] or p["extra_on_target"] for p in r["presence"].values())
            or r["casting"]["mismatches"] or r["status"]["mismatches"])
    soft = r["coverage"]["shot_thumbnails"]["source"] != r["coverage"]["shot_thumbnails"]["target"]
    r["verdict"] = "match" if not (hard or (strict and soft)) else "discrepancies"
    return r


def format_report(r: dict) -> str:
    """Human-readable one-screen summary of a verify() report."""
    icon = "PASS" if r["verdict"] == "match" else "DIFF"
    out = ["[%s]  %s:%s  ->  %s:%s" % (icon, r["source"], r["source_project"], r["target"], r["target_project"])]
    for k, c in r["counts"].items():
        out.append("    counts.%-9s src=%5s tgt=%5s  d%+d  %s" %
                   (k, c["source"], c["target"], c["delta"], "ok" if c["ok"] else "MISMATCH"))
    for kind, p in r["presence"].items():
        if p["missing_on_target"] or p["extra_on_target"]:
            out.append("    %s: missing=%d %s  extra=%d %s" %
                       (kind, p["missing_on_target"], p["missing_examples"][:3],
                        p["extra_on_target"], p["extra_examples"][:3]))
    if r["casting"]["mismatches"]:
        out.append("    casting mismatches: %d  e.g. %s" % (r["casting"]["mismatches"], r["casting"]["examples"][:2]))
    if r["status"]["mismatches"]:
        out.append("    status mismatches:  %d  e.g. %s" % (r["status"]["mismatches"], r["status"]["examples"][:2]))
    cov = r["coverage"]["shot_thumbnails"]
    out.append("    coverage.shot_thumbnails src=%d tgt=%d%s" %
               (cov["source"], cov["target"], "" if cov["source"] == cov["target"] else "  (gap)"))
    return "\n".join(out)
