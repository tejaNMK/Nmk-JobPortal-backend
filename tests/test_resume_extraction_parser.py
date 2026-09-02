from copy import deepcopy

from app.service import resume_document_service
from app.utils.resume_extraction import parse_resume_text


MARKETING_MANAGER_TEXT = """Jane Marketing
jane@example.com
PROFESSIONAL SUMMARY
Growth marketing leader who scales SaaS demand generation.
CORE COMPETENCIES & SKILLS
Growth Marketing: Demand generation, lifecycle marketing
Performance Advertising: Paid search, paid social, display
Analytics & Attribution: GA4, Looker, incrementality testing
PROFESSIONAL EXPERIENCE
Marketing Coordinator at Vanguard Tech Innovations 2023 - Present
- Built full-funnel campaigns across paid social and search.
- Improved trial conversion through CRO tests.
KEY STRATEGIC CAMPAIGNS & PROJECTS
Global Product Relaunch Campaign
- Owned GTM planning and launch analytics.
SaaS CRO Overhaul
- Rebuilt landing pages and onboarding funnels.
CERTIFICATIONS
Google Ads Search Certification
Google Skillshop
Issued 2024
Growth Series
Reforge Executive Education
2023
"""


def test_marketing_resume_keeps_summary_skills_and_projects_separate():
    parsed = parse_resume_text(MARKETING_MANAGER_TEXT)

    assert parsed["summary"] == "Growth marketing leader who scales SaaS demand generation."
    assert "CORE COMPETENCIES" not in parsed["summary"]
    assert parsed["skills"] == [
        "Growth Marketing: Demand generation",
        "Growth Marketing: lifecycle marketing",
        "Performance Advertising: Paid search",
        "Performance Advertising: paid social",
        "Performance Advertising: display",
        "Analytics & Attribution: GA4",
        "Analytics & Attribution: Looker",
        "Analytics & Attribution: incrementality testing",
    ]
    assert [section["title"] for section in parsed["extra_sections"]] == ["Projects"]


def test_marketing_resume_does_not_promote_skill_or_cert_labels_to_sections():
    parsed = parse_resume_text(MARKETING_MANAGER_TEXT)

    section_titles = {section["title"] for section in parsed["extra_sections"]}
    assert "Performance Advertising" not in section_titles
    assert "Analytics & Attribution" not in section_titles
    assert "Google Skillshop" not in section_titles
    assert "Reforge Executive Education" not in section_titles


def test_marketing_resume_preserves_bullets_and_project_records():
    parsed = parse_resume_text(MARKETING_MANAGER_TEXT)

    experience = parsed["experience"]
    assert len(experience) == 1
    assert experience[0]["company"] == "Vanguard Tech Innovations"
    assert experience[0]["start_date"] == "2023"
    assert experience[0]["key_highlights"].splitlines() == [
        "Built full-funnel campaigns across paid social and search.",
        "Improved trial conversion through CRO tests.",
    ]

    projects = parsed["extra_sections"][0]["items"]
    assert projects == [
        "<b>Global Product Relaunch Campaign</b>",
        "Owned GTM planning and launch analytics.",
        "<b>SaaS CRO Overhaul</b>",
        "Rebuilt landing pages and onboarding funnels.",
    ]


def test_marketing_resume_groups_certification_name_issuer_and_date():
    parsed = parse_resume_text(MARKETING_MANAGER_TEXT)

    assert parsed["certifications"] == [
        {
            "name": "Google Ads Search Certification",
            "issuing_organization": "Google Skillshop",
            "issue_date": "2024",
        },
        {
            "name": "Growth Series",
            "issuing_organization": "Reforge Executive Education",
            "issue_date": "2023",
        },
    ]


def test_multiline_header_experience_with_numeric_month_dates_and_location():
    """Company/Role/Date each on their own line (rather than one combined
    "Role at Company 2023 - Present" header), with numeric "MM/YYYY" dates
    -- both previously broke role/company/date parsing (see
    resume_extraction._blocks_from_section and NUMERIC_MONTH_YEAR_RE)."""
    text = """Bhaswanth Kalluru
Data Analyst
PROFESSIONAL EXPERIENCE
Ashok Leyland
Territory Parts Manager
07/2024 – 07/2025 | Vijaywada
Conducted territory-wise and customer-wise sales analysis to identify
revenue trends and customer patterns.
Monitored KPIs including monthly revenue, inventory turnover,
order frequency, and sales growth.
EDUCATION
Data Science
Innomatics Research Labs
2025
"""
    parsed = parse_resume_text(text)
    experience = parsed["experience"]
    assert len(experience) == 1
    assert experience[0]["company"] == "Ashok Leyland"
    assert experience[0]["role"] == "Territory Parts Manager"
    assert experience[0]["location"] == "Vijaywada"
    assert experience[0]["start_date"] == "07/2024"
    assert experience[0]["end_date"] == "07/2025"
    assert experience[0]["key_highlights"].splitlines() == [
        "Conducted territory-wise and customer-wise sales analysis to identify revenue trends and customer patterns.",
        "Monitored KPIs including monthly revenue, inventory turnover, order frequency, and sales growth.",
    ]


def test_education_grade_line_attaches_to_its_own_entry_not_the_next_one():
    """A "Grade : X" line always trails after an entry's own date line, but
    isn't itself a date -- naively treating it as "the next non-dated line"
    used to close the current entry early and open a bogus new one starting
    with the grade line, corrupting the *next* real entry's institution."""
    text = """Jordan Lee
EDUCATION
Data Science
Innomatics Research Labs
09/2025 – Present | Bengaluru
Mechanical Engineering
Sastra University, Thanjavur
09/2020 – 05/2024 | Thanjavur
Grade : 8.58
Intermediate
Narayana junior college, Nellore
2018 – 2020 | Nellore
Grade : 9.7
"""
    parsed = parse_resume_text(text)
    education = parsed["education"]
    assert len(education) == 3
    assert education[0] == {
        "institution": "Innomatics Research Labs", "degree": "Data Science",
        "field_of_study": "", "start_year": "2025", "graduation_year": "", "grade": "",
    }
    assert education[1] == {
        "institution": "Sastra University, Thanjavur", "degree": "Mechanical Engineering",
        "field_of_study": "", "start_year": "2020", "graduation_year": "2024", "grade": "8.58",
    }
    assert education[2] == {
        "institution": "Narayana junior college, Nellore", "degree": "Intermediate",
        "field_of_study": "", "start_year": "2018", "graduation_year": "2020", "grade": "9.7",
    }


def test_bullet_only_noise_line_is_dropped_not_glued_into_the_sentence():
    """Some source PDFs print a bullet's glyph as its own text run on
    whichever line pdfplumber's row-clustering happens to place it --
    including the *second* line of a two-line-wrapped bullet, landing a
    lone "•" between two lines that are actually one sentence."""
    text = """Sam Rivera
PROFESSIONAL EXPERIENCE
Acme Corp
Analyst
2020 - 2022
Conducted territory-wise and customer-wise sales analysis to identify
•
revenue trends and customer patterns.
"""
    parsed = parse_resume_text(text)
    highlights = parsed["experience"][0]["key_highlights"]
    assert highlights == (
        "Conducted territory-wise and customer-wise sales analysis to identify revenue trends and customer patterns."
    )
    assert "•" not in highlights


def test_skills_wrapped_comma_list_is_not_fragmented_at_line_wraps():
    """A category's value list wrapping across several PDF lines (no
    bullet/colon of its own on the continuation lines) must be merged back
    into one list before splitting on commas -- otherwise a comma that
    merely happens to fall at a line wrap creates two bogus half-skills
    ("Data" / "Manipulation" instead of "Data Manipulation")."""
    text = """Sam Rivera
SKILLS
Python
Anaconda, Jupyter/Colab, Python Programming, Pandas, NumPy, Data
Manipulation, Exception Handling, APIs, Trend Analysis, Reporting,
Problem Solving.
SQL
SQL Queries, Joins, Subqueries.
"""
    parsed = parse_resume_text(text)
    assert parsed["skills"] == [
        "Python",
        "Anaconda", "Jupyter/Colab", "Python Programming", "Pandas", "NumPy",
        "Data Manipulation", "Exception Handling", "APIs", "Trend Analysis",
        "Reporting", "Problem Solving.",
        "SQL",
        "SQL Queries", "Joins", "Subqueries.",
    ]
    assert "Data" not in parsed["skills"]
    assert "Manipulation" not in parsed["skills"]


def test_row_text_does_not_insert_a_space_between_zero_gap_words():
    """Some PDF generators split a single visual token (most often an
    email address, right at the "@") into two separate pdfplumber "words"
    with *zero* gap between them. Joining every word with a plain space
    then corrupts "name@gmail.com" into "name @gmail.com", which no longer
    matches EMAIL_RE and silently drops the contact's email."""
    from app.utils.resume_extraction import _row_text

    row = [
        {"text": "bhaswanthkalluru", "x0": 89.4, "x1": 152.6, "top": 84.5},
        {"text": "@gmail.com", "x0": 152.6, "x1": 195.5, "top": 84.5},
        {"text": "9063716350", "x0": 218.2, "x1": 266.1, "top": 84.5},
    ]
    assert _row_text(row) == "bhaswanthkalluru@gmail.com 9063716350"


def test_template_rendering_uses_same_extracted_structure_for_each_style(monkeypatch):
    parsed = parse_resume_text(MARKETING_MANAGER_TEXT)
    original = deepcopy(parsed)
    captured = []

    def fake_render(profile, user, resume_detail, style="ats", extra_sections=None):
        captured.append({
            "style": style,
            "summary": profile.summary,
            "experience": deepcopy(resume_detail.experience_json),
            "education": deepcopy(resume_detail.education_json),
            "skills": deepcopy(resume_detail.skills_json),
            "certifications": deepcopy(resume_detail.certifications_json),
            "extra_sections": deepcopy(extra_sections),
        })
        return b"%PDF-test"

    monkeypatch.setattr(resume_document_service, "render_resume_pdf", fake_render)

    assert resume_document_service.render_resume_pdf_from_extracted(parsed, style="ats") == b"%PDF-test"
    assert resume_document_service.render_resume_pdf_from_extracted(parsed, style="sidebar") == b"%PDF-test"

    assert parsed == original
    assert captured[0] | {"style": "sidebar"} == captured[1]


def test_role_company_split_prefers_pipe_over_an_internal_dash():
    """"Senior Marketing Manager - Acquisition | Elevation Media Group" has
    a dash *inside* the job title itself, ahead of the real (pipe)
    separator. Trying " - " before "|" split the title in half instead of
    at the real role/company boundary."""
    text = """Jane Marketing
PROFESSIONAL EXPERIENCE
Senior Marketing Manager - Acquisition | Elevation Media Group 2020 - 2023
Grew organic traffic through technical SEO.
"""
    parsed = parse_resume_text(text)
    exp = parsed["experience"][0]
    assert exp["role"] == "Senior Marketing Manager - Acquisition"
    assert exp["company"] == "Elevation Media Group"


def test_education_degree_and_date_combined_on_one_line_institution_next():
    """A different (and equally common) education layout than the
    Degree/Institution/Date/Grade one already covered above: degree name
    and its date range share one line, with the institution on the very
    next line and no separate date line at all. The block-boundary
    heuristic tuned for the 4-line layout used to treat the institution
    line as the start of a bogus second entry."""
    text = """Jane Marketing
EDUCATION
Bachelor of Arts in Communication & Digital Media 2011 – 2015
University of Texas at Austin, TX
"""
    parsed = parse_resume_text(text)
    education = parsed["education"]
    assert len(education) == 1
    assert education[0]["degree"] == "Bachelor of Arts in Communication & Digital Media"
    assert education[0]["institution"] == "University of Texas at Austin, TX"
    assert education[0]["start_year"] == "2011"
    assert education[0]["graduation_year"] == "2015"


def test_certifications_with_inline_issued_date_dont_swallow_the_next_certs_name():
    """Each cert given as "Name Issued <date>" then "Org" on the next line
    (no bullets, no pipe/dash). The second cert's own "Name Issued <date>"
    line used to be misread as just a date update for the *first* cert,
    so the first cert's name/org never got flushed and the second cert's
    real name became a stray date string."""
    text = """Jane Marketing
CERTIFICATIONS
Google Analytics 4 (GA4) Certification Issued Jan 2024
Google Skillshop
HubSpot Inbound Marketing & Inbound Sales Certified Issued Oct 2023
HubSpot Academy
"""
    parsed = parse_resume_text(text)
    assert parsed["certifications"] == [
        {"name": "Google Analytics 4 (GA4) Certification", "issuing_organization": "Google Skillshop", "issue_date": "Jan 2024"},
        {"name": "HubSpot Inbound Marketing & Inbound Sales Certified", "issuing_organization": "HubSpot Academy", "issue_date": "Oct 2023"},
    ]


def test_profile_summary_and_tools_and_skills_headings_are_recognized():
    """"Profile Summary" and "Tools & Skills" are common heading phrasings
    SECTION_PATTERNS didn't cover (only "Professional Summary"/"Profile"
    and "Skills"/"Core Competencies & Skills" were). An unrecognized
    heading doesn't just get misfiled -- it lets the section around it
    balloon into a much bigger, more heterogeneous block of PDF rows that
    the two-column layout detector is far more likely to misfire on."""
    from app.utils.resume_extraction import _is_header_line

    assert _is_header_line("PROFILE SUMMARY") == "summary"
    assert _is_header_line("TOOLS & SKILLS") == "skills"
    assert _is_header_line("Skills & Tools") == "skills"


def test_experience_header_with_no_delimiter_still_extracts_trailing_location():
    """"Datadog Senior Sales Engineer New York, NY" has no delimiter at all
    between company and role -- genuinely ambiguous to split without a
    company-name dictionary -- but the trailing "City, ST" shape is
    distinctive enough to still pull out as a location rather than being
    left glued onto the end of the role text."""
    text = """Sofia Bergmann
WORK EXPERIENCE
Datadog Senior Sales Engineer New York, NY • Apr 2022 - Present
Ran technical discovery on enterprise deals.
"""
    parsed = parse_resume_text(text)
    exp = parsed["experience"][0]
    assert exp["location"] == "New York, NY"
    assert "New York" not in exp["role"]
    assert exp["start_date"] == "Apr 2022"
    assert exp["currently_working"] is True


def test_sidebar_pdf_spills_onto_a_second_page_instead_of_dropping_content():
    """A resume with far more content than one page can hold (81 skills)
    used to silently truncate in the Sidebar template: Frame.addFromList()
    has no notion of "start a new page and keep going", so whatever didn't
    fit in the single fixed-size canvas frame was just dropped -- with no
    error, and no sign of it beyond the missing content in the download."""
    from app.service import resume_document_service as rds

    # Build the content dict in the same shape _gather_resume_content
    # produces, directly, since we only need to exercise
    # _render_sidebar_pdf's own pagination here -- not the extraction/
    # gathering step already covered by the tests above.
    many_skills = [f"Skill number {i}" for i in range(120)]
    content = {
        "full_name": "Jane Marketing", "headline": "Marketing Lead", "photo_key": None,
        "contact_items": [("email", "jane@example.com")],
        "summary": "", "languages": [],
        "experience": [], "education": [],
        "skills": many_skills, "certifications": [], "extra_sections": [],
    }
    pdf_bytes, fits_one_page = rds._render_sidebar_pdf(content, scale=1.0)
    assert fits_one_page is False
    assert rds._page_count(pdf_bytes) >= 2

    # Every skill actually made it into the PDF somewhere (not just
    # whatever fit on page 1) -- the real regression was silent data loss,
    # not just a missing page break.
    import pypdf
    from io import BytesIO
    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    full_text = "".join(page.extract_text() or "" for page in reader.pages)
    for skill in many_skills:
        assert skill in full_text

