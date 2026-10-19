# GrokBot Hackathon Starter

Production-ready starter template for a 4-person AI agent hackathon team using Next.js + TypeScript + local mock agent workflows.

## Quick start

```bash
npm install
npm run dev
```

Open http://localhost:3000.

## Scripts

- `npm run dev` - start local development server
- `npm run build` - production build
- `npm run lint` - ESLint validation
- `npm run typecheck` - TypeScript strict check
- `npm run test` - Vitest watch mode
- `npm run test:run` - Vitest single run

## Local mock mode

This starter works without API keys by default (`GROK_PROVIDER_MODE=mock`).

1. Copy environment values:
   ```bash
   cp .env.example .env.local
   ```
2. Keep `GROK_PROVIDER_MODE=mock` during local development.
3. Add `XAI_API_KEY` only when official xAI integration is enabled.

## API endpoints

- `GET /api/health`
- `GET /api/agents`
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/workflows`

## Team ownership

- **Developer 1:** frontend/ui/visualization (`src/components`, `src/app/page.tsx`)
- **Developer 2:** agent orchestration/workflows (`src/agents`, `src/workflows`)
- **Developer 3:** tools + integrations (`src/tools`, `src/app/api`)
- **Developer 4:** tests/reliability/docs (`tests`, `docs`, CI)

See `docs/team-workflow.md` and `HACKATHON_START.md` for execution playbook.
