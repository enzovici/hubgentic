// Progressive enhancement only: every page works without JS.
document.addEventListener("click", (e) => {
  const copy = e.target.closest("[data-copy]");
  if (copy) {
    const src = document.querySelector(copy.dataset.copy);
    const text = src ? (src.value ?? src.textContent) : copy.dataset.copy;
    navigator.clipboard.writeText(text.trim()).then(() => {
      const old = copy.textContent;
      copy.textContent = "Copied";
      setTimeout(() => (copy.textContent = old), 1400);
    });
    return;
  }
  const open = e.target.closest("[data-open]");
  if (open) {
    document.getElementById(open.dataset.open)?.showModal();
    return;
  }
  const close = e.target.closest("[data-close]");
  if (close) {
    close.closest("dialog")?.close();
    return;
  }
  const navToggle = e.target.closest("[data-nav-toggle]");
  if (navToggle) {
    document.querySelector(".shell")?.classList.toggle("nav-open");
    return;
  }
  const tab = e.target.closest("[role=tab]");
  if (tab) {
    const list = tab.closest("[role=tablist]");
    list.querySelectorAll("[role=tab]").forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
  }
  // Close workspace menu when clicking elsewhere.
  document.querySelectorAll("details[open][data-menu]").forEach((d) => {
    if (!d.contains(e.target)) d.removeAttribute("open");
  });
});

// Confirm destructive actions.
document.addEventListener("submit", (e) => {
  const msg = e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});

// Explorer: show a pending state while the federated query runs.
document.querySelectorAll("form[data-pending]").forEach((form) => {
  form.addEventListener("submit", () => {
    const btn = form.querySelector("button[type=submit]");
    if (btn) {
      btn.disabled = true;
      btn.textContent = form.dataset.pending;
    }
  });
});

document.addEventListener("change", (e) => {
  if (e.target.matches("[data-autosubmit]")) e.target.form.requestSubmit();
});
