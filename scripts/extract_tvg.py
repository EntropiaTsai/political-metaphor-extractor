"""Stage 1 — extract Tenor / Vehicle / Ground triples from a corpus.

Reads a generic JSONL or CSV corpus, sends it to the LLM in batches, and writes
one row per metaphor candidate. Domain labels are deliberately NOT assigned
here; that is stage 2's job.

    python3 scripts/extract_tvg.py --config config.yaml \
        --input corpus.jsonl --output out/tvg.csv
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from llm_client import LLMClient, LLMError, batched, load_env_file, load_yaml, parse_json, read_text

FIELDS = [
    "record_id", "doc_id", "tenor", "tenor_pos", "vehicle", "vehicle_pos",
    "semantic_focus", "ground", "literal_anchor", "rationale", "evidence",
    "confidence", "model",
]


def read_corpus(path, carry_fields, limit=None):
    """Load {id, text, ...} records from .jsonl or .csv."""
    path = Path(path)
    rows = []
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    elif path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("documents") or data.get("articles") or []
    elif path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    else:
        raise SystemExit(f"unsupported corpus format: {path.suffix} (use .jsonl, .json or .csv)")

    docs = []
    for i, row in enumerate(rows):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        doc = {
            "id": str(row.get("id") or f"doc{i + 1:05d}"),
            "text": text,
            "carry": {k: row.get(k, "") for k in carry_fields},
        }
        docs.append(doc)
        if limit and len(docs) >= limit:
            break
    return docs


def existing_doc_ids(path):
    path = Path(path)
    if not path.exists():
        return set()
    with path.open(encoding="utf-8-sig") as handle:
        return {row["doc_id"] for row in csv.DictReader(handle) if row.get("doc_id")}


def build_user_prompt(template, docs, max_chars):
    items = [{"text_id": d["id"], "text": d["text"][:max_chars]} for d in docs]
    payload = json.dumps({"items": items}, ensure_ascii=False, indent=1)
    return template.replace("{{context_json}}", payload)


def normalise_results(parsed, docs):
    """Accept either the batch shape or a bare single-document shape."""
    if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
        return parsed["results"]
    if isinstance(parsed, dict) and "metaphors" in parsed:
        return [{"text_id": parsed.get("text_id") or docs[0]["id"], "metaphors": parsed["metaphors"]}]
    if isinstance(parsed, list):
        return parsed
    raise ValueError("response has neither 'results' nor 'metaphors'")


def rows_from_results(results, by_id, model):
    rows = []
    for result in results:
        doc = by_id.get(str(result.get("text_id", "")))
        if not doc:
            continue
        for k, m in enumerate(result.get("metaphors") or [], start=1):
            if not (m.get("vehicle") and m.get("tenor")):
                continue
            row = {
                "record_id": f"{doc['id']}::m{k}",
                "doc_id": doc["id"],
                "tenor": m.get("tenor", ""),
                "tenor_pos": m.get("tenor_pos", ""),
                "vehicle": m.get("vehicle", ""),
                "vehicle_pos": m.get("vehicle_pos", ""),
                "semantic_focus": m.get("semantic_focus", ""),
                "ground": m.get("ground", ""),
                "literal_anchor": m.get("literal_anchor", ""),
                "rationale": m.get("rationale", ""),
                "evidence": m.get("evidence_text", ""),
                "confidence": m.get("confidence", ""),
                "model": model,
            }
            row.update(doc["carry"])
            rows.append(row)
    return rows


def process_batch(client, system_prompt, template, docs, cfg, depth=0):
    """Run one batch, splitting it on parse failure so one bad doc can't sink it."""
    by_id = {d["id"]: d for d in docs}
    user_prompt = build_user_prompt(template, docs, cfg.get("max_chars", 1800))
    try:
        raw = client.complete(system_prompt, user_prompt)
        results = normalise_results(parse_json(raw), docs)
        return rows_from_results(results, by_id, client.model)
    except (ValueError, LLMError, KeyError) as exc:
        chunk = cfg.get("fallback_chunk_size", 2)
        if len(docs) <= 1 or depth >= 3:
            print(f"    dropped {len(docs)} doc(s): {exc}", file=sys.stderr)
            return []
        print(f"    batch of {len(docs)} failed ({exc}); splitting", file=sys.stderr)
        rows = []
        for part in batched(docs, max(1, min(chunk, len(docs) - 1))):
            rows.extend(process_batch(client, system_prompt, template, part, cfg, depth + 1))
        return rows


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--input", required=True, help="Corpus as .jsonl, .json or .csv")
    parser.add_argument("--output", required=True, help="Destination CSV")
    parser.add_argument("--carry-fields", default="", help="Comma-separated corpus fields to copy into the output")
    parser.add_argument("--limit", type=int, help="Only process the first N documents")
    parser.add_argument("--resume", action="store_true", help="Skip documents already present in the output")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--dry-run", action="store_true", help="Report what would run without calling the LLM")
    return parser.parse_args()


def main():
    args = parse_args()
    load_env_file(args.env_file)
    config_dir = Path(args.config).resolve().parent
    config = load_yaml(args.config)
    stage = config.get("extract", {})

    carry = [f.strip() for f in args.carry_fields.split(",") if f.strip()]
    docs = read_corpus(args.input, carry, args.limit)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    done = existing_doc_ids(output) if args.resume else set()
    if done:
        docs = [d for d in docs if d["id"] not in done]
        print(f"resuming: {len(done)} document(s) already extracted")

    batch_size = stage.get("batch_size", 6)
    print(f"{len(docs)} document(s), batch size {batch_size}, model {config['llm']['model']}")
    if args.dry_run:
        for doc in docs[:3]:
            print(f"  {doc['id']}: {doc['text'][:60]}...")
        print("dry run, no requests sent")
        return

    system_prompt = read_text(stage["prompts"]["system"], config_dir)
    template = read_text(stage["prompts"]["user"], config_dir)
    client = LLMClient(config["llm"])

    fields = FIELDS + carry
    write_header = not (args.resume and output.exists())
    with output.open("a" if args.resume and output.exists() else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        total = 0
        for i, batch in enumerate(batched(docs, batch_size), start=1):
            rows = process_batch(client, system_prompt, template, batch, stage)
            for row in rows:
                writer.writerow(row)
            handle.flush()
            total += len(rows)
            print(f"  batch {i}: {len(batch)} doc(s) -> {len(rows)} candidate(s), {total} total")
            time.sleep(stage.get("sleep_seconds", 0.1))

    print(f"wrote {output} ({total} metaphor candidates)")


if __name__ == "__main__":
    main()
