#!/usr/bin/env python3
"""Benchmark report  per-task cross-model scatter.

Finds which tasks are always 0, high-variance, or universally hard.
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
    'k2.5':   [71775],
    'a1sft':  [71943, 71950],
    'a2sft':  [71960, 71961],
    'opus':   [71800],
}
EXPORT_DIR     = '/tmp'
SCORE_NAME     = 'overall'
ITEM_ID_FIELD  = 'query'
CATEGORY_FIELD = 'recall_type_human'   # set to None if no categories

COLORS = {
    'k2.5':  'rgba(55, 83, 209, 1)',
    'a1sft': 'rgba(220, 50, 47, 1)',
    'a2sft': 'rgba(255, 140, 0, 1)',
    'opus':  'rgba(46, 139, 87, 1)',
}

OUTPUT_PREFIX = 'taskview'
TITLE_PREFIX  = 'Task View'

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
# Display names for categories
cat_display = {c: c for c in cat_list}

all_tasks = collect_all_items(raw)
task_data = compute_task_stats(raw)
short_name = make_short_name_fn(LABEL_STRIP_PREFIXES)
model_names = list(BATCHES.keys())

outdir = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Analysis: always-zero, sometimes-zero, high-variance
# ---------------------------------------------------------------------------

print("\n=== Always 0 (all models, all runs) ===")
always_zero = []
for name in sorted(all_tasks):
    all_vals = task_data[name]['_all'][2]
    if max(all_vals) == 0:
        always_zero.append(name)
        print(f"  {get_category(name, categories):8s}  {name}")

print("\n=== Sometimes 0 (at least 1 model avg=0, but not all) ===")
sometimes_zero = []
for name in sorted(all_tasks):
    if name in always_zero:
        continue
    zeros = 0
    for model in model_names:
        avg = task_data[name][model][0]
        if avg == 0:
            zeros += 1
    if zeros > 0:
        models_zero = [m for m in model_names if task_data[name][m][0] == 0]
        sometimes_zero.append((name, models_zero))
        print(f"  {get_category(name, categories):8s}  "
              f"{name:45s}  zero_models={models_zero}")

total_runs = sum(len(runs) for runs in raw.values())
print(f"\n=== Top 20 Highest Cross-Model Variance "
      f"(σ across all {total_runs} runs) ===")
by_var = [(name, task_data[name]['_all'][1], task_data[name]['_all'][0])
          for name in all_tasks]
by_var.sort(key=lambda x: x[1], reverse=True)
for name, std, avg in by_var[:20]:
    per_model = "  ".join(
        f'{m}={task_data[name][m][0]:.2f}±{task_data[name][m][1]:.2f}'
        for m in model_names
    )
    print(f"  σ={std:.3f}  avg={avg:.2f}  "
          f"{get_category(name, categories):8s}  {name:45s}  {per_model}")

# ---------------------------------------------------------------------------
# Charts: one per category
# ---------------------------------------------------------------------------
# For each category: x-axis = tasks (sorted by cross-model avg desc)
# Models as lines, each with mean marker + individual run dots

chart_cats = cat_list if cat_list else ['ALL']

for cat in chart_cats:
    if cat == 'ALL':
        cat_names = sorted(all_tasks)
    else:
        cat_names = [n for n in sorted(all_tasks)
                     if get_category(n, categories) == cat]
    # Sort by cross-model avg descending
    cat_names.sort(key=lambda n: task_data[n]['_all'][0], reverse=True)
    labels = [short_name(n) for n in cat_names]
    n = len(cat_names)
    if n == 0:
        continue

    fig = go.Figure()

    for model in model_names:
        color = COLORS[model]
        dot_color = color.replace('1)', '0.3)')
        runs = raw[model]

        means = [task_data[name][model][0] for name in cat_names]
        stds  = [task_data[name][model][1] for name in cat_names]

        # Mean line
        fig.add_trace(go.Scatter(
            x=labels, y=means, mode='lines+markers',
            line=dict(color=color, width=2.5), marker=dict(size=7),
            name=model,
            error_y=dict(type='data', array=stds, visible=True,
                         thickness=1.5, width=3,
                         color=color.replace('1)', '0.4)'))
            if len(runs) > 1 else None,
        ))

        # Individual run dots
        if len(runs) > 1:
            for ri, run in enumerate(runs):
                run_vals = [run.get(name, 0) for name in cat_names]
                fig.add_trace(go.Scatter(
                    x=labels, y=run_vals, mode='markers',
                    marker=dict(size=3, color=dot_color, symbol='circle'),
                    showlegend=False,
                    hovertext=[f'{model} run{ri+1}: {v:.2f}'
                               for v in run_vals],
                    hoverinfo='text',
                ))

    display = cat_display.get(cat, cat)
    fig.update_layout(
        title=dict(
            text=f'<b>{TITLE_PREFIX}  {display}</b> ({n} tasks)'
                 f'<br><span style="font-size:11px;color:#888">'
                 f'按跨模型均分降序 | 线=model mean | whisker=±1σ '
                 f'| 小点=individual runs</span>',
            font=dict(size=14), x=0.5,
        ),
        xaxis=dict(tickangle=-40, tickfont=dict(size=9)),
        yaxis=dict(title='Score', range=[-0.05, 1.15], dtick=0.1),
        height=500, width=max(700, n * 55 + 200),
        template='plotly_white',
        legend=dict(orientation='h', yanchor='top', y=-0.22,
                    xanchor='center', x=0.5, font=dict(size=11)),
        margin=dict(l=50, r=30, t=75, b=120),
    )

    fname = f'{OUTPUT_PREFIX}_{cat}'
    fig.write_image(f'{outdir}/{fname}.png', scale=2)
    fig.write_html(f'{outdir}/{fname}.html')
    print(f"\n  → {fname}.png")

# ---------------------------------------------------------------------------
# Summary chart: all tasks sorted by cross-model avg
# ---------------------------------------------------------------------------

all_sorted = sorted(all_tasks,
                    key=lambda n: task_data[n]['_all'][0], reverse=True)
labels_all = [short_name(n) for n in all_sorted]
n_all = len(all_sorted)

fig_all = go.Figure()
for model in model_names:
    color = COLORS[model]
    means = [task_data[n][model][0] for n in all_sorted]
    fig_all.add_trace(go.Scatter(
        x=labels_all, y=means, mode='lines+markers',
        line=dict(color=color, width=1.5), marker=dict(size=4),
        name=model,
    ))

fig_all.update_layout(
    title=dict(
        text=f'<b>{TITLE_PREFIX}  All {n_all} Tasks</b>'
             f'<br><span style="font-size:11px;color:#888">'
             f'按跨模型均分降序</span>',
        font=dict(size=14), x=0.5,
    ),
    xaxis=dict(tickangle=-45, tickfont=dict(size=6)),
    yaxis=dict(title='Score', range=[-0.05, 1.1], dtick=0.1),
    height=500, width=max(900, n_all * 23 + 200),
    template='plotly_white',
    legend=dict(orientation='h', yanchor='top', y=-0.15,
                xanchor='center', x=0.5, font=dict(size=11)),
    margin=dict(l=50, r=30, t=75, b=150),
)

fig_all.write_image(f'{outdir}/{OUTPUT_PREFIX}_ALL.png', scale=2)
fig_all.write_html(f'{outdir}/{OUTPUT_PREFIX}_ALL.html')
print(f"\n  → {OUTPUT_PREFIX}_ALL.png")

print("\nDone.")
