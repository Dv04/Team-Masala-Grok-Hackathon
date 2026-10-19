# Troubleshooting

## App does not start

- Ensure Node.js 20+.
- Delete `node_modules` and run `npm install`.

## API keys missing

- Mock mode requires no keys.
- For real provider mode set `GROK_PROVIDER_MODE=xai` and provide `XAI_API_KEY`.

## Tests failing on fetch

- API route tests call handlers directly; ensure no browser-only globals are required.
