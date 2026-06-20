"""migrate — orchestrated cross-tracker project copy: read → write → verify.

A migration reads a source project into the hub's intermediate **export model** (richer than a
project_summary — it carries sequence membership, asset types and frame ranges), writes it to a NEW project
on the target tracker, then runs `verify` so every run ends with proof.

This module ships the **SG → Kitsu** reference edge (the most exercised one). Adding an edge = writing a
`read_<tracker>` and a `write_<tracker>` against that tracker's MCP; the orchestration and verify are shared.
Media (thumbnails / version movies) is carried by the dedicated media tools, not this reference — see the
COMPARISON for the per-edge media story.
"""
from verify import verify

# canonical status (the export model speaks canonical) -> each target's vocabulary
_CANON_TO_KITSU = {"todo": "todo", "wip": "wip", "done": "done", "review": "wfa", "approved": "approved"}
_SG_TO_CANON = {"wtg": "todo", "ip": "wip", "fin": "done", "rev": "review", "apr": "approved"}


def read_sg(SG, project_id, shots_filter=None):
    """Read a ShotGrid project into the intermediate export model. `shots_filter` = optional set of shot
    codes to limit the slice."""
    proj = SG.find_one("Project", [["id", "is", project_id]], ["name"])
    F = [["project", "is", {"type": "Project", "id": project_id}]]
    shots = SG.find("Shot", F, ["code", "sg_sequence", "sg_cut_duration", "image", "assets"], limit=0)
    if shots_filter:
        shots = [s for s in shots if s["code"] in shots_filter]
    seqs, assets, out = set(), {}, []
    for s in shots:
        seqs.add((s.get("sg_sequence") or {}).get("name"))
        for a in (s.get("assets") or []):
            if a["name"] not in assets:
                assets[a["name"]] = (SG.find_one("Asset", [["id", "is", a["id"]]],
                                                 ["sg_asset_type"]) or {}).get("sg_asset_type") or "Prop"
        tasks = [{"type": t["content"], "status": _SG_TO_CANON.get(t.get("sg_status_list"), t.get("sg_status_list"))}
                 for t in SG.find("Task", [["entity", "is", {"type": "Shot", "id": s["id"]}]],
                                  ["content", "sg_status_list"], limit=50)]
        out.append({"name": s["code"], "sequence": (s.get("sg_sequence") or {}).get("name"),
                    "frames": s.get("sg_cut_duration"), "cast": sorted([a["name"] for a in (s.get("assets") or [])]),
                    "tasks": tasks, "thumbnail": bool(s.get("image"))})
    return {"project": {"name": (proj or {}).get("name")}, "sequences": sorted(x for x in seqs if x),
            "assets": [{"name": n, "type": t} for n, t in assets.items()], "shots": out}


def write_kitsu(KS, model, project_name):
    """Restore the export model into a NEW Kitsu project (structure + casting + statuses). Returns the id."""
    pid = KS.new_project(project_name)["id"]
    shot_tt = {t["name"].lower() for t in KS.list_task_types() if t.get("for_entity") == "Shot"}
    seqmap = {s: KS.new_sequence(pid, s)["id"] for s in model["sequences"]}
    amap = {a["name"]: KS.new_asset(pid, a["type"], a["name"])["id"] for a in model["assets"]}
    for s in model["shots"]:
        sid = seqmap.get(s["sequence"]) or seqmap.setdefault(s["sequence"], KS.new_sequence(pid, s["sequence"] or "seq")["id"])
        ksh = KS.new_shot(pid, sid, s["name"], nb_frames=s.get("frames"))
        if s["cast"]:
            KS.set_casting(pid, ksh["id"], [amap[n] for n in s["cast"] if n in amap])
        for t in s["tasks"]:
            if (t["type"] or "").lower() not in shot_tt:
                continue
            kt = KS.new_task(ksh["id"], t["type"])
            KS.set_task_status(kt["id"], _CANON_TO_KITSU.get(t["status"], "todo"))
    return pid


def _model_summary(model):
    """Derive a normalized summary from the export model (so verify compares like-for-like)."""
    shot_tt = None  # the model already only contains migratable shot tasks at write time
    shots = {s["name"]: {"cast": s["cast"], "thumbnail": s.get("thumbnail", False),
                         "tasks": {t["type"]: t["status"] for t in s["tasks"]}} for s in model["shots"]}
    return {"tracker": "shotgrid", "project": model["project"],
            "counts": {"sequences": len(model["sequences"]), "assets": len(model["assets"]),
                       "shots": len(model["shots"]), "tasks": sum(len(s["tasks"]) for s in model["shots"])},
            "shots": shots, "assets": {a["name"]: {} for a in model["assets"]}}


def migrate_sg_to_kitsu(SG, KS, sg_project_id, target_name, shots_filter=None, verify_after=True):
    """Read a ShotGrid project (or slice) → write a new Kitsu project → verify. Returns
    {migrated_project_id, shots, verify}."""
    model = read_sg(SG, sg_project_id, shots_filter)
    # keep only migratable shot tasks in the model so the verify compares like-for-like
    shot_tt = {t["name"].lower() for t in KS.list_task_types() if t.get("for_entity") == "Shot"}
    for s in model["shots"]:
        s["tasks"] = [t for t in s["tasks"] if (t["type"] or "").lower() in shot_tt]
    kpid = write_kitsu(KS, model, target_name)
    result = {"migrated_project_id": kpid, "shots": len(model["shots"])}
    if verify_after:
        result["verify"] = verify(_model_summary(model), KS.project_summary(kpid))
    return result
