"""Turn agent-written JSON annotations into the canonical pipeline CSVs.

Use this when the agent does the annotating itself instead of calling an API,
so no key and no network are involved. The agent emits JSON in exactly the
shape the prompts specify; this script handles CSV quoting, taxonomy
enforcement and completeness checks — the parts that are easy to get subtly
wrong by hand.

    # after the agent has annotated the corpus
    python3 scripts/ingest_annotations.py --stage tvg \
        --corpus corpus.jsonl --input annotations.json \
        --output out/tvg.csv --carry-fields period

    # after the agent has assigned domains
    python3 scripts/ingest_annotations.py --stage map \
        --taxonomy taxonomy.yaml --tvg out/tvg.csv \
        --input mappings.json --output out/mapped.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from extract_tvg import FIELDS, read_corpus, rows_from_results
from map_domains import ADDED_FIELDS, normalise
from llm_client import load_yaml


def load_records(path):
    """Accept {"results": [...]}, a bare list, or one JSON object per line."""
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"{path} is empty")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        records = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path} line {line_no} is not valid JSON: {exc}") from exc
        return records
    if isinstance(data, dict):
        for key in ("results", "records", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    if isinstance(data, list):
        return data
    raise SystemExit(f"{path} must contain a list or an object with a 'results' list")


def ingest_tvg(args):
    carry = [f.strip() for f in args.carry_fields.split(",") if f.strip()]
    docs = read_corpus(args.corpus, carry)
    by_id = {d["id"]: d for d in docs}
    results = load_records(args.input)

    unknown = [str(r.get("text_id")) for r in results if str(r.get("text_id")) not in by_id]
    if unknown:
        print(f"warning: {len(unknown)} text_id(s) not in the corpus, ignored: {unknown[:5]}",
              file=sys.stderr)

    rows = rows_from_results(results, by_id, args.model)
    covered = {str(r.get("text_id")) for r in results}
    missing = [d["id"] for d in docs if d["id"] not in covered]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS + carry, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {output} ({len(rows)} candidate(s) from {len(covered)} annotated document(s))")
    if missing:
        print(f"  {len(missing)} corpus document(s) have no annotation entry: {missing[:8]}")
        print("  every document needs an entry, even an empty one, or your denominators will be wrong")


def ingest_map(args):
    taxonomy = load_yaml(args.taxonomy)
    target_aliases = taxonomy.get("target_domain_aliases") or {}
    source_aliases = taxonomy.get("source_domain_aliases") or {}
    allowed_targets = set(taxonomy.get("allowed_target_domains") or [])
    allowed_sources = set(taxonomy.get("allowed_source_domains") or [])
    invalid_sources = set(taxonomy.get("invalid_source_terms") or [])

    with open(args.tvg, encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        in_fields = reader.fieldnames or []

    mapped = {str(r.get("record_id")): r for r in load_records(args.input) if r.get("record_id")}
    known = {r["record_id"] for r in rows}
    stray = [rid for rid in mapped if rid not in known]
    if stray:
        print(f"warning: {len(stray)} record_id(s) not in {args.tvg}, ignored: {stray[:5]}",
              file=sys.stderr)

    out_fields = in_fields + [f for f in ADDED_FIELDS if f not in in_fields]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    valid = 0
    rejected = []
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            hit = mapped.get(row["record_id"], {})
            raw_target = (hit.get("target_domain") or "").strip()
            raw_source = (hit.get("source_domain") or "").strip()
            target = normalise(raw_target, target_aliases, allowed_targets)
            source = normalise(raw_source, source_aliases, allowed_sources)
            if source in invalid_sources:
                source = ""
            for raw, cleaned, kind in ((raw_target, target, "target"), (raw_source, source, "source")):
                if raw and not cleaned:
                    rejected.append(f"{kind}={raw}")
            row["target_domain"] = target
            row["source_domain"] = source
            row["mapping_valid"] = "1" if (target and source) else "0"
            valid += row["mapping_valid"] == "1"
            writer.writerow(row)

    print(f"wrote {output} ({len(rows)} rows, {valid} with a complete mapping)")
    missing = [r["record_id"] for r in rows if r["record_id"] not in mapped]
    if missing:
        print(f"  {len(missing)} triple(s) have no mapping entry: {missing[:8]}")
    if rejected:
        from collections import Counter
        print("  labels rejected as outside the taxonomy — add them to taxonomy.yaml "
              "or fix the annotation:")
        for label, count in Counter(rejected).most_common(8):
            print(f"    {label} ×{count}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", required=True, choices=["tvg", "map"])
    parser.add_argument("--input", required=True, help="JSON or JSONL written by the agent")
    parser.add_argument("--output", required=True)
    parser.add_argument("--corpus", help="[tvg] the corpus file the annotations refer to")
    parser.add_argument("--carry-fields", default="", help="[tvg] corpus fields to copy through")
    parser.add_argument("--model", default="agent", help="[tvg] value for the model column")
    parser.add_argument("--tvg", help="[map] the stage 1 CSV being labelled")
    parser.add_argument("--taxonomy", help="[map] taxonomy.yaml")
    args = parser.parse_args()

    required = {"tvg": ["corpus"], "map": ["tvg", "taxonomy"]}[args.stage]
    for name in required:
        if not getattr(args, name):
            parser.error(f"--{name} is required when --stage {args.stage}")
    return args


def main():
    args = parse_args()
    (ingest_tvg if args.stage == "tvg" else ingest_map)(args)


if __name__ == "__main__":
    main()
