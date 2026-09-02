"""
Renders a candidate's profile + resume detail data into a downloadable PDF.

This backs the "Generate ATS PDF" / "Export modern PDF" actions on the
Download CV page, and the per-version PDF download when a resume version
has no directly-uploaded file attached to it (e.g. a duplicated version).

The layout mirrors the reference "clean single-column" resume template
(name + title header row, a light-grey shaded bar per section, right-aligned
date ranges, a two-column skills grid, and a Languages line) rather than the
previous plain, unstyled paragraph dump -- while staying entirely
text-based/no-graphics so it still parses cleanly through an ATS.

Every section (Summary, Experience, Education, Skills, Languages,
Certificates) is only shown when there's actual data for it. When rendering
from an uploaded resume file's own content (render_resume_pdf_from_extracted,
backed by app.utils.resume_extraction), any additional sections the source
resume has that aren't part of that fixed set -- Projects, Internships,
Achievements, Awards, Publications, Volunteer Experience, etc. -- are
detected automatically and rendered with their own heading, in the same
bulleted, ATS-friendly format, via the `extra_sections` parameter.

Four base templates are supported -- "ats", "sidebar", "bold-header", plus
the original single-column layout reused for "ats". Any of them can be
paired with the "Modern Visual" treatment by suffixing "-modern" to the
style key (e.g. "sidebar-modern", "bold-header-modern"), or by passing the
bare legacy key "modern" (shorthand for "ats-modern", kept for backwards
compatibility with existing callers/links). The Modern Visual treatment
never changes a template's structure, section order, or content -- only
its typography: bolder section headings, an accent-tinted section bar
instead of flat grey, and slightly roomier spacing (every template already
uses the same embedded Inter font family either way). See _split_style().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import math
from typing import Optional

from pypdf import PdfReader

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Flowable,
    Frame,
)

from app.service import s3_service

# Every template uses this one embedded font family (SIL OFL 1.1 licensed,
# see app/assets/fonts/INTER-LICENSE.txt) instead of ReportLab's built-in
# Times/Helvetica, to match the reference designs' modern sans-serif look.
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
pdfmetrics.registerFont(TTFont("Inter", str(_FONT_DIR / "Inter-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Inter-Bold", str(_FONT_DIR / "Inter-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Inter-Italic", str(_FONT_DIR / "Inter-Italic.ttf")))
pdfmetrics.registerFont(TTFont("Inter-BoldItalic", str(_FONT_DIR / "Inter-BoldItalic.ttf")))
pdfmetrics.registerFontFamily("Inter", normal="Inter", bold="Inter-Bold", italic="Inter-Italic", boldItalic="Inter-BoldItalic")

ATS_ACCENT = colors.HexColor("#111827")
MODERN_ACCENT = colors.HexColor("#2563eb")
SECTION_BAR_BG = colors.HexColor("#eef0f2")
MUTED_TEXT = colors.HexColor("#6b7280")
BODY_TEXT = colors.HexColor("#1f2937")

PAGE_WIDTH = LETTER[0] - 1.5 * inch  # minus left+right margins below

PROFICIENCY_LABELS = {
    "NATIVE": "Native",
    "EXPERT": "Expert",
    "PROFESSIONAL": "Professional Working Proficiency",
    "INTERMEDIATE": "Intermediate",
    "BASIC": "Basic",
}

# Sidebar Profile shows language proficiency as a 5-dot rating instead of
# the text label the other templates use -- this maps each level to how
# many of the 5 dots are filled. Falls back to 3 (mid-scale) for an
# unrecognized/missing level rather than 0, so it never reads as "no
# proficiency at all".
PROFICIENCY_DOT_COUNTS = {
    "NATIVE": 5,
    "EXPERT": 4,
    "PROFESSIONAL": 3,
    "INTERMEDIATE": 2,
    "BASIC": 1,
}
PROFICIENCY_DOTS_DEFAULT = 3

SKILL_LEVEL_LABELS = {
    "BEGINNER": "Beginner",
    "INTERMEDIATE": "Intermediate",
    "ADVANCED": "Advanced",
    "EXPERT": "Expert",
}


def _split_style(style: str) -> tuple[str, bool]:
    """Splits a style key into (base_template, modern_enhancements).

    "ats" / "sidebar" / "bold-header" -> that template, no enhancements.
    "sidebar-modern" / "bold-header-modern" -> that template + Modern Visual
    typography. "ats-modern" and the bare legacy "modern" both mean the
    "ats" template + Modern Visual typography -- "modern" is kept as-is so
    existing links/callers using the old two-style ("ats"/"modern") API
    keep working unchanged.
    """
    if style == "modern":
        return "ats", True
    if style.endswith("-modern"):
        base = style[: -len("-modern")]
        return base, True
    return style, False


def _tint(color, factor: float):
    """Lightens `color` toward white by `factor` (0 = unchanged, 1 = white).
    Used by the Modern Visual variant for a soft accent-tinted section bar
    background instead of the flat neutral grey the base templates use --
    a visual-only change, the bar's text/structure stay identical."""
    r = color.red + (1 - color.red) * factor
    g = color.green + (1 - color.green) * factor
    b = color.blue + (1 - color.blue) * factor
    return colors.Color(r, g, b)


def _style_set(accent, scale: float = 1.0, modern: bool = False):
    bold = "Inter-Bold"
    roman = "Inter"
    italic = "Inter-Italic"
    name_size = (22 if modern else 21) * scale
    name_leading = (26 if modern else 25) * scale
    return {
        "name": ParagraphStyle("name", fontName=bold, fontSize=name_size, textColor=colors.HexColor("#111827"), leading=name_leading),
        "headerLine": ParagraphStyle("headerLine", fontName=bold, fontSize=name_size, textColor=colors.HexColor("#111827"), leading=name_leading),
        "sectionBar": ParagraphStyle("sectionBar", fontName=bold, fontSize=(11.5 if modern else 11) * scale, textColor=accent, leading=14 * scale, alignment=1),
        "entryTitle": ParagraphStyle("entryTitle", fontName=bold, fontSize=10.5 * scale, textColor=BODY_TEXT, leading=14 * scale),
        "entryMeta": ParagraphStyle("entryMeta", fontName=italic, fontSize=9.5 * scale, textColor=MUTED_TEXT, leading=13 * scale),
        "entryDate": ParagraphStyle("entryDate", fontName=roman, fontSize=9.5 * scale, textColor=MUTED_TEXT, alignment=2, leading=13 * scale),
        "bullet": ParagraphStyle("bullet", fontName=roman, fontSize=9.5 * scale, textColor=BODY_TEXT, leading=13 * scale, spaceAfter=(3 if modern else 2) * scale, leftIndent=12, bulletIndent=0),
        "body": ParagraphStyle("body", fontName=roman, fontSize=9.5 * scale, textColor=BODY_TEXT, leading=13.5 * scale),
    }


def _draw_icon(c, kind: str, x: float, y: float, s: float, color) -> None:
    """Draws one small vector icon (contact icons: email / phone / linkedin
    / location / github; section icons: profile / briefcase / graduation
    cap / skills / globe / badge) at (x, y) with size `s`, in `color`.
    Plain vector primitives -- not a font glyph -- since base-14 PDF fonts
    (Times/Helvetica) don't reliably include these symbols, and not a
    raster image, so this stays crisp at any zoom with no extra asset to
    ship. Shared by every template (ATS/Modern/Sidebar/Bold Header)."""
    c.saveState()
    c.translate(x, y)
    c.setStrokeColor(color)
    c.setFillColor(color)
    if kind == "email":
        c.setLineWidth(s * 0.09)
        c.rect(0, s * 0.15, s, s * 0.62, stroke=1, fill=0)
        c.line(0, s * 0.77, s * 0.5, s * 0.42)
        c.line(s, s * 0.77, s * 0.5, s * 0.42)
    elif kind == "phone":
        c.setLineWidth(s * 0.1)
        c.saveState()
        c.translate(s * 0.5, s * 0.45)
        c.rotate(-35)
        c.roundRect(-s * 0.42, -s * 0.15, s * 0.3, s * 0.3, s * 0.08, stroke=1, fill=0)
        c.roundRect(s * 0.12, -s * 0.15, s * 0.3, s * 0.3, s * 0.08, stroke=1, fill=0)
        c.line(-s * 0.12, 0, s * 0.12, 0)
        c.restoreState()
    elif kind == "linkedin":
        c.roundRect(0, 0, s, s, s * 0.16, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Inter-Bold", s * 0.58)
        c.drawCentredString(s * 0.5, s * 0.22, "in")
    elif kind == "location":
        c.setLineWidth(s * 0.09)
        c.circle(s * 0.5, s * 0.6, s * 0.3, stroke=1, fill=0)
        p = c.beginPath()
        p.moveTo(s * 0.5, s * 0.02)
        p.lineTo(s * 0.26, s * 0.46)
        p.lineTo(s * 0.74, s * 0.46)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
    elif kind == "github":
        c.roundRect(0, 0, s, s, s * 0.5, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Inter-Bold", s * 0.5)
        c.drawCentredString(s * 0.5, s * 0.28, "gh")
    elif kind == "profile":
        c.setLineWidth(s * 0.08)
        c.roundRect(0, 0, s, s * 0.72, s * 0.1, stroke=1, fill=0)
        c.circle(s * 0.24, s * 0.36, s * 0.15, stroke=0, fill=1)
        c.line(s * 0.48, s * 0.46, s * 0.86, s * 0.46)
        c.line(s * 0.48, s * 0.26, s * 0.86, s * 0.26)
    elif kind == "briefcase":
        c.setLineWidth(s * 0.08)
        c.roundRect(0, s * 0.1, s, s * 0.55, s * 0.08, stroke=1, fill=0)
        c.roundRect(s * 0.3, s * 0.55, s * 0.4, s * 0.22, s * 0.05, stroke=1, fill=0)
        c.line(0, s * 0.38, s, s * 0.38)
    elif kind == "graduation":
        p = c.beginPath()
        p.moveTo(0, s * 0.55)
        p.lineTo(s * 0.5, s * 0.78)
        p.lineTo(s, s * 0.55)
        p.lineTo(s * 0.5, s * 0.32)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setLineWidth(s * 0.06)
        c.line(s * 0.82, s * 0.5, s * 0.82, s * 0.18)
        c.ellipse(s * 0.32, s * 0.02, s * 0.68, s * 0.16, stroke=1, fill=0)
    elif kind == "skills":
        c.setLineWidth(s * 0.09)
        c.circle(s * 0.5, s * 0.5, s * 0.22, stroke=1, fill=0)
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x1, y1 = s * 0.5 + s * 0.3 * math.cos(rad), s * 0.5 + s * 0.3 * math.sin(rad)
            x2, y2 = s * 0.5 + s * 0.44 * math.cos(rad), s * 0.5 + s * 0.44 * math.sin(rad)
            c.line(x1, y1, x2, y2)
    elif kind == "globe":
        c.setLineWidth(s * 0.07)
        c.circle(s * 0.5, s * 0.5, s * 0.42, stroke=1, fill=0)
        c.ellipse(s * 0.24, s * 0.08, s * 0.76, s * 0.92, stroke=1, fill=0)
        c.line(s * 0.08, s * 0.5, s * 0.92, s * 0.5)
    elif kind == "badge":
        c.setLineWidth(s * 0.08)
        c.circle(s * 0.5, s * 0.62, s * 0.32, stroke=1, fill=0)
        p = c.beginPath()
        p.moveTo(s * 0.32, s * 0.4)
        p.lineTo(s * 0.24, s * 0.05)
        p.lineTo(s * 0.42, s * 0.16)
        p.lineTo(s * 0.5, s * 0.02)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


class _ContactLine(Flowable):
    """Renders the "icon  text    icon  text    ..." contact row -- e.g.
    an envelope icon then the email, a phone icon then the number, a
    LinkedIn badge then the URL, a pin then the location -- matching the
    reference template's icon-led contact line.

    Deliberately NOT built as a Table: Platypus sizes "auto" (colWidths=
    None) Table columns to a Paragraph's *minimum wrappable width*, not its
    actual rendered width, which is exactly what glued the name and title
    together with no gap in the header before that was fixed (see
    _render_resume_pdf_impl). Manually drawing each icon and text run at
    hand-computed x-positions sidesteps that entirely.
    """

    def __init__(self, items: list[tuple[str, str]], font_name: str, font_size: float, color, gap: float = 8.0, icon_text_gap: float = 4.0):
        super().__init__()
        self.items = items
        self.font_name = font_name
        self.font_size = font_size
        self.color = color
        self.gap = gap
        self.icon_text_gap = icon_text_gap
        self.icon_size = font_size * 1.1
        self.width = 0.0
        self.height = max(self.icon_size, font_size) * 1.2

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return (availWidth, self.height)

    def draw(self):
        c = self.canv
        x = 0.0
        text_baseline = (self.height - self.font_size) / 2 + self.font_size * 0.15
        icon_y = (self.height - self.icon_size) / 2
        for kind, text in self.items:
            _draw_icon(c, kind, x, icon_y, self.icon_size, self.color)
            x += self.icon_size + self.icon_text_gap
            c.setFont(self.font_name, self.font_size)
            c.setFillColor(self.color)
            c.drawString(x, text_baseline, text)
            x += stringWidth(text, self.font_name, self.font_size) + self.gap


class _IconCell(Flowable):
    """A single icon sized to fit as its own Table cell (Tables need a
    flowable with wrap()/draw(); this just delegates to _draw_icon)."""

    def __init__(self, kind: str, size: float, color):
        super().__init__()
        self.kind = kind
        self.size = size
        self.color = color
        self.width = size
        self.height = size

    def wrap(self, availWidth, availHeight):
        return (self.size, self.size)

    def draw(self):
        _draw_icon(self.canv, self.kind, 0, 0, self.size, self.color)


def _icon_heading_row(icon_kind: str, title: str, font_name: str, font_size: float, color,
                       page_width: float, shaded: bool = False, shade_color=None, icon_size=None) -> Table:
    """An icon + bold heading text row -- e.g. a briefcase icon next to
    "WORK EXPERIENCE" -- used by the Sidebar and Bold Header templates.
    `shaded=True` adds a light grey full-width background bar (Sidebar
    template's main column); `shaded=False` is a plain icon+text line with
    no background (Bold Header template's minimal section headings).

    Built with EXPLICIT (non-None) Table column widths -- unlike the old
    2-column header Table that glued the candidate's name and title
    together (colWidths=[None, None] sizes Platypus columns to a
    Paragraph's *minimum wrappable word width*, not its real width; see
    the header-line fix in _render_resume_pdf_impl). Known widths sidestep
    that bug entirely.
    """
    icon_size = icon_size or font_size * 1.3
    gap = font_size * 0.45
    icon_cell = _IconCell(icon_kind, icon_size, color)
    text_style = ParagraphStyle("iconHeadingText", fontName=font_name, fontSize=font_size, textColor=color, leading=font_size * 1.25)
    text_cell = Paragraph(title, text_style)
    tbl = Table([[icon_cell, text_cell]], colWidths=[icon_size + gap, page_width - icon_size - gap])
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6 if shaded else 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6 if shaded else 1),
    ]
    if shaded:
        cmds.append(("BACKGROUND", (0, 0), (-1, -1), shade_color or SECTION_BAR_BG))
        cmds.append(("LEFTPADDING", (0, 0), (-1, -1), 8))
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _gather_resume_content(profile, user, resume_detail, extra_sections: Optional[list] = None) -> dict:
    """Extracts a template-agnostic content dict (name, headline, contact,
    summary, experience, education, skills, languages, certifications,
    extra sections) from a candidate's profile/resume_detail. Every
    template (ATS, Modern, Sidebar, Bold Header) reads from this same
    structure, so switching templates only changes how a resume is
    *drawn*, never what data it shows -- selecting a different template
    for the same resume renders the same underlying content."""
    full_name = f"{_safe(getattr(user, 'first_name', None))} {_safe(getattr(user, 'last_name', None))}".strip() or "Candidate"
    headline = _safe(getattr(profile, "headline", None))
    country_code = _safe(getattr(user, "country_code", None))
    mobile_number = _safe(getattr(user, "mobile_number", None))
    phone = f"{country_code} {mobile_number}".strip() if mobile_number else ""
    contact_items = [(kind, text) for kind, text in [
        ("email", _safe(getattr(user, "email", None))),
        ("phone", phone),
        ("linkedin", _safe(getattr(profile, "linkedin_url", None))),
        ("location", _safe(getattr(profile, "current_location", None))),
    ] if text]
    summary = _safe(getattr(profile, "summary", None))

    experience = []
    for item in ((resume_detail.experience_json or {}).get("experience") if resume_detail else None) or []:
        role = _safe(item.get("role") or item.get("title"))
        company = _safe(item.get("company"))
        location = _safe(item.get("location"))
        start = _format_month(item.get("start_date"))
        end = "Present" if item.get("currently_working") else _format_month(item.get("end_date"))
        dates = " – ".join([b for b in [start, end] if b])
        highlights = _safe(item.get("key_highlights"))
        bullets = [ln.strip(" -•\t") for ln in highlights.splitlines() if ln.strip()] if highlights else []
        experience.append({"role": role, "company": company, "location": location, "dates": dates, "bullets": bullets})

    education = []
    for item in ((resume_detail.education_json or {}).get("education") if resume_detail else None) or []:
        institution = _safe(item.get("institution") or item.get("school"))
        degree = ", ".join([b for b in [_safe(item.get("degree")), _safe(item.get("field_of_study"))] if b])
        start_year = _safe(str(item.get("start_year"))) if item.get("start_year") else ""
        grad_year = _safe(str(item.get("graduation_year"))) if item.get("graduation_year") else ""
        dates = " – ".join([b for b in [start_year, grad_year] if b])
        education.append({"institution": institution, "degree": degree, "dates": dates, "grade": _safe(item.get("grade"))})

    skills_raw = (resume_detail.skills_json if resume_detail else None) or {}
    skill_list = skills_raw.get("skills") if isinstance(skills_raw, dict) else None
    skills = []
    for s in (skill_list or []):
        if isinstance(s, dict):
            label = _safe(s.get("name"))
            level = SKILL_LEVEL_LABELS.get(str(s.get("level") or "").upper())
            skills.append(f"{label} ({level})" if label and level else label)
        else:
            skills.append(_safe(s))
    skills = [s for s in skills if s]

    languages = []
    for item in ((resume_detail.languages_json or {}).get("languages") if resume_detail else None) or []:
        name = _safe(item.get("name"))
        level_key = str(item.get("proficiency_level") or "").upper()
        level = PROFICIENCY_LABELS.get(level_key)
        if name:
            dots = PROFICIENCY_DOT_COUNTS.get(level_key, PROFICIENCY_DOTS_DEFAULT) if level else 0
            languages.append({"name": name, "level": level or "", "dots": dots})

    certifications = []
    for item in ((resume_detail.certifications_json or {}).get("certifications") if resume_detail else None) or []:
        if isinstance(item, dict):
            certifications.append({
                "name": _safe(item.get("name")),
                "org": _safe(item.get("issuing_organization")),
                "date": _format_month(item.get("issue_date")),
            })
        else:
            certifications.append({"name": _safe(item), "org": "", "date": ""})

    return {
        "full_name": full_name, "headline": headline, "contact_items": contact_items,
        "summary": summary, "experience": experience, "education": education,
        "skills": skills, "languages": languages, "certifications": certifications,
        "extra_sections": extra_sections or [],
        "photo_key": _safe(getattr(user, "profile_image_url", None)),
    }



def _safe(value: Optional[str]) -> str:
    return (value or "").strip()


def _format_month(value) -> str:
    """Accepts a date, a datetime, or a 'YYYY-MM'/'YYYY-MM-DD' string and
    returns a short 'Mon YYYY' label; falls back to the raw value untouched
    if it doesn't parse (so we never hide real data behind a blank field)."""
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%b %Y")
    text = str(value).strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            from datetime import datetime
            return datetime.strptime(text, fmt).strftime("%b %Y")
        except ValueError:
            continue
    return text


def _section_bar(title: str, accent, styles, page_width=PAGE_WIDTH, modern: bool = False) -> Table:
    """A full-width shaded bar with an uppercase section title -- the
    "SUMMARY" / "PROFESSIONAL EXPERIENCE" / etc. headers in the reference
    template, instead of a plain bold paragraph. In the Modern Visual
    variant the background is a soft tint of the accent color (instead of
    flat grey) with a bolder rule underneath and a touch more padding --
    same bar, same title, same position in the layout."""
    bg = _tint(accent, 0.88) if modern else SECTION_BAR_BG
    pad = 6 if modern else 4
    line_width = 1.6 if modern else 1
    bar = Table(
        [[Paragraph(title.upper(), styles["sectionBar"])]],
        colWidths=[page_width],
    )
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 10 if modern else 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10 if modern else 8),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("LINEBELOW", (0, 0), (-1, -1), line_width, accent),
    ]))
    return bar


def _title_date_row(left_paragraphs, date_text: str, styles, page_width=PAGE_WIDTH) -> Table:
    """Two-column row: left-aligned title/company block, right-aligned date
    range -- matches the "Head of Product ... May 2020 – Present" rows."""
    right = Paragraph(date_text, styles["entryDate"]) if date_text else Paragraph("", styles["entryDate"])
    row = Table(
        [[left_paragraphs, right]],
        colWidths=[page_width - 1.6 * inch, 1.6 * inch],
    )
    row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return row


def _render_bullet_section(flow: list, title: str, lines: list[str], accent, styles, scale: float = 1.0, page_width=PAGE_WIDTH, modern: bool = False) -> None:
    """Renders a titled section as a bulleted list -- the same ATS-friendly
    shaded-bar-plus-bullets layout used for Certificates, now shared with
    any additional section detected in an uploaded resume (Projects,
    Internships, Achievements, Awards, Publications, ...).

    A line already wrapped in "<b>...</b>" (see
    app.utils.resume_extraction._parse_prose_section_with_headings) is a
    sub-entry heading -- e.g. one project's name sitting above its own
    description bullets -- and renders as a bold line with no bullet dot
    and a little extra space above it, instead of another indistinguishable
    bullet, so a section covering several entries reads as distinct items.
    """
    lines = [l for l in lines if l]
    if not title or not lines:
        return
    flow.append(_section_bar(title, accent, styles, page_width, modern=modern))
    flow.append(Spacer(1, (9 if modern else 8) * scale))
    for i, line in enumerate(lines):
        is_heading = line.startswith("<b>") and line.endswith("</b>")
        if is_heading:
            if i > 0:
                flow.append(Spacer(1, (5 if modern else 4) * scale))
            flow.append(Paragraph(line, styles["entryTitle"]))
        else:
            flow.append(Paragraph(f"•&nbsp;&nbsp;{line}", styles["bullet"]))
    flow.append(Spacer(1, (12 if modern else 10) * scale))


BOLD_HEADER_BG = colors.HexColor("#111111")


def _render_bold_header_pdf(content: dict, scale: float = 1.0, modern: bool = False) -> bytes:
    """"Bold Header" template: a full-width dark band across the top of
    page 1 (name, title, contact in white), then a clean white body with
    icon-led section headings on a light grey shaded bar and a 3-column
    grid for Skills/Languages/Certificates. Matches the reference "Aulia
    Prameswari" style layout.

    `modern=True` layers the Modern Visual typography on top (bolder
    heading rows, a touch more breathing room) -- the band,
    section order, and every piece of content are unchanged."""
    heading_font = "Inter-Bold"
    band_name_font = "Inter-Bold"
    band_text_font = "Inter"
    heading_gap = 7 if modern else 6
    margin = 0.65 * inch
    page_w, page_h = LETTER
    page_width = page_w - 2 * margin

    band_rows = 1 + (1 if content["contact_items"] else 0)
    contact_rows = (len(content["contact_items"]) + 1) // 2 if content["contact_items"] else 0
    band_height = (0.62 + 0.22 * max(contact_rows, 1) + 0.3) * inch * max(scale, 0.75)

    def draw_band(canv, doc):
        canv.saveState()
        canv.setFillColor(BOLD_HEADER_BG)
        canv.rect(0, page_h - band_height, page_w, band_height, fill=1, stroke=0)

        name_size = 22 * scale
        title_size = 12.5 * scale
        text_x = margin
        text_y = page_h - 0.5 * inch * max(scale, 0.8)
        canv.setFillColor(colors.white)
        canv.setFont(band_name_font, name_size)
        canv.drawString(text_x, text_y, content["full_name"])
        if content["headline"]:
            text_y -= name_size * 0.95
            canv.setFont(band_text_font, title_size)
            canv.drawString(text_x, text_y, content["headline"])

        # Contact info in a 2-column grid, icon-led, white on the dark band.
        if content["contact_items"]:
            col_w = page_width / 2
            row_h = 0.24 * inch * max(scale, 0.8)
            icon_size = 9.5 * scale
            font_size = 9.5 * scale
            start_y = text_y - name_size * 0.75
            for i, (kind, text) in enumerate(content["contact_items"]):
                col = i % 2
                row = i // 2
                cx = margin + col * col_w
                cy = start_y - row * row_h
                _draw_icon(canv, kind, cx, cy - icon_size * 0.75, icon_size, colors.white)
                canv.setFont(band_text_font, font_size)
                canv.setFillColor(colors.white)
                canv.drawString(cx + icon_size + 6, cy - icon_size * 0.7, text)
        canv.restoreState()

    accent = colors.HexColor("#111111")
    styles = _style_set(accent, scale=scale, modern=modern)
    # Bold Header section headings are plain icon+bold-text, no shaded bar.
    flow: list = []

    def heading(icon_kind, title):
        flow.append(_icon_heading_row(icon_kind, title.upper(), heading_font, 12 * scale, accent, page_width, shaded=True))
        flow.append(Spacer(1, heading_gap * scale))

    def bullets(lines):
        for line in lines:
            flow.append(Paragraph(f"•&nbsp;&nbsp;{line}", styles["bullet"]))

    def ncol_grid(items, n=3):
        rows = []
        for i in range(0, len(items), n):
            row = items[i:i + n]
            row += [""] * (n - len(row))
            rows.append([Paragraph(f"•&nbsp;&nbsp;{t}" if t else "", styles["bullet"]) for t in row])
        if rows:
            grid = Table(rows, colWidths=[page_width / n] * n)
            grid.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            flow.append(grid)

    if content["summary"]:
        heading("profile", "Summary")
        flow.append(Paragraph(content["summary"], styles["body"]))
        flow.append(Spacer(1, 10 * scale))

    if content["experience"]:
        heading("briefcase", "Professional Experience")
        for exp in content["experience"]:
            title_bits = [b for b in [exp["role"], exp["company"]] if b]
            left = Paragraph(", ".join(title_bits), styles["entryTitle"]) if title_bits else Paragraph("", styles["entryTitle"])
            date_loc = " | ".join([b for b in [exp["dates"], exp["location"]] if b])
            flow.append(_title_date_row(left, date_loc, styles, page_width))
            bullets(exp["bullets"])
            flow.append(Spacer(1, 8 * scale))

    if content["education"]:
        heading("graduation", "Education")
        for edu in content["education"]:
            title_bits = [b for b in [edu["institution"], edu["degree"]] if b]
            left = Paragraph(", ".join(title_bits), styles["entryTitle"])
            flow.append(_title_date_row(left, edu["dates"], styles, page_width))
        flow.append(Spacer(1, 10 * scale))

    if content["skills"]:
        heading("skills", "Skills")
        ncol_grid(content["skills"], n=3)
        flow.append(Spacer(1, 10 * scale))

    if content["languages"]:
        heading("globe", "Languages")
        lang_items = [f'{l["name"]}' + (f' ({l["level"]})' if l["level"] else '') for l in content["languages"]]
        ncol_grid(lang_items, n=3)
        flow.append(Spacer(1, 10 * scale))

    if content["certifications"]:
        heading("badge", "Certificates")
        cert_items = [" — ".join([b for b in [c["name"], c["org"]] if b]) for c in content["certifications"]]
        ncol_grid(cert_items, n=3)
        flow.append(Spacer(1, 10 * scale))

    for section in content["extra_sections"]:
        title = _safe(section.get("title"))
        items = [_safe(i) for i in (section.get("items") or [])]
        if title and items:
            heading("badge", title)
            for it in items:
                if it.startswith("<b>") and it.endswith("</b>"):
                    flow.append(Paragraph(it, styles["entryTitle"]))
                else:
                    flow.append(Paragraph(f"•&nbsp;&nbsp;{it}", styles["bullet"]))
            flow.append(Spacer(1, 10 * scale))

    if not flow:
        flow.append(Paragraph(
            "This candidate hasn't added resume details yet. Complete the resume builder to generate a full document.",
            styles["body"],
        ))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=LETTER,
        leftMargin=margin, rightMargin=margin,
        topMargin=band_height + 0.25 * inch, bottomMargin=0.5 * inch,
    )
    doc.build(flow, onFirstPage=draw_band, onLaterPages=lambda c, d: None)
    return buffer.getvalue()



SIDEBAR_BG = colors.HexColor("#1e2b3c")
SIDEBAR_TEXT = colors.HexColor("#e5e9ee")
SIDEBAR_MUTED = colors.HexColor("#9fb0c3")


def _sidebar_styles(scale: float, modern: bool = False) -> dict:
    """The Modern Visual variant here is a lighter touch than the size/tint
    changes used elsewhere: slightly larger, bolder section headings and a
    little extra leading for breathing room -- same two-column structure,
    same content, same Inter font family either way."""
    name_size = (20 if modern else 19) * scale
    heading_size = (11.5 if modern else 11) * scale
    main_heading_size = (12 if modern else 11.5) * scale
    return {
        "name": ParagraphStyle("sbName", fontName="Inter-Bold", fontSize=name_size, textColor=colors.white, leading=(name_size / scale + 3) * scale),
        "title": ParagraphStyle("sbTitle", fontName="Inter", fontSize=11.5 * scale, textColor=SIDEBAR_TEXT, leading=15 * scale),
        "heading": ParagraphStyle("sbHeading", fontName="Inter-Bold", fontSize=heading_size, textColor=colors.white, leading=14 * scale),
        "body": ParagraphStyle("sbBody", fontName="Inter", fontSize=9 * scale, textColor=SIDEBAR_TEXT, leading=13 * scale),
        "bodyBold": ParagraphStyle("sbBodyBold", fontName="Inter-Bold", fontSize=9 * scale, textColor=colors.white, leading=13 * scale),
        "contact": ParagraphStyle("sbContact", fontName="Inter", fontSize=8.7 * scale, textColor=SIDEBAR_TEXT, leading=12 * scale),
        "mainHeading": ParagraphStyle("mainHeading", fontName="Inter-Bold", fontSize=main_heading_size, textColor=colors.HexColor("#111827"), leading=14 * scale),
        "entryTitle": ParagraphStyle("sbEntryTitle", fontName="Inter-Bold", fontSize=10 * scale, textColor=BODY_TEXT, leading=13 * scale),
        "entryMeta": ParagraphStyle("sbEntryMeta", fontName="Inter-Italic", fontSize=9 * scale, textColor=MUTED_TEXT, leading=12 * scale),
        "entryDate": ParagraphStyle("sbEntryDate", fontName="Inter", fontSize=9 * scale, textColor=MUTED_TEXT, alignment=2, leading=12 * scale),
        "bullet": ParagraphStyle("sbBullet", fontName="Inter", fontSize=9 * scale, textColor=BODY_TEXT, leading=12.5 * scale, spaceAfter=(3 if modern else 2) * scale, leftIndent=10),
    }


class _SidebarContactRow(Flowable):
    """One icon+text contact line for the dark sidebar column (white/light
    icon and text on the dark background)."""

    def __init__(self, kind: str, text: str, scale: float):
        super().__init__()
        self.kind = kind
        self.text = text
        self.font_size = 8.7 * scale
        self.icon_size = self.font_size * 1.3
        self.height = max(self.icon_size, self.font_size) * 1.3
        self.width = 0.0

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return (availWidth, self.height)

    def draw(self):
        c = self.canv
        icon_y = (self.height - self.icon_size) / 2
        _draw_icon(c, self.kind, 0, icon_y, self.icon_size, SIDEBAR_TEXT)
        c.setFont("Inter", self.font_size)
        c.setFillColor(SIDEBAR_TEXT)
        text_y = (self.height - self.font_size) / 2 + self.font_size * 0.2
        max_width = self.width - self.icon_size - 6
        text = self.text
        if stringWidth(text, "Inter", self.font_size) > max_width:
            while text and stringWidth(text + "…", "Inter", self.font_size) > max_width:
                text = text[:-1]
            text = text + "…" if text != self.text else text
        c.drawString(self.icon_size + 6, text_y, text)


class _LanguageDotRow(Flowable):
    """One "Name  ● ● ● ○ ○" row for the sidebar's LANGUAGES block --
    `dots` (0-5) filled circles out of 5 total, matching the reference
    template's dot-rating instead of a text proficiency label."""

    def __init__(self, name: str, dots: int, scale: float, total: int = 5):
        super().__init__()
        self.name = name
        self.dots = max(0, min(total, dots))
        self.total = total
        self.font_size = 9 * scale
        self.dot_r = self.font_size * 0.16
        self.dot_gap = self.dot_r * 2.6
        self.height = self.font_size * 1.3
        self.width = 0.0

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return (availWidth, self.height)

    def draw(self):
        c = self.canv
        c.setFont("Inter-Bold", self.font_size)
        c.setFillColor(colors.white)
        text_y = (self.height - self.font_size) / 2 + self.font_size * 0.2
        c.drawString(0, text_y, self.name)

        dots_width = self.total * self.dot_gap
        x = self.width - dots_width
        dot_y = self.height / 2
        for i in range(self.total):
            filled = i < self.dots
            c.setFillColor(colors.white if filled else SIDEBAR_BG)
            c.setStrokeColor(SIDEBAR_TEXT)
            c.setLineWidth(0.6)
            c.circle(x + self.dot_r, dot_y, self.dot_r, stroke=1, fill=1)
            x += self.dot_gap


def _render_sidebar_pdf(content: dict, scale: float = 1.0, modern: bool = False) -> tuple[bytes, bool]:
    """"Sidebar Profile" template: a dark navy sidebar (candidate photo if
    on file, name, title, contact, profile summary, a 5-dot language
    proficiency rating) alongside a white main column (work experience,
    education, skills, certificates). Matches the reference "Brian T.
    Wayne" style layout.

    Built as two independent Frames filled directly via
    Frame.addFromList(...) rather than SimpleDocTemplate's automatic flow,
    since Platypus's normal multi-frame flow fills one frame completely
    before moving to the next -- it can't hold two *different* columns of
    content side by side on the same page. Frame.addFromList() only fills
    *one* page's worth of a Frame and, unlike SimpleDocTemplate, has no
    built-in notion of "start a new page and keep going" -- left entirely
    to itself it silently drops whatever doesn't fit instead of erroring,
    which is exactly what happened for any candidate with enough content
    to genuinely need a second page (the in-app preview has no such limit,
    so it looked fine there right up until download).

    This works around that by looping: draw the navy sidebar background,
    hand each column's remaining flowables to a fresh Frame, and -- as
    long as either column still has leftover content afterward -- start a
    new page and repeat, so a long resume spills onto page 2, 3, etc.
    exactly the way the other templates already do, instead of losing
    content. Returns (pdf_bytes, fits_on_one_page) so the caller's
    auto-shrink loop (render_resume_pdf) can still prefer the most compact
    scale that fits on a single page, the same way it does for the other
    templates -- but unlike before, whichever scale it ultimately falls
    back to now always renders *all* of the content, never a silent cut.
    """
    page_w, page_h = LETTER
    sidebar_w = page_w * 0.33
    margin = 0.35 * inch
    styles = _sidebar_styles(scale, modern=modern)
    accent = MODERN_ACCENT if modern else ATS_ACCENT

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)

    left = []

    # Circular candidate photo at the top of the sidebar, if one's on file.
    # Drawn directly on the canvas (same as the SIDEBAR_BG rect below)
    # rather than as a Flowable, then a matching Spacer reserves that
    # vertical space in the `left` Frame's flow so the text below doesn't
    # overlap it. Only ever drawn once, on the first page -- it's part of
    # the sidebar's header, not something that should repeat on page 2+.
    # A missing/stale S3 key degrades gracefully -- no photo, no error --
    # rather than failing the whole PDF.
    photo_diameter = 0.95 * inch * max(scale, 0.7)
    photo_bytes_cache = None
    if content.get("photo_key"):
        try:
            photo_bytes_cache, _ = s3_service.fetch_object_bytes(content["photo_key"])
            left.append(Spacer(1, photo_diameter + 10 * scale))
        except Exception:
            photo_bytes_cache = None

    left.append(Paragraph(content["full_name"], styles["name"]))
    if content["headline"]:
        left.append(Spacer(1, 2 * scale))
        left.append(Paragraph(content["headline"], styles["title"]))
    left.append(Spacer(1, 12 * scale))
    for kind, text in content["contact_items"]:
        left.append(_SidebarContactRow(kind, text, scale))
        left.append(Spacer(1, 5 * scale))

    if content["summary"]:
        left.append(Spacer(1, 10 * scale))
        left.append(_icon_heading_row("profile", "PROFILE", "Inter-Bold", 10.5 * scale, colors.white, sidebar_w - 2 * margin, icon_size=13 * scale))
        left.append(Spacer(1, 6 * scale))
        left.append(Paragraph(content["summary"], styles["body"]))

    if content["languages"]:
        left.append(Spacer(1, 12 * scale))
        left.append(_icon_heading_row("globe", "LANGUAGES", "Inter-Bold", 10.5 * scale, colors.white, sidebar_w - 2 * margin, icon_size=13 * scale))
        left.append(Spacer(1, 6 * scale))
        for lang in content["languages"]:
            left.append(_LanguageDotRow(lang["name"], lang.get("dots", 0), scale))
            left.append(Spacer(1, 4 * scale))

    right_x = sidebar_w
    right_w = page_w - sidebar_w
    right = []

    if content["experience"]:
        right.append(_icon_heading_row("briefcase", "WORK EXPERIENCE", "Inter-Bold", 11 * scale, accent, right_w - 2 * margin, shaded=True))
        right.append(Spacer(1, 8 * scale))
        for exp in content["experience"]:
            right.append(Paragraph(exp["company"] or exp["role"], styles["entryTitle"]))
            meta_bits = [b for b in [exp["role"] if exp["company"] else "", exp["location"]] if b]
            if meta_bits:
                right.append(Paragraph(" · ".join(meta_bits), styles["entryMeta"]))
            if exp["dates"]:
                right.append(Paragraph(exp["dates"], styles["entryMeta"]))
            for b in exp["bullets"]:
                right.append(Paragraph(f"•&nbsp;&nbsp;{b}", styles["bullet"]))
            right.append(Spacer(1, 8 * scale))

    if content["education"]:
        right.append(_icon_heading_row("graduation", "EDUCATION", "Inter-Bold", 11 * scale, accent, right_w - 2 * margin, shaded=True))
        right.append(Spacer(1, 8 * scale))
        for edu in content["education"]:
            right.append(Paragraph(edu["degree"] or edu["institution"], styles["entryTitle"]))
            if edu["degree"] and edu["institution"]:
                right.append(Paragraph(edu["institution"], styles["entryMeta"]))
            if edu["dates"]:
                right.append(Paragraph(edu["dates"], styles["entryMeta"]))
            right.append(Spacer(1, 6 * scale))

    if content["skills"]:
        right.append(_icon_heading_row("skills", "SKILLS", "Inter-Bold", 11 * scale, accent, right_w - 2 * margin, shaded=True))
        right.append(Spacer(1, 8 * scale))
        for s in content["skills"]:
            right.append(Paragraph(f"•&nbsp;&nbsp;{s}", styles["bullet"]))

    if content["certifications"]:
        right.append(Spacer(1, 10 * scale))
        right.append(_icon_heading_row("badge", "CERTIFICATES", "Inter-Bold", 11 * scale, accent, right_w - 2 * margin, shaded=True))
        right.append(Spacer(1, 8 * scale))
        for cert in content["certifications"]:
            right.append(Paragraph(cert["name"], styles["entryTitle"]))
            meta = " · ".join([b for b in [cert["org"], cert["date"]] if b])
            if meta:
                right.append(Paragraph(meta, styles["entryMeta"]))
            right.append(Spacer(1, 4 * scale))

    for section in content["extra_sections"]:
        title = _safe(section.get("title"))
        items = [_safe(i) for i in (section.get("items") or [])]
        if title and items:
            right.append(Spacer(1, 10 * scale))
            right.append(_icon_heading_row("badge", title.upper(), "Inter-Bold", 11 * scale, accent, right_w - 2 * margin, shaded=True))
            right.append(Spacer(1, 8 * scale))
            for it in items:
                if it.startswith("<b>") and it.endswith("</b>"):
                    right.append(Paragraph(it, styles["entryTitle"]))
                else:
                    right.append(Paragraph(f"•&nbsp;&nbsp;{it}", styles["bullet"]))

    if not right:
        right.append(Paragraph("No resume details added yet.", styles["entryMeta"]))

    fits_on_one_page = True
    # Safety cap: addFromList() making genuinely zero progress on a page
    # (e.g. one single flowable too tall to ever fit the frame at all)
    # would otherwise loop forever redrawing an identical, still-full page.
    # A resume needing more than this many pages is already far beyond
    # anything realistic, so bailing out here just stops a pathological
    # input from hanging the request -- it isn't a limit any real resume
    # should ever hit.
    max_pages = 30
    page_num = 0
    while True:
        page_num += 1
        c.setFillColor(SIDEBAR_BG)
        c.rect(0, 0, sidebar_w, page_h, fill=1, stroke=0)

        if page_num == 1 and photo_bytes_cache:
            try:
                photo = ImageReader(BytesIO(photo_bytes_cache))
                cx = sidebar_w / 2
                cy = page_h - margin - photo_diameter / 2
                c.saveState()
                clip = c.beginPath()
                clip.circle(cx, cy, photo_diameter / 2)
                c.clipPath(clip, stroke=0, fill=0)
                c.drawImage(
                    photo, cx - photo_diameter / 2, cy - photo_diameter / 2,
                    width=photo_diameter, height=photo_diameter,
                    preserveAspectRatio=True, mask="auto",
                )
                c.restoreState()
            except Exception:
                pass

        left_before = len(left)
        left_frame = Frame(margin, margin, sidebar_w - 2 * margin, page_h - 2 * margin, showBoundary=0)
        left_frame.addFromList(left, c)  # mutates `left`, removing what fit

        right_before = len(right)
        right_frame = Frame(right_x + margin, margin, right_w - 2 * margin, page_h - 2 * margin, showBoundary=0)
        right_frame.addFromList(right, c)  # mutates `right`, removing what fit

        if left or right:
            fits_on_one_page = False
            made_progress = len(left) < left_before or len(right) < right_before
            if not made_progress or page_num >= max_pages:
                # Truly can't make further progress (or hit the safety
                # cap) -- stop rather than loop forever on an identical page.
                break
            c.showPage()
            continue
        break

    c.showPage()
    c.save()
    return buffer.getvalue(), fits_on_one_page


def _render_resume_pdf_impl(profile, user, resume_detail, modern: bool = False, extra_sections: Optional[list] = None, scale: float = 1.0) -> bytes:
    accent = MODERN_ACCENT if modern else ATS_ACCENT
    styles = _style_set(accent, scale=scale, modern=modern)
    name_font = "Inter-Bold"
    italic_font = "Inter-Italic"
    roman_font = "Inter"

    buffer = BytesIO()
    # Margins shrink a little as scale drops too, so a long resume gets
    # extra room to fit on one page instead of relying on font/spacing
    # shrinkage alone.
    margin = (0.75 if scale >= 0.99 else 0.55) * inch
    top_bottom_margin = (0.7 if scale >= 0.99 else 0.5) * inch
    doc = SimpleDocTemplate(
        buffer, pagesize=LETTER,
        leftMargin=margin, rightMargin=margin,
        topMargin=top_bottom_margin, bottomMargin=top_bottom_margin,
    )

    flow = []
    page_width = LETTER[0] - 2 * margin

    # ── Header: Name + title on one line, then a contact line ──
    # Previously built as a 2-column Table with colWidths=[None, None] --
    # Platypus sizes "auto" Table columns to a Paragraph's *minimum*
    # wrappable width (roughly its longest unbreakable word), not its
    # actual rendered width, so the name and title columns collapsed
    # against each other with no real gap between them (e.g. "Susmitha
    # BhumireddyAI/ML Engineer" glued together with no space). A single
    # Paragraph with inline <font> tags avoids column sizing entirely and
    # guarantees a literal gap between the two.
    full_name = f"{_safe(getattr(user, 'first_name', None))} {_safe(getattr(user, 'last_name', None))}".strip() or "Candidate"
    headline = _safe(getattr(profile, "headline", None))
    name_size = 21 * scale
    title_size = 13 * scale
    if headline:
        flow.append(Paragraph(
            f'<font name="{name_font}" size="{name_size:.1f}" color="#111827">{full_name}</font>'
            f'&nbsp;&nbsp;&nbsp;'
            f'<font name="{italic_font}" size="{title_size:.1f}" color="#374151">{headline}</font>',
            styles["headerLine"],
        ))
    else:
        flow.append(Paragraph(full_name, styles["name"]))

    # _ContactLine is a raw Flowable (not a Paragraph), so it never picks up
    # a ParagraphStyle's spaceBefore automatically -- without an explicit
    # Spacer here it would render flush against the header line above with
    # no gap at all, especially for resumes with no extracted headline
    # (single "name" line) where this was visibly cramped.
    flow.append(Spacer(1, 4 * scale))

    country_code = _safe(getattr(user, "country_code", None))
    mobile_number = _safe(getattr(user, "mobile_number", None))
    phone = f"{country_code} {mobile_number}".strip() if mobile_number else ""
    contact_items = [(kind, text) for kind, text in [
        ("email", _safe(getattr(user, "email", None))),
        ("phone", phone),
        ("linkedin", _safe(getattr(profile, "linkedin_url", None))),
        ("location", _safe(getattr(profile, "current_location", None))),
    ] if text]
    if contact_items:
        flow.append(_ContactLine(contact_items, roman_font, 9.5 * scale, MUTED_TEXT))
        flow.append(Spacer(1, 8 * scale))
    else:
        flow.append(Spacer(1, 10 * scale))

    # ── Summary ──
    summary = _safe(getattr(profile, "summary", None))
    if summary:
        flow.append(_section_bar("Summary", accent, styles, page_width, modern=modern))
        flow.append(Spacer(1, 6 * scale))
        flow.append(Paragraph(summary, styles["body"]))
        flow.append(Spacer(1, 10 * scale))

    # ── Professional Experience ──
    experience = ((resume_detail.experience_json or {}).get("experience") if resume_detail else None) or []
    if experience:
        flow.append(_section_bar("Professional Experience", accent, styles, page_width, modern=modern))
        flow.append(Spacer(1, 8 * scale))
        for item in experience:
            role = _safe(item.get("role") or item.get("title"))
            company = _safe(item.get("company"))
            location = _safe(item.get("location"))
            start = _format_month(item.get("start_date"))
            end = "Present" if item.get("currently_working") else _format_month(item.get("end_date"))
            dates = " – ".join([b for b in [start, end] if b])

            title_block = [Paragraph(role, styles["entryTitle"])] if role else []
            meta_bits = [b for b in [company, location] if b]
            if meta_bits:
                title_block.append(Paragraph(" · ".join(meta_bits), styles["entryMeta"]))

            flow.append(_title_date_row(title_block or [Paragraph("", styles["entryTitle"])], dates, styles, page_width))
            flow.append(Spacer(1, 3 * scale))

            highlights = _safe(item.get("key_highlights"))
            if highlights:
                for line in [ln.strip(" -•\t") for ln in highlights.splitlines() if ln.strip()]:
                    flow.append(Paragraph(f"•&nbsp;&nbsp;{line}", styles["bullet"]))
            flow.append(Spacer(1, 10 * scale))

    # ── Education ──
    education = ((resume_detail.education_json or {}).get("education") if resume_detail else None) or []
    if education:
        flow.append(_section_bar("Education", accent, styles, page_width, modern=modern))
        flow.append(Spacer(1, 8 * scale))
        for item in education:
            institution = _safe(item.get("institution") or item.get("school"))
            degree_bits = [b for b in [_safe(item.get("degree")), _safe(item.get("field_of_study"))] if b]
            degree = ", ".join(degree_bits)
            start_year = _safe(str(item.get("start_year"))) if item.get("start_year") else ""
            grad_year = _safe(str(item.get("graduation_year"))) if item.get("graduation_year") else ""
            dates = " – ".join([b for b in [start_year, grad_year] if b])

            title_block = [Paragraph(institution, styles["entryTitle"])] if institution else []
            if degree:
                title_block.append(Paragraph(degree, styles["entryMeta"]))
            flow.append(_title_date_row(title_block or [Paragraph("", styles["entryTitle"])], dates, styles, page_width))

            grade = _safe(item.get("grade"))
            if grade:
                flow.append(Paragraph(f"Grade: {grade}", styles["bullet"]))
            flow.append(Spacer(1, 8 * scale))

    # ── Skills (two-column grid) ──
    skills = (resume_detail.skills_json if resume_detail else None) or {}
    skill_list = skills.get("skills") if isinstance(skills, dict) else None
    if skill_list:
        flow.append(_section_bar("Skills", accent, styles, page_width, modern=modern))
        flow.append(Spacer(1, 8 * scale))
        names = []
        for s in skill_list:
            if isinstance(s, dict):
                label = _safe(s.get("name"))
                level = SKILL_LEVEL_LABELS.get(str(s.get("level") or "").upper())
                names.append(f"{label} ({level})" if label and level else label)
            else:
                names.append(_safe(s))
        names = [n for n in names if n]
        rows = []
        for i in range(0, len(names), 2):
            left = Paragraph(f"•&nbsp;&nbsp;{names[i]}", styles["bullet"])
            right = Paragraph(f"•&nbsp;&nbsp;{names[i + 1]}", styles["bullet"]) if i + 1 < len(names) else Paragraph("", styles["bullet"])
            rows.append([left, right])
        if rows:
            grid = Table(rows, colWidths=[page_width / 2, page_width / 2])
            grid.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            flow.append(grid)
        flow.append(Spacer(1, 10 * scale))

    # ── Languages ──
    languages = ((resume_detail.languages_json or {}).get("languages") if resume_detail else None) or []
    if languages:
        flow.append(_section_bar("Languages", accent, styles, page_width, modern=modern))
        flow.append(Spacer(1, 8 * scale))
        parts = []
        for item in languages:
            name = _safe(item.get("name"))
            level = PROFICIENCY_LABELS.get(str(item.get("proficiency_level") or "").upper())
            if name:
                parts.append(f"<b>{name}</b> — {level}" if level else f"<b>{name}</b>")
        if parts:
            flow.append(Paragraph("&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts), styles["body"]))
        flow.append(Spacer(1, 10 * scale))

    # ── Certifications ──
    certifications = ((resume_detail.certifications_json or {}).get("certifications") if resume_detail else None) or []
    cert_lines = []
    for item in certifications:
        if isinstance(item, dict):
            name = _safe(item.get("name"))
            org = _safe(item.get("issuing_organization"))
            issued = _format_month(item.get("issue_date"))
            bits = [b for b in [name, f"({org})" if org else "", issued] if b]
            cert_lines.append(" ".join(bits))
        else:
            cert_lines.append(_safe(item))
    _render_bullet_section(flow, "Certificates", cert_lines, accent, styles, scale, page_width, modern=modern)

    # ── Any additional sections found in the source resume that don't map
    # to one of the structured fields above (Projects, Internships,
    # Achievements, Awards, Publications, Volunteer Experience, ...). Only
    # populated when rendering from an uploaded resume file's own content
    # (see render_resume_pdf_from_extracted / app.utils.resume_extraction);
    # each is shown with the resume's own heading text, in the order it
    # appeared in the source, using the same bulleted layout as Certificates.
    for section in extra_sections or []:
        if not isinstance(section, dict):
            continue
        title = _safe(section.get("title"))
        items = [_safe(i) for i in (section.get("items") or [])]
        _render_bullet_section(flow, title, items, accent, styles, scale, page_width, modern=modern)

    if len(flow) <= 2:
        flow.append(Paragraph(
            "This candidate hasn't added resume details yet. Complete the resume builder to generate a full document.",
            styles["body"],
        ))

    doc.build(flow)
    return buffer.getvalue()


def _page_count(pdf_bytes: bytes) -> int:
    try:
        return len(PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception:
        # If we somehow can't even read our own just-generated PDF, don't
        # block the download over it -- treat as "fits" so the candidate
        # still gets a file instead of an error.
        return 1


# Progressively smaller scale factors tried until the resume fits on one
# page. 1.0 is the normal, comfortable layout (used for typical resumes);
# smaller values shrink fonts, spacing, and margins together so a longer
# resume compresses gracefully instead of being cut off mid-section.
_ONE_PAGE_SCALES = (1.0, 0.92, 0.85, 0.78, 0.72, 0.66, 0.6)


def render_resume_pdf(profile, user, resume_detail, style: str = "ats", extra_sections: Optional[list] = None) -> bytes:
    """Renders the resume PDF in one of four templates ("ats", "modern",
    "sidebar", "bold-header"), automatically shrinking fonts, spacing, and
    margins together across a few steps until the whole resume fits on a
    single page. Falls back to the smallest scale tried (still a complete,
    readable document) if even that isn't enough for an unusually long
    resume, rather than failing the download.

    All four templates read from the same _gather_resume_content(...)
    output -- switching templates changes how a resume is drawn, never
    what data it shows. Any of them may be combined with the Modern Visual
    typography treatment (see _split_style / the module docstring)."""
    base_style, modern = _split_style(style)

    if base_style in ("sidebar", "bold-header"):
        content = _gather_resume_content(profile, user, resume_detail, extra_sections)
        last_bytes = None
        for scale in _ONE_PAGE_SCALES:
            if base_style == "sidebar":
                pdf_bytes, fits = _render_sidebar_pdf(content, scale=scale, modern=modern)
            else:
                pdf_bytes = _render_bold_header_pdf(content, scale=scale, modern=modern)
                fits = _page_count(pdf_bytes) <= 1
            last_bytes = pdf_bytes
            if fits:
                return pdf_bytes
        return last_bytes

    last_bytes = None
    for scale in _ONE_PAGE_SCALES:
        pdf_bytes = _render_resume_pdf_impl(
            profile, user, resume_detail, modern=modern, extra_sections=extra_sections, scale=scale,
        )
        last_bytes = pdf_bytes
        if _page_count(pdf_bytes) <= 1:
            return pdf_bytes
    return last_bytes


# ── Rendering straight from an uploaded resume file's extracted content ───
# (app.utils.resume_extraction pulls text out of the uploaded PDF/DOCX and
# parses it into this shape). These lightweight stand-ins carry only the
# attributes render_resume_pdf() actually reads via getattr, so the exact
# same ATS/Modern layout code above can render either a candidate's
# profile+resume-builder data (the original path) or their uploaded resume
# file's own content (this path) without any duplication.

@dataclass
class _ExtractedUser:
    first_name: str = ""
    last_name: str = ""
    country_code: str = ""
    mobile_number: str = ""
    email: str = ""
    profile_image_url: str = ""


@dataclass
class _ExtractedProfile:
    headline: str = ""
    summary: str = ""
    linkedin_url: str = ""
    current_location: str = ""


@dataclass
class _ExtractedResumeDetail:
    experience_json: dict = field(default_factory=dict)
    education_json: dict = field(default_factory=dict)
    skills_json: dict = field(default_factory=dict)
    languages_json: dict = field(default_factory=dict)
    certifications_json: dict = field(default_factory=dict)


def render_resume_pdf_from_extracted(extracted: dict, style: str = "ats", fallback_user=None) -> bytes:
    """Renders the same ATS/Modern PDF template as render_resume_pdf(), but
    sourced from `extracted` -- the structured dict produced by
    app.utils.resume_extraction.extract_resume_data() from an uploaded
    resume file's actual content, instead of the candidate's saved
    profile/resume-builder fields.

    `fallback_user` (the logged-in candidate's User row), if given, fills in
    name/email when the uploaded file's own text didn't yield them (e.g. a
    resume with no email address printed on it) -- it never overrides
    anything the file itself provided. It's also the only source for the
    Sidebar template's photo, since a resume file's own text never contains
    one.
    """
    full_name = (extracted.get("full_name") or "").strip()
    first_name, _, last_name = full_name.partition(" ")
    if not first_name and fallback_user is not None:
        first_name = _safe(getattr(fallback_user, "first_name", None))
        last_name = _safe(getattr(fallback_user, "last_name", None))

    email = extracted.get("email") or (
        _safe(getattr(fallback_user, "email", None)) if fallback_user is not None else ""
    )

    # A resume file's own text never contains the candidate's photo -- this
    # always comes from the candidate's saved profile picture, if any.
    photo_key = (
        _safe(getattr(fallback_user, "profile_image_url", None)) if fallback_user is not None else ""
    )
    user = _ExtractedUser(
        first_name=first_name,
        last_name=last_name,
        mobile_number=extracted.get("phone") or "",
        email=email,
        profile_image_url=photo_key,
    )
    profile = _ExtractedProfile(
        headline=extracted.get("headline") or "",
        summary=extracted.get("summary") or "",
        linkedin_url=extracted.get("linkedin_url") or "",
    )
    resume_detail = _ExtractedResumeDetail(
        experience_json={"experience": extracted.get("experience") or []},
        education_json={"education": extracted.get("education") or []},
        skills_json={"skills": extracted.get("skills") or []},
        languages_json={"languages": extracted.get("languages") or []},
        certifications_json={"certifications": extracted.get("certifications") or []},
    )
    return render_resume_pdf(
        profile, user, resume_detail, style=style, extra_sections=extracted.get("extra_sections") or []
    )


def draft_to_extracted(draft: dict) -> dict:
    
    personal = draft.get("personal") or {}
    by_type: dict = {}
    extra_sections: list = []

    def visible_entries(section):
        return [e for e in (section.get("entries") or []) if not e.get("hidden")]

    for section in draft.get("sections") or []:
        section_type = section.get("sectionType")
        entries = visible_entries(section)
        if section_type == "experience" and section.get("kind") == "entryModal":
            by_type["experience"] = [{
                "role": e.get("role", ""), "company": e.get("company", ""),
                "location": e.get("location", ""), "start_date": e.get("start_date", ""),
                "end_date": e.get("end_date", ""), "currently_working": bool(e.get("currently_working")),
                "key_highlights": e.get("key_highlights", ""),
            } for e in entries]
        elif section_type == "education" and section.get("kind") == "entryModal":
            by_type["education"] = [{
                "institution": e.get("institution", ""), "degree": e.get("degree", ""),
                "field_of_study": e.get("field_of_study", ""), "start_year": e.get("start_year", ""),
                "graduation_year": e.get("graduation_year", ""), "grade": e.get("grade", ""),
            } for e in entries]
        elif section_type == "skills" and section.get("kind") == "entryModal":
            by_type["skills"] = [e.get("name", "") for e in entries if e.get("name")]
        elif section_type == "languages" and section.get("kind") == "entryModal":
            by_type["languages"] = [{"name": e.get("name", ""), "proficiency_level": e.get("proficiency_level", "")} for e in entries]
        elif section_type == "certifications" and section.get("kind") == "entryModal":
            by_type["certifications"] = [{
                "name": e.get("name", ""), "issuing_organization": e.get("issuing_organization", ""),
                "issue_date": e.get("issue_date", ""),
            } for e in entries]
        elif section.get("kind") == "declaration":
            text = (section.get("text") or "").strip()
            if text:
                extra_sections.append({"title": section.get("title") or "Declaration", "items": [text]})
        else:
            # projects, plus every generic/custom section -- same
            # "<b>title</b>" heading + plain description lines convention
            # resume_extraction.py already uses for these, so they render
            # through the exact same extra_sections code path.
            items = []
            for e in entries:
                title = e.get("title", "")
                secondary = e.get("technologies_used") if section_type == "projects" else e.get("subtitle")
                description = e.get("description") or ""
                if title:
                    items.append(f"<b>{title}</b>")
                if secondary:
                    items.append(secondary)
                items.extend(ln.strip() for ln in description.splitlines() if ln.strip())
            if items:
                extra_sections.append({"title": section.get("title") or "Additional", "items": items})

    return {
        "full_name": personal.get("name") or "",
        "headline": personal.get("title") or "",
        "email": personal.get("email") or "",
        "phone": personal.get("phone") or "",
        "linkedin_url": personal.get("linkedin") or "",
        "summary": draft.get("summary") or "",
        "experience": by_type.get("experience") or [],
        "education": by_type.get("education") or [],
        "skills": by_type.get("skills") or [],
        "certifications": by_type.get("certifications") or [],
        "languages": by_type.get("languages") or [],
        "extra_sections": extra_sections,
    }