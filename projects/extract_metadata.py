"""Build final_projects.csv from the Gradescope export in ./pdfs.

- Authors come from pdfs/submission_metadata.yml (names only; emails, SIDs,
  and scores are deliberately not copied into the CSV).
- Titles are extracted from each PDF: the largest title-sized text block on
  the first few pages, with template headers ("Extended Abstract", "CS 224R
  Final Report", ...) filtered out. Hand fixes for stubborn PDFs go in
  OVERRIDES below.
- Teams that submitted the same report twice are merged into one row.
- Project type (Default/Custom) and mentor TA come from the staff sheet
  pdfs-adjacent ta_assignments_raw.txt (kept out of git: it contains
  student emails), matched to submissions by member names.

Output columns: PDF (path relative to this directory), Type, Title,
Authors, Mentor TA. Review the CSV (and tweak OVERRIDES / TA_OVERRIDES)
before running generate_page.py.
"""
import csv
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median

import fitz
import yaml

ROOT = Path(__file__).parent
PDF_ROOT = ROOT / "pdfs"
OUT_CSV = ROOT / "final_projects.csv"
TA_SHEET = ROOT / "ta_assignments_raw.txt"

# submission id -> (Type, Mentor TA), for rows the name matcher can't
# resolve (names on the TA sheet that differ too much from the roster)
TA_OVERRIDES = {
    "416260391": ("Custom", "Jonathan Yang"),    # "James" vs "JP Paul" McAnally
    "416253945": ("Default", "Anikait Singh"),   # Nate/Nathaniel Demchak team
}

# Submissions excluded from the public page at the authors' request
# (opt-out form, June 2026). Keyed by Gradescope submission id.
OPT_OUT_IDS = {
    "415445122", "415577309", "415708635", "416014905", "416033892",
    "416056827", "416101451", "416114701", "416122945", "416140355",
    "416158751", "416166578", "416167478", "416169645", "416175234",
    "416179862", "416198286", "416224092", "416225772", "416226434",
    "416237845", "416242187", "416249833", "416250401", "416251102",
    "416252554", "416253422", "416254377", "416257401", "416261521",
    "416267564", "416270209", "416271524", "416273125", "416273385",
    "416274832", "416276115", "416276694", "416276754", "416276960",
    "416281264", "416281688", "416282078", "416283030", "416283033",
    "416284091", "416284161", "416286352", "416287375", "416287462",
    "416287507", "416287710", "416288023", "416288034", "416288109",
    "416288210", "416288249", "416288264", "416288267", "416288334",
    "416288360", "416288417", "416288431", "416288434", "416288439",
    "416288547", "416288549", "416288552", "416288582", "416288588",
    "416288756", "416332047",
}
# Authors who asked for the report to be withheld but the title kept
TITLE_ONLY_IDS = {"416288758"}

# folder name -> title, for PDFs the heuristics cannot crack
OVERRIDES = {
    "Abhishek Bharani submission_416136219":
        "Systems-Aware Off-Policy RLOO: Amortizing Sampling Cost via K-Reuse",
    # bylines that differ from the Gradescope names sneak past the
    # author-line filter and get glued on as subtitles
    "Charlie Stringfellow submission_416288417":
        "Where the Length Penalty Enters GRPO: Placement, Collapse, and a Cure",
    "Olufeolu Oluwapelumi Kolawole Karn Kaura Nihar Mudigonda submission_416286897":
        "MARC: Multi-Agent Role Coordination",
}

DASH = r"\s:–—\-"
NOISE_PATTERNS = [
    re.compile(r"^extended\s+abstract$", re.I),
    re.compile(rf"^(stanford\s+)?cs\s*\.?\s*224r\b[{DASH}]*(deep\s+reinforcement\s+learning)?[{DASH}]*"
               rf"((default|custom|final)\s+)?(project|report|paper|milestone|reports?)?[{DASH}]*"
               rf"((final|project)\s*)?(project|report|paper|milestone)?\s*$", re.I),
    re.compile(r"^(final\s+(project|report|paper)(\s+report)?|project\s+(report|milestone|proposal)|final\s+project\s+report)$", re.I),
    re.compile(r"^stanford\s+university", re.I),
    re.compile(r"^department\s+of", re.I),
    re.compile(r"^(spring|winter|autumn|fall)\s+20\d\d$", re.I),
    re.compile(r"^\S+@\S+\.\S+$"),
    re.compile(r"^(january|february|march|april|may|june|july)\s+\d{1,2},?\s+20\d\d$", re.I),
    re.compile(r"^confidential$", re.I),
    re.compile(r"^(team\s+members?|email|mentor|key\s+information)\b", re.I),
]
SECTION_HEADERS = re.compile(
    r"^(\d+\.?\s*)?(abstract|introduction|motivation(\s+and\s+problem)?|method(s|ology)?|background|"
    r"related\s+works?|contents|results|experiments?|discussion|conclusions?|acknowledge?ments|"
    r"references|appendix|project\s+member\s+contributions?)\b[.:]?\s*$",
    re.I,
)
# prefixes to strip off an otherwise-good title
STRIP_PREFIXES = [
    re.compile(rf"^extended\s+abstract[{DASH}]+", re.I),
    re.compile(rf"^project\s+title[{DASH}]+", re.I),
    re.compile(rf"^title[{DASH}]+", re.I),
    re.compile(rf"^(stanford\s+)?cs\s*\.?\s*224r\b[{DASH}]*"
               rf"((default|custom|final)\s+)?(project|report|paper|milestone)?[{DASH}]+", re.I),
]


def is_noise(text):
    t = text.strip()
    return any(p.match(t) for p in NOISE_PATTERNS)


def is_section_header(text):
    return bool(SECTION_HEADERS.match(text.strip()))


def name_variants(authors):
    """['Henok Mikael Tewolde', ...] -> variants like 'Henok Tewolde' too."""
    variants = []
    for name in authors:
        parts = name.split()
        variants.append(name.lower())
        if len(parts) > 2:
            variants.append(f"{parts[0]} {parts[-1]}".lower())
    return variants


def is_author_line(text, variants):
    t = text.lower()
    return any(v in t for v in variants)


def looks_like_affiliation(text):
    return bool(re.search(r"@|\buniversity\b|\bdepartment\b|\bstanford\b|\binc\.?\b", text, re.I))


def line_text_with_case(line, line_size):
    """Rebuild text from spans, lowercasing small-caps spans (ICLR templates)."""
    parts = []
    for s in line["spans"]:
        t = s["text"]
        if s["size"] < line_size * 0.88 and t.isupper():
            t = t.lower()
        parts.append(t)
    return "".join(parts)


def page_lines(page):
    """Return [(y0, size, text)] for one page, in reading order."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type", 0) != 0:
            continue
        for line in block["lines"]:
            raw = "".join(s["text"] for s in line["spans"]).strip()
            if not raw:
                continue
            size = max(s["size"] for s in line["spans"])
            text = line_text_with_case(line, size).strip()
            out.append((line["bbox"][1], size, text))
    out.sort(key=lambda l: l[0])
    return out


def join_lines(texts):
    """Join wrapped lines, fixing hyphenation ("SIMULA- TORS")."""
    text = ""
    for t in texts:
        if text.endswith("-"):
            text = text[:-1] + t
        elif text:
            text += " " + t
        else:
            text = t
    return re.sub(r"\s+", " ", text).strip()


def title_from_big_text(lines, page_h, variants):
    """Title-sized text near the top of a page, with an optional subtitle."""
    body = median(l[1] for l in lines)
    threshold = max(11.3, body + 1.0)
    usable = [
        l for l in lines
        if l[0] < page_h * 0.75
        and not is_noise(l[2]) and not is_section_header(l[2])
        and not is_author_line(l[2], variants)
    ]
    big = [l for l in usable if l[1] >= threshold]
    if not big:
        return None
    first = big[0]
    picked = [first]
    for l in big[1:]:
        if abs(l[1] - first[1]) > 1.2:
            break
        if l[0] - picked[-1][0] > first[1] * 3.0:
            break
        picked.append(l)
    title = join_lines([l[2] for l in picked])
    if len(title) < 8 or len(title) > 250 or len(picked) > 5:
        return None

    # a short display title may have a smaller-font subtitle right below it
    if len(title) < 70:
        below = [
            l for l in usable
            if l[0] > picked[-1][0] and l[1] >= 11.3 and l[1] <= first[1] - 1.2
        ]
        sub = []
        for l in below:
            anchor = picked[-1] if not sub else sub[-1]
            if l[0] - anchor[0] > first[1] * 2.6:
                break
            if abs(l[1] - below[0][1]) > 0.6 or looks_like_affiliation(l[2]):
                break
            sub.append(l)
            if len(sub) == 2:
                break
        if sub:
            subtitle = join_lines([l[2] for l in sub])
            if 10 <= len(subtitle) <= 160:
                sep = " " if title.rstrip().endswith((":", "—", "–", "-", "?", "!")) else ": "
                title = title.rstrip() + sep + subtitle
    return title


def title_fallback_first_line(lines, page_h, variants):
    """First plausible line near the top of page 1, joining its wraps."""
    usable = [
        (y, s, t) for (y, s, t) in lines
        if y < page_h * 0.5
        and not is_noise(t) and not is_section_header(t)
        and not is_author_line(t, variants)
        and not looks_like_affiliation(t)
    ]
    if not usable:
        return None
    first = usable[0]
    if len(first[2]) < 8 or first[2][0].islower():
        return None
    picked = [first]
    for l in usable[1:]:
        if len(picked) == 3:
            break
        if abs(l[1] - first[1]) > 0.4 or l[0] - picked[-1][0] > first[1] * 1.9:
            break
        picked.append(l)
    title = join_lines([l[2] for l in picked])
    # a paragraph grabbed by mistake, not a title
    if len(title) > 160 or title.endswith((".", ";")):
        return None
    return title


def clean_title(title):
    if not title:
        return title
    title = unicodedata.normalize("NFKC", title)
    changed = True
    while changed:  # prefixes can nest: "CS224R Final Project Extended Abstract: ..."
        changed = False
        for p in STRIP_PREFIXES:
            stripped = p.sub("", title).strip()
            if stripped != title and len(stripped) >= 12:
                title, changed = stripped, True
    suffixed = re.sub(r"[\s:(–—-]*extended\s+abstract\)?\s*$", "", title, flags=re.I).strip()
    if suffixed != title and len(suffixed) >= 12:
        title = suffixed
    title = re.sub(r"\s*↔\s*", " ↔ ", title)
    title = re.sub(r"\s+", " ", title).strip(" :–—-")
    return title.strip()


def extract_title(pdf_path, authors):
    variants = name_variants(authors)
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None
    try:
        for pno in range(min(4, doc.page_count)):
            page = doc[pno]
            lines = page_lines(page)
            if not lines:
                continue
            t = title_from_big_text(lines, page.rect.height, variants)
            if t:
                return clean_title(t)
        page = doc[0]
        t = title_fallback_first_line(page_lines(page), page.rect.height, variants)
        return clean_title(t) if t else None
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# TA assignment matching


def load_ta_groups():
    """Parse the staff sheet into [{ta, track, members}, ...]."""
    if not TA_SHEET.exists():
        return None
    groups = []
    for line in TA_SHEET.read_text(encoding="utf-8").splitlines():
        line = line.replace('"', "").rstrip()
        if not line.strip():
            continue
        fields = re.split(r"\s{3,}", line.strip())
        if len(fields) < 3 or fields[1] not in ("Default", "Custom", "Undefined"):
            print(f"!! unparsed TA-sheet line: {line[:90]}", file=sys.stderr)
            continue
        names = [m.strip(" ,") for m in fields[2].split(",")]
        names = [re.sub(r"^and\s+", "", n) for n in names if n.strip()]
        groups.append({"ta": fields[0], "track": fields[1], "members": names})
    return groups


def _name_tokens(name):
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[._()]", " ", s.lower())
    return [t for t in re.split(r"[\s-]+", s) if t and t != "and"]


def _tok_match(a, b):
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.8


def _person_match(m_tokens, a_tokens):
    if not m_tokens or not a_tokens:
        return False
    hits = sum(1 for mt in m_tokens if any(_tok_match(mt, at) for at in a_tokens))
    return hits / min(len(m_tokens), len(a_tokens)) >= 0.67


def _group_score(members, authors):
    """(F1 over person matches, exact-token overlap as tie-breaker)."""
    m_toks = [_name_tokens(m) for m in members]
    a_toks = [_name_tokens(a) for a in authors]
    used, matched = set(), 0
    for mt in m_toks:
        for j, at in enumerate(a_toks):
            if j not in used and _person_match(mt, at):
                used.add(j)
                matched += 1
                break
    if matched == 0:
        return (0.0, 0)
    prec, rec = matched / len(m_toks), matched / len(a_toks)
    exact = len({t for ts in m_toks for t in ts} & {t for ts in a_toks for t in ts})
    return (2 * prec * rec / (prec + rec), exact)


def match_ta(groups, sub_id, authors):
    """-> (Type, Mentor TA) for a submission, or ("", "") if unresolved."""
    if sub_id in TA_OVERRIDES:
        return TA_OVERRIDES[sub_id]
    if not groups:
        return ("", "")
    best, best_s = None, (0.0, 0)
    for g in groups:
        s = _group_score(g["members"], authors)
        if s > best_s:
            best, best_s = g, s
    if best is None or best_s[0] < 0.5:
        return ("", "")
    track = best["track"] if best["track"] != "Undefined" else ""
    return (track, best["ta"])


# ---------------------------------------------------------------------------


def load_authors():
    """folder name -> [name, ...] from the Gradescope metadata."""
    meta_path = PDF_ROOT / "submission_metadata.yml"
    with open(meta_path, encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    return {
        str(folder): [s[":name"].strip() for s in info.get(":submitters", [])]
        for folder, info in meta.items()
    }


def main():
    authors_by_folder = load_authors()
    ta_groups = load_ta_groups()
    if ta_groups is None:
        print("!! ta_assignments_raw.txt not found; Type/Mentor TA left blank", file=sys.stderr)
    rows = []
    folders = sorted((p for p in PDF_ROOT.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
    missing_meta, missing_title = [], []
    skipped_optout = 0
    for folder in folders:
        m = re.search(r"submission_(\d+)$", folder.name)
        sub_id = m.group(1) if m else ""
        if sub_id in OPT_OUT_IDS:
            skipped_optout += 1
            continue
        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            print(f"!! no pdf in {folder.name}", file=sys.stderr)
            continue
        pdf = pdfs[0]
        authors = authors_by_folder.get(folder.name, [])
        if not authors:
            missing_meta.append(folder.name)
            authors = [re.sub(r"\s*submission_\d+$", "", folder.name)]
        if folder.name in OVERRIDES:
            title = OVERRIDES[folder.name]
        else:
            title = extract_title(pdf, authors)
        if not title:
            missing_title.append(folder.name)
            title = ""
        ptype, ta = match_ta(ta_groups, sub_id, authors)
        if ta_groups and not ta:
            print(f"!! no TA match for {folder.name}", file=sys.stderr)
        rows.append({
            # title-only entries keep no link to the withheld report
            "PDF": "" if sub_id in TITLE_ONLY_IDS else f"{folder.name}/{pdf.name}",
            "Type": ptype,
            "Title": title,
            "Authors": authors,
            "Mentor TA": ta,
        })

    # merge duplicate submissions of the same report (teammates who each
    # uploaded a copy): identical non-empty titles become one row
    merged, by_title = [], {}
    for row in rows:
        key = row["Title"].lower()
        if row["Title"] and key in by_title:
            kept = by_title[key]
            for name in row["Authors"]:
                if name not in kept["Authors"]:
                    kept["Authors"].append(name)
            print(f"merged duplicate: {row['Title'][:70]}\n    {row['PDF']}  ->  {kept['PDF']}")
            continue
        by_title[key] = row
        merged.append(row)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["PDF", "Type", "Title", "Authors", "Mentor TA"])
        w.writeheader()
        for row in merged:
            w.writerow({**row, "Authors": ", ".join(row["Authors"])})

    print(f"\nwrote {len(merged)} rows to {OUT_CSV.name} "
          f"({len(rows) - len(merged)} duplicates merged, {skipped_optout} opt-outs excluded)")
    if missing_meta:
        print(f"{len(missing_meta)} folders missing in metadata yml:", *missing_meta, sep="\n  ")
    if missing_title:
        print(f"{len(missing_title)} PDFs with no extracted title:", *missing_title, sep="\n  ")


if __name__ == "__main__":
    main()
