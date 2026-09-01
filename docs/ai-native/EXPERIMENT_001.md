# Experiment 001 — structured world slice

## Objective

Use the new control layer—not hand-authored `.bw` data—to modify the M980 flat template within a 64×64 region. Target content: ground, winding path, pond, raised feature, forest, clearing, landmark, player start, NPC dialogue, validation, image capture and minimal playtest interaction.

Reproducible driver: `tools/run_experiment_001.py`. Raw local output: `work/agent-output/experiment-001-results.json`. Overview: `work/agent-output/M980-overview.png`. Generated project data and work output are intentionally not committed.

## Operations and results

The driver executed 28 successful MCP operations with zero final-run tool failures. It discovered authored IDs first, then used:

- Path: block 34, `(18,51)` to `(73,43)`, width 3, curvature 0.32, seed 1001; 193 changed cells.
- Pond: water block 8, center `(43,62)`, radius 7, irregularity 0.28, seed 1002; 320 low-level operations.
- Raised feature: an 8×3×8 ground-block volume.
- Forest: real free-block type 20, authored variations `0,1,2,3`, seed 1003; 26 trees placed.
- Clearing: 10×10; 10 generated trees removed.
- Landmark: real `MA008` church, 2,085 block/free-block operations, baked at `(61,2,47)`.
- Player start: block `(20,2,51)`.
- Event: villager `1000001`, model `CV004`, dialogue at `(27,2,49)`.

After generation the 64×64 region contained 29 free blocks (27 simple objects, one door and one roof), one event, elevation 1–18, and approximate traversable surface coverage 0.960938.

## Validation

`rpgcobo_map_validate` returned `valid=true`, zero errors and zero warnings. Metrics: 128×64×128 map, 1 event, 29 free blocks, 7 used block IDs, 16,224 approximately walkable columns, 10 approximate components, and 98.3358% of walkable columns in the largest component.

This is not proof of physical reachability: the validator does not fully model free-block collision, slopes, barriers or event/runtime conditions.

## Visual inspection

The editor produced a 512×512 deterministic overview. The geometry is present according to inspection, but the full-map view is visually low contrast: green/brown ground variants, water and the green-roofed landmark are difficult to distinguish at this scale. This is a useful negative result for the research question—the control layer can build the structures, but the visual feedback interface is not yet strong enough for reliable aesthetic iteration.

## Playtest

Test play launched on M980. Structured state reported the player landed at `[10.0,1.0,25.5]`. A relative move of +1.5 x completed at approximately `[11.431,1.0,25.5]`. Interaction found and accepted event `1000001`. The debug session was stopped normally. The script did not semantically inspect dialogue UI text after interaction.

## Failures encountered while developing the experiment

| observation | classification | response |
|---|---|---|
| `BlockOperation.drawWorld()` calls `BlockWorld.collectBlocks`, absent in the bundled binary | ENGINE LIMITATION | Asset placement compiles equivalent undoable operations with `blockat` and `collectFreeBlocks` |
| Checked-in asset path also calls absent `Block.rotate` and `IMat.transformv` | ENGINE LIMITATION | Rotation 0 uses explicit translation; non-zero rotation is rejected |
| Initial material ordering was lexicographic, yielding variations 0,1,10,11 | IMPLEMENTATION BUG | Material results now sort numerically; experiment uses tree variations 0–3 |
| Full-map overview is too low-contrast/small for confident aesthetic judgment | INTERFACE LIMITATION | Preserve result; next iteration needs crop/zoom/isometric/player-view capture |
| Authored asset/material records lack semantic tags such as “shrine” or color/style descriptors | ASSET LIMITATION | Empty authored metadata overlay added; no brittle inferred tags fabricated |
| Baked MA source identity cannot be recovered from destination geometry | REPRESENTATION LIMITATION | Tools report provenance loss and operate on resulting free-block UIDs |
| Validator cannot prove physics-backed reachability | REPRESENTATION LIMITATION | Output explicitly labels connectivity approximate |

No final-run failure was attributable to a MODEL LIMITATION. The weak visual evaluation loop is primarily an interface/asset-vocabulary problem.
