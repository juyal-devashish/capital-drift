"""
Read a reserve study PDF: the funding summary and the component inventory.

Lines are rebuilt from pdfplumber word boxes grouped by vertical position, so every component
keeps its page and bounding box as evidence. The table logic is specific to reserve studies:

1. **Funding summary**: label lines anywhere in the report ("Starting reserve balance ...",
   "Recommended annual contribution", "Inflation rate assumed") followed by an amount.
2. **Inventory**: a header line containing the column words (Ref, Component, Category, Location,
   Life, Remaining, Cost, Planned) sets each column's left edge. Each following line is a row:
   every word goes to the column whose left edge is the closest one at or before it. The table
   ends at the first line that doesn't parse, and starts again at the next header (the header
   repeats on every page).

A row that has the right shape but bad values (a non-numeric life, say) becomes a warning, never a
silent skip, so a reader of the result can see what was not loaded.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

HEADER = ("Ref", "Component", "Category", "Location", "Life", "Remaining", "Cost", "Planned")
_COLUMN_SLACK = 3.0  # points a word may start left of its column edge and still belong to it
_LINE_TOLERANCE = 2.5  # points: words whose tops differ by less than this are on one line
_MONEY_RE = re.compile(r"^\$?([\d,]+(?:\.\d+)?)$")
_PERCENT_RE = re.compile(r"^([\d.]+)%$")
_FUNDING = {
    "reserve_balance_start": re.compile(r"^Starting reserve balance\b"),
    "annual_contribution": re.compile(r"^Recommended annual contribution\b"),
    "inflation_rate": re.compile(r"^Inflation rate assumed\b"),
}
_NO_LOCATION = {"-", "—", "n/a", ""}


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float


def group_lines(words: list[dict]) -> list[list[Word]]:
    """Group pdfplumber words into lines (top-to-bottom), each sorted left-to-right."""
    ws = sorted(
        (Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"]) for w in words), key=lambda w: (round(w.top), w.x0)
    )
    lines: list[list[Word]] = []
    for w in ws:
        if lines and abs(lines[-1][0].top - w.top) <= _LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


@dataclass
class ParsedComponent:
    ref: str  # e.g. ROOF-B, unique within the study
    name: str
    category: str  # snake_case code, e.g. life_safety
    location: str | None
    useful_life_years: int
    remaining_life_years: int
    replacement_cost: float
    planned_year: int
    page: int  # 1-based
    bbox: tuple[float, float, float, float]  # x0, top, x1, bottom of the whole row


@dataclass
class ParsedStudy:
    path: str
    funding: dict[str, float] = field(default_factory=dict)
    components: list[ParsedComponent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _money(text: str) -> float | None:
    m = _MONEY_RE.match(text)
    return float(m.group(1).replace(",", "")) if m else None


def _header_edges(line: list[Word]) -> list[float] | None:
    """Left edge of each column if this line is the inventory header, else None."""
    words = [w.text for w in line]
    if words != list(HEADER):
        return None
    return [w.x0 for w in line]


def _row_cells(line: list[Word], edges: list[float]) -> list[str]:
    cells: list[list[str]] = [[] for _ in edges]
    for w in line:
        index = max((i for i, edge in enumerate(edges) if w.x0 >= edge - _COLUMN_SLACK), default=0)
        cells[index].append(w.text)
    return [" ".join(c) for c in cells]


def _component(cells: list[str], page_no: int, line: list[Word]) -> ParsedComponent:
    """Build a component from one row's cells. Raises ValueError on any bad cell."""
    ref, name, category, location, life, remaining, cost, planned = cells
    if not ref or not name or not category:
        raise ValueError("empty ref, component or category")
    replacement_cost = _money(cost)
    if replacement_cost is None:
        raise ValueError(f"cost {cost!r} is not an amount")
    return ParsedComponent(
        ref=ref,
        name=name,
        category=category.lower().replace(" ", "_"),
        location=None if location.lower() in _NO_LOCATION else location,
        useful_life_years=int(life),
        remaining_life_years=int(remaining),
        replacement_cost=replacement_cost,
        planned_year=int(planned),
        page=page_no,
        bbox=(
            round(min(w.x0 for w in line), 1),
            round(min(w.top for w in line), 1),
            round(max(w.x1 for w in line), 1),
            round(max(w.bottom for w in line), 1),
        ),
    )


def _funding_value(key: str, line: list[Word]) -> float | None:
    last = line[-1].text
    if key == "inflation_rate":
        m = _PERCENT_RE.match(last)
        return round(float(m.group(1)) / 100, 6) if m else None
    return _money(last)


def parse_reserve_study(path: Path) -> ParsedStudy:
    """Read one reserve study PDF. Never raises on content problems; they go to ``warnings``."""
    study = ParsedStudy(path=str(path))
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            edges: list[float] | None = None
            for line in group_lines(page.extract_words(keep_blank_chars=False, use_text_flow=False)):
                text = " ".join(w.text for w in line)
                for key, pattern in _FUNDING.items():
                    if key not in study.funding and pattern.match(text):
                        value = _funding_value(key, line)
                        if value is None:
                            study.warnings.append(f"page {page_no}: can't read the amount in {text!r}")
                        else:
                            study.funding[key] = value
                header = _header_edges(line)
                if header:
                    edges = header
                    continue
                if edges is None:
                    continue
                cells = _row_cells(line, edges)
                if not all(cells[i] for i in (0, 1, 4, 5, 6, 7)):
                    edges = None  # not a row: the table has ended
                    continue
                try:
                    study.components.append(_component(cells, page_no, line))
                except ValueError as exc:
                    study.warnings.append(f"page {page_no}: skipped row {text!r}: {exc}")

    refs = [c.ref for c in study.components]
    for ref in sorted({r for r in refs if refs.count(r) > 1}):
        study.warnings.append(f"component ref {ref} appears more than once")
    for key in _FUNDING:
        if key not in study.funding:
            study.warnings.append(f"funding summary has no {key.replace('_', ' ')}")
    if not study.components:
        study.warnings.append("no component inventory found")
    return study
