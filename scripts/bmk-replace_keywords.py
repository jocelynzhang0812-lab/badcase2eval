#!/usr/bin/env python3
"""
Scan Platform datasets for sensitive keywords and replace them.

Usage:
    # Dry run on specific datasets
    python replace_keywords.py --datasets "ds1,ds2" --dry-run

    # Dry run on all datasets with a tag
    python replace_keywords.py --tag "Online_Exp_Withtools_260323" --dry-run

    # Actually replace
    python replace_keywords.py --datasets "ds1,ds2"

    # Save detailed replacement log
    python replace_keywords.py --datasets "ds1" --output replacements.json
"""

import os
import json
import copy
import argparse
import urllib.parse
from typing import List, Dict, Any, Tuple

import requests


# Replacement rules: (old, new)
# ORDER MATTERS  longer strings first to avoid partial matches.
# All replacements are case-sensitive.
REPLACE_RULES = [
    ("/mnt/AI_Platform", "/mnt/agents"),
    ("/mnt/Internal_Toolomputer", "/mnt/agents"),
    ("OpenAI-compatible", "Apollo"),
    ("OpenAI-compatible", "apollo"),
    ("Internal_Toolomputer", "cosmos"),
    ("Internal_Toolomputer", "Cosmos"),
    ("月之暗面", "宇宙无敌"),
    ("AI_Platform", "nova"),
    ("AI_Platform", "Nova"),
    ("msh", "orion"),
    ("Msh", "Orion"),
    # Note: lowercase 'Internal_Tool' is NOT replaced (too many false positives like "boInternal_Toolases")
    ("Internal_Tool", "Cosmos"),
]


# ---------------------------------------------------------------------------
# Helpers reused from scan_keywords.py
# ---------------------------------------------------------------------------

def get_auth_headers() -> Dict[str, str]:
    """Get Platform API authentication headers."""
    token = os.environ.get("AuthGateway_ACCESS_TOKEN")
    if not token:
        raise ValueError("AuthGateway_ACCESS_TOKEN environment variable not set")
    return {"X-AuthGateway-Access-Token": token}


def extract_all_strings(obj: Any, path: str = "root") -> List[Tuple[str, str]]:
    """Recursively extract all string values and their paths from an object."""
    strings = []
    if isinstance(obj, str):
        strings.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            strings.extend(extract_all_strings(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            strings.extend(extract_all_strings(v, f"{path}[{i}]"))
    return strings


def get_datasets_by_tag(tag: str, base_url: str, headers: Dict[str, str]) -> List[Dict]:
    """Get all datasets with a specific tag."""
    r = requests.get(
        f"{base_url}/api/datasets",
        headers=headers,
        params={"limit": 100, "tag": tag},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("datasets", [])


# ---------------------------------------------------------------------------
# Replacement logic
# ---------------------------------------------------------------------------

def apply_rules(text: str, rules: List[Tuple[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
    """
    Apply replacement rules to *text* in order.

    Returns (new_text, changes) where *changes* is a list of
    ``{"old": ..., "new": ...}`` dicts describing every rule that fired.
    """
    changes: List[Dict[str, str]] = []
    for old, new in rules:
        if old in text:
            changes.append({"old": old, "new": new})
            text = text.replace(old, new)
    return text, changes


def replace_in_obj(
    obj: Any,
    rules: List[Tuple[str, str]],
    path: str = "root",
) -> Tuple[Any, List[Dict[str, Any]]]:
    """
    Recursively walk *obj* (dict / list / str / other) and apply replacement
    rules to every string value.

    Returns (new_obj, replacements) where *replacements* is a list of
    ``{"path": ..., "changes": [...], "before": ..., "after": ...}`` entries.
    """
    replacements: List[Dict[str, Any]] = []

    if isinstance(obj, str):
        new_text, changes = apply_rules(obj, rules)
        if changes:
            replacements.append({
                "path": path,
                "changes": changes,
                "before": obj[:200],
                "after": new_text[:200],
            })
        return new_text, replacements

    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            new_v, sub = replace_in_obj(v, rules, f"{path}.{k}")
            new_dict[k] = new_v
            replacements.extend(sub)
        return new_dict, replacements

    if isinstance(obj, list):
        new_list = []
        for i, v in enumerate(obj):
            new_v, sub = replace_in_obj(v, rules, f"{path}[{i}]")
            new_list.append(new_v)
            replacements.extend(sub)
        return new_list, replacements

    # int, float, bool, None  leave unchanged
    return obj, replacements


# ---------------------------------------------------------------------------
# Dataset-level operations
# ---------------------------------------------------------------------------

def fetch_all_items(
    dataset_name: str,
    base_url: str,
    headers: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Paginate through all items in a dataset."""
    all_items: List[Dict[str, Any]] = []
    page = 1
    encoded = urllib.parse.quote(dataset_name, safe="")

    while True:
        try:
            r = requests.get(
                f"{base_url}/api/datasets/{encoded}/items",
                headers=headers,
                params={"page": page, "limit": 50},
                timeout=60,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                break
            all_items.extend(items)
            if len(items) < 50:
                break
            page += 1
        except Exception as e:
            print(f"  Error fetching {dataset_name} page {page}: {e}")
            break

    return all_items


def patch_item(
    dataset_name: str,
    item_id: str,
    new_input: Any,
    new_metadata: Any,
    base_url: str,
    headers: Dict[str, str],
) -> bool:
    """PATCH a single item back to Platform. Returns True on success."""
    encoded = urllib.parse.quote(dataset_name, safe="")
    body: Dict[str, Any] = {}
    if new_input is not None:
        body["input"] = new_input
    if new_metadata is not None:
        body["metadata"] = new_metadata

    try:
        r = requests.patch(
            f"{base_url}/api/datasets/{encoded}/items/{item_id}",
            headers={**headers, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  Error patching item {item_id} in {dataset_name}: {e}")
        return False


def process_dataset(
    dataset_name: str,
    rules: List[Tuple[str, str]],
    base_url: str,
    headers: Dict[str, str],
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Process a single dataset: fetch items, apply replacements, optionally
    PATCH back.

    Returns a result dict with statistics and per-item replacement details.
    """
    print(f"Processing {dataset_name} ...", flush=True)
    items = fetch_all_items(dataset_name, base_url, headers)
    print(f"  Fetched {len(items)} items", flush=True)

    modified_items: List[Dict[str, Any]] = []
    total_replacements = 0

    for item in items:
        item_id = item.get("id", "unknown")
        original_input = item.get("input")
        original_metadata = item.get("metadata")

        new_input, input_reps = replace_in_obj(
            copy.deepcopy(original_input), rules, "input"
        )
        new_metadata, meta_reps = replace_in_obj(
            copy.deepcopy(original_metadata), rules, "metadata"
        )

        all_reps = input_reps + meta_reps
        if not all_reps:
            continue

        rep_count = sum(len(r["changes"]) for r in all_reps)
        total_replacements += rep_count

        entry = {
            "item_id": item_id,
            "replacements": all_reps,
            "replacement_count": rep_count,
            "patched": False,
        }

        if not dry_run:
            ok = patch_item(
                dataset_name, item_id, new_input, new_metadata, base_url, headers
            )
            entry["patched"] = ok
            status = "" if ok else ""
            print(f"  {status} Patched item {item_id} ({rep_count} replacements)")
        else:
            print(f"  [dry-run] Item {item_id}: {rep_count} replacements")

        modified_items.append(entry)

    return {
        "dataset_name": dataset_name,
        "total_items": len(items),
        "modified_items": len(modified_items),
        "total_replacements": total_replacements,
        "details": modified_items,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(results: List[Dict[str, Any]], dry_run: bool):
    """Print a formatted summary report."""
    datasets_scanned = len(results)
    items_scanned = sum(r["total_items"] for r in results)
    items_modified = sum(r["modified_items"] for r in results)
    total_replacements = sum(r["total_replacements"] for r in results)

    mode = "DRY-RUN" if dry_run else "REPLACE"

    print()
    print("=" * 80)
    print(f"REPLACEMENT SUMMARY  ({mode})")
    print("=" * 80)
    print(f"Datasets scanned:    {datasets_scanned}")
    print(f"Items scanned:       {items_scanned}")
    print(f"Items modified:      {items_modified}")
    print(f"Total replacements:  {total_replacements}")
    print()

    print("-" * 80)
    print(f"{'Dataset':<50} {'Items':>8} {'Modified':>10} {'Replacements':>14}")
    print("-" * 80)
    for r in results:
        print(
            f"{r['dataset_name']:<50} "
            f"{r['total_items']:>8} "
            f"{r['modified_items']:>10} "
            f"{r['total_replacements']:>14}"
        )
    print("-" * 80)
    print()

    # Show first few detailed changes per dataset
    for r in results:
        if r["modified_items"] == 0:
            continue
        print(f"### {r['dataset_name']} ({r['modified_items']} items modified)")
        for entry in r["details"][:10]:
            print(f"  Item: {entry['item_id']}  ({entry['replacement_count']} replacements)")
            for rep in entry["replacements"][:5]:
                rules_desc = ", ".join(
                    f"'{c['old']}'→'{c['new']}'" for c in rep["changes"]
                )
                print(f"    {rep['path']}: {rules_desc}")
                print(f"      before: {rep['before'][:100]}")
                print(f"      after:  {rep['after'][:100]}")
            if len(entry["replacements"]) > 5:
                print(f"    ... and {len(entry['replacements']) - 5} more paths")
            print()
        if len(r["details"]) > 10:
            print(f"  ... and {len(r['details']) - 10} more items\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scan Platform datasets for sensitive keywords and replace them."
    )
    parser.add_argument("--datasets", type=str, help="Comma-separated dataset names")
    parser.add_argument("--tag", type=str, help="Tag to filter datasets")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be replaced without writing back",
    )
    parser.add_argument("--output", type=str, help="Save detailed replacement log as JSON")
    parser.add_argument(
        "--base-url",
        type=str,
        default="https://platform.internal.ai.com",
        help="Platform API base URL",
    )

    args = parser.parse_args()
    headers = get_auth_headers()

    # Resolve dataset names ------------------------------------------------
    if args.tag:
        datasets = get_datasets_by_tag(args.tag, args.base_url, headers)
        dataset_names = [d["name"] for d in datasets]
        print(f"Found {len(dataset_names)} datasets with tag '{args.tag}'")
    elif args.datasets:
        dataset_names = [d.strip() for d in args.datasets.split(",")]
    else:
        parser.error("Either --datasets or --tag must be provided")

    if not dataset_names:
        print("No datasets found to process")
        return

    # Process ---------------------------------------------------------------
    results: List[Dict[str, Any]] = []
    for ds_name in dataset_names:
        result = process_dataset(
            ds_name, REPLACE_RULES, args.base_url, headers, dry_run=args.dry_run
        )
        results.append(result)

    # Report ----------------------------------------------------------------
    print_report(results, dry_run=args.dry_run)

    # Optional JSON output --------------------------------------------------
    if args.output:
        output_data = {
            "mode": "dry-run" if args.dry_run else "replace",
            "rules": [{"old": old, "new": new} for old, new in REPLACE_RULES],
            "datasets": results,
            "summary": {
                "datasets_scanned": len(results),
                "items_scanned": sum(r["total_items"] for r in results),
                "items_modified": sum(r["modified_items"] for r in results),
                "total_replacements": sum(r["total_replacements"] for r in results),
            },
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Detailed replacement log saved to {args.output}")


if __name__ == "__main__":
    main()
