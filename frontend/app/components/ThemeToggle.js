"use client";
/**
 * Light / dark switch.
 * Until the user clicks, the site follows the system setting.
 * The choice is saved in localStorage and applied by a tiny script in layout.js
 * before the page paints, so there is no flash of the wrong theme.
 */
function currentTheme() {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function ThemeToggle() {
  function toggle() {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* storage blocked: still works for this visit */ }
  }

  return (
    <button className="icon-btn" onClick={toggle} aria-label="Toggle light and dark theme" title="Toggle theme">
      <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden>
        <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
      </svg>
    </button>
  );
}
