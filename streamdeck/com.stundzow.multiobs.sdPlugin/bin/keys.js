"use strict";
// Dessin des touches en SVG (144 × 144). En haut, le bandeau de l'OBS piloté : sa couleur et son nom
// (ou « TOUS » sur les couleurs des instances concernées). En dessous, l'état, toujours dans les mêmes
// couleurs : rouge = enregistre, orange = en pause, vert = allumé / actif, gris = éteint.
// Chargé par le plugin (Node) et par la fenêtre de réglages (navigateur, pour les pictos).
(function (root) {
  const C = {
    off: "#1c1d22",
    offInk: "#5b606d",
    idle: "#2a2c34",
    ink: "#ffffff",
    soft: "#c9ccd6",
    muted: "#8a8f9c",
    rec: "#e5243b",
    pause: "#f5a30a",
    pauseInk: "#2a1c00",
    on: "#1d9f48",
    vcam: "#0a8dd0",
    blue: "#476bd7",
    alert: "#ffcc33",
    message: "#3a1118",
    grey: ["#6b7080", "#5b6273", "#4e5566", "#3c404d", "#2d3039", "#22242b"],
  };
  // Couleurs d'une action selon son état (touche « Action OBS »).
  const TONES = {
    idle: { bg: C.idle, ink: C.ink, accent: C.rec },
    on: { bg: C.on, ink: C.ink, accent: C.ink },
    rec: { bg: C.rec, ink: C.ink, accent: C.ink },
    pause: { bg: C.pause, ink: C.pauseInk, accent: C.pauseInk },
    vcam: { bg: C.vcam, ink: C.ink, accent: C.ink },
    dim: { bg: C.idle, ink: C.muted, accent: C.muted },
    off: { bg: C.off, ink: C.offInk, accent: "#5c2a33" },
  };
  const FONT = 'font-family="Segoe UI" font-weight="bold"';
  const BAND = 40;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  }

  // Largeur approximative d'un texte en gras (Segoe UI), pour choisir une taille qui tient.
  function textWidth(s, size) {
    let w = 0;
    for (const ch of String(s)) {
      if ("il.,:;!|'I".includes(ch)) w += 0.3;
      else if ("mwMW".includes(ch)) w += 0.92;
      else if (ch === " ") w += 0.27;
      else if (/[0-9]/.test(ch)) w += 0.57;
      else if (ch === ch.toUpperCase() && ch !== ch.toLowerCase()) w += 0.68;
      else w += 0.56;
    }
    return w * size;
  }

  function fit(s, max, width, min = 13) {
    let size = max;
    while (size > min && textWidth(s, size) > width) size -= 1;
    let txt = String(s);
    while (txt.length > 2 && textWidth(txt, size) > width) txt = txt.slice(0, -2) + "…";
    return { txt, size };
  }

  function text(s, x, y, size, color, extra = "") {
    return `<text x="${x}" y="${y}" font-size="${size}" ${FONT} fill="${color}" text-anchor="middle"${extra}>${esc(s)}</text>`;
  }

  // Un nom sur une ligne s'il reste lisible, sinon sur deux (« Caméra principale du live »).
  function nameLines(name, cx, y1, y2, single, max2, width, color) {
    const one = fit(name, single, width);
    const words = String(name).split(" ");
    if (one.size >= Math.min(single, 18) || words.length < 2) return text(one.txt, cx, y2, one.size, color);
    let best = 1;
    let bestDiff = Infinity;
    for (let i = 1; i < words.length; i++) {
      const diff = Math.abs(textWidth(words.slice(0, i).join(" "), 10) - textWidth(words.slice(i).join(" "), 10));
      if (diff < bestDiff) [best, bestDiff] = [i, diff];
    }
    const a = fit(words.slice(0, best).join(" "), max2, width);
    const b = fit(words.slice(best).join(" "), max2, width);
    const size = Math.min(a.size, b.size);
    return text(fit(a.txt, size, width).txt, cx, y1, size, color) + text(fit(b.txt, size, width).txt, cx, y2, size, color);
  }

  function formatTime(ms, hours) {
    const t = Math.max(0, Math.floor((ms || 0) / 1000));
    const h = Math.floor(t / 3600);
    const m = Math.floor(t / 60) % 60;
    const s = t % 60;
    const p = (n) => String(n).padStart(2, "0");
    if (hours) return `${p(h)}:${p(m)}:${p(s)}`;
    return h ? `${h}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
  }

  // ---------------------------------------------------------------- pictos (boîte de 48)
  function glyph(name, cx, cy, size, color, accent) {
    const k = size / 48;
    const t = `transform="translate(${(cx - 24 * k).toFixed(2)} ${(cy - 24 * k).toFixed(2)}) scale(${k.toFixed(4)})"`;
    const line = `fill="none" stroke="${color}" stroke-linecap="round" stroke-linejoin="round"`;
    const eye = `<path d="M3 24 C10 12.5 16.5 9 24 9 C31.5 9 38 12.5 45 24 C38 35.5 31.5 39 24 39 C16.5 39 10 35.5 3 24 Z" ${line} stroke-width="4"/>`;
    const speaker = `<path d="M5 18 H13 L24 9 V39 L13 30 H5 Z" fill="${color}" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>`;
    let g = "";
    switch (name) {
      case "rec":
        g = `<circle cx="24" cy="24" r="20" ${line} stroke-width="4.5"/><circle cx="24" cy="24" r="11.5" fill="${accent || C.rec}"/>`;
        break;
      case "stop":
        g = `<rect x="10" y="10" width="28" height="28" rx="5" fill="${color}"/>`;
        break;
      case "pause":
        g = `<rect x="10" y="8" width="10" height="32" rx="3" fill="${color}"/><rect x="28" y="8" width="10" height="32" rx="3" fill="${color}"/>`;
        break;
      case "play":
        g = `<path d="M15 9 L39 24 L15 39 Z" fill="${color}" stroke="${color}" stroke-width="4" stroke-linejoin="round"/>`;
        break;
      case "power":
        g = `<path d="M24 5 V23" ${line} stroke-width="5"/><path d="M33.2 12.9 A16 16 0 1 1 14.8 12.9" ${line} stroke-width="5"/>`;
        break;
      case "camera":
        g = `<rect x="3" y="12" width="30" height="24" rx="6" fill="${color}"/><path d="M35 21 L45 14.5 V33.5 L35 27 Z" fill="${color}" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>`;
        break;
      case "eye":
        g = `${eye}<circle cx="24" cy="24" r="7.5" fill="${color}"/>`;
        break;
      case "eyeoff":
        g = `${eye}<circle cx="24" cy="24" r="7.5" fill="${color}"/><path d="M7 41 L41 7" ${line} stroke-width="4.5"/>`;
        break;
      case "scene":
        g = `<rect x="4" y="7" width="40" height="28" rx="5" ${line} stroke-width="4"/><path d="M20 14.5 L30 21 L20 27.5 Z" fill="${color}" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/><path d="M15 42 H33" ${line} stroke-width="4"/>`;
        break;
      case "filter":
        g = `<path d="M5 8 H43 L28 25 V39 L20 43 V25 Z" ${line} stroke-width="4"/>`;
        break;
      case "speaker":
        g = `${speaker}<path d="M30.5 17.5 A9 9 0 0 1 30.5 30.5 M36 12 A16.5 16.5 0 0 1 36 36" ${line} stroke-width="4"/>`;
        break;
      case "speakeroff":
        g = `${speaker}<path d="M31 18 L43 30 M43 18 L31 30" ${line} stroke-width="4.5"/>`;
        break;
      case "live":
        g = `<circle cx="24" cy="24" r="5.5" fill="${color}"/><path d="M15.5 15.5 A12 12 0 0 0 15.5 32.5 M32.5 15.5 A12 12 0 0 1 32.5 32.5 M9 9 A21 21 0 0 0 9 39 M39 9 A21 21 0 0 1 39 39" ${line} stroke-width="4"/>`;
        break;
      case "photo":
        g = `<path d="M5 15 H14 L18 9 H30 L34 15 H43 V39 H5 Z" ${line} stroke-width="4"/><circle cx="24" cy="27" r="7" ${line} stroke-width="4"/>`;
        break;
      case "tap":
        g = `<rect x="4" y="4" width="40" height="40" rx="9" ${line} stroke-width="4"/><circle cx="16" cy="24" r="5" fill="${color}"/><rect x="25" y="20" width="14" height="8" rx="4" fill="${color}"/>`;
        break;
      case "none":
        g = `<path d="M14 24 H34" ${line} stroke-width="5"/>`;
        break;
      default:
        return "";
    }
    return `<g ${t}>${g}</g>`;
  }

  // ---------------------------------------------------------------- bandeau
  function band(m) {
    const b = m.band || {};
    const out = [];
    const side = m.alert || m.recDot ? 24 : 8;   // place des pastilles à gauche (alerte) et à droite (rec)
    if (b.all) {
      // Une bande par instance concernée par la touche ; atténuée si cette instance est éteinte.
      const cols = (b.colors && b.colors.length ? b.colors : [{ color: C.grey[1] }])
        .map((c) => (typeof c === "string" ? { color: c } : c));
      const w = 144 / cols.length;
      cols.forEach((c, i) => {
        const x = (i * w).toFixed(2);
        out.push(`<rect x="${x}" y="0" width="${(w + 0.5).toFixed(2)}" height="${BAND}" fill="${c.color}"/>`);
        if (c.dim || b.dim) out.push(`<rect x="${x}" y="0" width="${(w + 0.5).toFixed(2)}" height="${BAND}" fill="#000000" fill-opacity="0.58"/>`);
      });
      out.push(`<rect x="38" y="7" width="68" height="26" rx="13" fill="#000000" fill-opacity="0.5"/>`);
      out.push(text("TOUS", 72, 27.5, 19, C.ink));
    } else {
      const s = b.shades && b.shades.length === 6 ? b.shades : C.grey;
      const top = b.dim ? s[4] : s[1];
      const bottom = b.dim ? s[5] : s[2];
      out.push(`<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${top}"/><stop offset="1" stop-color="${bottom}"/></linearGradient></defs>`);
      out.push(`<rect x="0" y="0" width="144" height="${BAND}" fill="url(#bg)"/>`);
      const width = 144 - 2 * side;
      const one = fit(b.name || "?", 27, width);
      out.push(one.size >= 18 ? text(one.txt, 72, 20 + one.size * 0.36, one.size, b.dim ? "#d6d8de" : C.ink)
        : nameLines(b.name || "?", 72, 17, 34, 27, 17, width, b.dim ? "#d6d8de" : C.ink));
    }
    out.push(`<rect x="0" y="${BAND}" width="144" height="2" fill="#000000" fill-opacity="0.4"/>`);
    if (m.alert) {
      out.push(`<path d="M13 8 L25 31 H1 Z" fill="${C.alert}" stroke="#1a1a1a" stroke-width="1.5" stroke-linejoin="round"/>`);
      out.push(text("!", 13, 29, 16, "#1a1a1a"));
    }
    if (m.recDot) {
      // Pastille REC (blanc + rouge : visible même sur un bandeau rouge), elle clignote.
      out.push(`<circle cx="131" cy="20" r="9" fill="#ffffff"/>`);
      if (m.blink !== false) out.push(`<circle cx="131" cy="20" r="5.5" fill="${C.rec}"/>`);
    }
    return out.join("");
  }

  // ---------------------------------------------------------------- corps
  function body(color) {
    return `<rect x="0" y="${BAND + 2}" width="144" height="${142 - BAND}" fill="${color}"/>`;
  }

  function iconLabel(bg, name, ink, label, labelColor, accent) {
    const f = fit(label, 23, 128);
    return body(bg) + glyph(name, 72, 81, 46, ink, accent) + text(f.txt, 72, 133, f.size, labelColor || ink);
  }

  function lines(bg, l1, l2, color) {
    const a = fit(l1, 22, 134);
    if (!l2) return body(bg) + text(a.txt, 72, 101, a.size, color);
    const b = fit(l2, 22, 134);
    return body(bg) + text(a.txt, 72, 87, a.size, color) + text(b.txt, 72, 117, b.size, color);
  }

  function timecodeBody(bg, head, digits, ink) {
    const size = digits.length <= 5 ? 46 : digits.length <= 7 ? 37 : 33;
    return body(bg) + head + text(digits, 72, 115 - (46 - size) * 0.25, size, ink);
  }

  function recHead(m, ink) {
    // « ● REC » : le point clignote ; « ❚❚ PAUSE » dessiné en rectangles.
    if (m.rec === "recording") {
      return (m.blink !== false ? `<circle cx="47" cy="63" r="7.5" fill="${ink}"/>` : `<circle cx="47" cy="63" r="6.5" fill="none" stroke="${ink}" stroke-width="2"/>`)
        + text("REC", 80, 70, 20, ink);
    }
    return `<rect x="34" y="55" width="5.5" height="16" rx="1.5" fill="${ink}"/><rect x="43" y="55" width="5.5" height="16" rx="1.5" fill="${ink}"/>`
      + text("PAUSE", 85, 70, 20, ink);
  }

  function bar(p, color, track) {
    const w = Math.max(0, Math.min(1, p)) * 144;
    return `<rect x="0" y="136" width="144" height="8" fill="${track || "#ffffff"}" fill-opacity="0.16"/><rect x="0" y="136" width="${w.toFixed(1)}" height="8" fill="${color}"/>`;
  }

  // Appui long : un cercle blanc grandit depuis le centre jusqu'à couvrir toute la touche (sans
  // toucher au bandeau). Sous le cercle, la même touche en négatif : fond blanc, texte et pictos
  // sombres, donc toujours lisibles. Masque SVG : affiché par le Qt du logiciel Stream Deck (6.8).
  function luminance(hex) {
    const n = parseInt(hex.slice(1), 16);
    return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  }

  function inverted(content) {
    return content
      .replace(/(fill|stroke)="(#[0-9a-fA-F]{6})"/g, (all, attr, c) => (luminance(c) > 0.5 ? `${attr}="#1c1d22"` : all))
      .replace(/<rect x="0" y="42" width="144" height="102" fill="#[0-9a-fA-F]{6}"/g, '<rect x="0" y="42" width="144" height="102" fill="#ffffff"')
      .replace(/(<rect [^>]*rx="10" )fill="#[0-9a-fA-F]{6}"/g, '$1fill="#ffffff"');
  }

  function holdLayer(content, p) {
    const r = (Math.max(0, Math.min(1, p)) * 89).toFixed(1);
    return `<defs><mask id="hold" maskUnits="userSpaceOnUse" x="0" y="0" width="144" height="144">`
      + `<rect width="144" height="144" fill="#000000"/><circle cx="72" cy="93" r="${r}" fill="#ffffff"/></mask></defs>`
      + `<g mask="url(#hold)">${inverted(content)}</g>`;
  }

  function stateColors(m) {
    if (m.rec === "recording") return { bg: C.rec, ink: C.ink, dot: C.ink };
    if (m.rec === "paused") return { bg: C.pause, ink: C.pauseInk, dot: C.pauseInk };
    return { bg: C.idle, ink: C.ink, dot: C.rec };
  }

  function recordBody(m) {
    if (m.phase === "stopped") return iconLabel(C.off, "rec", C.offInk, "ÉTEINT", C.offInk, "#5c2a33");
    if (m.phase === "starting" || m.phase === "closing")
      return iconLabel(C.idle, "rec", C.muted, m.phase === "starting" ? "DÉMARRE" : "ARRÊT…", C.soft, "#8c3341");
    if (m.rec !== "idle") {
      const sc = stateColors(m);
      return timecodeBody(sc.bg, recHead(m, sc.ink), formatTime(m.recMs, m.hours), sc.ink);
    }
    if (m.remux != null) return iconLabel(C.idle, "rec", C.ink, `MP4 ${m.remux} %`, C.soft) + bar(m.remux / 100, C.blue);
    return iconLabel(C.idle, "rec", C.ink, "REC");
  }

  function pauseBody(m) {
    if (m.phase === "stopped") return iconLabel(C.off, "pause", C.offInk, "ÉTEINT", C.offInk);
    if (m.phase === "starting" || m.phase === "closing") return iconLabel(C.idle, "pause", C.muted, m.phase === "starting" ? "DÉMARRE" : "ARRÊT…", C.soft);
    if (m.rec === "idle") return iconLabel(C.idle, "pause", "#6f7480", "PAS DE REC", C.muted);
    const sc = stateColors(m);
    if (m.blocked && m.rec === "recording") return iconLabel(sc.bg, "pause", "#ffffff", "BLOQUÉE", sc.ink);
    return iconLabel(sc.bg, m.rec === "paused" ? "play" : "pause", sc.ink, formatTime(m.recMs, m.hours), sc.ink);
  }

  function powerBody(m) {
    switch (m.phase) {
      case "stopped": return iconLabel(C.off, "power", C.muted, "ÉTEINT", C.muted);
      case "starting": return iconLabel(C.idle, "power", C.soft, "DÉMARRE", C.soft);
      case "closing": return iconLabel(C.idle, "power", C.soft, "ARRÊT…", C.soft);
      case "partial": return iconLabel(C.idle, "power", C.ink, m.partial || "EN PARTIE");
      default: return iconLabel(C.on, "power", C.ink, "ALLUMÉ");
    }
  }

  function vcamBody(m) {
    if (m.phase === "stopped") return iconLabel(C.off, "camera", C.offInk, "ÉTEINT", C.offInk);
    if (m.phase === "starting" || m.phase === "closing") return iconLabel(C.idle, "camera", C.muted, m.phase === "starting" ? "DÉMARRE" : "ARRÊT…", C.soft);
    return m.vcam ? iconLabel(C.vcam, "camera", C.ink, "VCAM ON") : iconLabel(C.idle, "camera", C.soft, "VCAM OFF", C.muted);
  }

  function showBody(m) {
    if (m.band && m.band.all) return iconLabel(C.idle, "eye", C.ink, "MULTI OBS");
    if (m.phase === "stopped") return iconLabel(C.off, "eye", C.offInk, "ÉTEINT", C.offInk);
    return iconLabel(C.idle, "eye", C.ink, "VOIR OBS");
  }

  // Touche « Action OBS » : une action (toute la touche) ou deux (appui court à gauche, long à droite).
  function viewBody(v) {
    const t = TONES[v.tone] || TONES.idle;
    return body(t.bg) + glyph(v.glyph, 72, 73, 40, t.ink, t.accent)
      + nameLines(v.label || "", 72, 114, 132, 22, 16, 130, t.ink);
  }

  function tilesBody(views) {
    const out = [body(C.off)];
    views.forEach((v, i) => {
      const t = TONES[v.tone] || TONES.idle;
      const x = i ? 75 : 6;
      const cx = x + 31.5;
      out.push(`<rect x="${x}" y="47" width="63" height="91" rx="10" fill="${t.bg}"/>`);
      out.push(text(i ? "LONG" : "COURT", cx, 61, 11, t.ink, ' fill-opacity="0.75"'));
      out.push(glyph(v.glyph, cx, 88, 30, t.ink, t.accent));
      const f = fit(v.label || "", 14, 57, 9);
      out.push(text(f.txt, cx, 128, f.size, t.ink));
    });
    return out.join("");
  }

  function customBody(m) {
    const views = (m.views || []).filter(Boolean);
    if (!views.length) return lines(C.off, "CHOISIS", "UNE ACTION", C.soft);
    if (m.phase === "stopped" || m.phase === "starting" || m.phase === "closing") {
      const state = { stopped: "ÉTEINT", starting: "DÉMARRE", closing: "ARRÊT…" }[m.phase];
      const off = views.map((v) => ({ ...v, tone: "off" }));
      return off.length === 1 ? viewBody({ ...off[0], label: state }) : tilesBody(off);
    }
    return views.length === 1 ? viewBody(views[0]) : tilesBody(views);
  }

  function offlineBody(m) {
    const name = { record: "rec", pause: "pause", power: "power", vcam: "camera", show: "eye", custom: "tap" }[m.kind];
    if (m.phase === "launching") return iconLabel(C.idle, name, C.soft, "OUVERTURE…", C.soft, "#8c3341");
    if (m.phase === "nofile") return lines(C.off, "MULTI OBS", "INTROUVABLE", C.muted);
    return iconLabel(C.off, name, C.offInk, "FERMÉ", C.muted, "#5c2a33");
  }

  function render(m) {
    let content;
    if (m.message) content = lines(C.message, m.message[0], m.message[1], "#ffffff");
    else if (m.phase === "offline" || m.phase === "launching" || m.phase === "nofile") content = offlineBody(m);
    else if (m.phase === "unset") content = lines(C.off, "CHOISIS", "UN OBS", C.soft);
    else if (m.phase === "missing") content = lines(C.off, "OBS", "INTROUVABLE", C.muted);
    else {
      content = { record: recordBody, pause: pauseBody, power: powerBody, vcam: vcamBody, show: showBody, custom: customBody }[m.kind](m);
      if (m.fired) content = inverted(content);   // appui long parti : toute la touche en négatif
      else if (m.press != null) content += holdLayer(content, m.press);
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144" viewBox="0 0 144 144">`
      + `<rect width="144" height="144" fill="${C.off}"/>${band(m)}${content}</svg>`;
  }

  const api = { render, glyph, formatTime, COLORS: C };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MultiObsKeys = api;
})(this);
