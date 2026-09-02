# AI-native architecture audit

## What RPG-Cobo is

RPG-Cobo is a Sakana/SakanaGL editor and runtime with a JSON-backed RPG database, resource registries, and a BlockWorld voxel map. The open scripting layer under `project/` owns most editor, game, MCP and runtime orchestration; `sakanagl.dll` and add-ons provide native rendering, physics and voxel primitives.

The map representation is intentionally hybrid:

```text
project/data/map.json                  project/data/mapdata/Mxxx.bw
semantic map record                    serialized BlockWorld
(name, events, encounters, settings)   (blocks, free blocks, chunks)
              \                         /
               MapEditor + MapCanvas
                 | BlockOperation
                 | OperationStack
                 v
          save JSON + ObjectOutput.encode(BlockWorld)
```

Agents must never interpret or patch `.bw` bytes. `MapEditor.init()` loads geometry with `ObjectInput.decode`; `MapEditor.save()` uses `ObjectOutput.encode`. Runtime `RPGStage` follows the same decoding route and builds `SK3DBlockWorld` rendering/collision state.

## Project database

`project/data/*.json` is registered into `::conf` and RPG objects are available through `::rpgdata`. Upstream MCP already lists, searches, gets and sets database entries. The set operation is routed through `MCPServer.processChange()` and editor/resource APIs; this fork fixes the previously ignored `override` argument.

Map events live in each map record’s `event` table. They are not stored inside the BlockWorld. The fork’s event inspection tools read the open editor record, while creation applies registered `RPGSystem.eventrole` defaults and updates the normal event gizmo/undo stack.

## Geometry and placed objects

`MapEditor.bw` is the live `BlockWorld`. Low-level changes are accumulated as redo/undo closures by `BlockOperation` and submitted through `MapEditor.submitOp()`. Fork mutations use that route and then invalidate the cached map shot.

Blocks are encoded material/variation IDs. Free blocks are positioned voxel objects (trees, rocks, doors, roofs and furniture) with a stable per-map `fbuid`. A map asset (`MAxxx`) is itself a compressed, base64-embedded BlockWorld resource. Placement bakes its blocks and free blocks into the destination; upstream does not preserve the source MA ID. Consequently, free blocks can be moved/removed by UID, but a baked house cannot later be selected as one provenance-bearing “house instance.”

This binary also disagrees with the checked-in `BlockOperation.drawWorld()` implementation: the method calls unavailable `collectBlocks`, `Block.rotate`, and `IMat.transformv` APIs. The fork’s rotation-0 asset placement uses `blockat`, `collectFreeBlocks`, explicit translation and `BlockOperation`; non-zero rotation is rejected rather than silently misorienting blocks.

## Assets and resources

Resource JSON is registered under `::conf._resource`. Upstream MCP lists one resource type at a time. The fork searches across map assets, character voxels, pictures, enemies, effects, equipment/object voxels and audio; MA bounds are decoded with RPG-Cobo’s own `ObjectInput`, not by parsing the payload.

Voxel block/free-block variations are a separate authored vocabulary in `map_vox`. `rpgcobo_project_search_map_materials` exposes their configured type/model and mutation-ready IDs. Optional human-authored metadata lives in `project/agent/asset-metadata.json`. Experiment 002 populates a small provider-neutral overlay from authored localized names and resource paths; the entries are explicitly curated rather than inferred from rendered appearance. Later vision or embedding pipelines can extend the same seam without coupling the editor to an online model.

## Runtime and playtesting

Upstream MCP can execute Sakana, save/reload, capture the tool, and start/status/pause/screenshot/stop test play. Test play is a child process connected through `IPCConnection`/`DebugSession`. The fork fixes `debug_start`’s undefined menu variable and adds test-process functions for structured state, relative collision-aware walking, and interaction. Dedicated MCP tools invoke those functions over the existing IPC bridge.

`debugskills` remains a declared-but-unused upstream argument: no corresponding translation exists in `DebugActivity.getDebugArgs()`.

## Visual feedback

`MapCanvas.captureMapShot()` already performs a top-down orthographic render at four pixels per x/z block. The fork saves that result to `work/agent-output/<map-id>-overview.png`. It is a geometry overview, not a semantic diagram; on low-contrast palettes, paths and water can remain difficult for vision models to distinguish.

## Transaction boundary

Mutating MCP calls validate first, then ask for MCP elicitation, submit one editor operation, return JSON containing a `changeid`, and keep a rollback closure. `rpgcobo_change_rollback` succeeds only while that change remains the newest editor operation. The normal editor undo tool is also exposed. Saving is deliberately separate via upstream `rpgcobo_runtime_save_all`.

Experiment 002 found that `OperationStack.submit()` records and advances an operation before executing its redo array. If a redo tail such as an editor-list refresh throws, state and the undo cursor can change before MCP registers the change. `AgentNative.submitEditorOperation()` now catches that case and immediately invokes editor undo before returning the exception.

The experiment also showed that tool reload is not a reliable revert/discard boundary: a partial draft survived `rpgcobo_runtime_reload_tool`. Agents must use guarded rollback or normal undo before later mutations, and the platform should eventually expose explicit save, reload, discard and restore commands with distinct semantics.

Generic database mutation and live editor state are separate copies. A database-set call can report success while an open `MapEditor` retains stale data and overwrites the resource at its next save. The fork uses editor-backed commands for event updates and map renaming; a future generic setter needs explicit live-editor synchronization.
