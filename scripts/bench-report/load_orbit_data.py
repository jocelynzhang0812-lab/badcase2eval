#!/usr/bin/env python3
"""Shared data loading from Platform JSONL exports.

Platform export format (one JSON object per line):
    {
      "id": "task-uuid",
      "seq": 1,
      "input": {"query": "...", "ground_truth": "...", "recall_type_human": "必须", ...},
      "output": "model response...",
      "scores": [
        {"name": "overall", "rawValue": 0.8, "normalizedValue": 0.8},
        {"name": "tool_count", "rawValue": 5, "normalizedValue": null}
      ],
      "status": "exported",
      "batchId": 71950
    }

Key mapping:
    Mangrove "task"      → Platform "batch"  (one complete run)
    Mangrove "container" → Platform "task"   (one line in JSONL)
    container name       → input[item_id_field]
    container score      → scores[score_name].rawValue
"""
import json
import os
import re


# ---------------------------------------------------------------------------
# Core loading
# ---------------------------------------------------------------------------

def load_batch(batch_id, export_dir, score_name, item_id_field, category_field=None):
    """Load a single batch JSONL export.

    Returns:
        run:  dict  {item_id: score_value}
        cats: dict  {item_id: category_name}  (empty if category_field is None)
    """
    path = os.path.join(export_dir, f'export_{batch_id}.jsonl')
    run = {}
    cats = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            inp = item.get('input', {})

            item_id = inp.get(item_id_field)
            if item_id is None:
                continue

            # Find requested score by name
            score_val = None
            for s in item.get('scores', []):
                if s['name'] == score_name:
                    score_val = s.get('rawValue')
                    break
            if score_val is None:
                continue

            run[item_id] = score_val
            if category_field:
                cats[item_id] = inp.get(category_field, 'ALL')
    return run, cats


def load_batches(batches_config, export_dir, score_name, item_id_field,
                 category_field=None):
    """Load all batches for every model.

    Args:
        batches_config: {model_name: [batch_id, ...]}
        export_dir:     directory containing export_<id>.jsonl files
        score_name:     which score metric to extract
        item_id_field:  field in ``input`` to use as item identifier
        category_field: field in ``input`` for category grouping, or None

    Returns:
        raw:        {model_name: [run_dict, ...]}
        categories: {item_id: category_name}  (empty dict if no category_field)
    """
    raw = {}
    categories = {}
    for model, batch_ids in batches_config.items():
        raw[model] = []
        for bid in batch_ids:
            print(f'  Loading batch {bid} for {model}...')
            run, cats = load_batch(bid, export_dir, score_name,
                                   item_id_field, category_field)
            if not run:
                print(f'    WARNING: batch {bid} yielded 0 scored items')
            raw[model].append(run)
            categories.update(cats)
    return raw, categories


# ---------------------------------------------------------------------------
# Category helpers
# ---------------------------------------------------------------------------

def discover_categories(categories):
    """Return sorted list of unique category names from *categories* dict.

    Returns empty list if *categories* is empty (i.e. no CATEGORY_FIELD).
    """
    if not categories:
        return []
    return sorted(set(categories.values()))


def get_category(item_id, categories):
    """Category for *item_id*, defaults to ``'ALL'``."""
    return categories.get(item_id, 'ALL')


def build_cat_labels(raw, categories, cat_list):
    """Build ``{cat: 'CatName (N题)'}`` display labels with item counts.

    Always includes an ``'ALL'`` key with the total count.
    """
    all_items = collect_all_items(raw)
    cat_counts = {}
    for item_id in all_items:
        cat = get_category(item_id, categories)
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    labels = {}
    for cat in cat_list:
        labels[cat] = f'{cat} ({cat_counts.get(cat, 0)}题)'
    labels['ALL'] = f'Overall ({len(all_items)}题)'
    return labels


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def stats(vals):
    """Return ``(mean, std)`` for a list of numbers."""
    if not vals:
        return 0, 0
    avg = sum(vals) / len(vals)
    std = (sum((v - avg) ** 2 for v in vals) / len(vals)) ** 0.5
    return avg, std


# ---------------------------------------------------------------------------
# Aggregation helpers used by multiple scripts
# ---------------------------------------------------------------------------

def collect_all_items(raw):
    """Collect the set of all item IDs across every model and run."""
    items = set()
    for runs in raw.values():
        for run in runs:
            items.update(run.keys())
    return items


def compute_model_cat_runs(raw, categories, cat_list):
    """Compute per-model per-category per-run average scores.

    Returns:
        ``{model: {cat: [run_avg, ...], 'ALL': [run_avg, ...]}}``
    """
    result = {}
    for model, runs in raw.items():
        result[model] = {}
        for cat in cat_list + ['ALL']:
            run_avgs = []
            for run in runs:
                if cat == 'ALL':
                    scores = list(run.values())
                else:
                    scores = [v for k, v in run.items()
                              if get_category(k, categories) == cat]
                if scores:
                    run_avgs.append(sum(scores) / len(scores))
            result[model][cat] = run_avgs
    return result


def compute_task_stats(raw):
    """Per-task per-model stats.

    Returns:
        ``{item_id: {model: (avg, std, [vals]), '_all': (avg, std, [vals])}}``
    """
    all_items = collect_all_items(raw)
    task_data = {}
    for name in sorted(all_items):
        task_data[name] = {}
        all_vals = []
        for model, runs in raw.items():
            vals = [r.get(name, 0) for r in runs]
            avg, std = stats(vals)
            task_data[name][model] = (avg, std, vals)
            all_vals.extend(vals)
        avg, std = stats(all_vals)
        task_data[name]['_all'] = (avg, std, all_vals)
    return task_data


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def make_short_name_fn(strip_prefixes=None):
    """Return a function that strips known prefixes for shorter labels."""
    prefixes = strip_prefixes or []

    def short_name(name):
        for p in prefixes:
            if name.startswith(p):
                return name[len(p):]
        return name

    return short_name


def rgba_to_hex(rgba_str):
    """Convert ``'rgba(R, G, B, A)'`` to ``'#RRGGBB'``."""
    m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', rgba_str)
    if m:
        return f'#{int(m.group(1)):02X}{int(m.group(2)):02X}{int(m.group(3)):02X}'
    return '#000000'


def color_legend_html(models, colors):
    """Inline HTML colour legend for chart subtitles."""
    parts = []
    for m in models:
        hx = rgba_to_hex(colors.get(m, 'rgba(0,0,0,1)'))
        parts.append(f'<span style="color:{hx}">■ {m}</span>')
    return '  '.join(parts)
