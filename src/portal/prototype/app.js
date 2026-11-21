(() => {
  const $ = s => document.querySelector(s);
  const root = document.documentElement;
  const LOCALES = { de: "de-CH", fr: "fr-CH", it: "it-CH", en: "en-GB" };

  // ---------- i18n ----------
  // Die Texte stehen in i18n/<sprache>.json. Das Deutsch im HTML ist nur der Fallback ohne JavaScript.
  const dicts = {};
  let lang = window.INITIAL_LANG || "de";
  let dict = {};
  let manifest = null;

  // Als Datei geöffnet (file://) darf der Browser keine JSON-Dateien nachladen.
  // Dann liest die Seite dieselben Daten aus data.js (erzeugt mit src/portal/build_data.py).
  const isFile = location.protocol === "file:";
  let bundle = null;
  const loadBundle = () => bundle || (bundle = new Promise((resolve, reject) => {
    if (window.PORTAL_DATA) return resolve(window.PORTAL_DATA);
    const sc = document.createElement("script");
    sc.src = "data.js";
    sc.onload = () => window.PORTAL_DATA ? resolve(window.PORTAL_DATA) : reject(new Error("data.js leer"));
    sc.onerror = () => reject(new Error("data.js fehlt"));
    document.head.appendChild(sc);
  }));
  const loadJson = (path, pick) => isFile
    ? loadBundle().then(pick)
    : fetch(path, { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });

  // tr: Übersetzung oder undefined; t: mit Platzhaltern, notfalls der Schlüssel.
  const tr = key => dict[key] ?? dicts.de?.[key];
  const t = (key, vars = {}) => (tr(key) ?? key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
  const loadDict = l => dicts[l]
    ? Promise.resolve(dicts[l])
    : loadJson(`i18n/${l}.json`, b => b.i18n[l]).then(d => { if (!d) throw new Error("keine Texte"); return (dicts[l] = d); });

  const fmtSize = b => {
    const nf = new Intl.NumberFormat(LOCALES[lang], { maximumFractionDigits: 1 });
    return b >= 1e9 ? nf.format(Math.round(b / 1e8) / 10) + " GB" : b >= 1e6 ? nf.format(Math.round(b / 1e6)) + " MB" : nf.format(Math.max(1, Math.round(b / 1e3))) + " KB";
  };
  const fmtDate = d => new Date(d).toLocaleDateString(LOCALES[lang], { day: "numeric", month: "long", year: "numeric" });

  function applyStatic() {
    root.lang = lang;
    // Fehlt ein Text, bleibt der deutsche Fallback aus dem HTML stehen.
    if (tr("meta.title")) document.title = tr("meta.title");
    if (tr("meta.description")) document.querySelector('meta[name="description"]').content = tr("meta.description");
    document.querySelectorAll("[data-i18n]").forEach(el => { const v = tr(el.dataset.i18n); if (v != null) el.innerHTML = v; });
    document.querySelectorAll("[data-i18n-attr]").forEach(el => {
      el.dataset.i18nAttr.split(";").forEach(pair => {
        const [attr, key] = pair.split(":");
        const v = tr(key);
        if (v != null) el.setAttribute(attr, v);
      });
    });
    document.querySelectorAll("#langSwitch button").forEach(b => b.setAttribute("aria-pressed", b.dataset.lang === lang));
  }

  // ---------- Downloads ----------
  const thumbs = { vektor: "img/vgl-vektor.jpg", pixel: "img/vgl-raster.jpg", luftbild: "img/vgl-luftbild.jpg",
    routen: ["img/vgl-vektor.jpg", "img/vgl-raster.jpg", "img/vgl-luftbild.jpg"] };   // Overlay: drei Karten nebeneinander
  let regionShapes = null;   // regions.json: Zellflächen der Download-Gebiete und Landesgrenze (build_regions.py)
  const dlIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/></svg>';
  const fmtScale = n => "1:" + new Intl.NumberFormat(LOCALES[lang]).format(n);
  const groupOf = p => manifest.groups.find(g => g.id === p.group) || {};
  const fmtMonth = d => new Date(d).toLocaleDateString(LOCALES[lang], { month: "long", year: "numeric" });
  const srcTitle = s => (dict[`source.${s.id}`] ?? s.title);
  const srcLabel = s => [srcTitle(s), s.edition || (s.date ? fmtMonth(s.date) : "")].filter(Boolean).join(" ");
  const fileUrl = f => manifest.baseUrl + f.name;

  const fileBtn = f => {
    let label = t(`dl.target.${f.target}`);
    if (f.parts) label += " · " + t("dl.part", { n: f.part, total: f.parts });
    const title = `${f.name}\nSHA-256: ${f.sha256}` + (f.os ? `\n${t("dl.os")}` : "");
    const cls = f.target === "info" ? "fbtn small" : f.primary ? "fbtn primary" : "fbtn";
    return `<a class="${cls}" href="${fileUrl(f)}" download title="${title}" aria-label="${t("dl.aria", { title: label, size: fmtSize(f.size) })}">${dlIcon}${label} <span class="sz">${fmtSize(f.size)}</span></a>`;
  };

  const docIcon = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4M9 13h6M9 17h6"/></svg>';
  // README, Lizenz und Quellstand liegen je Release auf dem Download-Server (Pfade relativ zu baseUrl), nicht auf GitHub.
  const docUrl = path => manifest.baseUrl + path.split("/").map(encodeURIComponent).join("/");
  const docLinks = p => {
    if (!p.docs) return "";
    const links = ["readme", "license", "sources"].filter(k => p.docs[k])
      .map(k => `<a href="${docUrl(p.docs[k])}" target="_blank" rel="noopener" title="${t("dl.docs.title")}">${t(`dl.docs.${k}`)}</a>`);
    return `<div class="doclinks">${docIcon}${links.join('<span aria-hidden="true">·</span>')}</div>`;
  };

  // Ältere Releases: nur die, die beim Bau des Manifests noch auf dem Download-Server lagen (make_release.py).
  const olderBlock = m => !(m.older && m.older.length) ? "" :
    `<details class="older"><summary>${t("dl.older")}</summary><p>${t("dl.olderNote")}</p>${m.older.map(o =>
      `<p><b>${t("dl.olderRelease", { release: o.release })}:</b> ${o.files.map(f =>
        `<a href="${o.baseUrl}${encodeURIComponent(f.name)}" download>${f.name}</a> (${fmtSize(f.size)})`).join(" · ")}${o.checksums ? ` · <a href="${o.baseUrl}${encodeURIComponent(o.checksums)}">SHA-256</a>` : ""}</p>`).join("")}</details>`;

  const zoomIcon = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/></svg>';
  // Optionaler Hinweis je Kartenart (i18n: group.<id>.highlight), z. B. der Massstabswechsel beim Zoomen.
  const highlight = g => { const v = tr(`group.${g.id}.highlight`); return v ? `<p class="highlight">${zoomIcon}<span>${v}</span></p>` : ""; };

  // BaseCamp (Computer) visuell getrennt vom Download fürs Gerät; das Paket umfasst immer die ganze Schweiz.
  const bcRow = p => {
    const bc = p.files.filter(f => f.target === "basecamp");
    // optionaler Hinweis je Produkt (i18n: product.<id>.bcNote), z. B. wenn es kein eigenes BaseCamp-Paket gibt
    const extra = tr(`product.${p.id}.bcNote`);
    if (!bc.length) return extra ? `<div class="bcrow"><span class="bclabel">${laptopIcon}<span>${extra}</span></span></div>` : "";
    const base = p.area === "regionen" || p.area === "haelften" ? t("dl.bcWhole") : t("dl.bcNote");
    const note = extra ? `${base}${/[.!?]$/.test(base) ? "" : "."} ${extra}` : base;
    return `<div class="bcrow"><span class="bclabel">${laptopIcon}<span>${note}</span></span>${bc.map(f => fileBtn(f)).join("")}</div>`;
  };
  const laptopIcon = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/></svg>';

  function productRow(p) {
    const chips = [];
    if (p.scale) chips.push(p.scale.min === p.scale.max ? fmtScale(p.scale.min) : `${fmtScale(p.scale.min)} – ${fmtScale(p.scale.max)}`);
    chips.push(t(`dl.area.${p.area}`));
    if (p.fid) chips.push(`FID ${p.fid}`);
    let actions;
    let map = "";
    if (p.planned) {
      // Noch nicht gebaut: Eintrag zeigen, aber ohne Downloads und ohne Karte
      actions = `<span class="pending">${t("dl.soon")}</span>`;
    } else if (p.area === "regionen" || p.area === "haelften") {
      const regs = manifest.regions.filter(r => p.files.some(f => f.region === r.id));
      actions = `<select class="region-select" data-product="${p.id}" aria-label="${t("dl.region")}">
          ${regs.map(r => `<option value="${r.id}">${t(`region.${r.id}`)}</option>`).join("")}
        </select><span class="region-files" data-product="${p.id}"></span>`;
      map = regionMap(p);
    } else {
      actions = p.files.filter(f => f.target !== "basecamp").map(f => fileBtn(f)).join("");
      // Pixelkarte und Luftbild: auch die Varianten für die ganze Schweiz zeigen die Karte, alles markiert
      if (p.area === "schweiz" && ["pixel", "luftbild"].includes(p.group)) map = regionMap(p, true);
    }
    return `<li class="prod">
        <div>
          <div class="t">${t(`product.${p.id}.title`)}${p.experimental && !groupOf(p).experimental ? ` <span class="tag exp">${t("dl.experimental")}</span>` : ""}${p.planned ? ` <span class="tag plan">${t("dl.follows")}</span>` : ""}</div>
          <div class="s">${t(`product.${p.id}.subtitle`)}</div>
          <div class="chips">${chips.map(c => `<span class="chip">${c}</span>`).join("")}</div>
        </div>
        <div class="actions">${actions}</div>
        ${map}
        ${bcRow(p)}
        ${docLinks(p)}
      </li>`;
  }

  // Kleine Schweizerkarte: die tatsächlichen Zellflächen der Download-Gebiete (folgen dem Kachelgitter),
  // darüber die Landesgrenze. Ein Klick auf ein Gebiet wählt es aus.
  function regionMap(p, all = false) {
    if (!regionShapes) return "";
    const ids = all ? ["schweiz"] : [...new Set(p.files.map(f => f.region).filter(Boolean))];
    const paths = ids.filter(id => regionShapes.areas[id])
      .map(id => `<path d="${regionShapes.areas[id]}" data-region="${id}"${all ? ' class="on"' : ""}>${all ? "" : `<title>${t(`region.${id}`)}</title>`}</path>`).join("");
    const label = all ? t("dl.area.schweiz") : t("dl.map");
    return `<svg class="regmap${all ? " static" : ""}" data-product="${p.id}" viewBox="${regionShapes.viewBox}" role="img" aria-label="${label}">${paths}<path class="land" d="${regionShapes.outline}"/></svg>`;
  }
  function fillRegion(sel) {
    const p = manifest.products.find(x => x.id === sel.dataset.product);
    const files = p.files.filter(f => f.region === sel.value);
    document.querySelector(`.region-files[data-product="${p.id}"]`).innerHTML = files.map(f => fileBtn(f)).join("");
    document.querySelectorAll(`.regmap[data-product="${p.id}"] path[data-region]`).forEach(el => el.classList.toggle("on", el.dataset.region === sel.value));
  }

  function renderDownloads() {
    if (!manifest) return;
    const m = manifest;
    $("#dlMeta").textContent = t("dl.meta", { release: m.release, date: fmtDate(m.date) });
    // GitHub nur als Entwickler-Link (Quellcode); Lizenz vom Download-Server
    document.querySelectorAll(".gh").forEach(a => { if (m.repo) a.href = m.repo.url; });
    const lic = m.products.find(p => p.docs && p.docs.license);
    document.querySelectorAll(".lic").forEach(a => { if (lic) a.href = docUrl(lic.docs.license); });
    const prev = {};
    document.querySelectorAll(".region-select").forEach(s => prev[s.dataset.product] = s.value);

    $("#groups").innerHTML = m.groups.map(g => {
      const prods = m.products.filter(p => p.group === g.id);
      const tags = [
        g.recommended && `<span class="tag rec">${t("dl.recommended")}</span>`,
        g.experimental && `<span class="tag exp">${t("dl.experimental")}</span>`,
        g.planned && `<span class="tag plan">${t("dl.planned")}</span>`
      ].filter(Boolean).join("");
      const srcIds = [...new Set(prods.flatMap(p => p.sources || []))];
      const main = m.sources.filter(s => s.prominent && srcIds.includes(s.id));
      const srcline = main.length ? `<p class="srcline"><b>${t("dl.sources")}:</b> ${main.map(srcLabel).join(" · ")}</p>` : "";
      const list = g.planned || !prods.length
        ? `<p class="soon">${t("dl.soon")}</p>`
        : `<ul class="prods">${prods.map(productRow).join("")}</ul>`;
      return `<article class="group${g.recommended ? " recommended" : ""}">
          <div class="thumb${g.planned ? " planned" : ""}${Array.isArray(thumbs[g.id]) ? " tri" : ""}" ${typeof thumbs[g.id] === "string" ? `data-bg="${thumbs[g.id]}"` : ""}>${Array.isArray(thumbs[g.id]) ? thumbs[g.id].map(u => `<span data-bg="${u}"></span>`).join("") : ""}<div class="tags">${tags}</div></div>
          <div class="main">
            <div class="body"><h3>${t(`group.${g.id}.title`)}</h3><p class="desc">${t(`group.${g.id}.description`)}</p>${highlight(g)}${srcline}</div>
            ${list}
          </div>
        </article>`;
    }).join("");

    // Hintergrundbilder per CSSOM statt style-Attribut (CSP ohne 'unsafe-inline')
    document.querySelectorAll("#groups [data-bg]").forEach(el => el.style.backgroundImage = `url("${el.dataset.bg}")`);
    document.querySelectorAll(".region-select").forEach(sel => {
      if (prev[sel.dataset.product]) sel.value = prev[sel.dataset.product];
      fillRegion(sel);
      sel.addEventListener("change", () => fillRegion(sel));
    });
    document.querySelectorAll(".regmap:not(.static)").forEach(svg => svg.addEventListener("click", e => {
      const id = e.target.closest("path")?.dataset.region;
      const sel = document.querySelector(`.region-select[data-product="${svg.dataset.product}"]`);
      const opt = [...sel.options].find(o => o.value === id);
      if (opt) { sel.value = opt.value; fillRegion(sel); }
    }));

    const minor = m.sources.filter(s => !s.prominent);
    $("#dlFoot").innerHTML = `<div class="fineprint">
        <p><b>${t("dl.finePrint")}:</b> ${minor.map(srcLabel).join(" · ")}</p>
        <p>${t("dl.fat32")}</p>
        <p>${t("dl.attribution")}</p>
        <p>${t("dl.checksums", { file: m.baseUrl + m.checksums, name: m.checksums })}</p>
        ${olderBlock(m)}
      </div>`;
  }

  async function setLang(l, { persist = false } = {}) {
    try { dict = await loadDict(l); lang = l; }
    catch { dict = dicts.de || {}; }
    applyStatic();
    renderDownloads();
    root.classList.remove("i18n-wait");
    if (persist) {
      try { localStorage.setItem("lang", l); } catch {}
      const url = new URL(location.href);
      url.searchParams.set("lang", l);
      history.replaceState(null, "", url);
    }
  }

  document.querySelectorAll("#langSwitch button").forEach(b =>
    b.addEventListener("click", () => setLang(b.dataset.lang, { persist: true })));

  // Sicherheitsnetz: Seite nie dauerhaft ausgeblendet lassen.
  setTimeout(() => root.classList.remove("i18n-wait"), 1500);

  Promise.all([
    loadDict("de").catch(() => ({})),
    loadJson("manifest.json", b => b.manifest).then(m => (manifest = m)).catch(() => null),
    loadJson("regions.json", b => b.regions).then(r => (regionShapes = r)).catch(() => null)
  ]).then(() => setLang(lang)).then(() => {
    if (!manifest) $("#dlMeta").textContent = tr("dl.unavailable") ?? "Release-Informationen nicht verfügbar.";
  });

  // ---------- Lightbox ----------
  const lb = $("#lightbox");
  const closeLb = () => lb.classList.remove("open");
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeLb(); });
  document.querySelectorAll(".shot").forEach(f => f.addEventListener("click", () => {
    lb.querySelector("img").src = f.querySelector("img").src;
    lb.querySelector("img").alt = f.querySelector("img").alt;
    lb.querySelector("p").textContent = f.querySelector("figcaption").textContent;
    lb.classList.add("open");
  }));
  lb.addEventListener("click", e => { if (e.target === lb || e.target.tagName === "BUTTON") closeLb(); });

  // ---------- Vergleich ----------
  const cmp = $("#compare");
  cmp.querySelector("input").addEventListener("input", e => cmp.style.setProperty("--pos", e.target.value + "%"));

  // ---------- Tabs ----------
  document.querySelectorAll('[role="tab"]').forEach(tab => tab.addEventListener("click", () => {
    document.querySelectorAll('[role="tab"]').forEach(x => x.setAttribute("aria-selected", x === tab));
    document.querySelectorAll("[data-panel]").forEach(p => p.hidden = p.dataset.panel !== tab.dataset.tab);
  }));

  // ---------- Theme ----------
  try { const th = localStorage.getItem("theme"); if (th) root.dataset.theme = th; } catch {}
  $("#themeToggle").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch {}
  });
})();

  // Datenschutz: Link im Footer klappt den Abschnitt auf
  const openPriv = () => { if (location.hash === "#datenschutz") { const d = document.getElementById("priv"); d.open = true; d.scrollIntoView(); } };
  addEventListener("hashchange", openPriv); openPriv();
