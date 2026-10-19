# Architecture

The starter is split into ownership boundaries to reduce merge conflicts:

- `src/components` and `src/app`: UI shell and dashboard
- `src/agents`: agent contracts, registry, providers
- `src/tools`: tool contracts, registry, safe adapters
- `src/workflows`: workflow contracts and mock execution engine
- `src/lib`: shared config/schemas/utils/in-memory adapters

All challenge-specific logic should be added via new agents, tools, and workflows rather than restructuring core folders.
