# Marketing bot (Pulse Studio)

Drafts launch copy when a product listing goes live. Sandbox only: nothing is posted to X, LinkedIn, or the web.

Dept string: `marketing`. Webhook: `http://127.0.0.1:8899/pulse`.

On startup the bot `POST`s `{DEPARTMENTS_URL}/api/webhooks` with `{url: http://127.0.0.1:8899/pulse, dept: marketing}`. `DEPARTMENTS_URL` defaults to `http://127.0.0.1:8810`. If that call fails it logs and keeps running. It also polls `GET /api/events`, because department webhooks fire only for approvals, routed tasks, and executed actions.

`listing_live` (product `{type, title, tagline, price, cost, trend}`, plus `url` and `action`) gets a `running` event immediately, then drafts: an X post and short thread, a LinkedIn post, a short blog draft, and landing copy (headline, subhead, bullets, CTA). Copy is grounded in the listing and, when present, a `trend_spotted` event `{trend, why, source: x}`. Drafts are marked `needs_qa: true` and sent through `POST /api/qa/check`. Pass logs `done`. Fail revises once and re-checks. Founder logs `needs_approval`. A listing with no assets also emits `output.kind: design_request` with `brand` and `brief`.

Without `XAI_API_KEY` every draft is a labeled mock (`mode: mock`). That is the default until a key is provided. With a key, text calls use httpx against `https://api.x.ai/v1` only. Models are `GROK_TEXT_MODEL` (default `grok-4`), `GROK_FAST_MODEL` (default `grok-4`), and `GROK_IMAGE_MODEL` (default `grok-imagine-image-2.0`). Each must be a `grok-*` model. Requests omit `stop` and presence/frequency penalties. This bot does not generate images; design requests go to the design department.

## Run

```bash
# terminal 1: department service
departments/start.sh

# terminal 2
dev1/marketing_bot/run.sh
```

## Tests

```bash
python3 dev1/marketing_bot/tests/test_marketing.py
# with both processes up:
python3 dev1/marketing_bot/smoke.py
```
