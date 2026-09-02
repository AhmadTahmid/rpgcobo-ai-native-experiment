# Experiment 005 — Historical growth without authored coordinates

## Objective

Test the strongest remaining authorship objection from Experiment 004: its three towns were causal, but an agent had still written normalized route endpoints, plot rectangles, and building positions into the world grammar.

Experiment 005 replaces those spatial specifications with one deterministic historical-growth simulator. Its input briefs contain only:

- a founding cause;
- a seed;
- ordered historical phases and growth rules;
- semantic building programs;
- narrative and land-use pressures;
- non-spatial constraints such as map size, margins, counts, and clearances.

Coordinates, positions, anchors, points, path endpoints, and rectangles are forbidden in a brief and rejected by validation. The hypothesis was that the simulator could generate distinct, coherent settlements whose irregularity emerged from accumulated causes rather than from hand-authored layouts.

The hypothesis is supported for this bounded asset vocabulary. Three from-blank towns were generated, compiled, saved, completely reloaded, compared, and one was semantically refined and playtested. The result is not yet a general town language or proof of transfer to another asset pack.

## Reproducible inputs and implementation

- `docs/ai-native/experiment-005/briefs.json` — three coordinate-free causal briefs
- `docs/ai-native/experiment-005/generated-plan-river_crossing.json`
- `docs/ai-native/experiment-005/generated-plan-road_confluence.json`
- `docs/ai-native/experiment-005/generated-plan-civic_accretion.json`
- `docs/ai-native/experiment-005/generated-plan-index.json` — checksums and structural metrics
- `docs/ai-native/experiment-005/agent-evaluation.json` — post-reload visual comparison and semantic refinement request
- `tools/historical_growth.py` — deterministic simulator
- `tools/run_experiment_005.py` — grounding, compilation, reload, scoring, refinement, runtime, and recovery driver
- `tests/ai_native/test_historical_growth.py` — six simulator invariants
- `work/agent-output/experiment-005-results.json` — full local tool trace

Experiment 004's discovered `rpgcobo_bindings.json` was deliberately reused. This isolates the planning question: the asset vocabulary stayed fixed while the source of spatial form changed.

## Authorship boundary

Human-provided input was the macro research direction and permission to experiment. The agent authored the simulator, causal test briefs, phase programs, evaluation, and recovery logic. RPG-Cobo supplied its engine, editor semantics, rendering, typed tools, source assets, materials, character models, collision behavior, and runtime.

The three compact briefs contain **zero spatial coordinate fields**. The simulator generated all of the following:

- persistent semantic nodes;
- geography and active routes;
- obsolete route traces;
- districts and land-use surfaces;
- plots and non-overlapping building instances;
- entrances and connector routes;
- infrastructure, props, forest patches, and ponds;
- player entry and guide positions;
- phase membership and creation history.

“Generated” does not mean learned from arbitrary examples. The simulator contains explicit implementations for river-crossing, road-confluence, and civic-accretion causes. Its randomness is seeded and its constraints are engineered. This is a reusable causal generator for three known cause families, not an unrestricted settlement model.

## Simulator design

The pipeline is:

1. validate that a brief contains no forbidden spatial keys;
2. seed cause-specific semantic nodes and initial geography;
3. execute historical phases in order;
4. grow routes from existing nodes and pressure relationships;
5. sample frontage candidates against generated routes;
6. reject plots that overlap other plots, buildings, water, or margins;
7. retain each accepted building's role, phase, district, plot, entrance, and connector identity;
8. add land-use clusters, forests, an obsolete route, and a boundary remnant;
9. validate topology and serialize the semantic plan with a SHA-256 checksum;
10. ground its nouns against real RPG-Cobo assets and compile through typed editor operations.

The same seed produces byte-identical plan JSON. Changing only the seed changes the spatial plan. Unit tests also require eight complete non-overlapping building/plot instances, all declared phases, and distinct topology for each cause family.

## Generated variants

| cause | map | result | generated spatial records | route angle bins | plot-area CV | historical distance spread | planned props |
|---|---|---|---:|---:|---:|---:|---:|
| River crossing | `M975` | Willowford | 63 | 5 | 0.2382 | 0.6503 | 20 |
| Road confluence | `M974` | Threeways | 69 | 6 | 0.2450 | 0.6949 | 24 |
| Civic accretion | `M972` | Ashcourt | 62 | 5 | 0.4710 | 0.7010 | 17 |

Every variant contains eight buildings, at least three districts, an obsolete route, five historical phases including a residue/decay phase, eight inhabitants plus an entry guide, and a generated player entry route.

### Willowford

The river, ford, bridge, and unequal bank approaches immediately explain the settlement. It is the clearest answer to “why does this town exist here?” Its weakness is low pressure at the crossing: buildings remain more dispersed than the traffic cause suggests. Nineteen of twenty planned props were accepted. Reload validation returned no errors and two warnings: isolated walkable components under the conservative approximation, and an overlapping event position involving one resident and the guide.

### Threeways

Multiple arrival roads, a freight turnout, and buildings responding to different frontages make the cause legible. It was structurally the cleanest variant: all 24 props were accepted and there was no event-overlap warning. Visually, however, its large rectangular paved center and radial connectors make the town look as if it was resolved in one design session rather than accumulated over time.

### Ashcourt

Ashcourt retains an old diagonal route, an offset civic court, a market that shifted away from the original center, later residential accretion, unequal plot sizes, and a decayed enclosure. Its plot-area coefficient of variation, `0.471`, is almost double the other variants and is visible in its massing and setbacks. It received the highest agent visual score, `8.63/10`, because several periods remain simultaneously legible.

Ashcourt's weaknesses are also real: one planned lamp was rejected, two outer inhabitants share a connector target, and some late buildings remain isolated because the available assets cannot rotate to follow their frontages.

## Selection and semantic refinement

The automated structural scorer ranked Threeways highest. The visual review selected Ashcourt instead. This disagreement is useful: route-angle counts, plot variance, and validation cannot determine whether historical layers read convincingly.

The refinement request contained no coordinates. It asked for prop clusters at the generated `market`, `civic_core`, and `residential` node kinds. The driver derived candidate locations from those nodes and rejected positions intersecting buildings or existing prop spacing.

Only three of ten requested additions were accepted:

- one market bench;
- two residential flowerbeds.

The civic core had no safe candidates within the requested radius, and three market objects collided with existing content. This is a good failure mode: the agent did not override collision checks to make its refinement count look successful. It also reveals that semantic refinement needs feedback-driven resampling over navigable and visible surface masks, not merely a larger random search.

## Recovery findings

### 1. Blank-map creation was not atomic

RPG-Cobo reported `applied=true` when creating `M973`, and the database subsequently listed it, but the editor could not open `.x/map/M973`. The operation left a semantic database record without usable map data. Rollback returned `rolledback=false`, and no typed deletion operation was exposed.

The experiment preserved that ghost record, moved the third requested ID to unused `M972`, and changed the driver to resume completed variants without overwriting them. This is direct evidence for an AI-native requirement: creation must atomically commit the database record, data file, editor visibility, undo state, and persistence—or return a structured partial-commit recovery handle.

### 2. Generated decoration blocked generated interaction

The first playtest reached `running=true` on Ashcourt but never acquired the entry guide. The trace showed that a generated lamp at `[59,15]` sat one block from the guide at `[59,16]` and occupied the direct approach corridor.

The driver diagnosed the obstruction from the semantic plan and original placement UID. It moved the lamp perpendicular to the generated entry vector, then repeated the playtest. The first relocation attempt also exposed a typed-tool inconsistency: placement accepts `y=-1` as a surface-relative convention, while relocation requires the resolved object height (`y=4`). The rejected call did not mutate the map.

The successful retry:

- started runtime on `M972`;
- moved along the generated entrance approach;
- acquired event `1000009`;
- returned `accepted=true` from interaction;
- displayed “Welcome to Ashcourt”;
- stopped normally;
- saved, reloaded, reopened, and validated the final town.

This was an organically discovered defect-injection test. The lesson is broader than “move the lamp”: planners must reserve interaction envelopes and validators should test spawn-to-critical-event affordances with runtime collision, not only a 2D surface approximation.

### 3. Overview capture completion was asynchronous

The refinement capture was copied while black, and the first final capture returned stale imagery from Willowford even though every structured query reported `M972`, `Ashcourt`, and the correct block/event counts. Repeated captures drained the renderer queue and returned Ashcourt's previously known hash.

The driver now issues a capture, waits, requests it again, waits for rendering, and only then copies the output. The stale frames are treated as feedback-pipeline failures, not map evidence. A purpose-built API should return a render revision, requested map ID, completion state, and content hash, rather than a path before the frame is guaranteed current.

## Final selected result

Ashcourt (`M972`) after recovery contains:

| property | final value |
|---|---:|
| Occupied blocks | 30,717 |
| Free-block objects | 128 |
| Events | 9 |
| Chunks | 319 |
| Validation errors | 0 |
| Runtime interaction | accepted, event `1000009` |

Two non-fatal warnings remain:

- events `1000007` and `1000008` share one exact connector position;
- the conservative 2D traversability approximation finds 24 components, with 91.4% of walkable columns in the largest component.

The runtime proof covers the generated spawn-to-guide interaction slice. It does not prove that every building entrance, resident, or isolated approximation component is reachable under full physics.

Artifacts:

- `work/agent-output/M972-civic_accretion-final.png`
- `work/agent-output/M972-civic_accretion-runtime.png`
- `work/agent-output/M975-river_crossing-reloaded.png`
- `work/agent-output/M974-road_confluence-reloaded.png`
- `work/agent-output/M972-civic_accretion-reloaded.png`

## Quantitative execution record

The completed trace contains 354 recorded typed operations and six recorded tool failures:

- one deliberately preserved required failure opening ghost `M973`;
- two rejected planned props across generated towns;
- three rejected market refinement props.

In addition, the driver records the first targetless runtime attempt separately because it was a failed end-to-end assertion rather than a tool-call exception. The relocation calls using an invalid height were rejected before the recorder could persist the in-memory retry trace; the contract mismatch is documented above and covered by the corrected code path.

All three successful maps survived save, complete tool reload, reopen, inspection, and validation.

## What this proves

- The explicit normalized spatial authorship in Experiment 004 can be removed for three bounded cause families.
- One deterministic simulator can turn cause, phases, programs, constraints, and a seed into distinct executable RPG-Cobo towns.
- Semantic identity can survive outside the engine strongly enough to support node-level refinement and causal diagnosis.
- Visual comparison remains necessary; the cleanest structural score did not select the strongest historical result.
- Runtime feedback can diagnose a conflict that structural validation misses and can drive a semantic repair.
- Refusing unsafe or colliding placements is compatible with autonomous progress when the system exposes enough state to resample or revise.

## What this does not prove

- The simulator does not understand arbitrary settlement causes or learn new growth rules.
- Cause-specific seeding logic is still implemented in code.
- Engine objects do not retain native district, plot, frontage, or phase identity; the JSON plan is the semantic source of truth.
- The asset pack is unchanged from Experiment 004, so cross-pack transfer remains untested.
- Buildings are still rotation-constrained, interiors are absent, and no quest chain or economy was generated.
- One short runtime path does not prove whole-map navigation.
- A ghost database record and two warnings remain; the environment is agent-operable, not transactionally complete.

## Lessons for an AI-native platform

1. **Make historical state native.** Roads, plots, buildings, entrances, districts, phases, and obsolete fabric should remain addressable engine objects after placement.
2. **Reserve affordance envelopes.** Spawn routes, doors, dialogue radii, and navigation corridors should participate in placement constraints.
3. **Unify coordinate contracts.** Placement, inspection, movement, and relocation should share canonical coordinates or expose explicit transforms.
4. **Make lifecycle operations atomic.** Creating a map must not leave its index and data file in different states.
5. **Make capture revisioned.** Visual feedback needs a completion handshake and identity/hash guarantees.
6. **Separate structural and perceptual evaluation.** Both are required, and disagreement should be inspectable rather than averaged away.
7. **Persist rejection explanations.** Collision failures are useful planning evidence when returned with the blocking objects and candidate alternatives.
8. **Validate through the runtime model.** Approximate topology is helpful, but critical affordances should be checked with the actual collision and interaction system.

## Recommended next experiment

Apply a changed brief to Ashcourt or Barrelstead while preserving existing semantic instances and settlement identity. The key test is no longer initial generation. It is whether an agent can interpret a delta such as population growth, a blocked market, a new institution, or a damaged route; decide what should remain; generate only the necessary additions and adaptations; and verify that the town still works.
