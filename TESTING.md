# Testing — the tracker-MCP trio (ShotGrid · ftrack · Kitsu)

How these MCP servers ([`shotgrid-mcp`](https://github.com/huikku/shotgrid-mcp),
[`ftrack-mcp`](https://github.com/huikku/ftrack-mcp), [`kitsu-mcp`](https://github.com/huikku/kitsu-mcp))
are validated, what is covered, and how to reproduce it. The goal is honest confidence: state what was
actually exercised against a live system, how it was verified, and what is *not* yet covered.

> Sanitized for public use — no site URLs, credentials, or project names. The same procedure applies to all
> three servers; tracker-specific notes are called out inline.

---

## 1. Principles

- **Live, not mocked.** Every functional test runs against a *real, running* instance of the tracker (a
  ShotGrid site, an ftrack instance, a self-hosted Kitsu). Reads and writes hit the real API.
- **Round-trip verification.** A write is only "passing" if it is **read back** from the server and asserted
  (counts match, fields match, links resolve). We never trust the create call's return value alone.
- **Representative slices.** Functional coverage is proven on small, real slices (a sequence, a handful of
  shots/assets/tasks, a few versions) rather than full-scale projects — enough to exercise every code path
  and data type without creating large amounts of test data. Scale is a known gap (see §7).
- **Clean up after every test.** Each test creates clearly-named throwaway entities (prefixed
  `ZZZ_…_DELETEME` / `zzz_…`) and removes them at the end. A final sweep asserts **zero** test artifacts
  remain on any tracker.
- **Credentials from the environment only.** No secrets in source or in tests; each server reads its creds
  from env vars. Test runs export them locally and never log values.

---

## 2. Test layers

| Layer | What it checks | How |
|---|---|---|
| **Import / registration** | The server imports cleanly and registers exactly the expected tool count | Load the module, list tools, assert count (ShotGrid 15 · ftrack 30 · Kitsu 29) |
| **Connectivity / auth** | Credentials work; the right identity/server is reached | `whoami` against the live instance |
| **Schema / discovery** | Read-only introspection returns the site's real configuration | List projects, entity/asset/task types, statuses, custom-field definitions |
| **Generic CRUD round-trip** | create → read back → delete, with the count restored | Create a throwaway entity, assert it exists, delete it, assert the count is back |
| **Dry-run safety** | Previews never write; previews validate intent | See §4 |
| **Migration (cross-platform)** | A project's data can be read from one tracker and recreated in another | See §5 |
| **Media** | Real image/video bytes move host→host and are reviewable on the target | See §6 |

A test passes only when the **read-back assertion** passes, not when the write call returns.

---

## 3. Tool coverage

Every write tool exposes a `dry_run` flag (audited by a coverage check that greps each `server.py` and flags
any create/update/delete/set/new/upload/log/assign tool lacking it). Read tools are exercised by the
schema/discovery layer and as the verification half of every round-trip.

> These checks are **harness scripts run on demand** against live instances — not a packaged test suite
> committed in the repos (yet). §7 notes the CI gap.

---

## 4. Dry-run testing (two levels)

`create` / `update` / `delete` / `set_status` support two preview modes; both are tested to **write nothing**:

- **`dry_run="plan"`** — client-side echo of the intent. Verified to return without contacting the server.
- **`dry_run="preflight"`** — a real dry run: resolves every reference against **live data**, validates
  statuses against the **live schema**, returns a before→after diff and an `ok`/`would_fail` verdict.
  ftrack additionally stages the operation in its session (its own schema validation) and rolls back.

**How preflight is verified:**
- *Catches bad input* — preflight a create against a non-existent parent → `would_fail` with the unresolved
  reference; preflight a status change to an invalid value → `would_fail` listing the valid values.
- *Shows truth* — preflight an update and assert the `from` value equals the entity's real current value.
- *Writes nothing* — record the entity count before/after a batch of preflights and assert it is unchanged.
- *Plan log* — with `MCP_PLAN_LOG=/path.jsonl` set, assert each plan/preflight appends one line, producing a
  reviewable plan file.

> **Scope of dry-run, stated honestly:** preflight is **high-confidence validation, not transactional
> simulation.** None of these APIs offer a rollback-based dry run, and some rules only surface on the real
> commit (e.g. ftrack enforces certain parent requirements at commit, not at create). Preflight tells you an
> operation *would* land, or exactly why not — it does not guarantee the commit.

---

## 5. Migration testing (the headline)

A migration reads a project's structure and data from a **source** tracker and recreates it on a
**target**. The *test* wraps that real migration in throwaway scaffolding and a cleanup step.

**The migration itself (steps 1–4):**
1. Pick a real slice on the source (one sequence + a few shots/assets/tasks; entities that actually have the
   data type under test — e.g. shots that have casting, an asset that has versions).
2. Create the target project.
3. Recreate, in order: sequences → shots/assets → tasks (mapping each tracker's status vocabulary) →
   casting → media → notes → custom fields → publish references.
4. **Verify by read-back on the target:** counts match the slice; a sampled status, casting link, comment,
   and version are present and correct.

**Test-only wrapper (steps 0 and 5):**
- **0.** The target project is created with a throwaway name (`ZZZ_…_DELETEME`) — because the test runs
  against a real, shared instance we don't want to pollute.
- **5.** **Tear down** the target project and assert it is gone.

> **Teardown is a property of the *test*, not of migration.** A real migration stops at step 4 — the
> recreated project on the target *is* the deliverable and is kept. We delete it here only so repeated test
> runs leave the live instances exactly as they were found (see §9).

**Directions covered** (the 3×3 matrix, minus the diagonal):

| Source → Target | ShotGrid | ftrack | Kitsu |
|---|---|---|---|
| from ShotGrid | — | ✅ | ✅ |
| from ftrack | ✅ | — | ✅ |
| from Kitsu | ✅ | ✅ | — |

**Data types carried and verified** (richest on the SG↔Kitsu edge): sequences, shots, assets, tasks,
statuses (mapped per tracker), asset→shot casting, thumbnails, multi-version video, notes, custom fields,
and publish references (path + version + type + **dependency chain**). The per-tracker fidelity matrix and
the known incompatibilities live in [`COMPARISON.md`](COMPARISON.md).

### Verification & reporting — current state

Step 4 above ("verify by read-back") is performed **inline by the test harness**: it reads the target back
and asserts counts and sampled fields, printing results. It is **not yet a reusable tool**, and **no
verification report is generated**. The closest structured artifact is the dry-run **plan log**
(`MCP_PLAN_LOG`) — but that is the *before* side (what a run *would* do), not an *after* confirmation of what
landed.

> **Planned (not built):** a reusable post-migration `verify` that diffs source ↔ target — per-entity-type
> counts, sampled field/link parity, and media/version/note coverage — and emits a report (machine-readable
> JSON + a human-readable summary). It would be the symmetric "after" companion to the "before" plan log:
> **plan → migrate → verify report.**

---

## 6. Media testing

Because there is no shared storage between trackers, media is **downloaded from the source host and
re-uploaded to the target host**, which transcodes as needed. Tested with **real video files** (production
plate clips, several MB each), multiple versions on one task/asset:

- Upload N video clips as N successive versions → assert N versions exist, each with a playable movie and an
  incrementing revision; the last sets the entity thumbnail.
- Migrate those versions to another tracker (download each transcoded movie, recreate the version, upload) →
  assert the target shows N versions each with media attached.
- Thumbnails: download an entity's image from the source, set it on the target entity, assert it is set.

Transcoding is performed by the target (Kitsu via its preview pipeline; ftrack via `encode_media` →
`ftrackreview-mp4`; ShotGrid via `sg_uploaded_movie`).

---

## 7. Scope & known limitations

Stated plainly so the green checks aren't over-read:

- **Slices, not full scale.** Coverage is proven on small slices, not full hundreds-of-shots projects.
  Full-scale runs (throughput, pagination, rate limits) are not yet part of the suite.
- **Preflight ≠ guarantee.** See §4 — high-confidence validation, not transactional simulation.
- **Edge asymmetry.** Some data types are proven on specific edges only. Notably **ftrack has no shot↔asset
  casting model**, so casting does not round-trip through ftrack; and custom fields / time logs are proven
  on the SG↔Kitsu edges, not yet with ftrack as a target.
- **Not yet carried:** heavy publish *bytes* (only references migrate — by design), and some secondary
  fields. Time logs depend on tracker permission rules (e.g. Kitsu requires the person be assigned to the
  task).
- **Manual, not yet CI.** Tests are harness scripts run on demand against live instances — not a packaged
  suite in the repos, and no CI harness with a disposable instance per run (natural next steps).
- **No post-migration verification report.** Verification is inline read-back in the harness; there is no
  reusable `verify` tool or generated report yet (see §5 → *Verification & reporting*).

---

## 8. How to reproduce

The pattern for any check (pseudo-shell):

```bash
# 1. Credentials from the environment (never committed)
export <TRACKER>_URL=…  <TRACKER>_USER=…  <TRACKER>_KEY=…
export MCP_PLAN_LOG=/tmp/plan.jsonl        # optional: capture a dry-run plan file

# 2. Drive the server's tools (via an MCP client, or by importing server.py)
#    a) connectivity:        whoami
#    b) registration:        list tools, assert count
#    c) round-trip:          create throwaway -> read back -> delete -> assert restored
#    d) dry-run:             create(..., dry_run="preflight") -> assert verdict, assert nothing written
#    e) migration slice:     read source slice -> recreate on a (throwaway) target -> verify by read-back
#                            ('remove target' below is TEST cleanup only — a real migration keeps the result)

# 3. Clean-up sweep (test-only): list projects on every tracker, assert no ZZZ_/zzz_ test artifacts remain
```

The MCP tools and the `server.py` functions are the same code, so tests may call either; multi-step
migration runs typically import `server.py` for speed, while spot checks use the live MCP tools.

---

## 9. Cleanup discipline

- Throwaway entities use an unmistakable prefix (`ZZZ_…_DELETEME` / `zzz_…`).
- Each test removes what it created (note: Kitsu requires a project be *closed* before deletion — use the
  dedicated teardown tool).
- A final sweep lists projects on **all three** trackers and asserts none match the test prefix.
- Temporary downloaded media is removed from the local temp dir.

After a full test pass, every tracker is left exactly as it was found.
