# Spec schema (build_report.py)

```json
{
  "variant": "simple | sidebar | scorecard", "lang": "es | en", "title": "...", "eyebrow": "Team · Report type",
  "subtitle": "...", "status": "Draft | Final", "date": "YYYY-MM-DD", "audience": "internal | client",
  "author": "optional", "illustrative": true, "source": "footer source note", "footer": "footer line",
  "description": "meta description (defaults to subtitle)",
  "summary": {"verdict": "one sentence", "text": ["paragraph"], "kpis": [{"value": "87%", "label": "Accuracy", "caption": "Baseline 79%"}]},
  "sections": [{"id": "optional-slug", "title": "...", "blocks": [ ... ]}],
  "appendices": [{"title": "...", "blocks": [ ... ]}]
}
```

Blocks (one key per block):

| Key | Value |
|---|---|
| `p` | text |
| `h3` | text |
| `callout` | `{kind: note\|key\|warning, title, text}` |
| `findings` | list of `{id, severity: critical\|high\|medium\|low\|info, title, text, evidence, recommendation}`; `evidence` is text, `{table}`, `{code}`, `{text}` or a list of those and is mandatory |
| `table` | `{caption, headers, rows, num: [numeric column indexes]}` |
| `code` | `{text, caption}` |
| `recommendations` | list of `{title, text, priority: high\|medium\|low, owner}` |
| `kpis` | list as in summary |
| `score` | `{items: [{label, score, max (5), state: ok\|warn\|bad, state_label}]}` |
| `columns` | list of block lists, rendered side by side |
| `html` | raw markup escape hatch (inline SVG figure); you own accessibility and colors (core tokens only) |

Inline `` `code` `` is supported in text. Anchors: each finding gets `id` lowercased (`f-01`); sections get a slug.
