"""Render target-source pairings as an interactive bipartite diagram.

The circle packing answers "politics is compared to what?", treating every
target as one lump. This cuts the same rows along the other axis: targets on
the left, source domains on the right, links weighted by count. It shows that
metaphor assignment is usually divided — different targets draw on different
source domains — which the packing view cannot reveal.

Produces one self-contained HTML file: click either side to highlight what it
pairs with, click a source domain to open it into its mid layer, click a link
to read the sentences behind that pair.

    python3 scripts/make_pairing_diagram.py --input out/hierarchy.csv \
        --output out/pairing.html --group-field period
"""

import argparse
import csv
import json
from collections import OrderedDict, defaultdict
from pathlib import Path

CDN_D3 = "https://cdn.jsdelivr.net/npm/d3@7"

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<script src="__D3_SRC__"></script>
<style>
  :root {
    --bg:#fdfcf8; --surface:#fff; --surface-2:#f5f3ea; --border:rgba(20,20,20,.14);
    --text-1:#0a0a0a; --text-2:#333; --text-3:#707070; --accent:#1a3a7a; --accent-3:#8a1a1a;
  }
  * { box-sizing:border-box; }
  body { margin:0; padding:28px 36px; background:var(--bg); color:var(--text-1);
         font-family:"Iowan Old Style",Georgia,"Noto Serif TC",serif; }
  header { display:flex; align-items:flex-end; justify-content:space-between; gap:32px; }
  h1 { margin:0; font-size:30px; }
  .hint { margin:6px 0 0; font-size:14px; color:var(--text-3); }
  .groups { display:inline-flex; border:2px solid var(--text-1); }
  .groups button { padding:6px 20px; font:inherit; font-size:18px; font-weight:700;
                   color:var(--text-3); background:var(--surface); border:0; cursor:pointer; }
  .groups button + button { border-left:2px solid var(--text-1); }
  .groups button.is-active { color:var(--bg); background:var(--text-1); }
  main { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,400px);
         gap:36px; margin-top:18px; align-items:start; }
  #chart svg { display:block; width:100%; height:auto; }
  #crumb { display:flex; flex-wrap:wrap; gap:8px; padding-bottom:10px;
           border-bottom:2px solid var(--border); font-size:17px; color:var(--text-3); }
  #crumb .cur { font-weight:700; color:var(--text-1); }
  #crumb .sep { color:var(--border); }
  #panel { padding-top:14px; max-height:78vh; overflow-y:auto; }
  .lead { margin:0 0 12px; font-size:22px; font-weight:700; }
  .note { margin:0 0 14px; font-size:16px; line-height:1.5; color:var(--text-3); }
  .sec { margin:18px 0 8px; font-size:16px; font-weight:700; color:var(--text-2); }
  ul { margin:0; padding:0; list-style:none; }
  .row { display:flex; align-items:center; gap:10px; padding:6px 0;
         border-bottom:1px solid var(--border); font-size:18px; }
  .dot { flex:none; width:12px; height:12px; border-radius:50%; }
  .val { margin-left:auto; color:var(--text-3); font-variant-numeric:tabular-nums; }
  .head { display:flex; gap:12px; align-items:flex-start; margin-bottom:12px; }
  .head .dot { width:18px; height:18px; margin-top:5px; }
  .term { margin:0; font-size:26px; font-weight:700; }
  .sub { margin:2px 0 0; font-size:16px; color:var(--text-3); }
  .ev { padding:10px 0 10px 14px; border-left:3px solid var(--border); }
  .ev + .ev { border-top:1px solid var(--border); }
  .ev p { margin:0; font-size:17px; line-height:1.45; color:var(--text-2); }
  .ev .pair { margin-bottom:4px; font-size:15px; font-weight:700; color:var(--text-3); }
  mark { background:#fbeeb5; color:inherit; padding:0 2px; }
  text { font-family:inherit; }
</style>
</head>
<body>
<header>
  <div>
    <h1>__TITLE__</h1>
    <p class="hint">Click either side to see what it pairs with · click a source
      domain to open it · click a line to read the sentences · click the
      background to reset</p>
  </div>
  <div class="groups" id="groups"></div>
</header>
<main>
  <div id="chart"></div>
  <div>
    <div id="crumb"></div>
    <div id="panel"></div>
  </div>
</main>
<script>
const DATA = __DATA__;
const PALETTE = __PALETTE__;
/* Not Object.keys(DATA.groups): JS hoists integer-like keys such as "2014"
 * ahead of the rest, which would silently reorder the group buttons. */
const GROUPS = DATA.order;
const W = 1040, H = 620, COL = __COL__, BAR = 12;
const MAX_EXAMPLES = __MAX_EXAMPLES__, TOP_CHILDREN = __TOP_CHILDREN__;
const TARGET_COLOR = "#4a4a48", NEUTRAL = "#8c8478";
/* With nothing to compare against, naming the group on every line is noise. */
const GROUPED = GROUPS.length > 1;
const inGroup = () => (GROUPED ? " · " + esc(group) : "");

let group = GROUPS[0];
let expanded = null;   /* macro source name, one open at a time */
let selected = null;   /* {side, id} or {side:"source", macro} */
let hovered = null;
let activeLink = null;
let view = null;

const el = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const colorOf = (macro) => PALETTE[macro] || NEUTRAL;

/* Show the raw term next to the display label only when --labels renamed it. */
function sub(node) {
  return node.label === node.name ? String(node.value)
                                  : esc(node.name) + " · " + node.value;
}

/* Mark where the vehicle sits inside the sentence, when it appears verbatim. */
function highlight(text, vehicle) {
  const at = vehicle ? String(text).indexOf(vehicle) : -1;
  if (at < 0) return esc(text);
  return esc(text.slice(0, at)) + "<mark>" + esc(vehicle) +
         "</mark>" + esc(text.slice(at + vehicle.length));
}

/* Give every node a floor so small ones stay legible, then share what is left
 * in proportion to the counts. */
function stack(nodes, minH, gap) {
  const heights = new Map();
  let free = H - gap * (nodes.length - 1);
  let pool = nodes.reduce((sum, d) => sum + d.value, 0);

  for (;;) {
    if (pool <= 0) { nodes.forEach((d) => heights.has(d.id) || heights.set(d.id, minH)); break; }
    const scale = free / pool;
    const small = nodes.filter((d) => !heights.has(d.id) && d.value * scale < minH);
    if (!small.length) {
      nodes.forEach((d) => { if (!heights.has(d.id)) heights.set(d.id, d.value * scale); });
      break;
    }
    small.forEach((d) => { heights.set(d.id, minH); free -= minH; pool -= d.value; });
  }

  let y = 0;
  return nodes.map((d) => {
    const h = heights.get(d.id);
    const node = Object.assign({}, d, {y0:y, y1:y + h, yc:y + h / 2, h:h});
    y += h + gap;
    return node;
  });
}

/* The open domain is replaced by its mid layer in place, so every other
 * domain keeps its position and the eye does not lose them. */
function visibleSources(data) {
  const out = [];
  data.sources.forEach((m) => {
    if (m.name !== expanded) {
      out.push({id:m.name, name:m.name, label:m.label, value:m.value,
                macro:m.name, kind:"macro", mids:m.children.map((c) => c.name)});
      return;
    }
    m.children.slice(0, TOP_CHILDREN).forEach((c) => {
      out.push({id:m.name + "/" + c.name, name:c.name, label:c.label,
                value:c.value, macro:m.name, kind:"child", mids:[c.name]});
    });
    const rest = m.children.slice(TOP_CHILDREN);
    if (rest.length) {
      out.push({id:m.name + "/__rest", name:"(" + rest.length + ")",
                label:"Other (" + rest.length + ")",
                value:rest.reduce((sum, c) => sum + c.value, 0),
                macro:m.name, kind:"child", mids:rest.map((c) => c.name)});
    }
  });
  return out;
}

/* Links are stored at the mid layer; roll them up to whichever node is on
 * screen right now. Keyed by macro/mid because a mid name can repeat. */
function visibleLinks(data, sources) {
  const midTo = new Map();
  sources.forEach((n) => n.mids.forEach((m) => midTo.set(n.macro + "/" + m, n.id)));

  const agg = new Map();
  data.links.forEach((l) => {
    const nodeId = midTo.get(l.source + "/" + l.mid);
    if (!nodeId) return;
    const key = l.target + "|" + nodeId;
    let entry = agg.get(key);
    if (!entry) { entry = {target:l.target, source:nodeId, value:0, pool:[]}; agg.set(key, entry); }
    entry.value += l.value;
    entry.pool.push.apply(entry.pool, l.examples);
  });

  const links = Array.from(agg.values());
  links.forEach((l) => {
    l.examples = l.pool.sort((a, b) =>
      Math.abs(a.evidence.length - 28) - Math.abs(b.evidence.length - 28)
    ).slice(0, MAX_EXAMPLES);
    delete l.pool;
  });
  links.sort((a, b) => b.value - a.value);
  return links;
}

function selectedIds() {
  if (!selected) return null;
  const nodes = selected.side === "target" ? view.targets : view.sources;
  return new Set(nodes.filter((n) =>
    selected.macro ? n.macro === selected.macro : n.id === selected.id
  ).map((n) => n.id));
}

/* ---------- side panel ---------- */

function crumb(parts) {
  el("crumb").innerHTML = parts.map((p, i) =>
    `<span class="${i === parts.length - 1 ? "cur" : ""}">${esc(p)}</span>`
  ).join('<span class="sep">&rsaquo;</span>');
}

function partnersOf(side, ids) {
  const other = side === "target" ? "source" : "target";
  const totals = new Map();
  view.links.forEach((l) => {
    if (!ids.has(l[side])) return;
    totals.set(l[other], (totals.get(l[other]) || 0) + l.value);
  });
  const nodes = other === "target" ? view.targets : view.sources;
  const list = Array.from(totals, ([id, value]) => {
    const node = nodes.find((n) => n.id === id);
    return {label:node.label, macro:node.macro, value:value};
  });
  list.sort((a, b) => b.value - a.value);
  return list;
}

function partnerRows(side, ids, total) {
  return `<ul>${partnersOf(side, ids).map((p) => `<li class="row">
    <span class="dot" style="background:${side === "target" ? colorOf(p.macro) : TARGET_COLOR}"></span>
    <span>${esc(p.label)}</span>
    <span class="val">${p.value} · ${((p.value / total) * 100).toFixed(1)}%</span>
  </li>`).join("")}</ul>`;
}

function renderOverview() {
  crumb(GROUPED ? ["All pairings", group] : ["All pairings"]);
  el("panel").innerHTML =
    `<p class="lead">${view.data.total} instances${inGroup()}</p>
     <p class="note">Different targets get compared to different worlds. Click
       either side to see what it pairs with; a source domain also opens up
       into what is actually inside it.</p>
     <p class="sec">Strongest pairings</p>
     <ul>${view.links.slice(0, 8).map((l) => {
       const t = view.targets.find((n) => n.id === l.target);
       const s = view.sources.find((n) => n.id === l.source);
       return `<li class="row">
         <span class="dot" style="background:${colorOf(s.macro)}"></span>
         <span>${esc(t.label)} → ${esc(s.label)}</span>
         <span class="val">${l.value} · ${((l.value / view.data.total) * 100).toFixed(1)}%</span>
       </li>`;
     }).join("")}</ul>`;
}

function renderMacro(name) {
  const macro = view.macros.find((m) => m.name === name);
  const ids = new Set(view.sources.filter((n) => n.macro === name).map((n) => n.id));
  crumb(["Source", macro.label]);
  el("panel").innerHTML =
    `<div class="head"><span class="dot" style="background:${colorOf(name)}"></span>
      <div><p class="term">${esc(macro.label)}</p>
      <p class="sub">${sub(macro)} instances${inGroup()}</p></div></div>
     <p class="sec">Opened into ${macro.children.length} kinds</p>
     <ul>${macro.children.map((c) => `<li class="row">
       <span class="dot" style="background:${colorOf(name)}"></span>
       <span>${esc(c.label)}</span>
       <span class="val">${c.value} · ${((c.value / macro.value) * 100).toFixed(1)}%</span>
     </li>`).join("")}</ul>
     <p class="sec">Used for</p>${partnerRows("source", ids, macro.value)}`;
}

function renderNode(side, id) {
  const node = (side === "target" ? view.targets : view.sources).find((n) => n.id === id);
  crumb([side === "target" ? "Target" : "Source", node.label]);
  el("panel").innerHTML =
    `<div class="head">
      <span class="dot" style="background:${side === "source" ? colorOf(node.macro) : TARGET_COLOR}"></span>
      <div><p class="term">${esc(node.label)}</p>
      <p class="sub">${sub(node)} instances${inGroup()}</p></div></div>
     <p class="sec">${side === "target" ? "Is compared to" : "Used for"}</p>
     ${partnerRows(side, new Set([id]), node.value)}
     <p class="note" style="margin-top:14px">Click a connecting line to read the sentences.</p>`;
}

function renderLink(link) {
  const t = view.targets.find((n) => n.id === link.target);
  const s = view.sources.find((n) => n.id === link.source);
  const shown = link.examples.length;
  crumb([t.label, s.label]);
  el("panel").innerHTML =
    `<div class="head"><span class="dot" style="background:${colorOf(s.macro)}"></span>
      <div><p class="term">${esc(t.label)} → ${esc(s.label)}</p>
      <p class="sub">${shown < link.value ? "showing " + shown + " of " + link.value
                                          : link.value + " instances"}${inGroup()}</p></div></div>
     <ul>${link.examples.map((it) => `<li class="ev">
       <p class="pair">${esc(it.tenor)} → ${esc(it.vehicle)}</p>
       <p>${highlight(it.evidence, it.vehicle)}</p>
     </li>`).join("")}</ul>`;
}

function describe() {
  if (activeLink) renderLink(activeLink);
  else if (selected && selected.macro) renderMacro(selected.macro);
  else if (selected) renderNode(selected.side, selected.id);
  else renderOverview();
}

/* ---------- chart ---------- */

function build() {
  const data = DATA.groups[group];
  const sources = visibleSources(data);
  const links = visibleLinks(data, sources);

  /* An open domain adds rows, so the column has to tighten up. */
  const dense = sources.length > 11;
  const gap = dense ? 8 : 10, minH = dense ? 30 : 42;
  const fontMain = dense ? 17 : 20, fontSub = dense ? 12 : 15;

  const targets = stack(data.targets.map((t) => Object.assign({id:t.name}, t)), 42, 10);
  const stacked = stack(sources, minH, gap);
  view = {data:data, macros:data.sources, targets:targets, sources:stacked, links:links};

  const tIndex = new Map(targets.map((d) => [d.id, d]));
  const sIndex = new Map(stacked.map((d) => [d.id, d]));
  const maxLink = d3.max(links, (l) => l.value) || 1;
  const widthOf = (l) => Math.max(1.5, (l.value / maxLink) * 26);
  const x0 = COL, x1 = W - COL, PAD_TOP = 42;

  const svg = d3.create("svg")
    .attr("viewBox", [0, -PAD_TOP, W, H + PAD_TOP])
    .attr("role", "img")
    .attr("aria-label", "Target and source domain pairings, " + group);

  svg.append("rect").attr("y", -PAD_TOP).attr("width", W).attr("height", H + PAD_TOP)
    .attr("fill", "transparent")
    .on("click", () => {
      const wasOpen = expanded !== null;
      expanded = null; selected = null; activeLink = null;
      if (wasOpen) build(); else { paint(); describe(); }
    });

  const linkSel = svg.append("g").attr("fill", "none").selectAll("path").data(links).join("path")
    .attr("d", (l) => {
      const t = tIndex.get(l.target), s = sIndex.get(l.source);
      const dx = (x1 - x0) * 0.42;
      return `M${x0},${t.yc}C${x0 + dx},${t.yc} ${x1 - dx},${s.yc} ${x1},${s.yc}`;
    })
    .attr("stroke", (l) => colorOf(sIndex.get(l.source).macro))
    .attr("stroke-width", widthOf)
    .attr("stroke-linecap", "round")
    .style("cursor", "pointer")
    .on("click", (event, l) => { event.stopPropagation(); activeLink = l; paint(); describe(); });

  linkSel.append("title").text((l) =>
    tIndex.get(l.target).label + " → " + sIndex.get(l.source).label + ": " + l.value);

  function column(nodes, side) {
    const isTarget = side === "target";
    const labelX = isTarget ? x0 - BAR - 14 : x1 + BAR + 14;

    const g = svg.append("g").selectAll("g").data(nodes).join("g")
      /* Also what an automated check aims at; the bars carry no text. */
      .attr("data-node", (d) => d.id)
      .attr("data-side", side)
      .style("cursor", "pointer")
      .on("mouseenter", (event, d) => { hovered = {side:side, id:d.id}; paint(); })
      .on("mouseleave", () => { hovered = null; paint(); })
      .on("click", (event, d) => {
        event.stopPropagation();
        activeLink = null;
        /* A closed source domain opens up; everything else just selects. */
        if (side === "source" && d.kind === "macro") {
          expanded = d.name;
          selected = {side:"source", macro:d.name};
          hovered = null;
          build();
          return;
        }
        const same = selected && !selected.macro && selected.id === d.id;
        selected = same ? null : {side:side, id:d.id};
        paint();
        describe();
      });

    /* A generous invisible hit area: the bars are thin and people aim at the
     * label, not the bar. */
    g.append("rect").attr("x", isTarget ? 0 : x1)
      .attr("y", (d) => d.y0 - gap / 2).attr("width", COL)
      .attr("height", (d) => d.h + gap).attr("fill", "transparent");

    g.append("rect").attr("class", "bar")
      .attr("x", isTarget ? x0 - BAR : x1).attr("y", (d) => d.y0)
      .attr("width", (d) => (d.kind === "child" ? BAR - 4 : BAR))
      .attr("height", (d) => d.h).attr("rx", 3)
      .attr("fill", (d) => (isTarget ? TARGET_COLOR : colorOf(d.macro)));

    const text = g.append("text").attr("text-anchor", isTarget ? "end" : "start");
    text.append("tspan").attr("x", labelX).attr("y", (d) => d.yc).attr("dy", "-0.15em")
      .attr("font-size", isTarget ? 20 : fontMain).attr("font-weight", 700)
      .attr("fill", "var(--text-1)").text((d) => d.label);
    text.append("tspan").attr("x", labelX).attr("y", (d) => d.yc).attr("dy", "1.1em")
      .attr("font-size", isTarget ? 15 : fontSub)
      .attr("fill", "var(--text-3)").text(sub);

    return g;
  }

  const targetG = column(targets, "target");
  const sourceG = column(stacked, "source");

  function paint() {
    const selIds = selectedIds();
    /* Hover is only a preview. Once something is clicked it stays put, so
     * opening a domain does not lose its highlight to whatever the cursor
     * happens to be resting on afterwards. */
    const ids = selIds || (hovered ? new Set([hovered.id]) : null);
    const side = selected ? selected.side : hovered && hovered.side;

    const linked = {target:new Set(), source:new Set()};
    if (ids) links.forEach((l) => {
      if (ids.has(l[side])) { linked.target.add(l.target); linked.source.add(l.source); }
    });

    linkSel
      .attr("stroke-opacity", (l) => {
        if (activeLink) return l === activeLink ? 0.95 : 0.05;
        if (!ids) return 0.2;
        return ids.has(l[side]) ? 0.78 : 0.04;
      })
      .attr("stroke-width", (l) => widthOf(l) * (l === activeLink ? 1.4 : 1));

    const on = (nodeSide, d) => {
      if (activeLink) return activeLink[nodeSide] === d.id;
      if (!ids) return true;
      return (nodeSide === side && ids.has(d.id)) || linked[nodeSide].has(d.id);
    };

    [[targetG, "target"], [sourceG, "source"]].forEach(([g, nodeSide]) => {
      g.attr("opacity", (d) => (on(nodeSide, d) ? 1 : 0.22));
      g.select(".bar")
        .attr("stroke", (d) => (selIds && selected.side === nodeSide && selIds.has(d.id)
                                ? "var(--text-1)" : "none"))
        .attr("stroke-width", 2);
    });
  }

  /* Anchored to the outer edges so the whole label gutter stays usable.
   * Transparent to clicks, or they swallow the reset without doing anything. */
  const heading = svg.append("g").attr("pointer-events", "none")
    .attr("font-size", 15).attr("font-weight", 700).attr("letter-spacing", "0.06em")
    .attr("fill", "var(--text-3)");
  heading.append("text").attr("x", 0).attr("y", -16).text("WHAT IS TALKED ABOUT");
  heading.append("text").attr("x", W).attr("y", -16).attr("text-anchor", "end")
    .text(expanded ? "COMPARED TO WHAT · OPENED" : "COMPARED TO WHAT · CLICK TO OPEN");

  paint();
  describe();
  el("chart").replaceChildren(svg.node());
}

function setGroup(next) {
  group = next;
  expanded = null; selected = null; hovered = null; activeLink = null;
  Array.from(el("groups").querySelectorAll("button")).forEach((b) =>
    b.classList.toggle("is-active", b.dataset.group === group));
  build();
}

el("groups").innerHTML = GROUPS.map((g) => `<button data-group="${esc(g)}">${esc(g)}</button>`).join("");
el("groups").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-group]");
  if (b) setGroup(b.dataset.group);
});
if (GROUPS.length < 2) el("groups").style.display = "none";
setGroup(GROUPS[0]);
</script>
</body>
</html>
"""

# Same pool and assignment order as make_circle_packing.py, so a macro domain
# keeps its colour across both pages.
PALETTE_POOL = [
    "#5c7794", "#a56152", "#74906b", "#86708f", "#b8934f",
    "#ab7a78", "#5f8580", "#918878", "#7b7397", "#8a6f5c",
]


def build_side(rows, column, labels):
    counts = defaultdict(int)
    for row in rows:
        counts[row[column]] += 1
    nodes = [
        {"name": name, "label": labels.get(name, name), "value": value}
        for name, value in counts.items()
    ]
    nodes.sort(key=lambda n: (-n["value"], n["name"]))
    return nodes


def build_sources(rows, labels):
    """Macro source domains, each carrying the mid layer it can open into."""
    counts = defaultdict(int)
    children = defaultdict(lambda: defaultdict(int))
    for row in rows:
        counts[row["macro_source"]] += 1
        children[row["macro_source"]][row["mid_source"]] += 1

    nodes = []
    for macro, value in counts.items():
        kids = [
            {"name": name, "label": labels.get(name, name), "value": count}
            for name, count in children[macro].items()
        ]
        kids.sort(key=lambda n: (-n["value"], n["name"]))
        nodes.append({
            "name": macro,
            "label": labels.get(macro, macro),
            "value": value,
            "children": kids,
        })
    nodes.sort(key=lambda n: (-n["value"], n["name"]))
    return nodes


def build_links(rows, max_examples):
    """Emitted at the mid-source layer; the page aggregates them back up to the
    macro layer whenever that domain is closed."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["mid_target"], row["macro_source"], row["mid_source"])].append(row)

    links = []
    for (target, source, mid), instances in grouped.items():
        # Mid-length quotes read best: long ones overflow the panel, very short
        # ones carry no context.
        instances.sort(key=lambda r: abs(len(r.get("evidence", "")) - 28))
        links.append({
            "target": target,
            "source": source,
            "mid": mid,
            "value": len(instances),
            "examples": [
                {
                    "tenor": r.get("tenor", ""),
                    "vehicle": r.get("vehicle", ""),
                    "evidence": r.get("evidence", ""),
                }
                for r in instances[:max_examples]
            ],
        })
    links.sort(key=lambda l: (-l["value"], l["target"], l["source"], l["mid"]))
    return links


def build_group(rows, labels, max_examples):
    return {
        "targets": build_side(rows, "mid_target", labels),
        "sources": build_sources(rows, labels),
        "links": build_links(rows, max_examples),
        "total": len(rows),
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="hierarchy.csv from build_hierarchy.py")
    parser.add_argument("--output", required=True)
    parser.add_argument("--group-field", default="", help="Column to build a toggle from, e.g. period")
    parser.add_argument("--title", default="Who gets compared to what")
    parser.add_argument("--labels", help="JSON file mapping raw terms to display labels")
    parser.add_argument("--max-examples", type=int, default=5)
    parser.add_argument("--max-open", type=int, default=8,
                        help="Kinds shown when a source domain is opened; the tail is bucketed")
    parser.add_argument("--label-width", type=int, default=216,
                        help="Pixels reserved for the label gutter on each side")
    parser.add_argument("--include-residual", action="store_true")
    parser.add_argument("--d3-src", default=CDN_D3,
                        help="Override with a local path to make the page work offline")
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.input, encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"mid_target", "macro_source", "mid_source"} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(
                f"{args.input} is missing {sorted(missing)}. "
                "Run build_hierarchy.py first — the pairing view needs the target layer too."
            )
        rows = [r for r in reader
                if args.include_residual or r.get("is_residual_mid") != "1"]
    if not rows:
        raise SystemExit("no rows to plot")

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8")) if args.labels else {}

    groups = OrderedDict()
    if args.group_field:
        # "All" first: the pairing pattern is the point, the group split is the
        # follow-up question.
        all_label = "全部 (All)"
        groups[all_label] = build_group(rows, labels, args.max_examples)
        for value in sorted({r.get(args.group_field, "") for r in rows}):
            subset = [r for r in rows if r.get(args.group_field, "") == value]
            groups[value or "(blank)"] = build_group(subset, labels, args.max_examples)
    else:
        groups["全部 (All)"] = build_group(rows, labels, args.max_examples)

    macro_names = sorted({r["macro_source"] for r in rows})
    palette = {name: PALETTE_POOL[i % len(PALETTE_POOL)] for i, name in enumerate(macro_names)}

    # Match make_circle_packing.py: pick the dataset name out of a metaphor_*
    # working directory so the two pages carry the same heading.
    title = args.title
    identifier = ""
    for part in list(Path(args.output).resolve().parts) + [Path.cwd().name]:
        if part.startswith("metaphor_"):
            identifier = part[len("metaphor_"):]
            break
    if identifier and identifier not in title:
        title = f"{identifier}：{title}"

    payload = {"order": list(groups), "groups": groups}
    html = (TEMPLATE
            .replace("__TITLE__", title)
            .replace("__D3_SRC__", args.d3_src)
            .replace("__COL__", str(args.label_width))
            .replace("__MAX_EXAMPLES__", str(args.max_examples))
            .replace("__TOP_CHILDREN__", str(args.max_open))
            .replace("__PALETTE__", json.dumps(palette, ensure_ascii=False))
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False)))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")

    first = next(iter(groups.values()))
    print(f"wrote {output} ({len(rows)} instances, {len(groups)} group(s), "
          f"{len(first['targets'])} targets, {len(first['sources'])} source domains, "
          f"{len(first['links'])} links)")


if __name__ == "__main__":
    main()
