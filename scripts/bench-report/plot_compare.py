#!/usr/bin/env python3
"""Benchmark report  side-by-side left/right comparison.

Each panel shows its subject models with shared baselines.
Reads Platform JSONL exports via load_orbit_data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from load_orbit_data import (
    load_batches, discover_categories, build_cat_labels,
    compute_model_cat_runs, stats, color_legend_html,
)

# ============ CONFIG  edit this ============
BATCHES = {
    'k2.5 (baseline)': [71775],
    'a1sft':            [71943, 71950],
    'a2sft':            [71960, 71961],
    'opus':             [71800],
}

# Left panel models and right panel models
LEFT_MODELS  = ['k2.5 (baseline)', 'a1sft', 'opus']
RIGHT_MODELS = ['k2.5 (baseline)', 'a2sft', 'opus']

LEFT_TITLE  = 'a1sft'
RIGHT_TITLE = 'a2sft'

EXPORT_DIR     = '/tmp'
SCORE_NAME     = 'overall'
ITEM_ID_FIELD  = 'query'
CATEGORY_FIELD = 'recall_type_human'   # set to None if no categories

COLORS = {
    'k2.5 (baseline)': 'rgba(55, 83, 209, 1)',
    'a1sft':            'rgba(220, 50, 47, 1)',
    'a2sft':            'rgba(220, 50, 47, 1)',   # same colour for "subject"
    'opus':             'rgba(46, 139, 87, 1)',
}

OUTPUT_PREFIX = 'bench_compare'
TITLE_PREFIX  = 'Benchmark'
# ============================================


# ---------------------------------------------------------------------------
# Plotting helper
# ---------------------------------------------------------------------------

def add_model(fig, vals, name, color, row, col, max_x, n_cols, show_legend):
    """Add a model trace to a subplot cell."""
    if not vals:
        return
    x = list(range(1, len(vals) + 1))
    avg, std = stats(vals)

    # ±1σ band
    if len(vals) > 1:
        upper = [avg + std] * len(x)
        lower = [avg - std] * len(x)
        fig.add_trace(go.Scatter(
            x=x + x[::-1], y=upper + lower[::-1],
            fill='toself', fillcolor=color.replace('1)', '0.1)'),
            line=dict(width=0), showlegend=False, hoverinfo='skip',
        ), row=row, col=col)

    fig.add_trace(go.Scatter(
        x=x, y=vals, mode='lines+markers',
        line=dict(color=color, width=3), marker=dict(size=7),
        showlegend=show_legend, name=name, legendgroup=name,
    ), row=row, col=col)

    fig.add_trace(go.Scatter(
        x=[0.5, max_x + 0.5], y=[avg, avg], mode='lines',
        line=dict(color=color, width=2, dash='dash'),
        showlegend=False, hoverinfo='skip',
    ), row=row, col=col)

    idx = (row - 1) * n_cols + col
    fig.add_annotation(
        x=max_x + 0.3, y=avg, text=f'{avg:.2f}', showarrow=False,
        font=dict(color=color, size=10, family='Arial Black'),
        xref=f'x{idx}', yref=f'y{idx}',
    )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

print("Loading data...")
raw, categories = load_batches(BATCHES, EXPORT_DIR, SCORE_NAME,
                               ITEM_ID_FIELD, CATEGORY_FIELD)

cat_list = discover_categories(categories)
cat_labels = build_cat_labels(raw, categories, cat_list)

# Categories to plot: discovered categories + 'ALL' at the end
cat_list_with_all = cat_list + ['ALL']
cat_label_list = [cat_labels.get(c, c) for c in cat_list_with_all]

model_cat_runs = compute_model_cat_runs(raw, categories, cat_list)
max_runs = max(len(v) for v in raw.values())

# ---------------------------------------------------------------------------
# Build subplot: N rows × 2 cols
# ---------------------------------------------------------------------------

n_rows = len(cat_list_with_all)
n_cols = 2

titles = []
for label in cat_label_list:
    titles.append(f'<b>{LEFT_TITLE}</b> × {label}')
    titles.append(f'<b>{RIGHT_TITLE}</b> × {label}')

fig = make_subplots(rows=n_rows, cols=n_cols,
                    subplot_titles=titles,
                    vertical_spacing=0.05, horizontal_spacing=0.10)

# Collect all values for y-range
all_vals = []
for m in model_cat_runs.values():
    for vals in m.values():
        all_vals.extend(vals)
ymin = max(0, min(all_vals) - 0.05) if all_vals else 0
ymax = min(1.05, max(all_vals) + 0.05) if all_vals else 1

left_set = set(LEFT_MODELS)

for ci, cat in enumerate(cat_list_with_all):
    row = ci + 1

    # Left column
    for model in LEFT_MODELS:
        vals = model_cat_runs[model].get(cat, [])
        show = (ci == 0)  # legend on first row only
        add_model(fig, vals, model, COLORS[model], row, 1,
                  max_runs, n_cols, show)

    # Right column
    for model in RIGHT_MODELS:
        vals = model_cat_runs[model].get(cat, [])
        # Only show legend for models unique to right panel, on first row
        show = (ci == 0 and model not in left_set)
        add_model(fig, vals, model, COLORS[model], row, 2,
                  max_runs, n_cols, show)

legend_html = color_legend_html(
    list(dict.fromkeys(LEFT_MODELS + RIGHT_MODELS)),  # unique, ordered
    COLORS,
)

fig.update_layout(
    title=dict(
        text=f'<b>{TITLE_PREFIX}</b>  {LEFT_TITLE} vs {RIGHT_TITLE}'
             f'<br><span style="font-size:11px;color:#888">'
             f'{legend_html}  '
             f'| 实线=每轮 | 虚线=avg | 色带=±1σ</span>',
        font=dict(size=14), x=0.5,
    ),
    height=max(400, n_rows * 250),
    width=1000,
    template='plotly_white',
    legend=dict(orientation='h', yanchor='top', y=-0.02,
                xanchor='center', x=0.5, font=dict(size=11)),
    margin=dict(l=50, r=60, t=80, b=40),
)

for r in range(1, n_rows + 1):
    for c in [1, 2]:
        fig.update_yaxes(range=[ymin, ymax],
                         title_text='Score' if c == 1 else '',
                         row=r, col=c)
        fig.update_xaxes(title_text='Run' if r == n_rows else '',
                         dtick=1, range=[0.5, max_runs + 0.5],
                         row=r, col=c)

outdir = os.path.dirname(os.path.abspath(__file__))
chart_h = max(400, n_rows * 250)
fig.write_image(f'{outdir}/{OUTPUT_PREFIX}.png', scale=2,
                width=1000, height=chart_h)
fig.write_html(f'{outdir}/{OUTPUT_PREFIX}.html')
print(f"\nSaved → {OUTPUT_PREFIX}.png")

# ---------------------------------------------------------------------------
# Summary comparison
# ---------------------------------------------------------------------------

# Identify the "subject" model unique to each panel
left_only = [m for m in LEFT_MODELS if m not in RIGHT_MODELS]
right_only = [m for m in RIGHT_MODELS if m not in LEFT_MODELS]
shared = [m for m in LEFT_MODELS if m in RIGHT_MODELS]

header_models = left_only + right_only + shared
header = f"{'Category':20s}" + "".join(f'  {m:>14s}' for m in header_models)
if left_only and shared:
    header += f"  {left_only[0]+'-base':>10s}"
if right_only and shared:
    header += f"  {right_only[0]+'-base':>10s}"

print(f"\n=== {LEFT_TITLE} vs {RIGHT_TITLE} ===")
print(header)

for ci, cat in enumerate(cat_list_with_all):
    line = f'{cat_label_list[ci]:20s}'
    model_avgs = {}
    for model in header_models:
        vals = model_cat_runs[model].get(cat, [])
        a, s = stats(vals)
        model_avgs[model] = a
        line += f'  {a:.3f}±{s:.3f}'
    # Deltas vs first shared (baseline) model
    if shared:
        base_avg = model_avgs.get(shared[0], 0)
        for subj in left_only:
            line += f'  {model_avgs.get(subj, 0) - base_avg:+.3f}     '
        for subj in right_only:
            line += f'  {model_avgs.get(subj, 0) - base_avg:+.3f}     '
    print(line)

print("\nDone.")
