"use strict";
// Fenêtre de réglages d'une touche (affichée par le logiciel Stream Deck sous la grille des touches).
// Les réglages sont gardés par Stream Deck ; la liste des instances et les menus (scènes, sources,
// filtres, sons) viennent de Multi OBS, via le plugin.

const DEFAULTS = {
  record: { target: "all", short: "record", long: "none", longMs: 600 },
  pause: { target: "all" },
  power: { target: "all" },
  vcam: { target: "" },
  show: { target: "all" },
  custom: { target: "all", short: { op: "pause" }, long: { op: "none" }, longMs: 600 },   // appui long : en option
};

const OPS = {
  record: { label: "Rec / Stop", color: "#e5243b", glyph: "rec" },
  pause: { label: "Pause / Reprendre", color: "#f5a30a", glyph: "pause" },
  power: { label: "Allumer / Éteindre", color: "#1d9f48", glyph: "power" },
  vcam: { label: "Caméra virtuelle", color: "#0a8dd0", glyph: "camera" },
  show: { label: "Voir OBS", color: "#c9ccd6", glyph: "eye" },
  scene: { label: "Changer de scène", color: "#9b8cff", glyph: "scene" },
  item: { label: "Montrer / cacher une source", color: "#34d399", glyph: "eye" },
  filter: { label: "Activer / couper un filtre", color: "#f472b6", glyph: "filter" },
  mute: { label: "Couper / remettre le son", color: "#fb7185", glyph: "speakeroff" },
  stream: { label: "Lancer / arrêter le live", color: "#ef4444", glyph: "live" },
  screenshot: { label: "Capture d'écran", color: "#e5e7eb", glyph: "photo" },
  none: { label: "Rien", color: "#80858f", glyph: "none" },
};
const ALL_OPS = ["record", "pause", "power", "vcam", "show", "scene", "item", "filter", "mute", "stream", "screenshot", "none"];
const PRESS_OPS = {
  record: { short: ["record", "pause"], long: ["none", "record", "pause"] },
  custom: { short: ALL_OPS, long: ALL_OPS },
};
const SINGLE_ONLY = new Set(["vcam", "scene", "item", "filter", "mute", "stream", "screenshot"]);

const ABOUT = {
  record: "Démarre / arrête l'enregistrement, avec le timecode sur la touche. Au choix : appui court = pause et appui long = rec / stop, pour ne jamais couper un rec par erreur.",
  pause: "Met l'enregistrement en pause, puis le reprend. Avec « Tous », toutes les instances liées s'arrêtent sur la même image.",
  power: "Allume ou éteint l'OBS. Éteindre est refusé pendant un enregistrement, pour ne rien perdre.",
  custom: "La touche à tout faire : scène, source, filtre, son, live, capture, rec… Choisis son action. Tu peux en ajouter une 2e en appui long : la touche se partage en deux, et un cercle blanc grandit pendant le maintien.",
  vcam: "Allume ou éteint la caméra virtuelle de l'OBS (« VCam Rouge »…), pour Discord, Zoom ou une autre instance.",
  show: "Affiche la fenêtre de l'OBS pour régler ses scènes. Avec « Tous » : la fenêtre de Multi OBS.",
};

let ws = null;
let piUUID = "";
let actionUUID = "";
let kind = "";
let settings = {};
let state = { connected: false, launching: false, instances: [] };
const lists = {};          // menus déjà demandés : clé → { status, items, reason }
const pendingLists = {};   // numéro de demande → clé
let nextReq = 1;

window.connectElgatoStreamDeckSocket = function (port, uuid, registerEvent, _info, actionInfo) {
  piUUID = uuid;
  const info = JSON.parse(actionInfo);
  actionUUID = info.action;
  kind = actionUUID.split(".").pop();
  settings = (info.payload && info.payload.settings) || {};
  ws = new WebSocket("ws://127.0.0.1:" + port);
  ws.onopen = () => {
    ws.send(JSON.stringify({ event: registerEvent, uuid: piUUID }));
    toPlugin({ type: "hello" });
  };
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.event === "sendToPropertyInspector" && m.payload) {
      if (m.payload.type === "state") {
        const statuses = (s) => JSON.stringify([s.connected, (s.instances || []).map((i) => i.status)]);
        // Multi OBS revenu, OBS allumé ou éteint : les menus sont redemandés.
        if (statuses(m.payload) !== statuses(state)) clearLists();
        state = m.payload;
        render();
      } else if (m.payload.type === "list") {
        const key = pendingLists[m.payload.req];
        delete pendingLists[m.payload.req];
        if (key) {
          lists[key] = m.payload.ok ? { status: "ok", items: m.payload.items } : { status: "error", reason: m.payload.reason, items: [] };
          render();
        }
      }
    } else if (m.event === "didReceiveSettings") {
      settings = (m.payload && m.payload.settings) || {};
      render();
    }
  };
  render();
};

function toPlugin(payload) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ event: "sendToPlugin", action: actionUUID, context: piUUID, payload }));
}

function save(patch) {
  Object.assign(settings, patch);
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ event: "setSettings", context: piUUID, payload: settings }));
  render();
}

function current() {
  return Object.assign({}, DEFAULTS[kind] || {}, settings);
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function rgba(hex, a) {
  const n = parseInt(String(hex).replace("#", ""), 16) || 0;
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

function newer(a, b) {
  const pa = String(a || "").split(".").map(Number);
  const pb = String(b || "").split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0);
  }
  return false;
}

// Action d'un appui : chaîne pour « Enregistrer », objet { op, scene… } pour « Action OBS ».
function getOp(s, press) {
  const v = s[press];
  if (typeof v === "string") return { op: v };
  if (v && typeof v === "object" && OPS[v.op]) return { ...v };
  return { op: "none" };
}

function setOp(press, o) {
  save({ [press]: kind === "custom" ? o : o.op });
}

// Instances que « Tous » pilote, pour cette touche (comme les boutons du haut de Multi OBS).
function allTargets(list) {
  if (kind === "power") return list.filter((i) => !i.minimized || (i.status !== "stopped" && i.status !== "unknown"));
  if (kind === "show") return list.filter((i) => !i.minimized);
  return list.filter((i) => i.linked);
}

// ---------------------------------------------------------------- affichage
function render() {
  if (!kind) return;
  const s = current();
  renderStatus();
  document.getElementById("about").textContent = ABOUT[kind] || "";
  renderTargets(s);
  const pressing = !!PRESS_OPS[kind];
  document.getElementById("pressSection").hidden = !pressing;
  // « Action OBS » : une action, l'appui long en plus si on veut ; « Enregistrer » : les deux appuis.
  document.getElementById("shortTitle").textContent = kind === "custom" ? "Action" : "Appui court";
  document.getElementById("longTitle").textContent = kind === "custom" ? "Appui long (en option)" : "Appui long";
  document.getElementById("longSub").textContent = kind === "custom" ? "— une 2e action en maintenant la touche" : "— maintenir la touche";
  if (pressing) renderPresses(s);
}

function renderStatus() {
  const box = document.getElementById("status");
  box.className = "status";
  let title;
  let detail = "";
  let button = null;
  if (state.connected) {
    title = `Connecté à Multi OBS ${esc(state.version || "")}`;
    if (newer(state.version, state.pluginVersion)) detail = "Plugin à mettre à jour : Multi OBS → Paramètres → Stream Deck";
  } else if (state.launching) {
    box.classList.add("launching");
    title = "Ouverture de Multi OBS…";
  } else {
    box.classList.add("closed");
    title = state.exeFound ? "Multi OBS est fermé" : "Multi OBS introuvable";
    detail = state.exeFound ? "Un appui sur une touche l'ouvre aussi" : "Installe Multi OBS, puis ouvre-le une fois";
    if (state.exeFound) button = "Ouvrir";
  }
  box.innerHTML = `<span class="dot"></span><span class="txt">${title}${detail ? `<small>${esc(detail)}</small>` : ""}</span>`;
  if (button) {
    const b = el("button", "", button);
    b.onclick = () => toPlugin({ type: "launch" });
    box.appendChild(b);
  }
}

function statusText(i) {
  if (!state.connected) return i.colorName || "";
  if (i.status === "stopped") return "éteint";
  if (i.status === "starting") return "démarre…";
  if (i.status === "closing") return "s'éteint…";
  if (i.recording) return i.paused ? "en pause" : "● enregistre";
  return "allumé";
}

function renderTargets(s) {
  const box = document.getElementById("targets");
  box.innerHTML = "";
  const list = state.instances || [];
  const chips = [];
  if (kind !== "vcam") {
    const picked = allTargets(list);
    const colors = picked.map((i) => (i.shades || [])[2]).filter(Boolean);
    const grad = colors.length > 1 ? `linear-gradient(135deg, ${colors.join(", ")})` : colors[0] || "#476bd7";
    const dot = colors.length > 1 ? `conic-gradient(${colors.map((c, n) => `${c} ${(n * 100) / colors.length}% ${((n + 1) * 100) / colors.length}%`).join(", ")})` : grad;
    chips.push({ id: "all", name: "Tous", sub: kind === "power" || kind === "show" ? "Multi OBS" : "instances liées", bg: grad, dot });
  }
  for (const i of list) {
    const c = (i.shades || [])[2] || "#5b6273";
    chips.push({ id: i.id, name: i.name, sub: statusText(i), bg: c, dot: c, shades: i.shades });
  }
  if (s.target && s.target !== "all" && !list.some((i) => i.id === s.target)) {
    const c = (s.targetShades || [])[2] || "#5b6273";
    chips.push({ id: s.target, name: s.targetName || "OBS", sub: list.length ? "supprimée" : "", bg: c, dot: c, missing: list.length > 0, shades: s.targetShades });
  }
  for (const c of chips) {
    const b = el("button", "chip" + (c.id === s.target ? " selected" : "") + (c.missing ? " missing" : ""));
    b.type = "button";
    b.style.setProperty("--c", c.bg);
    b.innerHTML = `<span class="dot" style="background:${c.dot}"></span><span class="txt">${esc(c.name)}${c.sub ? `<small>${esc(c.sub)}</small>` : ""}</span>`;
    b.onclick = () => {
      if (c.id === s.target) return;
      clearLists();
      save(c.id === "all" ? { target: "all" } : { target: c.id, targetName: c.name, targetShades: c.shades || [] });
    };
    box.appendChild(b);
  }

  const hint = document.getElementById("targetHint");
  let text = "";
  if (!list.length && !state.connected) text = "Ouvre Multi OBS pour voir tes instances ici.";
  else if (kind === "vcam" && !s.target) text = "Choisis l'OBS dont cette touche allume la caméra virtuelle.";
  else if (s.target === "all") {
    const names = allTargets(list).map((i) => i.name);
    const others = list.filter((i) => !names.includes(i.name)).map((i) => i.name);
    if (kind === "show") text = "« Tous » affiche la fenêtre de Multi OBS.";
    else if (kind === "power") {
      text = `« Tous » allume / éteint : ${names.join(", ") || "aucune instance"}, comme les boutons du haut de Multi OBS.`;
      if (others.length) text += ` Les instances réduites (${others.join(", ")}) restent éteintes.`;
    } else {
      text = `« Tous » pilote les instances liées (Link) : ${names.join(", ") || "aucune"}.`;
      if (others.length) text += ` ${others.join(", ")} ${others.length > 1 ? "ne sont pas liées" : "n'est pas liée"}.`;
    }
  }
  hint.textContent = text;
  hint.hidden = !text;
}

function renderPresses(s) {
  const ops = PRESS_OPS[kind];
  const single = s.target && s.target !== "all";
  for (const press of ["short", "long"]) {
    const box = document.querySelector(`.tiles[data-press="${press}"]`);
    const chosen = getOp(s, press);
    box.innerHTML = "";
    const K = window.MultiObsKeys;
    for (const op of ops[press]) {
      const o = OPS[op];
      const b = el("button", "tile" + (chosen.op === op ? " selected" : ""));
      b.type = "button";
      b.disabled = !single && SINGLE_ONLY.has(op) && kind === "custom";
      if (b.disabled) b.title = "Pour un seul OBS : choisis-le en haut";
      b.style.setProperty("--c", o.color);
      b.style.setProperty("--ct", rgba(o.color, 0.18));
      const ink = op === "record" ? "#ffffff" : o.color;
      b.innerHTML = `<svg viewBox="0 0 48 48">${K ? K.glyph(o.glyph, 24, 24, 44, ink, "#e5243b") : ""}</svg><span>${esc(o.label)}</span>`;
      b.onclick = () => {
        if (chosen.op !== op) setOp(press, { op });
      };
      box.appendChild(b);
    }
    renderParams(press, chosen, single ? s.target : "");
  }
  const long = getOp(s, "long");
  document.getElementById("delay").hidden = long.op === "none";
  const slider = document.getElementById("longMs");
  const out = document.getElementById("longMsOut");
  const showMs = (v) => (out.textContent = (v / 1000).toLocaleString("fr-FR", { minimumFractionDigits: 1 }) + " s");
  slider.value = s.longMs || 600;
  showMs(slider.value);
  slider.oninput = () => showMs(slider.value);
  slider.onchange = () => save({ longMs: Number(slider.value) });

  const hint = document.getElementById("pressHint");
  let text = "";
  if (kind === "record" && getOp(s, "short").op === "pause" && long.op === "record") {
    text = "Appui court : pause / reprise. Maintiens la touche pour lancer ou couper le rec.";
  } else if (kind === "custom" && !single) {
    text = "Scène, source, filtre, son, live, capture et caméra virtuelle : pour un seul OBS, choisis-le en haut.";
  }
  hint.textContent = text;
  hint.hidden = !text;
}

// ---------------------------------------------------------------- menus : scène, source, filtre, son
function clearLists() {
  for (const k of Object.keys(lists)) delete lists[k];
}

function list(target, what, params) {
  const key = JSON.stringify([target, what, params || {}]);
  if (!lists[key]) {
    lists[key] = { status: "loading", items: [] };
    const req = nextReq++;
    pendingLists[req] = key;
    toPlugin({ type: "list", req, target, what, params: params || {} });
  }
  return lists[key];
}

function select(labelText, value, entry, onPick, placeholder) {
  const row = el("div", "param");
  row.appendChild(el("label", "", esc(labelText)));
  const sel = document.createElement("select");
  const items = entry ? entry.items : [];
  const add = (v, text, disabled) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = text;
    opt.disabled = !!disabled;
    sel.appendChild(opt);
  };
  if (!entry) add("", placeholder, true);
  else if (entry.status === "loading") add("", "Chargement…", true);
  else {
    add("", placeholder || "— choisir —", true);
    for (const it of items) add(it, it);
  }
  if (value && !items.includes(value)) add(value, entry && entry.status === "ok" ? `${value} (introuvable)` : value);
  sel.value = value || "";
  sel.disabled = !entry || entry.status === "loading" || (entry.status === "error" && !value);
  sel.onchange = () => onPick(sel.value);
  row.appendChild(sel);
  return row;
}

function renderParams(press, o, target) {
  const box = document.querySelector(`.params[data-press="${press}"]`);
  box.innerHTML = "";
  if (!["scene", "item", "filter", "mute"].includes(o.op)) return;
  if (!target) return;
  const rows = [];
  let error = "";
  if (o.op === "scene") {
    const scenes = list(target, "scenes");
    error = scenes.status === "error" ? scenes.reason : "";
    rows.push(select("Scène", o.scene, scenes, (v) => setOp(press, { ...o, scene: v }), "— choisir une scène —"));
  } else if (o.op === "item") {
    const scenes = list(target, "scenes");
    error = scenes.status === "error" ? scenes.reason : "";
    rows.push(select("Dans la scène", o.scene, scenes, (v) => setOp(press, { op: "item", scene: v, source: "" }), "— choisir une scène —"));
    const items = o.scene ? list(target, "items", { scene: o.scene }) : null;
    rows.push(select("Source", o.source, items, (v) => setOp(press, { ...o, source: v }), o.scene ? "— choisir une source —" : "— d'abord la scène —"));
  } else if (o.op === "filter") {
    const sources = list(target, "sources");
    error = sources.status === "error" ? sources.reason : "";
    rows.push(select("Source", o.source, sources, (v) => setOp(press, { op: "filter", source: v, filter: "" }), "— choisir une source —"));
    const filters = o.source ? list(target, "filters", { source: o.source }) : null;
    rows.push(select("Filtre", o.filter, filters, (v) => setOp(press, { ...o, filter: v }), o.source ? "— choisir un filtre —" : "— d'abord la source —"));
    if (filters && filters.status === "ok" && !filters.items.length) rows.push(el("p", "note", "Cette source n'a pas de filtre."));
  } else if (o.op === "mute") {
    const audio = list(target, "audio");
    error = audio.status === "error" ? audio.reason : "";
    rows.push(select("Source audio", o.input, audio, (v) => setOp(press, { ...o, input: v }), "— choisir une source audio —"));
  }
  for (const r of rows) box.appendChild(r);
  if (error) {
    const name = (state.instances.find((i) => i.id === target) || {}).name || "l'OBS";
    const text = error === "Éteint" || error === "Démarrage" ? `Allume « ${name} » pour voir ses scènes et ses sources.` : `Liste indisponible : ${error}.`;
    box.appendChild(el("p", "note", esc(text)));
  }
}
