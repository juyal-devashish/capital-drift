"""
Render an association's reserve study as a PDF report, the way a reserve-study firm would deliver
it: a cover with the funding summary, a short scope section, the component inventory (one row per
building part, repeated header on every page) and a schedule of planned replacements by year.

Every page carries a SYNTHETIC DATA footer. The firm, the association and every figure are made up.
"""

import textwrap
from collections import defaultdict
from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

from app.synth.generator import SynthAssociation, SynthComponent

FIRM = "Delaware Valley Reserve Consultants (fictional)"
FOOTER = "SYNTHETIC DATA - made up for the Capital Drift Monitor demo"
PAGE = landscape(letter)  # 792 x 612 points
MARGIN = 40
ROW_HEIGHT = 15
FONT, BOLD = "Helvetica", "Helvetica-Bold"

# Inventory columns: header word and its left x. Every cell is left-aligned at its column's x,
# which is also where the reader finds each header word.
COLUMNS = (
    ("Ref", 40),
    ("Component", 120),
    ("Category", 325),
    ("Location", 420),
    ("Life", 495),
    ("Remaining", 545),
    ("Cost", 625),
    ("Planned", 715),
)
KIND_LABELS = {
    "condo_midrise": "Mid-rise condominium",
    "garden": "Garden-style apartments and townhomes",
    "sfh_hoa": "Single-family homeowners association",
}


def category_label(category: str) -> str:
    """How a category is printed: life_safety -> Life safety."""
    return category.replace("_", " ").capitalize()


def money(x: float) -> str:
    return f"${x:,.0f}"


def _footer(c: canvas.Canvas, page_no: int, assoc: SynthAssociation) -> None:
    c.setFont(FONT, 7)
    c.drawString(MARGIN, 20, f"{FOOTER}  |  {assoc.name} reserve study {assoc.study_year}")
    c.drawRightString(PAGE[0] - MARGIN, 20, f"Page {page_no}")


def _cover(c: canvas.Canvas, assoc: SynthAssociation, components: list[SynthComponent]) -> None:
    y = PAGE[1] - 70
    c.setFont(BOLD, 20)
    c.drawString(MARGIN, y, f"Reserve Study {assoc.study_year}")
    y -= 28
    c.setFont(BOLD, 14)
    c.drawString(MARGIN, y, assoc.name)
    y -= 20
    c.setFont(FONT, 10)
    for line in (
        f"{KIND_LABELS[assoc.kind]}, {assoc.town}, Pennsylvania",
        f"{assoc.units} units in {assoc.buildings} building(s), built {assoc.year_built}",
        f"Prepared for the Board of Directors by {FIRM}",
    ):
        c.drawString(MARGIN, y, line)
        y -= 14

    y -= 18
    c.setFont(BOLD, 12)
    c.drawString(MARGIN, y, "Funding summary")
    y -= 18
    c.setFont(FONT, 10)
    total = sum(x.replacement_cost for x in components)
    for label, value in (
        (f"Starting reserve balance (January 1, {assoc.study_year})", money(assoc.reserve_balance_start)),
        ("Recommended annual contribution", money(assoc.annual_contribution)),
        ("Inflation rate assumed", f"{assoc.inflation_rate * 100:.2f}%"),
        (f"Components in this study: {len(components)}", f"total replacement cost {money(total)}"),
    ):
        c.drawString(MARGIN, y, label)
        c.drawString(MARGIN + 330, y, value)
        y -= 15

    y -= 18
    c.setFont(BOLD, 12)
    c.drawString(MARGIN, y, "Scope and method")
    y -= 16
    c.setFont(FONT, 9)
    scope = (
        "This study lists the common-area components the association must repair or replace, with each one's "
        "useful life, remaining life and current replacement cost. Remaining life is estimated from age and a "
        f"visual inspection. Costs are in {assoc.study_year} dollars; future costs grow at the inflation rate "
        "above. Planned year is the study year plus remaining life. Components with a useful life under three "
        "years, and owner-maintained items, are left out."
    )
    for line in textwrap.wrap(scope, 115):
        c.drawString(MARGIN, y, line)
        y -= 12


def _inventory_header(c: canvas.Canvas, y: float, continued: bool) -> float:
    c.setFont(BOLD, 12)
    c.drawString(MARGIN, y, "Component inventory" + (" (continued)" if continued else ""))
    y -= 14
    c.setFont(FONT, 8)
    c.drawString(MARGIN, y, "Life and Remaining are in years. Cost is the replacement cost in study-year dollars.")
    y -= 18
    c.setFont(BOLD, 9)
    for word, x in COLUMNS:
        c.drawString(x, y, word)
    c.line(MARGIN, y - 4, PAGE[0] - MARGIN, y - 4)
    return y - ROW_HEIGHT


def _row(c: canvas.Canvas, y: float, comp: SynthComponent) -> None:
    ref = comp.id.split("-", 1)[1]
    cells = (
        ref,
        comp.name,
        category_label(comp.category),
        comp.location or "-",
        str(comp.useful_life_years),
        str(comp.remaining_life_years),
        money(comp.replacement_cost),
        str(comp.planned_year),
    )
    c.setFont(FONT, 9)
    for (_, x), text in zip(COLUMNS, cells, strict=True):
        c.drawString(x, y, text)


def _schedule(c: canvas.Canvas, y: float, assoc: SynthAssociation, components: list[SynthComponent]) -> None:
    by_year: dict[int, list[SynthComponent]] = defaultdict(list)
    for comp in components:
        by_year[comp.planned_year].append(comp)
    c.setFont(BOLD, 12)
    c.drawString(MARGIN, y, "Planned replacements by year")
    y -= 14
    c.setFont(FONT, 8)
    c.drawString(MARGIN, y, "First replacement of each component only; costs inflated to the year of work.")
    y -= 16
    c.setFont(FONT, 9)
    for year in sorted(by_year):
        items = by_year[year]
        cost = sum(x.replacement_cost * (1 + assoc.inflation_rate) ** (year - assoc.study_year) for x in items)
        names = ", ".join(x.id.split("-", 1)[1] for x in items)
        c.drawString(MARGIN, y, str(year))
        c.drawString(MARGIN + 50, y, money(cost))
        c.drawString(MARGIN + 140, y, names[:110] + ("..." if len(names) > 110 else ""))
        y -= 13
        if y < 50:
            break


def write_study_pdf(assoc: SynthAssociation, components: list[SynthComponent], path: Path) -> None:
    """Write one association's reserve study to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=PAGE, invariant=1)  # invariant: same input, same bytes
    c.setTitle(f"Reserve Study {assoc.study_year} - {assoc.name} (synthetic)")
    c.setAuthor(FIRM)
    page_no = 1
    _cover(c, assoc, components)
    _footer(c, page_no, assoc)
    c.showPage()

    page_no += 1
    y = _inventory_header(c, PAGE[1] - 50, continued=False)
    for comp in components:
        if y < 50:
            _footer(c, page_no, assoc)
            c.showPage()
            page_no += 1
            y = _inventory_header(c, PAGE[1] - 50, continued=True)
        _row(c, y, comp)
        y -= ROW_HEIGHT
    _footer(c, page_no, assoc)
    c.showPage()

    page_no += 1
    _schedule(c, PAGE[1] - 50, assoc, components)
    _footer(c, page_no, assoc)
    c.showPage()
    c.save()


def write_all(associations: list[SynthAssociation], components: list[SynthComponent], out_dir: Path) -> int:
    """One PDF per association at ``out_dir/<association id>.pdf``. Returns the number written."""
    by_assoc: dict[str, list[SynthComponent]] = defaultdict(list)
    for comp in components:
        by_assoc[comp.association_id].append(comp)
    for assoc in associations:
        write_study_pdf(assoc, by_assoc[assoc.id], out_dir / f"{assoc.id}.pdf")
    return len(associations)
