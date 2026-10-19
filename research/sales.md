# Sales & Lead Gen: Top 3 Open-Source Repos (updated: top 3, building blocks for an AI agent)

Researched Oct 19, 2026 (CT). Star counts, push dates, licenses and releases come from the live GitHub API that day. Dates are in America/Chicago (CT).
I looked at 22 candidates: twenty, krayin/laravel-crm, espocrm, frappe/crm, SuiteCRM-Core, atomic-crm, erxes, relaticle, DeskcommCRM, mautic, listmonk, plunk, warmbly, OpenOutreach, SalesGPT, gosom/google-maps-scraper, omkarcloud/google-maps-scraper, theHarvester, reacher (check-if-email-exists), crawl4ai, firecrawl, browser-use, ScrapeGraphAI and crawlee.

## Update: narrowed to the top 3
New rule: these repos should also work as building blocks for your own AI assistant bot. That bot has its own computer, connects to apps through MCP, runs routines and hands work to subagents. So I favored repos that have an MCP server or a clean API/CLI, can run without a screen, and are easy to self-host.

**Top 3: Twenty (#1), OpenOutreach (#2), Warmbly (#3).** Together they cover the whole job: the CRM, building lead lists, drafting outreach and sending it.
gosom/google-maps-scraper (#4) and Reacher (#5) are now **add-ons / runners-up**. Both are permissive (MIT) REST services the bot can call, but each does one narrow job.

How each top pick plugs into the bot:
- **Twenty:** Register `https://{domain}/mcp` as one of the bot's MCP connectors (OAuth or API key). Point Twenty's signed webhooks at the bot's event endpoint so new or changed deals start routines.
- **OpenOutreach:** Install it on the bot's computer (`uv tool install openoutreach`). A "prospecting" subagent runs `openoutreach find N --json` on a schedule, guided by the included SKILL.md. Its JSON Lines output gets upserted into Twenty.
- **Warmbly:** Run it self-hosted with Docker and connect it as an MCP connector (MCP is in its docs; I didn't verify it's included when self-hosted) or use the REST API/SDK. An "outreach" subagent signs contacts up for campaigns, and Warmbly's reply/bounce webhooks start follow-up routines.

## Original 5 candidates in detail (#1-#3 are the picks; #4-#5 are now runners-up)

### 1. Twenty: CRM and system of record
- URL: https://github.com/twentyhq/twenty
- Role: The CRM where every lead, company, deal and activity lives. Twenty describes itself as an open alternative to Salesforce, built for AI. You can add your own objects and fields, and it has workflows and agents.
- Verified: 58,585 stars. Last push Oct 19, 2026. Latest release twenty/v2.49.0 (Oct 19, 2026).
- License: Mostly AGPL-3.0. It adds a "Twenty Application Exception": apps that only talk to Twenty through its published REST/GraphQL APIs, webhooks or SDKs are not covered by AGPL. Files marked `/* @license Enterprise */` are under a commercial license. The CLI and SDK packages are MIT.
- Interop (best of all candidates):
  - A built-in MCP server at `https://{domain}/mcp` (streamable-http, OAuth 2.1 or API-key Bearer). It works self-hosted too.
  - REST at `/rest` and GraphQL at `/graphql`, plus an OpenAPI spec for each workspace and a metadata API for changing the schema.
  - Signed webhooks (HMAC-SHA256) on record create/update/delete, e.g. `person.created` or `opportunity.updated`. A workflow webhook trigger handles incoming data.
- Caveats: API limit is 100 requests/min and 60 records per batch. Don't change Twenty's own code unless you're willing to open-source the changes under AGPL. Integrating over the API is fine. Webhooks can't be filtered by event type yet.

### 2. OpenOutreach: AI SDR (find, qualify and email leads)
- URL: https://github.com/eracle/OpenOutreach
- Role: You describe your product and target market. It finds matching people from a licensed data provider (BetterContact), scores each one against your ideal customer profile with a written reason, buys verified work emails only when told to, and writes and sends the opening email from your own mailbox.
- Verified: 3,337 stars. Last push Oct 19, 2026. 100+ commits, the latest on Oct 19, 2026. It has no GitHub releases; it ships on PyPI (`uv tool install openoutreach`).
- License: GPL-3.0. Fine for internal use, since it runs as a separate CLI.
- Interop: A CLI built for agents and scripts (`find`, `send`, `run`, `status`). Output is CSV or JSON Lines on stdout, and the parts can be piped together: `outfind find 50 --json | outsend`. It includes a Claude Code plugin and skill (`skills/find-leads/SKILL.md`) that any agent can follow. CSV columns match what Instantly and Smartlead import.
- Caveats: You need an LLM API key and a BetterContact key, and verified emails cost credits. There is no HTTP API or MCP, so the orchestrator calls it through a shell or wraps it. Older versions automated LinkedIn. The current version uses no browser and no scraping. GPL means any changes you distribute must stay GPL.

### 3. Warmbly: cold email sequences, warmup and deliverability
- URL: https://github.com/warmbly/warmbly
- Role: Sends multi-step cold email campaigns from mailboxes you own, with per-mailbox caps and spacing. It also handles mailbox warmup, bounce/complaint suppression, and a shared inbox for replies, and has AI reply playbooks.
- Verified: 461 stars. Created Jan 17, 2026. Last push Oct 19, 2026. Latest release v0.6.57 (Oct 19, 2026), and it ships releases very often.
- License: Apache-2.0, the most company-friendly license in this stack.
- Interop: REST API, webhooks, an SDK, a CLI, OAuth, an OpenAPI spec and a realtime WebSocket. Its docs list an MCP server, "agent tools (REST)", Zapier and an n8n guide for two-way traffic. HubSpot and Slack integrations come built in.
- Caveats: The project is only 9 months old and the community is small. The MCP server is in the docs, but I didn't confirm it's included when you self-host. It has its own lightweight CRM; keep Twenty as the master copy and sync to it over webhooks.

### 4. gosom/google-maps-scraper: lead lists for local and SMB businesses
- URL: https://github.com/gosom/google-maps-scraper
- Role: Builds lead lists from Google Maps by search query. For each business it returns name, phone, website, address, ratings, coordinates and (optionally) emails found on its site.
- Verified: 6,626 stars, 1,037 forks. Last push Sep 23, 2026. Latest release v1.18.1 (Sep 20, 2026).
- License: MIT.
- Interop: CLI, web UI and a REST API in web-server mode (`POST/GET /api/v1/jobs`). Output goes to CSV, JSON, PostgreSQL, S3 or custom writer plugins. It's written in Go and runs in Docker.
- Caveats: Scraping Google Maps may break Google's terms of service, so get legal sign-off (a job for the Legal department). The README's MCP mention belongs to LeadsDB, a separate commercial service, not the scraper. Only useful if your customers are local or SMB businesses.

### 5. Reacher (check-if-email-exists): email verification
- URL: https://github.com/reacherhq/check-if-email-exists
- Role: Checks that an email address exists without sending it a message, so outreach stays under bounce limits and mailboxes stay healthy. It's written in Rust.
- Verified: 10,208 stars. Last push Oct 16, 2026. Latest release v0.11.10 (Oct 16, 2026).
- License: MIT. GitHub's API and the current README both say MIT. An older docs page and the archived `reacherhq/backend` repo still mention AGPL plus a commercial license, but the current repo license is MIT.
- Interop: An HTTP backend in Docker (`docker run -p 8080:8080 reacherhq/backend`) with one endpoint, `POST /v0/check_email`, plus an OpenAPI spec. Optional bulk endpoints are backed by Postgres. It can also be used as a CLI or Rust library.
- Caveats: SMTP checks need outbound port 25, which many clouds block, so you may need a proxy. Results on catch-all domains are uncertain.

## Runners-up
- **gosom/google-maps-scraper** (#4 above, MIT, REST): Great for local/SMB lead lists the bot can call over REST. It's narrow and carries Google terms-of-service risk.
- **Reacher** (#5 above, MIT, REST): The bot should run this check before every send. It's a one-endpoint tool, so I treat it as an add-on rather than a core pick.
- **Krayin CRM** (krayin/laravel-crm, 24,027 stars, MIT, v2.2.7 on Oct 16, 2026): A solid MIT Laravel CRM with leads and pipelines. I couldn't confirm a first-party MCP server, and the API/webhook story isn't as strong as Twenty's. Pick it if Twenty's AGPL is a deal-breaker.
- **Relaticle** (relaticle/relaticle, 1,772 stars, AGPL-3.0, v3.6.6 on Oct 18, 2026): A CRM built for agents, with 37 MCP tools and a REST API. Smaller and less proven than Twenty, with the same AGPL issue and none of Twenty's exceptions.
- **Mautic** (mautic/mautic, 10,803 stars, GPL-3.0, 7.2.1 on Sep 23, 2026): Mature marketing automation with REST and webhooks. It's built for nurture and marketing email rather than cold outreach from your own mailboxes, so it fits Marketing better.
- Others I dropped: SalesGPT (no push since Sep 16, 2024, so effectively abandoned). DeskcommCRM (MIT, MCP, but focused on WhatsApp, Portuguese only, and less than 6 months old). theHarvester (GPL-2.0, a security/OSINT tool, not built for sales). listmonk and Plunk (AGPL, made for newsletters and transactional email, not cold sequences). crawl4ai, firecrawl and browser-use (good enrichment tools, but they overlap with Research; firecrawl is AGPL). EspoCRM, Frappe CRM and SuiteCRM (all AGPL and less agent-ready than Twenty).

## How they fit together (the 3 picks plus 2 optional add-ons) and plug into the orchestrator
```
Orchestrator --"get 50 leads for ICP X"--> OpenOutreach (CLI, JSON Lines)  ┐
             --"local leads in Austin"--> gosom maps scraper (REST /api/v1/jobs) ┤
                                                                            v
                                     Reacher  POST /v0/check_email  (drop bad emails)
                                                                            v
                                     Twenty CRM  (REST/GraphQL upsert; MCP for agents)
                                                                            v
                                     Warmbly campaign  (REST/MCP: enroll contacts)
Warmbly webhooks (reply/bounce/open) --> orchestrator/n8n --> update Twenty deal stage
Twenty webhooks (opportunity.updated) --> orchestrator --> Finance, Data dashboard, Support
```
- **Twenty is the shared hub.** Other departments (Support, Finance, Data/analytics) read and write the same Person, Company and Opportunity records through Twenty's MCP or API. That gives every department one customer ID.
- **The orchestrator calls each tool directly.** Twenty and Warmbly over MCP (per their docs), Reacher and the maps scraper over REST, OpenOutreach through a shell/CLI wrapper (it emits JSON Lines). None of the five supports A2A natively; add a thin A2A or MCP wrapper if the orchestrator requires one.
- **Events flow back by webhook.** Twenty's signed record webhooks and Warmbly's webhooks go to the orchestrator or an n8n instance, which updates statuses and alerts other departments.
- **QA should check every send.** OpenOutreach drafts and Warmbly sequences should pass QA and founder approval before anything goes out.
- **License summary:** Warmbly (Apache-2.0), the maps scraper and Reacher (MIT) are permissive. Twenty (AGPL with an API exception) and OpenOutreach (GPL-3.0) are safe if you integrate over their APIs or CLI and don't distribute changed versions.

---

## Update (Oct 19, 2026, 6:25 PM CT): picks #4 and #5 added
Twenty, OpenOutreach and Warmbly stay #1-#3. The two new picks fill the remaining gaps: **email verification** and **lead enrichment/scraping**. I re-checked their stats on the GitHub API today. Both are now **picks** instead of runners-up. gosom/google-maps-scraper stays a runner-up.

### 4. Reacher (check-if-email-exists): email verification before every send
- URL: https://github.com/reacherhq/check-if-email-exists
- Role: Checks that an address exists (syntax, MX record, SMTP handshake, disposable/role/catch-all flags) without sending a message. Bad addresses get dropped before Warmbly sends, which keeps bounce rates and mailbox reputation healthy.
- Verified: 10,209 stars. Last push Oct 16, 2026. Latest release v0.11.10 (Oct 16, 2026).
- License: MIT (GitHub API and current README). An older docs page and the archived `reacherhq/backend` repo still mention AGPL plus a commercial license. The current repo license is MIT.
- Interop: A Rust HTTP backend in Docker (`docker run -p 8080:8080 reacherhq/backend`). One endpoint, `POST /v0/check_email`, plus an OpenAPI spec. Optional bulk endpoints are backed by Postgres (`RCH_ENABLE_BULK=1`). It also works as a CLI or Rust library. Headless, no UI needed.
- Caveats: SMTP checks need outbound port 25, which many clouds block, so you may need a SOCKS proxy (it supports one). Catch-all domains come back "unknown". I found **no MCP server**, so it needs a small adapter.
- In your bot: Wrap `POST /v0/check_email` as one MCP tool, `sales.verify_email`, and have the outreach subagent call it on every contact before signing them up in Warmbly.
- Fit with the shared contract: It has REST but no MCP, so it needs a thin MCP adapter. The contract allows this. The adapter writes one JSONL event per check. It isn't customer-facing, so no qa.check is needed.

### 5. Crawl4AI: lead enrichment (company websites to data for personalized emails)
- URL: https://github.com/unclecode/crawl4ai
- Role: Turns a lead's company website (about page, pricing, careers, blog) into clean Markdown, or pulls structured fields via an LLM or CSS/XPath schema. The data covers industry, size signals, tech stack, recent news and contact pages. Use it to score leads and personalize the openers OpenOutreach drafts.
- Verified: 85,861 stars. Last push Oct 19, 2026. Latest release v0.9.5 (Oct 14, 2026).
- License: Apache-2.0.
- Interop: The self-hosted Docker server is protected by `CRAWL4AI_API_TOKEN`. Its REST endpoints are `/md`, `/html`, `/crawl`, `/crawl/stream`, `/screenshot`, `/pdf` and `/execute_js`. The server code (`deploy/docker/server.py`) includes a built-in MCP layer with tools `md`, `html`, `screenshot`, `pdf`, `execute_js`, `crawl` and `ask`, served at `/mcp/ws`, `/mcp/sse` and `/mcp/schema`. There is also a Python SDK (`arun_many` for batches). It runs headless and the images support AMD64 and ARM64.
- Caveats: The self-hosted MCP uses **SSE/WebSocket, not streamable HTTP**. Only the paid cloud MCP at `api.crawl4ai.com/mcp` uses HTTP transport. So for the contract, either call the REST API through an adapter or put an SSE-to-streamable-HTTP bridge in front of it. It overlaps with the Research department's crawling, so share one instance. Respect robots.txt and site terms. The README pushes the paid cloud heavily, but the open-source version is fully usable on its own.
- In your bot: Register it as the bot's web-reading MCP connector (through a bridge) or call REST `/md` and `/crawl`. An enrichment subagent crawls each new Twenty company record and writes a summary or fields back to Twenty.
- Fit with the shared contract: It has native MCP, but over SSE or WebSocket, so it needs a bridge or REST adapter. The adapter logs each crawl to the JSONL event log. Its output feeds drafts but isn't customer-facing itself.

### Runner-up for these slots
- **gosom/google-maps-scraper** (6,627 stars, MIT, v1.18.1 on Sep 20, 2026, last push Sep 23, 2026 CT): Good for local/SMB lead lists over REST (`/api/v1/jobs`). It lost to Crawl4AI because it only covers one data source, carries Google terms-of-service risk, and has no MCP of its own. Add it if your customers are local businesses.

### How all 5 fit the shared contract (MCP + JSONL log + qa.check)
| Repo | MCP (streamable HTTP) | Adapter needed | Events for JSONL log | Customer-facing? qa.check |
|---|---|---|---|---|
| Twenty | Yes, native `/mcp` | No | Signed record webhooks map to events | Not itself |
| OpenOutreach | No (CLI with JSON Lines output) | CLI-to-MCP wrapper | Its JSON Lines output maps directly to events | **Yes, its drafts/sends must pass qa.check. Gate `send` behind it and don't let the bot call `run`/`send` directly** |
| Warmbly | Yes per docs (self-host not verified) | Maybe | Webhooks (reply/bounce/open) | **Yes, every campaign/sequence goes through qa.check before launch** |
| Reacher | No (REST) | Thin MCP adapter | One event per check | No |
| Crawl4AI | Yes, but SSE/WebSocket | Bridge or REST adapter | One event per crawl | No |

Gating rule: the bot never sends directly. OpenOutreach's role is limited to `find`, with `send` disabled. Drafts go to qa.check, then founder approval, then Warmbly. All five tools need their actions logged by the adapter or orchestrator; none of them writes to a shared JSONL log on its own.
