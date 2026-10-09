# Charts and figures

Charts in Word documents are static images made with matplotlib (`scripts/blend_charts.py`) and embedded with
`doc.chart(fig, caption=...)` at 220 dpi. Static images keep fonts and layout identical everywhere, but they are
pictures: in Word the user can resize and move them, not edit the data. To change a number, regenerate the
chart from the script (keep it next to the .docx) or put the exact values in a table beside the figure.

## Contents

- [Pick the form](#pick-the-form)
- [Functions](#functions)
- [Color rules](#color-rules)
- [Rules baked in](#rules-baked-in)
- [Custom charts](#custom-charts)
- [Diagrams and screenshots](#diagrams-and-screenshots)

## Pick the form

| Data job | Use | Not |
|---|---|---|
| Compare a few amounts | `bar_chart` (vertical; `horizontal=True` for long labels) | pie |
| Change over time | `line_chart` | bars for dense time series |
| Part of a whole, up to 5 parts | `donut_chart` | 3D, exploded, or more than 5 slices |
| Composition across categories | `bar_chart(stacked=True)` | grouped bars with 4+ series |
| One headline number | `doc.kpis([...])`, not a chart | a one-bar chart |
| Exact values | `doc.table(...)` | a chart with every value labeled |

If the point is one comparison, say it in the caption and highlight the one bar (`highlight="Q4"`).

## Functions

All return a matplotlib `Figure` 6.3 in wide (the text column). Pass it to `doc.chart`.

| Function | Signature |
|---|---|
| `bar_chart` | `(categories, {series: [values]}, horizontal=False, stacked=False, highlight=None, value_fmt="{:,.0f}", axis_label="")` |
| `line_chart` | `(x, {series: [values]}, value_fmt="{:,.0f}", axis_label="")` |
| `donut_chart` | `(labels, values, center_text="", value_fmt="{:.0f}%")` (narrower figure; use `width_cm=11`) |

## Color rules

- **One series:** navy `#003059`. With `highlight`, the focus bar is navy and the rest neutral `#B8C4CC`.
- **Two to five series:** fixed order, never cycled or reordered by value:

  | Slot | Hue | Hex |
  |---|---|---|
  | 1 | Blue | `#2F6FA3` |
  | 2 | Teal | `#00A3A3` |
  | 3 | Amber | `#E39B2D` |
  | 4 | Violet | `#8E6BBF` |
  | 5 | Red | `#C8524B` |

  More than five series raises an error: fold the tail into "Other" or split into small multiples.
- **Why not brand navy and cyan for series:** brand cyan on white is 1.5:1, far too faint for data, and
  navy next to blue is hard to separate. The set above was run through a palette validator (lightness band,
  chroma, color-vision-deficiency separation, normal-vision separation): all checks pass, with worst adjacent
  separation 14.5 (deuteranopia) and 15.5 (normal vision). One warning: amber is 2.3:1 on white, so every
  multi-series chart carries a legend and the line charts label line ends. Never rely on amber alone for thin text.
- **Status colors** (red, amber) mean something; do not reuse them as arbitrary series unless the data is status.
- Text is always ink or slate, never a series color.

## Rules baked in

- No chart title inside the figure: the Word caption (`caption=`) is the title, and it numbers itself.
- No dual axes. Two measures on different scales become two charts.
- Legend above the plot whenever there are 2 or more series; none for one series.
- Value labels only on single-series bars; line charts label the last point of each line (up to 4 lines).
- Thin marks, light horizontal grid only, no box, no left spine, 2 px white gaps between stacked segments.
- Axis labels carry units; `value_fmt` formats labels (`"{:.1f}"`, `"{:.0f}%"`, `"${:,.0f}"`).
- Opaque white background by default, because transparent PNGs show dark fringes on thin lines in some
  PDF viewers. Use `doc.chart(fig, transparent=True)` only when the background mark must show through.
- The font is Montserrat when installed, else DejaVu Sans. Install Montserrat before generating final charts.

## Custom charts

For anything the three functions do not cover (scatter, heatmap, small multiples), use matplotlib directly
and reuse the constants:

```python
import blend_charts as bc
import matplotlib.pyplot as plt
fig, ax = bc._setup((bc.WIDTH_IN, 3.2))       # brand axes: no top/right/left spines, light grid-ready
ax.scatter(x, y, color=bc.NAVY, s=18)
ax.grid(axis="y", color=bc.RULE, linewidth=0.6)
doc.chart(fig, caption="...", alt="Scatter of X against Y; positive trend")
```

Keep to 8 to 9 pt text, `bc.SERIES` for multiple series, a sequential single hue (light to dark navy tints)
for magnitude, and two hues with a neutral midpoint for diverging data.

## Diagrams and screenshots

- Architecture or process diagrams: export from the `diagram-design` or `archify` skills as PNG, brand colors
  navy, cyan and slate, then `doc.image(path, width_cm=14, caption=..., alt=...)`.
- Screenshots: crop tightly, 2x resolution, width 12 to 16 cm, caption says what to look at.
- Every figure gets alt text (`alt=`), or the caption is used.
