# Engineering & Product: top 3 open-source repos
Research by Mochi (Grok Bot), Oct 19, 2026. All stars, dates and licenses come from the live GitHub API on Oct 19, 2026 (~6 PM CT). Times are US Central.

Selection criteria: real capability, 2025-2026 maintenance, permissive license, self-hostable, and above all **interoperability**. Each pick has to accept a task from an orchestrator and report status back through an API, MCP or GitHub. Each also has to work as a building block for our own AI assistant bot, which has its own computer, MCP connectors, routines and subagents.

---

## 1. OpenHands: autonomous issue-to-PR engineering agent (the "engineer")
- **URL:** https://github.com/OpenHands/OpenHands (formerly All-Hands-AI/OpenHands; the old URL redirects). The engine lives in https://github.com/OpenHands/software-agent-sdk.
- **What it does:** A self-hosted coding agent platform ("Agent Canvas"). Its prebuilt Issue-to-PR automation watches GitHub Issues, GitLab, Jira or Linear for issues that are ready to work on. It implements the change in a sandbox, runs the tests, opens a PR that links back to the issue, and posts progress on the issue. The older `fix-me` label and `@openhands-agent` GitHub Action resolver is also documented. It opens a draft PR when it succeeds and pushes a branch when it fails.
- **Verified:** 91,305 stars. Latest release v1.28.1 on Oct 19, 2026. Last commit Oct 19, 2026. The SDK is at v1.56.0 (Oct 19, 2026, 1,274 stars).
- **License:** MIT (OpenHands and software-agent-sdk). OpenHands Cloud/Enterprise are separate commercial offerings.
- **Interop:** The Agent Server has a REST API (POST /conversations and similar) plus a WebSocket event stream, protected by a session API key. Python SDK, TypeScript client, OpenAI-compatible Chat Completions and Responses endpoints. MCP client support, including OAuth MCP. ACP, so it can drive Claude Code, Codex, Gemini CLI or OpenCode as backends. An automation service handles schedules and webhooks. Slack, GitHub and Linear triggers.
- **Benchmark:** The SDK paper (arXiv 2511.03690) reports up to 72.8% on SWE-bench Verified with Claude Sonnet 4.5.
- **Caveats:** Agent Canvas is badged "beta". A2A is not supported (a draft PR #9248 went stale and was closed). Running without a sandbox gives the agent full filesystem access, so use the Docker runtime.
- **In our bot:** This is the bot's "engineering subagent with its own computer". The orchestrator POSTs a conversation to the Agent Server, streams events for status, and reads the PR link back. Each task runs in its own Docker sandbox.

## 2. OpenCode: headless coding agent with an HTTP API and a GitHub Action (the "CI/on-demand coder")
- **URL:** https://github.com/anomalyco/opencode (formerly sst/opencode; redirects)
- **What it does:** A terminal coding agent that works with any model provider. Mention `/opencode fix this` (or `/oc`) on a GitHub issue and it branches, implements and opens a PR. On a PR it commits requested changes. It can also auto-review PRs, triage new issues, and run on a cron schedule or `workflow_dispatch`, all inside GitHub Actions runners.
- **Verified:** 217,749 stars. Latest release v1.19.3 on Oct 16, 2026. Last commit Oct 19, 2026.
- **License:** MIT.
- **Interop:** `opencode serve` runs a headless HTTP server with an OpenAPI 3.1 spec at /doc and a generated SDK. It has session create, message, prompt_async and abort endpoints, `/session/status`, `/session/:id/diff`, and an SSE `/event` stream. MCP servers can be added at runtime (POST /mcp). Basic-auth password. GitHub App or plain GITHUB_TOKEN mode. Listed by OpenHands Agent Canvas as an ACP-compatible agent.
- **Caveats:** No published SWE-bench number found. The default GitHub App mode exchanges an OIDC token through api.opencode.ai; set `use_github_token: true` to avoid that third-party hop.
- **In our bot:** A lightweight, cheap coding worker. The bot calls `prompt_async` and then polls `/session/status` or listens on SSE. Routines map directly to its scheduled GitHub workflows.

## 3. GitHub MCP Server: the shared GitHub "bus" for every agent
- **URL:** https://github.com/github/github-mcp-server
- **What it does:** GitHub's official MCP server. Any MCP-capable agent gets tools to read code, create and update issues and PRs, triage, review, and watch GitHub Actions runs and build failures. The orchestrator uses it to file issues and track PR or CI status. Every other department's agents use it too.
- **Verified:** 33,770 stars. Latest release v2.0.2 on Oct 8, 2026. Last commit Oct 15, 2026.
- **License:** MIT.
- **Interop:** Native MCP. Run it hosted by GitHub (remote, OAuth) or self-host the public Docker image `ghcr.io/github/github-mcp-server` with a PAT. Configurable toolsets limit which capabilities each agent gets.
- **Caveats:** This is plumbing, not an agent; it does nothing without an LLM client. Write tools are powerful, so give each agent a least-privilege token and only the toolsets it needs. GitHub Enterprise Server can't use the remote server; self-host instead.
- **In our bot:** Register it as one of the bot's MCP connectors. It's also the bridge where the orchestrator writes tasks as GitHub issues and OpenHands or OpenCode pick them up.

---

## Runners-up and others considered (17 more checked)
- **PR-Agent** (https://github.com/The-PR-Agent/pr-agent, MIT, 13,458 stars, v0.48.0 Oct 16, 2026): the best dedicated AI PR reviewer (/describe, /review, /improve, /ask; GitHub/GitLab/Bitbucket/Azure/Gitea; Action, webhook, CLI, Docker). It lost only because of the top-3 cut. Qodo donated it, and it is now a "community-maintained legacy project" with no MCP server. OpenCode's PR-review mode covers the basics. **#4 if you want a dedicated review bot.**
- **Plane** (https://github.com/makeplane/plane, 61,143 stars, v1.4.3-rc1 Oct 6, 2026): the best open-source Linear/Jira alternative. It has a REST API, v2 signed webhooks, and an official MIT MCP server (makeplane/plane-mcp-server, stdio mode for self-hosted). It lost because of its **AGPL-3.0** license. Self-hosted Community Edition also can't use MCP OAuth, so you'd use a PAT. **#5 if you need a product tracker beyond GitHub Issues/Projects.**
- **OpenAI Codex CLI** (https://github.com/openai/codex, Apache-2.0, 129,934 stars, very active): strong `codex exec --json` and the openai/codex-action CI autofix. But `codex mcp-server` has been **removed**, and the replacement app-server is experimental and "not supported for production". It is effectively tied to OpenAI models. OpenHands can drive it through ACP anyway.
- Also checked: Gemini CLI (Apache-2.0, 107k stars; its A2A server is marked experimental; run-gemini-cli Action), goose (Apache-2.0, 55k stars; great general MCP agent but not GitHub-workflow-focused), SWE-agent (MIT, 20.6k stars; research-oriented, last release May 2025), mini-swe-agent (MIT, 8.7k stars; 65% SWE-bench Verified per README, a minimal benchmark harness), Aider (Apache-2.0, 49.6k stars; no commits since May 22, 2026, last release Aug 2025), Open SWE (MIT, 11k stars; deploying it as-is needs LangChain's private-beta Managed Deep Agents, and it doesn't accept contributions), claude-code-action (MIT action, but Claude Code itself isn't open source), Kodus (AGPL-3.0 reviewer), Cline (Apache-2.0, IDE-centric), Continue (Apache-2.0), Plandex (stale since Oct 2025), Sweep (stale since Sep 2025, no clear license), Roo Code (archived), Tabby (has an `ee/` directory under a separate license), Huly (EPL-2.0), OpenProject (GPL-3.0).

## How the 3 fit together and plug into the orchestrator / our bot
1. The orchestrator (or the founder) creates a GitHub issue through the **GitHub MCP Server**.
2. Big or complex tasks go to **OpenHands** through its Agent Server REST API, or are triggered by the Issue-to-PR automation. Status streams back over WebSocket, and the PR link is posted on the issue.
3. Small fixes, PR follow-ups, reviews and scheduled routines go to **OpenCode**: `/oc` in GitHub, or `opencode serve` `prompt_async` plus SSE.
4. The orchestrator and the QA department track PR, review and CI state through the GitHub MCP Server, then report to the founder.
5. All three are MIT, self-hostable and headless. The two agents are MCP clients, so they can also use the other departments' MCP servers (CRM, support inbox, docs). GitHub issues and PRs are the shared task-and-status record across departments.
Gap: none of these speaks A2A natively today. If the orchestrator uses A2A, wrap the OpenHands or OpenCode REST APIs in a thin A2A adapter.

## Not verified
- SWE-bench scores for OpenCode and for OpenHands' latest release.
- Whether OpenHands' Issue-to-PR automation needs Agent Canvas specifically, rather than only the SDK.
- Exact github-mcp-server toolset names. Toolset configuration exists, but I didn't list the toolsets.

---

# Addendum (Oct 19, 2026, ~6:25 PM CT): picks #4 and #5
These fill the two gaps left by #1-3: AI PR review, and a product/issue tracker with MCP. Numbers were re-verified from the GitHub API today.

## 4. PR-Agent: AI pull-request reviewer (the "code review" seat)
- **URL:** https://github.com/The-PR-Agent/pr-agent (formerly qodo-ai/pr-agent; redirects)
- **What it does:** Runs on each PR. `/describe` writes the PR title and summary, `/review` produces a reviewer guide with effort, test, security and focus-area notes, `/improve` gives code suggestions, and `/ask` answers questions. Each tool is a single LLM call (about 30 seconds per the README). It covers GitHub, GitLab, Bitbucket, Azure DevOps and Gitea.
- **Verified:** 13,458 stars. Latest release v0.48.0 on Oct 16, 2026. Last commit Oct 19, 2026, with 100+ commits since Sep 1, 2026. License MIT.
- **Interop:** GitHub Action, a self-hosted webhook server (GitHub App or GitLab webhook), Docker CLI (`docker run pragent/pr-agent --pr_url <url> review`), and PR comment commands. Works with any LLM provider (OpenAI key by default).
- **Caveats:** There is no MCP server, so it needs a small adapter. Qodo donated it, and it is now community-maintained by one external maintainer (@naorpeled), with a move to a foundation in progress. Overlaps a bit with OpenCode's PR-review mode, but PR-Agent is the purpose-built reviewer.
- **Contract fit:** Wrap the CLI as an MCP tool (`eng.review_pr(pr_url)`) behind streamable HTTP. `configuration.toml` has `publish_output=true` by default, so setting `publish_output=false` should stop it posting straight to the PR. The adapter can then capture the review, send it through `qa.check`, and post only what passes. I did not test exactly where the output goes in that mode. Log every run to the JSONL event log.
- **In our bot:** The bot's "second pair of eyes" subagent. Any PR that OpenHands or OpenCode opens is automatically reviewed before a human or QA sees it.

## 5. Plane + Plane MCP Server: product and issue tracker (the "Linear/Jira" seat)
- **URLs:** https://github.com/makeplane/plane (the app) and https://github.com/makeplane/plane-mcp-server (the official MCP server)
- **What it does:** A full product tracker: work items, cycles (sprints), modules, roadmaps, intake. It holds the product backlog that is bigger than GitHub Issues. The engineering department turns its items into GitHub issues and PRs.
- **Verified:** Plane has 61,143 stars, latest release v1.4.3-rc1 on Oct 6, 2026, last commit Oct 19, 2026, license **AGPL-3.0**. plane-mcp-server has 343 stars, v0.3.4 on Oct 8, 2026, license **MIT**.
- **Interop:**
  - REST API with `x-api-key`.
  - Workspace-level v2 webhooks: signed, with dedup ids (`delivery_id`/`event_id`), `previous_attributes` diffs, filters, and retries.
  - The MCP server exposes 30 tools covering 207 operations.
  - MCP transports: stdio, **streamable HTTP**, and SSE (deprecated).
  - MCP auth is either OAuth or PAT headers (`Authorization: Bearer`, `X-Workspace-slug`).
  - The MCP server can be self-hosted with `python -m plane_mcp http` (port 8211), Docker Compose or Helm.
  - Structured JSON logs record each tool call.
- **Caveats:**
  - **AGPL-3.0** for the Plane app. Running it unmodified for internal use is fine. If you modify it and expose it to outside users over a network, you must publish your changes. Get a lawyer to confirm.
  - On self-hosted Community Edition, the MCP **OAuth** transport is unavailable (Plane docs say it needs Cloud or Commercial Edition). Docs point CE users to stdio with a PAT. To meet the streamable-HTTP contract on CE, either use the server's PAT HTTP route self-hosted, or bridge stdio to HTTP. The PAT HTTP route is documented for the hosted endpoint; I did not verify that it works on a self-hosted CE install.
  - Release v1.4.3 is still an rc.
- **Contract fit:** Native MCP over streamable HTTP. Its webhooks can feed the shared event log and the orchestrator's triggers. Its JSON tool-call logs map easily onto JSONL. Plane docs say to treat issue text as untrusted model input, which matches the qa.check gate.
- **In our bot:** The bot's "task board" connector. The orchestrator creates and updates work items over MCP, and Plane webhooks wake the bot when an item moves to "Ready".

## Runner-up for #5
- **Gitea + gitea-mcp** is the MIT-licensed tracker alternative if AGPL is a dealbreaker. `go-gitea/gitea` has 58,573 stars, last pushed Oct 19, 2026, MIT. It is a weaker product tracker than Plane, though. The gitea-mcp server is not on GitHub (it is hosted on gitea.com, not checked), so I couldn't verify it with the GitHub API.

## Fit of all 5 with the shared contract (MCP streamable HTTP + JSONL event log + qa.check)
| # | Repo | Speaks MCP server natively? | Adapter needed | Event source for JSONL log | qa.check hook point |
|---|------|-----------------------------|----------------|----------------------------|---------------------|
| 1 | OpenHands | No (REST + WebSocket Agent Server; it is an MCP *client*) | Thin MCP wrapper: `eng.start_task`, `eng.task_status` → Agent Server REST | Agent Server event stream | Gate the PR or draft PR before it's marked ready / merged |
| 2 | OpenCode | No (OpenAPI HTTP server; MCP *client*) | Thin MCP wrapper: `prompt_async`, `/session/status`, `/session/:id/diff` | SSE `/event` stream | Gate `/session/:id/diff` before push/PR |
| 3 | GitHub MCP Server | **Yes** (remote, streamable HTTP; or self-hosted Docker) | None | Adapter logs each tool call | Gate risky write tools (merge, close, comment) |
| 4 | PR-Agent | No (CLI / Action / webhook) | MCP wrapper around the CLI with `publish_output=false` | Wrapper logs each run | Review text goes through qa.check before it's posted |
| 5 | Plane | **Yes** (plane-mcp-server, streamable HTTP; CE caveat above) | None (or stdio→HTTP bridge on CE) | Plane webhooks v2 + JSON tool logs | Gate status changes / bulk edits |
Not verified: SWE-bench for PR-Agent (not applicable; it is a reviewer), and whether Plane's self-hosted PAT-HTTP route works on CE.
