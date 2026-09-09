"""Render the three-layer ontology as a zoomable circle-packing page.

Produces one self-contained HTML file: click a circle to descend one level,
click the background to go back up, and the third level lists the original
sentences behind each vehicle.

    python3 scripts/make_circle_packing.py --input out/hierarchy.csv \
        --output out/hierarchy.html --group-field period
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
  main { display:grid; grid-template-columns:minmax(0,660px) minmax(0,1fr);
         gap:36px; margin-top:18px; align-items:start; }
  #chart svg { display:block; width:100%; height:auto; }
  #crumb { display:flex; flex-wrap:wrap; gap:8px; padding-bottom:10px;
           border-bottom:2px solid var(--border); font-size:17px; color:var(--text-3); }
  #crumb .cur { font-weight:700; color:var(--text-1); }
  #crumb .sep { color:var(--border); }
  #panel { padding-top:14px; max-height:76vh; overflow-y:auto; }
  .lead { margin:0 0 12px; font-size:22px; font-weight:700; }
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
</style>
</head>
<body>
<header>
  <div>
    <h1>__TITLE__</h1>
    <p class="hint">Click a circle to go one level deeper · click the background to go back up</p>
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
const SIZE = 660, MAX_EXAMPLES = 5;
const GROUPS = Object.keys(DATA.groups);
const DEPTH_TINT = {1:0.76, 2:0.58, 3:0.38};
const paper = getComputedStyle(document.body).backgroundColor || "#ffffff";
let group = GROUPS[0];

const el = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function macroOf(d) { let n = d; while (n && n.depth > 1) n = n.parent; return n; }
function baseColor(d) { const m = macroOf(d); return (m && PALETTE[m.data.name]) || "#8c8478"; }
function fillFor(d) {
  const t = DEPTH_TINT[d.depth];
  return t === undefined ? baseColor(d) : d3.interpolateLab(baseColor(d), paper)(t);
}

function crumb(node) {
  el("crumb").innerHTML = node.ancestors().reverse().map((d, i) =>
    `<span class="${i === node.depth ? "cur" : ""}">${esc(d.data.label)}</span>`
  ).join('<span class="sep">&rsaquo;</span>');
}

function listRows(parent, kids) {
  return `<ul>${kids.slice(0, 14).map((d) => `<li class="row">
    <span class="dot" style="background:${baseColor(d)}"></span>
    <span>${esc(d.data.label)}</span>
    <span class="val">${d.value} · ${((d.value / parent.value) * 100).toFixed(1)}%</span>
  </li>`).join("")}</ul>`;
}

function describe(node, root) {
  crumb(node);
  if (node === root) {
    el("panel").innerHTML = `<p class="lead">${root.value} instances · ${esc(group)}</p>` +
      listRows(root, root.children || []);
    return;
  }
  const head = `<div class="head"><span class="dot" style="background:${baseColor(node)}"></span>
    <div><p class="term">${esc(node.data.label)}</p>
    <p class="sub">${esc(node.data.name)} · ${node.value} instances · ${esc(group)}</p></div></div>`;
  if (node.children) { el("panel").innerHTML = head + listRows(node, node.children); return; }
  const items = (node.data.instances || []).slice(0, MAX_EXAMPLES);
  el("panel").innerHTML = head + `<ul>${items.map((it) =>
    `<li class="ev"><p>${esc(it.evidence)}</p></li>`).join("")}</ul>`;
}

function build() {
  const root = d3.pack().size([SIZE, SIZE])
    .padding((d) => (d.depth === 0 ? 18 : d.depth === 1 ? 12 : 4))(
      d3.hierarchy(DATA.groups[group])
        .sum((d) => (d.children ? 0 : d.value))
        .sort((a, b) => b.value - a.value));

  const svg = d3.create("svg").attr("viewBox", [-SIZE/2, -SIZE/2, SIZE, SIZE]).style("cursor","pointer");
  const bg = svg.append("circle").attr("r", root.r).attr("fill", "var(--surface-2)");
  const nodes = root.descendants().slice(1);

  const circle = svg.append("g").selectAll("circle").data(nodes).join("circle")
    .attr("fill", (d) => fillFor(d)).attr("stroke", "none")
    .on("click", (event, d) => { event.stopPropagation(); select(d); });

  const label = svg.append("g").attr("pointer-events","none").attr("text-anchor","middle")
    .selectAll("text").data(nodes).join("text")
    .attr("fill", "var(--text-1)").attr("paint-order","stroke")
    .attr("stroke", "var(--bg)").attr("stroke-width", 3.5).attr("stroke-linejoin","round");
  label.append("tspan").attr("x",0).attr("dy","-0.1em").attr("font-weight",700)
    .text((d) => d.data.label);
  label.append("tspan").attr("x",0).attr("dy","1.15em").attr("font-weight",500)
    .attr("fill","var(--text-3)").text((d) => d.value);

  let focus = root, selected = null, view;
  const fits = (d, k) => d.r * k > 26 && d.r * k * 2 > d.data.label.length * 6.4;

  function zoomTo(v) {
    const k = SIZE / v[2];
    view = v;
    circle.attr("transform", (d) => `translate(${(d.x-v[0])*k},${(d.y-v[1])*k})`).attr("r", (d) => d.r*k);
    label.attr("transform", (d) => `translate(${(d.x-v[0])*k},${(d.y-v[1])*k})`)
      .attr("font-size", (d) => Math.min(20, Math.max(11, d.r*k*0.22)))
      .style("display", (d) => (d.parent === focus && fits(d, k) ? "inline" : "none"));
    bg.attr("r", root.r*k).attr("transform", `translate(${(root.x-v[0])*k},${(root.y-v[1])*k})`);
  }
  function zoom(d) {
    focus = d;
    const target = [d.x, d.y, d.r*2.08];
    svg.transition().duration(620).tween("zoom", () => {
      const i = d3.interpolateZoom(view, target);
      return (t) => zoomTo(i(t));
    });
  }
  function paint() {
    circle.attr("stroke", (d) => (d === selected ? baseColor(d) : "none"))
      .attr("stroke-width", (d) => (d === selected ? 3 : 0));
  }
  function select(d) {
    const path = d.ancestors().reverse();
    const target = path[Math.min(focus.depth + 1, d.depth)];
    if (!target) return;
    selected = target.children ? null : target;
    paint();
    describe(target, root);
    const next = target.children ? target : target.parent;
    if (next !== focus) zoom(next);
  }
  svg.on("click", () => {
    const up = focus.parent || root;
    selected = null; paint(); describe(up, root); zoom(up);
  });

  zoomTo([root.x, root.y, root.r*2.08]);
  describe(root, root);
  el("chart").replaceChildren(svg.node());
}

function setGroup(next) {
  group = next;
  Array.from(el("groups").querySelectorAll("button")).forEach((b) =>
    b.classList.toggle("is-active", b.dataset.group === group));
  build();
}
el("groups").innerHTML = GROUPS.map((g) => `<button data-group="${g}">${g}</button>`).join("");
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

# Muted, warm-leaning hues that survive a projector.
PALETTE_POOL = [
    "#5c7794", "#a56152", "#74906b", "#86708f", "#b8934f",
    "#ab7a78", "#5f8580", "#918878", "#7b7397", "#8a6f5c",
]


def build_tree(rows, labels, max_examples, root_label=None):
    macro_map = OrderedDict()
    for row in rows:
        mids = macro_map.setdefault(row["macro_source"], defaultdict(lambda: defaultdict(list)))
        mids[row["mid_source"]][row["sub_source"]].append(row)

    def label_of(name):
        return labels.get(name, name)

    macros = []
    for macro_name, mids in macro_map.items():
        mid_nodes = []
        for mid_name, subs in mids.items():
            sub_nodes = []
            for sub_name, items in subs.items():
                items.sort(key=lambda r: abs(len(r.get("evidence", "")) - 28))
                sub_nodes.append({
                    "name": sub_name,
                    "label": label_of(sub_name),
                    "value": len(items),
                    "instances": [
                        {"evidence": r.get("evidence", ""), "tenor": r.get("tenor", "")}
                        for r in items[:max_examples]
                    ],
                })
            sub_nodes.sort(key=lambda n: (-n["value"], n["name"]))
            mid_nodes.append({
                "name": mid_name, "label": label_of(mid_name),
                "value": sum(n["value"] for n in sub_nodes), "children": sub_nodes,
            })
        mid_nodes.sort(key=lambda n: (-n["value"], n["name"]))
        macros.append({
            "name": macro_name, "label": label_of(macro_name),
            "value": sum(n["value"] for n in mid_nodes), "children": mid_nodes,
        })
    macros.sort(key=lambda n: (-n["value"], n["name"]))
    if not root_label:
        root_label = labels.get("__root__", "All")
    return {"name": "__root__", "label": root_label,
            "value": sum(n["value"] for n in macros), "children": macros}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="hierarchy.csv from build_hierarchy.py")
    parser.add_argument("--output", required=True)
    parser.add_argument("--group-field", default="", help="Column to build a toggle from, e.g. period")
    parser.add_argument("--title", default="Source-domain hierarchy")
    parser.add_argument("--root-label", default="All")
    parser.add_argument("--labels", help="JSON file mapping raw terms to display labels")
    parser.add_argument("--max-examples", type=int, default=5)
    parser.add_argument("--include-residual", action="store_true")
    parser.add_argument("--d3-src", default=CDN_D3,
                        help="Override with a local path to make the page work offline")
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.input, encoding="utf-8-sig") as handle:
        rows = [r for r in csv.DictReader(handle)
                if args.include_residual or r.get("is_residual_mid") != "1"]
    if not rows:
        raise SystemExit("no rows to plot")

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8")) if args.labels else {}
    labels.setdefault("__root__", args.root_label)

    groups = OrderedDict()
    if args.group_field:
        # Add "All" option at the very beginning to aggregate all rows
        all_label = "全部 (All)"
        groups[all_label] = build_tree(rows, labels, args.max_examples, root_label=all_label)

        for value in sorted({r.get(args.group_field, "") for r in rows}):
            subset = [r for r in rows if r.get(args.group_field, "") == value]
            group_name = value or "(blank)"
            groups[group_name] = build_tree(subset, labels, args.max_examples, root_label=group_name)
    else:
        groups["all"] = build_tree(rows, labels, args.max_examples)

    macro_names = sorted({r["macro_source"] for r in rows})
    palette = {name: PALETTE_POOL[i % len(PALETTE_POOL)] for i, name in enumerate(macro_names)}

    html = (TEMPLATE
            .replace("__TITLE__", args.title)
            .replace("__D3_SRC__", args.d3_src)
            .replace("__PALETTE__", json.dumps(palette, ensure_ascii=False))
            .replace("__DATA__", json.dumps({"groups": groups}, ensure_ascii=False)))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"wrote {output} ({len(rows)} instances, {len(groups)} group(s), {len(macro_names)} macro domains)")


if __name__ == "__main__":
    main()
