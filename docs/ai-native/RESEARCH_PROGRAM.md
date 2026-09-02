# RPG-Cobo AI-native research program

## Macro question

Can a constrained creative environment such as RPG-Cobo be made genuinely AI-native, and can the resulting interface and failure lessons inform a purpose-built creative platform?

The work is not primarily about generating one map. RPG-Cobo is the research environment because it already has a structured world model, authored assets, editing semantics, undo, validation targets, and a playable runtime. The research asks which representations, actions, feedback loops, and safety properties an agent needs to operate such a system with progressively less human intervention.

## Working definition

Three levels are distinguished:

1. **AI-compatible**: an application can accept generated text, scripts, or arbitrary code.
2. **Agent-accessible**: an agent can inspect and invoke selected application operations through a machine-readable interface.
3. **AI-native**: the environment exposes intent-level, typed and reversible actions; semantic discovery; bounded state inspection; visual and runtime feedback; validation; persistent identity; and enough error information for an agent to plan, act, critique, recover, and revise without hidden manual work.

Arbitrary code execution is an escape hatch, not evidence of AI-native design. A successful artifact is also insufficient if its coordinates, resource IDs, or decisions were embedded manually in a task-specific generator.

## Hypotheses

- **H1 — Constraints help autonomy.** A structured RPG editor should require less inference than an unconstrained 3D package because its maps, events, materials, and runtime concepts already carry useful semantics.
- **H2 — A control plane is necessary but insufficient.** Typed mutation tools can create geometry, but autonomy stalls without spatial summaries, asset vocabulary, visual feedback, and runtime observations.
- **H3 — Semantic vocabulary is infrastructure.** Localized names, raw file paths, and numeric IDs are not enough for reliable intent-to-asset selection. Authored or curated metadata must be first-class and traceable.
- **H4 — Reversibility must include failures.** Undo and rollback are not sufficient if a command can partially mutate state before throwing, or if a recovery command unexpectedly persists the draft.
- **H5 — Intent tools and primitives are both required.** Agents benefit from roads, plots, ponds, and forests, but also need typed placement and inspection primitives for novel compositions.
- **H6 — Runtime feedback changes the standard of success.** A town that looks correct from above can still fail at spawn, movement, collision, interaction, or dialogue.
- **H7 — Generalization is the decisive test.** A single successful town demonstrates feasibility. Repeated builds, changed briefs, repairs, and different asset packs are required to distinguish environmental understanding from a town-specific recipe.

## Two research tracks

### Track A — Make RPG-Cobo increasingly AI-native

- Audit the actual editor/runtime representation.
- Expose bounded inspection and semantic resource discovery.
- Add typed, reversible mutations using normal editor operations.
- Add structural validation, visual capture, and runtime control.
- Attempt increasingly autonomous artifacts and repair the interface gaps they expose.

### Track B — Extract requirements for a future platform

Every RPG-Cobo limitation is classified as one or more of:

- representation;
- semantics/asset vocabulary;
- action interface;
- transaction/recovery;
- visual feedback;
- runtime observability;
- engine capability;
- model/planning behavior.

Recurring limitations should become design requirements for a future engine rather than accumulating as project-specific patches.

## Evidence ladder

| level | evidence | status |
|---|---|---|
| 0 | Architecture and capability audit | Complete |
| 1 | Typed control layer can inspect, mutate, validate, capture, and playtest a bounded slice | Experiment 001 complete |
| 2 | Agent can discover assets, derive coordinates, construct a semantically detailed town, recover from failures, and playtest it | Experiment 002 complete |
| 3 | Same system can revise an existing town from a changed brief and repair introduced defects | Not run |
| 4 | Multiple briefs/seeds/templates produce coherent results without task-specific code changes | Not run |
| 5 | Interface abstractions transfer to another editor or a purpose-built prototype | Not run |

## Evaluation dimensions

Future experiments should report:

- **Autonomy:** which inputs came from the brief, the environment, the agent, or a human.
- **Semantic correctness:** whether selected assets and events serve the intended roles.
- **Spatial coherence:** non-overlap, hierarchy, street access, composition, and density.
- **Functional correctness:** validation, spawn, movement, interaction, save, and reload.
- **Feedback quality:** whether captures and state queries support reliable critique.
- **Recoverability:** whether rejected or throwing operations leave state unchanged and can be reversed.
- **Generalization:** whether the same interface handles changed goals and unfamiliar content.
- **Efficiency:** tool calls, mutation granularity, output volume, and avoidable retries.

## Preliminary answer after Experiment 002

RPG-Cobo can be made meaningfully agent-operable, and a constrained editor is a productive setting for AI-native research. The autonomous Canalwatch town demonstrates semantic asset discovery, derived spatial planning, typed construction, contextual event creation, runtime interaction, and recovery from real tool defects.

It is not yet proof of a generally autonomous game-development platform. The experiment adapted an authored city template, used a curated metadata overlay, could not rotate baked building assets, did not verify physics-backed access to every door, and did not create interiors or a quest chain. These boundaries are part of the result.

## Requirements emerging for a purpose-built platform

- Semantic object identity must survive placement; a building should remain a selectable building instance.
- Assets need authored descriptions, tags, dimensions, anchors, entrances, allowed rotations, and compatibility constraints.
- Spatial queries should expose height, occupancy, collision, navigation, visibility, and district-level summaries.
- Transactions must be atomic across data, scene graph, UI refresh, undo registration, and persistence.
- Reload, revert, save, and discard must be explicit and have distinct machine-readable semantics.
- Validation should combine structural checks with the same navigation/physics model used at runtime.
- Visual capture needs region, scale, angle, semantic overlays, and stable camera control.
- Event/dialogue systems need typed schemas for creation, modification, conditions, and stateful quest logic.
- High-level planners should operate over persistent plots, roads, entrances, districts, and relationships rather than anonymous baked voxels.

## Recommended next experiments

1. Apply a changed brief to Canalwatch: add a market district, move civic emphasis, and preserve existing residents and routes.
2. Run the same town brief on the grassland or flat template with no prebuilt city infrastructure.
3. Generate three variants from one brief and compare semantic/spatial metrics and failure rates.
4. Introduce deliberate defects—blocked entrance, invalid event reference, isolated spawn—and require autonomous diagnosis and repair.
5. Prototype persistent semantic building instances and physics-backed path queries as if designing the future platform rather than extending the current representation.

