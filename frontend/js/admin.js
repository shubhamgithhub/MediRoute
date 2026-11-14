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
    user_selected: "User selected", emergency_rule: "Red flag → Emergency", multi_area_general_medicine: "Several body areas → General Medicine", none: "No Step 1"
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

    if (ev.stage) detail.append(section("Step 1: how the speciality was worked out (algorithms, weights, scores)", "calculator", step1Algorithms(events)));

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

  // ------------------------------------------------------------ Step 1 algorithms (what each stage computed)
  const V1_PARAMS_FALLBACK = {
    keyword_search: "TF-IDF, 0.5 x word (1-2 words) + 0.5 x character (3-5 letters), cosine", keyword_min_score: 0.25,
    meaning_search: "all-MiniLM-L6-v2 sentence embeddings, cosine", meaning_min_score: 0.45, results_per_search: 20,
    rrf_k: 60, entries_kept_per_phrase: 8, runner_up_weight: 0.1, weak_evidence_weight: 0.5,
  };
  const table = (headers, rows, cls = "data-table s1-table") => {
    const t = el("table", cls);
    const hr = el("tr");
    headers.forEach((h) => hr.append(el("th", "", h)));
    t.append(hr);
    rows.forEach((cells) => {
      const tr = el("tr");
      cells.forEach((c) => {
        const td = el("td", c && c.cls ? c.cls : "");
        const v = c && typeof c === "object" && !(c instanceof Node) ? c.v : c;
        if (v instanceof Node) td.append(v); else td.textContent = v === undefined || v === null || v === "" ? "—" : String(v);
        tr.append(td);
      });
      t.append(tr);
    });
    const wrap = el("div", "table-wrap");
    wrap.append(t);
    return wrap;
  };
  const stageBox = (n, title, kind, ...children) => {
    const box = el("div", `s1-stage s1-${kind}`);
    const h = el("div", "s1-stage-head");
    h.append(el("span", "s1-num", n), el("strong", "", title), el("span", `s1-kind s1-kind-${kind}`, kind === "llm" ? "LLM" : kind === "ml" ? "ML search (code)" : "code"));
    box.append(h, ...children);
    return box;
  };
  const io = (label, value) => {
    const d = el("div", "s1-io");
    d.append(el("div", "s1-io-label", label), value instanceof Node ? value : pre(value));
    return d;
  };
  const rankScore = (pair) => (pair ? `#${pair[0]} (${Number(pair[1]).toFixed(3)})` : "—");

  function step1Algorithms(events) {
    const one = (stage, pred = () => true) => events.find((e) => e.stage === stage && pred(e)) || {};
    const input = one("input");
    const ev = one("evidence");
    const evCall = one("llm_call", (e) => e.stage_for === "evidence_extraction");
    const v1 = one("vote", (e) => e.voter === "V1_lookup");
    const v2 = one("vote", (e) => e.voter === "V2_llm");
    const v2Call = one("llm_call", (e) => e.stage_for === "specialty_vote");
    const judge = one("judge");
    const judgeCalls = events.filter((e) => e.stage === "llm_call" && e.stage_for === "judge");
    const dec = events.filter((e) => e.stage === "decision").slice(-1)[0] || {};
    const out = el("div", "s1-algos");
    const text = (input.patient_text && input.patient_text.text) || "(patient text hidden)";

    // 3 · evidence ------------------------------------------------------------
    const evParts = [el("p", "muted", "Why: pull the medical words out of free text so the lookup searches only those, not the noise around them.")];
    if (evCall.stage) {
      const inBox = el("div");
      inBox.append(el("p", "patient-text", text), collapsible("Full prompt sent (fixed instruction + the message)", pre(evCall.prompt || "(not logged)")));
      evParts.push(io(`Input to the LLM · prompt ${evCall.prompt_version} · ${evCall.model} · temperature ${evCall.options ? evCall.options.temperature : "—"} · ${evCall.prompt_tokens ?? "?"} tokens`, inBox));
      evParts.push(io(`LLM output · ${ms(evCall.duration_ms)}`, evCall.raw_response || (evCall.ok ? "(empty)" : `failed: ${evCall.error}`)));
    } else {
      evParts.push(el("p", "muted", "No LLM call: evidence came from the keyword list only (LLM unavailable)."));
    }
    const checks = ev.checks;
    if (checks && checks.length) {
      evParts.push(el("div", "s1-io-label", "Code check: a phrase is kept only if at least 60% of its words are in the text (exact, abbreviation or close spelling ≥ 0.85)"),
        table(["phrase", "type", "words found in text", "result"], checks.map((c) => [
          c.phrase, c.kind.replace("_", " "), c.share === null || c.share === undefined ? "—" : `${Math.round(c.share * 100)}%`,
          { v: c.kept ? "kept" : `dropped: ${c.why}`, cls: c.kept ? "s2-plus" : "s1-drop" }])));
    } else {
      const box = el("div");
      box.append(el("div", "muted", "kept (per-phrase check details are recorded for requests from 13 Nov 2026)"));
      Object.entries(ev.kept || {}).forEach(([k, p]) => { if (p.length) box.append(el("div", "", `${k.replace("_", " ")}: ${p.join(", ")}`)); });
      evParts.push(box);
    }
    evParts.push(el("div", "s1-io-label", "Keyword matches added by code (everyday terms found word for word)"), chips((ev.kept || {}).keyword_matches));
    evParts.push(el("div", "s1-io-label", "→ Phrases given to the lookup voter (body parts only if nothing else was found)"), chips(ev.routing_phrases));
    out.append(stageBox("3", "Evidence: LLM call 1 + code check", "llm", ...evParts));

    // 3b · body areas (code) ------------------------------------------------------
    const ac = one("area_check");
    if (ac.stage) {
      const acParts = [el("p", "muted", "Why: a message with only symptoms from several body areas (no named condition or procedure) is asked which area matters most; “More than one / whole body” or “Not sure” → General Medicine. Neighbour pairs (reflux, cold, migraine) count as one area.")];
      acParts.push(table(["symptom", "tag"], (ac.tags || []).map((x) => [x.phrase, x.tag])));
      acParts.push(el("p", "", `Named diagnosis or procedure: ${(ac.named || []).join(", ") || "none"} · areas: ${(ac.areas || []).join(", ") || "none"} · counted as ${ac.count} (threshold ${ac.threshold})${(ac.merged || []).length ? ` · merged: ${ac.merged.join("; ")}` : ""}`));
      acParts.push(el("p", ac.multi_area ? "s1-drop" : "muted", ac.multi_area ? "→ several body areas: ask (or General Medicine after the answer)" : "→ one area or a named condition: normal voting"));
      out.append(stageBox("3b", "Body areas: code", "code", ...acParts));
    }

    // 4a · V1 lookup ------------------------------------------------------------
    if (v1.stage) {
      const d = v1.details || {};
      const p = d.params || V1_PARAMS_FALLBACK;
      const parts = [el("p", "muted", "Why: an independent check against fixed medical data (ICD-10-CM via AHRQ CCSR, CGHS procedures, everyday terms). No LLM.")];
      const steps = el("ol", "s1-steps");
      [
        `Clean the phrase: generic words removed ("problem in my stomach" → "stomach").`,
        `Keyword search: ${p.keyword_search}; keep the top ${p.results_per_search} scoring ≥ ${p.keyword_min_score}.`,
        `Meaning search: ${p.meaning_search}; keep the top ${p.results_per_search} scoring ≥ ${p.meaning_min_score}.`,
        `Fuse the two lists by rank (Reciprocal Rank Fusion): score = Σ 1 / (${p.rrf_k} + rank). An entry found by both searches near the top scores highest (max ≈ ${(2 / (p.rrf_k + 1)).toFixed(4)}). Keep the top ${p.entries_kept_per_phrase}.`,
        `Each phrase votes once: its best entry's speciality gets the full score; its other specialities count ×${p.runner_up_weight}. Symptom / weak terms count ×${p.weak_evidence_weight}.`,
        "Add the votes over all phrases. General Medicine is dropped if any specialist matched. Highest total = V1's answer.",
      ].forEach((t) => steps.append(el("li", "", t)));
      parts.push(steps);
      const hits = (v1.hits || []).filter((h) => h.entry_id);
      const phrases = d.phrases && d.phrases.length ? d.phrases : [...new Set(hits.map((h) => h.phrase))].map((ph) => ({ phrase: ph }));
      phrases.forEach((ph) => {
        const rows = hits.filter((h) => h.phrase === ph.phrase).map((h) => [
          `${h.entry_id}: ${h.text}`, h.specialty, h.evidence_type || "—", rankScore(h.kw), rankScore(h.emb),
          { v: Number(h.score).toFixed(4), cls: "num" },
          { v: h.weak ? `×${p.weak_evidence_weight}` : "×1", cls: "num" },
        ]);
        const head = el("div", "s1-phrase-head");
        head.append(el("strong", "", `“${ph.phrase}”`));
        if (ph.query && ph.query !== ph.phrase) head.append(el("span", "muted", ` searched as “${ph.query}”`));
        if (ph.keyword_results !== undefined) head.append(el("span", "muted", ` · keyword search found ${ph.keyword_results}, meaning search found ${ph.meaning_results}`));
        parts.push(head, table(["lookup entry", "→ speciality", "type", "keyword rank (score)", "meaning rank (score)", "RRF score", "weight"], rows));
        if (ph.added) {
          parts.push(el("div", "s1-added", `Vote of this phrase: ${(ph.added || []).map(([s, v], i) => `${s} +${v.toFixed(4)}${i === 0 ? " (best, full)" : ` (×${p.runner_up_weight})`}`).join(" · ")}${ph.general_only ? " · general symptom: only General Medicine counted" : ""}`));
        }
      });
      const totals = d.totals || (v1.top3 || []);
      if (totals.length) {
        const max = Math.max(...totals.map(([, v]) => v), 1e-9);
        const rows = totals.map(([s, v], i) => {
          const bar = el("div", "s1-bar");
          const fill = el("span");
          fill.style.width = `${(v / max) * 100}%`;
          bar.append(fill);
          return [{ v: i === 0 ? `${s} ← V1 answer` : s, cls: i === 0 ? "s2-final" : "" }, { v: Number(v).toFixed(4), cls: "num" }, bar];
        });
        parts.push(el("div", "s1-io-label", `Totals (sum over phrases)${d.dropped_general_medicine ? " · General Medicine dropped because a specialist matched" : ""}`),
          table(["speciality", "total", ""], rows));
      }
      if (!v1.details) parts.push(el("p", "muted", "Search ranks and per-phrase votes are recorded for requests from 13 Nov 2026; older requests show only the fused scores."));
      out.append(stageBox("4a", "V1 lookup voter: keyword + meaning search, fused", "ml", ...parts));
    }

    // 4b · V2 LLM vote ----------------------------------------------------------
    if (v2.stage) {
      const parts = [el("p", "muted", "Why: an independent opinion. It reads the whole text and the speciality list (with route-here / not-here rules); it never sees the lookup or V1's answer.")];
      if (v2Call.stage) {
        const inBox = el("div");
        inBox.append(el("p", "patient-text", text), collapsible(`Full prompt sent (${(v2Call.prompt || "").length.toLocaleString()} characters: rules + every speciality + the message)`, pre(v2Call.prompt || "(not logged)")));
        parts.push(io(`Input to the LLM · prompt ${v2Call.prompt_version} · ${v2Call.model} · temperature ${v2Call.options ? v2Call.options.temperature : "—"} · ${v2Call.prompt_tokens ?? "?"} tokens${v2Call.parallel ? " · ran at the same time as LLM call 1" : ""}`, inBox));
        parts.push(io(`LLM output · ${ms(v2Call.duration_ms)}`, v2Call.raw_response || (v2Call.ok ? "(empty)" : `failed: ${v2Call.error}`)));
      }
      const h = (v2.hits || [])[0] || {};
      parts.push(el("div", "s1-io-label", "Code check: the answer must be a name on the list (or “Unclear” = abstain); alternatives not on the list are ignored"));
      parts.push(table(["rank", "speciality", "score used"], (v2.top3 || []).map(([s, sc], i) => [i + 1, i === 0 ? `${s} ← V2 answer` : s, { v: sc, cls: "num" }])));
      parts.push(el("p", "muted", `Scores are by rank (1st 1.0, 2nd 0.5, 3rd 0.33): the LLM returns a choice, not a probability (temperature 0). Words it cited: ${(h.evidence_terms || []).join(", ") || "—"}.${v2.note ? " Note: " + v2.note + "." : ""}`));
      out.append(stageBox("4b", "V2 AI voter: LLM call 2", "llm", ...parts));
    }

    // 5 · judge (only on disagreement) -----------------------------------------
    if (judge.stage) {
      const parts = [el("p", "muted", "Runs only when V1 and V2 disagree. Asked twice with the two candidates in opposite order; both answers must match and pass the checks, else the patient is asked.")];
      parts.push(kv([
        ["Candidates", (judge.candidates || []).join(" vs ")],
        ["Answers (order A, order B)", (judge.choices || []).join(" · ") || "—"],
        ["Failed checks", (judge.failures || []).join("; ") || "none"],
        ["Quote from patient", judge.patient_quote || "—"],
        ["Result", judge.final ? `${judge.final} (${judge.status})` : judge.status],
        ["Cost", judge.cost ? `$${Number(judge.cost).toFixed(5)}` : "—"],
      ]));
      if ((judge.evidence_lines || []).length) parts.push(collapsible(`Evidence lines given to the judge (${judge.evidence_lines.length})`, pre(judge.evidence_lines)));
      judgeCalls.forEach((c, i) => parts.push(collapsible(`Judge call ${i + 1}: prompt and output`, pre(`${c.prompt || ""}\n\n--- output ---\n${c.raw_response || c.error || ""}`))));
      out.append(stageBox("5b", "AI judge: LLM calls 3 + 4", "llm", ...parts));
    }

    // 5 · decision rules ----------------------------------------------------------
    const RULES = [
      ["emergency_rule", "Red flag (chest pain with breathlessness / racing heart / dizziness, loss of sight, confusion, stroke signs…) → Emergency Medicine, before any LLM call"],
      ["multi_area_general_medicine", "Symptoms only, 2+ body areas, patient answered “More than one” or “Not sure” → General Medicine"],
      ["agreement", "V1 = V2 → that speciality"],
      ["patient_answer", "They differ, but the patient's body-area answer fits exactly one → that one"],
      ["judge", "They differ otherwise → AI judge (must pass all checks)"],
      ["lookup_only", "AI not available (error / no key) → V1 alone, with a notice"],
      ["clarification_required", "V2 says “Unclear”, no phrases, judge unsure, or General Medicine on the first try → ask the patient"],
      ["needs_user_choice", "Still unclear after the questions → offer a short list"],
      ["user_selected", "Patient picked from the list"],
    ];
    const taken = dec.method || (events.find((e) => e.stage === "response") || {}).decision;
    const rl = el("ol", "s1-rules");
    RULES.forEach(([m, t]) => { const li = el("li", m === taken ? "taken" : "", t); rl.append(li); });
    out.append(stageBox("5", "Decide: fixed rules, first match wins", "code", rl,
      el("p", "muted", `This request: ${decisionLabel[taken] || taken || "—"}${dec.selected_specialty ? ` → ${dec.selected_specialty}` : ""}. ${dec.reason || ""}`)));
    return out;
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
      + "the list is filled from the same state, then the rest of India (shown as separate groups). "
      + "If the area has none at all, hospitals in the area with a related speciality (specialty_fallbacks.csv) are shown as an extra group; the suggested speciality does not change.");
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
      const group = r.related_specialty
        ? `Related speciality in ${wf.city || "the chosen area"}: ${r.related_specialty} (no hospital there lists ${wf.step2_specialty || "the suggested one"}; specialty_fallbacks.csv)`
        : r.outside_area ? (r.area_group || "Outside the area") : `In ${wf.city || "the chosen area"}`;
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
