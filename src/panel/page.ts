export function panelHtml(options: { mode: "live" | "mock"; dashboardUrl: string }): string {
  const live = options.mode === "live";
  const company = `${options.dashboardUrl.replace(/\/$/, "")}/dashboard`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dev2 counter — Sales, Support, Engineering</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #1c1612;
      --muted: #5c5148;
      --paper: #f4efe6;
      --card: #fffdf8;
      --line: #e4d8c8;
      --focus: #9a3412;
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
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 16px/1.45 "Iowan Old Style", Palatino, "Palatino Linotype", Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #fde7d4 0, transparent 28rem),
        var(--paper);
    }
    body, button, input, select { font-family: inherit; }
    main { max-width: 1100px; margin: 0 auto; padding: 1.25rem; }
    header { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: flex-end; justify-content: space-between; }
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
      background: ${live ? "#dcfce7" : "#ffedd5"};
    }
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
      background: white;
      color: var(--ink);
    }
    button, .linkish {
      margin-top: 0.55rem;
      min-height: 44px;
      padding: 0.45rem 0.75rem;
      border-radius: 12px;
      border: 2px solid var(--ink);
      background: white;
      color: var(--ink);
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { background: #fff7ed; }
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
    .badge { align-self: start; border-radius: 999px; padding: 0.15rem 0.5rem; font-size: 0.78rem; font-weight: 700; border: 1px solid transparent; }
    .queued, .running { background: #f5f5f4; color: #292524; }
    .needs_approval { background: var(--wait-bg); color: var(--wait); }
    .approved, .done { background: var(--ok-bg); color: var(--ok); }
    .rejected, .failed { background: var(--bad-bg); color: var(--bad); }
    .approval { border: 2px solid var(--line); border-radius: 12px; padding: 0.6rem; margin-top: 0.5rem; }
    .row { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .empty { color: var(--muted); padding: 0.8rem 0; }
    .note { font-size: 0.92rem; color: var(--muted); }
    @media (max-width: 860px) {
      .grid, .layout { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Dev2 counter</h1>
        <p class="lede">Sales, Support, and Engineering share this panel. The company-wide dashboard, with all 13 teams, stays on dev4. Approve and reject here still go to that shared queue.</p>
      </div>
      <p class="mode" id="mode" role="status">${live ? "LIVE" : "MOCK"}</p>
    </header>
    <p class="note">Company dashboard: <a id="company-link" href="${escapeAttr(company)}">${escapeText(company)}</a>. This page is meant to sit inside an iframe.</p>
    <section class="grid" aria-label="Departments">
      <article class="card sales">
        <h2>Sales</h2>
        <p>Builds a short list of fictional leads and drafts the first email. That first email always waits for a founder.</p>
        <label for="icp">Who are we looking for?</label>
        <input id="icp" value="independent coffee roasters in Austin">
        <div class="row">
          <button type="button" id="find" title="Search the mock lead list and file any product question with Support">Try it: find leads</button>
          <button type="button" id="draft" title="Draft one first email. It will wait here for approval.">Try it: draft outreach</button>
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
          <button type="button" id="triage" title="Sort the sample inbox by what each person needs">Try it: triage inbox</button>
          <button type="button" id="reply" title="Draft a reply. Refunds wait for approval.">Try it: draft reply</button>
        </div>
        <p class="hint">A shipping question can go out. A refund or a price change waits for you.</p>
      </article>
      <article class="card engineering">
        <h2>Engineering</h2>
        <p>Turns issue #42 into a short plan. If the issue needs another person, it raises a hiring signal for HR.</p>
        <p class="hint">Issue 42: checkout times out when the queue backs up.</p>
        <button type="button" id="plan" title="Write the plan and, when needed, ask HR to start a search">Try it: plan issue</button>
        <button type="button" id="launch" title="QA a landing page, publish a sales listing, and answer a buyer">Try it: launch Pulse Studio</button>
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
  </main>
  <script>
    const modeEl = document.getElementById("mode");
    const activity = document.getElementById("activity");
    const queue = document.getElementById("queue");
    const link = document.getElementById("company-link");
    const buttons = [...document.querySelectorAll("button")];

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
      modeEl.textContent = state.mode === "live" ? "LIVE" : "MOCK";
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
        queue.innerHTML = pending.map((item) =>
          '<div class="approval"><p><strong>' + item.dept + '</strong> — ' + item.summary + '</p><div class="row">' +
          '<button type="button" data-decision="approved" data-task="' + item.task_id + '">Approve</button>' +
          '<button type="button" data-decision="rejected" data-task="' + item.task_id + '">Reject</button></div></div>'
        ).join("");
      }
    }

    async function refresh() {
      const response = await fetch("/api/panel/state");
      if (!response.ok) return;
      render(await response.json());
    }

    async function run(url, body) {
      buttons.forEach((button) => { button.disabled = true; });
      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body || {}),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Request failed");
      } catch (error) {
        activity.insertAdjacentHTML("afterbegin", '<p class="empty">' + error.message + "</p>");
      } finally {
        buttons.forEach((button) => { button.disabled = false; });
        await refresh();
      }
    }

    document.getElementById("find").addEventListener("click", () => {
      run("/api/sales/find-leads", { icp: document.getElementById("icp").value, limit: 3 });
    });
    document.getElementById("draft").addEventListener("click", () => {
      const request = run("/api/sales/draft-outreach", { icp: document.getElementById("icp").value, limit: 1 });
      const timer = setInterval(refresh, 10000);
      request.finally(() => clearInterval(timer));
    });
    document.getElementById("triage").addEventListener("click", () => run("/api/support/triage", {}));
    document.getElementById("reply").addEventListener("click", () => {
      const id = document.getElementById("ticket").value;
      const request = run("/api/support/draft-reply", { message_id: id });
      if (id === "msg_refund") {
        const timer = setInterval(refresh, 10000);
        request.finally(() => clearInterval(timer));
      }
    });
    document.getElementById("plan").addEventListener("click", () => run("/api/engineering/plan-issue", {}));
    document.getElementById("launch").addEventListener("click", () => run("/api/chains/launch", {}));
    document.body.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-decision]");
      if (!button) return;
      run("/api/panel/decision", { task_id: button.dataset.task, decision: button.dataset.decision });
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
