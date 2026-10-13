---
name: cost-report-generator
description: Regenera el "Reporte Costos" de AWS (Excel con Resumen, Analisis de Costos, Por_cuenta, Por_servicio, Cuenta_servicio_uso, Analisis y Detalle_facturado) desde el CUR de la cuenta prod de Medical Audit para un rango de fechas. Usar cuando pidan "reporte de costos", "regenerar el reporte de costos", "costos de AWS entre fechas", "actualizar el Excel de costos", "CUR", or in English "cost report", "regenerate the AWS cost report", "build the cost spreadsheet from the CUR", "cost and usage report to Excel".
---

# cost-report-generator

Builds `Reporte Costos - <start> a <end>.xlsx` with the same sheets, layout, formulas and 10 charts as the
template `Reporte Costos - 24 Julio - 27 Agosto.xlsx`, from the prod CUR Parquet files.

## Scope

Project skill for the `adr-medicalAudit-pipelineCDK` repo only. Source of truth lives in the `useful-skills` repo under
`project-skills/pipelinecdk/`; the pipelineCDK repo uses it through the symlink `.claude/skills/cost-report-generator`.
It is deliberately outside `skills/`, so `scripts/install.sh` and the plugin do not install it globally.

## When to use

The user wants the monthly/period cost report (COP, with licensing on Procesamiento) for a date window.
Do not use it for ad hoc cost questions (use the `aws-billing-and-cost-management` skill).

## Parameters

| Flag | Default | Meaning |
|---|---|---|
| `--start YYYY-MM-DD` | required | first day (usage start >= 00:00, CUR timestamps are UTC) |
| `--end YYYY-MM-DD` | required | last day, inclusive (usage start < next day 00:00) |
| `--profile` | `ADR-PROD-MEDICALAUDIT-SENSITIVE` | AWS SSO profile; never falls back to the default profile |
| `--region` | `us-east-1` | |
| `--bucket` / `--prefix` | `adr-prod-medicalaudit-datalake` / `costs/adr-prod-medicalaudit-cost-export-938536499966/data/` | CUR location |
| `--output` | `Reporte Costos - <start> a <end>.xlsx` in the working dir | refuses to overwrite the template |
| `--trm` | `3655.16` | COP per USD. Resumen!C27. Used by Detalle_facturado S, Por_cuenta F, Por_servicio F, Cuenta_servicio_uso K, Resumen F28 |
| `--licensing` | `0.76` | licensing rate on rubro Procesamiento. Resumen!C28. Used by Detalle_facturado U, Por_cuenta H, Por_servicio H, Cuenta_servicio_uso M |
| `--audits` | template value 3241 | `Analisis de Costos` O3:X3 (CANTIDAD DE AUDITORIAS, scenario table) |
| `--set CELL=VALUE` | none | override other numeric constants of `Analisis de Costos`: O8=3655 (TRM of the scenario table, not linked to Resumen), T6=10420000, U8=361051863, U12=3241, V12=5250, AA18=0, AD18=0. Repeatable |
| `--template` | `assets/template_skeleton.xlsx` | package to fill |
| `--soffice` | `soffice` | LibreOffice binary |

Literals inside `Analisis de Costos` formulas are NOT parameters (scenario/forecast model, not CUR data):
3450 (S5, W5), 2600 (P6), 4.5 (U13:AF13), 3650 (U14:AF14, X17, AA17, AD17), 173035*3200 (U17), 9000, 94159,
230282, 35% (X19:AD19), /3, /6.

## Cost rules (source: QuickSight dashboard)

The cost figures follow the rules of the dashboard `adr-prod-medicalaudit-kpis-analysis-v3` (dataset `adr-prod-medicalaudit-costos`),
not the raw CUR cost. Per row, the "Costo Atribuible Auditoria Medica" is `line_item_unblended_cost` times a factor:

| Account | Rule |
|---|---|
| 697030116526 | x 0.7 |
| 276553701208 | full cost only when usage start >= 2026-08-01, else 0 |
| 938536499966, 798406098406, 895890050455, 640122371010 | full cost |
| 329643319012, 639994152617 | full cost only when tag `user_project_id` = P2847, else 0 |

The rules live in `reference.json` (`factor`, `from` per account), so they are data, not code. The row filter does not use the
adjusted value: rows with raw cost 0 are dropped, rows that the rules turn into 0 are kept (row count stays 60,304 for the template window).

Which columns are adjusted and which are raw:
- `Detalle_facturado!R` "Costo AWS (USD)" holds the **attributable** cost (adjusted). The template has no second USD column, so the layout was kept
  and the raw CUR cost is not in the workbook. The script prints both totals at the end (`CUR sin ajuste`). Everything downstream is adjusted:
  T/V/W, `Por_cuenta`, `Por_servicio`, `Cuenta_servicio_uso` (USD, COP, licensing, total), `Resumen`, `Analisis de Costos`, `Analisis`.
- `Detalle_facturado!N` / `Cuenta_servicio_uso!I` "Cantidad reportada por AWS" is the raw usage amount (not adjusted).
- `Detalle_facturado!X` "Regla de atribución" says which rule applied ("Cuenta directa x 0.7", "Cuenta directa desde 2026-08-01", ...).
- Labels such as "Costo AWS total" (Resumen) keep their template text but now show the attributable cost.

COP side, as in the dashboard (TRM 3655.16): Procesamiento = account 798406098406 with `user_cost_center` = MedicalAudit; Plataforma = the rest;
Licenciamiento = Procesamiento x 0.76; Total = the three. Procesamiento + Plataforma = attributable x TRM. The Rubro rule already matches
(only 798406098406 has MedicalAudit rows outside the Pruebas accounts). The Test/Prod platform split is shown by `Resumen!B10`/`H10`
(Rubro "Plataforma - Ambiente de Pruebas" / "Producción y Soporte"); to match the dashboard's "Plataforma Test", account 697030116526 is now
`rubro_pruebas` (as 276553701208), so B10 = dashboard "Costo Plataforma Test" and H10 = "Costo Plataforma Prod".
`--trm` and `--licensing` are unchanged; the dashboard's `Target ...` and "Unidades" parameters and the glosas/reclamaciones filters are not modeled.

Known gap: the dashboard reads from 2026-07-25 (fixed in its SQL) up to yesterday (rolling, exclusive end); the skill takes `--start` and an inclusive `--end`.
To compare against the dashboard, use the same window: its "Fecha Fin" is exclusive, so dashboard 01/08 to 31/08 equals
`--start 2026-08-01 --end 2026-08-30`. Verified: Procesamiento, Licenciamiento and Total match within 6 COP (Plataforma within 546 COP, not yet explained).

## Read-only rules (prod is sensitive)

- Only S3 `ListObjectsV2` and `GetObject` on the CUR Parquet files. No Athena (it writes result files), no Glue, no S3 writes.
- Always pass `--profile` explicitly if not using the default shown above. If the token is expired
  (`ExpiredToken`, `Token has expired`, `LoginRefreshRequired`), ask the user to run `awsl`
  (needs a browser; do not run it yourself).
- Credentials are never printed.

## How to run

```bash
python3 -m venv /tmp/cr-venv && /tmp/cr-venv/bin/pip install -r requirements.txt   # once
/tmp/cr-venv/bin/python .claude/skills/cost-report-generator/cost_report.py \
    --start 2026-07-25 --end 2026-08-27 --output "/path/Reporte Costos - 2026-07-25 a 2026-08-27.xlsx"
```

Run-time needs: Python 3.10+, `boto3 pandas pyarrow openpyxl`, and LibreOffice (`soffice`) so that the cached
values of `Analisis de Costos` are exact. Without `soffice` the file still opens (Excel recalculates on load,
`fullCalcOnLoad` is set) but non-Excel viewers show stale numbers there.

The script prints rows, totals (USD attributable and raw, COP, licensing) and WARNING lines. Read the warnings: they list accounts,
services, categories or window sizes the template cannot represent.

## What it produces

Same 7 sheets and 10 charts. How it is written: the template package is kept and only the `sheetData` of
Detalle_facturado, Por_cuenta, Por_servicio and Cuenta_servicio_uso is regenerated (openpyxl would drop the
charts and cached values). Charts, styles, merged cells, `Analisis de Costos` and `Analisis` formulas, dynamic
array metadata survive. Formula ranges that end in row 60305 (Resumen) and the autofilter/defined names are
resized to the new row count. Cached values are refreshed (Python for the data sheets, LibreOffice for
`Analisis de Costos`, chart caches rewritten). `calcChain` is dropped (Excel rebuilds it).

Derivation of Detalle_facturado (reverse-engineered from the template, 60,304/60,304 rows reproduced; the template's USD used the raw cost, see Cost rules):
- Rows: usage start in window, `line_item_line_item_type` in (Usage, FlatRateSubscription), raw `line_item_unblended_cost` != 0,
  usage account in the 8 accounts of `reference.json`; accounts 329643319012 and 639994152617 only when tag
  `user_project_id` = P2847 ("Cuenta condicionada + P2847").
- Rubro: accounts 276553701208 and 697030116526 -> "Plataforma - Ambiente de Pruebas"; else tag `user_cost_center` = MedicalAudit ->
  "Procesamiento"; else "Plataforma - Producción y Soporte". Licensing applies only to Procesamiento.
- Centro de costo / Proyecto / Aplicación = tags `user_cost_center` / `user_project_id` / `user_app`.
- Servicio AWS, Modelo, Categoria principal, account names and Ambiente come from the static tables in `reference.json`
  (the export has no product_name or pricing_unit column). Unit label ("GB", "requests", "unidad CUR", ...) is a keyword rule in `usage_unit()`.
- Aggregate sheets are rebuilt from the rows, sorted by Total facturable desc, with the template's Spanish layer
  (Cuenta_servicio_uso: Storage/Networking replaced in all text fields of those rows, accents on other categories;
  Por_servicio: partial translation and the template's "Análitica y BI" spelling).

## Known limits

- Accounts of the CUR that are not in `reference.json` are excluded (the export is payer-wide, 23 accounts, 15 unrelated). The script reports their cost.
- Product codes or services missing from `reference.json` get the raw code as name and category "Sin clasificar" (warning). Add them to `reference.json`.
- `Analisis de Costos` uses fixed label lists (services AK13:AK76, categories AO13:AO34, accounts AS13:AS20, models BF13:BF17), a 34-day daily series
  (rows 13-46), and ranges to row 100000. `Analisis` has a fixed 22-category range. The script warns when data falls outside them.
- Template defect kept as is: `Analisis de Costos!AO14` is "Computo" (no accent) but the data says "Cómputo", so Cómputo (COP 9.39M in the template window)
  is missing from the category ranking and charts.
- Rows with equal totals in the aggregate sheets may be in a different order than the template.
- Saved filter states (AWSCloudTrail in Por_servicio, FinOps in Cuenta_servicio_uso), odd scroll positions and the stray "T" cell are not reproduced.
- CUR files are restated by AWS after the fact: the 2026-08 file now differs from the template's snapshot in 14 rows (Enterprise Support and KMS keys; +USD 637.95).
- Narrative cells `Analisis de Costos!A233:A241` use `TEXT()`; the template's cached text did not honor the format string ("70%" for "0.0%"), ours does ("70.1%").
- `Resumen!B21` mentions "controles inferiores" that do not exist in the template; reproduced as is.
- The template file name says 24 Julio but its data starts 2026-07-25 00:00 (UTC timestamps); use `--start 2026-07-25`.

## Maintenance

`make_skeleton.py "<full template>.xlsx"` rebuilds `assets/template_skeleton.xlsx` (template without the bulk rows). The template itself is only read.
