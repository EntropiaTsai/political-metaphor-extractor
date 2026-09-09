"""Stage 2 — map each Tenor/Vehicle/Ground triple onto a target and source domain.

This stage never re-reads the original document. It only sees the structured
fields from stage 1, which keeps the labelling decision separate from the
extraction decision and makes disagreements easy to audit.

    python3 scripts/map_domains.py --config config.yaml \
        --input out/tvg.csv --output out/mapped.csv
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from llm_client import LLMClient, LLMError, batched, load_env_file, load_yaml, parse_json, read_text

ADDED_FIELDS = ["target_domain", "source_domain", "mapping_valid"]


def render_taxonomy(template, taxonomy):
    """Let the taxonomy file be the single source of truth for the label space."""
    def bullet(items):
        return "\n".join(f"- {item}" for item in items)

    return (
        template
        .replace("{{allowed_target_domains}}", bullet(taxonomy.get("allowed_target_domains", [])))
        .replace("{{allowed_source_domains}}", bullet(taxonomy.get("allowed_source_domains", [])))
        .replace("{{invalid_source_terms}}", "、".join(taxonomy.get("invalid_source_terms", [])))
    )


def normalise(label, aliases, allowed):
    """Fold aliases, then drop anything outside the allowed label space."""
    label = (label or "").strip().strip("。.,，").strip()
    if not label:
        return ""
    label = aliases.get(label, label)
    if allowed and label not in allowed:
        return ""
    return label


def build_user_prompt(template, rows):
    items = [
        {
            "record_id": r["record_id"],
            "tenor": r.get("tenor", ""),
            "vehicle": r.get("vehicle", ""),
            "ground": r.get("ground", ""),
            "semantic_focus": r.get("semantic_focus", ""),
            "literal_anchor": r.get("literal_anchor", ""),
            "evidence": r.get("evidence", "")[:120],
        }
        for r in rows
    ]
    payload = json.dumps({"items": items}, ensure_ascii=False, indent=1)
    return template.replace("{{context_json}}", payload)


def process_batch(client, system_prompt, template, rows, depth=0):
    try:
        raw = client.complete(system_prompt, build_user_prompt(template, rows))
        parsed = parse_json(raw)
        results = parsed.get("results") if isinstance(parsed, dict) else parsed
        if not isinstance(results, list):
            raise ValueError("response has no 'results' list")
        return {str(r.get("record_id")): r for r in results if r.get("record_id")}
    except (ValueError, LLMError, KeyError) as exc:
        if len(rows) <= 1 or depth >= 3:
            print(f"    unmapped {len(rows)} row(s): {exc}", file=sys.stderr)
            return {}
        print(f"    batch of {len(rows)} failed ({exc}); splitting", file=sys.stderr)
        merged = {}
        for part in batched(rows, max(1, len(rows) // 2)):
            merged.update(process_batch(client, system_prompt, template, part, depth + 1))
        return merged


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--input", required=True, help="Stage 1 CSV")
    parser.add_argument("--output", required=True)
    parser.add_argument("--drop-invalid", action="store_true", help="Omit rows that ended up without a source domain")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    load_env_file(args.env_file)
    config_dir = Path(args.config).resolve().parent
    config = load_yaml(args.config)
    stage = config.get("map", {})
    taxonomy = load_yaml(Path(config_dir) / stage["taxonomy"])

    with open(args.input, encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        in_fields = reader.fieldnames or []

    batch_size = stage.get("batch_size", 20)
    print(f"{len(rows)} triple(s), batch size {batch_size}, model {config['llm']['model']}")
    if args.dry_run:
        print(f"  target labels: {len(taxonomy.get('allowed_target_domains', []))}")
        print(f"  source labels: {len(taxonomy.get('allowed_source_domains', []))}")
        print("dry run, no requests sent")
        return

    system_prompt = render_taxonomy(read_text(stage["prompts"]["system"], config_dir), taxonomy)
    template = read_text(stage["prompts"]["user"], config_dir)
    client = LLMClient(config["llm"])
    if stage.get("max_tokens"):
        client.max_tokens = stage["max_tokens"]

    mapped = {}
    for i, batch in enumerate(batched(rows, batch_size), start=1):
        mapped.update(process_batch(client, system_prompt, template, batch))
        print(f"  batch {i}: {len(mapped)}/{len(rows)} mapped")
        time.sleep(stage.get("sleep_seconds", 0.05))

    target_aliases = taxonomy.get("target_domain_aliases") or {}
    source_aliases = taxonomy.get("source_domain_aliases") or {}
    allowed_targets = set(taxonomy.get("allowed_target_domains") or [])
    allowed_sources = set(taxonomy.get("allowed_source_domains") or [])
    invalid_sources = set(taxonomy.get("invalid_source_terms") or [])

    out_fields = in_fields + [f for f in ADDED_FIELDS if f not in in_fields]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    kept = valid = 0
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            hit = mapped.get(row["record_id"], {})
            target = normalise(hit.get("target_domain"), target_aliases, allowed_targets)
            source = normalise(hit.get("source_domain"), source_aliases, allowed_sources)
            if source in invalid_sources:
                source = ""
            row["target_domain"] = target
            row["source_domain"] = source
            row["mapping_valid"] = "1" if (target and source) else "0"
            valid += row["mapping_valid"] == "1"
            if args.drop_invalid and row["mapping_valid"] != "1":
                continue
            writer.writerow(row)
            kept += 1

    print(f"wrote {output} ({kept} rows, {valid} with a complete mapping)")
    if valid < len(rows):
        print(f"  {len(rows) - valid} row(s) left unmapped — inspect them before trusting the counts")


if __name__ == "__main__":
    main()
