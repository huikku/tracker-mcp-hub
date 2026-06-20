"""snapshot — a portable, tracker-agnostic archive of a project.

Wraps a normalized `project_summary` (the verification fingerprint) into a versioned, restorable archive,
optionally with a media manifest (download URLs) for a fuller backup. `restore` is performed by `migrate`
(apply the archive to any target tracker).

Note on fidelity: `project_summary` is a *verification* fingerprint (counts + per-shot status/cast/thumbnail).
A full backup also needs sequence membership, asset types, frame ranges and a media manifest — pass those via
`extra`. The summary alone is enough for verify/audit/rollup; a full restore needs the richer payload.
"""
import json


def snapshot(summary: dict, media: dict = None, extra: dict = None, created_at: str = None) -> dict:
    """Build a portable archive from a project summary. `media` = optional media manifest (urls/paths);
    `extra` = optional richer export (sequence membership, asset types, frames) for full restore.
    `created_at` is stamped by the caller (the hub has no clock of its own in headless runs)."""
    return {"format": "tracker-mcp-snapshot/v1", "created_at": created_at,
            "summary": summary, "media": media or {}, "extra": extra or {}}


def save(snap: dict, path: str) -> str:
    """Write a snapshot archive to disk as JSON. Returns the path."""
    with open(path, "w") as f:
        json.dump(snap, f, indent=2, default=str)
    return path


def load(path: str) -> dict:
    """Read a snapshot archive from disk."""
    with open(path) as f:
        return json.load(f)
