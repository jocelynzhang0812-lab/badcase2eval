#!/usr/bin/env python3
"""Benchmark report  per-task variance bars, one chart per category.

Shows which specific tasks are unstable across runs.
Reads Platform JSONL exports via load_orbit_data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import plotly.graph_objects as go

from load_orbit_data import (
    load_batches, discover_categories, get_category,
    collect_all_items, compute_task_stats, make_short_name_fn,
)

# ============ CONFIG  edit this ============
BATCHES = {
    'k2.5 (baseline)': [71775],
    'sft-candidate':    [71943, 71950],
    'opus':             [71800],
}
EXPORT_DIR     = '/tmp'
SCORE_NAME     = 'overall'
ITEM_ID_FIELD  = 'query'
CATEGORY_FIELD = 'recall_type_human'   # set to None if no categories

COLORS = {
    'k2.5 (baseline)': 'rgba(55, 83, 209, 1)',
    'sft-candidate':    'rgba(220, 50, 47, 1)',
    'opus':             'rgba(46, 139, 87, 1)',
}

OUTPUT_PREFIX = 'variance'
TITLE_PREFIX  = 'Task Variance'

# Model to sort tasks by σ (None = first model in BATCHES)
VARIANCE_SORT_MODEL = None

# Prefixes to strip from item IDs for shorter display labels
LABEL_STRIP_PREFIXES = []  # e.g. ['memory-', 'cron-', 'content-creation-', 'feishu-', 'content-']
# ============================================


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

print("Loading data...")
raw, categories = load_batches(BATCHES, EXPORT_DIR, SCORE_NAME,
                               ITEM_ID_FIELD, CATEGORY_FIELD)

cat_list = discover_categories(categories)
cat_display = {c: c for c in cat_list}

all_tasks = collect_all_items(raw)
task_stats = compute_task_stats(raw)
short_name = make_short_name_fn(LABEL_STRIP_PREFIXES)
model_names = list(BATCHES.keys())
sort_model = VARIANCE_SORT_MODEL or model_names[0]

outdir = os.path.dirname(os.path.abspath(__file__))

# Precompute dot colours (30 % opacity)
DOT_COLORS = {m: COLORS[m].replace('1)', '0.3)') for m in model_names}

# ---------------------------------------------------------------------------
# Generate one chart per category (or single 'ALL' if no categories)
# ---------------------------------------------------------------------------

chart_cats = cat_list if cat_list else ['ALL']

for cat in chart_cats:
    if cat == 'ALL':
        cat_names = sorted(all_tasks)
    else:
        cat_names = sorted(n for n in all_tasks
                           if get_category(n, categories) == cat)
    if not cat_names:
        continue

    # Sort by sort_model σ descending (most unstable first)
    cat_names.sort(
        key=lambda n: task_stats[n].get(sort_model, (0, 0, []))[1],
        reverse=True,
    )
    labels = [short_name(n) for n in cat_names]
    n = len(cat_names)

    fig = go.Figure()

    for model in model_names:
        runs = raw[model]
        color = COLORS[model]
        dot_color = DOT_COLORS[model]

        means = [task_stats[name][model][0] for name in cat_names]
        stds  = [task_stats[name][model][1] for name in cat_names]

        # Horizontal bar: mean with error bar = std
        fig.add_trace(go.Bar(
            y=labels, x=means, orientation='h',
            name=model,
            marker_color=color,
            error_x=dict(type='data', array=stds, visible=True,
                         thickness=1.5, width=3,
                         color=color.replace('1)', '0.5)'))
            if len(runs) > 1 else None,
            text=[f'{m:.2f}±{s:.2f}' if s > 0 else f'{m:.2f}'
                  for m, s in zip(means, stds)],
            textposition='outside',
            textfont=dict(size=8),
        ))

        # Individual run dots
        if len(runs) > 1:
            for name_i, name in enumerate(cat_names):
                _, _, vals = task_stats[name][model]
                fig.add_trace(go.Scatter(
                    x=vals, y=[labels[name_i]] * len(vals),
                    mode='markers',
                    marker=dict(size=5, color=dot_color, symbol='diamond'),
                    showlegend=False,
                    hovertext=[f'{model} run{j+1}: {v:.2f}'
                               for j, v in enumerate(vals)],
                    hoverinfo='text',
                ))

    display = cat_display.get(cat, cat)
    fig.update_layout(
        title=dict(
            text=f'<b>{TITLE_PREFIX}  {display}</b> ({n} tasks)'
                 f'<br><span style="font-size:11px;color:#888">'
                 f'按 {sort_model} σ 降序 | bar=mean | whisker=±1σ '
                 f'| ◇=individual runs</span>',
            font=dict(size=14), x=0.5,
        ),
        xaxis=dict(title='Score', range=[-0.05, 1.25], dtick=0.1),
        yaxis=dict(autorange='reversed'),
        barmode='group',
        height=max(400, n * 45 + 150),
        width=850,
        template='plotly_white',
        legend=dict(orientation='h', yanchor='top', y=-0.08,
                    xanchor='center', x=0.5, font=dict(size=11)),
        margin=dict(l=180, r=30, t=75, b=60),
    )

    fname = f'{OUTPUT_PREFIX}_{cat}'
    fig.write_image(f'{outdir}/{fname}.png', scale=2)
    fig.write_html(f'{outdir}/{fname}.html')
    print(f"  → {fname}.png")

# ---------------------------------------------------------------------------
# Top unstable tasks summary
# ---------------------------------------------------------------------------

print(f"\n=== Top 15 Most Unstable Tasks ({sort_model} σ) ===")
all_by_std = [
    (n, task_stats[n][sort_model][1], task_stats[n][sort_model][0],
     task_stats[n][sort_model][2])
    for n in all_tasks if sort_model in task_stats[n]
]
all_by_std.sort(key=lambda x: x[1], reverse=True)
for name, std, avg, vals in all_by_std[:15]:
    cat = get_category(name, categories)
    vals_str = ','.join(f'{v:.2f}' for v in vals)
    print(f'  σ={std:.3f}  avg={avg:.2f}  {cat:8s}  '
          f'{name:45s}  [{vals_str}]')

print("\nDone.")
