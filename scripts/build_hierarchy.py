"""Stage 3 — fold the mapped triples into a three-layer source-domain ontology.

    macro source  (from the LLM, constrained by the taxonomy)
      mid source  (from your keyword rules — the layer worth curating by hand)
        sub source (the surface vehicle, kept verbatim for auditing)

Also emits the macro and mid frequency tables the write-up needs.

    python3 scripts/build_hierarchy.py --input out/mapped.csv \
        --rules hierarchy_rules.yaml --outdir out/ --group-field period
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from llm_client import load_yaml

ADDED_FIELDS = [
    "macro_target", "mid_target", "macro_source", "mid_source", "sub_source",
    "is_residual_mid",
]


def compile_mid_rules(rules):
    """Keyword -> mid label per macro domain, longest keyword first.

    Longest-first matching is what stops '走狗' (running dog) from being
    swallowed by the shorter '狗' (dog) rule.
    """
    compiled = {}
    for macro, mids in (rules.get("mid_source") or {}).items():
        pairs = []
        for mid_label, keywords in (mids or {}).items():
            for keyword in keywords or []:
                pairs.append((str(keyword), mid_label))
        pairs.sort(key=lambda kv: len(kv[0]), reverse=True)
        compiled[macro] = pairs
    return compiled


def assign_mid(macro, vehicle, ground, compiled, residual_prefix):
    """Return (mid_label, is_residual)."""
    pairs = compiled.get(macro)
    if not pairs:
        # No rules written for this domain yet: the macro label is the mid label.
        return macro, False
    haystack = f"{vehicle} {ground}"
    for keyword, mid_label in pairs:
        if keyword in haystack:
            return mid_label, False
    return f"{residual_prefix}{macro}", True


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def frequency_rows(rows, group_field, keys):
    """Counts and within-group ratios for the given key columns."""
    totals = Counter()
    counts = Counter()
    for row in rows:
        group = row.get(group_field, "") if group_field else "all"
        counts[(group,) + tuple(row[k] for k in keys)] += 1
        totals[group] += 1
    out = []
    for combo, count in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1:])):
        group, values = combo[0], combo[1:]
        entry = {"group": group, "count": count,
                 "ratio": round(count / totals[group], 6) if totals[group] else 0}
        entry.update(dict(zip(keys, values)))
        out.append(entry)
    return out


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Stage 2 CSV")
    parser.add_argument("--rules", required=True, help="hierarchy_rules.yaml")
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--group-field", default="", help="Column to compare across, e.g. period")
    parser.add_argument("--keep-invalid", action="store_true",
                        help="Keep rows without a complete mapping (excluded by default)")
    return parser.parse_args()


def main():
    args = parse_args()
    rules = load_yaml(args.rules)
    compiled = compile_mid_rules(rules)
    residual_prefix = rules.get("residual_prefix", "其他")
    macro_target = rules.get("macro_target", "")
    target_merge = rules.get("target_merge") or {}

    with open(args.input, encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        in_fields = reader.fieldnames or []

    kept = []
    for row in rows:
        if not args.keep_invalid and row.get("mapping_valid") != "1":
            continue
        macro = row.get("source_domain", "")
        mid, residual = assign_mid(macro, row.get("vehicle", ""), row.get("ground", ""),
                                   compiled, residual_prefix)
        row["macro_target"] = macro_target
        row["mid_target"] = target_merge.get(row.get("target_domain", ""), row.get("target_domain", ""))
        row["macro_source"] = macro
        row["mid_source"] = mid
        row["sub_source"] = row.get("vehicle", "")
        row["is_residual_mid"] = "1" if residual else "0"
        kept.append(row)

    outdir = Path(args.outdir)
    out_fields = in_fields + [f for f in ADDED_FIELDS if f not in in_fields]
    write_csv(outdir / "hierarchy.csv", out_fields, kept)

    clean = [r for r in kept if r["is_residual_mid"] == "0"]
    group = args.group_field or None
    write_csv(outdir / "stats_macro.csv",
              ["group", "macro_source", "count", "ratio"],
              frequency_rows(clean, group, ["macro_source"]))
    write_csv(outdir / "stats_mid.csv",
              ["group", "macro_source", "mid_source", "count", "ratio"],
              frequency_rows(clean, group, ["macro_source", "mid_source"]))

    print(f"wrote {outdir / 'hierarchy.csv'}")
    print(f"  {len(rows)} input row(s) -> {len(kept)} with a complete mapping")
    print(f"  clean mid (excluding '{residual_prefix}*' residuals): {len(clean)}"
          f" ({len(clean) / len(kept) * 100:.1f}%)" if kept else "  no rows")

    residual = Counter(r["mid_source"] for r in kept if r["is_residual_mid"] == "1")
    if residual:
        print("  residual buckets — these are your cue to add mid-level rules:")
        for label, count in residual.most_common(8):
            print(f"    {label}: {count}")

    if group:
        by_group = defaultdict(int)
        for row in clean:
            by_group[row.get(group, "")] += 1
        print(f"  by {group}: " + ", ".join(f"{k}={v}" for k, v in sorted(by_group.items())))


if __name__ == "__main__":
    main()
