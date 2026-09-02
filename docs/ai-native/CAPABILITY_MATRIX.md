# RPG-Cobo AI-native capability matrix

Audit baseline: upstream commit `4bbeb25` (`Minor bugfix`). “Existing” means implemented in executable code, not merely mentioned in comments. “MCP” distinguishes upstream (`yes, upstream`) from this fork (`yes, fork`). The JSON companion is [CAPABILITY_MATRIX.json](CAPABILITY_MATRIX.json).

| capability | existing? | exposed through MCP? | underlying engine/editor API available? | implementation difficulty | priority | notes |
|---|---|---|---|---|---|---|
| Project identity/path/plugin introspection | yes | yes, upstream | yes | low | A | `rpgcobo_project_get_info` |
| Database list/get/search | yes | yes, upstream | yes | low | A | Structured RPG data in `::conf`/`::rpgdata` |
| Database set | yes | yes, upstream | yes | low | A | Fork fixes ignored `override=false` merge behavior |
| Basic resource listing | yes | yes, upstream | yes | low | A | Upstream returns ID/name/model by one resource type |
| Rich cross-type asset search/info | partial upstream | yes, fork | yes | medium | A | Searches IDs, localized names, paths, authored tags; decodes MA bounds with RPG-Cobo APIs |
| Block/free-block material discovery | yes | yes, fork | yes | medium | A | Exposes authored voxel group/type/model and mutation-ready IDs; no guessed categories |
| Editor workspace/tabs | yes | yes, upstream | yes | low | A | `rpgcobo_editor_get_workspace_info` |
| Open database item/editor | yes | yes, upstream | yes | low | A | `rpgcobo_editor_open_data` |
| Template-free map creation | no upstream | yes, fork | yes | medium | A | Creates an engine-serialized uniform BlockWorld plus runtime/editor defaults without copying template geometry |
| Current map metadata/size | yes | yes, fork | yes | low | A | Requires a database-backed map open in `MapEditor` |
| Event list/get | yes | yes, fork | yes | low | A | Compact pagination plus full event retrieval |
| Bounded terrain/occupancy summary | yes | yes, fork | yes | medium | A | Surface/material counts, elevation, events, free blocks, approximate traversal, plus per-column planning grid |
| Placed-object inspection | partial | yes, fork | yes | medium | A | Free blocks retain UIDs; baked MA source IDs do not retain provenance |
| Single block/fill/clear mutation | yes | yes, fork | yes | medium | A | `BlockOperation`, editor undo, MCP elicitation and change rollback |
| Place map asset | partial | yes, fork | partial | medium | A | Rotation 0 works; non-zero rejected because this build lacks upstream-called `Block.rotate` |
| Place/move/remove authored free-block object | yes | yes, fork | yes | medium | A | Typed placement has bounds/overlap checks; move/remove use UID; arbitrary baked structures cannot be reconstructed as one asset |
| Create basic event/player start | yes | yes, fork | yes | medium | A | Uses role defaults, editor gizmos and undo |
| Modify existing event | partial | yes, fork | yes | medium | A | Typed name/dialogue/model/color update and invalid-palette repair; role, position, conditions and arbitrary fields remain unsupported |
| Rename open map | yes | yes, fork | yes | low | A | Editor-backed mutation persists correctly; generic database set can be overwritten by a stale open editor copy |
| Semantic path | no | yes, fork | yes | medium | A | Seeded quadratic path compiled into reversible surface block operations |
| Semantic pond | no | yes, fork | yes | medium | A | Seeded irregular footprint, explicit level/material |
| Semantic forest patch/clearing | no | yes, fork | yes | medium | A | Authored tree free-block variations, density/spacing/cap/seed |
| Existing procedural map generator | yes | no | yes | high | B | `MapGenerator.sk` is editor-oriented; no MCP wrapper upstream |
| Map validation | no | yes, fork | partial | high | A | References, bounds, duplicates, portals, spawn, encounters, approximate components |
| Editor top-down map capture | yes | yes, fork | yes | medium | A | Deterministic PNG path using `MapCanvas.captureMapShot()` |
| Tool/runtime screenshot | yes | yes, upstream | yes | low | A | Existing tools return MCP image content |
| Arbitrary Sakana execution | yes | yes, upstream | yes | low | escape hatch | Powerful and unsafe as a primary interface |
| Save/reload editor state | yes | yes, upstream | yes | low | A | `runtime_save_all`, `runtime_reload_tool` |
| Test-play start/status/pause/stop | yes | yes, upstream | yes | medium | A | Fork fixes upstream `debug_start` undefined variable bug |
| Debug player state/move/interact | no | yes, fork | yes | medium | A | Uses existing tool↔test-process IPC and collision-aware `walkTo` |
| Debug skills option | planned/declared only | argument only | no implementation found | medium | C | Declared by upstream MCP schema but never translated by `getDebugArgs()` |
| MCP cancellation | planned only | method stub | partial | medium | B | Comment explicitly says thread cancellation is unimplemented |
| UI editing | planned only | no | partial | high | C | Mentioned in MCP comments; no callable tool implementation |
| Sprite editing | planned only | no | partial | high | C | No callable tool implementation |
| Icon editing | planned only | no | partial | high | C | No callable tool implementation |
| Vision/embedding asset retrieval | no | no | metadata seam added | high | B | Optional `project/agent/asset-metadata.json`; editor remains model/provider agnostic |

## Counts

- Upstream MCP tools audited: 19.
- Fork MCP tools added: 33.
- Total registered and observed through native `tools/list`: 52.
