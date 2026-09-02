from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from app.service.candidate_job_recommendation_engine import compute_skill_match


SCORING_VERSION = "ai_candidate_matching_v1"

SCORE_WEIGHTS = {
    "required_skills": 35,
    "experience": 25,
    "title_domain": 15,
    "education": 10,
    "location": 5,
    "preferred_skills": 5,
    "semantic": 5,
}

MATCH_LEVELS = (
    (90, "Excellent Match", "Highly Recommended"),
    (80, "Strong Match", "Recommended"),
    (70, "Good Match", "Recommended"),
    (60, "Moderate Match", "Review Manually"),
    (0, "Low Match", "Not Recommended"),
)

SKILL_SYNONYMS = {
    "py": "python",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "js": "javascript",
    "ts": "typescript",
    "nodejs": "node.js",
    "node": "node.js",
    "reactjs": "react",
    "rest": "rest api",
    "restful": "rest api",
    "amazonwebservices": "aws",
}

_WORD_RE = re.compile(r"[a-z0-9+#.]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "of", "on", "or", "the", "to", "with", "years", "year", "work",
    "job", "role", "required", "preferred", "candidate",
}


def normalize_skill(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9+#.]", "", str(value or "").strip().lower())
    return SKILL_SYNONYMS.get(normalized, normalized)


def normalize_skills(values: Iterable[str] | None) -> set[str]:
    return {normalize_skill(value) for value in values or [] if normalize_skill(value)}


def tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {word for word in _WORD_RE.findall(str(text).lower()) if word not in _STOPWORDS}


def match_level(score: float) -> str:
    for threshold, label, _ in MATCH_LEVELS:
        if score >= threshold:
            return label
    return "Low Match"


def recommendation(score: float, missing_required_skills: list[str]) -> str:
    if missing_required_skills and score < 90:
        return "Review Manually" if score >= 60 else "Not Recommended"
    for threshold, _, label in MATCH_LEVELS:
        if score >= threshold:
            return label
    return "Not Recommended"


@dataclass
class JobMatchInput:
    job_id: str
    title: str = ""
    description: str = ""
    required_skills: set[str] = field(default_factory=set)
    preferred_skills: set[str] = field(default_factory=set)
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    education: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None
    industry: Optional[str] = None
    requirements: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)

    @property
    def semantic_text(self) -> str:
        return " ".join(
            part
            for part in [
                self.title,
                self.description,
                self.education,
                self.location,
                self.work_mode,
                self.employment_type,
                self.industry,
                " ".join(self.required_skills),
                " ".join(self.preferred_skills),
                " ".join(self.requirements),
                " ".join(self.responsibilities),
            ]
            if part
        )


@dataclass
class CandidateMatchInput:
    candidate_id: str
    candidate_name: str
    skills: set[str] = field(default_factory=set)
    total_experience_years: Optional[float] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    current_company: Optional[str] = None
    target_roles: Optional[str] = None
    current_location: Optional[str] = None
    preferred_location: Optional[str] = None
    work_preference: Optional[str] = None
    desired_employment: Optional[str] = None
    education: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    job_titles: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    application_id: Optional[str] = None
    source_type: str = "AI Recommended Candidate"

    @property
    def semantic_text(self) -> str:
        return " ".join(
            part
            for part in [
                self.headline,
                self.summary,
                self.current_company,
                self.target_roles,
                self.current_location,
                self.preferred_location,
                self.work_preference,
                self.desired_employment,
                " ".join(self.skills),
                " ".join(self.education),
                " ".join(self.certifications),
                " ".join(self.job_titles),
                " ".join(self.projects),
            ]
            if part
        )


@dataclass
class CandidateScore:
    candidate_id: str
    overall_score: float
    skills_score: float
    experience_score: float
    title_domain_score: float
    education_score: float
    location_score: float
    preferred_skills_score: float
    semantic_score: float
    matched_skills: list[str]
    missing_required_skills: list[str]
    matched_preferred_skills: list[str]
    strengths: list[str]
    gaps: list[str]
    ai_summary: str
    recommendation: str
    hard_requirements: dict
    preferred_requirements: dict
    semantic_signals: dict


def _percent_to_points(percent: float, weight: int) -> float:
    return round(max(0.0, min(100.0, percent)) * weight / 100, 2)


def _experience_percent(candidate_years: Optional[float], minimum: Optional[int], maximum: Optional[int]) -> float:
    if minimum is None and maximum is None:
        return 70.0 if candidate_years is not None else 50.0
    if candidate_years is None:
        return 40.0
    lo = minimum if minimum is not None else 0
    hi = maximum
    if candidate_years < lo:
        return max(0.0, 100.0 * (candidate_years / lo)) if lo else 100.0
    if hi is not None and candidate_years > hi:
        overage = candidate_years - hi
        return max(70.0, 100.0 - min(30.0, overage * 5))
    return 100.0


def _location_percent(candidate: CandidateMatchInput, job: JobMatchInput) -> float:
    mode = (job.work_mode or "").lower()
    if "remote" in mode:
        return 100.0
    job_location = (job.location or "").strip().lower()
    if not job_location:
        return 60.0
    locations = [
        (candidate.current_location or "").strip().lower(),
        (candidate.preferred_location or "").strip().lower(),
    ]
    if any(loc and (loc in job_location or job_location in loc) for loc in locations):
        return 100.0
    return 30.0 if any(locations) else 50.0


def _education_percent(candidate: CandidateMatchInput, job: JobMatchInput) -> float:
    if not job.education:
        return 70.0
    job_tokens = tokenize(job.education)
    candidate_tokens = tokenize(" ".join(candidate.education + candidate.certifications))
    if not candidate_tokens:
        return 40.0
    if not job_tokens:
        return 70.0
    return round(100.0 * len(job_tokens & candidate_tokens) / len(job_tokens), 2)


def _title_domain_percent(candidate: CandidateMatchInput, job: JobMatchInput) -> float:
    job_tokens = tokenize(" ".join([job.title, job.industry or ""]))
    candidate_tokens = tokenize(" ".join([candidate.headline or "", candidate.target_roles or "", " ".join(candidate.job_titles)]))
    if not job_tokens or not candidate_tokens:
        return 40.0
    important_overlap = job_tokens & candidate_tokens
    return round(min(100.0, 100.0 * len(important_overlap) / max(1, min(len(job_tokens), 10))), 2)


def _semantic_percent(candidate: CandidateMatchInput, job: JobMatchInput) -> tuple[float, list[str]]:
    job_tokens = tokenize(job.semantic_text)
    candidate_tokens = tokenize(candidate.semantic_text)
    if not job_tokens or not candidate_tokens:
        return 0.0, []
    overlap = job_tokens & candidate_tokens
    denominator = math.sqrt(len(job_tokens) * len(candidate_tokens))
    percent = round(100.0 * len(overlap) / denominator, 2) if denominator else 0.0
    return min(100.0, percent), sorted(overlap)[:20]


def score_candidate_for_job(candidate: CandidateMatchInput, job: JobMatchInput) -> CandidateScore:
    required_detail = compute_skill_match(
        candidate.skills,
        job.required_skills,
        set(),
    )
    preferred_detail = compute_skill_match(
        candidate.skills,
        job.preferred_skills,
        set(),
    )
    required_skill_percent = required_detail.match_percentage
    preferred_skill_percent = preferred_detail.match_percentage
    experience_percent = _experience_percent(candidate.total_experience_years, job.experience_min, job.experience_max)
    title_domain_percent = _title_domain_percent(candidate, job)
    education_percent = _education_percent(candidate, job)
    location_percent = _location_percent(candidate, job)
    semantic_percent, semantic_overlap = _semantic_percent(candidate, job)

    skills_score = _percent_to_points(required_skill_percent, SCORE_WEIGHTS["required_skills"])
    experience_score = _percent_to_points(experience_percent, SCORE_WEIGHTS["experience"])
    title_domain_score = _percent_to_points(title_domain_percent, SCORE_WEIGHTS["title_domain"])
    education_score = _percent_to_points(education_percent, SCORE_WEIGHTS["education"])
    location_score = _percent_to_points(location_percent, SCORE_WEIGHTS["location"])
    preferred_skills_score = _percent_to_points(preferred_skill_percent, SCORE_WEIGHTS["preferred_skills"])
    semantic_score = _percent_to_points(semantic_percent, SCORE_WEIGHTS["semantic"])

    overall = round(
        skills_score
        + experience_score
        + title_domain_score
        + education_score
        + location_score
        + preferred_skills_score
        + semantic_score,
        2,
    )

    strengths: list[str] = []
    gaps: list[str] = []
    if required_detail.matched_skills:
        strengths.append("Matches required skills: " + ", ".join(required_detail.matched_skills[:5]))
    if preferred_detail.matched_skills:
        strengths.append("Also matches preferred skills: " + ", ".join(preferred_detail.matched_skills[:5]))
    if experience_percent >= 90:
        strengths.append("Experience aligns with the job requirement")
    if title_domain_percent >= 50:
        strengths.append("Profile titles or domain language align with the role")
    if location_percent >= 90:
        strengths.append("Location or work preference aligns with the job")

    if required_detail.missing_required_skills:
        gaps.append("Missing required skills: " + ", ".join(required_detail.missing_required_skills[:5]))
    if experience_percent < 60:
        gaps.append("Experience is below or not clearly aligned with the requested range")
    if education_percent < 50 and job.education:
        gaps.append("Education or certification evidence is incomplete for this role")
    if location_percent < 60:
        gaps.append("Location or work preference may not align")
    if not strengths:
        strengths.append("Some professional signals overlap with the job")
    if not gaps:
        gaps.append("No major gaps found in available structured data")

    rec = recommendation(overall, required_detail.missing_required_skills)
    summary = (
        f"{match_level(overall)} based on structured profile and job scoring. "
        f"Required skill coverage is {required_skill_percent:.0f}%, "
        f"experience alignment is {experience_percent:.0f}%, and semantic relevance is {semantic_percent:.0f}%."
    )

    return CandidateScore(
        candidate_id=candidate.candidate_id,
        overall_score=overall,
        skills_score=skills_score,
        experience_score=experience_score,
        title_domain_score=title_domain_score,
        education_score=education_score,
        location_score=location_score,
        preferred_skills_score=preferred_skills_score,
        semantic_score=semantic_score,
        matched_skills=required_detail.matched_skills,
        missing_required_skills=required_detail.missing_required_skills,
        matched_preferred_skills=preferred_detail.matched_skills,
        strengths=strengths,
        gaps=gaps,
        ai_summary=summary,
        recommendation=rec,
        hard_requirements={
            "required_skills": sorted(job.required_skills),
            "experience_min": job.experience_min,
            "experience_max": job.experience_max,
            "education": job.education,
        },
        preferred_requirements={
            "preferred_skills": sorted(job.preferred_skills),
            "location": job.location,
            "work_mode": job.work_mode,
            "employment_type": job.employment_type,
        },
        semantic_signals={
            "method": "token_overlap",
            "overlap_terms": semantic_overlap,
            "semantic_percent": semantic_percent,
        },
    )
