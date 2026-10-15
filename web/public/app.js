// Spotify Review Insights dashboard: renders data fetched from the read-only API (/api/*).
// Every number shown comes from the backend, which reads the database; nothing here calls a model.
// Formatting (thousands separators, percentages, rounding for display) never changes a stored value:
// the exact value stays in the tooltip and in the traced-numbers tables.
"use strict";

const API = "/api";
const charts = {};
const loaded = {};
const fmt = new Intl.NumberFormat("en-US");
const COLORS = ["#1db954", "#2e90fa", "#f79009", "#9e77ed", "#f04438", "#667085", "#12b76a", "#ee46bc"];
const AREA_COLORS = {"access/onboarding": "#2e90fa", "usability": "#9e77ed", "playback/performance": "#f04438",
                     "billing/support": "#f79009", "catalog/content": "#12b76a", "general/unspecified": "#98a2b3"};
const MODEL_NAMES = {"gpt-6-luna": "GPT-6 Luna", "sonnet": "Claude Sonnet", "haiku": "Claude Haiku", "opus": "Claude Opus"};
const TABS = ["overview", "recommendation", "issues", "trends", "evaluation", "run", "lookup"];
let TOKENS = {};          // token_id -> {value, measure, source, kind} from memo.json token_index (via the database)
let recPromise = null;    // /api/recommendation is shared by the Overview headline and the recommendation tab
let currentTab = null;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const n = (v) => (v === null || v === undefined || v === "" ? "–" : fmt.format(v));
const pct = (v, d = 1) => (v === null || v === undefined || v === "" ? "–" : `${(Number(v) * 100).toFixed(d)}%`);
const big = (s) => String(s).replace(/\b\d{5,}\b/g, (d) => fmt.format(Number(d)));  // 16964 -> 16,964 (years untouched)

function pp(x) {  // percentage-point change for display: one decimal, never "-0.0"
  const r = Math.round(Number(x) * 10) / 10;
  if (!isFinite(r)) return "–";
  if (r === 0) return "0.0 pp";
  return `${r > 0 ? "+" : "−"}${Math.abs(r).toFixed(1)} pp`;
}
function hms(s) {  // seconds -> "2 h 26 min" / "3 min 28 s" / "56.1 s"
  const v = Number(s);
  if (!isFinite(v)) return "–";
  if (v < 60) return `${v.toFixed(1)} s`;
  const h = Math.floor(v / 3600), m = Math.floor((v % 3600) / 60), sec = Math.round(v % 60);
  return h ? `${h} h ${m} min` : `${m} min ${sec} s`;
}
function clock(s) {  // seconds -> "3:00" or "2:26:07"
  const v = Math.max(0, Math.round(Number(s) || 0)), h = Math.floor(v / 3600), m = Math.floor((v % 3600) / 60), sec = String(v % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}
function utc(iso) { return iso ? `${String(iso).slice(0, 16).replace("T", " ")} UTC` : ""; }
function usd(v, d = 2) { return v === null || v === undefined ? "–" : `$${Number(v).toFixed(d)}`; }

// "gpt-6-luna@low(10%)" -> {name: "GPT-6 Luna", effort: "low", cap: "10%"}
function parseTier(spec) {
  const m = String(spec || "").trim().match(/^([^@(]+)(?:@([^()]+))?(?:\(([^)]+)\))?$/) || [];
  const id = (m[1] || String(spec || "")).trim();
  return {id, name: MODEL_NAMES[id] || id, effort: m[2] || "", cap: m[3] || ""};
}
function labelSummary(cfg) {  // label_config -> "GPT-6 Luna (fallbacks: GPT-6 Luna low effort ≤10%, Claude Sonnet ≤0.25%)"
  const tiers = String(cfg || "").split("|")[0].split(">").filter(Boolean).map(parseTier);
  if (!tiers.length) return "";
  const [p, ...fb] = tiers;
  const one = (t) => `${t.name}${t.effort && !["none", "n/a"].includes(t.effort) ? ` ${t.effort} effort` : ""}${t.cap ? ` ≤${t.cap}` : ""}`;
  return `${p.name}${fb.length ? ` (fallbacks: ${fb.map(one).join(", ")})` : ""}`;
}
function configName(cfg) {  // "haiku@n/a|verify-v1|cfg-…" -> "Claude Haiku (verify-v1)"
  const parts = String(cfg || "").split("|");
  return parts[0] ? `${parseTier(parts[0]).name}${parts[1] ? ` (${parts[1]})` : ""}` : "";
}
function prettyStop(status, reason) {  // avoid "interrupted: interrupted (SIGINT)"
  if (!reason) return status || "";
  return String(reason).startsWith(status || "\u0000") ? reason : `${status}: ${reason}`;
}

async function get(path) {
  const r = await fetch(API + path);
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).detail; } catch (e) { /* not JSON */ }
    throw new Error(detail ? String(detail) : `${path}: HTTP ${r.status}`);
  }
  return r.json();
}
function getRec() {
  if (!recPromise) {
    recPromise = get("/recommendation").then((r) => {
      TOKENS = Object.fromEntries((r.token_index || []).map((t) => [t.token_id, t]));
      return r;
    });
    recPromise.catch(() => { recPromise = null; });
  }
  return recPromise;
}

function chart(id, config) {
  if (charts[id]) charts[id].destroy();
  const css = getComputedStyle(document.documentElement);
  Chart.defaults.color = css.getPropertyValue("--muted").trim() || "#5b6573";
  Chart.defaults.borderColor = css.getPropertyValue("--line").trim() || "#e3e6eb";
  Chart.defaults.maintainAspectRatio = false;  // every canvas sits in a fixed-height .chart box
  charts[id] = new Chart($(id), config);
}
const LINE = {cubicInterpolationMode: "monotone", tension: 0, pointRadius: 2};  // no overshoot between points

// ---- memo tokens ---------------------------------------------------------------------------------------
function humanMeasure(m) {  // "areas[billing/support].share_of_complaints" -> "billing/support · share of complaints"
  const s = String(m || "");
  if (/\s/.test(s)) return s;  // already a plain-language label (scope figures)
  const parts = s.replace(/^trends_and_robustness\./, "").match(/[^.\[\]]+(\[[^\]]*\])?/g) || [];
  return parts.map((p) => {
    const mm = p.match(/^([^[]+)(?:\[(.*)\])?$/) || [p, p, ""];
    const key = ["areas", "top_issues"].includes(mm[1]) ? "" : mm[1].replace(/_/g, " ");
    const sel = mm[2] ? (mm[1] === "top_issues" ? `issue ${mm[2]}` : mm[2]) : "";
    return [key, sel].filter(Boolean).join(" · ");
  }).join(" · ");
}
function tokDisplay(id, raw) {
  const t = TOKENS[id] || {};
  const v = String(raw ?? t.value ?? "");
  const m = String(t.measure || "");
  if (/^-?\d+$/.test(v)) return fmt.format(Number(v));
  if (/^-?\d*\.\d+$/.test(v)) {
    if (/share_of_complaints$|\(rate\)$|share$/i.test(m)) return pct(v);
    if (/mean_severity$/.test(m)) return Number(v).toFixed(2);
  }
  return v;
}
function tokTitle(id) {
  const t = TOKENS[id];
  return t ? `${id}: ${humanMeasure(t.measure)}. Exact value ${t.value}. Source: ${t.source}` : id;
}
function tokHtml(id, value) {
  const title = esc(tokTitle(id));
  return `<span class="tok"><strong title="${title}">${esc(tokDisplay(id, value))}</strong><a class="chip" href="#recommendation/${id}" title="${title}">${id}</a></span>`;
}
function codeText(text) {  // code-written memo text: "25.7% (A19)" -> number with a token chip; `file` -> <code>
  return esc(big(text)).replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/([^\s(]+) \(([CAST]\d{2,3})\)/g, (m, v, id) => (TOKENS[id] ? tokHtml(id, TOKENS[id].value) : m));
}
function fillTokens(text, tokens) {
  return esc(text).replace(/\{([CAST]\d{2,3})\}/g, (m, t) => (tokens[t] === undefined ? m : tokHtml(t, tokens[t])));
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
    if (/^\d+\. /.test(l)) { html += "<ol>"; while (i < lines.length && /^\d+\. /.test(lines[i])) html += `<li>${inline(lines[i++].replace(/^\d+\. /, ""))}</li>`; html += "</ol>"; continue; }
    if (/^> /.test(l)) { html += `<blockquote>${inline(l.slice(2))}</blockquote>`; i++; continue; }
    if (l.trim()) html += `<p>${inline(l)}</p>`;
    i++;
  }
  return html;
}

// ---- navigation: #tab or #tab/<argument> (review ID, issue ID or token ID) ------------------------------
const loaders = {overview: loadOverview, recommendation: loadRecommendation, issues: loadIssues, trends: loadTrends,
                 evaluation: loadEvaluation, run: loadRun, lookup: async () => {}};
function parseHash() {
  const raw = location.hash.replace(/^#/, "");
  const cut = raw.indexOf("/");
  const tab = cut < 0 ? raw : raw.slice(0, cut);
  let arg = cut < 0 ? "" : raw.slice(cut + 1);
  try { arg = decodeURIComponent(arg); } catch (e) { /* keep raw */ }
  return {tab: TABS.includes(tab) ? tab : "overview", arg: arg || null};
}
function go(tab, arg) {
  const h = `#${tab}${arg ? "/" + encodeURIComponent(arg) : ""}`;
  if (location.hash === h) route(); else location.hash = h;  // hashchange -> route()
}
function ensureLoaded(tab) {
  if (!loaded[tab]) loaded[tab] = loaders[tab]().catch((e) => { fail(tab, e); delete loaded[tab]; throw e; });
  return loaded[tab];
}
function activate(tab, instant = false) {
  document.querySelectorAll(".tabs button").forEach((b) => {
    const on = b.dataset.tab === tab;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    if (on) {  // keep the active tab visible in the scrollable strip (phones)
      const nav = $("tabs"), dx = b.getBoundingClientRect().left - nav.getBoundingClientRect().left;
      nav.scrollTo({left: Math.max(0, nav.scrollLeft + dx - 24), behavior: instant ? "auto" : "smooth"});
    }
  });
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${tab}`));
}
async function route() {
  const {tab, arg} = parseHash();
  const changed = tab !== currentTab, first = currentTab === null;
  currentTab = tab;
  activate(tab, first);
  if (changed && !arg) window.scrollTo(0, 0);
  try { await ensureLoaded(tab); } catch (e) { return; }
  if (!arg) return;
  if (tab === "lookup") traceReview(arg);
  else if (tab === "issues") loadIssue(arg, true);
  else if (tab === "recommendation") focusRow(`tok-${arg}`);
}
function focusRow(id) {
  const row = $(id);
  if (!row) return;
  row.scrollIntoView({behavior: "smooth", block: "center"});
  row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash");
}
function fail(tab, e) {
  const sec = $(`tab-${tab}`);
  const div = document.createElement("div");
  div.className = "card bad";
  div.textContent = `Could not load: ${e.message}`;
  sec.prepend(div);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => go(b.dataset.tab)));
window.addEventListener("hashchange", route);
function tabHint() {
  const nav = $("tabs");
  nav.classList.toggle("more-right", nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 4);
  nav.classList.toggle("more-left", nav.scrollLeft > 4);
}
$("tabs").addEventListener("scroll", tabHint, {passive: true});
window.addEventListener("resize", tabHint);

// ---- overview ------------------------------------------------------------------------------------------
async function loadOverview() {
  const o = await get("/overview");
  const c = o.counts, run = o.run;
  if (run.offline_stub) $("stub-banner").classList.remove("hidden");
  const acct = run.scope || {};
  const verifier = configName(o.verification?.verifier_config);
  $("scope").innerHTML = `Run ${esc(run.run_key)} · ${n(run.analysis_rows)} reviews in the declared scope` +
    (acct.full_rows ? ` (uniform sample of ${n(acct.full_rows)} ingested)` : "") +
    ` · <span title="label_config: ${esc(run.label_config)}">labels: ${esc(labelSummary(run.label_config))}</span>` +
    (verifier ? ` · verifier: ${esc(verifier)}` : "");
  const v = o.verification?.agreement, g = o.golden?.agreement;
  const unfinished = c.rows - c.completed - c.quarantined;
  const qr = o.quarantine_reasons || [];
  const onlyEmpty = qr.length > 0 && qr.every((x) => x.reason === "empty_review_text");
  const fr = o.cost?.final_run;
  const kpis = [
    ["Reviews in scope", n(c.rows), acct.full_rows ? `of ${n(acct.full_rows)} ingested and profiled` : ""],
    ["Classified", n(c.completed), unfinished === 0 && (onlyEmpty || !c.quarantined)
      ? `all ${n(c.completed)} non-empty reviews${c.quarantined ? ` (${n(c.quarantined)} empty-text rows quarantined)` : ""}`
      : `${pct(c.completed / c.rows)} of scope; ${n(unfinished)} unfinished`],
    ["Quarantined", n(c.quarantined), qr.map((x) => `${n(x.n)} ${String(x.reason || "").replace(/_/g, " ")}`).join("; ").slice(0, 80)],
    ["Complaints + cancellations", n(c.complaints), `${pct(c.complaints / c.completed)} of classified; ${n(c.cancellations)} cancellation intent`],
    ["Exact-text cache reuses", n(c.exact_text_cache_reuses), "duplicate texts reuse one model result"],
    ["Flagged needs_review", n(c.needs_review), `${pct(c.needs_review / c.completed)} of classified`],
    ["Verifier agreement (topic / intent / severity)", v ? `${pct(v.topic.rate, 0)} / ${pct(v.intent.rate, 0)} / ${pct(v.severity.rate, 0)}` : "–", o.verification ? `${n(o.verification.compared)} sampled reviews` : "pending"],
    ["Golden agreement (topic / intent / severity)", g ? `${pct(g.topic, 0)} / ${pct(g.intent, 0)} / ${pct(g.severity, 0)}` : "–", o.golden ? `${o.golden.cases ?? ""} human-labelled reviews` : "pending"],
    ["Billed API spend (all runs)", usd(o.cost?.billed_api_spend_recorded_usd), fr ? `final run ${usd(fr.billed_usd)}; from saved call logs × dated rates` : "from saved call logs × dated rates"],
  ];
  $("kpis").innerHTML = kpis.map(([l, val, s]) => `<div class="kpi"><div class="l">${esc(l)}</div><div class="v">${esc(val)}</div><div class="s">${esc(s)}</div></div>`).join("");
  const areas = o.areas;
  chart("chart-areas", {type: "bar", data: {labels: areas.map((a) => a.area + (a.decision_option ? "" : " *")),
    datasets: [{label: "Severity sum (baseline priority)", data: areas.map((a) => a.severity_sum), backgroundColor: areas.map((a) => AREA_COLORS[a.area] || "#98a2b3")},
               {label: "Complaint and cancellation reviews", data: areas.map((a) => a.complaint_count), backgroundColor: "rgba(102,112,133,.35)"}]},
    options: {indexAxis: "y", plugins: {legend: {display: false}, tooltip: {callbacks: {afterBody: (it) => {
      const a = areas[it[0].dataIndex]; return `share of complaints ${pct(a.share_of_complaints)}; ${n(a.cancellation_count)} cancellation intent${a.decision_option ? "" : "; not a decision area"}`; }}}}}});
  const totalIntents = o.intents.reduce((s, x) => s + x.n, 0);
  chart("chart-intents", {type: "doughnut", data: {labels: o.intents.map((x) => `${x.intent} ${n(x.n)} (${pct(x.n / totalIntents)})`), datasets: [{data: o.intents.map((x) => x.n), backgroundColor: COLORS}]},
    options: {plugins: {legend: {position: "right"}}}});
  chart("chart-topics", {type: "bar", data: {labels: o.topics.map((t) => t.topic), datasets: [{label: "Complaints + cancellations", data: o.topics.map((t) => t.complaints), backgroundColor: "#2e90fa"}, {label: "All classified", data: o.topics.map((t) => t.n), backgroundColor: "rgba(102,112,133,.3)"}]},
    options: {plugins: {legend: {position: "bottom"}}}});
  chart("chart-severity", {type: "bar", data: {labels: o.complaint_severity.map((s) => `severity ${s.severity}`), datasets: [{label: "Complaint reviews", data: o.complaint_severity.map((s) => s.n), backgroundColor: ["#98a2b3", "#fdb022", "#f79009", "#f04438", "#912018"]}]},
    options: {plugins: {legend: {display: false}}}});
  const tiers = (o.labeled_by || []).map((t) => `${esc(t.labeled_by)} ${n(t.n)}`).join(" · ");
  $("accounting").innerHTML = `<table class="kv">
    <tr><th>Full source file</th><td class="mono">${esc(run.full_source || "–")} ${run.full_sha256 ? "sha256 " + esc(run.full_sha256.slice(0, 16)) + "…" : ""}</td></tr>
    <tr><th>Declared analysis input</th><td class="mono">${esc(run.analysis_input)} sha256 ${esc(run.analysis_sha256.slice(0, 16))}…</td></tr>
    <tr><th>Rows: ingested / in scope / out of scope</th><td>${n(acct.full_rows)} / ${n(acct.analysis_rows_matched_in_full_file ?? run.analysis_rows)} / ${n(acct.out_of_scope_rows)} (out of scope: profiled, not classified)</td></tr>
    <tr><th>Completed / quarantined / unfinished</th><td>${n(c.completed)} / ${n(c.quarantined)} / ${n(unfinished)}</td></tr>
    <tr><th>Who labelled</th><td>${tiers} <span class="muted small">(cache = exact-text reuse of an original's result)</span></td></tr>
    <tr><th>Labelling configuration</th><td>${esc(labelSummary(run.label_config))}<br><span class="mono small muted">label_config ${esc(run.label_config)}</span></td></tr></table>`;
  loadHeadline(c).catch((e) => { $("headline").innerHTML = `<p class="bad">Could not load the recommendation: ${esc(e.message)}</p>`; });
}

async function loadHeadline(counts) {
  const r = await getRec();
  const h = r.headline || {}, t = h.top_issue;
  const box = $("headline");
  box.classList.remove("loading");
  const tk = (x) => (x ? tokHtml(x.token, x.value) : "–");
  const claim = (metric, value) => (t?.claim_ids?.[metric] ? tokHtml(t.claim_ids[metric], value) : esc(n(value)));
  let caveat = "";
  if (h.verifier_top && h.verifier_top.area !== h.area) {
    caveat = `<p class="small">Caveat: the independent verifier's sample ranks <strong>${esc(h.verifier_top.area)}</strong> first by severity sum (${tk(h.verifier_top)}${h.verifier_recommended ? ` vs ${tk(h.verifier_recommended)} for ${esc(h.area)}` : ""}), so the lead is provisional.</p>`;
  }
  box.innerHTML = `<div class="rec-head"><span class="pill-label">Recommended focus for next quarter</span><span class="pill">${esc(h.area || r.recommended_area)}</span></div>
    ${t ? `<p class="lead">#${t.rank} issue overall, and the largest in this area: <strong>${esc(t.name || t.issue_id)}</strong>, ${claim("complaint_count", t.complaint_count)} complaint and cancellation reviews, severity sum ${claim("severity_sum", t.severity_sum)} (${pct(t.share_of_complaints)} of all ${n(counts?.complaints)} complaints).</p>` : ""}
    <p>Area severity sum ${tk(h.area_severity_sum)}${h.period_change ? `; area complaints as a share of all reviews ${tk(h.period_change)} between the same months one year apart` : ""}.</p>
    ${caveat}
    <p><a class="more" href="#recommendation">Full recommendation, alternatives, limitations and every number traced →</a></p>`;
}

// ---- recommendation ------------------------------------------------------------------------------------
function memoSource(r) {
  const parts = String(r.memo_config || "").split("|");
  const who = parseTier(parts[0]).name, ver = parts[1] || "";
  if (String(r.source).startsWith("template")) return `Written by code (${r.source}); numbers filled in by code; ${utc(r.generated_at)}`;
  return `Written by ${who}${ver ? ` (${ver})` : ""} from saved aggregates and quotes${r.source === "cache" ? " (saved model output reused)" : ""}; every number filled in by code; ${utc(r.generated_at)}`;
}
function checkCell(chk) {
  if (!chk) return "<span class='muted small'>from the saved file</span>";
  return chk.matches ? `<span class="ok" title="${esc(chk.method)}">✔</span> <span class="small muted">${esc(chk.method)}</span>`
    : `<span class="bad" title="${esc(chk.method)}">✖</span> <span class="small">database ${esc(chk.database_value)}</span>`;
}
async function loadRecommendation() {
  const r = await getRec();
  const consP = get("/consistency");
  const out = r.output, tk = r.tokens;
  $("rec-area").textContent = r.recommended_area;
  $("rec-source").textContent = memoSource(r);
  $("rec-source").title = `memo_config ${r.memo_config || ""} · source ${r.source}`;
  $("rec-text").innerHTML = fillTokens(out.recommendation, tk);
  $("rec-why").innerHTML = out.rationale.map((x) => `<li>${fillTokens(x, tk)}</li>`).join("");
  const nt = r.notes || {};
  const notes = [];
  const outside = (nt.period_changes_outside_decision_areas || []).filter((o) => o.pp_change !== null && o.pp_change !== undefined)
    .sort((a, b) => b.pp_change - a.pp_change);
  if (outside.length) {
    const lead = nt.largest_period_change_among_decision_areas;
    notes.push(`Period comparisons that rank areas refer to the four decision areas${lead ? ` (largest change among them: ${esc(lead.area)} ${pp(lead.pp_change)})` : ""}. ` +
      `Outside them (not decision options): ${outside.map((o) => `${esc(o.area)} ${pp(o.pp_change)}`).join(", ")} over the same months (see Trends).`);
  }
  const sl = nt.complaint_share_leader;
  if (sl) {
    notes.push(`On share of complaints, ${esc(sl.leader)} (${pct(sl.leader_share)}, 95% interval ${pct(sl.leader_ci95[0])}–${pct(sl.leader_ci95[1])}) is ahead of ${esc(sl.recommended)} (${pct(sl.recommended_share)}, ${pct(sl.recommended_ci95[0])}–${pct(sl.recommended_ci95[1])}); the intervals ${sl.intervals_overlap ? "overlap" : "do not overlap"}.` +
      (nt.severity_leader ? ` On the baseline priority (severity sum) ${esc(nt.severity_leader.area)} leads (${n(nt.severity_leader.severity_sum)}).` : ""));
  }
  $("rec-notes").innerHTML = notes.length ? `<div class="note"><strong>Checked by code against the database:</strong>${notes.map((x) => `<p>${x}</p>`).join("")}</div>` : "";
  $("rec-alts").innerHTML = out.alternatives.map((a) => `<li><strong>${esc(a.area)}</strong>: ${fillTokens(a.why_not_first, tk)}</li>`).join("");
  $("rec-limits").innerHTML = out.limitations.map((x) => `<li>${fillTokens(x, tk)}</li>`).join("") +
    (r.limitations_code || []).map((x) => `<li>${codeText(x)} <span class="tag">added by code</span></li>`).join("");
  const text = (x) => (typeof x === "string" ? x : (x.action || x.text || Object.values(x).join(" — ")));
  const list = (xs) => (xs || []).map((x) => `<li>${fillTokens(text(x), tk)}</li>`).join("");
  $("rec-actions").innerHTML = list(out.next_quarter_actions) || "<li class='muted'>not in this memo version</li>";
  $("rec-change").innerHTML = list(out.what_would_change_the_call) || "<li class='muted'>not in this memo version</li>";
  $("rec-cited").innerHTML = (r.cited_reviews || []).map((c) => `<blockquote>“${esc(c.evidence_quote)}”<br><span class="small muted">review <a href="#lookup/${esc(c.review_id)}">${esc(c.review_id)}</a> · issue <code>${esc(c.issue_id)}</code> · severity ${c.severity} · ${esc(c.intent)}</span></blockquote>`).join("") || "<p class='muted'>The memo cited no specific reviews; see the evidence pack in the full memo.</p>";
  $("rec-card").classList.remove("loading");
  $("rec-claims").innerHTML = "<tr><th>Token</th><th>Issue</th><th>Metric</th><th class='num'>Memo value</th><th class='num'>Database value</th><th>Match</th><th>Source</th></tr>" +
    r.claims.map((c) => `<tr id="tok-${esc(c.claim_id)}"><td class="mono">${esc(c.claim_id)}</td><td class="mono">${esc(c.issue_id)}</td><td>${esc(c.metric.replace(/_/g, " "))}</td><td class="num">${esc(c.value)}</td><td class="num">${esc(c.database_value)}</td><td>${c.matches_database ? "<span class='ok'>✔</span>" : "<span class='bad'>✖</span>"}</td><td class="small muted">${esc(TOKENS[c.claim_id]?.source || "claims.csv")}</td></tr>`).join("");
  const others = (r.token_index || []).filter((t) => !t.token_id.startsWith("C"));
  const KIND = {A: "Area roll-up (A): complaint and cancellation reviews grouped by decision area", S: "Scope figures (S)", T: "Trends and robustness (T)"};
  const renderTokens = (checks) => {
    let prev = "";
    $("rec-tokens").innerHTML = others.length ? "<tr><th>Token</th><th class='num'>Shown as</th><th class='num'>Exact value</th><th>What it measures</th><th>Source file</th><th>Rechecked in SQL</th></tr>" +
      others.map((t) => {
        const k = t.token_id[0];
        const head = k !== prev ? `<tr class="group"><th colspan="6">${esc(KIND[k] || k)}</th></tr>` : "";
        prev = k;
        return head + `<tr id="tok-${esc(t.token_id)}"><td class="mono">${esc(t.token_id)}</td><td class="num">${esc(tokDisplay(t.token_id))}</td><td class="num mono">${esc(t.value)}</td><td title="${esc(t.measure)}">${esc(humanMeasure(t.measure))}</td><td class="small mono">${esc(t.source)}</td><td>${checks ? checkCell(checks[t.token_id]) : "<span class='muted small'>checking…</span>"}</td></tr>`;
      }).join("") : "<tr><td class='muted'>No token index in this database (reload it with the current web/load_db.py).</td></tr>";
  };
  renderTokens(null);
  $("rec-memo").innerHTML = md(r.memo_md);
  if (parseHash().arg) focusRow(`tok-${parseHash().arg}`);
  consP.then((cons) => {
    renderTokens(cons.token_checks || {});
    $("rec-consistency").innerHTML = `<p>${cons.ranking_matches ? "<span class='ok'>✔</span>" : "<span class='bad'>✖</span>"} Ranking recomputed in SQL from the reviews and membership tables ${cons.ranking_matches ? "matches" : "does NOT match"} the saved ranking (${n(cons.issues_recomputed)} issues; ${n(cons.ungrouped_complaints)} ungrouped complaints).</p>` +
      `<p>${r.all_claims_match_database && cons.claims_match ? "<span class='ok'>✔</span> All" : "<span class='bad'>✖</span> Not all"} ${r.claims.length} issue-level claims equal the database values.</p>` +
      (cons.tokens_checked ? `<p>${cons.tokens_match ? "<span class='ok'>✔</span>" : "<span class='bad'>✖</span>"} ${cons.tokens_checked} of the ${others.length} area, scope and trend figures were recomputed in SQL; ${cons.tokens_match ? "all match" : "some differ (marked ✖)"}. The rest come from saved analysis files listed per row.</p>` : "");
    if (parseHash().arg) focusRow(`tok-${parseHash().arg}`);
  }).catch((e) => { $("rec-consistency").innerHTML = `<span class="bad">SQL check failed: ${esc(e.message)}</span>`; renderTokens({}); });
}

// ---- issues --------------------------------------------------------------------------------------------
function namedBy(v) {
  const s = String(v || "");
  if (s === "model") return "Named by the model from the representative quotes below";
  if (s === "cache") return "Named by the model from the representative quotes below (saved output reused)";
  if (s.includes("catch-all")) return "Taxonomy name: catch-all issue, never named by a model";
  if (s.startsWith("taxonomy default (")) return `Taxonomy name (${esc(s.replace(/^taxonomy default \(|\)$/g, ""))})`;
  if (s.startsWith("taxonomy")) return "Taxonomy name (only the top-ranked issues are named by the model)";
  return esc(s || "Taxonomy name");
}
const catchAll = (i) => String(i.named_by || "").includes("catch-all");
async function loadIssues() {
  const r = await get("/ranking");
  const total = r.total_complaints ?? r.issues.reduce((s, i) => s + i.complaint_count, 0);
  $("ranking").innerHTML = `<tr><th>Issue (rank)</th><th class='num'>Priority<br>(= severity sum)</th><th class='num'>Complaints</th><th class='num'>Mean<br>severity</th><th class='num'>Share of complaints<br>(of ${n(total)})</th><th class='num'>Cancellation<br>intent</th><th>Area</th></tr>` +
    r.issues.map((i) => `<tr class="click" id="issue-row-${esc(i.issue_id)}" data-issue="${esc(i.issue_id)}"><td><span class="muted">#${i.rank}</span> <strong>${esc(i.name || i.issue_id)}</strong>${catchAll(i) ? ' <span class="tag">catch-all</span>' : ""}<br><code>${esc(i.issue_id)}</code></td><td class="num"><strong>${n(i.priority_score)}</strong>${i.priority_score !== i.severity_sum ? `<br><span class="small bad">severity sum ${n(i.severity_sum)}</span>` : ""}</td><td class="num">${n(i.complaint_count)}</td><td class="num" title="${esc(i.mean_severity)}">${Number(i.mean_severity).toFixed(2)}</td><td class="num">${pct(i.share_of_complaints)}</td><td class="num">${n(i.cancellation_count)}</td><td>${esc(i.area)}</td></tr>`).join("");
  document.querySelectorAll("#ranking tr.click").forEach((tr) => tr.addEventListener("click", () => go("issues", tr.dataset.issue)));
  if (r.issues.length && !parseHash().arg) loadIssue(r.issues[0].issue_id, false);
}
function quoteHtml(e, quote) {
  return `<blockquote${e.misfit ? ' class="misfit"' : ""}>“${esc(quote ?? e.evidence_quote)}”${e.misfit ? ' <span class="tag">naming model: does not fit the name</span>' : ""}<br><span class="small muted">review <a href="#lookup/${esc(e.review_id)}">${esc(String(e.review_id).slice(0, 8))}…</a>${e.review_timestamp ? ` · ${esc(String(e.review_timestamp).slice(0, 10))}` : ""}${e.severity != null ? ` · severity ${e.severity}` : ""}${e.intent ? ` · ${esc(e.intent)}` : ""}${e.review_likes != null ? ` · ${n(e.review_likes)} helpful votes` : ""}${e.labeled_by ? ` · labelled by ${esc(e.labeled_by)}` : ""}</span></blockquote>`;
}
async function loadIssue(id, scroll = true) {
  const box = $("issue-detail");
  let d;
  try { d = await get(`/issues/${encodeURIComponent(id)}`); } catch (e) { box.classList.remove("hidden"); box.innerHTML = `<p class="bad">${esc(e.message)}</p>`; return; }
  const i = d.issue;
  document.querySelectorAll("#ranking tr.selected").forEach((tr) => tr.classList.remove("selected"));
  $(`issue-row-${i.issue_id}`)?.classList.add("selected");
  box.classList.remove("hidden");
  const rep = d.representative || [];
  box.innerHTML = `<h3>#${i.rank ?? "–"} ${esc(i.name)} <code>${esc(i.issue_id)}</code>${catchAll(i) ? ' <span class="tag">catch-all</span>' : ""}</h3>
    <p>${esc(i.summary || i.definition || "")}</p>
    <p class="small muted">${namedBy(i.named_by)} · ${n(i.complaint_count)} complaint and cancellation reviews · priority (severity sum) ${n(i.priority_score)} · mean severity ${i.mean_severity != null ? Number(i.mean_severity).toFixed(2) : "–"} · ${n(i.cancellation_count)} with cancellation intent · ${n(i.needs_review_count)} flagged needs_review</p>
    ${i.summary && i.definition ? `<details class="small"><summary>Taxonomy definition used for labelling</summary><p>${esc(i.definition)}</p></details>` : ""}
    <div class="grid2" style="margin-top:10px"><div><p class="small muted">Issue complaints as a share of all classified reviews in the month (* partial month; counts on hover)</p><div class="chart" style="height:230px"><canvas id="chart-issue"></canvas></div></div><div><p class="small muted">Severity of this issue's reviews (most common: ${d.modal_severity ?? "–"})</p><div class="chart" style="height:230px"><canvas id="chart-issue-sev"></canvas></div></div></div>
    ${rep.length ? `<h3 style="margin-top:14px">Representative quotes</h3><p class="small muted">The bounded evidence pack (chosen by code) that the issue name was based on${rep.some((e) => e.misfit) ? "; quotes the naming model flagged as not fitting are listed last" : ""}.</p>${rep.map((e) => quoteHtml(e, e.quote)).join("")}` : ""}
    <h3 style="margin-top:14px">More reviews in this issue</h3><p class="small muted">Closest to the issue's most common severity (${d.modal_severity ?? "–"}) first, then most helpful votes; original texts only (exact-text copies share these labels).</p>
    ${d.evidence.map((e) => quoteHtml(e)).join("") || "<p class='muted'>No further reviews.</p>"}`;
  const m = d.monthly;
  chart("chart-issue", {type: "line", data: {labels: m.map((x) => x.month + (x.partial_month ? "*" : "")),
    datasets: [{label: "Share of the month's classified reviews (%)", data: m.map((x) => (x.month_reviews ? (100 * x.complaints) / x.month_reviews : null)), borderColor: "#1db954", backgroundColor: "#1db954", ...LINE}]},
    options: {plugins: {legend: {display: false}, tooltip: {callbacks: {label: (it) => `${it.parsed.y.toFixed(2)}% · ${n(m[it.dataIndex].complaints)} of ${n(m[it.dataIndex].month_reviews)} classified reviews`}}},
      scales: {y: {beginAtZero: true, title: {display: true, text: "% of classified reviews"}}}}});
  chart("chart-issue-sev", {type: "bar", data: {labels: d.severity_distribution.map((s) => `severity ${s.severity}`), datasets: [{label: "Reviews", data: d.severity_distribution.map((s) => s.n), backgroundColor: "#f79009"}]}, options: {plugins: {legend: {display: false}}}});
  if (scroll) box.scrollIntoView({behavior: "smooth", block: "start"});
}

// ---- trends --------------------------------------------------------------------------------------------
async function loadTrends() {
  const t = await get("/trends");
  const months = t.months, decision = new Set(t.decision_areas || []);
  const star = (a) => (decision.size && !decision.has(a) ? `${a} *` : a);
  const labels = months.map((m) => m.month + (m.partial_month ? "*" : ""));
  chart("chart-monthly", {type: "line", data: {labels,
    datasets: [{label: "Complaint share (%)", data: months.map((m) => m.complaint_share * 100), borderColor: "#f04438", backgroundColor: "#f04438", yAxisID: "y", ...LINE},
               {label: "Classified reviews (denominator)", data: months.map((m) => m.reviews), type: "bar", backgroundColor: "rgba(102,112,133,.25)", yAxisID: "y1"}]},
    options: {scales: {y: {beginAtZero: true, title: {display: true, text: "% of classified reviews"}}, y1: {position: "right", grid: {drawOnChartArea: false}, title: {display: true, text: "reviews"}}}, plugins: {legend: {position: "bottom"}}}});
  const areaKeys = Object.keys(months[0]?.areas || {}).filter((k) => k.endsWith("_share_of_reviews"));
  chart("chart-area-months", {type: "line", data: {labels,
    datasets: areaKeys.map((k) => { const a = k.replace("_share_of_reviews", ""); const col = AREA_COLORS[a] || "#98a2b3"; return {label: star(a), data: months.map((m) => Number(m.areas[k]) * 100), borderColor: col, backgroundColor: col, borderDash: decision.size && !decision.has(a) ? [5, 4] : [], ...LINE}; })},
    options: {scales: {y: {beginAtZero: true, title: {display: true, text: "% of all classified reviews"}}}, plugins: {legend: {position: "bottom"}}}});
  const pc = t.period_comparison;
  if (pc) {
    const p = pc.periods, keys = Object.keys(p);
    const rows = Object.entries(pc.change_in_share_of_reviews);
    const anyOutside = rows.some(([a]) => decision.size && !decision.has(a));
    $("period").innerHTML = `<p class="small muted">${esc(pc.method)}</p><table><tr><th>Area</th>${keys.map((k) => `<th class="num">${esc(k)}</th>`).join("")}<th class="num">Change</th></tr>` +
      rows.map(([a, ch]) => `<tr><td>${esc(star(a))}</td>${keys.map((k, j) => `<td class="num">${pct(ch[Object.keys(ch).filter((x) => x !== "pp_change")[j]])}</td>`).join("")}<td class="num ${Math.round(ch.pp_change * 10) > 0 ? "bad" : "ok"}">${pp(ch.pp_change)}</td></tr>`).join("") +
      `<tr><td class="muted">Denominator (classified reviews)</td>${keys.map((k) => `<td class="num muted">${n(p[k].reviews)}</td>`).join("")}<td></td></tr></table>` +
      (anyOutside ? `<p class="small muted">* Not one of the four decision areas. The memo compares the four decision areas only, so its “largest increase” refers to them.</p>` : "");
  }
  const sp = t.spike_months;
  const rises = (s) => (s.largest_increases || []).filter((l) => Math.round(l.pp_difference * 10) > 0);
  $("spikes").innerHTML = sp && sp.spikes?.length ? `<p class="small muted">${esc(sp.rule)}</p>` + sp.spikes.map((s) => {
    const up = rises(s);
    return `<p><strong>${esc(s.month)}</strong>: ${n(s.reviews)} reviews (median full month ${n(s.median_full_month_reviews)}), complaint share ${pct(s.complaint_share)}.</p>` +
      (up.length ? `<p class="small">Issues whose share of complaints rose versus the other months:</p><ul>${up.map((l) => `<li><a href="#issues/${esc(l.issue_id)}"><code>${esc(l.issue_id)}</code></a> ${pct(l.share_in_month)} vs ${pct(l.share_other_months)} (${pp(l.pp_difference)})</li>`).join("")}</ul>`
        : `<p class="small muted">No issue's share of complaints rose: the extra volume kept the usual issue mix.</p>`);
  }).join("") : "<p class='muted'>No spike months.</p>";
}

// ---- evaluation ----------------------------------------------------------------------------------------
function agreeTable(rows) {
  return "<div class='table-wrap'><table class='kv'>" + rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`).join("") + "</table></div>";
}
function needsReviewText(m) {  // {"human=False,model=False": 41, …} -> readable agreement
  const get = (h, mo) => Number(m?.[`human=${h},model=${mo}`] || 0);
  const nn = get("False", "False"), yy = get("True", "True"), my = get("False", "True"), hy = get("True", "False");
  const tot = nn + yy + my + hy;
  if (!tot) return "–";
  return `agree ${nn + yy}/${tot} (both no ${nn}, both yes ${yy}); model only ${my}; human only ${hy}`;
}
const labelsText = (x) => (x ? `${esc(x.topic)} / ${esc(x.intent)} / severity ${esc(x.severity)} / sentiment ${esc(x.sentiment)}` : "–");
const confusions = (obj) => Object.entries(obj || {}).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, c]) => `<code>${esc(k)}</code> ${n(c)}`).join(", ") || "–";
function candidatesTable(c, final) {  // setups compared on the golden 50 before the final run was chosen
  if (!c || !Object.keys(c).length) return "";
  const rows = [["golden-luna-none", "GPT-6 Luna, effort none"], ["golden-luna-low", "GPT-6 Luna, effort low (chosen)"], ["golden-decisions", "OpenAI Decisions"]]
    .filter(([k]) => c[k]?.agreement);
  const best = Math.max(...rows.map(([k]) => c[k].agreement.joint));
  return `<p class="small"><strong>Setup chosen on these 50.</strong> Each candidate labelled the same texts; the predeclared rule picks the best “all three correct” within the cost cap, and the final run uses the winner's exact configuration.</p>` +
    `<div class="table-wrap"><table><tr><th>Candidate</th><th class="num">Topic</th><th class="num">Intent</th><th class="num">Severity</th><th class="num">All three</th></tr>` +
    rows.map(([k, label]) => { const a = c[k].agreement; return `<tr${a.joint === best ? " class='hl'" : ""}><td>${esc(label)}</td><td class="num">${pct(a.topic, 0)}</td><td class="num">${pct(a.intent, 0)}</td><td class="num">${pct(a.severity, 0)}</td><td class="num">${pct(a.joint, 0)}</td></tr>`; }).join("") +
    (final?.agreement ? `<tr><td>Final run (winner's configuration, all 200,000)</td><td class="num">${pct(final.agreement.topic, 0)}</td><td class="num">${pct(final.agreement.intent, 0)}</td><td class="num">${pct(final.agreement.severity, 0)}</td><td class="num">${pct(final.agreement.joint, 0)}</td></tr>` : "") +
    `</table></div>`;
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
      ["needs_review flag vs human flag", needsReviewText(g.needs_review_vs_human)]]) +
      candidatesTable(e.golden_candidates, g) +
      (e.golden_error_analysis ? `<details><summary>Error analysis</summary><div class="md">${md(e.golden_error_analysis)}</div></details>` : "");
  } else $("golden").innerHTML = "<p class='muted'>Golden-set comparison not loaded yet.</p>";
  const qs = e.quote_support;
  if (qs && qs.by_set) {
    const order = ["golden/model", "golden/human", "final_sample/model"];
    const name = {"golden/model": "Golden 50, final run's quotes", "golden/human": "Golden 50, Eason's quotes", "final_sample/model": "Random final-run sample"};
    const keys = order.filter((k) => qs.by_set[k]);
    $("quotes").innerHTML = `<p class="small muted">Code checks that each quote is an exact substring of its review. A blind judge (Claude Haiku, Claude Pro, not billed) then reads the review, the quote and the three labels, and says whether the quote alone supports each label. Model and human items are shuffled together, so Eason's own quotes calibrate the judge.</p>` +
      `<div class="table-wrap"><table><tr><th>Set</th><th class="num">Items</th><th class="num">Exact substring</th><th class="num">Topic</th><th class="num">Intent</th><th class="num">Severity</th><th class="num">All three</th></tr>` +
      keys.map((k) => { const t = qs.by_set[k]; return `<tr><td>${esc(name[k] || k)}</td><td class="num">${n(t.items)}</td><td class="num">${n(t.exact_substring)}/${n(t.items)}</td><td class="num">${pct(t.topic?.supported, 0)}</td><td class="num">${pct(t.intent?.supported, 0)}</td><td class="num">${pct(t.severity?.supported, 0)}</td><td class="num">${pct(t.all_three_supported, 0)}</td></tr>`; }).join("") +
      `</table></div>` +
      keys.filter((k) => qs.by_set[k].same_sentence_as_human !== undefined).map((k) => `<p class="small">${esc(name[k] || k)}: the model quoted Eason's evidence sentence in ${n(qs.by_set[k].same_sentence_as_human)} of ${n(qs.by_set[k].items)} reviews (multi-sentence reviews: ${esc(qs.by_set[k].same_sentence_as_human_multi)}).</p>`).join("") +
      `<p class="small muted">Shares are “supported” verdicts; the full report, with every quote the judge did not accept, is <code>evals/quote_support/report.md</code>.</p>`;
  } else $("quotes").innerHTML = "<p class='muted'>Quote check not loaded yet.</p>";
  const v = e.verification_report;
  if (v && v.agreement) {
    const a = v.agreement;
    $("verify").innerHTML = `<p class="small muted"><span title="${esc(v.verifier_config)}">${esc(configName(v.verifier_config))}</span> relabelled a declared random sample of ${n(v.sample?.sample_size)} distinct texts without seeing the enricher's labels; code compared field by field.</p>` +
      agreeTable([["Topic", `${pct(a.topic.rate)} (${n(a.topic.agree)}/${n(a.topic.of)})`], ["Intent", `${pct(a.intent.rate)} (${n(a.intent.agree)}/${n(a.intent.of)})`], ["Severity exact", `${pct(a.severity.rate)} (${n(a.severity.agree)}/${n(a.severity.of)})`], ["Sentiment within ±0.5", pct(a.sentiment_within_tolerance.rate)], ["Verifier failures", n(v.verifier_failures)]]) +
      `<p class="small">Largest topic confusions (enricher → verifier): ${confusions(v.top_confusions?.topic)}</p>` +
      `<p class="small">Largest intent confusions: ${confusions(v.top_confusions?.intent)}</p>`;
  }
  const p = e.planted_error;
  $("planted").innerHTML = p ? `<p>Status: <span class="${p.status === "detected" ? "ok" : "bad"}">${esc(p.status)}</span></p>` + agreeTable([["Review", `<a href="#lookup/${esc(p.review_id)}" class="mono">${esc(p.review_id)}</a>`], ["Stored labels (unchanged)", labelsText(p.original)], ["Planted on a test copy", labelsText(p.planted)], ["Verifier's labels", labelsText(p.verifier)], ["Fields flagged after planting", esc((p.comparison_after || []).join(", ").replace(/_/g, " "))]]) : "<p class='muted'>not loaded</p>";
  const inj = e.injection;
  $("injection").innerHTML = inj ? `<p>${esc(inj.summary || `${inj.passed ?? ""} of ${(inj.cases || []).length} cases passed.`)}</p><div class="table-wrap"><table><tr><th>Case</th><th>Expectation</th><th>Result</th></tr>${(inj.cases || []).map((c) => `<tr><td class="mono">${esc(c.case_id)}</td><td>${esc(c.expectation)}</td><td class="${c.passed ? "ok" : "bad"}">${c.passed ? "pass" : "fail"} <span class="small">${esc(c.detail || "")}</span></td></tr>`).join("")}</table></div>` : "<p class='muted'>not loaded</p>";
  const sc = e.self_check, sf = e.self_check_full, rc = e.rank_check;
  const issuesText = (c) => Object.entries(c?.issue_counts || {}).map(([k, x]) => `${esc(k.replace(/_/g, " "))} ${n(x)}`).join(" · ") || "none";
  const declared = sc ? `<span class="${sc.status === "pass" ? "ok" : "bad"}">${esc(sc.status)}</span> · coverage ${sc.working_coverage_point_candidate} · ${n(sc.coverage?.valid_completed)} valid completed, ${n(sc.coverage?.quarantined)} quarantined, ${n(sc.coverage?.valid_cache_reuses)} valid cache reuses · checker issues: ${issuesText(sc)}` : "–";
  const full = sf ? `<span class="neutral">Disclosure, expected</span><span class="disclosure">The reference was built from all ${n(sf.coverage?.expected)} rows of the full file; ${n(sf.coverage?.missing)} of them are outside the declared ${n(sc?.coverage?.expected)}-row scope by design, so the checker counts them as missing (coverage ${sf.working_coverage_point_candidate}; status <code>${esc(sf.status)}</code>).</span><span class="small muted">Checker notes: ${issuesText(sf)}.</span>` : "–";
  $("checks").innerHTML = agreeTable([
    [`Course checker, reference = declared ${sc?.coverage?.expected ? n(sc.coverage.expected) + "-row " : ""}scope (the graded scope)`, declared],
    ["Ranking rebuilt from grading/ files", rc ? (rc.identical ? "<span class='ok'>identical</span>" : "<span class='bad'>different</span>") + ` (${n(rc.issues)} issues)` : "–"],
    [`Course checker, reference = full ${sf?.coverage?.expected ? n(sf.coverage.expected) + "-row " : ""}file (for disclosure)`, full]]);
}

// ---- run & cost ----------------------------------------------------------------------------------------
async function loadRun() {
  const r = await get("/run");
  const c = r.cost || {}, fr = c.final_run;
  const finalRows = fr ? [[`Final run (${fr.run_dir})`, `<strong>${usd(fr.billed_usd, 6)}</strong> billed API spend${fr.calls != null ? ` over ${n(fr.calls)} calls` : ""}` +
      (fr.api_equivalent_subscription_usd != null ? `; Claude Pro calls priced at API rates: ${usd(fr.api_equivalent_subscription_usd, 4)} API-equivalent (<em>not billed</em>, never added to spend)` : "") +
      (fr.cost_per_1000_input_rows_usd != null ? `; ${usd(fr.cost_per_1000_input_rows_usd, 4)} billed per 1,000 rows` : "") +
      (fr.wall_clock_s != null ? `; ${hms(fr.wall_clock_s)} wall clock (${n(Math.round(fr.wall_clock_s))} s) over ${n(fr.invocations)} invocations` : "")]] : [];
  $("cost").innerHTML = agreeTable([...finalRows,
    ["Billed API spend recorded (all runs)", c.billed_api_spend_recorded_usd != null ? `${usd(c.billed_api_spend_recorded_usd, 4)}${c.budget_usd != null ? ` of the ${usd(c.budget_usd)} project cap` : ""}` : "–"],
    ["100-review pilot: cold run", c.pilot_cold != null ? usd(c.pilot_cold, 6) : "–"], ["100-review pilot: warm run", c.pilot_warm != null ? `${usd(c.pilot_warm, 6)} (${n(c.pilot_warm_new_enrichment_calls)} new enrichment calls)` : "–"]]) +
    (c.per_run ? `<details><summary class="small">Billed spend per run directory</summary><div class="table-wrap"><table><tr><th>Run</th><th class="num">Calls</th><th class="num">Billed</th></tr>${Object.entries(c.per_run).map(([k, v]) => `<tr><td class="mono small">${esc(k)}</td><td class="num">${n(v.calls)}</td><td class="num">${usd(v.billed_usd, 4)}</td></tr>`).join("")}</table></div></details>` : "") +
    `<p class="small muted">Claude Pro (claude -p) calls are not billed per call; their API-equivalent value is reported separately (cost/report.md).</p>`;
  const b = r.checkpoint_before, a = r.checkpoint_after;
  $("checkpoints").innerHTML = agreeTable([["Before interruption", b ? `${n(b.completed_ids_count)} completed IDs saved when the run stopped (${esc(prettyStop(b.status, b.stop_reason))})` : "–"],
    ["After resume", a ? `${n(a.completed_ids_count)} completed IDs (${esc(a.status)})` : "–"],
    ["Rule", "the resumed invocation sent only pending reviews; no completed ID was re-sent under the same label_config"]]);
  const metas = r.recording_meta || (r.recordings || []).map((name) => ({name, markers: []}));
  $("recordings").innerHTML = metas.length ? metas.map((m) => `<div class="cast-caption"><strong>${esc(m.name.replace(/^(\d+)-/, "$1 · ").replace(/-/g, " "))}</strong>${m.duration_s ? ` <span class="muted small">(${hms(m.duration_s)} recorded)</span>` : ""}` +
      (m.markers?.length ? `<ul class="small">${m.markers.map(([t, label]) => `<li><span class="mono">${clock(t)}</span> ${esc(label)}</li>`).join("")}</ul>` : "") +
      `${m.transcript ? `<p class="small"><a href="${API}/recording/${encodeURIComponent(m.name)}/transcript" target="_blank" rel="noopener">Plain-text transcript</a></p>` : ""}</div><div class="cast" id="cast-${esc(m.name)}"></div>`).join("") : "<p class='muted'>No recording loaded.</p>";
  metas.forEach((m) => {
    try {
      AsciinemaPlayer.create(`${API}/recording/${encodeURIComponent(m.name)}`, $(`cast-${m.name}`),
        {idleTimeLimit: 2, speed: 2, fit: "width", cols: m.width || 140, rows: Math.min(20, m.height || 20), preload: true, markers: (m.markers || []).map(([t, label]) => [t, label])});
    } catch (e) { $(`cast-${m.name}`).textContent = "player failed to load; use the transcript link"; }
  });
  const hist = r.run_summary?.history || [];
  const detail = Object.fromEntries((fr?.invocations_detail || []).map((x) => [x.run_id, x]));
  const did = (h) => {
    const x = detail[h.run_id];
    if (!x) return "–";
    const stages = Object.keys(x.stage_seconds || {});
    return x.enrichment_calls ? `${n(x.enrichment_calls)} enrichment calls; stages: ${esc(stages.join(", "))}`
      : `regenerated outputs only (${esc(stages.filter((s) => s !== "ingest").join(", "))}); no enrichment calls`;
  };
  $("history").innerHTML = "<tr><th>Invocation</th><th>Phase</th><th>Status</th><th>What it did</th><th class='num'>Wall clock</th><th class='num'>Completed IDs saved</th></tr>" +
    hist.map((h) => `<tr><td class="mono small">${esc(h.run_id)}</td><td>${esc(h.phase)}</td><td>${esc(prettyStop(h.status, h.stop_reason))}</td><td class="small">${did(h)}</td><td class="num" title="${esc(h.wall_clock_s)} s">${hms(h.wall_clock_s)}</td><td class="num">${n(h.completed_ids_saved)}</td></tr>`).join("");
  const regen = hist.filter((h) => detail[h.run_id] && !detail[h.run_id].enrichment_calls && h.phase === "resume");
  $("history-note").textContent = regen.length ? `${regen.length} later resume invocations made no enrichment calls: every review was already labelled, so they only rebuilt outputs from the saved labels (issue naming, ranking, memo, export), for example after a prompt or code fix.` : "";
  $("trace-md").innerHTML = r.trace_example_md ? md(r.trace_example_md) : "<p class='muted'>not loaded</p>";
}

// ---- lookup / trace ------------------------------------------------------------------------------------
let lastSearch = null;
async function runSearch(params, offset) {
  const p = new URLSearchParams(params);
  p.set("limit", "25"); p.set("offset", String(offset));
  $("s-results").innerHTML = "<p class='muted'>Searching…</p>";
  let r;
  try { r = await get(`/reviews?${p}`); } catch (e) { $("s-results").innerHTML = `<p class="bad">${esc(e.message)}</p>`; return; }
  lastSearch = {params, offset};
  const from = r.total ? offset + 1 : 0, to = offset + r.reviews.length;
  const pager = `<div class="pager"><span class="small muted">${n(r.total)} matching reviews · showing ${n(from)}–${n(to)}</span><button type="button" data-page="-1" ${offset <= 0 ? "disabled" : ""}>← Previous 25</button><button type="button" data-page="1" ${to >= r.total ? "disabled" : ""}>Next 25 →</button></div>`;
  $("s-results").innerHTML = pager + `<div class="table-wrap"><table><tr><th>Review</th><th>Labels</th><th>Text</th></tr>` +
    r.reviews.map((x) => `<tr class="click" data-review="${esc(x.review_id)}"><td class="mono small">${esc(x.review_id.slice(0, 8))}…<br>${esc(x.review_timestamp.slice(0, 10))}</td><td>${x.status === "completed" ? `${esc(x.topic)}/${esc(x.subtopic)}<br>${esc(x.intent)} · sev ${x.severity}` : `<span class="warn">${esc(String(x.reason || "").replace(/_/g, " "))}</span>`}</td><td>${esc(x.review_text)}</td></tr>`).join("") + "</table></div>" +
    (r.total > 25 ? pager : "");
}
$("s-results").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-page]");
  if (b && lastSearch) runSearch(lastSearch.params, Math.max(0, lastSearch.offset + 25 * Number(b.dataset.page)));
});
$("search").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const id = $("s-id").value.trim(), text = $("s-q").value.trim(), intent = $("s-intent").value, topic = $("s-topic").value;
  if (id && !text && !intent && !topic) return go("lookup", id);
  const p = {};
  if (text) p.q = text;
  if (intent) p.intent = intent;
  if (topic) p.topic = topic;
  runSearch(p, 0);
});
document.addEventListener("click", (ev) => {
  const t = ev.target.closest("[data-review]");
  if (t && !ev.target.closest("a[href]")) { ev.preventDefault(); go("lookup", t.dataset.review); }
});
async function traceReview(id) {
  const box = $("trace");
  box.classList.remove("hidden");
  box.innerHTML = "<p class='muted'>Loading trace…</p>";
  $("s-id").value = id;
  try {
    const d = await get(`/reviews/${encodeURIComponent(id)}`);
    const r = d.review, v = d.verification, m = d.issue;
    if (r.review_id !== id) { $("s-id").value = r.review_id; try { history.replaceState(null, "", `#lookup/${r.review_id}`); } catch (e) { /* ignore */ } }
    const vc = d.verification_comparison;
    box.innerHTML = `<h3>Trace: review <code>${esc(r.review_id)}</code> <a class="small" href="#lookup/${esc(r.review_id)}" title="Link to this trace">link</a></h3><div class="steps">
      <div class="step"><b>1 · Source row (ingest, code)</b>${esc(r.review_text)}<br><span class="small muted">${esc(r.review_timestamp)} · ${esc(r.review_rating)}★ (metadata only) · ${n(r.review_likes)} helpful votes · app ${esc(r.app_version || "missing")} · row hash <code>${esc(r.source_sha256.slice(0, 16))}…</code></span></div>
      <div class="step"><b>2 · Enrichment (model + code)</b>${r.status === "completed" ? `topic <strong>${esc(r.topic)}</strong> / ${esc(r.subtopic)} · intent <strong>${esc(r.intent)}</strong> · severity <strong>${r.severity}</strong> · sentiment ${r.sentiment} · needs_review ${r.needs_review ? "yes" : "no"} · labelled by ${esc(r.labeled_by)}<br>evidence quote: “${esc(r.evidence_quote)}”<br><span class="small muted">entities (code): ${esc((r.entities || []).join(", ") || "–")} · <span title="label_config ${esc(r.label_config)}">labels: ${esc(labelSummary(r.label_config))}</span>${d.cache_source ? ` · exact-text reuse of <a href="#lookup/${esc(d.cache_source.review_id)}">${esc(d.cache_source.review_id)}</a>` : ""}</span>` : `<span class="warn">quarantined: ${esc(String(r.reason || "").replace(/_/g, " "))}</span>`}</div>
      <div class="step"><b>3 · Independent verification</b>${v ? (v.status === "completed" ? `verifier: ${esc(v.topic)} · ${esc(v.intent)} · severity ${v.severity} · confidence ${esc(v.confidence)}<br>${Object.entries(vc || {}).map(([k, ok]) => `${esc(k.replace(/_/g, " "))} ${ok ? "<span class='ok'>agrees</span>" : "<span class='bad'>differs</span>"}`).join(" · ")}` : `failed: ${esc(v.reason || "")}`) : "<span class='muted'>not in the declared verification sample</span>"}</div>
      <div class="step"><b>4 · Issue membership (code)</b>${m ? `<a href="#issues/${esc(m.issue_id)}"><code>${esc(m.issue_id)}</code></a> ${esc(m.name || "")}` : "<span class='muted'>not grouped (only complaint and cancellation reviews are ranked)</span>"}</div>
      <div class="step"><b>5 · Ranking (code)</b>${m ? `rank <strong>${m.rank}</strong> · ${n(m.complaint_count)} complaints · priority (severity sum) ${n(m.priority_score)} · mean severity ${Number(m.mean_severity).toFixed(2)}` : "–"}</div>
      <div class="step"><b>6 · Memo</b>${d.claims.length ? d.claims.map((c) => `<a class="chip" href="#recommendation/${esc(c.claim_id)}">${esc(c.claim_id)}</a> ${esc(c.metric.replace(/_/g, " "))} = ${esc(c.value)}`).join(" · ") : "<span class='muted'>no memo claim for this issue</span>"}<br><span class="small">${d.quoted_in_memo_evidence ? "Quoted in the memo evidence pack." : "Not quoted in the memo evidence pack."}${d.cited_by_memo ? " Cited by the memo." : ""}</span></div>
    </div>`;
  } catch (e) {
    box.innerHTML = `<p class="bad">${esc(e.message)}</p>`;
  }
  box.scrollIntoView({behavior: "smooth", block: "start"});
}

// ---- boot ----------------------------------------------------------------------------------------------
(function boot() {
  get("/health").then((h) => {  // in parallel with the first tab, not before it
    $("health").textContent = `backend ✓ · ${h.database} · ${n(h.review_rows)} review rows`;
    $("health").classList.add("ok");
    if (h.run?.loaded_at) $("loaded-at").textContent = ` (loaded ${utc(h.run.loaded_at)})`;
  }).catch(() => {
    $("health").textContent = "backend unavailable";
    $("health").classList.add("bad");
  });
  route();
  if (parseHash().tab !== "overview") ensureLoaded("overview").catch(() => {});  // fills the header line
  tabHint();
})();
