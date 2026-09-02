import re
from decimal import Decimal
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from app.utils.utc import utc_now
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from dateutil import tz

from app.constants.notification_constants import NotificationFrequency, NotificationPreference
from app.utils.sanitize import reject_html, sanitize_rich_html, rich_text_plain_length


# ─────────────────────────────────────────────
# URL validation helpers (LinkedIn, GitHub, and other applicable links)
# ─────────────────────────────────────────────

_URL_PATTERN = re.compile(
    r"^https?://"
    r"(([a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,})"
    r"(/[^\s]*)?$"
)

# Domain hints so we can validate that a "LinkedIn URL" is actually a
# linkedin.com link and not some other random site, etc. Each entry is a
# tuple of acceptable host substrings for that field.
DOMAIN_HINTS = {
    "linkedin_url": ("linkedin.com",),
    "github_url": ("github.com",),
    "dribbble_url": ("dribbble.com",),
    "twitter_url": ("twitter.com", "x.com"),
}


def _validate_iana_timezone_name(value: str) -> str:
    if value.upper() != "UTC" and "/" not in value:
        raise ValueError("Timezone must be a valid IANA timezone name.")

    try:
        ZoneInfo(value)
        return value
    except ZoneInfoNotFoundError:
        if tz.gettz(value) is not None:
            return value
        raise ValueError("Timezone must be a valid IANA timezone name.")


def _validate_profile_url(value: str, field_label: str, allowed_domains: Optional[tuple] = None) -> Optional[str]:
    """Shared URL validation for LinkedIn, GitHub, website, portfolio, and
    other profile link fields. Returns the cleaned URL (or None if blank),
    raising ValueError on anything that isn't a well-formed http(s) URL, or
    that doesn't match the field's expected domain when one is specified.
    """
    value = (value or "").strip()
    if not value:
        return None

    if not _URL_PATTERN.match(value):
        raise ValueError(f"{field_label} must be a valid URL starting with http:// or https://")

    if allowed_domains:
        host = value.split("://", 1)[1].split("/", 1)[0].lower()
        host = host.split(":")[0]  # strip any port
        if host.startswith("www."):
            host = host[4:]

        def _host_matches(host: str, domain: str) -> bool:
            return host == domain or host.endswith(f".{domain}")

        if not any(_host_matches(host, domain) for domain in allowed_domains):
            pretty = " or ".join(allowed_domains)
            raise ValueError(f"{field_label} must be a valid link from {pretty}")

    return value


# ─────────────────────────────────────────────
# SECTION 1 ─ Personal Info (Basic Details)
# ─────────────────────────────────────────────

class CandidatePersonalInfoUpdateSchema(BaseModel):
    """
    PATCH /candidate/profile/personal-info

    Partial-update schema — send only the fields you want to change.
    All fields are optional; at least one must be provided.

    Updates: first_name, last_name, middle_name, phone_number (on Users table)
             professional_title, about_you, country_id, location_id,
             primary_location_id, preferred_location_id, primary_location,
             preferred_locations, website, portfolio_url (on CandidateProfile)
    """
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    # silently drops it as unrecognised, so it must be declared here.
    phone_country_code: Optional[str] = None
    # Distinguishes countries sharing the same calling code, such as US/CA.
    phone_country_iso2: Optional[str] = None

    # CandidateProfile fields - named to match the frontend form labels
    professional_title: Optional[str] = None   # e.g. "Lead Product Designer"
    about_you: Optional[str] = None            # "About you" bio textarea

    # "Country" dropdown - drives which locations show up in Primary/Preferred
    # Location. master_countries.country_id
    country_id: Optional[str] = None
    location_id: Optional[str] = None

    # Primary/Preferred Location dropdowns, populated from
    # GET /master-data/countries/{country_id}/locations for the chosen country.
    primary_location_id: Optional[str] = None
    preferred_location_id: Optional[str] = None

    # Deprecated free-text fallbacks, kept for backward compatibility with
    # older clients that haven't migrated to the country/location dropdowns.
    primary_location: Optional[str] = None     # "Primary location"
    preferred_locations: Optional[str] = None  # "Preferred locations"

    website: Optional[str] = None              # "Website"
    portfolio_url: Optional[str] = None        # "Portfolio / Case study"

    @model_validator(mode="after")
    def validate_fields(self):
        # Require at least one field to be explicitly provided
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update")

        def _name(val: str, label: str) -> str:
            val = val.strip()
            if not re.fullmatch(r"[A-Za-z]+", val):
                raise ValueError(f"{label} must contain alphabets only")
            if not (2 <= len(val) <= 30):
                raise ValueError(f"{label} must be between 2 and 30 characters")
            return val

        if self.first_name is not None:
            self.first_name = _name(self.first_name, "First name")

        if self.last_name is not None:
            self.last_name = _name(self.last_name, "Last name")

        if self.middle_name is not None:
            m = self.middle_name.strip()
            if m:
                if not re.fullmatch(r"[A-Za-z]+", m):
                    raise ValueError("Middle name must contain alphabets only")
                if not (2 <= len(m) <= 30):
                    raise ValueError("Middle name must be between 2 and 30 characters")
                self.middle_name = m
            else:
                self.middle_name = None

        if self.phone_number is not None:
            digits = self.phone_number.strip()
            
            # phonenumbers-backed rules as registration.
            if not re.fullmatch(r"\d+", digits):
                raise ValueError("Phone number must contain digits only")
            self.phone_number = digits

        if self.phone_country_iso2 is not None:
            iso2 = self.phone_country_iso2.strip().upper()
            if iso2 and not re.fullmatch(r"[A-Z]{2}", iso2):
                raise ValueError("Invalid phone country")
            self.phone_country_iso2 = iso2 or None

        if self.professional_title and len(self.professional_title) > 255:
            raise ValueError("Professional title must be at most 255 characters")

        if self.about_you is not None:
            about_you = self.about_you.strip()
            word_count = len(about_you.split())
            if word_count > 200:
                raise ValueError("About you must be at most 200 words")
            self.about_you = about_you

        for field in ("website", "portfolio_url"):
            val = getattr(self, field, None)
            if val is not None:
                setattr(self, field, _validate_profile_url(val, field))

        if self.country_id is not None and not self.country_id.strip():
            raise ValueError("country_id cannot be blank")
        if self.location_id is not None and not self.location_id.strip():
            raise ValueError("location_id cannot be blank")
        if self.primary_location_id is not None and not self.primary_location_id.strip():
            raise ValueError("primary_location_id cannot be blank")
        if self.preferred_location_id is not None and not self.preferred_location_id.strip():
            raise ValueError("preferred_location_id cannot be blank")

        if self.preferred_locations is not None:
            items = [p.strip() for p in self.preferred_locations.split(",") if p.strip()]
            if len(items) > 3:
                raise ValueError("You can select up to 3 preferred locations")
            self.preferred_locations = ", ".join(items)

        return self


class CandidatePersonalInfoResponse(BaseModel):
    """Response shape for personal info."""
    user_id: UUID
    first_name: str
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    professional_title: Optional[str] = None
    about_you: Optional[str] = None

    country_id: Optional[str] = None
    country: Optional[str] = None

    primary_location_id: Optional[str] = None
    location_id: Optional[str] = None
    primary_location: Optional[str] = None

    preferred_location_id: Optional[str] = None
    preferred_locations: Optional[str] = None

    website: Optional[str] = None
    portfolio_url: Optional[str] = None
    profile_completion_pct: int

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# SECTION 2 ─ Social Links
# ─────────────────────────────────────────────

class CandidateSocialLinksUpdateSchema(BaseModel):
    """
    PATCH /candidate/profile/social-links

    Mirrors the "Social & Contact Links" card on the frontend Edit Profile
    page exactly: LinkedIn, Dribbble, GitHub / Code, Twitter / X.
    """
    linkedin_url: Optional[str] = None
    dribbble_url: Optional[str] = None
    github_url: Optional[str] = None
    twitter_url: Optional[str] = None

    @model_validator(mode="after")
    def validate_urls(self):
        url_fields = {
            "linkedin_url": self.linkedin_url,
            "dribbble_url": self.dribbble_url,
            "github_url": self.github_url,
            "twitter_url": self.twitter_url,
        }
        for field, value in url_fields.items():
            if value is not None:
                cleaned = _validate_profile_url(value, field, DOMAIN_HINTS.get(field))
                setattr(self, field, cleaned)
        return self


# ─────────────────────────────────────────────
# SECTION 3 ─ Skills (Add Skill modal)
# ─────────────────────────────────────────────

SkillProficiency = Literal["BEGINNER", "INTERMEDIATE", "ADVANCED", "EXPERT"]


class SkillEntrySchema(BaseModel):
    """
    Mirrors the "Add Skill" modal: Skill name *, Proficiency, Years of experience.
    """
    name: str
    level: Optional[SkillProficiency] = None       # "Proficiency" dropdown
    years: Optional[Decimal] = None                # "Years of experience"

    @field_validator("level", mode="before")
    @classmethod
    def validate_level(cls, v):
        if v is None or v == "":
            return None
        allowed = {"BEGINNER", "INTERMEDIATE", "ADVANCED", "EXPERT"}
        value = str(v).upper()
        if value not in allowed:
            raise ValueError(f"level must be one of {allowed}")
        return value

    @field_validator("name")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    @model_validator(mode="after")
    def validate_skill(self):
        if not self.name or not self.name.strip():
            raise ValueError("Skill name is required")
        self.name = self.name.strip()
        if len(self.name) > SKILL_NAME_MAX_LENGTH:
            raise ValueError(_MAX_LENGTH_MESSAGE)
        if self.years is not None:
            if self.years < 0:
                raise ValueError("Years of experience cannot be negative")
            if self.years > 99:
                raise ValueError("Years of experience cannot exceed 99")
        return self


class SkillEntryResponse(SkillEntrySchema):
    skill_id: str


class CandidateSkillCreateSchema(SkillEntrySchema):
    """POST /candidate/profile/skills - add one skill (Add Skill modal: Save)."""

    @model_validator(mode="after")
    def require_level(self):
        # Proficiency Level must be selected when adding a new skill, matching
        # the Build Resume "Add Skill" modal's client-side validation. This is
        # enforced only on create, not on SkillEntrySchema/Update, so existing
        # skills saved without a level (from before this fix) still read back
        # fine and a PATCH that doesn't touch level isn't forced to supply one.
        if self.level is None:
            raise ValueError("Proficiency Level is required")
        return self


class CandidateSkillUpdateSchema(BaseModel):
    """PATCH /candidate/profile/skills/{skill_id} - edit one skill."""
    name: Optional[str] = None
    level: Optional[SkillProficiency] = None
    years: Optional[Decimal] = None

    @field_validator("level", mode="before")
    @classmethod
    def validate_level(cls, v):
        if v is None or v == "":
            return None
        allowed = {"BEGINNER", "INTERMEDIATE", "ADVANCED", "EXPERT"}
        value = str(v).upper()
        if value not in allowed:
            raise ValueError(f"level must be one of {allowed}")
        return value

    @field_validator("name")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    @model_validator(mode="after")
    def validate_skill(self):
        if self.name is not None:
            if not self.name.strip():
                raise ValueError("Skill name cannot be empty")
            self.name = self.name.strip()
        if self.years is not None:
            if self.years < 0:
                raise ValueError("Years of experience cannot be negative")
            if self.years > 99:
                raise ValueError("Years of experience cannot exceed 99")
        return self


# ─────────────────────────────────────────────
# SECTION 3B ─ Languages (Add Language modal)
# ─────────────────────────────────────────────

LanguageProficiency = Literal["NATIVE", "EXPERT", "PROFESSIONAL", "INTERMEDIATE", "BASIC"]


class LanguageEntrySchema(BaseModel):
    """
    Mirrors the "Add Language" modal: Language name *, Proficiency level *.
    """
    name: str
    proficiency_level: LanguageProficiency

    @field_validator("proficiency_level", mode="before")
    @classmethod
    def validate_proficiency_level(cls, v):
        allowed = {"NATIVE", "EXPERT", "PROFESSIONAL", "INTERMEDIATE", "BASIC"}
        value = str(v).upper()
        if value not in allowed:
            raise ValueError(f"proficiency_level must be one of {allowed}")
        return value

    @field_validator("name")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    @model_validator(mode="after")
    def validate_language(self):
        if not self.name or not self.name.strip():
            raise ValueError("Language name is required")
        self.name = self.name.strip()
        return self


class LanguageEntryResponse(LanguageEntrySchema):
    language_id: str


class CandidateLanguageCreateSchema(LanguageEntrySchema):
    """POST /candidate/profile/languages - add one language (Add Language modal: Save)."""
    pass


class CandidateLanguageUpdateSchema(BaseModel):
    """PATCH /candidate/profile/languages/{language_id} - edit one language."""
    name: Optional[str] = None
    proficiency_level: Optional[LanguageProficiency] = None

    @field_validator("proficiency_level", mode="before")
    @classmethod
    def validate_proficiency_level(cls, v):
        if v is None or v == "":
            return None
        allowed = {"NATIVE", "EXPERT", "PROFESSIONAL", "INTERMEDIATE", "BASIC"}
        value = str(v).upper()
        if value not in allowed:
            raise ValueError(f"proficiency_level must be one of {allowed}")
        return value

    @field_validator("name")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    @model_validator(mode="after")
    def validate_language(self):
        if self.name is not None:
            if not self.name.strip():
                raise ValueError("Language name cannot be empty")
            self.name = self.name.strip()
        return self


# ─────────────────────────────────────────────
# SECTION 4 ─ Education (Add Education modal)
# ─────────────────────────────────────────────

# validation and get persisted. Messages mirror the frontend's
# validateYearField() in EntryModal.jsx so users see the same wording
# regardless of which validation layer catches the problem.
MIN_EDUCATION_YEAR = 1900
MAX_EDUCATION_YEAR = date.today().year


def _validate_education_year(value: Optional[int]) -> Optional[int]:
    if value is None:
        return value
    if value < 0:
        raise ValueError("Year cannot be negative.")
    if value < 100:
        # Two-digit (or shorter) shorthand like 20 or 7 — not a real year.
        raise ValueError("Enter a valid four-digit year.")
    if value < MIN_EDUCATION_YEAR:
        raise ValueError("Enter a valid four-digit year.")
    if value > MAX_EDUCATION_YEAR:
        raise ValueError("Year cannot be later than the current year.")
    return value
# a limit here, a multi-thousand-character paste into any of these renders
# as an oversized card that breaks the Education section's layout.
EDUCATION_FIELD_MAX_LENGTHS = {
    "institution": 100,
    "degree": 50,
    "field_of_study": 50,
}


def _enforce_education_max_length(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value
    max_length = EDUCATION_FIELD_MAX_LENGTHS.get(field_name)
    if max_length is not None and len(value) > max_length:
        raise ValueError(_MAX_LENGTH_MESSAGE)
    return value


class EducationEntrySchema(BaseModel):
    """
    Mirrors the "Add Education" modal: Institution *, Degree, Field of Study,
    Start Year, Graduation Year, Grade / GPA. Only Institution is required.
    """
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_year: Optional[int] = None
    graduation_year: Optional[int] = None    # "Graduation Year" field in the modal
    grade: Optional[str] = None              # "Grade / GPA"

    @field_validator("start_year")
    @classmethod
    def _check_start_year(cls, v):
        return _validate_education_year(v)

    @field_validator("graduation_year")
    @classmethod
    def _check_graduation_year(cls, v):
        return _validate_education_year(v)

    @field_validator("institution", "degree", "field_of_study")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    @field_validator("institution", "degree", "field_of_study")
    @classmethod
    def enforce_max_length(cls, v, info):
        return _enforce_education_max_length(v, info.field_name)

    @model_validator(mode="after")
    def validate_education(self):
        if not self.institution or not self.institution.strip():
            raise ValueError("Institution is required")
        self.institution = self.institution.strip()
        if self.start_year is not None and self.graduation_year is not None:
            if self.graduation_year < self.start_year:
                raise ValueError("End year cannot be earlier than start year.")
        return self


class EducationEntryResponse(EducationEntrySchema):
    education_id: str


class CandidateEducationCreateSchema(EducationEntrySchema):
    """POST /candidate/profile/education - add one education entry (Add Education modal: Save)."""
    pass


class CandidateEducationUpdateSchema(BaseModel):
    """PATCH /candidate/profile/education/{education_id} - edit one education entry."""
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_year: Optional[int] = None
    graduation_year: Optional[int] = None
    grade: Optional[str] = None

    @field_validator("start_year")
    @classmethod
    def _check_start_year(cls, v):
        return _validate_education_year(v)

    @field_validator("graduation_year")
    @classmethod
    def _check_graduation_year(cls, v):
        return _validate_education_year(v)

    @field_validator("institution", "degree", "field_of_study")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    @field_validator("institution", "degree", "field_of_study")
    @classmethod
    def enforce_max_length(cls, v, info):
        return _enforce_education_max_length(v, info.field_name)

    @model_validator(mode="after")
    def validate_education(self):
        if self.institution is not None:
            if not self.institution.strip():
                raise ValueError("Institution cannot be empty")
            self.institution = self.institution.strip()
        if self.start_year is not None and self.graduation_year is not None:
            if self.graduation_year < self.start_year:
                raise ValueError("End year cannot be earlier than start year.")
        return self


# ─────────────────────────────────────────────
# SECTION 5 ─ Experience (Add Experience modal)
# ─────────────────────────────────────────────

ExperienceEmploymentType = Literal["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP", "FREELANCE"]

_EMPLOYMENT_TYPE_ALIASES = {
    "FULL_TIME": "FULL_TIME", "FULL-TIME": "FULL_TIME", "FULLTIME": "FULL_TIME",
    "PART_TIME": "PART_TIME", "PART-TIME": "PART_TIME", "PARTTIME": "PART_TIME",
    "CONTRACT": "CONTRACT",
    "INTERNSHIP": "INTERNSHIP",
    "FREELANCE": "FREELANCE",
}


def _normalize_employment_type(v):
    if v is None or v == "":
        return None
    value = str(v).strip().upper().replace(" ", "_")
    normalized = _EMPLOYMENT_TYPE_ALIASES.get(value)
    if normalized is None:
        raise ValueError(f"employment_type must be one of {sorted(set(_EMPLOYMENT_TYPE_ALIASES.values()))}")
    return normalized


# to the same length whether it's on an employer profile or a candidate's
# work history. Without a limit here, a multi-thousand-character paste into
# any of these fields renders as an oversized card that breaks the Work
# Experience summary page's layout.
EXPERIENCE_FIELD_MAX_LENGTHS = {
    "role": 150,            # Job Title
    "company": 150,          # Company Name
    "location": 200,         # Location
}

# Mirrors the "Add Experience" modal's Job Description field (EntryModal.jsx),
# validated by word count instead of character count -- same approach as
# CandidatePersonalInfoUpdateSchema.about_you below.
KEY_HIGHLIGHTS_MAX_WORDS = 200

# Mirrors the "Add Skill" modal's Skill Name field (EntryModal.jsx). Without
# a limit here, a multi-thousand-character paste into Skill Name renders as
# an oversized chip that breaks the Skills section's layout.
SKILL_NAME_MAX_LENGTH = 50

_MAX_LENGTH_MESSAGE = "Maximum character limit exceeded."


def _enforce_experience_max_length(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value
    max_length = EXPERIENCE_FIELD_MAX_LENGTHS.get(field_name)
    if max_length is not None and len(value) > max_length:
        raise ValueError(_MAX_LENGTH_MESSAGE)
    return value


class ExperienceEntrySchema(BaseModel):
    """
    Mirrors the "Add Experience" modal: Job Title *, Company Name *, Employment Type,
    Location, Start Date, End Date, Currently working here, Job Description.
    """
    company: str
    role: str
    employment_type: Optional[ExperienceEmploymentType] = None   # "Employment Type" dropdown
    location: Optional[str] = None                               # "Location" e.g. "Lahore, Pakistan"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    currently_working: bool = False
    key_highlights: Optional[str] = None   # "Job Description" textarea

    @field_validator("employment_type", mode="before")
    @classmethod
    def validate_employment_type(cls, v):
        return _normalize_employment_type(v)

    @field_validator("company", "role", "location")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    # key_highlights ("Job Description") is edited with the RichTextArea
    # WYSIWYG toolbar and legitimately carries real HTML (bold/italic/
    # underline/lists/links/alignment) -- reject_html's blanket "no tags"
    # rule would reject the editor's own output, so this field gets the
    # same allowlist sanitizer the frontend uses instead of an outright ban.
    @field_validator("key_highlights")
    @classmethod
    def sanitize_key_highlights(cls, v):
        return sanitize_rich_html(v)

    @field_validator("company", "role", "location")
    @classmethod
    def enforce_max_length(cls, v, info):
        return _enforce_experience_max_length(v, info.field_name)

    @model_validator(mode="after")
    def validate_experience(self):
        if not self.company or not self.company.strip():
            raise ValueError("Company is required")
        if not self.role or not self.role.strip():
            raise ValueError("Role / Title is required")
        self.company = self.company.strip()
        self.role = self.role.strip()
        if self.location is not None:
            self.location = self.location.strip() or None
        if self.key_highlights is not None:
            if rich_text_plain_length(self.key_highlights) > KEY_HIGHLIGHTS_MAX_WORDS:
                raise ValueError(f"Job Description must be at most {KEY_HIGHLIGHTS_MAX_WORDS} words")

        # <input type="month"> has no built-in floor client-side (and its
        # Firefox text-box fallback has none either), so an implausible year
        # like "0001" is shape-valid and needs to be rejected here too, same
        # floor as Education/Certifications since no employment predates it.
        if self.start_date is not None and self.start_date.year < MIN_EDUCATION_YEAR:
            raise ValueError("Please select a valid Start Date")
        if self.end_date is not None and self.end_date.year < MIN_EDUCATION_YEAR:
            raise ValueError("Please select a valid End Date")

        if self.currently_working:
            self.end_date = None
        elif self.end_date is not None and self.start_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("End Date cannot be before Start Date")
        return self


class ExperienceEntryResponse(ExperienceEntrySchema):
    experience_id: str


class CandidateExperienceCreateSchema(ExperienceEntrySchema):
    """POST /candidate/profile/experience - add one experience entry (Add Experience modal: Save)."""
    pass


class CandidateExperienceUpdateSchema(BaseModel):
    """PATCH /candidate/profile/experience/{experience_id} - edit one experience entry."""
    company: Optional[str] = None
    role: Optional[str] = None
    employment_type: Optional[ExperienceEmploymentType] = None
    location: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    currently_working: Optional[bool] = None
    key_highlights: Optional[str] = None

    @field_validator("employment_type", mode="before")
    @classmethod
    def validate_employment_type(cls, v):
        return _normalize_employment_type(v)

    @field_validator("company", "role", "location")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    # See ExperienceEntrySchema.sanitize_key_highlights above for why this
    # field gets the WYSIWYG allowlist instead of reject_html.
    @field_validator("key_highlights")
    @classmethod
    def sanitize_key_highlights(cls, v):
        return sanitize_rich_html(v)

    @field_validator("company", "role", "location")
    @classmethod
    def enforce_max_length(cls, v, info):
        return _enforce_experience_max_length(v, info.field_name)

    @model_validator(mode="after")
    def validate_experience(self):
        if self.company is not None:
            if not self.company.strip():
                raise ValueError("Company cannot be empty")
            self.company = self.company.strip()
        if self.role is not None:
            if not self.role.strip():
                raise ValueError("Role / Title cannot be empty")
            self.role = self.role.strip()
        if self.location is not None:
            self.location = self.location.strip() or None
        if self.key_highlights is not None:
            if rich_text_plain_length(self.key_highlights) > KEY_HIGHLIGHTS_MAX_WORDS:
                raise ValueError(f"Job Description must be at most {KEY_HIGHLIGHTS_MAX_WORDS} words")
        # Same floor as the create path (ExperienceEntrySchema) -- see that
        # class's model_validator for why this is needed even though
        # <input type="month"> is shape-valid for a year like "0001".
        if self.start_date is not None and self.start_date.year < MIN_EDUCATION_YEAR:
            raise ValueError("Please select a valid Start Date")
        if self.end_date is not None and self.end_date.year < MIN_EDUCATION_YEAR:
            raise ValueError("Please select a valid End Date")
        if self.currently_working:
            self.end_date = None
        elif self.end_date is not None and self.start_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("End Date cannot be before Start Date")
        # `employment_type` is only present in `model_fields_set` when the

        if "employment_type" in self.model_fields_set and self.employment_type is None:
            raise ValueError("Please select an Employment Type.")
        return self


# ─────────────────────────────────────────────
# SECTION 6 ─ Certifications
# ─────────────────────────────────────────────

_CERT_DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CERT_DATE_FORMAT_MSG = "Enter a valid date in YYYY-MM format."

_MIN_CERT_YEAR = 1900

_MAX_CERT_YEAR = utc_now().year + 50


def _validate_cert_date_format(v):
    if v is None:
        return None
    value = str(v).strip()
    if not value:
        return None
    if not _CERT_DATE_RE.match(value):
        raise ValueError(_CERT_DATE_FORMAT_MSG)
    if int(value[:4]) < _MIN_CERT_YEAR:
        raise ValueError(_CERT_DATE_FORMAT_MSG)
    if int(value[:4]) > _MAX_CERT_YEAR:
        raise ValueError(_CERT_DATE_FORMAT_MSG)
    return value


def _validate_cert_dates_after(issue_date, expiry_date):
    
    if issue_date is not None:
        current_month = utc_now().strftime("%Y-%m")
        if issue_date > current_month:
            raise ValueError("Issue Date cannot be in the future.")
    if issue_date is not None and expiry_date is not None:
        if expiry_date < issue_date:
            raise ValueError("Expiry Date cannot be earlier than Issue Date.")

CERTIFICATION_FIELD_MAX_LENGTHS = {
    "name": 200,
    "issuing_organization": 200,
}


def _enforce_certification_max_length(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value
    max_length = CERTIFICATION_FIELD_MAX_LENGTHS.get(field_name)
    if max_length is not None and len(value) > max_length:
        raise ValueError(_MAX_LENGTH_MESSAGE)
    return value


class CertificationEntrySchema(BaseModel):
    """Single certification entry."""
    name: str
    issuing_organization: str
    issue_date: Optional[str] = None        # "YYYY-MM"
    expiry_date: Optional[str] = None       # "YYYY-MM" or None if no expiry
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None

    @field_validator("issue_date", "expiry_date", mode="before")
    @classmethod
    def validate_date_format(cls, v):
        return _validate_cert_date_format(v)

    @field_validator("credential_url", mode="before")
    @classmethod
    def validate_url(cls, v):
        if v is None:
            return v
        v = str(v).strip()
        if v and not re.match(r"^https?://", v):
            raise ValueError("credential_url must start with http:// or https://")
        return v or None

    @field_validator("name", "issuing_organization", "credential_id", "credential_url")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    @field_validator("name", "issuing_organization")
    @classmethod
    def enforce_max_length(cls, v, info):
        return _enforce_certification_max_length(v, info.field_name)

    @model_validator(mode="after")
    def validate_dates(self):
        _validate_cert_dates_after(self.issue_date, self.expiry_date)
        return self


class CandidateCertificationsUpdateSchema(BaseModel):
    """
    PUT /candidate/profile/certifications
    Replaces the entire certifications_json list.
    """
    certifications: List[CertificationEntrySchema]


class CandidateCertificationUpdateSchema(BaseModel):
    
    name: Optional[str] = None
    issuing_organization: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update")
        return self

    @field_validator("issue_date", "expiry_date", mode="before")
    @classmethod
    def validate_date_format(cls, v):
        return _validate_cert_date_format(v)

    @field_validator("credential_url", mode="before")
    @classmethod
    def validate_url(cls, v):
        if v is None:
            return v
        v = str(v).strip()
        if v and not re.match(r"^https?://", v):
            raise ValueError("credential_url must start with http:// or https://")
        return v or None

    @field_validator("name", "issuing_organization", "credential_id", "credential_url")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    @field_validator("name", "issuing_organization")
    @classmethod
    def enforce_max_length(cls, v, info):
        return _enforce_certification_max_length(v, info.field_name)

    @model_validator(mode="after")
    def validate_dates(self):
        # Only cross-check dates that were actually sent in this partial
        # update — see _validate_cert_dates_after's docstring.
        issue_date = self.issue_date if "issue_date" in self.model_fields_set else None
        expiry_date = self.expiry_date if "expiry_date" in self.model_fields_set else None
        _validate_cert_dates_after(issue_date, expiry_date)
        return self


# ─────────────────────────────────────────────
# SECTION 6b ─ Projects (Add Project modal)
# ─────────────────────────────────────────────

PROJECT_FIELD_MAX_LENGTHS = {
    "title": 200,
    "technologies_used": 200,
}

# Project Description is validated by word count instead of character count
# (same approach as ExperienceEntrySchema.key_highlights / CandidatePersonalInfoUpdateSchema.about_you).
PROJECT_DESCRIPTION_MAX_WORDS = 200


def _enforce_project_max_length(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value
    max_length = PROJECT_FIELD_MAX_LENGTHS.get(field_name)
    if max_length is not None and len(value) > max_length:
        raise ValueError(_MAX_LENGTH_MESSAGE)
    return value


class ProjectEntrySchema(BaseModel):
    """
    Mirrors the "Add Project" modal: Title *, Technologies Used, Project URL,
    Description.
    """
    title: str
    technologies_used: Optional[str] = None   # comma-separated tags, e.g. "React, Node.js, PostgreSQL"
    project_url: Optional[str] = None         # "Project URL"
    description: Optional[str] = None

    @field_validator("title", "technologies_used", "project_url")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    # description is edited with the RichTextArea WYSIWYG toolbar and
    # legitimately carries real HTML -- same reasoning as
    # ExperienceEntrySchema.sanitize_key_highlights above.
    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v):
        return sanitize_rich_html(v)

    @field_validator("title", "technologies_used")
    @classmethod
    def enforce_max_length(cls, v, info):
        return _enforce_project_max_length(v, info.field_name)

    @model_validator(mode="after")
    def validate_project(self):
        if not self.title or not self.title.strip():
            raise ValueError("Project title is required")
        self.title = self.title.strip()
        if self.description is not None:
            if rich_text_plain_length(self.description) > PROJECT_DESCRIPTION_MAX_WORDS:
                raise ValueError(f"Project Description must be at most {PROJECT_DESCRIPTION_MAX_WORDS} words")
        if self.project_url is not None:
            u = self.project_url.strip()
            if u and not re.match(r"^https?://", u):
                raise ValueError("Project URL must start with http:// or https://")
            self.project_url = u or None
        return self


class ProjectEntryResponse(ProjectEntrySchema):
    project_id: str


class CandidateProjectCreateSchema(ProjectEntrySchema):
    """POST /candidate/profile/projects - add one project (Add Project modal: Save)."""
    pass


class CandidateProjectUpdateSchema(BaseModel):
    """PATCH /candidate/profile/projects/{project_id} - edit one project."""
    title: Optional[str] = None
    technologies_used: Optional[str] = None
    project_url: Optional[str] = None
    description: Optional[str] = None

    @field_validator("title", "technologies_used", "project_url")
    @classmethod
    def reject_html_markup(cls, v):
        return reject_html(v)

    # See CandidateProjectCreateSchema/ProjectEntrySchema.sanitize_description
    # above for why this field gets the WYSIWYG allowlist instead of
    # reject_html.
    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v):
        return sanitize_rich_html(v)

    @field_validator("title", "technologies_used")
    @classmethod
    def enforce_max_length(cls, v, info):
        return _enforce_project_max_length(v, info.field_name)

    @model_validator(mode="after")
    def validate_project(self):
        if self.title is not None:
            if not self.title.strip():
                raise ValueError("Project title cannot be empty")
            self.title = self.title.strip()
        if self.description is not None:
            if rich_text_plain_length(self.description) > PROJECT_DESCRIPTION_MAX_WORDS:
                raise ValueError(f"Project Description must be at most {PROJECT_DESCRIPTION_MAX_WORDS} words")
        if self.project_url is not None:
            u = self.project_url.strip()
            if u and not re.match(r"^https?://", u):
                raise ValueError("Project URL must start with http:// or https://")
            self.project_url = u or None
        return self


# ─────────────────────────────────────────────
# SECTION 7 ─ Profile Visibility / Preferences
# ─────────────────────────────────────────────

ProfileVisibility = Literal["PUBLIC", "PRIVATE", "CONNECTIONS"]
ExperienceLevel = Literal["FRESHER", "JUNIOR", "MID", "SENIOR", "LEAD"]
EmploymentPreference = Literal["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP", "FREELANCE"]
WorkPreference = Literal["ONSITE", "REMOTE", "HYBRID"]
JobAlertExperienceLevel = Literal[
    "FRESHER",
    "JUNIOR",
    "MID_LEVEL",
    "SENIOR",
]

JOB_ALERT_EXPERIENCE_LEVEL_MAP = {
    "FRESHER": "FRESHER",
    "0": "FRESHER",
    "0 YEARS": "FRESHER",
    "JUNIOR": "JUNIOR",
    "1-3": "JUNIOR",
    "1 - 3": "JUNIOR",
    "1-3 YEARS": "JUNIOR",
    "1 - 3 YEARS": "JUNIOR",
    "MID": "MID_LEVEL",
    "MID_LEVEL": "MID_LEVEL",
    "MID LEVEL": "MID_LEVEL",
    "3-5": "MID_LEVEL",
    "3 - 5": "MID_LEVEL",
    "3-5 YEARS": "MID_LEVEL",
    "3 - 5 YEARS": "MID_LEVEL",
    "SENIOR": "SENIOR",
    "5+": "SENIOR",
    "5+ YEARS": "SENIOR",
}

JobAlertEmploymentType = Literal[
    "FULL_TIME",
    "PART_TIME",
    "CONTRACT",
    "INTERNSHIP",
]

JobAlertNotificationPreference = Literal[
    "EMAIL",
    "IN_APP",
    "BOTH",
]

JobAlertFrequency = Literal[
    "INSTANT",
    "DAILY",
    "WEEKLY",
]


class CandidateVisibilityUpdateSchema(BaseModel):
    """
    PATCH /candidate/profile/visibility
    """
    profile_visibility: Optional[ProfileVisibility] = None
    searchable_flag: Optional[bool] = None
    open_to_work: Optional[bool] = None
    search_engine_indexing: Optional[bool] = None

    @field_validator("profile_visibility", mode="before")
    @classmethod
    def validate_visibility(cls, v):
        if v is None:
            return v
        allowed = {"PUBLIC", "PRIVATE", "CONNECTIONS"}
        if str(v).upper() not in allowed:
            raise ValueError(f"profile_visibility must be one of {allowed}")
        return str(v).upper()


# ─────────────────────────────────────────────
# SECTION 8 ─ Full Profile Read Response
# ─────────────────────────────────────────────

class CandidateProfileFullResponse(BaseModel):
    """
    GET /candidate/profile
    Returns all sections merged, matching the frontend Edit Profile page.
    """
    # User fields
    user_id: UUID
    first_name: str
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    # NOTE: was previously passed into this model's constructor (see
    # CandidateProfileService.get_profile) but never declar
    # save. See CandidatePersonalInfoUpdateSchema.phone_country_code for
    # the write side, which was already correct.
    phone_country_code: Optional[str] = None
    phone_country_iso2: Optional[str] = None
    profile_image_url: Optional[str] = None
    cover_image_url: Optional[str] = None

    # CandidateProfile fields - Personal Information card
    candidate_id: str
    professional_title: Optional[str] = None
    about_you: Optional[str] = None

    country_id: Optional[str] = None
    country: Optional[str] = None

    primary_location_id: Optional[str] = None
    location_id: Optional[str] = None
    primary_location: Optional[str] = None

    preferred_location_id: Optional[str] = None
    preferred_locations: Optional[str] = None

    website: Optional[str] = None
    portfolio_url: Optional[str] = None

    # Professional Snapshot card
    experience_level: Optional[str] = None
    current_company: Optional[str] = None

    notice_period_id: Optional[str] = None
    notice_period: Optional[str] = None

    desired_employment: Optional[str] = None

    salary_expectation_id: Optional[str] = None
    salary_expectation: Optional[str] = None

    current_ctc: Optional[Decimal] = None
    expected_ctc: Optional[Decimal] = None

    work_preference: Optional[str] = None

    target_role_ids: List[str] = []
    target_roles: List[str] = []

    # Social & Contact Links card
    linkedin_url: Optional[str] = None
    dribbble_url: Optional[str] = None
    github_url: Optional[str] = None
    twitter_url: Optional[str] = None

    profile_visibility: str
    searchable_flag: bool
    open_to_work: bool
    search_engine_indexing: bool = False
    profile_completion_pct: int
    active_resume_id: Optional[str] = None

    # From CandidateResumeDetail (latest) - list sections with Add/Edit modals
    education: List[EducationEntryResponse] = []
    experience: List[ExperienceEntryResponse] = []
    skills: List[SkillEntryResponse] = []
    certifications: Optional[List[Dict[str, Any]]] = None
    projects: List[ProjectEntryResponse] = []
    languages: List[LanguageEntryResponse] = []

    model_config = ConfigDict(from_attributes=True)

class CandidateProfessionalSnapshotUpdateSchema(BaseModel):
    
    experience_level: Optional[ExperienceLevel] = None
    current_company: Optional[str] = None

    notice_period_id: Optional[str] = None
    desired_employment: Optional[EmploymentPreference] = None

    salary_expectation_id: Optional[str] = None
    current_ctc: Optional[Decimal] = None
    expected_ctc: Optional[Decimal] = None

    work_preference: Optional[WorkPreference] = None

    target_role_ids: Optional[List[str]] = None
    target_role_names: Optional[List[str]] = None

    # Deprecated free-text fallbacks, kept for backward compatibility.
    notice_period: Optional[str] = None
    salary_expectation: Optional[str] = None
    target_roles: Optional[str] = None

    @model_validator(mode="after")
    def validate_snapshot(self):
        for field in ("current_ctc", "expected_ctc"):
            val = getattr(self, field)
            if val is not None:
                if val < 0:
                    raise ValueError(f"{field} cannot be negative")
                if val > Decimal("999999999.99"):
                    raise ValueError(f"{field} is too large")

        if self.target_role_ids is not None:
            cleaned = [rid.strip() for rid in self.target_role_ids if rid and rid.strip()]
            if len(cleaned) > 10:
                raise ValueError("You can select up to 10 target roles")
            self.target_role_ids = cleaned or None

        if self.target_role_names is not None:
            cleaned = [name.strip() for name in self.target_role_names if name and name.strip()]
            if len(cleaned) > 10:
                raise ValueError("You can select up to 10 target roles")
            self.target_role_names = cleaned or None

        return self


class CandidateResumeResponse(BaseModel):
    resume_id: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    blob_ref: Optional[str] = None

    # field existed -- the Download CV page omits the size in that case
    # rather than showing "0 Bytes".
    file_size: Optional[int] = None
    version_no: int = 1
    is_active: bool = False

    # ── Resume Library fields ──
    version_name: Optional[str] = None
    template: Optional[str] = None
    notes: Optional[str] = None
    usage_note: Optional[str] = None
    is_archived: bool = False
    download_count: int = 0
    share_token: Optional[str] = None
    share_enabled: bool = False
    share_requires_email: bool = False
    share_expires_at: Optional[datetime] = None
    share_view_count: int = 0
    share_url: Optional[str] = None

    uploaded_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _build_share_url(self):
        if self.share_enabled and self.share_token and not self.share_url:
            # Import kept local to avoid a hard circular import at module load time.
            from app.config import FRONTEND_BASE_URL
            object.__setattr__(self, "share_url", f"{FRONTEND_BASE_URL}/cv/{self.share_token}")
        return self


class CandidateResumeListResponse(BaseModel):
    total: int
    active_resume_id: Optional[str] = None
    default_is_explicit: bool = True
    items: List[CandidateResumeResponse]


class CandidateResumeDownloadResponse(BaseModel):
    resume_id: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    blob_ref: Optional[str] = None
    file_size: Optional[int] = None
    is_active: bool = False

    model_config = ConfigDict(from_attributes=True)


class ExtractedExperienceItem(BaseModel):
    role: str = ""
    company: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    currently_working: bool = False
    key_highlights: str = ""


class ExtractedEducationItem(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_year: str = ""
    graduation_year: str = ""
    grade: str = ""


class ExtractedCertificationItem(BaseModel):
    name: str = ""
    issuing_organization: str = ""
    issue_date: str = ""


class ExtractedLanguageItem(BaseModel):
    name: str = ""
    proficiency_level: Optional[str] = None


class ExtractedExtraSection(BaseModel):
    title: str = ""
    items: List[str] = []


class ExtractedResumeDataSchema(BaseModel):
    
    full_name: str = ""
    headline: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    summary: str = ""
    experience: List[ExtractedExperienceItem] = []
    education: List[ExtractedEducationItem] = []
    skills: List[str] = []
    certifications: List[ExtractedCertificationItem] = []
    languages: List[ExtractedLanguageItem] = []
    extra_sections: List[ExtractedExtraSection] = []


class ResumeDraftPersonalSchema(BaseModel):
    name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    website: str = ""
    linkedin: str = ""


class ResumeDraftSectionSchema(BaseModel):
    
    sectionType: str
    kind: str
    title: str = ""
    entries: Optional[List[Dict[str, Any]]] = None
    text: Optional[str] = None


class ResumeStudioDraftSchema(BaseModel):
    
    personal: ResumeDraftPersonalSchema = ResumeDraftPersonalSchema()
    summary: str = ""
    sections: List[ResumeDraftSectionSchema] = []


class CandidateResumeUpdateSchema(BaseModel):
    
    version_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    template: Optional[str] = Field(default=None, min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _at_least_one_field(self):
        if self.version_name is None and self.template is None and self.notes is None:
            raise ValueError("At least one field (version_name, template, notes) must be provided")
        return self


class ResumeShareLinkCreateSchema(BaseModel):
    """POST /candidate/profile/resumes/{resume_id}/share"""
    requires_email: bool = False
    expires_in_days: Optional[int] = Field(default=30, ge=1, le=365)


class ResumeShareLinkResponse(BaseModel):
    resume_id: str
    share_token: Optional[str] = None
    share_enabled: bool = False
    share_requires_email: bool = False
    share_expires_at: Optional[datetime] = None
    share_view_count: int = 0
    share_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SharedResumeInfoResponse(BaseModel):
    
    candidate_name: str
    file_name: Optional[str] = None
    template: Optional[str] = None
    requires_email: bool = False
    download_url: Optional[str] = None


class SharedResumeAccessRequestSchema(BaseModel):
    """POST /candidate/public/resume/{share_token}/access -- used only when
    requires_email is true on the info response above."""
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        value = (value or "").strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Please enter a valid email address")
        return value


class SharedResumeAccessResponse(BaseModel):
    download_url: str
    file_name: Optional[str] = None


class CandidateListingFilterParams(BaseModel):
    search: Optional[str] = None
    location: Optional[str] = None
    skill: Optional[str] = None
    experience_level: Optional[ExperienceLevel] = None
    work_preference: Optional[WorkPreference] = None
    page: int = 1
    page_size: int = 20

    @model_validator(mode="after")
    def validate_filters(self):
        if self.page < 1:
            raise ValueError("page must be greater than or equal to 1")
        if not (1 <= self.page_size <= 100):
            raise ValueError("page_size must be between 1 and 100")
        for field_name in ("search", "location", "skill"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(self, field_name, value.strip() or None)
        return self


class CandidateListingItemResponse(BaseModel):
    candidate_id: str
    full_name: str
    headline: Optional[str] = None
    current_company: Optional[str] = None
    current_location: Optional[str] = None
    total_experience: Optional[Decimal] = None
    experience_level: Optional[str] = None
    skills_summary: Optional[str] = None
    work_preference: Optional[str] = None
    open_to_work: bool = False
    profile_completion_pct: int = 0
    active_resume_id: Optional[str] = None
    profile_image_url: Optional[str] = None


class CandidateListingResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CandidateListingItemResponse]


class CandidatePublicDetailResponse(CandidateListingItemResponse):
    profile_photo: Optional[str] = None
    headline: Optional[str] = None
    professional_summary: Optional[str] = None
    about_me: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    professional_title: Optional[str] = None
    about_you: Optional[str] = None
    location: Optional[str] = None
    cover_image_url: Optional[str] = None
    profile_visibility: Optional[str] = None
    searchable_flag: Optional[bool] = None
    search_engine_indexing: Optional[bool] = None
    summary: Optional[str] = None
    current_designation: Optional[str] = None
    total_experience_years: Optional[float] = None
    current_employment: Optional[Dict[str, Any]] = None
    notice_period: Optional[str] = None
    employment_type: Optional[str] = None
    work_preference: Optional[str] = None
    preferred_locations: Optional[List[str]] = None
    current_salary: Optional[float] = None
    expected_salary: Optional[float] = None
    open_to_work: bool = False
    remote_preference: Optional[str] = None
    relocation_preference: Optional[str] = None
    preferred_location: Optional[str] = None
    desired_employment: Optional[str] = None
    salary_expectation: Optional[str] = None
    target_roles: Optional[str] = None
    education: Optional[List[Dict[str, Any]]] = None
    experience: Optional[List[Dict[str, Any]]] = None
    skills: Optional[Dict[str, Any]] = None
    certifications: Optional[List[Dict[str, Any]]] = None
    projects: Optional[List[Dict[str, Any]]] = None
    languages: Optional[List[Dict[str, Any]]] = None
    resume: Optional[Dict[str, Any]] = None
    resumes: Optional[List[Dict[str, Any]]] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    website: Optional[str] = None
    leetcode_url: Optional[str] = None
    hackerrank_url: Optional[str] = None
    social_links: Optional[Dict[str, Any]] = None
    profile_completion: Optional[Dict[str, Any]] = None
    saved_candidate: bool = False
    applied_job: Optional[Dict[str, Any]] = None
    current_application_status: Optional[str] = None
    interview_status: Optional[str] = None
    interview_date: Optional[date] = None
    notes_count: int = 0


class CandidateSavedJobCreateSchema(BaseModel):
    job_id: str


class CandidateSavedJobResponse(BaseModel):
    saved_job_id: str
    job_id: str
    saved_flag: bool
    created_at: datetime
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    work_mode: Optional[str] = None
    skills: List[str] = []


class CandidateSavedJobListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CandidateSavedJobResponse]

#=============================================
# JOB ALERTS
#=============================================

class JobAlertResponse(BaseModel):
    alert_id: str

    title: Optional[str] = None

    job_category: Optional[str] = None

    job_title: Optional[str] = None

    preferred_location: Optional[str] = None

    experience_level: Optional[str] = None

    employment_type: Optional[str] = None

    notification_preference: Optional[str] = None

    frequency: Optional[str] = None

    timezone: Optional[str] = None

    is_active: bool

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    
class JobAlertUpsertSchema(BaseModel):

    title: str = Field(..., min_length=1)

    job_category: Optional[str] = None

    job_title: str

    preferred_location: Optional[str] = None

    experience_level: JobAlertExperienceLevel

    employment_type: JobAlertEmploymentType

    notification_preference: JobAlertNotificationPreference

    frequency: JobAlertFrequency = "INSTANT"

    timezone: Optional[str] = None

    is_active: bool = True

    @model_validator(mode="before")
    @classmethod
    def validate_required_fields(cls, values):
        if isinstance(values, dict) and (
            values.get("title") is None
            or not str(values.get("title")).strip()
        ):
            raise ValueError("Job Alert Title is required.")

        if isinstance(values, dict) and (
            values.get("job_title") is None
            or not str(values.get("job_title")).strip()
        ):
            raise ValueError("Job Title is required.")

        return values

    @field_validator("title")
    @classmethod
    def validate_title(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("Job Alert Title is required.")

        if len(value) < 3:
            raise ValueError(
                "Job Alert Title must be at least 3 characters."
            )

        if len(value) > 100:
            raise ValueError(
                "Job Alert Title cannot exceed 100 characters."
            )

        if not re.fullmatch(r"[A-Za-z0-9 ]+", value):
            raise ValueError(
                "Job Alert Title can contain only alphabets, numbers and spaces."
            )

        return value

    @field_validator("job_category")
    @classmethod
    def validate_job_category(cls, value):
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        if len(value) > 100:
            raise ValueError(
                "Job Category cannot exceed 100 characters."
            )

        return value

    @field_validator("job_title")
    @classmethod
    def validate_job_title(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("Job Title is required.")

        if len(value) > 100:
            raise ValueError(
                "Job Title cannot exceed 100 characters."
            )

        return value

    @field_validator("preferred_location")
    @classmethod
    def validate_preferred_location(cls, value):
        if value is None:
            return value

        value = value.strip()

        if len(value) > 100:
            raise ValueError(
                "Preferred Location cannot exceed 100 characters."
            )

        return value or None

    @field_validator("experience_level", mode="before")
    @classmethod
    def validate_experience_level(cls, value):
        normalized = str(value).strip().upper()
        return JOB_ALERT_EXPERIENCE_LEVEL_MAP.get(normalized, normalized)

    @field_validator("employment_type", mode="before")
    @classmethod
    def validate_employment_type(cls, value):
        return str(value).upper()

    @field_validator("notification_preference", mode="before")
    @classmethod
    def validate_notification_preference(cls, value):
        return NotificationPreference.normalize(value)

    @field_validator("frequency", mode="before")
    @classmethod
    def validate_frequency(cls, value):
        if value is None:
            return "INSTANT"

        value = NotificationFrequency.normalize(value)

        allowed = {
            "INSTANT",
            "DAILY",
            "WEEKLY",
        }

        if value not in allowed:
            raise ValueError(
                f"Frequency must be one of {allowed}"
            )

        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        if value is None:
            return value

        value = value.strip()
        if not value:
            return None

        return _validate_iana_timezone_name(value)
class JobAlertUpdateSchema(BaseModel):

    title: Optional[str] = None

    job_category: Optional[str] = None

    job_title: Optional[str] = None

    preferred_location: Optional[str] = None

    experience_level: Optional[JobAlertExperienceLevel] = None

    employment_type: Optional[JobAlertEmploymentType] = None

    notification_preference: Optional[JobAlertNotificationPreference] = None

    frequency: Optional[JobAlertFrequency] = None

    timezone: Optional[str] = None

    is_active: Optional[bool] = None

    @field_validator("experience_level", mode="before")
    @classmethod
    def validate_experience_level(cls, value):
        if value is None:
            return value
        normalized = str(value).strip().upper()
        return JOB_ALERT_EXPERIENCE_LEVEL_MAP.get(normalized, normalized)

    @model_validator(mode="after")
    def validate_fields(self):

        if not self.model_fields_set:
            raise ValueError(
                "At least one field must be provided for update."
            )

        if self.title is not None:
            self.title = self.title.strip()

            if not self.title:
                raise ValueError("Job Alert Title is required.")

            if self.title is not None and len(self.title) < 3:

                raise ValueError(
                    "Job Alert Title must be at least 3 characters."
                )

            if self.title is not None and len(self.title) > 100:
                raise ValueError(
                    "Job Alert Title cannot exceed 100 characters."
                )

            if self.title is not None and not re.fullmatch(r"[A-Za-z0-9 ]+", self.title):
                raise ValueError(
                    "Job Alert Title can contain only alphabets, numbers and spaces."
                )

        if self.job_category is not None:
            self.job_category = self.job_category.strip()

            if not self.job_category:
                self.job_category = None

            if self.job_category is not None and len(self.job_category) > 100:
                raise ValueError(
                    "Job Category cannot exceed 100 characters."
                )

        if self.job_title is not None:
            self.job_title = self.job_title.strip()

            if len(self.job_title) > 100:
                raise ValueError(
                    "Job Title cannot exceed 100 characters."
                )

            if not self.job_title:
                raise ValueError("Job Title is required.")

        if self.preferred_location is not None:
            self.preferred_location = self.preferred_location.strip()

            if not self.preferred_location:
                raise ValueError(
                    "Preferred Location is required."
                )

            if len(self.preferred_location) > 100:
                raise ValueError(
                    "Preferred Location cannot exceed 100 characters."
                )

        if self.experience_level is not None:
            normalized = str(self.experience_level).strip().upper()
            self.experience_level = JOB_ALERT_EXPERIENCE_LEVEL_MAP.get(
                normalized,
                normalized,
            )

        if self.employment_type is not None:
            self.employment_type = str(
                self.employment_type
            ).upper()

        if self.notification_preference is not None:
            self.notification_preference = NotificationPreference.normalize(
                self.notification_preference
            )

        if self.frequency is not None:
            self.frequency = str(self.frequency).upper()

            allowed = {
                "INSTANT",
                "DAILY",
                "WEEKLY",
            }

            if self.frequency not in allowed:
                raise ValueError(
                    f"Frequency must be one of {allowed}"
                )

        if self.timezone is not None:
            self.timezone = self.timezone.strip()

            if not self.timezone:
                self.timezone = None
            else:
                self.timezone = _validate_iana_timezone_name(self.timezone)

        return self
# ============================================================
# Section 9 - Candidate List Response
# ============================================================

class CandidateListItem(BaseModel):
    candidate_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    job_applied: str | None = None
    status: str


class CandidateListResponse(BaseModel):
    total_records: int
    page: int
    page_size: int
    candidates: list[CandidateListItem]

class SavedSearchCreateSchema(BaseModel):
    search_name: Optional[str] = None
    keywords: Optional[str] = None
    skills: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None
    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    experience_min: Optional[Decimal] = None
    experience_max: Optional[Decimal] = None


class SavedSearchResponse(BaseModel):
    saved_search_id: str
    search_name: Optional[str] = None
    keywords: Optional[str] = None
    skills: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None
    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    experience_min: Optional[Decimal] = None
    experience_max: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
