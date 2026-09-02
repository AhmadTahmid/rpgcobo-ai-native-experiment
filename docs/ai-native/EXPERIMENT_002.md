# Experiment 002 — autonomous Canalwatch town

## Objective

Test whether an agent can turn RPG-Cobo's uninhabited `M982` city template into a detailed, inhabited and playable town from a high-level brief while deriving assets and coordinates from the environment.

This is a proof of autonomous **semantic infill and adaptation**, not a claim that the entire terrain and street network were generated from a blank map. The template supplied canals, paved infrastructure, terrain, vegetation, lamps, and some props. The agent supplied the settlement program, building selection and packing, connections, added props, inhabitants, entry, validation, recovery, and playtest.

Reproducible driver: `tools/run_experiment_002.py`. Raw trace: `work/agent-output/experiment-002-results.json`. Generated map data and captures remain local and are intentionally not committed.

## Brief and autonomy boundary

The brief asked for a detailed canal town using discovered project content, preserving useful authored infrastructure, avoiding `.bw` manipulation, and postponing save until inspection and validation.

No building coordinates or resource IDs were supplied to the spatial planner. The driver:

1. queried semantic asset terms such as `town hall`, `church`, `shop`, and `warehouse`;
2. inspected each discovered asset's decoded dimensions and placement offset;
3. requested a 128×128 surface/material/traversability grid;
4. identified authored build and water materials from bounded region summaries;
5. scored candidate plots by flatness, water, approximate traversability, existing infrastructure, prop conflicts, centrality, and street adjacency;
6. selected a non-overlapping global packing with deterministic backtracking;
7. found baked door free blocks after placement and routed them toward the baseline street graph;
8. discovered character resources for contextual inhabitants;
9. derived the player entry from street cells nearest a map edge.

## Interface work prompted before and during the experiment

Four MCP tools were added, raising the fork total from 28 to 32 and the observed total from 47 to 51:

- `rpgcobo_editor_map_get_surface_grid`: bounded per-column height, material, and approximate traversability.
- `rpgcobo_editor_map_place_free_block`: direct authored lamp/tree/rock/planter placement with bounds and overlap checks.
- `rpgcobo_editor_map_update_event`: typed name/dialogue/model/color updates and invalid palette repair.
- `rpgcobo_editor_map_set_name`: editor-backed map renaming that persists with the map.

The optional semantic metadata overlay was populated for 35 relevant map and character assets. Entries were curated from authored localized names and resource paths; they were not inferred from rendered appearance.

The editor-operation transaction wrapper was also hardened: if `OperationStack.submit()` records an operation and a redo tail such as UI refresh throws, the wrapper immediately invokes editor undo before surfacing the error.

## Derived building plan

All buildings were placed at rotation 0 because the bundled native API still lacks the rotation calls referenced by upstream asset placement code.

| semantic role | asset | x,z footprint | size x,z | origin y | planner note |
|---|---|---:|---:|---:|---|
| Town hall | `MA005` manor | 88,27 | 26×17 | 6 | Highest street-adjacency score |
| Apartment | `MA007` | 43,27 | 18×17 | 6 | One conflicting template prop removed |
| Church | `MA008` | 71,25 | 14×19 | 6 | Adjacent to existing paving |
| Shop | `MA006` | 24,26 | 16×16 | 7 | Only plot with one-block roughness; foundation levelled |
| Warehouse | `MA010` | 96,5 | 18×10 | 6 | Short commercial/road connection |
| Brick house | `MA001` | 74,3 | 12×12 | 6 | Compact street-edge residence |
| Wooden house | `MA003` | 49,80 | 12×12 | 6 | One conflicting template prop removed |
| Large house | `MA000` | 71,83 | 12×12 | 6 | Southern residential infill |

Three conflicting template free blocks were removed. Six connector-path mutations succeeded. Two door starts were already classified as baseline street cells and therefore produced no non-trivial route; these were recorded as optional planner failures rather than forced into unnecessary terrain changes.

Three authored flower-bed objects were added. Two proposed new street lamps were rejected by overlap checks, and no new lamps were forced because the template already contained street lighting.

## Inhabitants and entry

Nine events were created:

- mayor at the town hall (`CV003`);
- resident at the apartment (`CV021` after semantic refinement);
- priest at the church (`CV020`);
- merchant at the shop (`CV008`);
- farmer at the warehouse (`CV028`);
- elder at the brick house (`CV025`);
- boy at the wooden house (`CV014`);
- bard at the large house (`CV018`);
- guard at the generated eastern entry (`CV002`).

Each inhabitant received location-aware dialogue. The player start was derived at block `[127,1,65]`; the guard was placed at `[126,1,65]` so the entry interaction could be tested immediately. Runtime coordinates correctly appeared at half scale.

## Failure and recovery chronology

The raw trace preserves five tool/planner failures.

| observation | classification | response and finding |
|---|---|---|
| Church route contained only its start cell | PLANNER/REPRESENTATION LIMITATION | The start was already a baseline street cell; no terrain edit was needed. The planner should distinguish “already connected” from “no route.” |
| Wooden-house route contained only its start cell | PLANNER/REPRESENTATION LIMITATION | Same false-negative classification as the church. |
| Proposed lamp overlapped one existing free block | EXPECTED SAFETY REJECTION | Placement was skipped; overlap validation worked. |
| Proposed lamp overlapped two existing free blocks | EXPECTED SAFETY REJECTION | Placement was skipped; template lighting was retained. |
| Seventh inhabitant used editor color 6 and `MapToolEvent.updateEventList()` threw | IMPLEMENTATION BUG | The MCP schema allowed 0–7, but upstream defines six colors, 0–5. Schema and runtime validation were corrected. |

The event-color failure exposed a deeper transaction defect. `OperationStack.submit()` appends and advances its cursor before executing redo closures. The event table had already been mutated when the UI refresh threw, but the MCP change was never registered. Guarded rollbacks for earlier changes were therefore blocked by the unregistered newest operation.

An attempted emergency reload then exposed another critical behavior: `rpgcobo_runtime_reload_tool` persisted or retained the partial editor state instead of acting as a discard/revert operation. Reload must not be used as a transaction abort.

The experiment resumed from the persisted partial town rather than hiding the failure:

1. the invalid event palette index was repaired through the new typed update-event tool;
2. the bard and entry guard were added;
3. player start was set;
4. the recovered draft was validated and visually inspected;
5. save, playtest, reload, and revalidation completed.

The generic database-set tool also reported both attempted map renames as applied, but the open `MapEditor` retained `City template` and later overwrote the resource. A dedicated editor-backed rename tool was added; `Canalwatch` then survived save and reload. This shows that “resource mutation succeeded” and “active editor state is synchronized” are separate guarantees.

The first apartment-inhabitant query used the broad term `woman`. Asset search filters matching IDs, names, paths, tags and categories, then sorts by ID; it therefore selected `CV001` because its path contains `woman_knight` before reaching the generic `CV021` resident. A specific curated `resident` tag and query were added, and the existing event was changed to `CV021` through the typed update-event command. The refinement survived reload. Semantic filtering without relevance ranking or role compatibility is not enough for reliable autonomous casting.

## Quantitative result

The complete trace contains 159 recorded successful observations/actions and five preserved failures. Repeated polish passes account for some duplicated runtime evidence.

| metric | baseline M982 | final Canalwatch |
|---|---:|---:|
| Blocks | 104,166 | 118,068 |
| Free blocks | 105 | 195 |
| Events | 0 | 9 |
| Chunks | 506 | 542 |
| Used block IDs | not measured | 43 |
| Approx. walkable columns | not measured | 14,424 |
| Approx. connected components | not measured | 36 |
| Largest approximate component | not measured | 12,453 columns / 86.3353% |

Final and reload validation both returned `valid=true` with zero errors. Three warnings remained:

- two `FREE_BLOCK_OUTSIDE_MAP` warnings for UIDs 196 and 309, both present in the baseline template inventory;
- one approximate isolated-walkable-areas warning.

The connectivity result is not physics-backed proof and includes roofs, platforms, canal separations, and other surfaces that may legitimately form distinct components.

## Visual result

The overview clearly shows eight new buildings distributed around the authored canal and street grid. Compared with Experiment 001, the high-contrast roofs and paving make large-scale composition much easier to inspect. Building orientation is visibly repetitive because non-zero map-asset rotation remains unavailable.

Artifacts:

- `work/agent-output/M982-town-before.png`
- `work/agent-output/M982-town-draft-recovered.png`
- `work/agent-output/M982-town-final.png`
- `work/agent-output/M982-town-runtime.png`

The player-scale capture initially showed a blank dialogue box because it was taken immediately after interaction. Repeating the capture after 1.5 seconds produced visible guard dialogue. This classifies the first image as a capture-timing issue. The runtime image still shows a blurred/right-side region, indicating that debug screenshots need better camera/render stabilization or clearer capture-state reporting.

## Playtest

Test play launched on `M982` after save. Structured state reported the player running and landed near `[63.6,0.5,33.03]`. The agent moved toward the entry guard and interaction returned:

```text
accepted=true
event_id=1000009
interaction_target_event_id=1000009
```

The settled runtime screenshot displays the guard's dialogue beginning with “Welcome to Canalwatch.” The session stopped normally. After tool reload, the town retained nine events, the player start, the `Canalwatch` name, geometry counts, and zero validation errors.

## What this proves

- An agent can select assets from semantic intent rather than supplied IDs.
- Per-column spatial state is sufficient for deterministic non-overlap building packing on an authored template.
- Baked door inspection can reconnect placed content to existing infrastructure in simple cases.
- Typed overlap rejection prevents decorative-object collisions without manual cleanup.
- Contextual NPC creation, spawn placement, save, runtime movement, interaction, and reload can form one closed loop.
- Failure recovery is itself a high-value AI-native test and exposed defects not found by the smaller first experiment.

## What this does not prove

- Generation of an entire town from blank terrain; the street/canal framework was authored.
- Physics-backed access to every building door.
- Semantic preservation of buildings after placement; source provenance remains lost.
- Robust aesthetic variation; every building uses rotation 0.
- Interiors, merchants with store logic, portals, quests, schedules, or stateful event chains.
- Generalization across new briefs, templates, seeds, or asset packs.
- That the current top-down or runtime capture is sufficient for fine-grained autonomous art direction.

## Design lessons

1. **Spatial aggregates were not enough.** The surface grid changed building placement from guessed coordinates into environment-derived planning.
2. **Metadata is part of the engine interface.** English semantic queries were impossible against Japanese-only display names without curated aliases.
3. **Placed assets need retained identity and anchors.** Inferring doors after baking works, but a future platform should preserve building instance, entrance, plot, role, and source asset explicitly.
4. **Transactions span more than data.** Scene graph, UI lists, undo cursors, change registration, and persistence all need one atomic boundary.
5. **Save, reload, revert, and discard need separate commands.** Their ambiguity is dangerous for autonomous recovery.
6. **“Already connected” is a semantic route state.** It should not be reported as route failure.
7. **Visual feedback must report readiness.** Captures need stable camera/render/dialogue state rather than relying on fixed sleeps.
8. **Generic resource writes can conflict with active editor copies.** AI-native APIs should identify the authoritative live state and synchronize it explicitly.
9. **Semantic search needs ranking and compatibility.** A matching path token can outrank a better role-specific asset unless intent, metadata confidence, and asset role are scored.

The strongest next test is not a larger one-shot build. It is a changed-brief revision of Canalwatch, followed by the same town brief on a non-city template, to test preservation, repair, and generalization.
