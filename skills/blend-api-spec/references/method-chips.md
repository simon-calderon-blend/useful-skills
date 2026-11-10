# Method chip palette (contrast checked 2026-11-10)

| Method | Chip fill | Chip text | Ratio | Block border / tint |
|---|---|---|---|---|
| GET | navy `#053057` | white | 13.4 | navy / 4% navy |
| POST | soft cyan `#A2F3F3` + navy border | navy | 10.6 | navy with cyan left edge / 22% soft cyan |
| PUT, PATCH | `#0E6BA8` (series color of the dashboard shares) | white | 5.7 | same / 6% |
| DELETE | `#B5290F` (bad red from the dashboard proposal) | white | 6.4 | same / 5% |
| HEAD, OPTIONS, TRACE | slate `#314550` | white | 10.0 | same / 5% |
| GET in dark (optional) | cyan `#00EDED` | navy | 9.2 | cyan on dark is allowed |
| POST in dark (optional) | transparent, soft-cyan `#A2F3F3` border | soft cyan | high on `#0B0D0E` | 7% soft cyan; keeps it distinct from the solid-cyan GET chip |

Cyan is never text on a light background, so POST uses a soft-cyan fill with navy text. `#0E6BA8` and `#B5290F` are not in
core `tokens.css` (the validator counts them as derived hex, within its 20 hex allowance).
