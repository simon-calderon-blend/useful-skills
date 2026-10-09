---
title: Project status brief
subtitle: Data platform migration, week 12
date: October 9, 2026
author: Blend360 delivery team
---

# Summary

The migration is **on track**. Of 40 pipelines, 31 now run on the new platform and the rest are scheduled
for the next two sprints. See the [project board](https://www.example.com/board) for ticket detail.

> [!KEY]
> No pipeline has been lost or duplicated. Cutover can proceed on the planned date.

# Progress

| Workstream | Pipelines | Migrated | Status |
|:--|--:|--:|:-:|
| Ingestion | 12 | 12 | Done |
| Transformation | 18 | 14 | On track |
| Reporting | 10 | 5 | At risk |

```chart
{"type": "bar", "categories": ["Wk 9", "Wk 10", "Wk 11", "Wk 12"],
 "series": {"Migrated pipelines": [18, 23, 27, 31]}, "highlight": "Wk 12",
 "axis_label": "Pipelines", "caption": "Migrated pipelines by week (synthetic data)"}
```

## Risks

1. Reporting depends on a vendor connector that is not yet certified.
2. Two transformation jobs need a schema change:
   - the orders table
   - the customer dimension
3. Cutover freeze overlaps with quarter close.

> [!WARNING]
> Reporting is the only workstream at risk; it needs a decision on the connector by Friday.

## Next steps

- Certify the connector or agree a fallback.
- Migrate the remaining 9 pipelines.
- Run the parallel reconciliation for two weeks.

```
uv run scripts/md_to_docx.py examples/sample.md out/sample.docx --year 2026
```
