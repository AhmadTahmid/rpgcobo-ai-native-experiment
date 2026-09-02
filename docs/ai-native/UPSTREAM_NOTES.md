# Upstream and rebase notes

Baseline is upstream `djkotori/rpgcobo-tool` commit `4bbeb25`. Work is on branch `ai-native-experiment`.

## Upstream files modified

- `project/plugin/rpgtools/mcp/load.sk`: loads isolated AI-native modules.
- `project/plugin/rpgtools/mcp/MCPServer.sk`: structured mutation result with `changeid` and optional details.
- `project/plugin/rpgtools/mcp/MCPServerTools.sk`: fixes database merge semantics and debug-start argument translation.
- `project/testplay.sk`: adds structured player state, movement and interaction endpoints for existing IPC.

## New isolated files

- `project/plugin/rpgtools/mcp/AgentNative.sk`
- `project/plugin/rpgtools/mcp/AgentInspect.sk`
- `project/plugin/rpgtools/mcp/AgentAssetTools.sk`
- `project/plugin/rpgtools/mcp/AgentMapTools.sk`
- `project/plugin/rpgtools/mcp/AgentValidation.sk`
- `project/plugin/rpgtools/mcp/AgentPlaytest.sk`
- `project/agent/asset-metadata.json`
- `tools/ai_native_mcp.py`
- `tools/run_experiment_001.py`
- `tools/run_experiment_002.py`
- `tests/ai_native/test_ai_native.py`
- `docs/ai-native/*`

## Rebase risk

Most work is additive and should rebase cleanly. The four modified upstream files have small, localized changes. Highest conflict risk is `MCPServerTools.sk` if upstream fixes debug start or database merging, and `testplay.sk` if the debug IPC section moves.

Internal assumptions to recheck after an upstream update:

- `MapEditor`, `BlockOperation`, `OperationStack`, editor tool IDs and gizmo methods retain their current contracts.
- `MCPServer.processChange()` continues to serialize mutations through elicitation.
- `BlockWorld` encoding remains accessible via `ObjectInput`/`ObjectOutput`.
- Event role defaults remain in `RPGSystem.eventrole`.
- Debug tool/runtime IPC continues to support `invokeIPCScript`.
- If native `collectBlocks`, `Block.rotate`, or `IMat.transformv` become available, simplify the local rotation-0 asset placement fallback and add non-zero rotation tests.
- `OperationStack.submit()` currently advances before redo completes; retain the local exception-atomic wrapper unless upstream changes that ordering.
- `rpgcobo_runtime_reload_tool` is not a discard boundary in Experiment 002; recheck persistence semantics after upstream changes.
- Generic database writes can diverge from an active `MapEditor` copy; use editor-backed mutations until synchronization is defined.

No native DLL, renderer, closed engine file, generated map file, downloaded asset pack, cache, secret or machine-specific configuration is committed.
