# Experiment 003 — Linden Crossing from a template-free map

## Objective and claim boundary

Test the stronger version of the town proof of concept: can the agent turn a genuinely new, uniform RPG-Cobo map into a detailed, inhabited, persistent town without inheriting a human-laid street, canal, terrain, or prop composition?

The answer for this run is **yes, with an important authorship boundary**. The world layout and all scene composition began from a one-layer plane and were produced autonomously. The engine, textures, building assets, character models, animations, block vocabulary, and map-property defaults remain human-authored RPG-Cobo inputs. “From scratch” here means **from blank world geometry**, not that the agent modelled every roof, tree, texture, or character.

Reproducible driver: `tools/run_experiment_003.py`. Raw trace: `work/agent-output/experiment-003-results.json`. The generated map and captures remain local and are intentionally not committed.

## Proven baseline

`M979` was created through the new typed `rpgcobo_project_create_blank_map` command. That command constructs a `BlockWorld`, fills only a uniform authored ground material, serializes with the same `ObjectOutput` path used by `MapEditor.save()`, and creates the corresponding structured map record. It does not copy a template or expose serialized bytes to the agent.

Before construction, the driver refused to proceed unless inspection matched this exact contract:

| property | baseline |
|---|---:|
| Size | 128×64×128 |
| Occupied blocks | 16,384 |
| Free-block objects | 0 |
| Events | 0 |
| Used block IDs | 1 |
| Approximate traversability | 16,384/16,384 columns in one component |
| Source map | none |
| Source map asset | none |

The blank baseline validated with zero errors and zero warnings. Its capture is a featureless green plane: `work/agent-output/M979-town-before.png`.

## Autonomous plan

The high-level brief supplied no coordinates or asset IDs. The driver discovered eight semantic building roles and their decoded dimensions, then derived a normalized axial plan from the map center, asset widths/depths, safety margins, and deterministic packing.

| role | selected asset | derived origin | footprint |
|---|---|---:|---:|
| Town hall | `MA005` | 8,1,20 | 26×17 |
| Church | `MA008` | 40,1,20 | 14×19 |
| Shop | `MA006` | 74,1,20 | 16×16 |
| Warehouse | `MA010` | 96,1,20 | 18×10 |
| Apartment | `MA007` | 16,1,84 | 18×17 |
| Large house | `MA000` | 41,1,84 | 12×12 |
| Brick house | `MA001` | 75,1,84 | 12×12 |
| Wooden house | `MA003` | 94,1,84 | 12×12 |

The generated settlement grammar was:

- a five-block north–south boulevard and east–west boulevard;
- two three-block service streets serving the northern and southern plots;
- eight short plot connectors;
- a 27×27 stone civic square;
- a seeded central reflecting pool;
- twelve boulevard lamps, four flower beds, two benches, and two warehouse props;
- four bounded, seeded perimeter groves using discovered tree variants;
- eight contextual building inhabitants and a west-gate guide;
- a west-gate player start chosen from the generated primary street.

All map assets use rotation zero. The current upstream binary does not expose the native rotation operation referenced by the asset placement code, so non-zero rotation remains rejected rather than risk corrupt orientation.

## Quantitative result

| metric | blank M979 | final Linden Crossing | delta |
|---|---:|---:|---:|
| Occupied blocks | 16,384 | 30,033 | +13,649 |
| Free-block objects | 0 | 202 | +202 |
| Events | 0 | 9 | +9 |
| Chunks | 256 | 310 | +54 |
| Used block IDs | 1 | 18 | +17 |
| Approximate walkable columns | 16,384 | 16,336 | -48 water columns |

The +13,649 occupied blocks exactly matches the sum of blocks in the eight baked building assets. Roads and plaza replace ground cells rather than increasing occupied-cell count.

The complete trace contains 126 successful recorded observations/actions and three preserved failures. Final validation and reload validation returned `valid=true` with zero errors. One warning remains: the approximate 2D surface graph reports 24 components and 91.6687% largest-component coverage. It counts disconnected roofs and other elevated surfaces, so this is not evidence that the ground street network is disconnected.

## Visual result

The overview reads as a coherent garden town: a strong central square and blue pool, clear civic/commercial/residential rows, short walks to streets, and a dense green perimeter. Eight building silhouettes are distinct and the high-contrast roofs make zoning legible.

It is also more visibly procedural than Canalwatch. Its axial symmetry, equal setbacks, rectangular lawns, and rotation-zero façades make the planning grammar easy to infer. Canalwatch looked more human-curated because its inherited civil layout contained irregular canals, bridge constraints, terrain variation, and accumulated prop placement. Linden Crossing proves blank-world composition, but also shows why plausible irregularity and richer plot semantics matter.

Artifacts:

- `work/agent-output/M979-town-before.png`
- `work/agent-output/M979-town-draft-polished.png`
- `work/agent-output/M979-town-final.png`
- `work/agent-output/M979-town-runtime.png`

## Failure chronology and repairs

### 1. Missing thumbnail assumption

The first template-free map record and BlockWorld were valid, but `MapEditor.init()` dereferenced `mapshottex.ref`. Normal map creation always copies a template `.webp`, so the editor had never needed to handle a missing thumbnail.

Repair: map loading and saving were made null-safe. The editor can now open a new map without a pre-rendered thumbnail and generate one later through its normal capture path.

Classification: **hidden template dependency / editor robustness defect**.

### 2. Forest boundary leak

The initial edge-grove primitive placed two large tree free blocks whose centers were inside the requested region but whose rendered bounds crossed the east map boundary. Validation exposed UIDs 165 and 177. A decorative crack baked by the warehouse also extended one cell below y=0.

Repair: all three objects were removed through typed UID operations. Forest generation now instantiates the proposed rotated free block, checks its complete bounds, and skips any placement outside the map.

Classification: **semantic primitive boundary bug found by validation**.

### 3. Optional barrel collisions

Two first-pass warehouse barrels overlapped free blocks baked with the warehouse and were correctly rejected before mutation. They were retried in the gap between commercial plots after visual review.

Classification: **expected safety rejection / local-planning weakness**.

### 4. Missing runtime camera record

Save and reload passed, but the first test play failed at `RPGStageState.enter()` because `map.camwork` did not exist. `camwork` is a required runtime field declared in `MapToolSel.baseprops`, not in the `RPGSystem.stageprops` defaults used by `MapEditor.init()`. Template copying had always supplied it implicitly.

Repair:

1. M979 received the normal camera record through the typed database mutation path.
2. Blank-map creation now writes camera, selector, thumbnail-crop, and visibility defaults in addition to stage defaults.
3. `rpgcobo_map_validate` now reports missing or malformed camera work as an error before test play.
4. Reload and test play were repeated.

Classification: **hidden template dependency / validation gap**.

## Runtime proof

After repair, test play launched on `M979`. The player was running and landed at world position `[4.0, ~0.5, 32.0]`, corresponding to block start `[8,2,64]`. A collision-aware move toward the guide was accepted. The next state exposed interaction target `1000009`; interaction returned `accepted=true` for that event. The runtime capture displays the guide, the generated boulevard/trees/buildings, and “Welcome to Linden Crossing.” The session stopped normally.

## What this proves

- RPG-Cobo can support a real from-blank autonomous town composition loop without copying human street geometry.
- Semantic queries plus decoded asset bounds are sufficient for deterministic zoning and packing in a constrained world.
- Intent-level primitives for roads, water, groves, props, events, and spawn materially reduce control complexity.
- Overview critique, structural validation, player-state control, interaction, persistence, and reload can close the loop.
- Starting from blank is a powerful way to expose platform invariants that template-based workflows conceal.

## What this does not prove

- Human-equivalent organic urban design; the result remains visibly axial and repetitive.
- Generalization beyond this one layout grammar, map size, asset pack, or seed family.
- Physics-backed access to every building entrance.
- Persistent semantic building/road/plot instances after assets are baked.
- Interiors, portals, schedules, commerce logic, quests, or stateful narrative progression.
- AI authorship of the source meshes, voxel assets, textures, characters, or animations.

## AI-native design lessons

1. **Fresh-document creation is a first-class capability.** An agent cannot prove generation from blank if the only supported creation path clones a template.
2. **Runtime invariants need one schema.** Editor selector defaults, runtime-required fields, and database defaults should not be split across unrelated modules.
3. **Validation must inspect proposed object bounds, not just centers.** This applies to vegetation, lights, buildings, effects, and nav blockers.
4. **Aesthetic coherence and organic plausibility are separate objectives.** Axial packing is coherent but exposes its recipe; future planners need varied setbacks, curved secondary streets, district-specific density, and controlled asymmetry.
5. **Semantic instances should survive composition.** Buildings, roads, entrances, plots, and districts should remain typed objects rather than anonymous baked voxels.
6. **Editor and runtime captures answer different questions.** Top-down evidence supports composition critique; player-scale evidence catches cameras, collision, scale, dialogue timing, and occlusion.
7. **Expected rejection is useful training data.** The barrel collisions demonstrate that safe failure can feed a second local-planning pass without corrupting state.
8. **Template-free tests should be mandatory.** They reveal hidden assumptions earlier than increasingly elaborate template adaptation.

The strongest next experiment is now multi-variant generation: run the same semantic town brief with three layout grammars/seeds, measure visual diversity and failure rate, and require the planner to choose and refine one result without task-specific coordinate code.
