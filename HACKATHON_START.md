# HACKATHON START

## Immediate sequence when track is announced

1. Define the problem and success criteria in one paragraph.
2. Decide agent roles needed (orchestrator/researcher/executor/reviewer or custom).
3. List required tools + external APIs and approval boundaries.
4. Assign workstreams across 4 developers (frontend/agents/tools/qa).
5. Configure workflow steps in `src/workflows/examples`.
6. Build minimum end-to-end path from task input to result panel.
7. Integrate, run checks, and rehearse demo.

## 5-minute preflight per teammate

- Pull latest branch and run `npm install`.
- Run `npm run lint && npm run typecheck`.
- Confirm app starts with `npm run dev`.
- Confirm mock mode is active (`GROK_PROVIDER_MODE=mock`).
- Open issue/branch for assigned module.

## Extension recipes

- Add agent: implement `Agent` in `src/agents/providers` and register in `src/agents/registry/bootstrap.ts`.
- Add tool: implement `Tool` in `src/tools/adapters` and register via `toolRegistry`.
- Add API integration: add server-side adapter in `src/tools/adapters` or `src/agents/providers`.
- Add workflow: create definition in `src/workflows/examples` and wire in orchestrator.
- Add page: create route in `src/app` and reuse shared components.
- Add UI component: add reusable primitive in `src/components/ui`.
