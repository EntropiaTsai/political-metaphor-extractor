"""Run the extraction twice or more on the same sample and measure agreement.

This is a reproducibility diagnostic, not an accuracy score: it tells you how
much the model's output moves when nothing else changes. Accuracy still needs
human review.

    python3 scripts/stability_check.py --config config.yaml \
        --input corpus.jsonl --sample 40 --runs 3 --outdir out/stability
"""

import argparse
import csv
import itertools
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sample_corpus(input_path, sample_size, seed, destination):
    sys.path.insert(0, str(HERE))
    from extract_tvg import read_corpus

    docs = read_corpus(input_path, [])
    random.Random(seed).shuffle(docs)
    picked = docs[:sample_size]
    destination.write_text(
        "\n".join(json.dumps({"id": d["id"], "text": d["text"]}, ensure_ascii=False) for d in picked),
        encoding="utf-8",
    )
    return len(picked)


def run(cmd):
    print("  $ " + " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, cwd=HERE.parent)
    if result.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(str(c) for c in cmd)}")


def pairs_by_doc(path):
    """doc_id -> set of (target_domain, source_domain) for one run."""
    out = defaultdict(set)
    with open(path, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("mapping_valid") == "1":
                out[row["doc_id"]].add((row["target_domain"], row["source_domain"]))
    return out


def jaccard(a, b):
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--sample", type=int, default=40)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=4242)
    parser.add_argument("--env-file", default=".env")
    return parser.parse_args()


def main():
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    sample_path = outdir / "sample.jsonl"
    n = sample_corpus(args.input, args.sample, args.seed, sample_path)
    print(f"sampled {n} document(s) with seed {args.seed}")

    mapped_paths = []
    for r in range(1, args.runs + 1):
        print(f"run {r}/{args.runs}")
        tvg = outdir / f"tvg_run{r}.csv"
        mapped = outdir / f"mapped_run{r}.csv"
        run([sys.executable, HERE / "extract_tvg.py", "--config", args.config,
             "--input", sample_path, "--output", tvg, "--env-file", args.env_file])
        run([sys.executable, HERE / "map_domains.py", "--config", args.config,
             "--input", tvg, "--output", mapped, "--env-file", args.env_file])
        mapped_paths.append(mapped)

    runs = [pairs_by_doc(p) for p in mapped_paths]
    doc_ids = sorted({d for run_data in runs for d in run_data})

    per_doc = []
    for doc_id in doc_ids:
        scores = [jaccard(a.get(doc_id, set()), b.get(doc_id, set()))
                  for a, b in itertools.combinations(runs, 2)]
        per_doc.append({"doc_id": doc_id,
                        "mean_jaccard": round(sum(scores) / len(scores), 4) if scores else 1.0,
                        "pairs_run1": len(runs[0].get(doc_id, set()))})

    with (outdir / "doc_jaccard.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doc_id", "mean_jaccard", "pairs_run1"])
        writer.writeheader()
        writer.writerows(per_doc)

    distributions = []
    for r, path in enumerate(mapped_paths, start=1):
        with open(path, encoding="utf-8-sig") as handle:
            counts = Counter(row["source_domain"] for row in csv.DictReader(handle)
                             if row.get("mapping_valid") == "1")
        for domain, count in counts.most_common():
            distributions.append({"run": r, "source_domain": domain, "count": count})

    with (outdir / "source_distribution.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["run", "source_domain", "count"])
        writer.writeheader()
        writer.writerows(distributions)

    overall = sum(d["mean_jaccard"] for d in per_doc) / len(per_doc) if per_doc else 0
    print(f"\nmean pairwise Jaccard across {args.runs} runs: {overall:.3f}")
    print(f"  per-document detail: {outdir / 'doc_jaccard.csv'}")
    print(f"  source distribution per run: {outdir / 'source_distribution.csv'}")
    unstable = [d for d in per_doc if d["mean_jaccard"] < 0.5]
    if unstable:
        print(f"  {len(unstable)} document(s) below 0.5 — read a few by hand before reporting numbers")


if __name__ == "__main__":
    main()
