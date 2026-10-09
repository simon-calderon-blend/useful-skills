# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx>=1.1", "lxml", "matplotlib"]
# ///
"""Example: business letter on the Blend letterhead (also fits memos, proposals and short notes).

    uv run examples/letter.py out/letter.docx

All names and details are placeholders. Copy this file and replace the content.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from blend_docx import BlendDocument  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "letter.docx"

doc = BlendDocument(title="Proposal follow-up", author="Jordan Sample")
doc.letter_head(
    recipient=["Ms. Alex Example", "Director of Analytics", "Example Corp", "100 Sample Street, Suite 4"],
    subject="Re: Customer analytics proposal",
    on="October 9, 2026",
    reference="Reference: EX-2026-014",
)
doc.paragraph("Dear Ms. Example,")
doc.paragraph("Thank you for the time you and your team gave us last week. Below is a summary of what we "
              "agreed and the next steps on our side.")
doc.bullets([
    "**Scope:** retention analysis for the existing customer base, plus a monthly reporting pack.",
    "**Timeline:** kickoff in November, first deliverable six weeks later.",
    "**Team:** one lead analyst and one data engineer, with a fortnightly review.",
])
doc.paragraph("If this matches your understanding, we will send the statement of work for signature this week. "
              "Please [reach out](mailto:jordan.sample@example.com) with any changes.")
doc.signature("Jordan Sample", "Senior Manager, Analytics")

print(doc.save(out))
