export function panelHtml(options: { mode: "live" | "mock"; dashboardUrl: string }): string {
  const live = options.mode === "live";
  const company = `${options.dashboardUrl.replace(/\/$/, "")}/dashboard`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dev2 counter — Sales, Support, Engineering</title>
  <script>
    (function () {
      try {
        var storedTheme = localStorage.getItem("dev2-panel-theme");
        if (storedTheme === "default" || storedTheme === "contrast" || storedTheme === "dark") {
          document.documentElement.setAttribute("data-theme", storedTheme);
        }
      } catch (error) {}
    })();
  </script>
  <style>
    :root {
      color-scheme: light;
      --ink: #1c1612;
      --muted: #5c5148;
      --paper: #f4efe6;
      --card: #fffdf8;
      --line: #e4d8c8;
      --focus: #9a3412;
      --glow: #fde7d4;
      --sales: #9a3412;
      --sales-bg: #fff4ec;
      --support: #115e59;
      --support-bg: #f0fdfa;
      --eng: #312e81;
      --eng-bg: #eef2ff;
      --ok: #166534;
      --ok-bg: #ecfdf3;
      --wait: #9a3412;
      --wait-bg: #ffedd5;
      --bad: #991b1b;
      --bad-bg: #fef2f2;
      --neutral-bg: #f5f5f4;
      --neutral-ink: #292524;
      --field-bg: #ffffff;
      --button-bg: #ffffff;
      --button-hover: #fff7ed;
      --live-bg: #dcfce7;
      --live-ink: #14532d;
      --mock-bg: #ffedd5;
      --mock-ink: #9a3412;
      --badge-border: transparent;
    }
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme]) {
        color-scheme: dark;
        --ink: #f7f3ee;
        --muted: #d7cdc3;
        --paper: #141110;
        --card: #1f1a17;
        --line: #c4b5a8;
        --focus: #ffb86b;
        --glow: #3a2418;
        --sales: #ffb86b;
        --sales-bg: #3a2418;
        --support: #7eefe0;
        --support-bg: #0e2e2b;
        --eng: #d6dcff;
        --eng-bg: #1e1b4b;
        --ok: #86efac;
        --ok-bg: #052e16;
        --wait: #fdba74;
        --wait-bg: #431407;
        --bad: #fecaca;
        --bad-bg: #450a0a;
        --neutral-bg: #3a342e;
        --neutral-ink: #f7f3ee;
        --field-bg: #2a2420;
        --button-bg: #2a2420;
        --button-hover: #3a322c;
        --live-bg: #064e3b;
        --live-ink: #d1fae5;
        --mock-bg: #7c2d12;
        --mock-ink: #ffedd5;
      }
    }
    @media (prefers-contrast: more) {
      :root:not([data-theme]) {
        color-scheme: light;
        --ink: #000000;
        --muted: #1b1b1b;
        --paper: #ffffff;
        --card: #ffffff;
        --line: #000000;
        --focus: #000000;
        --glow: transparent;
        --sales: #6b1600;
        --sales-bg: #ffffff;
        --support: #003833;
        --support-bg: #ffffff;
        --eng: #1a1464;
        --eng-bg: #ffffff;
        --ok: #064e1a;
        --ok-bg: #ffffff;
        --wait: #6b1600;
        --wait-bg: #ffffff;
        --bad: #7f1d1d;
        --bad-bg: #ffffff;
        --neutral-bg: #ffffff;
        --neutral-ink: #000000;
        --field-bg: #ffffff;
        --button-bg: #ffffff;
        --button-hover: #ffff00;
        --live-bg: #ffffff;
        --live-ink: #064e1a;
        --mock-bg: #ffffff;
        --mock-ink: #6b1600;
        --badge-border: #000000;
      }
    }
    :root[data-theme="dark"] {
      color-scheme: dark;
      --ink: #f7f3ee;
      --muted: #d7cdc3;
      --paper: #141110;
      --card: #1f1a17;
      --line: #c4b5a8;
      --focus: #ffb86b;
      --glow: #3a2418;
      --sales: #ffb86b;
      --sales-bg: #3a2418;
      --support: #7eefe0;
      --support-bg: #0e2e2b;
      --eng: #d6dcff;
      --eng-bg: #1e1b4b;
      --ok: #86efac;
      --ok-bg: #052e16;
      --wait: #fdba74;
      --wait-bg: #431407;
      --bad: #fecaca;
      --bad-bg: #450a0a;
      --neutral-bg: #3a342e;
      --neutral-ink: #f7f3ee;
      --field-bg: #2a2420;
      --button-bg: #2a2420;
      --button-hover: #3a322c;
      --live-bg: #064e3b;
      --live-ink: #d1fae5;
      --mock-bg: #7c2d12;
      --mock-ink: #ffedd5;
      --badge-border: transparent;
    }
    :root[data-theme="contrast"] {
      color-scheme: light;
      --ink: #000000;
      --muted: #1b1b1b;
      --paper: #ffffff;
      --card: #ffffff;
      --line: #000000;
      --focus: #000000;
      --glow: transparent;
      --sales: #6b1600;
      --sales-bg: #ffffff;
      --support: #003833;
      --support-bg: #ffffff;
      --eng: #1a1464;
      --eng-bg: #ffffff;
      --ok: #064e1a;
      --ok-bg: #ffffff;
      --wait: #6b1600;
      --wait-bg: #ffffff;
      --bad: #7f1d1d;
      --bad-bg: #ffffff;
      --neutral-bg: #ffffff;
      --neutral-ink: #000000;
      --field-bg: #ffffff;
      --button-bg: #ffffff;
      --button-hover: #ffff00;
      --live-bg: #ffffff;
      --live-ink: #064e1a;
      --mock-bg: #ffffff;
      --mock-ink: #6b1600;
      --badge-border: #000000;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 16px/1.45 "Iowan Old Style", Palatino, "Palatino Linotype", Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, var(--glow) 0, transparent 28rem),
        var(--paper);
    }
    body, button, input, select { font-family: inherit; }
    main { max-width: 1100px; margin: 0 auto; padding: 1.25rem; }
    main:focus { outline: none; }
    main:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
    header { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: flex-end; justify-content: space-between; }
    .header-tools { display: flex; flex-wrap: wrap; gap: 0.6rem 0.8rem; align-items: center; }
    h1 { font-size: 1.8rem; line-height: 1.1; margin: 0 0 0.25rem; }
    h2 { font-size: 1.15rem; margin: 0; }
    p { margin: 0.35rem 0; }
    a { color: var(--focus); }
    .lede { max-width: 42rem; color: var(--muted); }
    .mode {
      border: 2px solid var(--ink);
      border-radius: 999px;
      padding: 0.35rem 0.8rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      margin: 0;
    }
    .mode.live { background: var(--live-bg); color: var(--live-ink); }
    .mode.mock { background: var(--mock-bg); color: var(--mock-ink); }
    .theme-switch { display: flex; flex-wrap: wrap; gap: 0.35rem; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.9rem; margin: 1rem 0; }
    .card { background: var(--card); border: 2px solid var(--line); border-radius: 18px; padding: 0.9rem 1rem 1rem; }
    .card.sales { border-top: 8px solid var(--sales); background: var(--sales-bg); }
    .card.support { border-top: 8px solid var(--support); background: var(--support-bg); }
    .card.engineering { border-top: 8px solid var(--eng); background: var(--eng-bg); }
    label { display: block; font-size: 0.92rem; font-weight: 700; margin-top: 0.55rem; }
    input, select {
      width: 100%;
      margin-top: 0.2rem;
      padding: 0.55rem 0.6rem;
      border-radius: 10px;
      border: 2px solid var(--line);
      background: var(--field-bg);
      color: var(--ink);
    }
    button, .linkish {
      margin-top: 0.55rem;
      min-height: 44px;
      padding: 0.45rem 0.75rem;
      border-radius: 12px;
      border: 2px solid var(--ink);
      background: var(--button-bg);
      color: var(--ink);
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { background: var(--button-hover); }
    .theme-switch button { margin-top: 0; }
    .theme-switch button[aria-pressed="true"],
    .theme-switch button[aria-pressed="true"]:hover {
      background: var(--ink);
      color: var(--paper);
    }
    button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible {
      outline: 3px solid var(--focus);
      outline-offset: 2px;
    }
    button[disabled] { opacity: 0.6; cursor: wait; }
    .hint { color: var(--muted); font-size: 0.92rem; }
    .layout { display: grid; grid-template-columns: 1.4fr 0.8fr; gap: 0.9rem; }
    .panel { background: var(--card); border: 2px solid var(--line); border-radius: 18px; padding: 0.9rem 1rem; }
    ol { list-style: none; margin: 0; padding: 0; }
    li { display: grid; grid-template-columns: auto 1fr; gap: 0.55rem; padding: 0.55rem 0; border-bottom: 1px solid var(--line); }
    .badge { align-self: start; border-radius: 999px; padding: 0.15rem 0.5rem; font-size: 0.78rem; font-weight: 700; border: 1px solid var(--badge-border); }
    .queued, .running { background: var(--neutral-bg); color: var(--neutral-ink); }
    .needs_approval { background: var(--wait-bg); color: var(--wait); }
    .approved, .done { background: var(--ok-bg); color: var(--ok); }
    .rejected, .failed { background: var(--bad-bg); color: var(--bad); }
    .approval { border: 2px solid var(--line); border-radius: 12px; padding: 0.6rem; margin-top: 0.5rem; background: var(--card); color: var(--ink); }
    .row { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .empty { color: var(--muted); padding: 0.8rem 0; }
    .note { font-size: 0.92rem; color: var(--muted); }
    button, a, .card, .mode, input, select {
      transition: background-color 160ms ease, color 160ms ease, border-color 160ms ease;
    }
    .skip-link {
      position: absolute;
      left: 0.75rem;
      top: 0.75rem;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      clip-path: inset(50%);
      white-space: nowrap;
      border: 0;
    }
    .skip-link:focus {
      width: auto;
      height: auto;
      margin: 0;
      padding: 0.55rem 0.85rem;
      overflow: visible;
      clip: auto;
      clip-path: none;
      white-space: normal;
      z-index: 30;
      background: var(--button-bg);
      color: var(--ink);
      border: 2px solid var(--ink);
      border-radius: 12px;
      font-weight: 700;
      text-decoration: none;
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      clip-path: inset(50%);
      white-space: nowrap;
      border: 0;
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation: none !important;
        transition: none !important;
        scroll-behavior: auto !important;
      }
    }
    @media (max-width: 860px) {
      .grid, .layout { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <main id="main" tabindex="-1">
    <header>
      <div>
        <h1>Dev2 counter</h1>
        <p class="lede">Sales, Support, and Engineering share this panel. The company-wide dashboard, with all 13 teams, stays on dev4. Approve and reject here still go to that shared queue.</p>
      </div>
      <div class="header-tools">
        <div class="theme-switch" role="group" aria-label="Color theme">
          <button type="button" data-theme-choice="default" aria-pressed="true">Default</button>
          <button type="button" data-theme-choice="contrast" aria-pressed="false">High contrast</button>
          <button type="button" data-theme-choice="dark" aria-pressed="false">Dark</button>
        </div>
        <p class="mode ${live ? "live" : "mock"}" id="mode" role="status">${live ? "LIVE" : "MOCK"}</p>
      </div>
    </header>
    <p class="note">Company dashboard: <a id="company-link" href="${escapeAttr(company)}">${escapeText(company)}</a>. This page is meant to sit inside an iframe.</p>
    <section class="grid" aria-label="Departments">
      <article class="card sales">
        <h2>Sales</h2>
        <p>Builds a short list of fictional leads and drafts the first email. That first email always waits for a founder.</p>
        <label for="icp">Who are we looking for?</label>
        <input id="icp" value="independent coffee roasters in Austin">
        <div class="row">
          <button type="button" id="find" aria-describedby="find-hint">Try it: find leads</button>
          <span id="find-hint" class="sr-only">Search the mock lead list and file any product question with Support</span>
          <button type="button" id="draft" aria-describedby="draft-hint">Try it: draft outreach</button>
          <span id="draft-hint" class="sr-only">Draft one first email. It will wait here for approval.</span>
        </div>
        <p class="hint">Find leads is instant. Draft outreach stays open until you approve or reject the email.</p>
      </article>
      <article class="card support">
        <h2>Support</h2>
        <p>Reads the sample inbox, answers from the FAQ, and sends a bug on to Engineering.</p>
        <label for="ticket">Which ticket?</label>
        <select id="ticket">
          <option value="msg_ship">Avery asks where the order is</option>
          <option value="msg_refund">Sam wants a refund</option>
          <option value="msg_bug">Riley reports a timeout bug</option>
          <option value="msg_design">Jules asks for a setup diagram</option>
        </select>
        <div class="row">
          <button type="button" id="triage" aria-describedby="triage-hint">Try it: triage inbox</button>
          <span id="triage-hint" class="sr-only">Sort the sample inbox by what each person needs</span>
          <button type="button" id="reply" aria-describedby="reply-hint">Try it: draft reply</button>
          <span id="reply-hint" class="sr-only">Draft a reply. Refunds wait for approval.</span>
        </div>
        <p class="hint">A shipping question can go out. A refund or a price change waits for you.</p>
      </article>
      <article class="card engineering">
        <h2>Engineering</h2>
        <p>Turns issue #42 into a short plan. If the issue needs another person, it raises a hiring signal for HR.</p>
        <p class="hint">Issue 42: checkout times out when the queue backs up.</p>
        <button type="button" id="plan" aria-describedby="plan-hint">Try it: plan issue</button>
        <span id="plan-hint" class="sr-only">Write the plan and, when needed, ask HR to start a search</span>
        <button type="button" id="launch" aria-describedby="launch-hint">Try it: launch Pulse Studio</button>
        <span id="launch-hint" class="sr-only">QA a landing page, publish a sales listing, and answer a buyer</span>
      </article>
    </section>
    <div class="layout">
      <section class="panel" aria-labelledby="activity-title">
        <h2 id="activity-title">What just happened</h2>
        <div id="activity" aria-live="polite"><p class="empty">Nothing yet. Pick a Try it button above.</p></div>
      </section>
      <section class="panel" aria-labelledby="queue-title">
        <h2 id="queue-title">Needs a founder</h2>
        <p class="hint">These buttons call the shared company queue. They do not send mail on their own.</p>
        <div id="queue"><p class="empty">Nothing is waiting.</p></div>
      </section>
    </div>
    <div id="request-status" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></div>
  </main>
  <script>
    const modeEl = document.getElementById("mode");
    const activity = document.getElementById("activity");
    const queue = document.getElementById("queue");
    const link = document.getElementById("company-link");
    const requestStatus = document.getElementById("request-status");
    const themeButtons = Array.prototype.slice.call(document.querySelectorAll("[data-theme-choice]"));

    function resolvedTheme() {
      const chosen = document.documentElement.getAttribute("data-theme");
      if (chosen === "default" || chosen === "contrast" || chosen === "dark") return chosen;
      if (window.matchMedia("(prefers-contrast: more)").matches) return "contrast";
      if (window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
      return "default";
    }

    function markTheme(theme) {
      themeButtons.forEach((button) => {
        button.setAttribute("aria-pressed", button.getAttribute("data-theme-choice") === theme ? "true" : "false");
      });
    }

    function onSystemTheme() {
      if (document.documentElement.hasAttribute("data-theme")) return;
      markTheme(resolvedTheme());
    }

    markTheme(resolvedTheme());
    themeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const theme = button.getAttribute("data-theme-choice");
        document.documentElement.setAttribute("data-theme", theme);
        try { localStorage.setItem("dev2-panel-theme", theme); } catch (error) {}
        markTheme(theme);
      });
    });
    ["(prefers-color-scheme: dark)", "(prefers-contrast: more)"].forEach((query) => {
      const list = window.matchMedia(query);
      if (typeof list.addEventListener === "function") list.addEventListener("change", onSystemTheme);
    });

    function actionButtons() {
      return Array.prototype.slice.call(document.querySelectorAll("button:not([data-theme-choice])"));
    }

    function announce(message) {
      requestStatus.textContent = message;
    }

    function esc(value) {
      return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[char]);
    }

    function badge(status) {
      const label = ({
        queued: "Queued",
        running: "Working",
        needs_approval: "Needs you",
        approved: "Approved",
        rejected: "Rejected",
        done: "Done",
        failed: "Failed",
      })[status] || status;
      return '<span class="badge ' + status + '">' + label + '</span>';
    }

    function plain(event) {
      const decision = event.output && event.output.decision;
      if (event.actor === "qa" && decision === "pass") return "QA check passed";
      if (event.actor === "qa" && decision === "fail") return "QA asked for one revision";
      if (event.actor === "qa" && decision === "founder") return "QA sent this to the founder queue";
      if (event.actor === "founder" && event.status === "approved") return "Founder approved it";
      if (event.actor === "founder" && event.status === "rejected") return "Founder rejected it. Nothing was sent.";
      if (event.actor === "ops") return event.summary;
      if (event.status === "needs_approval") return "Needs your approval before anything goes out";
      if (event.output && event.output.kind === "hire_needed") return "Asked HR to start a hiring search";
      if (event.output && event.output.kind === "design_request" && event.output.handed_off) return "Handed a design request to Design";
      if (event.output && event.output.sent === true) return "Sent: " + event.summary;
      if (event.output && event.output.sent === false && event.status === "done") return "Closed without sending";
      return event.summary;
    }

    function render(state) {
      const liveMode = state.mode === "live";
      modeEl.textContent = liveMode ? "LIVE" : "MOCK";
      modeEl.classList.toggle("live", liveMode);
      modeEl.classList.toggle("mock", !liveMode);
      if (state.company_dashboard) {
        link.href = state.company_dashboard;
        link.textContent = state.company_dashboard;
      }
      const events = state.events || [];
      if (!events.length) {
        activity.innerHTML = '<p class="empty">Nothing yet. Pick a Try it button above.</p>';
      } else {
        activity.innerHTML = "<ol>" + events.slice(-12).reverse().map((event) =>
          "<li>" + badge(event.status) + "<div><strong>" + event.dept + "</strong> — " + plain(event) + "</div></li>"
        ).join("") + "</ol>";
      }
      const pending = state.approvals || [];
      if (!pending.length) {
        queue.innerHTML = '<p class="empty">Nothing is waiting.</p>';
      } else {
        queue.innerHTML = pending.map((item) => {
          const title = item.summary || item.dept || "item";
          return '<div class="approval"><p><strong>' + esc(item.dept) + '</strong> — ' + esc(item.summary) + '</p><div class="row">' +
            '<button type="button" data-decision="approved" data-task="' + esc(item.task_id) + '" aria-label="Approve ' + esc(title) + '">Approve</button>' +
            '<button type="button" data-decision="rejected" data-task="' + esc(item.task_id) + '" aria-label="Reject ' + esc(title) + '">Reject</button></div></div>';
        }).join("");
      }
    }

    async function refresh() {
      const response = await fetch("/api/panel/state");
      if (!response.ok) return;
      render(await response.json());
    }

    async function run(url, body, source) {
      const button = source && source.tagName === "BUTTON" ? source : null;
      const card = button ? button.closest(".card, .approval") : null;
      const originalLabel = button ? button.textContent : "";
      actionButtons().forEach((item) => { item.disabled = true; });
      if (button) {
        button.setAttribute("aria-busy", "true");
        button.textContent = "Working…";
      }
      if (card) card.setAttribute("aria-busy", "true");
      announce(originalLabel ? "Started: " + originalLabel : "Started");
      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body || {}),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Request failed");
        announce(originalLabel ? "Finished: " + originalLabel : "Finished");
      } catch (error) {
        announce("Error: " + error.message);
        activity.insertAdjacentHTML("afterbegin", '<p class="empty">' + error.message + "</p>");
      } finally {
        if (button) {
          button.textContent = originalLabel;
          button.removeAttribute("aria-busy");
        }
        if (card) card.removeAttribute("aria-busy");
        actionButtons().forEach((item) => { item.disabled = false; });
        await refresh();
      }
    }

    document.getElementById("find").addEventListener("click", (event) => {
      run("/api/sales/find-leads", { icp: document.getElementById("icp").value, limit: 3 }, event.currentTarget);
    });
    document.getElementById("draft").addEventListener("click", (event) => {
      const request = run("/api/sales/draft-outreach", { icp: document.getElementById("icp").value, limit: 1 }, event.currentTarget);
      const timer = setInterval(refresh, 10000);
      request.finally(() => clearInterval(timer));
    });
    document.getElementById("triage").addEventListener("click", (event) => run("/api/support/triage", {}, event.currentTarget));
    document.getElementById("reply").addEventListener("click", (event) => {
      const id = document.getElementById("ticket").value;
      const request = run("/api/support/draft-reply", { message_id: id }, event.currentTarget);
      if (id === "msg_refund") {
        const timer = setInterval(refresh, 10000);
        request.finally(() => clearInterval(timer));
      }
    });
    document.getElementById("plan").addEventListener("click", (event) => run("/api/engineering/plan-issue", {}, event.currentTarget));
    document.getElementById("launch").addEventListener("click", (event) => run("/api/chains/launch", {}, event.currentTarget));
    document.body.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-decision]");
      if (!button) return;
      run("/api/panel/decision", { task_id: button.dataset.task, decision: button.dataset.decision }, button);
    });
    refresh();
  </script>
</body>
</html>`;
}

function escapeText(value: string): string {
  return value.replace(/[&<>]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[char] ?? char);
}

function escapeAttr(value: string): string {
  return escapeText(value).replace(/"/g, "&quot;");
}
