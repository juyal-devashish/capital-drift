"""
Reference tables for the synthetic data: association kinds, the reserve components each kind has,
vendors by trade, routine operating services and place names.

Every name here is made up. Town names are real Philadelphia-area places so the demo reads as
local, but no association, vendor or building is real.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentSpec:
    """One kind of building part, as a reserve study would list it."""

    code: str  # short id used in component ids, e.g. ROOF
    category: str
    name: str
    trade: str  # vendor trade that repairs and replaces it
    useful_life: int  # years
    base_cost: float  # replacement cost in study-year dollars, before scaling
    per_unit_cost: float  # added per dwelling unit (or per unit served, for per-building parts)
    per_building: bool  # one component per building (roofs, siding) or one for the site
    repair_words: tuple[str, ...]  # nouns a repair memo might use
    replace_words: tuple[str, ...]  # phrases a replacement memo might use


@dataclass(frozen=True)
class KindSpec:
    kind: str
    label: str
    name_suffixes: tuple[str, ...]
    units: tuple[int, int]
    buildings: tuple[int, int]
    year_built: tuple[int, int]
    components: tuple[ComponentSpec, ...]


def _c(code, category, name, trade, life, base, per_unit, per_building, repair, replace) -> ComponentSpec:
    return ComponentSpec(code, category, name, trade, life, base, per_unit, per_building, repair, replace)


CONDO_MIDRISE = KindSpec(
    kind="condo_midrise",
    label="Mid-rise condominium",
    name_suffixes=("Condominium", "Condominium Association", "Towers Condominium"),
    units=(60, 180),
    buildings=(1, 2),
    year_built=(1968, 2004),
    components=(
        _c(
            "ROOF",
            "roofing",
            "Roof membrane (EPDM)",
            "roofing",
            20,
            60_000,
            900,
            True,
            ("leak at roof drain", "membrane blister", "flashing repair", "seam repair"),
            ("roof membrane replacement", "full tear-off and new EPDM membrane"),
        ),
        _c(
            "ELEV",
            "elevators",
            "Elevator modernization",
            "elevator",
            25,
            180_000,
            600,
            True,
            ("door operator", "leveling fault", "controller board", "entrapment callout"),
            ("elevator modernization", "new controller and machine"),
        ),
        _c(
            "BOIL",
            "mechanical",
            "Central boiler plant",
            "hvac",
            25,
            90_000,
            500,
            True,
            ("burner tune-up", "no heat call", "circulator pump", "low water cutoff"),
            ("boiler replacement", "new high-efficiency boilers"),
        ),
        _c(
            "DHW",
            "plumbing",
            "Domestic water heaters",
            "plumbing",
            12,
            18_000,
            150,
            True,
            ("water heater leak", "relief valve", "no hot water call", "anode rod"),
            ("water heater replacement", "new domestic hot water heaters"),
        ),
        _c(
            "FACADE",
            "envelope",
            "Facade masonry repointing",
            "masonry",
            20,
            70_000,
            700,
            True,
            ("loose brick", "spalling at lintel", "caulk joints", "efflorescence"),
            ("facade repointing project", "masonry restoration"),
        ),
        _c(
            "HALL",
            "interiors",
            "Hallway carpet and paint",
            "painting",
            10,
            25_000,
            250,
            False,
            ("carpet seam", "touch-up paint", "stain removal"),
            ("hallway renovation", "new corridor carpet and paint"),
        ),
        _c(
            "FIRE",
            "life_safety",
            "Fire alarm panel and devices",
            "electrical",
            15,
            35_000,
            200,
            True,
            ("trouble signal", "smoke detector", "panel battery"),
            ("fire alarm system replacement", "new fire alarm panel"),
        ),
        _c(
            "GARAGE",
            "paving",
            "Parking garage deck sealant",
            "paving",
            10,
            40_000,
            200,
            False,
            ("crack at deck", "drain clog", "spalled concrete"),
            ("garage deck traffic coating", "deck sealant replacement"),
        ),
    ),
)

GARDEN = KindSpec(
    kind="garden",
    label="Garden-style apartments and townhomes",
    name_suffixes=("Homeowners Association", "Community Association", "Village Association"),
    units=(80, 260),
    buildings=(3, 6),
    year_built=(1972, 2008),
    components=(
        _c(
            "ROOF",
            "roofing",
            "Asphalt shingle roof",
            "roofing",
            22,
            30_000,
            2_500,
            True,
            ("missing shingles", "leak at valley", "vent boot", "ridge cap"),
            ("roof replacement", "tear-off and new architectural shingles"),
        ),
        _c(
            "SIDING",
            "envelope",
            "Vinyl siding",
            "siding",
            30,
            40_000,
            2_000,
            True,
            ("loose siding panel", "storm damage siding", "J-channel"),
            ("siding replacement", "new vinyl siding"),
        ),
        _c(
            "PAVE",
            "paving",
            "Asphalt paving (mill and overlay)",
            "paving",
            20,
            80_000,
            450,
            False,
            ("pothole patch", "crack fill", "catch basin"),
            ("mill and overlay", "parking lot repaving"),
        ),
        _c(
            "SEAL",
            "paving",
            "Asphalt sealcoat and striping",
            "paving",
            4,
            12_000,
            60,
            False,
            ("restripe handicap spaces", "patch sealcoat"),
            ("sealcoat and restripe", "full lot sealcoating"),
        ),
        _c(
            "DECK",
            "envelope",
            "Wood decks and balconies",
            "carpentry",
            20,
            20_000,
            900,
            True,
            ("rotted deck board", "railing repair", "deck stair"),
            ("deck replacement", "new composite decks"),
        ),
        _c(
            "GUTTER",
            "roofing",
            "Gutters and downspouts",
            "roofing",
            25,
            5_000,
            350,
            True,
            ("gutter cleaning and repair", "downspout reattach", "gutter leak"),
            ("gutter replacement", "new seamless gutters"),
        ),
        _c(
            "PAINT",
            "envelope",
            "Exterior trim paint",
            "painting",
            7,
            15_000,
            300,
            False,
            ("trim touch-up", "door painting", "peeling paint"),
            ("exterior painting project", "full exterior trim repaint"),
        ),
        _c(
            "LIGHT",
            "site",
            "Site lighting poles",
            "electrical",
            20,
            25_000,
            120,
            False,
            ("pole light out", "photocell", "ballast"),
            ("site lighting replacement", "new LED pole lights"),
        ),
    ),
)

SFH_HOA = KindSpec(
    kind="sfh_hoa",
    label="Single-family homeowners association",
    name_suffixes=("Homeowners Association", "Community Association", "Estates HOA"),
    units=(120, 420),
    buildings=(1, 1),
    year_built=(1985, 2012),
    components=(
        _c(
            "ROADS",
            "paving",
            "Private roads (mill and overlay)",
            "paving",
            22,
            150_000,
            700,
            False,
            ("pothole repair", "curb repair", "crack sealing"),
            ("road repaving", "mill and overlay of community roads"),
        ),
        _c(
            "POOL",
            "amenities",
            "Pool resurfacing",
            "pool",
            12,
            60_000,
            0,
            False,
            ("pool crack", "tile repair", "coping stone"),
            ("pool resurfacing", "new pool plaster finish"),
        ),
        _c(
            "PUMP",
            "amenities",
            "Pool pumps and filters",
            "pool",
            10,
            15_000,
            0,
            False,
            ("pump motor", "filter cartridges", "chlorinator"),
            ("pool equipment replacement", "new pumps and filters"),
        ),
        _c(
            "CROOF",
            "roofing",
            "Clubhouse roof",
            "roofing",
            22,
            45_000,
            0,
            False,
            ("clubhouse leak", "missing shingles", "flashing"),
            ("clubhouse roof replacement", "new clubhouse roof"),
        ),
        _c(
            "CHVAC",
            "mechanical",
            "Clubhouse HVAC",
            "hvac",
            15,
            30_000,
            0,
            False,
            ("no cooling call", "compressor", "thermostat"),
            ("clubhouse HVAC replacement", "new rooftop units"),
        ),
        _c(
            "POND",
            "site",
            "Retention pond dredging",
            "landscape",
            15,
            70_000,
            0,
            False,
            ("outfall cleanout", "algae treatment", "erosion at bank"),
            ("pond dredging", "retention basin dredging and restoration"),
        ),
        _c(
            "PLAY",
            "amenities",
            "Playground equipment",
            "carpentry",
            15,
            40_000,
            0,
            False,
            ("swing hardware", "mulch top-up", "slide repair"),
            ("playground replacement", "new play structure"),
        ),
        _c(
            "FENCE",
            "site",
            "Perimeter fencing",
            "carpentry",
            20,
            35_000,
            60,
            False,
            ("fence post", "gate latch", "storm damage fence"),
            ("fence replacement", "new perimeter fence"),
        ),
    ),
)

KINDS: dict[str, KindSpec] = {k.kind: k for k in (CONDO_MIDRISE, GARDEN, SFH_HOA)}

# Vendors by trade. Each vendor has a canonical name and the variants its invoices actually use.
VENDORS: dict[str, tuple[tuple[str, ...], ...]] = {
    "roofing": (
        ("Keystone Roofing & Sheet Metal", "KEYSTONE ROOFING", "Keystone Roofing & S/M Inc."),
        ("Delco Roof Pros LLC", "Delco Roof Pros", "DELCO ROOF PROS, LLC"),
    ),
    "elevator": (("Liberty Lift Services", "LIBERTY LIFT SVC", "Liberty Lift Services Inc"),),
    "hvac": (
        ("Schuylkill Mechanical", "Schuylkill Mech.", "SCHUYLKILL MECHANICAL CONTRACTORS"),
        ("Main Line Heating & Air", "Main Line HVAC", "MAINLINE HEATING AND AIR"),
    ),
    "plumbing": (
        ("Brandywine Plumbing Co.", "Brandywine Plbg", "BRANDYWINE PLUMBING COMPANY"),
        ("Fishtown Pipe Works", "FISHTOWN PIPE WORKS LLC", "Fishtown Pipeworks"),
    ),
    "masonry": (("Old City Masonry", "OLD CITY MASONRY & RESTORATION", "Old City Masonry Inc"),),
    "painting": (("Wissahickon Painting", "WISSAHICKON PAINTING CO", "Wiss. Painting"),),
    "electrical": (
        ("Penn Electric & Alarm", "PENN ELECTRIC AND ALARM", "Penn Elec & Alarm"),
        ("Bright Line Electric", "BRIGHTLINE ELECTRIC LLC", "Bright Line Elec."),
    ),
    "paving": (
        ("Route 1 Paving", "ROUTE ONE PAVING INC", "Rt 1 Paving"),
        ("Tri-County Asphalt", "TRI COUNTY ASPHALT", "Tri-County Asphalt & Sealcoating"),
    ),
    "siding": (("Ridge Exteriors", "RIDGE EXTERIORS LLC", "Ridge Exteriors & Siding"),),
    "carpentry": (("Manayunk Carpentry", "MANAYUNK CARPENTRY", "Manayunk Carpentry & Decks"),),
    "pool": (("Blue Heron Pools", "BLUE HERON POOL SERVICE", "Blue Heron Pools Inc."),),
    "landscape": (
        ("Green Valley Landscaping", "GREEN VALLEY LANDSCAPE", "Green Valley Lndscp"),
        ("Cresheim Grounds", "CRESHEIM GROUNDS MGMT", "Cresheim Grounds Co"),
    ),
    "janitorial": (("Spotless Commons Cleaning", "SPOTLESS COMMONS", "Spotless Commons Cleaning Svc"),),
    "pest": (("Patriot Pest Control", "PATRIOT PEST", "Patriot Pest Control LLC"),),
    "snow": (("Nor'easter Snow Services", "NOREASTER SNOW", "Nor'easter Snow Svc"),),
    "waste": (("Delaware Valley Hauling", "DV HAULING", "Delaware Valley Hauling Co"),),
}

# Routine operating services: (trade, memo templates, typical amount, invoices per year by kind).
# Amounts scale with the association's size inside the generator.
ROUTINE_SERVICES: tuple[tuple[str, tuple[str, ...], float, dict[str, float]], ...] = (
    (
        "landscape",
        ("Grounds maintenance - {month}", "Landscape contract {month}", "Mowing/trimming {month}"),
        2_400,
        {"condo_midrise": 2, "garden": 5, "sfh_hoa": 5},
    ),
    (
        "janitorial",
        ("Common area cleaning {month}", "Janitorial svc - {month}"),
        1_800,
        {"condo_midrise": 4, "garden": 1, "sfh_hoa": 1},
    ),
    (
        "pest",
        ("Quarterly pest service", "Pest control - common areas"),
        350,
        {"condo_midrise": 2, "garden": 2, "sfh_hoa": 1},
    ),
    (
        "snow",
        ("Snow removal - storm of {day}", "Plowing and salting {day}"),
        1_500,
        {"condo_midrise": 1, "garden": 2, "sfh_hoa": 2},
    ),
    (
        "waste",
        ("Bulk trash pickup", "Dumpster service {month}"),
        600,
        {"condo_midrise": 1, "garden": 1, "sfh_hoa": 0.5},
    ),
)

TOWNS: tuple[str, ...] = (
    "Media",
    "Ardmore",
    "Conshohocken",
    "Glenside",
    "Havertown",
    "Lansdale",
    "Malvern",
    "Norristown",
    "Phoenixville",
    "Springfield",
    "Swarthmore",
    "Wayne",
    "West Chester",
    "Manayunk",
    "Roxborough",
    "Chestnut Hill",
    "Fishtown",
    "Haverford",
    "King of Prussia",
    "Drexel Hill",
)

NAME_STEMS: tuple[str, ...] = (
    "Ridley Creek",
    "Wissahickon",
    "Pennypack",
    "Crum Creek",
    "Valley Forge",
    "Darby Run",
    "Cobbs Creek",
    "Tacony",
    "Perkiomen",
    "Skippack",
    "Mill Race",
    "Old Gulph",
    "Chestnut Ridge",
    "Oak Lane",
    "Sycamore Mills",
    "Brandywine Green",
    "Gulph Mills",
    "Bryn Gweled",
    "Cedar Hollow",
    "Stony Run",
    "Hawthorne Park",
    "Briar Glen",
)

PORTFOLIO_NAMES: tuple[str, ...] = (
    "Keystone Community Management",
    "Delaware Valley Residential",
    "Main Line Association Services",
)
