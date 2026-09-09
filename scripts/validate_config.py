"""Check that the config, taxonomy, rules and prompts agree with each other.

Catches the mistakes that would otherwise show up as silently dropped rows:
a few-shot example that teaches a label the whitelist rejects, a mid-level rule
written under a macro domain that can never be produced, a prompt file that
moved. Run this after editing any of the templates and before a long run.

    python3 scripts/validate_config.py --config config.yaml --rules hierarchy_rules.yaml
"""

import argparse
import re
import sys
from pathlib import Path

from llm_client import load_yaml, read_text

# Matches the few-shot conclusion lines in the mapping prompt, e.g.
#   → target_domain: 政治制度, source_domain: 人工物
EXAMPLE_LINE = re.compile(r"target_domain:\s*([^,\n]+?)\s*,\s*source_domain:\s*([^\s,\n]+)")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, message):
        self.errors.append(message)

    def warn(self, message):
        self.warnings.append(message)

    def finish(self):
        for message in self.warnings:
            print(f"  warning: {message}")
        for message in self.errors:
            print(f"  error:   {message}")
        if self.errors:
            print(f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s)")
            return 1
        print(f"\nconfig is consistent ({len(self.warnings)} warning(s))")
        return 0


def check_prompts(config, config_dir, report):
    for stage in ("extract", "map"):
        for role in ("system", "user"):
            rel = config.get(stage, {}).get("prompts", {}).get(role)
            if not rel:
                report.error(f"config.{stage}.prompts.{role} is not set")
                continue
            path = Path(config_dir) / rel
            if not path.exists():
                report.error(f"prompt file not found: {rel}")
                continue
            if "{{context_json}}" not in path.read_text(encoding="utf-8") and role == "user":
                report.error(f"{rel} is missing the {{{{context_json}}}} placeholder")


def check_map_prompt_placeholders(text, report):
    for placeholder in ("{{allowed_target_domains}}", "{{allowed_source_domains}}"):
        if placeholder not in text:
            report.error(
                f"the mapping system prompt is missing {placeholder}; the model will not "
                "see the label space and its answers will be rejected wholesale"
            )


def check_examples(text, targets, sources, report):
    """Few-shot labels must live inside the whitelist or they teach rejected answers."""
    found = 0
    for target, source in EXAMPLE_LINE.findall(text):
        found += 1
        if targets and target not in targets:
            report.error(f"few-shot example uses target_domain '{target}', "
                         "which is not in allowed_target_domains")
        if sources and source not in sources:
            report.error(f"few-shot example uses source_domain '{source}', "
                         "which is not in allowed_source_domains")
    if not found:
        report.warn("no few-shot example lines detected in the mapping prompt")


def check_taxonomy(taxonomy, report):
    targets = set(taxonomy.get("allowed_target_domains") or [])
    sources = set(taxonomy.get("allowed_source_domains") or [])
    if not targets:
        report.error("allowed_target_domains is empty; every mapping will be discarded")
    if not sources:
        report.error("allowed_source_domains is empty; every mapping will be discarded")

    for name, aliases, allowed in (
        ("target_domain_aliases", taxonomy.get("target_domain_aliases") or {}, targets),
        ("source_domain_aliases", taxonomy.get("source_domain_aliases") or {}, sources),
    ):
        for key, value in aliases.items():
            if allowed and value not in allowed:
                report.error(f"{name}['{key}'] folds to '{value}', which is not in the "
                             "matching allowed list, so it is cleared right after folding")

    for term in taxonomy.get("invalid_source_terms") or []:
        if term in sources:
            report.error(f"'{term}' is in both allowed_source_domains and "
                         "invalid_source_terms; it will always be cleared")
    return targets, sources


def check_rules(rules, targets, sources, report):
    for macro in (rules.get("mid_source") or {}):
        if sources and macro not in sources:
            report.error(f"hierarchy_rules.mid_source has a block for '{macro}', which is not "
                         "in allowed_source_domains, so no row can ever reach it")

    for key in (rules.get("target_merge") or {}):
        if targets and key not in targets:
            report.warn(f"target_merge['{key}'] is not in allowed_target_domains; "
                        "the rule will never fire")

    seen = {}
    for macro, mids in (rules.get("mid_source") or {}).items():
        for mid, keywords in (mids or {}).items():
            for keyword in keywords or []:
                previous = seen.get((macro, keyword))
                if previous and previous != mid:
                    report.warn(f"keyword '{keyword}' under '{macro}' is claimed by both "
                                f"'{previous}' and '{mid}'; the longer rule wins")
                seen[(macro, keyword)] = mid

    if not rules.get("macro_target"):
        report.warn("macro_target is not set; the macro_target column will be empty")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--rules", help="hierarchy_rules.yaml (skipped if omitted)")
    return parser.parse_args()


def main():
    args = parse_args()
    report = Report()
    config_dir = Path(args.config).resolve().parent
    config = load_yaml(args.config)

    print(f"checking {args.config}")
    check_prompts(config, config_dir, report)

    taxonomy_rel = config.get("map", {}).get("taxonomy")
    if not taxonomy_rel or not (Path(config_dir) / taxonomy_rel).exists():
        report.error(f"taxonomy file not found: {taxonomy_rel}")
        sys.exit(report.finish())

    taxonomy = load_yaml(Path(config_dir) / taxonomy_rel)
    targets, sources = check_taxonomy(taxonomy, report)
    print(f"  {len(targets)} target label(s), {len(sources)} source label(s)")

    map_system = config.get("map", {}).get("prompts", {}).get("system")
    if map_system and (Path(config_dir) / map_system).exists():
        text = read_text(map_system, config_dir)
        check_map_prompt_placeholders(text, report)
        check_examples(text, targets, sources, report)

    if args.rules:
        if Path(args.rules).exists():
            check_rules(load_yaml(args.rules), targets, sources, report)
        else:
            report.error(f"rules file not found: {args.rules}")

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
