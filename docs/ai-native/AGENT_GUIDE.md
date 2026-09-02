# RPG-Cobo agent guide

RPG-Cobo combines structured RPG data with a BlockWorld voxel map. Treat these as two coordinated layers:

- `Mxxx` map records: properties, encounters, events and references.
- `project/data/mapdata/Mxxx.bw`: BlockWorld geometry loaded by the editor/runtime.

Never read, write or patch `.bw` bytes. Open a map with `rpgcobo_editor_open_data`, then use the dedicated map tools. Save only after inspection and validation.

## Recommended loop

1. Call `rpgcobo_project_get_info` and `rpgcobo_editor_get_workspace_info`.
2. Open an `Mxxx` ID and call `rpgcobo_editor_map_get_info`. For a template-free experiment, first create an unused ID with `rpgcobo_project_create_blank_map`; this uses RPG-Cobo's BlockWorld serializer and does not copy source geometry.
3. Inspect bounded areas with `rpgcobo_editor_map_get_region_summary`. Use `rpgcobo_editor_map_get_surface_grid` only when per-column spatial planning is required; keep its y range bounded.
4. Discover visual vocabulary with `rpgcobo_project_search_assets`, `rpgcobo_project_get_asset_info`, and `rpgcobo_project_search_map_materials`.
5. Prefer `create_path`, `create_pond`, `create_forest_patch`, or `create_clearing` over many individual cell calls. Always provide seeds.
6. Use fill/clear/set block for small deterministic edits, `place_asset` for real MA resources, and `place_free_block` for authored props with overlap checks.
7. Re-inspect, call `rpgcobo_map_validate`, capture an overview, then save.
8. Start test play, poll player state, make short relative moves, interact, and stop the session.

## IDs and coordinates

- Database/resource prefixes are semantic: `M` map, `MA` map asset, `CV` character voxel, `PC` event picture, `EP` enemy picture, and so on.
- Block IDs encode a base type plus variation; never invent them. Search materials or reuse IDs returned by a region summary.
- Free blocks use `fbtype`, `variation/fbparam`, and a placed `uid`. Move/remove tools require the UID from `map_list_assets`.
- Map/editor coordinates are integer BlockWorld coordinates. Runtime player coordinates are half-scale world coordinates; the player-start tool performs that conversion.
- Event positions are block coordinates. Verify y against the region’s surface elevation.

## Mutation safety

Each mutation validates bounds and resource IDs, uses editor operations, and returns a `changeid` after explicit elicitation approval. Use `rpgcobo_change_rollback` immediately if the result is wrong; later edits can make that guarded rollback unsafe. `rpgcobo_editor_map_undo` follows normal stack order.

Do not use `rpgcobo_runtime_reload_tool` as a discard or transaction-abort command. Experiment 002 observed a partial draft persist across reload. Save, reload, rollback and discard are not interchangeable in this build.

Event editor colors are indices 0–5. The typed create/update tools enforce the upstream palette. Existing event name, dialogue, model and color can be changed with `rpgcobo_editor_map_update_event`; other event fields still require a dedicated future command. Rename an open map with `rpgcobo_editor_map_set_name`, because a generic database write can be overwritten by the active editor's stale copy on save.

Map assets are baked. Their source `MAxxx` identity is lost, so later inspection sees resulting blocks/free blocks, not a movable asset instance. Rotation 0 is currently supported; non-zero asset rotation is explicitly rejected in this upstream binary because the called orientation API is absent.

## Validation and visual checks

Validation returns `errors`, `warnings`, `metrics`, `guarantees`, and `limitations`. Its connectivity graph is an approximation: it does not fully model free-block collision, slopes, event state or physics. A valid result is not a proof of fun or playability.

Validation also checks the runtime camera-work record. Experiment 003 showed that a map can open and save in the editor yet fail test play when this template-supplied field is absent.

`rpgcobo_editor_map_capture_view` writes `work/agent-output/Mxxx-overview.png`. The current view is full-map top-down only. Use runtime screenshots for player-scale appearance.

## Playtest

Use upstream `rpgcobo_debug_start/status/pause/screenshot/stop`, plus:

- `rpgcobo_debug_get_player_state`
- `rpgcobo_debug_player_move`
- `rpgcobo_debug_player_interact`

Movement is relative and collision-aware. Poll state until `moving` is false. Interaction reports whether a reachable target was found.

## Common mistakes

- Do not manipulate `.bw` files or embedded `bw64` as arbitrary data.
- Do not guess block/tree IDs or fabricate asset tags.
- Do not assume a baked MA asset retains provenance.
- Do not confuse block coordinates with half-scale runtime coordinates.
- Do not request enormous regions; use bounded summaries.
- Do not request a surface grid when aggregate inspection is sufficient.
- Do not save before inspection/validation unless persistence is intentional.
- Do not assume reload discards unsaved or partially applied work.
- Do not treat approximate traversability as physics-backed proof.

Use `rpgcobo_runtime_execute` only for diagnosis or an API gap. A repeated workflow deserves a dedicated, typed MCP command; ordinary world synthesis should use the explicit tools.
