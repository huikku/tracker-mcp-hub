# Tracker comparison — ShotGrid · ftrack · Kitsu · AYON

These four MCP servers ([`shotgrid-mcp`](https://github.com/huikku/shotgrid-mcp),
[`ftrack-mcp`](https://github.com/huikku/ftrack-mcp), [`kitsu-mcp`](https://github.com/huikku/kitsu-mcp),
[`ayon-mcp`](https://github.com/huikku/ayon-mcp)) expose the **same shape** so an agent can read a project
from one tracker and recreate it in another. This doc compares the servers, shows how the platforms' data
models line up, and — most importantly — lists the **incompatibilities you hit when migrating between them**.
The three original trackers were exercised in **live round-trip tests** (all six directions); **AYON** is the
newest addition — its data model is source-verified against a live install and the MCP is tested live
(read + CRUD); cross-tracker migration *edges* to/from AYON are the natural next step.

## 1. The MCP servers
| | shotgrid-mcp | ftrack-mcp | kitsu-mcp | ayon-mcp |
|---|---|---|---|---|
| Platform | ShotGrid / Flow Production Tracking | ftrack Studio | Kitsu (CGWire) | **AYON (Ynput)** |
| Backing SDK | `shotgun_api3` | `ftrack_api` | `gazu` → Zou REST | **`ayon-python-api`** (GraphQL+REST) |
| Auth | script name + API key | API user + API key | email + password | **server URL + API key** |
| Tools | 16 | 31 | 30 | **20** |
| API shape | generic CRUD over a schema | generic query + CRUD | generic REST + typed helpers | **generic CRUD over entities** |
| Write safety | `dry_run` on **every** write | `dry_run` on **every** write | `dry_run` on **every** write | `dry_run` on **every** write |
| Entity ids | **integer** | **UUID string** | **UUID string** | **UUID string** |
| Open source | platform: no | platform: no | platform: **yes** | platform: **yes** (AGPL) |
| License (MCP) | MIT | MIT | MIT | MIT |

> **Dry-run has two levels** (on `create`/`update`/`delete`/`set_status`, kubectl-style): `dry_run="plan"`
> = client-side echo (no server contact); `dry_run="preflight"` = a *real* dry run — resolves every
> reference against live data, validates statuses against the schema, returns a before→after diff and an
> `ok`/`would_fail` verdict, **writing nothing** (ftrack also stage-validates in its session, then rolls
> back). Set `MCP_PLAN_LOG=/path.jsonl` and a whole dry-run migration writes a reviewable plan file. It's
> high-confidence preflight, not transactional simulation — some errors only surface on the real commit.

## 2. Data-model mapping (how the concepts line up)
| Concept | ShotGrid | ftrack | Kitsu | AYON |
|---|---|---|---|---|
| Project | `Project` | `Project` (needs a **schema**) | `Project` | `Project` (+ **anatomy**) |
| Sequence | `Sequence` | `Sequence` | `Sequence` | **`Folder`** (`folder_type=Sequence`) |
| Shot | `Shot` (`sg_sequence` link) | `Shot` (parent = Sequence) | `Shot` (`parent_id`) | **`Folder`** (`folder_type=Shot`) |
| Asset | `Asset` (`sg_asset_type` string) | `AssetBuild` (typed) | `Asset` (asset-type entity) | **`Folder`** (`folder_type=Asset`) |
| Task | `Task` (+ pipeline **`Step`**) | `Task` (+ **`Type`**) | `Task` (+ **`task_type`**) | `Task` (+ `task_type`) |
| Task status | `sg_status_list` | `Status` (schema-scoped) | `task_status` | `Status` (with a `state`) |
| **Publish** | `PublishedFile` + `Version` | `AssetVersion` + `Component` | preview files on tasks | **`Product` → `Version` → `Representation`** |
| Casting (asset→shot) | `Shot.assets` (multi-entity) | **— none** (uses links) | **breakdown / casting** (first-class) | **typed links** (`breakdown\|folder\|folder`) |
| Custom fields | `sg_*` schema fields | custom attributes | metadata-descriptors | **Attributes** (typed, **inheriting**) |
| Hierarchy | flat + links | strict parent tree (Context) | project → entity tree | **polymorphic folders** (any type, any nesting) |

> **AYON is the structural outlier:** there is no fixed Sequence→Shot — **a Folder with a configurable
> `folder_type`** is the only nesting entity, so Episode/Sequence/Shot/Asset are just folder types and any
> tree is legal. It also models **Representations** (file-format variants of a version: abc/usd/exr/mov) that
> none of the others do, and **Attributes inherit down the folder tree** automatically.

## 3. Status vocabularies — **no 1:1; you must map**
Each platform ships a different status set, so migration has to translate. The mapping these servers use
(AYON statuses are per-project configurable, each carrying a `state` — the MCP maps via state + name):

| Meaning | Kitsu | ShotGrid | ftrack (VFX schema) | AYON (defaults) |
|---|---|---|---|---|
| not started | `todo` | `wtg` | `Not started` | `Not ready` |
| ready | `ready` | `wtg` | `Ready to start` | `Ready to start` |
| in progress | `wip` | `ip` | `In progress` | `In progress` |
| done / final | `done` | `fin` | *(no match)* → `In progress` | *(no default)* → `Approved` |
| waiting for approval | `wfa` | `rev` | `Pending Review` | `Pending review` |
| approved | `approved` | `apr` | *(no match)* → `Pending Review` | `Approved` |
| retake / revise | `retake` | `rev` | `Revise` | *(no default)* → `On hold` / custom |

> ⚠️ **ftrack's VFX schema has no clean "done"/"approved" *task* status**, and **AYON's default set has no
> "Done"/"Retake"** (Approved is terminal; statuses are fully configurable). Round-tripping the terminal
> states is lossy unless you add matching statuses first.

## 4. Migration incompatibilities & gotchas
- **Casting can't round-trip through ftrack.** First-class in **Kitsu** (breakdown) and **ShotGrid**
  (`Shot.assets`); **ftrack has none**; **AYON** has no dedicated casting but models it as **typed links**
  (`breakdown|folder|folder`) — so AYON↔casting maps to links, not a native field.
- **AYON's polymorphic folders cut both ways.** Importing SG/ftrack/Kitsu hierarchies *into* AYON is clean
  (everything flattens onto typed folders). Exporting AYON's arbitrary trees *out* to a fixed Seq→Shot
  tracker can need flattening, and AYON's **Representations** (multi-format per version) collapse to one file.
- **Task types aren't universal.** e.g. Kitsu's **`Storyboard`** has no equivalent in ftrack's VFX schema, so
  those tasks are skipped when targeting ftrack. Map or pre-create task types first.
- **Asset types differ.** SG `sg_asset_type` is a free string; **ftrack `AssetBuild` requires a type from a
  fixed list** (no `FX` → map `FX`→`Prop`); Kitsu asset types are named entities; **AYON** uses a folder
  `folder_type` (e.g. `Asset`) + product types.
- **Project creation quirks:**
  - **ShotGrid:** API-created projects have **no UI navigation pages** unless `layout_project` is set at creation.
  - **ftrack:** a project **requires a schema** (VFX / Animation / Model / Video / Media) at creation.
  - **Kitsu:** a project can only be **deleted once *closed*** (use `remove_project`: close → force).
  - **AYON:** no schema needed, but **addon-dependent features need a *bundle*** (the ynput.cloud bootstrap);
    the **core tracker works without any addon**.
- **Name uniqueness:** **ftrack** enforces **case-insensitive, per-parent** uniqueness (`FARMHOUSE`/`Farmhouse`
  collide). SG, Kitsu, AYON are more permissive (AYON folders are path-addressable).
- **Atomicity:** **ftrack** commits are **atomic** per `session.commit()` — dedupe up front. The others commit per call.
- **Ids:** ShotGrid uses **integer** ids; ftrack, Kitsu and **AYON** use **UUID strings** — don't assume a type.

## 5. What these migrations carry today — and what they don't
| Data | Migrates? |
|---|---|
| Project / Sequence / Shot / Asset / Task structure | ✅ all directions (SG/ftrack/Kitsu); AYON via `ayon-mcp` (folders) |
| Task **statuses** (mapped per §3) | ✅ (lossy into ftrack / AYON terminal states, per above) |
| **Casting** (asset→shot) | ✅ SG ↔ Kitsu; ❌ via ftrack; AYON via **links** |
| Frame ranges / cut durations | ✅ (where the field exists) |
| **Thumbnails** (entity images) | ✅ SG → Kitsu; **ftrack** via `set_thumbnail`; AYON via thumbnails |
| **Versions** (review media) | ✅ SG → Kitsu; **ftrack** via `encode_media`; AYON via `Version`/`Representation` |
| **Preview *movies*, multiple versions** | ✅ proven **Kitsu ↔ SG** and **→ ftrack** (real video, multiple versions, transcoded on target) |
| **Notes / comments** | ✅ SG → Kitsu; AYON has a rich **activity feed** (comments/mentions/reviewables) |
| **Custom fields** | ✅ SG → Kitsu; AYON **Attributes** (inheriting) via `get_attributes` |
| **Publishes** | ✅ **references** carry (path / version / type / **dependency chain**); ⚠️ heavy bytes stay on storage; AYON: `Product→Version→Representation` |

> **How media moves:** there is no shared storage — a thumbnail/version/movie is **downloaded from the
> source host and re-uploaded to the target host**, with the target transcoding as needed. **Heavy publishes**
> (EXRs, caches, scene files) live on studio storage referenced by path/URL — migration carries the
> **reference** (path + version + dependency chain); copying the bytes is a per-deployment storage decision.
>
> **Proven (read-back) on representative *slices*:** SG ↔ Kitsu carries structure + statuses + casting +
> thumbnails + **multi-version video** + notes + custom fields; **ftrack** carries structure + statuses +
> thumbnails + **video version media**; **publishes** carry as references with deps. **AYON**: data model
> verified on a live install, `ayon-mcp` tested live (read + full CRUD round-trip with dry_run + normalized
> `project_summary`); AYON↔others migration edges are the next step. Notably, AYON's own **`ayon-ftrack`
> addon** already does production AYON↔ftrack sync (leecher/processor/transmitter) — the hub thesis, shipped.

---
*Part of the tracker-MCP quartet: [shotgrid-mcp](https://github.com/huikku/shotgrid-mcp) ·
[ftrack-mcp](https://github.com/huikku/ftrack-mcp) · [kitsu-mcp](https://github.com/huikku/kitsu-mcp) ·
[ayon-mcp](https://github.com/huikku/ayon-mcp). MIT.*
