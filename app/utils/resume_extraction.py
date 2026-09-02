"""
Extracts plain text from an uploaded resume file (PDF/DOCX) and parses it
into the same structured shape the Resume Builder produces (experience,
education, skills, certifications, languages, contact info), so the
"Generate ATS PDF" action can render a template from what the candidate
actually uploaded instead of always falling back to their profile fields.

This is a heuristic, section-header-driven parser (no OCR, no LLM) -- it
works well on standard, text-based, single-column resumes with common
section headings (Experience, Education, Skills, ...), and degrades
gracefully (returns None) on scanned/image-only PDFs or files with no
recognizable structure, so the caller can fall back to profile data instead
of producing an empty/garbled document.
"""
from __future__ import annotations

import re
from typing import Optional

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - defensive, pypdf is a hard requirement
    PdfReader = None

try:
    import docx as _docx
except Exception:  # pragma: no cover - defensive, python-docx is a hard requirement
    _docx = None

from io import BytesIO


# ── Text extraction ──────────────────────────────────────────────────────

def extract_text(content: bytes, file_name: str = "", content_type: Optional[str] = None) -> str:
    """Best-effort plain-text extraction from a PDF or DOCX resume.

    Returns "" (not an exception) for unsupported formats, empty/corrupt
    files, or scanned/image-only PDFs with no text layer -- callers should
    treat an empty/whitespace-only result as "extraction failed" and fall
    back to another data source rather than rendering a blank resume.
    """
    lowered_name = (file_name or "").lower()
    is_pdf = lowered_name.endswith(".pdf") or (content_type or "") == "application/pdf"
    is_docx = lowered_name.endswith(".docx") or (content_type or "").endswith(
        "wordprocessingml.document"
    )

    if not is_pdf and not is_docx:
        # Fall back to sniffing the magic bytes, in case file_name/content_type
        # weren't reliable (e.g. a generic "application/octet-stream").
        if content[:4] == b"%PDF":
            is_pdf = True
        elif content[:2] == b"PK":
            is_docx = True

    try:
        if is_pdf:
            return _extract_pdf_text(content)
        if is_docx:
            return _extract_docx_text(content)
    except Exception:
        return ""
    return ""


try:
    import pdfplumber
except Exception:  # pragma: no cover - defensive, pdfplumber is a hard requirement
    pdfplumber = None


def _extract_pdf_text(content: bytes) -> str:
    if pdfplumber is not None:
        try:
            lines = _extract_pdf_lines_layout_aware(content)
            if lines:
                return "\n".join(lines)
        except Exception:
            pass  # fall through to the simpler pypdf-based extraction below

    if PdfReader is None:
        return ""
    reader = PdfReader(BytesIO(content))
    pages_text = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages_text)


def _extract_pdf_lines_layout_aware(content: bytes) -> list[str]:
    """Extracts text page-by-page using word bounding boxes rather than
    pdfplumber/pypdf's default reading order.

    Plain text extraction reads a PDF's content stream in whatever order
    the page draws it in, which for a *single*-column resume is normally
    top-to-bottom -- fine. But many resumes lay Skills/Certifications out
    as a two-column grid, and naive extraction then interleaves the two
    columns line-by-line (or dumps one column's content into the middle of
    the other), scrambling section content in ways the downstream parser
    can't recover from.

    This groups words into visual lines, then -- *within each block
    between two of our known section headings* -- checks whether that
    block's lines cleanly split into a left half and a right half of the
    page with little text crossing the middle. If so, the whole left
    column is emitted before the whole right column (each top-to-bottom),
    which matches how a person actually reads a two-column resume. Blocks
    that aren't a clean two-column split are left in their natural
    top-to-bottom order, so ordinary single-column resumes are unaffected.
    """
    all_lines: list[str] = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            all_lines.extend(_order_page_lines(words, page.width))
    return all_lines




def _cluster_words_into_rows(words: list[dict], tol: float = 3.0) -> list[list[dict]]:
    """Groups words with near-identical vertical position ('top') into a
    single visual row (left-to-right order), sorted top-to-bottom. A row
    may still contain words from two different columns at this point --
    that's resolved separately by `_split_row_at_gutter`, since simply
    joining every same-row word into one line (as an earlier version of
    this did) merges left- and right-column text on a shared row into one
    garbled line."""
    rows: list[list[dict]] = []
    tops: list[float] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        target_idx = None
        for i, t in enumerate(tops):
            if abs(t - w["top"]) <= tol:
                target_idx = i
                break
        if target_idx is None:
            rows.append([w])
            tops.append(w["top"])
        else:
            rows[target_idx].append(w)

    order = sorted(range(len(rows)), key=lambda i: tops[i])
    result = []
    for i in order:
        result.append(sorted(rows[i], key=lambda w: w["x0"]))
    return result


def _row_text(row_words: list[dict]) -> str:
    # Only insert a space between two consecutive words when there's an
    # actual visual gap between them. Some PDF generators split a single
    # visual token into two separate "words" right at a font-run boundary
    # with *zero* gap between them -- most commonly an email address, split
    # right at the "@" (e.g. "name" + "@gmail.com"). Blindly joining every
    # word with a space then corrupts that token into "name @gmail.com",
    # which no longer matches EMAIL_RE and silently drops the contact's
    # email -- so a real (non-zero) gap is required before adding one.
    out: list[str] = []
    prev = None
    for w in row_words:
        if prev is not None:
            out.append(" " if (w["x0"] - prev["x1"]) >= MIN_WORD_JOIN_GAP_PT else "")
        out.append(w["text"])
        prev = w
    return "".join(out)


MIN_WORD_JOIN_GAP_PT = 1.0  # min horizontal gap (points) to treat two words as genuinely separate


MIN_ROW_GUTTER_GAP_PT = 15.0  # per-row internal gap (points) that's a candidate gutter
GUTTER_CLUSTER_TOL_PT = 12.0  # how close candidate gutters must be to count as "the same" gutter


def _detect_gutter(rows: list[list[dict]]) -> Optional[float]:
    """Finds a plausible column-gutter x-position for a block of rows.

    Looks for a genuinely empty vertical band by examining the largest gap
    *within each individual row* (between two consecutive words), rather
    than merging every word's x-range across the whole block into one
    combined coverage map. The latter approach breaks as soon as the block
    contains even one full-width row (e.g. a centered name/contact line, or
    a heading that happens to sit on the same visual line as unrelated
    text in the other column) -- that single row's word spans "bridge" the
    real gutter in the merged coverage, hiding it entirely even though
    every *other* row cleanly splits into two columns.

    Real two-column layouts consistently wrap their text to fit each
    column, so most rows should show an internal gap at roughly the same
    x-position. This clusters those per-row gaps and only returns a gutter
    if enough rows agree on roughly the same position -- returns None if
    there's no such consistent gap (content likely isn't laid out in two
    columns, or too few rows show the pattern to be confident)."""
    candidates: list[float] = []
    rows_with_words = 0
    for row in rows:
        if len(row) < 2:
            continue
        rows_with_words += 1
        ordered = sorted(row, key=lambda w: w["x0"])
        best_gap, best_mid = 0.0, None
        for prev, nxt in zip(ordered, ordered[1:]):
            gap = nxt["x0"] - prev["x1"]
            if gap > best_gap:
                best_gap, best_mid = gap, (prev["x1"] + nxt["x0"]) / 2
        if best_gap > MIN_ROW_GUTTER_GAP_PT:
            candidates.append(best_mid)

    if rows_with_words < 4 or len(candidates) < 3 or len(candidates) < rows_with_words * 0.2:
        return None

    # Cluster candidates: for each candidate, count how many others fall
    # within GUTTER_CLUSTER_TOL_PT of it, and take the best-supported one
    # (as the mean of its cluster) -- this is the position most rows agree
    # a column boundary sits at.
    best_cluster: list[float] = []
    for c in candidates:
        cluster = [x for x in candidates if abs(x - c) <= GUTTER_CLUSTER_TOL_PT]
        if len(cluster) > len(best_cluster):
            best_cluster = cluster

    if len(best_cluster) < 3 or len(best_cluster) < len(candidates) * 0.4:
        return None

    return sum(best_cluster) / len(best_cluster)


def _order_body_rows(rows: list[list[dict]]) -> list[str]:
    """Emits body rows in reading order. If a consistent column gutter is
    detected for this block (see `_detect_gutter`), every row is split at
    that x-position and the whole left column is emitted (top-to-bottom)
    before the right column -- otherwise rows are left in their natural
    top-to-bottom order, so single-column content is unaffected."""
    gutter_x = _detect_gutter(rows)
    if gutter_x is None:
        return [_row_text(row) for row in rows]

    header_lines, left_lines, right_lines = [], [], []
    for row in rows:
        min_x0 = min(w["x0"] for w in row)
        max_x1 = max(w["x1"] for w in row)
        if max_x1 <= gutter_x:
            left_lines.append(_row_text(row))
            continue
        if min_x0 > gutter_x:
            right_lines.append(_row_text(row))
            continue

        # This row's words span both sides of the gutter. Only treat it as
        # a genuine two-column row if it has a real gap of its own at
        # roughly the gutter position -- otherwise it's a single
        # full-width element (e.g. a centered name or contact line) that
        # merely happens to cross the boundary, and splitting it at
        # gutter_x would scramble or drop words that belong together.
        ordered = sorted(row, key=lambda w: w["x0"])
        has_real_gap = any(
            nxt["x0"] - prev["x1"] > MIN_ROW_GUTTER_GAP_PT
            for prev, nxt in zip(ordered, ordered[1:])
        )
        row_text_full = _row_text(row)
        # A contact-info line (email / phone / LinkedIn / a bare URL) is
        # always one logical unit, even when the gap between two of its
        # fields (e.g. phone number -> city) happens to be as wide as a
        # genuine column gutter. Splitting it there doesn't produce two
        # sensible columns -- it silently drops the phone/email/location
        # from contact parsing and leaves the other half stranded as a
        # stray line wherever the far column's content happens to end.
        looks_like_contact_line = bool(
            EMAIL_RE.search(row_text_full)
            or LINKEDIN_RE.search(row_text_full)
            or _URL_LIKE_RE.search(row_text_full)
        )
        if not has_real_gap or looks_like_contact_line:
            header_lines.append(row_text_full)
            continue

        # Assign each word by which side of the gutter its midpoint falls
        # on, so a word whose bounding box merely touches the gutter isn't
        # silently dropped from the output.
        left_words = [w for w in row if (w["x0"] + w["x1"]) / 2 <= gutter_x]
        right_words = [w for w in row if (w["x0"] + w["x1"]) / 2 > gutter_x]
        if left_words:
            left_lines.append(_row_text(left_words))
        if right_words:
            right_lines.append(_row_text(right_words))

    if not left_lines or not right_lines:
        return [_row_text(row) for row in rows]

    return header_lines + left_lines + right_lines


def _order_page_lines(words: list[dict], page_width: float) -> list[str]:
    rows = _cluster_words_into_rows(words)

    # Split into blocks at each of our known section headings, so column
    # detection/reordering never mixes content from two different sections
    # (e.g. Skills' right column bleeding into Certifications' left column).
    blocks: list[list[list[dict]]] = []
    current: list[list[dict]] = []
    for row in rows:
        if _is_header_line(_row_text(row).strip()) and current:
            blocks.append(current)
            current = [row]
        else:
            current.append(row)
    if current:
        blocks.append(current)

    ordered: list[str] = []
    for block in blocks:
        header_row = None
        body_rows = block
        if block and _is_header_line(_row_text(block[0]).strip()):
            header_row, body_rows = block[0], block[1:]
            ordered.append(_row_text(header_row))

        if not body_rows:
            continue
        ordered.extend(_order_body_rows(body_rows))

    return ordered


def _extract_docx_text(content: bytes) -> str:
    if _docx is None:
        return ""
    document = _docx.Document(BytesIO(content))
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    lines.append(cell.text)
    return "\n".join(lines)


# ── Structured parsing ───────────────────────────────────────────────────

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{7,}\d)")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/\S+", re.I)
# Any other bare URL/domain-style link (GitHub, portfolio site, ...) sitting
# on a contact-info line -- used only to keep such a line from being split
# at a two-column gutter (see _order_body_rows), not for extracting a value.
_URL_LIKE_RE = re.compile(r"(?:https?://\S+|\bwww\.\S+|\b[a-z0-9-]+\.(?:com|io|dev|net|org)/\S*)", re.I)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
MONTH_YEAR_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b",
    re.I,
)
# Numeric "MM/YYYY" (or "MM-YYYY") dates -- e.g. "07/2024 – 07/2025", a
# format at least as common on resumes as the "Jul 2024" spelled-out form
# MONTH_YEAR_RE handles, but one the date-range matching below previously
# had no token for at all. Without it, DATE_RANGE_RE fails to match a
# "MM/YYYY – MM/YYYY" line outright (the trailing "/YYYY" on the first date
# breaks YEAR_RE's own match from lining up with the separator that
# follows it), which in turn breaks entry splitting and role/company
# parsing for every Experience entry using this date format.
NUMERIC_MONTH_YEAR_RE = re.compile(r"\b(?:0[1-9]|1[0-2])[/-](?:19|20)\d{2}\b")
# Named groups ("start"/"end") so composing sub-patterns that themselves
# contain parentheses (e.g. an earlier version of YEAR_RE) can't silently
# shift positional group numbers -- a real bug hit during testing.
_DATE_TOKEN = rf"(?:{MONTH_YEAR_RE.pattern}|{NUMERIC_MONTH_YEAR_RE.pattern}|{YEAR_RE.pattern})"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:-|–|—|to)\s*"
    rf"(?P<end>Present|Current|Now|{_DATE_TOKEN})",
    re.I,
)

SECTION_PATTERNS = {
    "summary": re.compile(
        r"^((profile|professional|career|executive)\s+)?summary$"
        r"|^profile$|^objective$|^about(\s*me)?$",
        re.I,
    ),
    "experience": re.compile(
        r"^(professional|work|relevant)?\s*experience$|^employment(\s+history)?$|^work\s+history$",
        re.I,
    ),
    "education": re.compile(r"^education(\s*(&|and)?\s*(background|qualifications?))?$", re.I),
    "skills": re.compile(
        r"^(technical\s+|core\s+|key\s+)?skills$"
        r"|^core\s+competencies(\s*(&|and)\s*skills)?$"
        # Generic "<a few words> & Skills" / "Skills & <a few words>" --
        # e.g. "Tools & Skills", "Skills & Tools", "Strengths & Skills".
        # Deliberately generic (rather than one more hardcoded phrase)
        # since resumes coin their own variant of this heading constantly;
        # anchored to the *whole* line and already capped at 40 chars by
        # _is_header_line, so it isn't a plausible match for real bullet
        # content.
        r"|^[a-z][a-z\s]{0,25}(&|and)\s*skills$"
        r"|^skills\s*(&|and)\s*[a-z][a-z\s]{0,25}$",
        re.I,
    ),
    "certifications": re.compile(
        r"^certifications?$|^certificates?$|^licenses?(\s*(&|and)\s*certifications?)?$", re.I
    ),
    "languages": re.compile(r"^languages?$", re.I),
    "projects": re.compile(
        r"^projects?$"
        r"|^(key\s+)?(strategic\s+)?(campaigns?\s*(&|and)\s*)?projects?$"
        r"|^key\s+strategic\s+campaigns?\s*(&|and)\s*projects?$",
        re.I,
    ),
    # Common resume section names given their own explicit pattern (rather
    # than relying on the generic, position-dependent custom-header
    # heuristic) so they're reliably recognized as their own top-level
    # section no matter where they sit -- e.g. "Internship" between Skills
    # and Certifications, or after Projects. This also keeps them from
    # being confused with an unrelated short line *inside* a Projects or
    # Experience entry (like a project's own sub-label, e.g. "HOTEL
    # RESERVATION" under "Design and Implementation of Hotel Reservation
    # Using Python") -- those aren't real section headings, just entry
    # sub-titles, and are handled by _parse_prose_section_with_headings.
    "internship": re.compile(r"^internships?$|^internship\s+experience$", re.I),
    "awards": re.compile(r"^awards?(\s*(&|and)\s*(honors?|achievements?))?$|^honors?$|^achievements?$", re.I),
    "publications": re.compile(r"^publications?$", re.I),
    "volunteer": re.compile(r"^volunteer(ing)?(\s+experience)?$|^volunteer\s+work$|^community\s+service$", re.I),
    "interests": re.compile(r"^(hobbies|interests)(\s*(&|and)\s*(hobbies|interests))?$", re.I),
}

# Display titles for the "extra" recognized sections above (those without a
# dedicated structured shape of their own -- they render as a titled bullet
# list via _render_bullet_section, same as Projects/custom sections).
_EXTRA_KNOWN_SECTION_TITLES = {
    "internship": "Internship",
    "awards": "Awards",
    "publications": "Publications",
    "volunteer": "Volunteer Experience",
    "interests": "Interests",
}

PROFICIENCY_WORDS = {
    "native": "NATIVE",
    "fluent": "EXPERT",
    "expert": "EXPERT",
    "professional": "PROFESSIONAL",
    "intermediate": "INTERMEDIATE",
    "basic": "BASIC",
    "beginner": "BASIC",
    "advanced": "EXPERT",
}


def _is_header_line(stripped: str) -> Optional[str]:
    """Returns the section key if `stripped` looks like one of our known
    section headings (short line, matches a known heading pattern), else
    None. For headings we don't specifically parse (Achievements, Awards,
    Internships, ...) see `_is_probable_custom_header` below."""
    if not stripped or len(stripped) > 40:
        return None
    candidate = stripped.strip(":").strip().strip("-").strip()
    for key, pattern in SECTION_PATTERNS.items():
        if pattern.match(candidate):
            return key
    return None


_GENERIC_HEADER_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z&/'.-]*$")
_HEADER_MINOR_WORDS = {"and", "or", "the", "of", "in", "on", "for", "with", "a", "an", "to"}


def _is_probable_custom_header(stripped: str) -> bool:
    """Heuristic fallback for section headings that aren't in our known
    SECTION_PATTERNS -- e.g. Achievements, Awards, Internships,
    Publications, Volunteer Experience, Hobbies. A line qualifies if it's
    short, unbulleted, made up of 1-5 title-like words, and doesn't look
    like body text (no email/phone/URL, no date, doesn't end mid-sentence).
    This is deliberately conservative: it only fires on lines that are
    ALL CAPS or fully Title Cased, since resume section headings almost
    always use one of those two conventions."""
    if not stripped or len(stripped) > 40:
        return False
    if BULLET_PREFIX_RE.match(stripped):
        return False
    if EMAIL_RE.search(stripped) or PHONE_RE.search(stripped) or LINKEDIN_RE.search(stripped):
        return False
    if DATE_RANGE_RE.search(stripped) or YEAR_RE.search(stripped):
        return False

    text = stripped.rstrip(":").strip()
    if not text or text.rstrip().endswith((".", ",", ";")):
        return False

    words = text.split()
    if not (1 <= len(words) <= 5):
        return False
    if not all(_GENERIC_HEADER_WORD_RE.match(w) for w in words):
        return False

    letters_only = re.sub(r"[^A-Za-z]", "", text)
    if len(letters_only) < 3:
        return False
    is_all_caps = letters_only.isupper()
    is_title_case = all(w[0].isupper() for w in words if w[:1].isalpha())
    return is_all_caps or is_title_case


def _titleize_header(title: str) -> str:
    """Turns an ALL-CAPS heading like "ACHIEVEMENTS AND AWARDS" into a
    readable "Achievements and Awards"; leaves already mixed-case headings
    (e.g. "Awards & Recognition") untouched."""
    letters_only = re.sub(r"[^A-Za-z]", "", title)
    if not (letters_only and letters_only.isupper()):
        return title.strip()
    words = title.split()
    out = []
    for i, w in enumerate(words):
        core = w.strip(".,:;")
        if i > 0 and core.lower() in _HEADER_MINOR_WORDS:
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def _split_sections(lines: list[str]) -> tuple[list[str], list[dict]]:

    known_boundaries = []  # (line_index, key, raw_title)
    for i, line in enumerate(lines):
        stripped = line.strip()
        key = _is_header_line(stripped)
        if key:
            known_boundaries.append((i, key, stripped.strip(":").strip()))

    if not known_boundaries:
        return lines, []

    header_block = lines[: known_boundaries[0][0]]
    raw_entries: list[dict] = []
    for idx, (start, key, title) in enumerate(known_boundaries):
        end = known_boundaries[idx + 1][0] if idx + 1 < len(known_boundaries) else len(lines)
        section_lines = [l for l in lines[start + 1 : end] if l.strip()]
        raw_entries.append({"key": key, "title": title, "lines": section_lines})

    # Any known section's body can itself contain a further, custom-style
    # heading that isn't one of our SECTION_PATTERNS -- e.g. an
    # "INTERNSHIP" heading sitting between a resume's Skills and
    # Certifications sections. Previously only the very *last* known
    # section's body was re-scanned for this, so a custom heading sandwiched
    # between two recognized sections (not after the last one) was silently
    # absorbed into whichever recognized section preceded it -- that's what
    # made "Internship" show up as if it were a skill. Re-scanning every
    # entry's body fixes that regardless of where in the resume it sits.
    #
    # EXCEPT "experience", "projects", and the other generic-bullet-section
    # keys in _EXTRA_KNOWN_SECTION_TITLES (internship, awards, publications,
    # volunteer, interests): those all already get their own sub-entry-aware
    # parsing downstream (_parse_experience / _parse_prose_section_with_
    # headings) that correctly recognizes a short unbulleted line -- a
    # job's dates, or a project's own sub-label like "HOTEL RESERVATION"
    # under "Design and Implementation of Hotel Reservation Using Python",
    # or "VIRTUAL INTERNSHIP ON CYBERSECURITY" under "Internship" -- as
    # part of that SAME entry, not a brand new top-level section. Running
    # this generic re-scan on them too was a regression: it split a
    # project's (or internship's) own sub-label out into a separate,
    # wrongly-promoted top-level section instead of leaving it nested.
    _no_rescan_keys = {
        "summary",
        "experience",
        "education",
        "skills",
        "certifications",
        "languages",
        "projects",
    } | set(_EXTRA_KNOWN_SECTION_TITLES.keys())
    entries: list[dict] = []
    for entry in raw_entries:
        if entry["key"] in _no_rescan_keys:
            entries.append(entry)
            continue

        body = entry["lines"]
        custom_boundaries = []  # (index within body, raw_title)
        for j, line in enumerate(body):
            stripped = line.strip()
            if _is_probable_custom_header(stripped):
                custom_boundaries.append((j, stripped.rstrip(":").strip()))

        if not custom_boundaries:
            entries.append(entry)
            continue

        first = custom_boundaries[0][0]
        entries.append({"key": entry["key"], "title": entry["title"], "lines": [l for l in body[:first] if l.strip()]})
        for cidx, (start, title) in enumerate(custom_boundaries):
            cend = custom_boundaries[cidx + 1][0] if cidx + 1 < len(custom_boundaries) else len(body)
            section_lines = [l for l in body[start + 1 : cend] if l.strip()]
            entries.append({"key": None, "title": title, "lines": section_lines})

    return header_block, entries


def _extract_contact(header_block: list[str], full_text: str) -> dict:
    stripped_lines = [l.strip() for l in header_block if l.strip()]

    email_match = EMAIL_RE.search(full_text)
    phone_match = PHONE_RE.search(full_text)
    linkedin_match = LINKEDIN_RE.search(full_text)

    name = ""
    headline = ""
    for line in stripped_lines[:4]:
        if EMAIL_RE.search(line) or PHONE_RE.search(line) or LINKEDIN_RE.search(line):
            continue
        if not name:
            name = line
        elif not headline and len(line) <= 90:
            headline = line
            break

    return {
        "full_name": name,
        "headline": headline,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "linkedin_url": linkedin_match.group(0) if linkedin_match else "",
    }


def _blocks_from_section(section_lines: list[str], raw_lines_with_blanks: list[str]) -> list[list[str]]:
    """Groups a section's lines into per-entry blocks. Prefers splitting on
    blank lines (as they appear between resume entries); if the section has
    no blank lines at all (common when a converter collapses them), falls
    back to starting a new block at each line containing a date range.

    Some resumes fit an entry's date range on its own line, separate from
    the company/role above it (e.g. "Company\\nRole\\nJul 2024 - Jul 2025")
    rather than one combined "Company | Jul 2024 - Jul 2025" header line.
    Splitting a new block open at *every* dated line -- as an earlier
    version of this did -- misreads that first entry's own date line as the
    start of a second, dateless, bullet-less entry, which is what silently
    turned "Company" into the whole highlight/role and left the real
    company blank. A dated line only starts a *new* block once the current
    one already has a date of its own -- i.e. once we're sure it's a
    second, genuinely separate entry, not this entry's own header still
    filling in."""
    blocks: list[list[str]] = []
    current: list[str] = []
    current_has_date = False
    for line in section_lines:
        has_date = bool(DATE_RANGE_RE.search(line))
        if has_date and current and current_has_date:
            blocks.append(current)
            current = [line]
            current_has_date = True
        else:
            current.append(line)
            current_has_date = current_has_date or has_date
    if current:
        blocks.append(current)
    return blocks


def _blocks_from_education_section(section_lines: list[str]) -> list[list[str]]:
    """Groups education lines into per-entry blocks. Unlike experience (where
    a new dated line usually *starts* an entry), education entries are
    typically "Institution" followed by "Degree, start – end", so a new
    entry is detected when a line with *no* date follows a line that
    already supplied one (i.e. the previous entry is "complete") --
    except a "Grade : 8.58" style line, which always trails *after* an
    entry's date line but isn't itself a date and isn't the start of a new
    entry either; without carving it out here it would wrongly close the
    current block early and then get stuck as the *next* entry's opening
    line, corrupting that entry's institution/degree.

    One more wrinkle some resumes have that others don't: whether the
    institution/degree line(s) come *before* the date line, or the date is
    combined onto the very first line ("Bachelor of Arts ... 2011 - 2015",
    institution following on its own line *after* that). In the first case
    the entry is "complete" (ready to close) the moment its date line has
    been seen; in the second, seeing the date on line 1 doesn't mean the
    entry's done -- the institution's still coming on line 2. Distinguish
    them by how many non-date lines this entry already had *before* its
    date line showed up: none (date arrived immediately, on line 1) means
    give it one extra line's grace before allowing a new entry to open."""
    blocks: list[list[str]] = []
    current: list[str] = []
    current_has_date = False
    lines_before_date = 0
    grace = 0
    for line in section_lines:
        has_date = bool(DATE_RANGE_RE.search(line)) or len(re.findall(r"\b(?:19|20)\d{2}\b", line)) >= 2
        is_grade_line = bool(_GRADE_LINE_RE.match(line.strip()))
        if current and current_has_date and not has_date and not is_grade_line and grace <= 0:
            blocks.append(current)
            current = []
            current_has_date = False
            lines_before_date = 0
            grace = 0
        if not current_has_date and not has_date:
            lines_before_date += 1
        current.append(line)
        if has_date and not current_has_date:
            grace = 1 if lines_before_date == 0 else 0
        elif not has_date and not is_grade_line and grace > 0:
            grace -= 1
        current_has_date = current_has_date or has_date
    if current:
        blocks.append(current)
    return blocks


_TRAILING_CITY_STATE_RE = re.compile(
    r",?\s*([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,1}),\s*([A-Z]{2})\s*$"
)


def _parse_experience(section_lines: list[str]) -> list[dict]:
    blocks = _blocks_from_section(section_lines, section_lines)
    entries = []
    for block in blocks:
        if not block:
            continue
        date_line_idx = None
        start_date, end_date, currently_working = "", "", False
        location = ""
        for i, line in enumerate(block):
            m = DATE_RANGE_RE.search(line)
            if m:
                date_line_idx = i
                start_date = m.group("start")
                end_raw = m.group("end")
                if end_raw.lower() in ("present", "current", "now"):
                    currently_working = True
                else:
                    end_date = end_raw
                # Whatever's left on the date's own line after the date
                # itself is removed is usually a location ("| Vijaywada"),
                # but only when the date sits on its own line separate from
                # company/role -- if it shares a line with them (the
                # single-line "Role | Company | Jan 2020 - Feb 2021" case,
                # i > 0 false... actually i can be 0 there too), leave it to
                # the role/company split below instead of guessing it's a
                # location.
                break

        # Some resumes put company and role on their own lines above a
        # separate date line ("Company\nRole\nJul 2024 - Jul 2025") instead
        # of one combined header ("Role | Company | Jul 2024 - Jul 2025").
        # When the date line isn't the block's first line, everything
        # before it is that multi-line header; anything left over on the
        # date line itself is a location, not more identity text.
        if date_line_idx is not None and date_line_idx > 0:
            header_lines = [l.strip() for l in block[:date_line_idx] if l.strip()]
            location = DATE_RANGE_RE.sub("", block[date_line_idx]).strip(" -–—|,")
        else:
            single = block[date_line_idx] if date_line_idx is not None else block[0]
            single = DATE_RANGE_RE.sub("", single).strip(" -–—|,•· ")
            # Some resumes combine company + role + location on one line
            # with no delimiter at all between company and role (e.g.
            # "Datadog Senior Sales Engineer New York, NY"), only using a
            # separator ("•", a date) after the location. There's no
            # reliable way to split company from role there without a
            # company-name dictionary, but a trailing "City, ST" is a
            # distinctive enough shape to pull out on its own -- doing so
            # at least keeps it from being glued onto the end of whatever
            # role/company text follows.
            loc_match = _TRAILING_CITY_STATE_RE.search(single)
            if loc_match:
                location = loc_match.group(0).strip(" ,")
                single = single[: loc_match.start()].strip(" -–—|,•· ")
            header_lines = [single]

        if len(header_lines) >= 2:
            # Company name as the heading line, job title beneath it --
            # the convention this multi-line header format almost always
            # follows on resumes that use it.
            company, role = header_lines[0], header_lines[1]
        else:
            header_line = header_lines[0] if header_lines else ""
            role, company = header_line, ""
            # "|" checked first: it's an unambiguous, deliberately-placed
            # separator a resume author put there on purpose. " - "/" – "
            # commonly appear *inside* a title itself (e.g. "Senior
            # Marketing Manager - Acquisition"), so trying those first
            # split a real title in half at its own internal dash instead
            # of at the actual role/company boundary.
            for sep in ("|", " at ", " @ ", " - ", " – "):
                if sep in header_line:
                    parts = header_line.split(sep, 1)
                    role, company = parts[0].strip(), parts[1].strip()
                    break
            else:
                if "," in header_line:
                    head, _, tail = header_line.partition(",")
                    if len(head.strip()) < 60 and len(tail.strip()) < 60:
                        role, company = head.strip(), tail.strip()

        consumed = set(header_lines) | ({block[date_line_idx]} if date_line_idx is not None else set())
        bullet_lines = [l for i, l in enumerate(block) if i != date_line_idx and l not in consumed]
        highlights = "\n".join(_merge_prose_bullets(bullet_lines))

        if role or company or highlights:
            entries.append({
                "role": role,
                "company": company,
                "location": location,
                "start_date": start_date,
                "end_date": end_date,
                "currently_working": currently_working,
                "key_highlights": highlights,
            })
    return entries


_GRADE_LINE_RE = re.compile(r"^(grade|cgpa|gpa)\b", re.I)
# Words that overwhelmingly show up in an institution's name, not a degree's
# -- used to tell the two apart when a source resume lists degree/major
# *before* institution (the reverse of this parser's documented default
# assumption). Only swaps when the second line has one of these words and
# the first doesn't, so the default (institution-first) ordering used
# elsewhere is unaffected.
_INSTITUTION_HINT_RE = re.compile(
    r"\b(university|college|institute|school|academy|polytechnic|labs?)\b", re.I
)


def _parse_education(section_lines: list[str]) -> list[dict]:
    blocks = _blocks_from_education_section(section_lines)
    entries = []
    for block in blocks:
        if not block:
            continue

        grade = ""
        core_lines: list[str] = []
        for line in block:
            if _GRADE_LINE_RE.match(line.strip()):
                # First "Grade"/"CGPA"/"GPA" line wins; keep any further
                # ones (unlikely, but a resume could repeat the label) out
                # of core_lines either way so they can't be mistaken for
                # the institution/degree lines below.
                if not grade:
                    grade = re.sub(r"^(grade|cgpa|gpa)\s*:?\s*", "", line.strip(), flags=re.I).strip(" .")
            else:
                core_lines.append(line)

        all_years = re.findall(r"\b((?:19|20)\d{2})\b", "\n".join(core_lines))
        start_year = all_years[0] if all_years else ""
        grad_year = all_years[-1] if len(all_years) > 1 else ""

        first = core_lines[0].strip() if core_lines else ""
        second = core_lines[1].strip() if len(core_lines) > 1 else ""
        if second and _INSTITUTION_HINT_RE.search(second) and not _INSTITUTION_HINT_RE.search(first):
            institution, degree = second, first
        else:
            institution, degree = first, second
        degree = DATE_RANGE_RE.sub("", degree)
        degree = re.sub(r"\b(?:19|20)\d{2}\b", "", degree)
        degree = degree.strip(" ,-–—|")

        entries.append({
            "institution": institution,
            "degree": degree,
            "field_of_study": "",
            "start_year": start_year,
            "graduation_year": grad_year,
            "grade": grade,
        })
    return entries


BULLET_PREFIX_RE = re.compile(r"^(?:[•▪◦●○➤‣∙·*]|-)\s+")

# Some source PDFs render a bullet's glyph as its own separate text run,
# positioned on whichever visual line pdfplumber's row-clustering happens to
# place it on -- not necessarily the first line of that bullet's text (seen
# in practice: the glyph landing on the *second* wrapped line of a bullet,
# between two lines that are actually one continuous sentence). Such a line
# is nothing but the bullet character, with no text of its own.
# BULLET_PREFIX_RE doesn't match it (it requires real text after the glyph),
# so left alone it survives into the merge step as a stray " •" token glued
# into the middle of a sentence. It carries no information -- drop it
# outright, wherever it appears, before any bullet/section parsing runs.
_BULLET_ONLY_RE = re.compile(r"^[•▪◦●○➤‣∙·*]$")


def _drop_bullet_only_noise(lines: list[str]) -> list[str]:
    return [l for l in lines if not _BULLET_ONLY_RE.match(l.strip())]


_SENTENCE_END_CHARS = ".!?:;"


def _ends_sentence(text: str) -> bool:
    """True if `text` looks like it reached the end of a sentence/clause,
    ignoring a trailing quote or closing parenthesis (e.g. "...IAM,
    CloudWatch)." ends in ")." which still counts)."""
    t = text.rstrip().rstrip("\"')")
    return bool(t) and t[-1] in _SENTENCE_END_CHARS


def _parse_prose_section_with_headings(lines: list[str]) -> list[str]:
    """Like `_merge_prose_bullets`, but a short line with no bullet marker
    of its own and no terminal punctuation is treated as a sub-heading
    (e.g. a project's name sitting above its own description bullets)
    rather than merged into a neighboring bullet -- rendered in bold so a
    section covering several entries (Projects, multiple Achievements,
    ...) reads as distinct entries instead of one long flat bullet list.
    Used for Projects/custom sections; Experience highlights use the
    simpler `_merge_prose_bullets` since they don't have this sub-entry
    structure within a single job block."""
    cleaned = [l.strip() for l in lines if l.strip()]
    merged: list[str] = []
    current = ""
    for line in cleaned:
        has_bullet = bool(BULLET_PREFIX_RE.match(line))
        text = BULLET_PREFIX_RE.sub("", line).strip()
        if not text:
            continue
        at_boundary = not current or _ends_sentence(current)
        is_heading = (not has_bullet) and at_boundary and len(text) <= 80 and not _ends_sentence(text)
        if is_heading:
            if current:
                merged.append(current)
            merged.append(f"<b>{text}</b>")
            current = ""
            continue
        if at_boundary:
            if current:
                merged.append(current)
            current = text
        else:
            current = f"{current} {text}".strip()
    if current:
        merged.append(current)
    return merged


def _merge_prose_bullets(lines: list[str]) -> list[str]:
    """Merges a wrapped bullet's continuation lines back into the previous
    bullet, for prose-style sections (Experience highlights, Projects,
    Achievements, ...) where each bullet is normally a full sentence.

    Some source PDFs re-print the bullet glyph on every visually-wrapped
    line of a single long bullet -- not just on genuinely new bullets -- so
    "this line starts with a bullet marker" isn't a reliable signal there
    (unlike the short list items _parse_flat_list handles). Instead, a new
    bullet only starts once the text accumulated so far actually reaches a
    sentence boundary (ends in . ! ? : or ;); otherwise the next line,
    bulleted or not, is treated as the rest of the same sentence. This is
    what turns a source PDF's

        • Built and deployed AI chatbots ... embeddings, and
        • vector search.

    back into one bullet ("...embeddings, and vector search.") instead of
    two fragments, without needing OCR or layout coordinates."""
    cleaned = [l.strip() for l in lines if l.strip()]
    merged: list[str] = []
    current = ""
    for line in cleaned:
        text = BULLET_PREFIX_RE.sub("", line).strip()
        if not text:
            continue
        if not current or _ends_sentence(current):
            if current:
                merged.append(current)
            current = text
        else:
            current = f"{current} {text}".strip()
    if current:
        merged.append(current)
    return merged


def _parse_flat_list(section_lines: list[str]) -> list[str]:
    """Splits a section (skills/certifications/languages) into individual
    items, whether the source used commas, bullets, or one-per-line.

    PDF text extraction preserves each *visual* line, including where a
    single bullet's text wraps onto a second/third line -- those wrapped
    lines carry no bullet marker of their own. If any line in the section
    has a bullet marker, lines without one are treated as a continuation of
    the previous item (merged back in) rather than a new item; this is what
    keeps a single wrapped certification description from exploding into
    several fake certificates. Sections with no bullet markers at all keep
    the previous one-line-per-item / comma-split behavior, since that's the
    format most compact single-line skill lists use.
    """
    cleaned_lines = [l.strip() for l in section_lines if l.strip()]
    any_bullets = any(BULLET_PREFIX_RE.match(l) for l in cleaned_lines)

    raw_items: list[str] = []
    current = ""
    for line in cleaned_lines:
        has_bullet = bool(BULLET_PREFIX_RE.match(line))
        text = BULLET_PREFIX_RE.sub("", line).strip()
        if ":" in text and len(text.split(":", 1)[0]) < 30:
            # "Languages: Java, Python" / "Frontend: React, Vue" style lines.
            text = text.split(":", 1)[1].strip()
        if not text:
            continue

        starts_new_item = has_bullet or not any_bullets
        if starts_new_item or not current:
            if current:
                raw_items.append(current)
            current = text
        else:
            current = f"{current} {text}".strip()
    if current:
        raw_items.append(current)

    # Only comma-split when nothing in the section used bullets -- that's
    # the classic single-line list case ("Python, Django, SQL"). When
    # bullets are present, a comma inside an item is far more likely to be
    # part of a real sentence (a certificate's description, say) than a
    # list delimiter, so leave it alone.
    items = raw_items
    if not any_bullets:
        expanded = []
        for item in items:
            if "," in item and not item.rstrip().endswith("."):
                expanded.extend(p.strip() for p in item.split(",") if p.strip())
            else:
                expanded.append(item)
        items = expanded

    # De-duplicate while preserving order.
    seen = set()
    deduped = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _parse_skills(section_lines: list[str]) -> list[str]:
    """Parse skills without losing category labels such as
    "Performance Advertising: Paid search, Display".

    A category's value list ("Anaconda, Jupyter/Colab, ..., Problem
    Solving.") often wraps across several PDF lines with no bullet, colon,
    or marker of its own -- only the very last physical line ends in a
    period. An earlier version of this split each *physical* line into
    skills independently, which fragments the list wherever a comma
    happened to fall at a line wrap -- e.g. "...Statistical Analysis,
    Data" / "Manipulation, Exception Handling..." became two bogus skills
    ("Data" and "Manipulation") instead of one ("Data Manipulation"). This
    first re-joins each such wrapped run into one logical line (the same
    sentence-boundary-aware merge Experience highlights use, plus a
    heading check so a short category-name line like "Python" sitting
    above its own value list isn't swallowed into that list) -- *then*
    splits on commas/colons, so a comma inside the true skill list still
    delimits items, but a comma that merely sits at a PDF line wrap
    doesn't.
    """
    cleaned_lines = [l.strip() for l in section_lines if l.strip()]

    logical_lines: list[str] = []
    current = ""
    for line in cleaned_lines:
        has_bullet = bool(BULLET_PREFIX_RE.match(line))
        text = BULLET_PREFIX_RE.sub("", line).strip()
        if not text:
            continue
        has_colon = ":" in text and len(text.split(":", 1)[0]) < 40
        at_boundary = not current or _ends_sentence(current)
        # A short, comma-free line at a boundary reads as a category
        # heading ("Python", "SQL", ...) sitting above its own wrapped
        # value list -- close it out as its own logical line rather than
        # let the list that follows merge into it.
        is_heading = (
            at_boundary and not has_bullet and not has_colon
            and "," not in text and len(text) <= 40 and not _ends_sentence(text)
        )
        if is_heading:
            if current:
                logical_lines.append(current)
            logical_lines.append(text)
            current = ""
            continue
        if has_bullet or has_colon or at_boundary:
            if current:
                logical_lines.append(current)
            current = text
        else:
            current = f"{current} {text}".strip()
    if current:
        logical_lines.append(current)

    items: list[str] = []
    for text in logical_lines:
        if ":" in text and len(text.split(":", 1)[0]) < 40:
            label, values = (part.strip() for part in text.split(":", 1))
            values_list = [value.strip() for value in values.split(",") if value.strip()]
            if values_list:
                items.extend(f"{label}: {value}" for value in values_list)
            else:
                items.append(label)
            continue
        if "," in text:
            items.extend(part.strip() for part in text.split(",") if part.strip())
        else:
            items.append(text)

    seen = set()
    deduped = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _parse_languages(section_lines: list[str]) -> list[dict]:
    languages = []
    for item in _parse_flat_list(section_lines):
        level_key = None
        name = item
        m = re.search(r"[\(\-–]\s*([A-Za-z]+)\s*\)?$", item)
        if m and m.group(1).lower() in PROFICIENCY_WORDS:
            level_key = PROFICIENCY_WORDS[m.group(1).lower()]
            name = item[: m.start()].strip(" -–(")
        languages.append({"name": name, "proficiency_level": level_key})
    return languages


def _clean_cert_issue_date(text: str) -> str:
    text = re.sub(r"^(issued|issue\s+date|date)\s*:?\s*", "", text.strip(), flags=re.I)
    return text.strip(" ,-–—|")


# Some resumes give each certification its own combined "Name Issued <date>"
# line rather than putting the date on a separate line -- e.g. "Google
# Analytics 4 (GA4) Certification Issued Jan 2024". Used both to pull the
# date out of that line up front, and (critically) to recognize that such a
# line is always the start of a *new* certificate, even when the current one
# in progress already has a date-shaped line pending -- without that check,
# a second cert's own "Name Issued <date>" line reads as just another date
# update for the *first* cert, and the first cert's name/org never get
# flushed at all.
_CERT_ISSUED_SUFFIX_RE = re.compile(
    r"\s*(?:issued|issue\s+date)\s*:?\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4})\s*$",
    re.I,
)


def _split_cert_name_and_inline_date(text: str) -> tuple[str, str]:
    m = _CERT_ISSUED_SUFFIX_RE.search(text)
    if m:
        return text[: m.start()].strip(" ,-–—|"), m.group(1)
    return text, ""


def _parse_certification_item(item: str) -> dict:
    name, org, issue_date = item.strip(), "", ""
    if "|" in item:
        parts = [part.strip() for part in item.split("|") if part.strip()]
    elif " - " in item or " – " in item or " — " in item:
        sep = " - " if " - " in item else (" – " if " – " in item else " — ")
        parts = [part.strip() for part in item.split(sep) if part.strip()]
    elif "," in item:
        parts = [part.strip() for part in item.split(",") if part.strip()]
    else:
        parts = [item.strip()]

    if len(parts) >= 2 and all(len(part) < 60 for part in parts[:2]):
        name, org = parts[0], parts[1]
    if len(parts) >= 3:
        issue_date = _clean_cert_issue_date(parts[2])
    return {"name": name, "issuing_organization": org, "issue_date": issue_date}


def _parse_certifications_legacy_flat(section_lines: list[str]) -> list[dict]:
    certs = []
    for item in _parse_flat_list(section_lines):
        name, org = item, ""
        for sep in (" - ", " – ", "|"):
            if sep in item:
                parts = item.split(sep, 1)
                name, org = parts[0].strip(), parts[1].strip()
                break
        else:
            # A bare comma only reads as a "Name, Issuing Org" separator
            # when both halves are short (an org name, not a sentence) --
            # otherwise leave the text alone rather than slicing a
            # certificate's description in half at its first comma.
            if "," in item:
                head, _, tail = item.partition(",")
                if len(head.strip()) < 60 and len(tail.strip()) < 60:
                    name, org = head.strip(), tail.strip()
        certs.append({"name": name, "issuing_organization": org, "issue_date": ""})
    return certs


def _parse_certifications(section_lines: list[str]) -> list[dict]:
    cleaned = [
        BULLET_PREFIX_RE.sub("", line).strip()
        for line in section_lines
        if line.strip()
    ]
    if not cleaned:
        return []

    any_bullets = any(BULLET_PREFIX_RE.match(line.strip()) for line in section_lines)
    if any_bullets:
        return [_parse_certification_item(item) for item in _parse_flat_list(section_lines)]

    def _flush(cur: dict) -> dict:
        return {
            "name": cur.get("name", ""),
            "issuing_organization": cur.get("issuing_organization", ""),
            "issue_date": cur.get("issue_date", ""),
        }

    certs: list[dict] = []
    current: dict = {}
    for text in cleaned:
        if "|" in text or " - " in text or " – " in text or " — " in text:
            if current:
                certs.append(_flush(current))
            current = _parse_certification_item(text)
            continue

        name_part, inline_date = _split_cert_name_and_inline_date(text)
        # A line with real name text *and* its own trailing date is a
        # brand new certificate's combined "Name Issued <date>" line --
        # true regardless of whether `current` already has a name pending,
        # since that's exactly what a second/third certificate's own line
        # looks like in this format too. Checking this before "does this
        # just look date-ish" is what keeps the *next* cert's name from
        # being swallowed as the current cert's issue_date.
        if inline_date and len(name_part) >= 3:
            if current:
                certs.append(_flush(current))
            current = {"name": name_part, "issuing_organization": "", "issue_date": _clean_cert_issue_date(inline_date)}
            continue

        has_date = bool(
            YEAR_RE.search(text)
            or MONTH_YEAR_RE.search(text)
            or re.match(r"^(issued|issue\s+date|date)\b", text, re.I)
        )
        if has_date and current and not current.get("issue_date"):
            current["issue_date"] = _clean_cert_issue_date(text)
            continue

        if not current:
            current = {"name": text, "issuing_organization": "", "issue_date": ""}
        elif not current.get("issuing_organization"):
            current["issuing_organization"] = text
        else:
            certs.append(_flush(current))
            current = {"name": text, "issuing_organization": "", "issue_date": ""}

    if current:
        certs.append({
            "name": current.get("name", ""),
            "issuing_organization": current.get("issuing_organization", ""),
            "issue_date": current.get("issue_date", ""),
        })
    return certs


def parse_resume_text(text: str) -> Optional[dict]:
    """Turns extracted plain text into the structured shape used to render
    the ATS PDF. Returns None if the text is too sparse to be a resume."""
    if not text or not text.strip():
        return None

    lines = [l.rstrip() for l in text.splitlines()]
    lines = _drop_bullet_only_noise(lines)
    header_block, entries = _split_sections(lines)
    contact = _extract_contact(header_block, text)

    # `known` collects lines for our specifically-parsed section types
    # (summary/experience/education/skills/certifications/languages/
    # projects), keeping the longest capture if a heading repeats. Anything
    # else -- a heading only matched by the generic custom-header heuristic
    # -- goes into `customs`, in document order, merging repeats of the
    # same title so the resume's own section (Achievements, Awards,
    # Internships, Publications, ...) survives untouched.
    known: dict[str, list[str]] = {}
    customs: list[dict] = []
    custom_index_by_title: dict[str, int] = {}
    for entry in entries:
        key, title, section_lines = entry["key"], entry["title"], entry["lines"]
        if key:
            if key not in known or len(section_lines) > len(known[key]):
                known[key] = section_lines
        else:
            norm = title.lower()
            if norm in custom_index_by_title:
                customs[custom_index_by_title[norm]]["lines"].extend(section_lines)
            else:
                custom_index_by_title[norm] = len(customs)
                customs.append({"title": title, "lines": section_lines})

    summary_lines = known.get("summary", [])
    summary = " ".join(l.strip() for l in summary_lines).strip()
    if not summary and not entries:
        # No recognizable section headers at all -- likely not a resume, or
        # a format this parser can't make sense of.
        return None

    experience = _parse_experience(known.get("experience", []))
    education = _parse_education(known.get("education", []))
    skills = _parse_skills(known.get("skills", []))
    certifications = _parse_certifications(known.get("certifications", []))
    languages = _parse_languages(known.get("languages", []))

    # Any section besides the structured ones above -- "Projects" (a known
    # heading we don't have a dedicated shape for) plus every custom
    # heading -- is rendered generically as a titled bullet list, using the
    # resume's own heading text, so the ATS template shows exactly the
    # extra sections this resume actually has instead of a fixed set.
    # These are prose-style bullets (each usually a full sentence), same as
    # Experience highlights, so they get the same sentence-boundary-aware
    # merge rather than _parse_flat_list's short-list-item logic -- that's
    # what stops a wrapped project description from exploding into several
    # fragment bullets.
    extra_sections: list[dict] = []
    projects_lines = known.get("projects")
    if projects_lines:
        items = _parse_prose_section_with_headings(projects_lines)
        if items:
            extra_sections.append({"title": "Projects", "items": items})
    for key, title in _EXTRA_KNOWN_SECTION_TITLES.items():
        section_lines = known.get(key)
        if section_lines:
            items = _parse_prose_section_with_headings(section_lines)
            if items:
                extra_sections.append({"title": title, "items": items})
    for custom in customs:
        items = _parse_prose_section_with_headings(custom["lines"])
        if items:
            extra_sections.append({"title": _titleize_header(custom["title"]), "items": items})

    has_any_data = any([
        contact["full_name"], contact["email"], contact["phone"], summary,
        experience, education, skills, certifications, languages, extra_sections,
    ])
    if not has_any_data:
        return None

    return {
        "full_name": contact["full_name"],
        "headline": contact["headline"],
        "email": contact["email"],
        "phone": contact["phone"],
        "linkedin_url": contact["linkedin_url"],
        "summary": summary,
        "experience": experience,
        "education": education,
        "skills": skills,
        "certifications": certifications,
        "languages": languages,
        "extra_sections": extra_sections,
    }


def extract_resume_data(content: bytes, file_name: str = "", content_type: Optional[str] = None) -> Optional[dict]:
    """End-to-end: raw uploaded file bytes -> structured resume dict, or
    None if the file couldn't be read or didn't yield anything usable
    (e.g. a scanned/image-only PDF with no text layer)."""
    text = extract_text(content, file_name, content_type)
    return parse_resume_text(text)