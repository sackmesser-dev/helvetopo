// Wird synchron im <head> geladen (CSP ohne 'unsafe-inline').
// Sprache früh bestimmen: ?lang= > gespeicherte Wahl > Browsersprache > Englisch.
// Deutsch steht direkt im HTML; andere Sprachen blenden die Seite bis zum Übersetzen kurz aus.
window.LANGS = ["de", "fr", "it", "en"];
window.pickLang = () => {
  const ok = l => l && LANGS.includes(l) ? l : null;
  let stored = null;
  try { stored = localStorage.getItem("lang"); } catch {}
  const fromUrl = ok(new URLSearchParams(location.search).get("lang"));
  const fromBrowser = (navigator.languages || [navigator.language || ""])
    .map(l => ok(String(l).toLowerCase().slice(0, 2))).find(Boolean);
  return fromUrl || ok(stored) || fromBrowser || "en";
};
window.INITIAL_LANG = pickLang();
document.documentElement.lang = INITIAL_LANG;
if (INITIAL_LANG !== "de") document.documentElement.classList.add("i18n-wait");
