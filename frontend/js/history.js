// My history (docs/design/user_history.md): the logged-in user's saved searches. Shown only after
// login; the backend returns only this user's entries.
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const account = window.MediRouteAccount;
  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const when = (iso) => {
    try { return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); } catch (e) { return iso; }
  };

  const list = $("#history-list");
  const status = $("#history-status");
  let openId = null;

  const renderDetail = (entry, holder) => {
    holder.replaceChildren();
    if (entry.request_text) {
      holder.append(el("h3", "", "What you asked"), el("p", "", entry.request_text));
    } else {
      holder.append(el("h3", "", "What you asked"), el("p", "history-meta", "Description not saved."));
    }
    const facts = [entry.city ? `City: ${entry.city}` : "", entry.language ? `Language: ${entry.language}` : ""].filter(Boolean);
    if (facts.length) holder.append(el("p", "history-meta", facts.join(" · ")));
    if ((entry.thread || []).length) {
      holder.append(el("h3", "", "Questions and your answers"));
      const ol = el("ol", "history-thread");
      entry.thread.forEach((t) => {
        const li = el("li");
        li.append(el("div", "q", t.question || "Question"), el("div", "", `Your answer: ${t.answer || "-"}`));
        ol.append(li);
      });
      holder.append(ol);
    }
    if (entry.specialty) {
      holder.append(el("h3", "", "Suggested speciality"));
      const p = el("p");
      p.append(el("span", "history-specialty", entry.specialty));
      if (entry.specialty_reason) p.append(document.createTextNode(` ${entry.specialty_reason}`));
      holder.append(p);
    }
    holder.append(el("h3", "", `Hospitals you chose (${entry.hospitals.length} of 3)`));
    const hs = el("div", "history-hospitals");
    entry.hospitals.forEach((h) => {
      const row = el("div", "history-hospital");
      const left = el("div");
      left.append(el("strong", "", h.name), el("small", "", [h.city, h.state].filter(Boolean).join(", ")));
      if (h.related_specialty) left.append(el("small", "", `Related speciality: ${h.related_specialty} (please confirm your treatment with the hospital)`));
      const right = el("div", "history-actions");
      if (h.website) {
        const a = el("a", "button button-small button-secondary", "Website");
        a.href = h.website; a.target = "_blank"; a.rel = "noopener noreferrer";
        right.append(a);
      }
      if (h.international_page) {
        const a = el("a", "button button-small button-secondary", "International patients");
        a.href = h.international_page; a.target = "_blank"; a.rel = "noopener noreferrer";
        right.append(a);
      }
      const remove = el("button", "account-link history-danger", "Remove");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`Remove ${h.name} from this saved search?`)) return;
        try {
          await account.api(`/api/history/${entry.id}/hospitals/${encodeURIComponent(h.hospital_id)}`, { method: "DELETE" });
          load();
        } catch (e) { window.alert(e.message); }
      });
      right.append(remove);
      row.append(left, right);
      hs.append(row);
    });
    holder.append(hs);

    const actions = el("div", "history-actions");
    const again = el("button", "button button-small button-primary", "Search again");
    again.type = "button";
    again.addEventListener("click", () => {
      // pre-fill the patient form with the saved request (the patient page reads this on ?edit=1)
      try {
        window.sessionStorage.setItem("mediroute_patient_request", JSON.stringify({
          requirement: entry.request_text || "", location: entry.city || "No preference",
          language: entry.language || "English", additionalPreference: "", reportName: [], reportSize: [], reportIds: [],
          timestamp: new Date().toISOString() }));
      } catch (e) { /* the form simply starts empty */ }
      window.location.href = "patient.html?edit=1";
    });
    const del = el("button", "button button-small button-secondary history-danger", "Delete this entry");
    del.type = "button";
    del.addEventListener("click", async () => {
      if (!window.confirm("Delete this saved search?")) return;
      try { await account.api(`/api/history/${entry.id}`, { method: "DELETE" }); openId = null; load(); }
      catch (e) { window.alert(e.message); }
    });
    actions.append(again, del);
    holder.append(actions);
  };

  const toggle = async (item, button, detail) => {
    const opening = button.getAttribute("aria-expanded") !== "true";
    list.querySelectorAll(".history-item").forEach((b) => b.setAttribute("aria-expanded", "false"));
    list.querySelectorAll(".history-detail").forEach((d) => { d.hidden = true; });
    openId = null;
    if (!opening) return;
    button.setAttribute("aria-expanded", "true");
    detail.hidden = false;
    detail.replaceChildren(el("p", "history-meta", "Loading…"));
    openId = item.id;
    try { renderDetail((await account.api(`/api/history/${item.id}`)).entry, detail); }
    catch (e) { detail.replaceChildren(el("p", "history-meta", e.message)); }
  };

  const load = async () => {
    const user = account.user() || await account.me();
    $("#history-login").hidden = Boolean(user);
    $("#history-account").hidden = !user;
    list.replaceChildren();
    if (!user) { status.textContent = ""; $("#history-empty").hidden = true; return; }
    $("#history-email").textContent = user.email;
    $("#history-country").textContent = user.country || "";
    status.textContent = "Loading…";
    let entries = [];
    try { entries = (await account.api("/api/history")).entries || []; }
    catch (e) { status.textContent = e.message; return; }
    status.textContent = entries.length ? `${entries.length} saved search${entries.length === 1 ? "" : "es"}` : "";
    $("#history-empty").hidden = entries.length > 0;
    entries.forEach((item) => {
      const li = el("li");
      const button = el("button", "history-item");
      button.type = "button";
      button.setAttribute("aria-expanded", "false");
      button.append(el("span", "history-meta", `${when(item.updated_at)}${item.city ? ` · ${item.city}` : ""}`),
        el("span", "history-text", item.request_text || "(description not saved)"));
      const line = el("span", "history-meta");
      if (item.specialty) line.append(el("span", "history-specialty", item.specialty), document.createTextNode(" "));
      line.append(document.createTextNode(item.hospitals.map((h) => `${h.name} (${h.city})`).join(" · ")));
      button.append(line);
      const detail = el("div", "history-detail");
      detail.hidden = true;
      button.addEventListener("click", () => toggle(item, button, detail));
      li.append(button, detail);
      list.append(li);
      if (openId === item.id) toggle(item, button, detail);
    });
  };

  $("#history-login-btn").addEventListener("click", async () => { if (await account.openDialog("login")) load(); });
  $("#history-delete-account").addEventListener("click", async () => {
    if (!window.confirm("Delete your account and all your saved searches? This cannot be undone.")) return;
    try { await account.api("/api/auth/me", { method: "DELETE" }); } catch (e) { window.alert(e.message); return; }
    window.location.href = "index.html";
  });
  account.onChange(() => load());
  load();
});
