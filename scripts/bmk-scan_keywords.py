#!/usr/bin/env python3
"""
Scan Platform datasets for sensitive keywords.

Usage:
    python scan_keywords.py --datasets "ds1,ds2" --keywords "AI_Platform,OpenAI-compatible"
    python scan_keywords.py --tag "Online_Exp_Withtools_260323" --keywords "AI_Platform,msh,Internal_Tool"
"""

import os
import re
import json
import argparse
import urllib.parse
from typing import List, Dict, Any
import requests


def get_auth_headers() -> Dict[str, str]:
    """Get Platform API authentication headers."""
    token = os.environ.get("AuthGateway_ACCESS_TOKEN")
    if not token:
        raise ValueError("AuthGateway_ACCESS_TOKEN environment variable not set")
    return {"X-AuthGateway-Access-Token": token}


def extract_all_strings(obj: Any, path: str = "root") -> List[tuple]:
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


def search_keywords(text: str, keyword_patterns: Dict[str, re.Pattern]) -> List[str]:
    """Check which keywords appear in text (case-insensitive)."""
    found = []
    for keyword, pattern in keyword_patterns.items():
        if pattern.search(text):
            found.append(keyword)
    return found


def get_datasets_by_tag(tag: str, base_url: str, headers: Dict[str, str]) -> List[Dict]:
    """Get all datasets with a specific tag."""
    r = requests.get(
        f"{base_url}/api/datasets",
        headers=headers,
        params={"limit": 100, "tag": tag},
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("datasets", [])


def scan_dataset(
    dataset_name: str,
    keywords: List[str],
    base_url: str,
    headers: Dict[str, str],
    max_items: int = None
) -> Dict[str, Any]:
    """
    Scan a single dataset for sensitive keywords.
    
    Returns:
        {
            "dataset_name": str,
            "total_items": int,
            "hit_count": int,
            "hits": List[{
                "item_id": str,
                "path": str,
                "keywords": List[str],
                "snippet": str
            }]
        }
    """
    keyword_patterns = {k: re.compile(re.escape(k), re.I) for k in keywords}
    
    hits = []
    page = 1
    total_items = 0
    
    while True:
        try:
            r = requests.get(
                f"{base_url}/api/datasets/{urllib.parse.quote(dataset_name, safe='')}/items",
                headers=headers,
                params={"page": page, "limit": 50},
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("items", [])
            
            if not items:
                break
            
            total_items += len(items)
            
            for item in items:
                item_id = item.get("id", "unknown")
                all_strings = extract_all_strings(item, "item")
                
                for path, text in all_strings:
                    found_keywords = search_keywords(text, keyword_patterns)
                    if found_keywords:
                        snippet = text.replace("\n", "\\n")
                        if len(snippet) > 200:
                            snippet = snippet[:197] + "..."
                        hits.append({
                            "item_id": item_id,
                            "path": path,
                            "keywords": found_keywords,
                            "snippet": snippet
                        })
            
            if len(items) < 50:
                break
            if max_items and total_items >= max_items:
                break
            page += 1
            
        except Exception as e:
            print(f"Error scanning {dataset_name} page {page}: {e}")
            break
    
    # Deduplicate hits
    seen = set()
    unique_hits = []
    for h in hits:
        key = (h["item_id"], h["snippet"])
        if key not in seen:
            seen.add(key)
            unique_hits.append(h)
    
    return {
        "dataset_name": dataset_name,
        "total_items": total_items,
        "hit_count": len(unique_hits),
        "hits": unique_hits
    }


def scan_datasets(
    dataset_names: List[str],
    keywords: List[str],
    base_url: str = "https://platform.internal.ai.com"
) -> Dict[str, Any]:
    """
    Scan multiple datasets for sensitive keywords.
    
    Args:
        dataset_names: List of dataset names to scan
        keywords: List of keywords to search for
        base_url: Platform API base URL
    
    Returns:
        {
            "datasets": {dataset_name: result},
            "summary": {
                "total_datasets": int,
                "total_items": int,
                "total_hits": int,
                "keywords_found": set
            }
        }
    """
    headers = get_auth_headers()
    results = {}
    total_items = 0
    total_hits = 0
    all_keywords = set()
    
    for ds_name in dataset_names:
        print(f"Scanning {ds_name}...", flush=True)
        result = scan_dataset(ds_name, keywords, base_url, headers)
        results[ds_name] = result
        total_items += result["total_items"]
        total_hits += result["hit_count"]
        for hit in result["hits"]:
            all_keywords.update(hit["keywords"])
    
    return {
        "datasets": results,
        "summary": {
            "total_datasets": len(dataset_names),
            "total_items": total_items,
            "total_hits": total_hits,
            "keywords_found": sorted(all_keywords)
        }
    }


def print_report(results: Dict[str, Any]):
    """Print a formatted report of scan results."""
    summary = results["summary"]
    
    print("\n" + "=" * 80)
    print("SCAN SUMMARY")
    print("=" * 80)
    print(f"Total datasets scanned: {summary['total_datasets']}")
    print(f"Total items scanned: {summary['total_items']}")
    print(f"Total hits: {summary['total_hits']}")
    print(f"Keywords found: {', '.join(summary['keywords_found'])}")
    print()
    
    # Print table
    print("-" * 80)
    print(f"{'Dataset':<50} {'Items':>8} {'Hits':>8} {'Keywords':<20}")
    print("-" * 80)
    
    for ds_name, result in results["datasets"].items():
        keywords = set()
        for hit in result["hits"]:
            keywords.update(hit["keywords"])
        kw_str = ", ".join(sorted(keywords)) if keywords else "-"
        print(f"{ds_name:<50} {result['total_items']:>8} {result['hit_count']:>8} {kw_str:<20}")
    
    print("-" * 80)
    print()
    
    # Print detailed hits for datasets with hits
    for ds_name, result in results["datasets"].items():
        if result["hit_count"] > 0:
            print(f"\n### {ds_name} ({result['hit_count']} hits)")
            for hit in result["hits"][:10]:  # Show first 10 hits
                print(f"  Item: {hit['item_id']}")
                print(f"  Path: {hit['path']}")
                print(f"  Keywords: {', '.join(hit['keywords'])}")
                print(f"  Snippet: {hit['snippet'][:100]}...")
                print()


def main():
    parser = argparse.ArgumentParser(description="Scan Platform datasets for sensitive keywords")
    parser.add_argument("--datasets", type=str, help="Comma-separated dataset names")
    parser.add_argument("--tag", type=str, help="Tag to filter datasets")
    parser.add_argument("--keywords", type=str, default="AI_Platform,OpenAI-compatible,msh,Internal_Tool",
                        help="Comma-separated keywords to search for")
    parser.add_argument("--output", type=str, help="Output JSON file path")
    parser.add_argument("--base-url", type=str, default="https://platform.internal.ai.com",
                        help="Platform API base URL")
    
    args = parser.parse_args()
    
    keywords = [k.strip() for k in args.keywords.split(",")]
    headers = get_auth_headers()
    
    if args.tag:
        datasets = get_datasets_by_tag(args.tag, args.base_url, headers)
        dataset_names = [d["name"] for d in datasets]
    elif args.datasets:
        dataset_names = [d.strip() for d in args.datasets.split(",")]
    else:
        parser.error("Either --datasets or --tag must be provided")
    
    if not dataset_names:
        print("No datasets found to scan")
        return
    
    results = scan_datasets(dataset_names, keywords, args.base_url)
    print_report(results)
    
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
