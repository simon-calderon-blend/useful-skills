# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx>=1.1", "lxml", "matplotlib"]
# ///
"""Example: analytics report with cover, KPIs, charts, tables and a landscape appendix.

    uv run examples/report.py out/report.docx

All figures are synthetic. Copy this file and replace the content.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from blend_charts import bar_chart, donut_chart, line_chart  # noqa: E402
from blend_docx import BlendDocument  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "report.docx"

doc = BlendDocument(title="FY26 customer analytics report", author="Blend360")
doc.cover("FY26 customer analytics report", "Retention, revenue and channel mix",
          ["October 2026", "Prepared for: Example Corp leadership team"])
doc.toc()

doc.heading("Executive summary")
doc.paragraph("Revenue grew in every quarter of FY26, driven mainly by **retention** in the existing base "
              "rather than new-customer acquisition. This report covers what changed, why, and what to do next.")
doc.kpis([("+44%", "Revenue, Q1 to Q4"), ("91%", "12-month retention"), ("3.2x", "Return on paid media")])
doc.callout("Retention improved six points after the onboarding redesign. Protecting it is worth more "
            "than any single acquisition channel.", title="Key takeaway", kind="key")

doc.heading("Revenue")
doc.paragraph("Quarterly revenue rose from 4.1 to 5.9 USD million. Growth accelerated in the second half.")
doc.chart(bar_chart(["Q1", "Q2", "Q3", "Q4"], {"Revenue": [4.1, 4.6, 5.2, 5.9]}, highlight="Q4",
                    value_fmt="{:.1f}", axis_label="USD million"),
          caption="Quarterly revenue, FY26 (synthetic data)")

doc.heading("Retention", 2)
doc.chart(line_chart(["Jan", "Mar", "May", "Jul", "Sep", "Nov"],
                     {"New cohorts": [78, 79, 83, 85, 86, 88], "Existing base": [85, 86, 87, 90, 91, 91]},
                     value_fmt="{:.0f}%", axis_label="12-month retention (%)"),
          caption="Retention by customer group (synthetic data)")

doc.heading("Channel mix")
doc.paragraph("Three channels account for most conversions; the others are held for testing.")
doc.chart(donut_chart(["Paid search", "Email", "Partners", "Other"], [38, 31, 21, 10], center_text="4 channels"),
          width_cm=11, caption="Share of conversions by channel (synthetic data)")
doc.table(["Channel", "Spend (USD k)", "Conversions", "Cost per conversion"],
          [["Paid search", "420", "5,300", "79"], ["Email", "95", "4,400", "22"],
           ["Partners", "180", "2,900", "62"], ["Other", "60", "1,400", "43"],
           ["Total", "755", "14,000", "54"]],
          widths=[3, 2, 2, 2.4], align=["l", "r", "r", "r"], total_row=True,
          caption="Spend and conversions by channel (synthetic data)")

doc.heading("Recommendations")
doc.numbered([
    "Keep the **onboarding redesign** and extend it to the partner channel.",
    ("Shift budget toward email and partners:", ["Move 10% of paid search spend in Q1.", "Review cost per conversion monthly."]),
    "Report retention by cohort in every monthly review.",
])
doc.callout("These results use synthetic data and are for layout reference only.", kind="warning")

doc.landscape()
doc.heading("Appendix: monthly detail")
months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
doc.table(["Metric"] + months,
          [["Revenue (USD M)", "1.3", "1.4", "1.4", "1.5", "1.5", "1.6"],
           ["Active customers (k)", "41", "42", "44", "45", "47", "48"],
           ["Retention (%)", "85", "85", "86", "86", "87", "88"]],
          widths=[3, 1, 1, 1, 1, 1, 1], align=["l"] + ["r"] * 6, caption="Monthly metrics, H1 (synthetic data)")

print(doc.save(out))
