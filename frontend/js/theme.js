"use strict";
// Colour theme: applied before the page paints (this script is loaded in <head> without defer),
// remembered per browser, and switchable from the selector added to the page footer.
(() => {
  const THEMES = [
    ["teal", "Teal (original)"],
    ["indigo", "Indigo + amber"],
    ["forest", "Forest green + coral"],
    ["navy", "Navy + crimson"],
  ];
  const KEY = "mediroute_theme";
  const read = () => {
    try { return window.localStorage.getItem(KEY) || "teal"; } catch (error) { return "teal"; }
  };
  const apply = (name) => document.documentElement.setAttribute("data-theme", name);
  apply(read());

  document.addEventListener("DOMContentLoaded", () => {
    const label = document.createElement("label");
    label.className = "theme-picker";
    label.textContent = "Colour theme ";
    const select = document.createElement("select");
    select.setAttribute("aria-label", "Colour theme");
    THEMES.forEach(([value, text]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      select.append(option);
    });
    select.value = read();
    select.addEventListener("change", () => {
      apply(select.value);
      try { window.localStorage.setItem(KEY, select.value); } catch (error) { /* private mode: not remembered */ }
    });
    label.append(select);
    const footer = document.querySelector("footer .container") || document.querySelector("footer");
    if (footer) {
      const wrap = document.createElement("div");
      wrap.append(label);
      footer.append(wrap);
    } else {
      label.classList.add("theme-picker-floating");
      document.body.append(label);
    }
  });
})();
