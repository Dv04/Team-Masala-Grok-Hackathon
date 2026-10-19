# Customer Support department: top 3 open-source repos
Researched Mon Oct 19, 2026 (times in CDT, UTC-5). Stars, push dates, releases and licenses come from the GitHub API on this date. Interop claims come from the official READMEs and docs.

Criteria: real support capability (inbox triage, drafting replies, FAQs), active in 2025-26, license usable by a company, self-hostable, and especially **agent-friendly**: an MCP server or clean REST API/SDK an LLM agent can call, webhooks to emit events, and headless operation. The user wants these as building blocks for their own AI assistant bot (own computer, MCP connectors, routines, subagents).

## 1. Chatwoot: shared inbox, live chat, help center (system of record)
- URL: https://github.com/chatwoot/chatwoot
- Stars: 37,970. Last push: Oct 19, 2026. Latest release: v4.18.0 (Sep 17, 2026, CDT).
- License: MIT for everything outside `enterprise/`. The `enterprise/` folder, which includes the Captain AI services, has its own enterprise license.
- What it does: omnichannel shared inbox (email, website live chat, WhatsApp, social and more) with assignment, labels, automations, canned responses, and a built-in Help Center for publishing FAQ articles.
- Interop: full REST API (accounts, conversations, messages, contacts, help center), account webhooks (`message_created`, `conversation_*`...), and the **Agent Bot API**. You register a bot with a webhook URL and attach it to an inbox. Chatwoot POSTs every customer message to the bot, which replies through the API with its own token and hands off to a human by setting status=open. Payloads are signed with a webhook secret.
- Caveats: no official MCP server yet. An MCP integration PR for Captain (#13456) was still open as of Jun 2026, and maintainers said it is "on our roadmap but not an immediate priority". Use the REST API or a thin MCP wrapper. Captain AI (built-in AI agent) is enterprise-licensed and paid on hosted plans, but you don't need it if your own bot is the brain. It's a Rails + Postgres + Redis + Sidekiq stack.
- **Plugs into the bot:** register your bot as a Chatwoot Agent Bot. Inbound messages arrive as webhooks, the bot drafts and sends replies (or leaves private notes for approval) via the REST API, and a subagent can write and update Help Center FAQ articles through the API.

## 2. Inbox Zero: AI email triage and reply drafting (founder/support@ mailbox)
- URL: https://github.com/elie222/inbox-zero
- Stars: 12,682. Last push: Oct 19, 2026. Latest tagged release: desktop-v0.1.20 (Oct 19, 2026). That tag is the desktop app; the web app ships from main and I did not check its own version.
- License: **AGPL-3.0 plus an added "commercial monetization restriction"**: you can't sell access to the software itself or offer it as a paid service. Internal use for your own company's inbox looks fine, but have a lawyer confirm. Don't resell it.
- What it does: AI assistant for Gmail and Outlook. You write rules in plain English and it labels, archives, forwards, drafts replies, calls webhooks, and notifies Slack/Teams/Telegram as mail arrives. It also has reply tracking, digests, and stats.
- Interop: **official MCP server** (Streamable HTTP at `/mcp`, OAuth with PKCE). Tools: `search_inbox`, `read_thread`, `create_draft` (never sends), rule CRUD, and stats. Sending needs a separate `mcp:send` scope. It also has a REST API (`/api/v1`, API-Key header, scoped keys), an API CLI, and a "Call webhook" rule action. Self-hosted via `npx @inbox-zero/cli setup` or Docker Compose.
- Caveats: email only (Gmail/Outlook), no live chat or ticketing. Restrictive license (above). MCP and the external API are off by default on self-host (`MCP_SERVER_ENABLED`, `NEXT_PUBLIC_EXTERNAL_API_ENABLED`).
- **Plugs into the bot:** add it as an MCP connector. The bot's support subagent searches and reads threads, creates drafts for human approval (safe by default), and edits triage rules. Rules fire webhooks back to the orchestrator for urgent mail.

## 3. RAGFlow: grounded answers and FAQ knowledge engine
- URL: https://github.com/infiniflow/ragflow
- Stars: 92,487. Last push: Oct 19, 2026. Latest release: v1.0.0-rc2 (Oct 16, 2026). Releases are frequent.
- License: **Apache-2.0** (permissive, the cleanest of the three).
- What it does: RAG engine with deep document parsing (PDFs, docs, tables, scans), chunk inspection, citations, and chat assistants over datasets. Point it at product docs, past resolved tickets, and policies, and you get cited answers for reply drafts. It's also the source for generating and refreshing FAQs.
- Interop: REST API and a Python SDK (in the `sdk/` folder). It has a **built-in MCP endpoint** (`POST /api/v1/mcp`, Bearer API key) plus an optional standalone MCP listener (`/mcp`, `/sse`). MCP tools: `ragflow_retrieval`, `ragflow_list_datasets`, `ragflow_list_chats`. Runs headless via Docker.
- Caveats: 1.0 is a Go rewrite and still a release candidate, so pin a version and test. It's a heavy stack (Elasticsearch/Infinity, MySQL, MinIO, Redis) that wants a beefy box. It produces answers, not a public FAQ site, so publish through Chatwoot's Help Center.
- **Plugs into the bot:** add it as an MCP connector. Any subagent (support, sales, QA) calls `ragflow_retrieval` for cited company knowledge before drafting. A routine re-ingests new docs and resolved tickets nightly.

## Runners-up
- **Dify** (langgenius/dify, 158,927 stars, release 1.17.1 Sep 10, 2026): excellent visual agent/workflow builder with two-way MCP (publishes apps as MCP servers and uses MCP tools) and a full API. It lost because its "modified Apache 2.0" license bans multi-tenant use and logo removal without a commercial license, and because it's a whole agent platform that overlaps with the bot you're building, not a building block.
- **Onyx** (onyx-dot-app/onyx, 32,592 stars, v4.9.2 Oct 15, 2026; MIT outside `ee/`): enterprise search across Slack, Gmail, Drive, GitHub, Zendesk and more, with its own MCP server. It's a great company-wide knowledge layer and possibly better owned by Data/Research. For support-doc RAG it overlaps with RAGFlow.
- **Zammad** (zammad/zammad, 6,018 stars, AGPL-3.0, pushed Oct 19, 2026): mature ticketing with a REST API, webhooks, and AI features in 7.0 (summaries, writing assistant). MCP is community-only (Softoft-Orga/zammad-mcp-server). It lost to Chatwoot on live chat and bot API and on license.
- **Libredesk** (abhinavxd/libredesk, 3,055 stars, AGPL-3.0, v2.9.0-rc.9 Oct 10, 2026): single Go binary with inbox, chat, help center, AI copilot, API, and HMAC webhooks, with no paid tiers. It's younger, webhooks are not retried, there's no MCP, and it's AGPL.
- Also considered and rejected: FreeScout (AGPL, key features are paid modules), osTicket (GPL-2.0, dated, last push Jun 2026), UVdesk (OSL-3.0), Frappe Helpdesk (AGPL, tied to the Frappe stack), Parlant (Apache-2.0 customer-facing agent framework, but last push Jul 12, 2026), AnythingLLM (MIT, MCP-compatible, but more a chat app than a support tool), Typebot (Functional Source License, not OSI open source), Botpress (open-source v12 last released 2023, now cloud-centric), Rasa (Apache, last push Jul 2026, Pro features gated), Flowise (GitHub shows it **archived**), Papercups (inactive since Feb 2024), Peppermint (archived), Helpy (last push 2023), Mail-0/Zero (MIT but last push May 2026), BookStack and Docmost (good wikis, but Chatwoot's Help Center covers FAQ publishing).

## How the 3 fit together and plug into the orchestrator / AI bot
1. **Intake:** email to Inbox Zero rules (label/priority, webhook to orchestrator). Chat, WhatsApp and support@ go into Chatwoot, which sends Agent Bot webhooks to the bot.
2. **Answer:** the support subagent calls RAGFlow `ragflow_retrieval` (MCP) for cited context, then drafts with Inbox Zero `create_draft` (MCP) or as a Chatwoot private note or reply (REST).
3. **Approve and send:** a human or the QA department reviews drafts. Nothing is sent by default (Inbox Zero drafts never send without `mcp:send`; Chatwoot notes are private).
4. **Learn:** a nightly routine exports resolved Chatwoot conversations to a RAGFlow dataset, clusters repeat questions, and writes or updates FAQ articles via the Chatwoot Help Center API.
5. **Report:** Chatwoot reports and Inbox Zero stats (`get_stats_by_period`, `get_response_time_stats`) feed the Data/analytics dashboard. Escalations such as bugs become GitHub issues for Engineering.
Connections: 2 of 3 have native MCP (Inbox Zero, RAGFlow). Chatwoot needs a small MCP wrapper around its REST API, or its webhooks can go straight to the orchestrator. All three are self-hostable with Docker.

---
# Addendum (Oct 19, 2026, 6:30 PM CDT): picks #4 and #5, plus a check against the shared team contract
Contract: departments talk over MCP (streamable HTTP; REST/webhook adapters are fine), every action is logged to a shared JSONL event log, and anything customer-facing goes through a `qa.check` gate.
Gaps in #1-3: Chatwoot has no MCP server, there was no central place to enforce logging and `qa.check`, and nothing published a public FAQ/docs site (Chatwoot's Help Center is basic).

## 4. ContextForge (IBM MCP Gateway): Chatwoot MCP wrapper, plus logging and the QA gate
- URL: https://github.com/IBM/mcp-context-forge
- Stars: 4,656. Last push: Oct 19, 2026. Latest release: v1.0.11 (Sep 28, 2026, CDT).
- License: **Apache-2.0**.
- What it does: an MCP gateway and registry. It turns REST APIs into MCP tools and federates other MCP servers. You build "virtual servers" from a chosen set of tools and serve them over **streamable HTTP**, SSE, or stdio. It also handles A2A agents. It comes with auth, RBAC, rate limits, retries, an admin UI, and OpenTelemetry.
- Why it fills the gaps:
  - Register Chatwoot's REST endpoints, plus RAGFlow, Inbox Zero and BookStack, and you get one `support` MCP server over streamable HTTP, with only the tools you allow. That's the missing Chatwoot MCP, without relying on a small community wrapper.
  - Plugin hooks (`tool_pre_invoke` and `tool_post_invoke`, documented in plugins/README.md) are the natural place to (a) append every call to the shared JSONL event log and (b) block customer-facing tools (send reply, publish FAQ) until `qa.check` passes. The QA call can be an external MCP/HTTP plugin.
  - Built-in JSON logging to file (`LOG_FORMAT=json`, `LOG_TO_FILE=true`, with rotation) gives an operational log as well. That log uses the gateway's own format; the team's event schema needs the small plugin.
- Caveats: this is shared infrastructure, so the Orchestrator teammate may already be choosing a gateway. Run one gateway for the whole company, not one per department. It's a fairly large Python service (Postgres/SQLite, Redis optional). Generating tools from OpenAPI depends on Chatwoot's spec being clean. I haven't tested that, so you may need to hand-write some tools.
- **Plugs into the bot:** the bot connects to one MCP URL per department. Its support subagent sees curated tools such as `chatwoot_reply` and `faq_publish`, and every call is logged and QA-gated automatically.

## 5. BookStack: public FAQ, help docs and internal SOP wiki
- URL: https://github.com/BookStackApp/BookStack
- Stars: 19,089. Last push: Oct 19, 2026. Latest release: v26.09.1 (Sep 29, 2026).
- License: **MIT**.
- What it does: a mature, self-hosted docs platform (shelves, books, chapters, pages) with search, revisions, roles, and public (guest) read access. It serves as the customer FAQ and help site, and Ops can use the same instance for SOPs.
- Interop:
  - Full REST API, documented at `/api/docs`, covering pages, books, search, and attachments. It also exposes an **audit-log API**.
  - **Outgoing webhooks** on any audit-log event (`page_create`, `page_update`...), sent as JSON and Slack-compatible. These map directly to the JSONL event log.
  - MCP comes through the community `pnocera/bookstack-mcp-server` (MIT, 98 stars, v2.1.0 on Aug 22, 2026), or by registering BookStack's REST API in ContextForge (#4).
- Caveats: no official MCP server, and the community one is small. Prefer the ContextForge route. It's a PHP/Laravel + MySQL stack. It has no built-in AI; drafting comes from the bot and RAGFlow. Pages can be saved as drafts or kept in a restricted book until `qa.check` passes, then moved to the public book.
- **Plugs into the bot:** a routine clusters repeat questions (from Chatwoot and RAGFlow) and drafts FAQ pages via the API. QA approves, then the page is published. BookStack webhooks log the event and trigger RAGFlow to re-ingest the page.

## Fit with the shared contract (all 5)
| Repo | MCP (streamable HTTP) | JSONL event logging | qa.check gate |
|---|---|---|---|
| Chatwoot | via ContextForge (REST to MCP) | webhooks, normalized by ContextForge or the bot | use private notes; public reply only after QA |
| Inbox Zero | native `/mcp` (streamable HTTP, OAuth) | webhook rule action, plus logging at the gateway | `create_draft` never sends; withhold `mcp:send` until QA |
| RAGFlow | native `/api/v1/mcp` (streamable HTTP) | log at the gateway | read-only, so no gate needed |
| ContextForge | is the MCP endpoint | `tool_post_invoke` plugin writes JSONL; JSON file logs built in | `tool_pre_invoke` plugin calls `qa.check` |
| BookStack | community MCP or via ContextForge | audit-log webhooks and API | draft or restricted book until QA, then publish |

Runners-up this round: tiny community Chatwoot MCP servers (fazer-ai/mcp-chatwoot, 12 stars; hugoblanc/chatwoot-mcp, 10; jjuanrivvera/wootctl, 1 star with 144 API operations, new). They're too small or new to depend on, but worth reading for tool design. stacklok/toolhive (Apache-2.0, 2,299 stars) is good for running MCP servers in containers, but it's less focused on REST-to-MCP and policy hooks. supercorp-ai/supergateway (MIT, 2,916 stars) only bridges transports. Zammad (AGPL) would fill a formal ticketing gap, and has a community MCP (basher83/Zammad-MCP, AGPL, 45 stars), but Chatwoot conversations already cover ticket workflows for a startup. Outline (BSL, not OSI open source) and Docmost (AGPL) were the docs alternatives to BookStack.
