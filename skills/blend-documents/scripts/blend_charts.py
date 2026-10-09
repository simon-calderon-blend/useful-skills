# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib"]
# ///
"""Brand-styled matplotlib charts for Blend documents.

Each function returns a Figure sized for the A4 text column (6.3 in wide). Pass it to
BlendDocument.chart(fig, caption=...). Rules baked in (see references/charts.md):
  - one series -> navy (or neutral bars with one navy highlight); the series colors
    below are only used from two series up
  - categorical colors are assigned in fixed order and pass a CVD/contrast validator
  - legend whenever there are 2+ series; direct value labels only where they stay readable
  - no dual axes, no chart title inside the figure (the Word caption carries it)
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

NAVY, CYAN, SLATE, INK, RULE, NEUTRAL = "#003059", "#00EDED", "#304550", "#1A1A1A", "#D9D9D4", "#B8C4CC"
# Fixed-order categorical set: blue, teal, amber, violet, red (validated, light surface).
SERIES = ["#2F6FA3", "#00A3A3", "#E39B2D", "#8E6BBF", "#C8524B"]
WIDTH_IN = 6.3

_available = {f.name for f in font_manager.fontManager.ttflist}
FONT = "Montserrat" if "Montserrat" in _available else "DejaVu Sans"


def _setup(figsize):
    plt.rcParams.update({"font.family": FONT, "font.size": 8.5, "text.color": INK,
                         "axes.labelcolor": SLATE, "xtick.color": SLATE, "ytick.color": SLATE})
    fig, ax = plt.subplots(figsize=figsize)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.tick_params(length=0)
    return fig, ax


def _grid(ax, axis="y"):
    ax.grid(axis=axis, color=RULE, linewidth=0.6)
    ax.set_axisbelow(True)


def _colors(n):
    if n > len(SERIES):
        raise ValueError(f"{n} series: fold the tail into 'Other' or use small multiples (max {len(SERIES)})")
    return [NAVY] if n == 1 else SERIES[:n]


def _legend(ax, n):
    if n > 1:
        ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=n, fontsize=8,
                  handlelength=1, handleheight=1, columnspacing=1.6)


def bar_chart(categories, series, *, horizontal=False, stacked=False, highlight=None, value_fmt="{:,.0f}",
              axis_label="", figsize=(WIDTH_IN, 3.2)):
    """series: {name: [values]}. highlight: a category to emphasize (single series only)."""
    names = list(series)
    fig, ax = _setup(figsize)
    n, k = len(categories), len(names)
    pos = list(range(n))
    cols = _colors(k)
    bar_cols = None
    if k == 1 and highlight is not None:
        bar_cols = [NAVY if c == highlight else NEUTRAL for c in categories]
    group = 0.55 if stacked else 0.7
    thickness = group if stacked else group / k
    bottoms = [0] * n
    for i, name in enumerate(names):
        vals = series[name]
        offs = [p + (0 if stacked else (i - (k - 1) / 2) * thickness) for p in pos]
        kw = dict(color=bar_cols or cols[i], label=name, edgecolor="white", linewidth=1.0 if stacked else 0)
        if horizontal:
            bars = ax.barh(offs, vals, height=thickness, left=bottoms if stacked else None, **kw)
        else:
            bars = ax.bar(offs, vals, width=thickness, bottom=bottoms if stacked else None, **kw)
        if k == 1:  # direct labels only when a single series keeps them uncluttered
            ax.bar_label(bars, labels=[value_fmt.format(v) for v in vals], padding=3, fontsize=8, color=INK)
        if stacked:
            bottoms = [b + v for b, v in zip(bottoms, vals)]
    if horizontal:
        ax.set_yticks(pos, categories)
        ax.invert_yaxis()
        _grid(ax, "x")
        ax.set_xlabel(axis_label)
        ax.margins(x=0.12)
    else:
        ax.set_xticks(pos, categories)
        _grid(ax, "y")
        ax.set_ylabel(axis_label)
        ax.margins(y=0.12)
    _legend(ax, k)
    fig.tight_layout()
    return fig


def line_chart(x, series, *, value_fmt="{:,.0f}", axis_label="", figsize=(WIDTH_IN, 3.2)):
    """series: {name: [values]} over shared x. Up to 4 series also get a direct label at the line end."""
    names = list(series)
    fig, ax = _setup(figsize)
    for name, color in zip(names, _colors(len(names))):
        vals = series[name]
        ax.plot(x, vals, color=color, linewidth=2, marker="o", markersize=4, markeredgecolor="white",
                markeredgewidth=1, label=name)
        if len(names) <= 4:
            ax.annotate(value_fmt.format(vals[-1]), (x[-1], vals[-1]), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8, color=INK)
    _grid(ax, "y")
    ax.set_ylabel(axis_label)
    ax.margins(x=0.08, y=0.15)
    _legend(ax, len(names))
    fig.tight_layout()
    return fig


def donut_chart(labels, values, *, center_text="", value_fmt="{:.0f}%", figsize=(4.2, 3.4)):
    """Part-to-whole for up to 5 parts. Labels sit beside the ring so color is never the only cue."""
    plt.rcParams.update({"font.family": FONT})
    fig, ax = plt.subplots(figsize=figsize)
    total = sum(values)
    wedges, _ = ax.pie(values, colors=_colors(len(values)), startangle=90, counterclock=False,
                       wedgeprops=dict(width=0.38, edgecolor="white", linewidth=2))
    ax.legend(wedges, [f"{l}  {value_fmt.format(100 * v / total)}" for l, v in zip(labels, values)],
              frameon=False, loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8.5)
    if center_text:
        ax.text(0, 0, center_text, ha="center", va="center", fontsize=15, fontweight="bold", color=NAVY)
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig
