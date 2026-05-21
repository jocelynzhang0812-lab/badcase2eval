#!/usr/bin/env python3
"""Benchmark report  2 charts: overall + per-category.

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
    'sft-candidate':    [71943, 71950],
}
EXPORT_DIR = '/tmp'
SCORE_NAME = 'overall'
ITEM_ID_FIELD = 'query'
CATEGORY_FIELD = 'recall_type_human'   # set to None if no categories

COLORS = {
    'k2.5 (baseline)': 'rgba(55, 83, 209, 1)',
    'sft-candidate':    'rgba(220, 50, 47, 1)',
}

OUTPUT_PREFIX = 'bench'        # output filenames: <prefix>_overall.png, etc.
TITLE_PREFIX  = 'Benchmark'   # chart title prefix
# ============================================


# ---------------------------------------------------------------------------
# Plotting helpers (identical to original awareness style)
# ---------------------------------------------------------------------------

def add_model_sub(fig, vals, name, color, row, col, max_x, n_cols):
    """Add a model trace to a subplot cell (per-category chart)."""
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

    # Per-run line + markers
    fig.add_trace(go.Scatter(
        x=x, y=vals, mode='lines+markers',
        line=dict(color=color, width=3), marker=dict(size=7),
        showlegend=(row == 1 and col == 1), name=name, legendgroup=name,
    ), row=row, col=col)

    # Avg dashed line
    fig.add_trace(go.Scatter(
        x=[0.5, max_x + 0.5], y=[avg, avg], mode='lines',
        line=dict(color=color, width=2, dash='dash'),
        showlegend=False, hoverinfo='skip',
    ), row=row, col=col)

    # Avg label
    idx = (row - 1) * n_cols + col
    fig.add_annotation(
        x=max_x + 0.3, y=avg, text=f'{avg:.2f}', showarrow=False,
        font=dict(color=color, size=11, family='Arial Black'),
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
model_cat_runs = compute_model_cat_runs(raw, categories, cat_list)

max_runs = max(len(v) for v in raw.values())
outdir = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Chart 1: Overall
# ---------------------------------------------------------------------------

fig1 = go.Figure()
all_vals = []
for model in BATCHES:
    vals = model_cat_runs[model]['ALL']
    all_vals.extend(vals)
    color = COLORS[model]
    x = list(range(1, len(vals) + 1))
    avg, std = stats(vals)

    if len(vals) > 1:
        upper = [avg + std] * len(x)
        lower = [avg - std] * len(x)
        fig1.add_trace(go.Scatter(
            x=x + x[::-1], y=upper + lower[::-1],
            fill='toself', fillcolor=color.replace('1)', '0.1)'),
            line=dict(width=0), showlegend=False, hoverinfo='skip',
        ))

    fig1.add_trace(go.Scatter(
        x=x, y=vals, mode='lines+markers',
        line=dict(color=color, width=3), marker=dict(size=8),
        name=model,
    ))

    fig1.add_trace(go.Scatter(
        x=[0.5, max_runs + 0.5], y=[avg, avg], mode='lines',
        line=dict(color=color, width=2, dash='dash'),
        showlegend=False, hoverinfo='skip',
    ))

    fig1.add_annotation(
        x=max_runs + 0.35, y=avg, text=f'{avg:.3f}', showarrow=False,
        font=dict(color=color, size=13, family='Arial Black'),
    )

ymin1 = max(0, min(all_vals) - 0.05) if all_vals else 0
ymax1 = min(1.0, max(all_vals) + 0.05) if all_vals else 1

# Build run-count note for subtitle
run_notes = ', '.join(f'{m} n={len(raw[m])}' for m in BATCHES)

fig1.update_layout(
    title=dict(
        text=f'<b>{TITLE_PREFIX}  {cat_labels["ALL"]}</b>'
             f'<br><span style="font-size:11px;color:#888">'
             f'实线=每轮 | 虚线=avg | 色带=±1σ | {run_notes}</span>',
        font=dict(size=15), x=0.5,
    ),
    xaxis=dict(title='Run', dtick=1, range=[0.5, max_runs + 0.5]),
    yaxis=dict(title='Score', range=[ymin1, ymax1], dtick=0.05),
    height=450, width=650, template='plotly_white',
    legend=dict(orientation='h', yanchor='top', y=-0.15,
                xanchor='center', x=0.5, font=dict(size=12)),
    margin=dict(l=50, r=65, t=75, b=70),
)

fig1.write_image(f'{outdir}/{OUTPUT_PREFIX}_overall.png', scale=2)
fig1.write_html(f'{outdir}/{OUTPUT_PREFIX}_overall.html')
print(f"  → {OUTPUT_PREFIX}_overall.png")

# ---------------------------------------------------------------------------
# Chart 2: Per-category grid (skip when no categories)
# ---------------------------------------------------------------------------

if cat_list:
    n_cats = len(cat_list)
    n_cols = min(2, n_cats)
    n_rows = (n_cats + n_cols - 1) // n_cols

    # Build layout_order: (cat, row, col)
    layout_order = []
    for i, cat in enumerate(cat_list):
        r = i // n_cols + 1
        c = i % n_cols + 1
        layout_order.append((cat, r, c))

    # Subplot titles (fill empty cells with '')
    sub_titles = []
    for i in range(n_rows * n_cols):
        if i < n_cats:
            sub_titles.append(f'<b>{cat_labels[cat_list[i]]}</b>')
        else:
            sub_titles.append('')

    fig2 = make_subplots(rows=n_rows, cols=n_cols,
                         subplot_titles=sub_titles,
                         vertical_spacing=0.10, horizontal_spacing=0.12)

    # Y-range from all category values
    all_cat_vals = []
    for model in BATCHES:
        for cat in cat_list:
            all_cat_vals.extend(model_cat_runs[model][cat])

    ymin2 = max(0, min(all_cat_vals) - 0.05) if all_cat_vals else 0
    ymax2 = min(1.05, max(all_cat_vals) + 0.05) if all_cat_vals else 1

    for cat, row, col in layout_order:
        for model in BATCHES:
            vals = model_cat_runs[model][cat]
            add_model_sub(fig2, vals, model, COLORS[model],
                          row, col, max_runs, n_cols)

    legend_html = color_legend_html(BATCHES.keys(), COLORS)
    fig2.update_layout(
        title=dict(
            text=f'<b>{TITLE_PREFIX}  By Category</b>  {legend_html}'
                 f'<br><span style="font-size:11px;color:#888">'
                 f'实线=每轮 | 虚线=avg | 色带=±1σ</span>',
            font=dict(size=15), x=0.5,
        ),
        height=max(450, n_rows * 280),
        width=950,
        template='plotly_white',
        legend=dict(orientation='h', yanchor='top', y=-0.04,
                    xanchor='center', x=0.5, font=dict(size=12)),
        margin=dict(l=50, r=60, t=80, b=50),
    )

    for r in range(1, n_rows + 1):
        for c in range(1, n_cols + 1):
            fig2.update_yaxes(range=[ymin2, ymax2],
                              title_text='Score' if c == 1 else '',
                              row=r, col=c)
            fig2.update_xaxes(title_text='Run' if r == n_rows else '',
                              dtick=1, range=[0.5, max_runs + 0.5],
                              row=r, col=c)

    fig2.write_image(f'{outdir}/{OUTPUT_PREFIX}_categories.png', scale=2,
                     width=950, height=max(450, n_rows * 280))
    fig2.write_html(f'{outdir}/{OUTPUT_PREFIX}_categories.html')
    print(f"  → {OUTPUT_PREFIX}_categories.png")
else:
    print("  (no CATEGORY_FIELD  skipping per-category chart)")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n=== Summary ===")
for model in BATCHES:
    print(f"\n  {model} (n={len(raw[model])}):")
    for cat in cat_list:
        vals = model_cat_runs[model][cat]
        a, s = stats(vals)
        print(f"    {cat_labels[cat]:20s}: {a:.3f}±{s:.3f}")
    vals = model_cat_runs[model]['ALL']
    a, s = stats(vals)
    print(f"    {cat_labels['ALL']:20s}: {a:.3f}±{s:.3f}")

print("\nDone.")
