"use strict";

// Admin: request history from /api/admin/requests (reads logs/step1_trace.jsonl). No auth yet.
document.addEventListener("DOMContentLoaded", () => {
  const API = "http://127.0.0.1:8000/api/admin/requests";
  const list = document.querySelector("#request-list");
  const detail = document.querySelector("#request-detail");
  const statsBox = document.querySelector("#admin-stats");
  const count = document.querySelector("#list-count");
  const q = document.querySelector("#filter-q");
  const decisionSel = document.querySelector("#filter-decision");
  const sourceSel = document.querySelector("#filter-source");
  const autoRefresh = document.querySelector("#auto-refresh");
  let selectedId = new URLSearchParams(window.location.search).get("id");
  let timer = null;

  // ------------------------------------------------------------ helpers (textContent only: logs hold user text)
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };
  const icon = (name) => { const i = document.createElement("i"); i.setAttribute("data-lucide", name); return i; };
  const badge = (text, cls) => el("span", `badge ${cls}`, text);
  const ms = (v) => (v === null || v === undefined ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`);
  const when = (ts) => {
    if (!ts) return "—";
    const d = new Date(ts);
    return isNaN(d) ? ts : d.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  const decisionLabel = {
    majority: "Majority (old)", agreement: "Voters agree", judge: "AI judge decided", lookup_only: "Lookup only", patient_answer: "Patient answer decided", clarification_required: "Asked a question", needs_user_choice: "List offered",
    user_selected: "User selected", none: "No Step 1"
  };
  const kv = (pairs) => {
    const dl = el("dl", "kv");
    pairs.forEach(([k, v]) => {
      dl.append(el("dt", "", k));
      const dd = el("dd");
      if (v instanceof Node) dd.append(v); else dd.textContent = v === undefined || v === null || v === "" ? "—" : String(v);
      dl.append(dd);
    });
    return dl;
  };
  const section = (title, iconName, ...children) => {
    const s = el("section", "detail-section");
    const h = el("h3");
    h.append(icon(iconName), document.createTextNode(` ${title}`));
    s.append(h, ...children);
    return s;
  };
  const chips = (items, cls = "chip") => {
    const box = el("div", "chips");
    (items || []).forEach((t) => box.append(el("span", cls, t)));
    if (!items || !items.length) box.append(el("span", "muted", "none"));
    return box;
  };
  const pre = (value) => el("pre", "code", typeof value === "string" ? value : JSON.stringify(value, null, 2));
  const collapsible = (summary, content) => {
    const d = el("details");
    d.append(el("summary", "", summary), content);
    return d;
  };
  const refreshIcons = () => { if (window.lucide) window.lucide.createIcons(); };

  // ------------------------------------------------------------ list
  async function loadList() {
    const params = new URLSearchParams({ limit: "300", q: q.value.trim(), decision: decisionSel.value, source: sourceSel.value });
    let data;
    try {
      const response = await fetch(`${API}?${params}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (error) {
      list.replaceChildren(el("p", "muted", `Could not load the history (${error.message}). Is the API running on port 8000?`));
      return;
    }
    renderStats(data.stats);
    count.textContent = `· ${data.stats.shown} of ${data.stats.total}`;
    list.replaceChildren();
    if (!data.requests.length) list.append(el("p", "muted", "No requests match."));
    data.requests.forEach((h) => list.append(renderRow(h)));
    if (selectedId) highlight(selectedId);
    refreshIcons();
  }

  function renderStats(stats) {
    statsBox.replaceChildren();
    const add = (label, value) => {
      const c = el("span", "stat-chip");
      c.append(document.createTextNode(`${label} `), el("strong", "", value));
      statsBox.append(c);
    };
    add("Requests", stats.total);
    Object.entries(stats.by_decision || {}).forEach(([k, v]) => add(decisionLabel[k] || k, v));
    add("Avg time", ms(stats.avg_total_ms));
  }

  function renderRow(h) {
    const row = el("button", "request-row");
    row.type = "button";
    row.dataset.id = h.request_id;
    const top = el("div", "row-top");
    top.append(el("span", "", when(h.ts)), el("span", "", ms(h.total_ms)));
    const text = el("div", "row-text", h.text ? h.text.replace(/\s+/g, " ") : (h.workflow ? "(no text: report only)" : "(empty)"));
    const bottom = el("div", "row-bottom");
    bottom.append(badge(decisionLabel[h.decision] || (h.complete ? "No Step 1" : "Incomplete"),
      `b-${h.decision || (h.complete ? "none" : "bad")}`));
    if (h.suggested_specialty) bottom.append(badge(h.suggested_specialty, "b-ok"));
    if (h.emergency) bottom.append(badge("Emergency", "b-emergency"));
    if (h.clarification_round) bottom.append(badge(`Round ${h.clarification_round}`, "b-muted"));
    if (h.workflow) {
      const wf = h.workflow;
      const cls = wf.outcome === "hospitals listed" ? "b-ok" : wf.outcome === "error" ? "b-bad" : "b-warn";
      bottom.append(badge(wf.outcome === "hospitals listed" ? `${wf.hospital_count} hospitals` : wf.outcome, cls));
    } else {
      bottom.append(badge("Step 1 only", "b-src"));
    }
    row.append(top, text, bottom);
    row.addEventListener("click", () => select(h.request_id));
    return row;
  }

  function highlight(id) {
    list.querySelectorAll(".request-row").forEach((r) => r.classList.toggle("is-selected", r.dataset.id === id));
  }

  async function select(id) {
    selectedId = id;
    highlight(id);
    history.replaceState(null, "", `?id=${encodeURIComponent(id)}`);
    detail.replaceChildren(el("p", "muted", "Loading…"));
    try {
      const response = await fetch(`${API}/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderDetail(await response.json());
    } catch (error) {
      detail.replaceChildren(el("p", "muted", `Could not load request ${id} (${error.message}).`));
    }
    refreshIcons();
  }

  // ------------------------------------------------------------ detail
  function renderDetail(data) {
    const s = data.summary;
    const events = data.step1_events || [];
    const wfEvents = data.workflow_events || [];
    const byStage = (stage) => events.filter((e) => e.stage === stage);
    const one = (stage) => byStage(stage)[0] || {};
    detail.replaceChildren();

    // header
    const head = el("div", "detail-head");
    head.append(el("h2", "", s.suggested_specialty ? `Suggested: ${s.suggested_specialty}` : (decisionLabel[s.decision] || "No Step 1 result")));
    const ids = el("div", "ids");
    ids.append(document.createTextNode(`${when(s.ts)} · ${s.source === "workflow" ? "Patient page (/api/patient-routing)" : "Step 1 only (/api/analyze)"} · request `),
      el("code", "", s.request_id));
    if (s.workflow) ids.append(document.createTextNode(" · workflow "), el("code", "", s.workflow.workflow_id));
    head.append(ids);
    detail.append(head);

    // timeline
    if (events.length) {
      const total = Math.max(...events.map((e) => e.t_ms || 0), 1);
      const tl = el("div", "timeline");
      let prev = 0;
      events.forEach((e) => {
        const r = el("div", "tl-row");
        const label = e.stage === "vote" ? e.voter : e.stage === "llm_call" ? `LLM: ${e.stage_for}` : e.stage;
        const bar = el("div", "tl-bar");
        const span = el("span", e.stage === "llm_call" ? "llm" : "");
        const start = e.stage === "llm_call"
          ? (e.started_t_ms ?? Math.max(0, (e.t_ms || 0) - (e.duration_ms || 0))) : prev;
        span.style.left = `${(start / total) * 100}%`;
        span.style.width = `${Math.max(0.6, (((e.t_ms || 0) - start) / total) * 100)}%`;
        bar.append(span);
        r.append(el("span", "", label), bar, el("span", "tl-ms", ms((e.t_ms || 0) - prev)));
        tl.append(r);
        prev = e.t_ms || 0;
      });
      detail.append(section(`Timeline · ${ms(s.total_ms)} total, ${ms(s.llm_ms)} in LLM calls`, "timer", tl,
        el("p", "muted", "Purple = LLM calls; teal = other stages. The right column is the time each stage added.")));
    }

    // input
    const input = one("input");
    const textBox = el("p", "patient-text", (input.patient_text && (input.patient_text.text ?? `hidden (${input.patient_text.length} chars, MEDIROUTE_LOG_PATIENT_TEXT=0)`)) || s.text || "(none)");
    detail.append(section("Input (after redaction)", "message-square-text", textBox, kv([
      ["Report text", input.report_chars ? `${input.report_chars} characters` : "none"],
      ["Clarification round", input.clarification_round ?? 0],
      ["Form answers", Object.keys(input.clarification_answers || {}).length ? JSON.stringify(input.clarification_answers) : "none"],
      ["Chosen by user", input.selected_specialty || "—"],
      ["Linked to (parent)", input.parent_request_id || "—"],
      ["Redactions", input.redactions ? Object.entries(input.redactions).filter(([, n]) => n).map(([k, n]) => `${k}: ${n}`).join(", ") || "none" : "—"],
    ])));

    // emergency
    const em = one("emergency_check");
    if (em.stage) {
      detail.append(section("Emergency check (fixed rules)", "siren",
        kv([["Result", em.is_emergency ? badge("EMERGENCY notice shown", "b-emergency") : "no red flags"],
            ["Rules matched", (em.matched_rules || []).join(", ") || "—"],
            ["Message", em.message || "—"]])));
    }

    // evidence
    const ev = one("evidence");
    if (ev.stage) {
      const box = el("div");
      Object.entries(ev.kept || {}).forEach(([kind, phrases]) => {
        box.append(el("div", "muted", kind.replace("_", " ")), chips(phrases));
      });
      box.append(el("div", "muted", "dropped (not found in the text, or an identifier)"),
        chips((ev.dropped || []).map((d) => `${d.phrase}${d.matched_share !== null && d.matched_share !== undefined ? ` (${Math.round(d.matched_share * 100)}%)` : ""}`), "chip dropped"));
      box.append(el("div", "muted", "phrases searched by the lookup voter"), chips(ev.routing_phrases));
      detail.append(section(`Evidence · ${ev.method}`, "highlighter", box));
    }

    // votes
    const votes = byStage("vote");
    const summary = one("votes_summary");
    if (votes.length) {
      const grid = el("div", "votes-grid");
      votes.forEach((v) => {
        const top1 = v.top3 && v.top3.length ? v.top3[0][0] : null;
        const chosen = summary.best_match || (one("decision") || {}).selected_specialty;
        const card = el("div", `vote-card${top1 && top1 === chosen ? " agrees" : ""}`);
        card.append(el("h4", "", v.voter), el("div", "method", `${v.method} · ${ms(v.ms)}`));
        card.append(el("div", "vote-top1", top1 || "abstained"));
        const ol = el("ol");
        (v.top3 || []).forEach(([name, score]) => ol.append(el("li", "", `${name} (${score})`)));
        card.append(ol);
        if (v.note) card.append(el("div", "note", v.note));
        const hits = (v.hits || []).filter((h) => h.entry_id);
        if (hits.length) {
          const table = el("table", "data-table");
          const thead = el("tr");
          ["phrase", "matched entry", "→ speciality", "score"].forEach((t) => thead.append(el("th", "", t)));
          table.append(thead);
          hits.slice(0, 8).forEach((h) => {
            const tr = el("tr");
            [h.phrase, `${h.entry_id}: ${h.text}`, h.specialty, h.score].forEach((t) => tr.append(el("td", "", t)));
            table.append(tr);
          });
          const wrap = el("div", "table-wrap");
          wrap.append(table);
          card.append(collapsible(`Top lookup matches (${hits.length})`, wrap));
        } else if (v.hits && v.hits[0] && v.hits[0].evidence_terms) {
          card.append(el("div", "muted", `LLM evidence terms: ${(v.hits[0].evidence_terms || []).join(", ") || "—"}`));
        }
        grid.append(card);
      });
      const tally = Object.entries(summary.tally || {}).map(([k, n]) => `${k}: ${n}`).join(" · ");
      detail.append(section("Votes", "vote", grid,
        el("p", "muted", (summary.agree !== undefined ? `Voters ${summary.agree ? "agree" : "disagree"}${one("judge").status ? ` · AI judge: ${one("judge").status}${one("judge").final ? " → " + one("judge").final : ""}` : ""}` : `Tally: ${tally || "—"} · best match: ${summary.best_match || "—"} (${summary.best_match_votes || 0} of 3)`))));
    }

    // LLM calls
    const calls = byStage("llm_call");
    if (calls.length) {
      const box = el("div");
      calls.forEach((c) => {
        const card = el("div", "llm-card");
        card.append(el("strong", "", `${c.stage_for} · ${c.model || "?"} · prompt ${c.prompt_version || "?"}`));
        const metrics = el("div", "llm-metrics");
        const hosted = c.provider === "openrouter";
        (hosted
          ? [["wall", ms(c.duration_ms)], ["wait for first token", ms(c.first_token_ms)],
             ["write answer", ms(c.generate_ms)], ["reasoning tokens", c.reasoning_tokens ?? "—"],
             ["reasoning", c.reasoning_enabled ? "on" : "off"], ["parallel", c.parallel ? "yes" : "no"],
             ["upstream", c.upstream_provider || "—"]]
          : [["wall", ms(c.duration_ms)], ["Ollama", ms(c.ollama_total_ms)], ["model load", ms(c.ollama_load_ms)],
             ["read prompt", ms(c.ollama_prompt_eval_ms)], ["write answer", ms(c.ollama_generate_ms)]])
        .concat([
         ["prompt tokens", c.prompt_tokens ?? "—"], ["output tokens", c.output_tokens ?? "—"],
         ["temperature", c.options ? c.options.temperature : "—"], ["ok", c.ok ? "yes" : `no: ${c.error}`]])
          .forEach(([k, v]) => metrics.append(el("span", "chip", `${k}: ${v}`)));
        card.append(metrics, el("div", "muted", "Raw response"), pre(c.raw_response || "(none)"),
          collapsible("Full prompt", pre(c.prompt || "(not logged)")));
        box.append(card);
      });
      detail.append(section("LLM calls", "cpu", box));
    }

    // decision
    const dec = byStage("decision").slice(-1)[0];
    if (dec) {
      detail.append(section("Decision", "gavel", kv([
        ["Method", badge(decisionLabel[dec.method] || dec.method, `b-${dec.method}`)],
        ["Selected speciality", dec.selected_specialty || "—"],
        ["Agreeing voters", (dec.agreeing_voters || []).join(", ") || "—"],
        ["Reason", dec.reason || "—"],
      ])));
    }

    // what was served
    const resp = one("response");
    const served = el("div", "served");
    if (s.suggested_specialty) served.append(el("p", "label", `Suggested speciality to search: ${s.suggested_specialty}`));
    served.append(kv([
      ["Decision returned", decisionLabel[resp.decision] || resp.decision || "—"],
      ["Evidence shown", (resp.evidence || []).join(", ") || "—"],
      ["Emergency notice", resp.emergency ? "shown" : "no"],
      ["Clarification form", resp.clarification_required ? "shown to the patient" : "no"],
      ["Speciality list offered", resp.user_choice_offered ? "yes" : "no"],
      ["Step 1 time", ms(resp.total_ms)],
    ]));
    if (s.workflow) {
      const wf = s.workflow;
      served.append(el("div", "muted", "Step 2 and final outcome (workflow)"));
      served.append(kv([
        ["Reports uploaded", `${wf.reports || 0} (${wf.report_status || "—"})`],
        ["Step 2 status", wf.step2_status || "not reached"],
        ["City filter", wf.city || "none"],
        ["Hospitals returned", wf.hospital_count ?? "—"],
        ["Outcome", wf.outcome],
      ]));
      if ((wf.top_hospitals || []).length) served.append(chips(wf.top_hospitals));
    } else {
      served.append(el("p", "muted", "Step 1 only (/api/analyze): no hospital search was run."));
    }
    detail.append(section("Output served", "send", served));

    if (s.workflow && s.workflow.step2_status) detail.append(section("Step 2: how hospitals were ranked", "list-ordered", step2Ranking(s.workflow)));

    if (wfEvents.length) {
      const table = el("table", "data-table");
      const head2 = el("tr");
      ["node", "time", "details"].forEach((t) => head2.append(el("th", "", t)));
      table.append(head2);
      wfEvents.forEach((e) => {
        const tr = el("tr");
        const { stage, request_id: _r, ts, ...rest } = e;
        [stage.replace("workflow:", ""), ts ? when(ts) : "—", JSON.stringify(rest)].forEach((t) => tr.append(el("td", "", t)));
        table.append(tr);
      });
      const wrap = el("div", "table-wrap");
      wrap.append(table);
      detail.append(section("Workflow nodes (LangGraph)", "workflow", wrap));
    }

    if ((data.related_rounds || []).length) {
      const box = el("div", "chips");
      data.related_rounds.forEach((rid) => {
        const b = el("button", "chip", rid);
        b.type = "button";
        b.addEventListener("click", () => select(rid));
        box.append(b);
      });
      detail.append(section("Other rounds of this search", "git-branch", box));
    }

    detail.append(section("Raw trace events", "braces", collapsible(`${events.length + wfEvents.length} events (JSON)`, pre([...events, ...wfEvents]))));
    refreshIcons();
  }

  // ------------------------------------------------------------ Step 2 ranking (weights + per-hospital scores)
  const BONUS_COLUMNS = [
    ["website_specialty", "Website speciality"], ["procedures", "Treatments"], ["verified", "Verified"],
    ["nabh", "NABH"], ["jci", "JCI"], ["international_patients", "Intl."], ["evidence", "Evidence"],
  ];
  const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(3));
  function step2Ranking(wf) {
    const w = wf.ranking_weights || {};
    const box = el("div", "s2");
    const steps = el("ol", "s2-criteria");
    const add = (title, text) => { const li = el("li"); li.append(el("strong", "", title), el("span", "", text)); steps.append(li); };
    add("1. Eligible hospitals",
      `Hospitals that list ${wf.step2_specialty || "the speciality"} (the hospital's website list, or the team list when the website list is missing): `
      + `${wf.specialty_candidates ?? "—"} hospitals; ${wf.location_candidates ?? "—"} of them in ${wf.city || "the chosen area"}.`);
    add("2. Relevance score (0 to 1)",
      `How close each hospital's profile is to the search text${wf.semantic_query ? ` “${wf.semantic_query}”` : ""} `
      + "(MiniLM sentence embeddings, cosine similarity with FAISS).");
    add("3. Bonus points (fixed weights, added to relevance)",
      `website speciality +${w.website_specialty ?? 0.04}; each requested treatment in the hospital's list +${w.procedure_each ?? 0.04} (max +${w.procedure_max ?? 0.08}); `
      + `verified details +${w.verified ?? 0.03} (partly +${w.partially_verified ?? 0.015}); NABH +${w.nabh ?? 0.02}; JCI +${w.jci ?? 0.02}; `
      + `international patient services +${w.international_patients ?? 0.02}; evidence quality up to +${w.evidence_max ?? 0.03} (High 0.03, Medium 0.02, Low 0.01). `
      + `All bonuses together are capped at +${w.bonus_cap ?? 0.2}.`);
    add("4. Order",
      "Final score = relevance + bonus, highest first. Hospitals in the chosen area come first; if fewer than 3 are in the area, "
      + "the list is filled from the same state, then the rest of India (shown as separate groups).");
    box.append(steps);

    const rows = wf.ranking || [];
    if (!rows.length) {
      box.append(el("p", "muted", (wf.top_hospitals || []).length
        ? "Score breakdown was not logged for this request (it is logged from 12 Nov 2026 onwards). Hospitals returned: " + wf.top_hospitals.join(", ")
        : "No hospitals were returned."));
      return box;
    }
    const table = el("table", "data-table s2-table");
    const head = el("tr");
    ["#", "Hospital", "Relevance", ...BONUS_COLUMNS.map(([, label]) => label), "Bonus", "Final score"].forEach((t) => head.append(el("th", "", t)));
    table.append(head);
    let lastGroup = null;
    rows.forEach((r) => {
      const group = r.outside_area ? (r.area_group || "Outside the area") : `In ${wf.city || "the chosen area"}`;
      if (group !== lastGroup) {
        const gr = el("tr", "s2-group");
        const td = el("td", "", group);
        td.colSpan = 4 + BONUS_COLUMNS.length + 1;
        gr.append(td);
        table.append(gr);
        lastGroup = group;
      }
      const tr = el("tr");
      tr.append(el("td", "", `#${r.position}`));
      const name = el("td");
      name.append(el("strong", "", r.name || "—"), el("div", "muted", [r.city, r.specialty_evidence ? `speciality from ${r.specialty_evidence}` : ""].filter(Boolean).join(" · ")));
      if ((r.matched_procedures || []).length) name.append(el("div", "muted", "matched: " + r.matched_procedures.join(", ")));
      tr.append(name, el("td", "num", fmt(r.semantic_score)));
      BONUS_COLUMNS.forEach(([key]) => {
        const v = (r.bonus_breakdown || {})[key];
        tr.append(el("td", v ? "num s2-plus" : "num s2-zero", v ? `+${Number(v).toFixed(3)}` : "0"));
      });
      tr.append(el("td", "num", `+${fmt(r.business_bonus)}`), el("td", "num s2-final", fmt(r.final_score)));
      table.append(tr);
    });
    const wrap = el("div", "table-wrap");
    wrap.append(table);
    box.append(wrap);
    return box;
  }

  // ------------------------------------------------------------ wiring
  let debounce = null;
  q.addEventListener("input", () => { window.clearTimeout(debounce); debounce = window.setTimeout(loadList, 250); });
  decisionSel.addEventListener("change", loadList);
  sourceSel.addEventListener("change", loadList);
  document.querySelector("#refresh-button").addEventListener("click", () => { loadList(); if (selectedId) select(selectedId); });
  autoRefresh.addEventListener("change", () => {
    window.clearInterval(timer);
    if (autoRefresh.checked) timer = window.setInterval(loadList, 5000);
  });

  loadList().then(() => { if (selectedId) select(selectedId); });
  refreshIcons();
});
