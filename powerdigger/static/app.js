// Power Digger 3000 frontend. No build step, no framework.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtNum = (n) => (n == null ? "–" : n >= 10000 ? (n / 1000).toFixed(1) + "k" : String(n));
const TAG_ICON = { sleeper: "💎", hot: "🔥", bargain: "💸", acclaimed: "★" };
const TAG_TITLE = { sleeper: "Sleeper: wanted far more than owned, still obscure", hot: "Hot: top 10% wantlist count on this label", bargain: "Bargain: cheap copy for a high-scoring record", acclaimed: "Acclaimed: rated ≥ 4.5 by 10+ people" };
const REISSUE_RE = /\b(RE|RP|RM|Reissue|Repress|Remastered|Unofficial|Unofficial Release)\b/;
const PAGE = 120;

const S = {
  me: null,
  labels: [],
  jobs: {},
  label: null,
  rows: [],
  view: [],
  shown: 0,
  f: { q: "", tag: "", style: "", y0: null, y1: null, vinyl: true, originals: false, master: false, sale: false, video: false, owned: false, price: null },
  sort: "dig",
  layout: localGet("layout") || "grid",
  queue: null, // { ids: [...], i, vi, release }
};

function localGet(k) { try { return localStorage.getItem("pd." + k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem("pd." + k, v); } catch {} }

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new Error(data?.detail || res.statusText);
  return data;
}

let toastTimer;
function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (err ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = ""), err ? 5000 : 2200);
}

// ---------------------------------------------------------------- labels/sidebar

async function loadLabels() {
  S.labels = await api("/api/labels");
  renderLabelList();
}

function renderLabelList() {
  const ul = $("#label-list");
  ul.innerHTML = S.labels.map((l) => {
    const job = S.jobs[l.id];
    const active = job && ["queued", "catalog", "details"].includes(job.phase);
    let sub = "", pct = 0;
    if (active) {
      pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
      sub = job.phase === "queued" ? "queued" : job.phase === "catalog" ? `catalogue ${job.done}/${job.total}` : `details ${job.done}/${job.total}${job.eta_min ? ` · ~${job.eta_min} min` : ""}`;
    } else if (job?.phase === "error") {
      sub = `<span style="color:var(--hot)">error</span>`;
    } else {
      const detailed = l.n_vinyl ? Math.min(100, Math.round((l.n_detailed / l.n_vinyl) * 100)) : 0;
      sub = l.catalog_synced_at ? `${detailed}% detailed` : `<span class="badge">legacy</span> refresh for full catalogue`;
    }
    return `<li data-id="${l.id}" class="${S.label?.id === l.id ? "on" : ""}">
      <span>${esc(l.name)}</span><span class="n">${l.n_releases}</span>
      <span class="sub">${sub}</span>
      ${active ? `<span class="bar"><i style="width:${pct}%"></i></span>` : ""}
      <span class="acts">
        ${active ? `<button data-act="cancel" title="Stop sync">■</button>` : `<button data-act="sync" title="Refresh from Discogs">↻</button>`}
        <button data-act="del" title="Remove">✕</button>
      </span>
    </li>`;
  }).join("");
}

$("#label-list").addEventListener("click", async (e) => {
  const li = e.target.closest("li");
  if (!li) return;
  const id = +li.dataset.id;
  const act = e.target.closest("button")?.dataset.act;
  if (act === "sync") return addLabel(String(id));
  if (act === "cancel") { await api(`/api/jobs/${id}/cancel`, { method: "POST" }); return pollJobs(); }
  if (act === "del") {
    const l = S.labels.find((x) => x.id === id);
    if (!confirm(`Remove ${l?.name} from your crates?`)) return;
    await api(`/api/labels/${id}`, { method: "DELETE" });
    if (S.label?.id === id) { S.label = null; history.replaceState(null, "", "#"); }
    await loadLabels();
    return route();
  }
  location.hash = `#/label/${id}`;
});

async function addLabel(ref) {
  try {
    const job = await api("/api/labels", { method: "POST", body: JSON.stringify({ ref, prices: $("#opt-prices").checked }) });
    toast(`Digging into ${job.name || "label #" + job.label_id} …`);
    S.jobs[job.label_id] = job;
    pollJobs();
    if (!S.label) location.hash = `#/label/${job.label_id}`;
  } catch (err) { toast(err.message, true); }
}

// Search-as-you-type for labels
let searchTimer, searchSel = -1;
$("#add-input").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (q.length < 2 || /label\/\d+/.test(q)) return ($("#search-results").hidden = true);
  searchTimer = setTimeout(async () => {
    try {
      const res = await api(`/api/search/labels?q=${encodeURIComponent(q)}`);
      const box = $("#search-results");
      searchSel = -1;
      box.innerHTML = res.length ? res.map((r) => `<button type="button" data-id="${r.id}">${r.thumb ? `<img src="${esc(r.thumb)}" alt="">` : `<span class="ph"></span>`}<span>${esc(r.title)}</span></button>`).join("") : `<div style="padding:10px;color:var(--muted)">No labels found</div>`;
      box.hidden = false;
    } catch (err) { toast(err.message, true); }
  }, 300);
});
$("#add-input").addEventListener("keydown", (e) => {
  const btns = $$("#search-results button");
  if (!btns.length || $("#search-results").hidden) return;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    searchSel = (searchSel + (e.key === "ArrowDown" ? 1 : -1) + btns.length) % btns.length;
    btns.forEach((b, i) => b.classList.toggle("sel", i === searchSel));
  } else if (e.key === "Enter" && searchSel >= 0) {
    e.preventDefault();
    btns[searchSel].click();
  } else if (e.key === "Escape") $("#search-results").hidden = true;
});
$("#search-results").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  $("#search-results").hidden = true;
  $("#add-input").value = "";
  addLabel(b.dataset.id);
});
$("#add-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("#add-input").value.trim();
  if (!v) return;
  if (/label\/\d+|^\d+$/.test(v)) { $("#add-input").value = ""; $("#search-results").hidden = true; addLabel(v); }
});
document.addEventListener("click", (e) => { if (!e.target.closest("#add-form")) $("#search-results").hidden = true; });

// ---------------------------------------------------------------- jobs polling

let pollTimer, lastLabelRefresh = 0;
const seenErrors = new Set();
async function pollJobs() {
  clearTimeout(pollTimer);
  try {
    const { jobs } = await api("/api/jobs");
    const before = JSON.stringify(Object.values(S.jobs).map((j) => [j.label_id, j.phase]));
    S.jobs = Object.fromEntries(jobs.map((j) => [j.label_id, j]));
    const after = JSON.stringify(jobs.map((j) => [j.label_id, j.phase]));
    const running = jobs.some((j) => ["queued", "catalog", "details"].includes(j.phase));
    if (before !== after || running) await loadLabels();
    for (const j of jobs) if (j.phase === "error" && !seenErrors.has(j.label_id + j.error)) { seenErrors.add(j.label_id + j.error); toast(`${j.name || j.label_id}: ${j.error}`, true); }
    // Live-refresh the open label while its sync runs (catalogue fast, details throttled).
    const cur = S.label && S.jobs[S.label.id];
    if (cur && (["catalog", "details"].includes(cur.phase) || before !== after)) {
      const gap = cur.phase === "catalog" ? 2000 : 15000;
      if (Date.now() - lastLabelRefresh > gap || before !== after) { lastLabelRefresh = Date.now(); await openLabel(S.label.id, true); }
    } else if (!S.label && running) {
      const first = jobs.find((j) => j.phase !== "queued");
      if (first && S.labels.some((l) => l.id === first.label_id)) location.hash = `#/label/${first.label_id}`;
    }
    pollTimer = setTimeout(pollJobs, running ? 2000 : 15000);
  } catch {
    pollTimer = setTimeout(pollJobs, 5000);
  }
}

// ---------------------------------------------------------------- label view

async function openLabel(id, keepState = false) {
  let data;
  try { data = await api(`/api/labels/${id}`); } catch (err) {
    if (!keepState) toast(err.message, true);
    return;
  }
  const switching = S.label?.id !== id;
  S.label = data;
  S.rows = data.releases;
  for (const r of S.rows) {
    r._hay = `${r.artist} ${r.title} ${r.catno} ${(r.styles || []).join(" ")} ${r.country || ""}`.toLowerCase();
    r._reissue = REISSUE_RE.test(r.format || "");
  }
  if (switching && !keepState) {
    S.f = { ...S.f, q: "", tag: "", style: "", y0: null, y1: null };
    $("#q").value = "";
    $$("#tag-filter button").forEach((b) => b.classList.toggle("on", b.dataset.tag === ""));
    $("#main").scrollTop = 0;
  }
  $("#empty").hidden = true;
  $("#label-view").hidden = false;
  renderLabelList();
  renderHead();
  applyFilters(!switching);
}

function renderHead() {
  const L = S.label, sm = L.summary;
  const vinyl = S.rows.filter((r) => r.is_vinyl).length;
  const detailed = S.rows.filter((r) => r.detail_at).length;
  const job = S.jobs[L.id];
  const syncing = job && ["queued", "catalog", "details"].includes(job.phase);
  const cur = S.me?.currency || "EUR";
  const profile = (L.profile || "").replace(/\[(?:a|l|r|m)=([^\]]+)\]/g, "$1").replace(/\[\/?\w+\]/g, "").replace(/\[[alrm](\d+)\]/g, "");
  $("#label-head").innerHTML = `
    ${L.image ? `<img class="logo" src="${esc(L.image)}" alt="">` : `<div class="logo"></div>`}
    <div>
      <h1>${esc(L.name)}</h1>
      ${L.parent ? `<div class="parent">part of <a href="#" data-add="${L.parent.id}">${esc(L.parent.name)}</a></div>` : ""}
      ${profile ? `<p class="profile" title="${esc(profile)}">${esc(profile)}</p>` : ""}
      <div class="stats">
        <div class="stat"><b>${S.rows.length}</b><span>releases</span></div>
        <div class="stat"><b>${vinyl}</b><span>vinyl</span></div>
        <div class="stat"><b>${sm.median_ratio ?? "–"}</b><span>median W/H</span></div>
        <div class="stat"><b>${sm.median_price != null ? sm.median_price.toFixed(0) + " " + cur : "–"}</b><span>median low</span></div>
        <div class="stat"><b>${sm.for_sale}</b><span>for sale</span></div>
      </div>
      <div class="chips" id="style-chips">${sm.styles.slice(0, 14).map(([s, n]) => `<button class="chip ${S.f.style === s ? "on" : ""}" data-style="${esc(s)}">${esc(s)}<small>${n}</small></button>`).join("")}</div>
      ${L.sublabels?.length ? `<div class="chips">${L.sublabels.slice(0, 12).map((s) => `<button class="chip" data-add="${s.id}" title="Add sublabel">+ ${esc(s.name)}</button>`).join("")}</div>` : ""}
      <div class="sync-note">
        ${syncing ? `⏳ Syncing… ${detailed}/${vinyl} vinyl releases have details. Results update live.` :
          !L.catalog_synced_at ? `Imported from the old version: only previously fetched records. <button class="ghost" data-sync>↻ Get full catalogue</button>` :
          `Synced ${new Date(L.catalog_synced_at).toLocaleDateString()} · ${detailed} with details <button class="ghost" data-sync>↻ Refresh</button>`}
      </div>
    </div>
    <div class="hist-wrap">${histogram(sm.years)}</div>`;
}

function histogram(years) {
  if (!years.length) return "";
  const y0 = years[0][0], y1 = years[years.length - 1][0];
  const counts = new Map(years);
  const max = Math.max(...years.map((y) => y[1]));
  const n = y1 - y0 + 1, w = 100 / n;
  let bars = "";
  for (let y = y0; y <= y1; y++) {
    const c = counts.get(y) || 0, h = c ? Math.max(3, (c / max) * 80) : 0;
    const inRange = S.f.y0 != null && y >= S.f.y0 && y <= S.f.y1;
    bars += `<rect data-year="${y}" x="${(y - y0) * w}%" y="${84 - h}" width="${w * 0.8}%" height="${h}" class="${inRange ? "in" : ""}"><title>${y}: ${c} releases</title></rect>`;
    bars += `<rect data-year="${y}" x="${(y - y0) * w}%" y="0" width="${w}%" height="84" style="fill:transparent"><title>${y}: ${c} releases</title></rect>`;
  }
  return `<svg class="hist" preserveAspectRatio="none">${bars}</svg>
    <div class="hist-axis"><span>${y0}</span><span>${S.f.y0 != null ? `${S.f.y0}–${S.f.y1} · <a href="#" data-clear-years>clear</a>` : "click / shift-click a year"}</span><span>${y1}</span></div>`;
}

$("#label-head").addEventListener("click", (e) => {
  const t = e.target;
  if (t.closest("[data-add]")) { e.preventDefault(); return addLabel(t.closest("[data-add]").dataset.add); }
  if (t.closest("[data-sync]")) return addLabel(String(S.label.id));
  if (t.closest("[data-clear-years]")) { e.preventDefault(); S.f.y0 = S.f.y1 = null; return refresh(); }
  if (t.closest("[data-style]")) {
    const s = t.closest("[data-style]").dataset.style;
    S.f.style = S.f.style === s ? "" : s;
    return refresh();
  }
  const year = t.closest("[data-year]")?.dataset.year;
  if (year) {
    const y = +year;
    if (e.shiftKey && S.f.y0 != null) { S.f.y0 = Math.min(S.f.y0, y); S.f.y1 = Math.max(S.f.y1, y); }
    else if (S.f.y0 === y && S.f.y1 === y) S.f.y0 = S.f.y1 = null;
    else S.f.y0 = S.f.y1 = y;
    refresh();
  }
});

// ---------------------------------------------------------------- filtering & sorting

const SORTS = {
  dig: (a, b) => b.dig - a.dig,
  ratio: (a, b) => b.ratio - a.ratio,
  want: (a, b) => (b.want || 0) - (a.want || 0),
  rating: (a, b) => (b.rating_avg || 0) * Math.min(1, (b.rating_count || 0) / 5) - (a.rating_avg || 0) * Math.min(1, (a.rating_count || 0) / 5),
  obscure: (a, b) => (a.have || 0) - (b.have || 0) || b.ratio - a.ratio,
  price: (a, b) => (a.lowest_price ?? 1e9) - (b.lowest_price ?? 1e9),
  year_desc: (a, b) => (b.year || 0) - (a.year || 0),
  year_asc: (a, b) => (a.year || 9999) - (b.year || 9999),
  catno: (a, b) => String(a.catno).localeCompare(String(b.catno), undefined, { numeric: true }),
};

function applyFilters(keepScroll = false) {
  const f = S.f, q = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  let v = S.rows.filter((r) =>
    (!f.vinyl || r.is_vinyl) &&
    (!f.originals || !r._reissue) &&
    (!f.sale || r.num_for_sale) &&
    (!f.video || r.n_videos) &&
    (!f.owned || !r.user_have) &&
    (!f.tag || r.tags.includes(f.tag)) &&
    (!f.style || (r.styles || []).includes(f.style)) &&
    (f.y0 == null || (r.year >= f.y0 && r.year <= f.y1)) &&
    (f.price == null || (r.lowest_price != null && r.lowest_price <= f.price)) &&
    q.every((w) => r._hay.includes(w))
  );
  v.sort(SORTS[S.sort]);
  if (f.master) {
    const seen = new Set();
    v = v.filter((r) => !r.master_id || (!seen.has(r.master_id) && seen.add(r.master_id)));
  }
  S.view = v;
  if (S.queue) S.queue.ids = v.map((r) => r.id);
  $("#count").textContent = `${v.length} / ${S.rows.length}`;
  renderActiveFilters();
  renderResults(keepScroll);
}

function refresh() { renderHead(); applyFilters(); }

function renderActiveFilters() {
  const a = [];
  if (S.f.style) a.push(`<button class="chip on" data-clear="style">${esc(S.f.style)} ✕</button>`);
  if (S.f.y0 != null) a.push(`<button class="chip on" data-clear="year">${S.f.y0}${S.f.y1 !== S.f.y0 ? "–" + S.f.y1 : ""} ✕</button>`);
  $("#active-filters").innerHTML = a.join("");
}
$("#active-filters").addEventListener("click", (e) => {
  const c = e.target.closest("[data-clear]")?.dataset.clear;
  if (c === "style") S.f.style = "";
  if (c === "year") S.f.y0 = S.f.y1 = null;
  refresh();
});

function renderResults(keepScroll) {
  const n = keepScroll ? Math.max(S.shown, PAGE) : PAGE;
  S.shown = 0;
  const box = $("#results");
  box.innerHTML = S.layout === "grid" ? `<div class="grid"></div>` :
    `<table class="list"><thead><tr><th></th><th data-sort="catno">Release</th><th data-sort="year_desc">Year</th><th data-sort="want">Want</th><th data-sort="obscure">Have</th><th data-sort="ratio">W/H</th><th data-sort="rating">Rating</th><th data-sort="price">Low</th><th>Sale</th><th data-sort="dig">Dig</th><th></th></tr></thead><tbody></tbody></table>`;
  if (!S.view.length) box.innerHTML = `<p style="color:var(--muted);padding:40px 0;text-align:center">Nothing matches. Loosen the filters.</p>`;
  renderMore(n);
}

function renderMore(n = PAGE) {
  const slice = S.view.slice(S.shown, S.shown + n);
  if (!slice.length) return;
  S.shown += slice.length;
  const playing = S.queue?.release?.id;
  if (S.layout === "grid") $(".grid").insertAdjacentHTML("beforeend", slice.map((r) => card(r, playing)).join(""));
  else $(".list tbody").insertAdjacentHTML("beforeend", slice.map((r) => rowHtml(r, playing)).join(""));
}

new IntersectionObserver((es) => { if (es[0].isIntersecting && S.label) renderMore(); }, { rootMargin: "800px" }).observe($("#sentinel"));

const cur = () => (S.me?.currency === "EUR" ? "€" : S.me?.currency || "€");
const digClass = (d) => (d >= 90 ? "d90" : d >= 75 ? "d75" : "");
const tagsHtml = (r) => r.tags.map((t) => `<span class="tag" title="${TAG_TITLE[t]}">${TAG_ICON[t]}</span>`).join("");

function card(r, playing) {
  const img = r.image || r.thumb;
  return `<div class="card ${r.detail_at ? "" : "pending"} ${playing === r.id ? "playing" : ""}" data-id="${r.id}">
    <div class="cover">
      ${img ? `<img loading="lazy" src="${esc(img)}" alt="">` : ""}
      <span class="dig ${digClass(r.dig)}" title="Dig score">${r.dig}</span>
      <span class="tags">${tagsHtml(r)}</span>
      <button class="heart ${r.user_want ? "on" : ""}" data-want title="Wantlist">${r.user_want ? "♥" : "♡"}</button>
      ${r.user_have ? `<span class="owned">in collection</span>` : ""}
      <button class="play" data-play title="Play">▶</button>
    </div>
    <div class="meta">
      <div class="t" title="${esc(r.title)}">${esc(r.title)}</div>
      <div class="a">${esc(r.artist)}</div>
      <div class="nums">
        <span class="wh" title="want / have"><b>${fmtNum(r.want)}</b>/${fmtNum(r.have)}</span>
        <span>${esc(r.catno || "")}${r.year ? " · " + r.year : ""}</span>
        ${r.lowest_price != null && r.num_for_sale ? `<span class="price" title="${r.num_for_sale} for sale">${cur()}${r.lowest_price.toFixed(0)}</span>` : ""}
      </div>
    </div>
  </div>`;
}

function rowHtml(r, playing) {
  return `<tr data-id="${r.id}" class="${playing === r.id ? "playing" : ""} ${r.detail_at ? "" : "pending"}">
    <td>${r.image || r.thumb ? `<img loading="lazy" src="${esc(r.image || r.thumb)}" alt="">` : ""}</td>
    <td class="tt">${esc(r.artist)} – ${esc(r.title)}<small>${esc(r.catno || "")} · ${esc(r.format || "")}${r.styles?.length ? " · " + esc(r.styles.slice(0, 3).join(", ")) : ""}</small></td>
    <td class="num">${r.year || "–"}</td>
    <td class="num">${fmtNum(r.want)}</td>
    <td class="num">${fmtNum(r.have)}</td>
    <td class="num">${r.raw_ratio != null ? r.raw_ratio.toFixed(2) : "–"}</td>
    <td class="num">${r.rating_avg ? `${r.rating_avg.toFixed(2)} <small style="color:var(--muted)">(${r.rating_count})</small>` : "–"}</td>
    <td class="num">${r.lowest_price != null && r.num_for_sale ? cur() + r.lowest_price.toFixed(2) : "–"}</td>
    <td class="num">${r.num_for_sale || "–"}</td>
    <td class="num">${r.dig}<span class="bar-cell"><i style="width:${r.dig}%"></i></span></td>
    <td>${tagsHtml(r)} ${r.user_want ? "♥" : ""}</td>
  </tr>`;
}

$("#results").addEventListener("click", (e) => {
  const th = e.target.closest("th[data-sort]");
  if (th) { S.sort = th.dataset.sort; $("#sort").value = S.sort; return applyFilters(); }
  const el = e.target.closest("[data-id]");
  if (!el) return;
  const id = +el.dataset.id;
  if (e.target.closest("[data-want]")) return toggleWant(id);
  if (e.target.closest("[data-play]")) return startQueue(id);
  openDrawer(id);
});

// toolbar wiring
$("#q").addEventListener("input", (e) => { S.f.q = e.target.value; applyFilters(); });
$("#sort").addEventListener("change", (e) => { S.sort = e.target.value; applyFilters(); });
$("#tag-filter").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  S.f.tag = b.dataset.tag;
  $$("#tag-filter button").forEach((x) => x.classList.toggle("on", x === b));
  applyFilters();
});
for (const [id, key] of [["f-vinyl", "vinyl"], ["f-originals", "originals"], ["f-master", "master"], ["f-sale", "sale"], ["f-video", "video"], ["f-owned", "owned"]]) {
  const el = $("#" + id);
  const saved = localGet("f." + key);
  if (saved != null) el.checked = saved === "1";
  S.f[key] = el.checked;
  el.addEventListener("change", () => { S.f[key] = el.checked; localSet("f." + key, el.checked ? "1" : "0"); applyFilters(); });
}
$("#f-price").addEventListener("input", (e) => { S.f.price = e.target.value === "" ? null : +e.target.value; applyFilters(); });
$("#view").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  S.layout = b.dataset.view;
  localSet("layout", S.layout);
  $$("#view button").forEach((x) => x.classList.toggle("on", x === b));
  renderResults();
});
$$("#view button").forEach((x) => x.classList.toggle("on", x.dataset.view === S.layout));
$("#play-crate").addEventListener("click", () => S.view.length && startQueue(S.view[0].id));

// ---------------------------------------------------------------- release drawer

const releaseCache = new Map();
async function getRelease(id, refresh = false) {
  if (!refresh && releaseCache.has(id)) return releaseCache.get(id);
  const r = await api(`/api/releases/${id}${refresh ? "?refresh=true" : ""}`);
  releaseCache.set(id, r);
  // fold fresh details back into the list row
  const row = S.rows.find((x) => x.id === id);
  if (row) Object.assign(row, { n_videos: r.n_videos, detail_at: r.detail_at, image: r.image, lowest_price: r.lowest_price, num_for_sale: r.num_for_sale, rating_avg: r.rating_avg, rating_count: r.rating_count, styles: r.styles, master_id: r.master_id });
  return r;
}

const ytId = (uri) => uri.match(/(?:v=|youtu\.be\/|embed\/)([\w-]{11})/)?.[1];
const dur = (s) => (s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "");

async function openDrawer(id) {
  const d = $("#drawer");
  d.hidden = false;
  d.dataset.id = id;
  const row = S.rows.find((x) => x.id === id);
  $("#drawer-body").innerHTML = row ? drawerHtml({ ...row, _loading: true }) : `<div class="d-body">Loading…</div>`;
  try {
    const r = await getRelease(id);
    if (+d.dataset.id === id) $("#drawer-body").innerHTML = drawerHtml({ ...row, ...r });
  } catch (err) { toast(err.message, true); }
}

function drawerHtml(r) {
  const c = cur();
  const sugg = r.price_suggestions && Object.keys(r.price_suggestions).length ? r.price_suggestions : null;
  return `
    ${r.image || r.thumb ? `<img class="d-cover" src="${esc(r.image || r.thumb)}" alt="">` : ""}
    <div class="d-body">
      <h2>${esc(r.title)}</h2>
      <div class="artist">${esc(r.artist)}</div>
      <div class="facts">${[r.label_info || r.catno, r.country, r.released || r.year].filter(Boolean).map(esc).join(" · ")}</div>
      <div class="facts">${esc(Array.isArray(r.formats) ? r.formats.join(", ") : r.format || "")}</div>
      ${r.tags?.length ? `<div class="chips">${r.tags.map((t) => `<span class="chip" title="${TAG_TITLE[t]}">${TAG_ICON[t]} ${t}</span>`).join("")}</div>` : ""}
      <div class="kpis">
        <div class="kpi"><b>${r.dig ?? "–"}</b><span>dig score</span></div>
        <div class="kpi"><b>${fmtNum(r.want)}/${fmtNum(r.have)}</b><span>want / have</span></div>
        <div class="kpi"><b>${r.rating_avg ? r.rating_avg.toFixed(2) : "–"}</b><span>${r.rating_count || 0} votes</span></div>
        <div class="kpi"><b>${r.lowest_price != null && r.num_for_sale ? c + r.lowest_price.toFixed(2) : "–"}</b><span>${r.num_for_sale || 0} for sale</span></div>
      </div>
      <div class="d-actions">
        ${r.videos?.length ? `<button class="primary" data-d-play>▶ Play</button>` : ""}
        <button class="ghost" data-d-want>${r.user_want ? "♥ In wantlist" : "♡ Add to wantlist"}</button>
        <a class="ghost" href="https://www.discogs.com/sell/release/${r.id}?sort=price%2Casc" target="_blank" rel="noopener">🛒 Buy</a>
        <a class="ghost" href="https://www.discogs.com/release/${r.id}" target="_blank" rel="noopener">Discogs ↗</a>
        ${r.master_id ? `<a class="ghost" href="https://www.discogs.com/master/${r.master_id}" target="_blank" rel="noopener">All versions ↗</a>` : ""}
        <button class="ghost" data-d-refresh title="Refetch from Discogs">↻</button>
      </div>
      ${r.styles?.length ? `<div class="chips">${r.styles.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}</div>` : ""}
      ${r._loading ? `<p style="color:var(--muted)">Fetching details…</p>` : ""}
      ${r.videos?.length ? `<div class="d-sec"><h3>Listen</h3><div class="videos">${r.videos.map((v, i) => {
        const yid = ytId(v.uri);
        return `<button data-vi="${i}">${yid ? `<img src="https://i.ytimg.com/vi/${yid}/default.jpg" alt="">` : ""}<span>${esc(v.title)}</span><span class="dur">${dur(v.duration)}</span></button>`;
      }).join("")}</div></div>` : !r._loading ? `<div class="d-sec"><h3>Listen</h3><a class="ghost" target="_blank" rel="noopener" href="https://www.youtube.com/results?search_query=${encodeURIComponent(r.artist + " " + r.title)}">Search YouTube ↗</a></div>` : ""}
      ${sugg ? `<div class="d-sec"><h3>Price suggestions</h3><div class="prices">${Object.entries(sugg).map(([k, v]) => `<div><span>${esc(k.match(/\(([^)]+)\)/)?.[1] || k)}</span>${c}${v.toFixed(2)}</div>`).join("")}</div></div>` : ""}
      ${r.tracklist?.length ? `<div class="d-sec"><h3>Tracklist</h3><table class="tracks">${r.tracklist.map((t) => `<tr><td>${esc(t.position)}</td><td>${esc(t.title)}</td><td>${esc(t.duration)}</td></tr>`).join("")}</table></div>` : ""}
      ${r.notes ? `<div class="d-sec"><h3>Notes</h3><div class="notes">${esc(r.notes)}</div></div>` : ""}
      ${r.detail_at ? `<p class="facts">details fetched ${new Date(r.detail_at).toLocaleDateString()}</p>` : ""}
    </div>`;
}

$("#drawer").addEventListener("click", async (e) => {
  const id = +$("#drawer").dataset.id;
  if (e.target.closest("#drawer-close")) return closeDrawer();
  if (e.target.closest("[data-d-want]")) { await toggleWant(id); return openDrawer(id); }
  if (e.target.closest("[data-d-refresh]")) { await getRelease(id, true); return openDrawer(id); }
  if (e.target.closest("[data-d-play]")) return startQueue(id, 0);
  const vi = e.target.closest("[data-vi]")?.dataset.vi;
  if (vi != null) startQueue(id, +vi);
});
function closeDrawer() { $("#drawer").hidden = true; }

async function toggleWant(id) {
  const row = S.rows.find((x) => x.id === id) || {};
  const on = !row.user_want;
  try {
    await api(`/api/wants/${id}`, { method: on ? "PUT" : "DELETE" });
    row.user_want = on ? 1 : 0;
    const cached = releaseCache.get(id);
    if (cached) cached.user_want = row.user_want;
    toast(on ? "♥ Added to wantlist" : "Removed from wantlist");
    $$(`[data-id="${id}"] .heart`).forEach((h) => { h.classList.toggle("on", on); h.textContent = on ? "♥" : "♡"; });
    if (S.queue?.release?.id === id) updateNowPlaying();
  } catch (err) { toast(err.message, true); }
}

// ---------------------------------------------------------------- player / dig mode

let yt = null, ytReady = false, ytErrors = 0;
window.onYouTubeIframeAPIReady = () => { ytReady = true; };

function ensurePlayer(videoId) {
  if (yt) { yt.loadVideoById(videoId); return; }
  yt = new YT.Player("yt", {
    videoId,
    playerVars: { autoplay: 1, rel: 0, playsinline: 1, origin: location.origin, widget_referrer: location.href },
    events: {
      onStateChange: (e) => {
        if (e.data === YT.PlayerState.PLAYING) ytErrors = 0;
        if (e.data === YT.PlayerState.ENDED) nextTrack();
      },
      onError: (e) => {
        // 100/101/150: removed or embedding disabled -> skip. Bail out if everything fails.
        console.warn("YouTube error", e.data);
        if (++ytErrors >= 6) { ytErrors = 0; return toast("YouTube keeps refusing to play these videos – stopping here", true); }
        nextTrack();
      },
    },
  });
}

async function startQueue(id, vi = 0) {
  if (!ytReady) return toast("YouTube player still loading, try again in a second", true);
  const ids = S.view.map((r) => r.id);
  if (!ids.includes(id)) ids.unshift(id);
  S.queue = { ids, i: ids.indexOf(id), vi, release: null };
  $("#player").hidden = false;
  await playCurrent();
}

async function playCurrent(dir = 1) {
  const q = S.queue;
  // Skip records without videos; fetch details on the fly for ones not enriched yet.
  for (let guard = 0; guard < 40 && q.i >= 0 && q.i < q.ids.length; guard++) {
    const id = q.ids[q.i];
    $("#now-title").textContent = "Finding a video…";
    let r;
    try { r = await getRelease(id); } catch { r = null; }
    if (S.queue !== q) return; // user moved on meanwhile
    if (r?.videos?.length && q.vi < r.videos.length) {
      q.release = { ...S.rows.find((x) => x.id === id), ...r };
      ensurePlayer(ytId(r.videos[q.vi].uri));
      updateNowPlaying();
      return;
    }
    q.i += dir;
    q.vi = 0;
  }
  toast("No more records with videos in this view");
}

function updateNowPlaying() {
  const r = S.queue.release;
  const v = r.videos[S.queue.vi];
  $("#now-cover").src = r.image || r.thumb || "";
  $("#now-title").textContent = `${r.artist} – ${r.title}`;
  $("#now-sub").innerHTML = `${esc(v.title)} · track ${S.queue.vi + 1}/${r.videos.length} · record ${S.queue.i + 1}/${S.queue.ids.length} · ${fmtNum(r.want)}/${fmtNum(r.have)} W/H · <a href="${esc(v.uri)}" target="_blank" rel="noopener">YouTube ↗</a>`;
  const row = S.rows.find((x) => x.id === r.id);
  $("#p-want").classList.toggle("on", !!row?.user_want);
  $("#p-want").textContent = row?.user_want ? "♥" : "♡";
  $$(".playing").forEach((el) => el.classList.remove("playing"));
  const el = $(`#results [data-id="${r.id}"]`);
  if (el) { el.classList.add("playing"); el.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
}

function nextRecord() { if (!S.queue) return; S.queue.i++; S.queue.vi = 0; playCurrent(1); }
function prevRecord() { if (!S.queue) return; S.queue.i = Math.max(0, S.queue.i - 1); S.queue.vi = 0; playCurrent(-1); }
function nextTrack() {
  const q = S.queue;
  if (!q?.release) return;
  if (q.vi + 1 < q.release.videos.length) { q.vi++; playCurrent(1); } else nextRecord();
}
function stopPlayer() {
  yt?.stopVideo();
  S.queue = null;
  $("#player").hidden = true;
  $$(".playing").forEach((el) => el.classList.remove("playing"));
}

$("#p-next").onclick = nextRecord;
$("#p-prev").onclick = prevRecord;
$("#p-track").onclick = nextTrack;
$("#p-close").onclick = stopPlayer;
$("#p-want").onclick = () => S.queue?.release && toggleWant(S.queue.release.id);
$("#p-open").onclick = () => S.queue?.release && openDrawer(S.queue.release.id);

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) {
    if (e.key === "Escape") e.target.blur();
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (k === "/") { e.preventDefault(); $("#q").focus(); }
  else if (k === "Escape") closeDrawer();
  else if (S.queue && (k === "ArrowRight" || k === "n")) { e.preventDefault(); nextRecord(); }
  else if (S.queue && (k === "ArrowLeft" || k === "p")) { e.preventDefault(); prevRecord(); }
  else if (S.queue && (k === "ArrowDown" || k === "t")) { e.preventDefault(); nextTrack(); }
  else if (S.queue && (k === "w" || k === "W")) toggleWant(S.queue.release.id);
  else if (S.queue && k === "Enter") openDrawer(S.queue.release.id);
  else if (S.queue && k === " ") { e.preventDefault(); yt?.getPlayerState() === 1 ? yt.pauseVideo() : yt?.playVideo(); }
});

// ---------------------------------------------------------------- routing / boot

function route() {
  const m = location.hash.match(/#\/label\/(\d+)/);
  if (m) return openLabel(+m[1]);
  if (S.labels.length) { location.hash = `#/label/${S.labels[0].id}`; return; }
  $("#empty").hidden = false;
  $("#label-view").hidden = true;
}
window.addEventListener("hashchange", route);

(async function boot() {
  try {
    S.me = await api("/api/me");
    $("#me").innerHTML = S.me.token ? `Signed in as <b>${esc(S.me.username)}</b> · ${esc(S.me.currency)}` : `<span style="color:var(--hot)">No DISCOGS_TOKEN set</span> – add it to .env`;
    $(".cur").textContent = S.me.currency;
  } catch {}
  await loadLabels();
  await route();
  pollJobs();
})();
