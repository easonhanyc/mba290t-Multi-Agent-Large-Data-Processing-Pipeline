// Spotify Review Insights dashboard: renders data fetched from the read-only API (/api/*).
// Every number shown comes from the backend, which reads the database; nothing here calls a model.
"use strict";

const API = "/api";
const charts = {};
const loaded = {};
const fmt = new Intl.NumberFormat("en-US");
const COLORS = ["#1db954", "#2e90fa", "#f79009", "#9e77ed", "#f04438", "#667085", "#12b76a", "#ee46bc"];
const AREA_COLORS = {"access/onboarding": "#2e90fa", "usability": "#9e77ed", "playback/performance": "#f04438",
                     "billing/support": "#f79009", "catalog/content": "#12b76a", "general/unspecified": "#98a2b3"};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const n = (v) => (v === null || v === undefined ? "–" : fmt.format(v));
const pct = (v, d = 1) => (v === null || v === undefined ? "–" : `${(Number(v) * 100).toFixed(d)}%`);

async function get(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

function chart(id, config) {
  if (charts[id]) charts[id].destroy();
  const css = getComputedStyle(document.documentElement);
  Chart.defaults.color = css.getPropertyValue("--muted").trim() || "#5b6573";
  Chart.defaults.borderColor = css.getPropertyValue("--line").trim() || "#e3e6eb";
  Chart.defaults.maintainAspectRatio = false;  // every canvas sits in a fixed-height .chart box
  charts[id] = new Chart($(id), config);
}

// ---- tiny markdown renderer (headings, tables, lists, bold, code, quotes) -------------------------------
function md(text) {
  const lines = String(text || "").split("\n");
  let html = "", i = 0;
  const inline = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  while (i < lines.length) {
    const l = lines[i];
    if (/^\|/.test(l)) {
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]);
      const cells = (r) => r.replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
      html += "<div class='table-wrap'><table><tr>" + cells(rows[0]).map((c) => `<th>${inline(c)}</th>`).join("") + "</tr>";
      rows.slice(2).forEach((r) => (html += "<tr>" + cells(r).map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>"));
      html += "</table></div>";
      continue;
    }
    if (/^#{1,4} /.test(l)) { const k = l.match(/^#+/)[0].length; html += `<h${k + 1}>${inline(l.replace(/^#+ /, ""))}</h${k + 1}>`; i++; continue; }
    if (/^- /.test(l)) { html += "<ul>"; while (i < lines.length && /^- /.test(lines[i])) html += `<li>${inline(lines[i++].slice(2))}</li>`; html += "</ul>"; continue; }
    if (/^> /.test(l)) { html += `<blockquote>${inline(l.slice(2))}</blockquote>`; i++; continue; }
    if (l.trim()) html += `<p>${inline(l)}</p>`;
    i++;
  }
  return html;
}

// ---- tabs ----------------------------------------------------------------------------------------------
const loaders = {overview: loadOverview, recommendation: loadRecommendation, issues: loadIssues, trends: loadTrends,
                 evaluation: loadEvaluation, run: loadRun, lookup: () => {}};
function show(tab) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${tab}`));
  if (!loaded[tab]) { loaded[tab] = true; loaders[tab]().catch((e) => fail(tab, e)); }
  try { history.replaceState(null, "", `#${tab}`); } catch (e) { /* ignore */ }
}
function fail(tab, e) {
  const sec = $(`tab-${tab}`);
  const div = document.createElement("div");
  div.className = "card bad";
  div.textContent = `Could not load: ${e.message}`;
  sec.prepend(div);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));

// ---- overview ------------------------------------------------------------------------------------------
async function loadOverview() {
  const o = await get("/overview");
  const c = o.counts, run = o.run;
  if (run.offline_stub) $("stub-banner").classList.remove("hidden");
  const acct = run.scope || {};
  $("scope").textContent = `Run ${run.run_key} · ${n(run.analysis_rows)} reviews in the declared scope` +
    (acct.full_rows ? ` (uniform sample of ${n(acct.full_rows)} ingested)` : "") + ` · ${run.label_config.split("|")[0]}`;
  const v = o.verification?.agreement, g = o.golden?.agreement;
  const kpis = [
    ["Reviews in scope", n(c.rows), acct.full_rows ? `of ${n(acct.full_rows)} ingested and profiled` : ""],
    ["Classified", n(c.completed), `${pct(c.completed / c.rows)} of scope`],
    ["Quarantined", n(c.quarantined), (o.quarantine_reasons || []).map((q) => `${n(q.n)} ${q.reason}`).join("; ").slice(0, 70)],
    ["Complaints + cancellations", n(c.complaints), `${pct(c.complaints / c.completed)} of classified; ${n(c.cancellations)} cancellation intent`],
    ["Exact-text cache reuses", n(c.exact_text_cache_reuses), "one model result per distinct text"],
    ["Flagged needs_review", n(c.needs_review), `${pct(c.needs_review / c.completed)} of classified`],
    ["Verifier agreement (topic / intent / severity)", v ? `${pct(v.topic.rate, 0)} / ${pct(v.intent.rate, 0)} / ${pct(v.severity.rate, 0)}` : "–", o.verification ? `${n(o.verification.compared)} sampled reviews` : "pending"],
    ["Golden agreement (topic / intent / severity)", g ? `${pct(g.topic, 0)} / ${pct(g.intent, 0)} / ${pct(g.severity, 0)}` : "–", o.golden ? `${o.golden.cases ?? ""} human-labelled reviews` : "pending"],
    ["Billed API spend (all runs)", o.cost?.billed_api_spend_recorded_usd != null ? `$${o.cost.billed_api_spend_recorded_usd.toFixed(2)}` : "–", "from saved call logs × dated rates"],
  ];
  $("kpis").innerHTML = kpis.map(([l, val, s]) => `<div class="kpi"><div class="l">${esc(l)}</div><div class="v">${esc(val)}</div><div class="s">${esc(s)}</div></div>`).join("");
  const areas = o.areas;
  chart("chart-areas", {type: "bar", data: {labels: areas.map((a) => a.area + (a.decision_option ? "" : " *")),
    datasets: [{label: "Severity sum", data: areas.map((a) => a.severity_sum), backgroundColor: areas.map((a) => AREA_COLORS[a.area] || "#98a2b3")},
               {label: "Complaints", data: areas.map((a) => a.complaint_count), backgroundColor: "rgba(102,112,133,.35)"}]},
    options: {indexAxis: "y", plugins: {legend: {position: "bottom"}, tooltip: {callbacks: {afterBody: (it) => {
      const a = areas[it[0].dataIndex]; return `share of complaints ${pct(a.share_of_complaints)}; ${n(a.cancellation_count)} cancellation intent`; }}}}}});
  chart("chart-intents", {type: "doughnut", data: {labels: o.intents.map((x) => x.intent), datasets: [{data: o.intents.map((x) => x.n), backgroundColor: COLORS}]},
    options: {plugins: {legend: {position: "right"}}}});
  chart("chart-topics", {type: "bar", data: {labels: o.topics.map((t) => t.topic), datasets: [{label: "Complaints + cancellations", data: o.topics.map((t) => t.complaints), backgroundColor: "#2e90fa"}, {label: "All classified", data: o.topics.map((t) => t.n), backgroundColor: "rgba(102,112,133,.3)"}]},
    options: {plugins: {legend: {position: "bottom"}}}});
  chart("chart-severity", {type: "bar", data: {labels: o.complaint_severity.map((s) => `severity ${s.severity}`), datasets: [{label: "Complaint reviews", data: o.complaint_severity.map((s) => s.n), backgroundColor: ["#98a2b3", "#fdb022", "#f79009", "#f04438", "#912018"]}]},
    options: {plugins: {legend: {display: false}}}});
  const tiers = (o.labeled_by || []).map((t) => `${esc(t.labeled_by)} ${n(t.n)}`).join(" · ");
  $("accounting").innerHTML = `<table>
    <tr><th>Full source file</th><td class="mono">${esc(run.full_source || "–")} ${run.full_sha256 ? "sha256 " + esc(run.full_sha256.slice(0, 16)) + "…" : ""}</td></tr>
    <tr><th>Declared analysis input</th><td class="mono">${esc(run.analysis_input)} sha256 ${esc(run.analysis_sha256.slice(0, 16))}…</td></tr>
    <tr><th>Rows: ingested / in scope / out of scope</th><td>${n(acct.full_rows)} / ${n(acct.analysis_rows_matched_in_full_file ?? run.analysis_rows)} / ${n(acct.out_of_scope_rows)} (out of scope: profiled, not classified)</td></tr>
    <tr><th>Completed / quarantined / unfinished</th><td>${n(c.completed)} / ${n(c.quarantined)} / ${n(c.rows - c.completed - c.quarantined)}</td></tr>
    <tr><th>Who labelled</th><td>${tiers} <span class="muted small">(cache = exact-text reuse of an original's result)</span></td></tr>
    <tr><th>label_config</th><td class="mono small">${esc(run.label_config)}</td></tr></table>`;
}

// ---- recommendation ------------------------------------------------------------------------------------
function fillTokens(text, tokens) {
  return esc(text).replace(/\{([CAST]\d{2,3})\}/g, (m, t) => `<strong title="${t}">${esc(tokens[t] ?? m)}</strong><sup class="chip">${t}</sup>`);
}
async function loadRecommendation() {
  const [r, cons] = await Promise.all([get("/recommendation"), get("/consistency")]);
  const out = r.output, tk = r.tokens;
  $("rec-area").textContent = r.recommended_area;
  $("rec-source").textContent = `memo ${r.source} · ${r.memo_config || ""} · generated ${r.generated_at || ""}`;
  $("rec-text").innerHTML = fillTokens(out.recommendation, tk);
  $("rec-why").innerHTML = out.rationale.map((x) => `<li>${fillTokens(x, tk)}</li>`).join("");
  $("rec-alts").innerHTML = out.alternatives.map((a) => `<li><strong>${esc(a.area)}</strong>: ${fillTokens(a.why_not_first, tk)}</li>`).join("");
  $("rec-limits").innerHTML = out.limitations.map((x) => `<li>${fillTokens(x, tk)}</li>`).join("");
  $("rec-cited").innerHTML = (r.cited_reviews || []).map((c) => `<blockquote>“${esc(c.evidence_quote)}”<br><span class="small muted">review <a href="#" data-review="${esc(c.review_id)}">${esc(c.review_id)}</a> · issue <code>${esc(c.issue_id)}</code> · severity ${c.severity} · ${esc(c.intent)}</span></blockquote>`).join("") || "<p class='muted'>The memo cited no specific reviews; see the evidence pack in the full memo.</p>";
  $("rec-consistency").innerHTML = `${cons.ranking_matches ? "<span class='ok'>✔</span>" : "<span class='bad'>✖</span>"} Ranking recomputed in SQL from the reviews and membership tables ${cons.ranking_matches ? "matches" : "does NOT match"} the saved ranking (${cons.issues_recomputed} issues; ${cons.ungrouped_complaints} ungrouped complaints). ` +
    `${r.all_claims_match_database ? "<span class='ok'>✔</span> All" : "<span class='bad'>✖</span> Not all"} ${r.claims.length} claims in claims.csv equal the database values.`;
  $("rec-claims").innerHTML = "<tr><th>Claim</th><th>Issue</th><th>Metric</th><th class='num'>Memo value</th><th class='num'>Database value</th><th>Match</th></tr>" +
    r.claims.map((c) => `<tr><td class="mono">${c.claim_id}</td><td class="mono">${esc(c.issue_id)}</td><td>${c.metric}</td><td class="num">${esc(c.value)}</td><td class="num">${esc(c.database_value)}</td><td>${c.matches_database ? "<span class='ok'>✔</span>" : "<span class='bad'>✖</span>"}</td></tr>`).join("");
  $("rec-memo").innerHTML = md(r.memo_md);
}

// ---- issues --------------------------------------------------------------------------------------------
async function loadIssues() {
  const r = await get("/ranking");
  $("ranking").innerHTML = "<tr><th class='num'>Rank</th><th>Issue</th><th>Area</th><th class='num'>Complaints</th><th class='num'>Severity sum</th><th class='num'>Mean severity</th><th class='num'>Priority</th><th class='num'>Cancellation intent</th><th class='num'>Share</th></tr>" +
    r.issues.map((i) => `<tr class="click" data-issue="${esc(i.issue_id)}"><td class="num">${i.rank}</td><td><strong>${esc(i.name || i.issue_id)}</strong><br><code>${esc(i.issue_id)}</code></td><td>${esc(i.area)}</td><td class="num">${n(i.complaint_count)}</td><td class="num">${n(i.severity_sum)}</td><td class="num">${i.mean_severity}</td><td class="num"><strong>${n(i.priority_score)}</strong></td><td class="num">${n(i.cancellation_count)}</td><td class="num">${pct(i.share_of_complaints)}</td></tr>`).join("");
  document.querySelectorAll("#ranking tr.click").forEach((tr) => tr.addEventListener("click", () => loadIssue(tr.dataset.issue)));
  if (r.issues.length) loadIssue(r.issues[0].issue_id, false);
}
async function loadIssue(id, scroll = true) {
  const d = await get(`/issues/${encodeURIComponent(id)}`);
  const i = d.issue, box = $("issue-detail");
  box.classList.remove("hidden");
  box.innerHTML = `<h3>#${i.rank} ${esc(i.name)} <code>${esc(i.issue_id)}</code></h3>
    <p>${esc(i.summary || i.definition || "")}</p>
    <p class="small muted">Named by ${esc(i.named_by || "taxonomy")} from bounded quotes · ${n(i.complaint_count)} complaints · severity sum ${n(i.severity_sum)} · mean ${i.mean_severity} · ${n(i.cancellation_count)} with cancellation intent · ${n(i.needs_review_count)} flagged needs_review</p>
    <div class="grid2"><div class="chart" style="height:240px"><canvas id="chart-issue"></canvas></div><div class="chart" style="height:240px"><canvas id="chart-issue-sev"></canvas></div></div>
    <h3 style="margin-top:12px">Source evidence (highest severity first, then most helpful votes)</h3>
    ${d.evidence.map((e) => `<div class="quote"><blockquote>“${esc(e.evidence_quote)}”<br><span class="small muted">review <a href="#" data-review="${esc(e.review_id)}">${esc(e.review_id)}</a> · ${esc(e.review_timestamp)} · severity ${e.severity} · ${esc(e.intent)} · ${n(e.review_likes)} helpful votes · labelled by ${esc(e.labeled_by)}</span></blockquote></div>`).join("")}`;
  chart("chart-issue", {type: "line", data: {labels: d.monthly.map((m) => m.month), datasets: [{label: "Complaints per month", data: d.monthly.map((m) => m.complaints), borderColor: "#1db954", tension: .25}]}, options: {plugins: {legend: {position: "bottom"}}}});
  chart("chart-issue-sev", {type: "bar", data: {labels: d.severity_distribution.map((s) => `severity ${s.severity}`), datasets: [{label: "Reviews", data: d.severity_distribution.map((s) => s.n), backgroundColor: "#f79009"}]}, options: {plugins: {legend: {display: false}}}});
  if (scroll) box.scrollIntoView({behavior: "smooth", block: "nearest"});
}

// ---- trends --------------------------------------------------------------------------------------------
async function loadTrends() {
  const t = await get("/trends");
  const months = t.months;
  chart("chart-monthly", {type: "line", data: {labels: months.map((m) => m.month + (m.partial_month ? "*" : "")),
    datasets: [{label: "Complaint share", data: months.map((m) => m.complaint_share * 100), borderColor: "#f04438", tension: .25, yAxisID: "y"},
               {label: "Classified reviews (denominator)", data: months.map((m) => m.reviews), type: "bar", backgroundColor: "rgba(102,112,133,.25)", yAxisID: "y1"}]},
    options: {scales: {y: {title: {display: true, text: "% of classified reviews"}}, y1: {position: "right", grid: {drawOnChartArea: false}, title: {display: true, text: "reviews"}}}, plugins: {legend: {position: "bottom"}}}});
  const areaKeys = Object.keys(months[0]?.areas || {}).filter((k) => k.endsWith("_share_of_reviews"));
  chart("chart-area-months", {type: "line", data: {labels: months.map((m) => m.month),
    datasets: areaKeys.map((k) => { const a = k.replace("_share_of_reviews", ""); return {label: a, data: months.map((m) => Number(m.areas[k]) * 100), borderColor: AREA_COLORS[a] || "#98a2b3", tension: .25}; })},
    options: {scales: {y: {title: {display: true, text: "% of all classified reviews"}}}, plugins: {legend: {position: "bottom"}}}});
  const pc = t.period_comparison;
  if (pc) {
    const p = pc.periods, keys = Object.keys(p);
    $("period").innerHTML = `<p class="small muted">${esc(pc.method)}</p><table><tr><th>Area</th>${keys.map((k) => `<th class="num">${esc(k)}</th>`).join("")}<th class="num">Change</th></tr>` +
      Object.entries(pc.change_in_share_of_reviews).map(([a, ch]) => `<tr><td>${esc(a)}</td><td class="num">${pct(ch["2022"])}</td><td class="num">${pct(ch["2023"])}</td><td class="num ${ch.pp_change > 0 ? "bad" : "ok"}">${ch.pp_change > 0 ? "+" : ""}${ch.pp_change.toFixed(1)} pp</td></tr>`).join("") +
      `<tr><td class="muted">Denominator (classified reviews)</td>${keys.map((k) => `<td class="num muted">${n(p[k].reviews)}</td>`).join("")}<td></td></tr></table>`;
  }
  const sp = t.spike_months;
  $("spikes").innerHTML = sp && sp.spikes?.length ? `<p class="small muted">${esc(sp.rule)}</p>` + sp.spikes.map((s) => `<p><strong>${esc(s.month)}</strong>: ${n(s.reviews)} reviews (median full month ${n(s.median_full_month_reviews)}), complaint share ${pct(s.complaint_share)}. Largest increases vs other months:</p><ul>${s.largest_increases.map((l) => `<li><code>${esc(l.issue_id)}</code> ${pct(l.share_in_month)} vs ${pct(l.share_other_months)} (${l.pp_difference > 0 ? "+" : ""}${l.pp_difference.toFixed(1)} pp)</li>`).join("")}</ul>`).join("") : "<p class='muted'>No spike months.</p>";
}

// ---- evaluation ----------------------------------------------------------------------------------------
function agreeTable(rows) {
  return "<table>" + rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`).join("") + "</table>";
}
async function loadEvaluation() {
  const e = await get("/evals");
  const g = e.golden;
  if (g && g.agreement) {
    const a = g.agreement;
    $("golden").innerHTML = agreeTable([["Cases (ambiguous, several accepted labels)", `${n(g.cases)} (${n(g.ambiguous_cases)})`], ["Topic agreement", pct(a.topic)], ["Intent agreement", pct(a.intent)],
      ["Severity exact / mean absolute error", `${pct(a.severity)} / ${g.severity?.mean_abs_error ?? "–"}`], ["All three correct", pct(a.joint)],
      [`Sentiment within ±${g.sentiment?.tolerance ?? 0.5} / MAE`, `${pct(g.sentiment?.within_tolerance)} / ${g.sentiment?.mean_abs_error ?? "–"}`],
      ["Missing or quarantined predictions (count as wrong)", n(g.missing_or_quarantined_predictions)],
      ["needs_review vs human flag", esc(JSON.stringify(g.needs_review_vs_human || {}))]]) +
      (e.golden_error_analysis ? `<details><summary>Error analysis</summary><div class="md">${md(e.golden_error_analysis)}</div></details>` : "");
  } else $("golden").innerHTML = "<p class='muted'>Golden-set comparison not loaded yet.</p>";
  const v = e.verification_report;
  if (v && v.agreement) {
    const a = v.agreement;
    $("verify").innerHTML = `<p class="small muted">${esc(v.verifier_config)} relabelled a declared random sample of ${n(v.sample?.sample_size)} distinct texts without seeing the enricher's labels; code compared field by field.</p>` +
      agreeTable([["Topic", `${pct(a.topic.rate)} (${a.topic.agree}/${a.topic.of})`], ["Intent", `${pct(a.intent.rate)} (${a.intent.agree}/${a.intent.of})`], ["Severity exact", `${pct(a.severity.rate)} (${a.severity.agree}/${a.severity.of})`], ["Sentiment within ±0.5", pct(a.sentiment_within_tolerance.rate)], ["Verifier failures", n(v.verifier_failures)]]) +
      `<p class="small">Top topic confusions (enricher → verifier): ${Object.entries(v.top_confusions?.topic || {}).slice(0, 5).map(([k, c]) => `<code>${esc(k)}</code> ${c}`).join(", ")}</p>`;
  }
  const p = e.planted_error;
  $("planted").innerHTML = p ? `<p>Status: <span class="${p.status === "detected" ? "ok" : "bad"}">${esc(p.status)}</span></p>` + agreeTable([["Review", `<code>${esc(p.review_id)}</code>`], ["Original", esc(JSON.stringify(p.original))], ["Planted (test copy)", esc(JSON.stringify(p.planted))], ["Flagged fields", esc((p.comparison_after || []).join(", "))]]) : "<p class='muted'>not loaded</p>";
  const inj = e.injection;
  $("injection").innerHTML = inj ? `<p>${esc(inj.summary || "")}</p><div class="table-wrap"><table><tr><th>Case</th><th>Expectation</th><th>Result</th></tr>${(inj.cases || []).map((c) => `<tr><td class="mono">${esc(c.case_id)}</td><td>${esc(c.expectation)}</td><td class="${c.passed ? "ok" : "bad"}">${c.passed ? "pass" : "fail"} ${esc(c.detail || "")}</td></tr>`).join("")}</table></div>` : "<p class='muted'>not loaded</p>";
  const sc = e.self_check, rc = e.rank_check;
  $("checks").innerHTML = agreeTable([
    ["Course checker (check_submission.py)", sc ? `<span class="${sc.status === "pass" ? "ok" : "warn"}">${esc(sc.status)}</span> · coverage candidate ${sc.working_coverage_point_candidate} · ${n(sc.coverage?.valid_completed)} valid completed, ${n(sc.coverage?.quarantined)} quarantined, ${n(sc.coverage?.valid_cache_reuses)} valid cache reuses · issues ${esc(JSON.stringify(sc.issue_counts))}` : "–"],
    ["Ranking rebuilt from grading/ files", rc ? (rc.identical ? "<span class='ok'>identical</span>" : "<span class='bad'>different</span>") + ` (${rc.issues} issues)` : "–"]]);
}

// ---- run & cost ----------------------------------------------------------------------------------------
async function loadRun() {
  const r = await get("/run");
  const c = r.cost || {};
  $("cost").innerHTML = agreeTable([["Billed API spend recorded (all runs)", c.billed_api_spend_recorded_usd != null ? `$${c.billed_api_spend_recorded_usd.toFixed(4)}` : "–"],
    ["100-review pilot: cold run", c.pilot_cold != null ? `$${c.pilot_cold.toFixed(6)}` : "–"], ["100-review pilot: warm run", c.pilot_warm != null ? `$${c.pilot_warm.toFixed(6)} (${n(c.pilot_warm_new_enrichment_calls)} new enrichment calls)` : "–"]]) +
    (c.per_run ? `<div class="table-wrap"><table><tr><th>Run</th><th class="num">Calls</th><th class="num">Billed</th></tr>${Object.entries(c.per_run).map(([k, v]) => `<tr><td class="mono small">${esc(k)}</td><td class="num">${n(v.calls)}</td><td class="num">$${v.billed_usd.toFixed(4)}</td></tr>`).join("")}</table></div>` : "") +
    `<p class="small muted">Claude Pro (claude -p) calls are not billed per call; their API-equivalent value is reported separately in cost/report.md.</p>`;
  const b = r.checkpoint_before, a = r.checkpoint_after;
  $("checkpoints").innerHTML = agreeTable([["Before interruption", b ? `${n(b.completed_ids_count)} completed IDs saved (${esc(b.status)}: ${esc(b.stop_reason || "")})` : "–"],
    ["After resume", a ? `${n(a.completed_ids_count)} completed IDs (${esc(a.status)})` : "–"],
    ["Rule", "the resumed invocation sent only pending reviews; no completed ID was re-sent under the same label_config"]]);
  const recs = r.recordings || [];
  $("recordings").innerHTML = recs.length ? recs.map((x) => `<p class="small muted">${esc(x)}</p><div id="cast-${esc(x)}"></div>`).join("") : "<p class='muted'>No recording loaded.</p>";
  recs.forEach((x) => { try { AsciinemaPlayer.create(`${API}/recording/${encodeURIComponent(x)}`, $(`cast-${x}`), {idleTimeLimit: 2, speed: 2, fit: "width", rows: 28}); } catch (e) { $(`cast-${x}`).textContent = "player failed to load"; } });
  const hist = r.run_summary?.history || [];
  $("history").innerHTML = "<tr><th>Invocation</th><th>Phase</th><th>Status</th><th>Stop reason</th><th class='num'>Wall clock s</th><th class='num'>Completed IDs saved</th></tr>" +
    hist.map((h) => `<tr><td class="mono small">${esc(h.run_id)}</td><td>${esc(h.phase)}</td><td>${esc(h.status)}</td><td>${esc(h.stop_reason || "")}</td><td class="num">${h.wall_clock_s}</td><td class="num">${n(h.completed_ids_saved)}</td></tr>`).join("");
  $("trace-md").innerHTML = r.trace_example_md ? md(r.trace_example_md) : "<p class='muted'>not loaded</p>";
}

// ---- lookup / trace ------------------------------------------------------------------------------------
$("search").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const id = $("s-id").value.trim();
  if (id) return traceReview(id);
  const p = new URLSearchParams();
  if ($("s-q").value.trim()) p.set("q", $("s-q").value.trim());
  if ($("s-intent").value) p.set("intent", $("s-intent").value);
  if ($("s-topic").value) p.set("topic", $("s-topic").value);
  p.set("limit", "25");
  const r = await get(`/reviews?${p}`);
  $("s-results").innerHTML = `<p class="small muted">${n(r.total)} matching reviews (first ${r.reviews.length})</p><div class="table-wrap"><table><tr><th>Review</th><th>Labels</th><th>Text</th></tr>` +
    r.reviews.map((x) => `<tr class="click" data-review="${esc(x.review_id)}"><td class="mono small">${esc(x.review_id.slice(0, 8))}…<br>${esc(x.review_timestamp.slice(0, 10))}</td><td>${x.status === "completed" ? `${esc(x.topic)}/${esc(x.subtopic)}<br>${esc(x.intent)} · sev ${x.severity}` : `<span class="warn">${esc(x.reason)}</span>`}</td><td>${esc(x.review_text)}</td></tr>`).join("") + "</table></div>";
});
document.addEventListener("click", (ev) => {
  const t = ev.target.closest("[data-review]");
  if (t) { ev.preventDefault(); show("lookup"); traceReview(t.dataset.review); }
});
async function traceReview(id) {
  const box = $("trace");
  box.classList.remove("hidden");
  box.innerHTML = "<p class='muted'>Loading trace…</p>";
  try {
    const d = await get(`/reviews/${encodeURIComponent(id)}`);
    const r = d.review, v = d.verification, m = d.issue;
    const vc = d.verification_comparison;
    box.innerHTML = `<h3>Trace: review <code>${esc(r.review_id)}</code></h3><div class="steps">
      <div class="step"><b>1 · Source row (ingest, code)</b>${esc(r.review_text)}<br><span class="small muted">${esc(r.review_timestamp)} · ${esc(r.review_rating)}★ (metadata only) · ${n(r.review_likes)} helpful votes · app ${esc(r.app_version || "missing")} · row hash <code>${esc(r.source_sha256.slice(0, 16))}…</code></span></div>
      <div class="step"><b>2 · Enrichment (model + code)</b>${r.status === "completed" ? `topic <strong>${esc(r.topic)}</strong> / ${esc(r.subtopic)} · intent <strong>${esc(r.intent)}</strong> · severity <strong>${r.severity}</strong> · sentiment ${r.sentiment} · needs_review ${r.needs_review ? "yes" : "no"} · labelled by ${esc(r.labeled_by)}<br>evidence quote: “${esc(r.evidence_quote)}”<br><span class="small muted">entities (code): ${esc((r.entities || []).join(", ") || "–")} · label_config <code>${esc(r.label_config)}</code>${d.cache_source ? ` · exact-text reuse of <a href="#" data-review="${esc(d.cache_source.review_id)}">${esc(d.cache_source.review_id)}</a>` : ""}</span>` : `<span class="warn">quarantined: ${esc(r.reason)}</span>`}</div>
      <div class="step"><b>3 · Independent verification</b>${v ? (v.status === "completed" ? `verifier: ${esc(v.topic)} · ${esc(v.intent)} · severity ${v.severity} · confidence ${esc(v.confidence)}<br>${Object.entries(vc || {}).map(([k, ok]) => `${k} ${ok ? "<span class='ok'>agrees</span>" : "<span class='bad'>differs</span>"}`).join(" · ")}` : `failed: ${esc(v.reason || "")}`) : "<span class='muted'>not in the declared verification sample</span>"}</div>
      <div class="step"><b>4 · Issue membership (code)</b>${m ? `<code>${esc(m.issue_id)}</code> ${esc(m.name || "")}` : "<span class='muted'>not grouped (only complaint and cancellation reviews are ranked)</span>"}</div>
      <div class="step"><b>5 · Ranking (code)</b>${m ? `rank <strong>${m.rank}</strong> · ${n(m.complaint_count)} complaints · severity sum ${n(m.severity_sum)} · mean ${m.mean_severity} · priority ${n(m.priority_score)}` : "–"}</div>
      <div class="step"><b>6 · Memo</b>${d.claims.length ? d.claims.map((c) => `<span class="chip">${c.claim_id}</span> ${c.metric} = ${esc(c.value)}`).join(" · ") : "<span class='muted'>no memo claim for this issue</span>"}<br><span class="small">${d.quoted_in_memo_evidence ? "Quoted in the memo evidence pack." : "Not quoted in the memo evidence pack."}${d.cited_by_memo ? " Cited by the memo." : ""}</span></div>
    </div>`;
  } catch (e) {
    box.innerHTML = `<p class="bad">${esc(e.message)}</p>`;
  }
  box.scrollIntoView({behavior: "smooth", block: "nearest"});
}

// ---- boot ----------------------------------------------------------------------------------------------
(async function boot() {
  try {
    const h = await get("/health");
    $("health").textContent = `backend ✓ · ${h.database} · ${n(h.review_rows)} review rows`;
    $("health").classList.add("ok");
  } catch (e) {
    $("health").textContent = "backend unavailable";
    $("health").classList.add("bad");
  }
  const start = (location.hash || "#overview").slice(1);
  show(loaders[start] ? start : "overview");
  if (start !== "overview" && !loaded.overview) { loaded.overview = true; loadOverview().catch((e) => fail("overview", e)); }
})();
