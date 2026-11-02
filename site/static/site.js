// Progressive enhancement only: every page works without JavaScript.
const header = document.querySelector("[data-hdr]");
const menuBtn = document.querySelector("[data-menu]");

function setMenu(open) {
  header?.classList.toggle("open", open);
  menuBtn?.setAttribute("aria-expanded", String(open));
}
menuBtn?.addEventListener("click", () => setMenu(!header.classList.contains("open")));
document.querySelectorAll(".nav a").forEach((a) => a.addEventListener("click", () => setMenu(false)));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") setMenu(false); });

const onScroll = () => header?.classList.toggle("scrolled", window.scrollY > 8);
onScroll();
window.addEventListener("scroll", onScroll, { passive: true });

// "Request early access" pre-ticks the matching interest in the contact form.
document.querySelectorAll("[data-interest]").forEach((link) => {
  link.addEventListener("click", () => {
    const box = document.querySelector(`input[name="interests"][value="${link.dataset.interest}"]`);
    if (box) box.checked = true;
  });
});

const form = document.querySelector("[data-lead]");
if (form) {
  const button = form.querySelector("button[type=submit]");
  const label = button.textContent;
  // The server redirects back with ?form=error when it can't accept the request.
  if (new URLSearchParams(location.search).get("form") === "error") {
    form.querySelector("[data-form-error]").hidden = false;
  }
  form.addEventListener("submit", () => {
    button.disabled = true;
    button.textContent = button.dataset.sending;
  });
  // Coming back via the browser's back button restores a usable form.
  window.addEventListener("pageshow", () => {
    button.disabled = false;
    button.textContent = label;
  });
}
