"""AI-powered job recommendation scoring engine.

This module is intentionally kept free of any database / ORM dependency so
it can be unit tested in isolation and, later, swapped out or augmented
with a model-backed implementation (embeddings similarity, an LLM re-ranker,
a learned-to-rank model, etc.) without touching the repository/service/
controller layers that surround it.

The current implementation is a transparent, explainable weighted-feature
scorer. Every factor from the "Recommendation Logic" section of the user
story is represented by one scoring function below, so the composite score
can be reasoned about (and unit tested) factor by factor. Swapping this for
a model-backed scorer later just means replacing `score_job_for_candidate`
with a call to that model while keeping the same
`CandidateMatchContext` / `JobMatchContext` / `MatchResult` contract, so
callers (the service layer) do not need to change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Set


# ---------------------------------------------------------------------------
# Weights — must sum to 100. Kept as named constants so the "why" behind a
# match score is easy to explain to a candidate/product owner, and easy to
# tune without touching the scoring logic itself.
# ---------------------------------------------------------------------------
WEIGHT_SKILLS = 35
WEIGHT_TITLE = 15
WEIGHT_EXPERIENCE = 15
WEIGHT_SALARY = 10
WEIGHT_EMPLOYMENT_TYPE = 8
WEIGHT_LOCATION = 8
WEIGHT_WORK_MODE = 7
WEIGHT_PROFILE_COMPLETENESS = 2

TOTAL_WEIGHT = (
    WEIGHT_SKILLS
    + WEIGHT_TITLE
    + WEIGHT_EXPERIENCE
    + WEIGHT_SALARY
    + WEIGHT_EMPLOYMENT_TYPE
    + WEIGHT_LOCATION
    + WEIGHT_WORK_MODE
    + WEIGHT_PROFILE_COMPLETENESS
)
assert TOTAL_WEIGHT == 100, "Recommendation engine weights must sum to 100"

# Minimum composite score (0-100) for a job to be considered a genuine
# recommendation rather than noise.
DEFAULT_MIN_MATCH_SCORE = 20.0

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with",
    "senior", "junior", "sr", "jr", "i", "ii", "iii", "iv", "level",
    "lead", "staff", "principal", "associate", "intern", "internship",
}

_WORD_RE = re.compile(r"[a-z0-9+#.]+")


def _tokenize(text: Optional[str]) -> Set[str]:
    if not text:
        return set()
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if w and w not in _STOPWORDS}


def _normalize_skill(skill: str) -> str:
    return re.sub(r"[^a-z0-9+#.]", "", skill.strip().lower())


def _normalize_skills(skills: Optional[Iterable[str]]) -> Set[str]:
    if not skills:
        return set()
    return {_normalize_skill(s) for s in skills if s and str(s).strip()}


def _normalize_token(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    return v or None


def _normalize_location(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return re.sub(r"\s+", " ", str(value).strip().lower()) or None


@dataclass
class CandidateMatchContext:
    """Every candidate-side signal the recommendation engine considers."""

    skills: Set[str] = field(default_factory=set)
    total_experience_years: Optional[float] = None
    headline: Optional[str] = None
    current_designation: Optional[str] = None
    preferred_titles: Set[str] = field(default_factory=set)
    current_location: Optional[str] = None
    preferred_location: Optional[str] = None
    desired_employment_type: Optional[str] = None
    work_preference: Optional[str] = None
    expected_salary_min: Optional[float] = None
    expected_salary_max: Optional[float] = None
    profile_completion_pct: int = 0

    @property
    def title_tokens(self) -> Set[str]:
        tokens: Set[str] = set()
        tokens |= _tokenize(self.headline)
        tokens |= _tokenize(self.current_designation)
        for title in self.preferred_titles:
            tokens |= _tokenize(title)
        return tokens


@dataclass
class JobMatchContext:
    """Every job-side signal the recommendation engine considers."""

    job_id: str
    title: str
    required_skills: Set[str] = field(default_factory=set)
    preferred_skills: Set[str] = field(default_factory=set)
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    work_mode: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None


@dataclass
class MatchResult:
    job_id: str
    score: float
    reasons: List[str]
    breakdown: dict


@dataclass
class SkillMatchDetail:
    """Standalone skill-match result — shared by the recommendation engine's
    skill factor (API-AI-003) and the dedicated Skill Matching Service
    (API-AI-002), so both APIs are guaranteed to agree with each other."""

    matched_skills: List[str]
    missing_required_skills: List[str]
    missing_preferred_skills: List[str]
    extra_skills: List[str]
    required_skills: List[str]
    preferred_skills: List[str]
    match_percentage: float


def compute_skill_match(
    candidate_skills: Set[str],
    required_skills: Set[str],
    preferred_skills: Optional[Set[str]] = None,
) -> SkillMatchDetail:
    """Compare a candidate's (normalized, lowercase) skill set against a
    job's required/preferred skills.

    `match_percentage` weights required-skill coverage more heavily than
    overall coverage — matching every required skill but none of the
    "nice to have" ones still scores well; matching only preferred skills
    while missing required ones scores poorly.
    """

    preferred_skills = preferred_skills or set()
    job_skills = required_skills | preferred_skills

    matched = candidate_skills & job_skills
    matched_required = candidate_skills & required_skills
    missing_required = required_skills - candidate_skills
    missing_preferred = preferred_skills - candidate_skills
    extra = candidate_skills - job_skills

    if not job_skills:
        # Nothing listed on the job to match against - neutral, not a
        # failure on the candidate's part.
        percentage = 50.0 if candidate_skills else 0.0
    elif not candidate_skills:
        percentage = 0.0
    else:
        coverage = len(matched) / len(job_skills)
        if required_skills:
            required_coverage = len(matched_required) / len(required_skills)
            ratio = min(1.0, 0.6 * coverage + 0.4 * required_coverage)
        else:
            ratio = coverage
        percentage = round(min(100.0, 100 * ratio), 2)

    return SkillMatchDetail(
        matched_skills=sorted(matched),
        missing_required_skills=sorted(missing_required),
        missing_preferred_skills=sorted(missing_preferred),
        extra_skills=sorted(extra),
        required_skills=sorted(required_skills),
        preferred_skills=sorted(preferred_skills),
        match_percentage=percentage,
    )


def _score_skills(candidate: CandidateMatchContext, job: JobMatchContext) -> tuple[float, Optional[str]]:
    detail = compute_skill_match(candidate.skills, job.required_skills, job.preferred_skills)

    if not (job.required_skills or job.preferred_skills):
        return WEIGHT_SKILLS * 0.5, None
    if not candidate.skills or not detail.matched_skills:
        return 0.0, None

    score = WEIGHT_SKILLS * (detail.match_percentage / 100)
    count = len(detail.matched_skills)
    reason = (
        f"Matches {count} skill{'s' if count != 1 else ''} you have: "
        + ", ".join(detail.matched_skills[:5])
    )
    return score, reason


def _score_title(candidate: CandidateMatchContext, job: JobMatchContext) -> tuple[float, Optional[str]]:
    job_tokens = _tokenize(job.title)
    candidate_tokens = candidate.title_tokens
    if not job_tokens or not candidate_tokens:
        return 0.0, None

    overlap = job_tokens & candidate_tokens
    if not overlap:
        return 0.0, None

    ratio = len(overlap) / len(job_tokens)
    score = WEIGHT_TITLE * min(1.0, ratio)
    reason = f"Job title aligns with your profile/target roles ({', '.join(sorted(overlap))})"
    return score, reason


def _score_experience(candidate: CandidateMatchContext, job: JobMatchContext) -> tuple[float, Optional[str]]:
    if candidate.total_experience_years is None:
        return WEIGHT_EXPERIENCE * 0.4, None  # unknown -> mild neutral credit

    exp = candidate.total_experience_years
    lo = job.experience_min
    hi = job.experience_max

    if lo is None and hi is None:
        return WEIGHT_EXPERIENCE * 0.5, None

    lo = lo if lo is not None else 0
    hi = hi if hi is not None else lo + 100

    if lo <= exp <= hi:
        return float(WEIGHT_EXPERIENCE), "Your experience fits the required range"

    # Graceful falloff for near misses (within 2 years of the band).
    distance = (lo - exp) if exp < lo else (exp - hi)
    if distance <= 2:
        ratio = max(0.0, 1 - (distance / 2))
        return WEIGHT_EXPERIENCE * ratio, "Your experience is close to the required range"

    return 0.0, None


def _score_salary(candidate: CandidateMatchContext, job: JobMatchContext) -> tuple[float, Optional[str]]:
    if candidate.expected_salary_min is None and candidate.expected_salary_max is None:
        return WEIGHT_SALARY * 0.5, None
    if job.salary_min is None and job.salary_max is None:
        return WEIGHT_SALARY * 0.5, None

    cand_lo = candidate.expected_salary_min if candidate.expected_salary_min is not None else 0
    cand_hi = candidate.expected_salary_max if candidate.expected_salary_max is not None else cand_lo
    job_lo = job.salary_min if job.salary_min is not None else 0
    job_hi = job.salary_max if job.salary_max is not None else job_lo

    if cand_hi <= 0:
        return WEIGHT_SALARY * 0.5, None

    # Overlapping ranges => full credit.
    if cand_lo <= job_hi and job_lo <= cand_hi:
        return float(WEIGHT_SALARY), "Salary range matches your expectation"

    gap = (cand_lo - job_hi) if cand_lo > job_hi else (job_lo - cand_hi)
    reference = max(cand_hi, job_hi, 1)
    ratio = max(0.0, 1 - (gap / reference))
    return WEIGHT_SALARY * ratio, None


def _score_employment_type(candidate: CandidateMatchContext, job: JobMatchContext) -> tuple[float, Optional[str]]:
    cand_type = _normalize_token(candidate.desired_employment_type)
    job_type = _normalize_token(job.employment_type)
    if not cand_type or not job_type:
        return WEIGHT_EMPLOYMENT_TYPE * 0.5, None
    if cand_type == job_type:
        return float(WEIGHT_EMPLOYMENT_TYPE), f"Employment type matches your preference ({job.employment_type})"
    return 0.0, None


def _score_work_mode(candidate: CandidateMatchContext, job: JobMatchContext) -> tuple[float, Optional[str]]:
    cand_mode = _normalize_token(candidate.work_preference)
    job_mode = _normalize_token(job.work_mode)
    if not cand_mode or not job_mode:
        return WEIGHT_WORK_MODE * 0.5, None
    if cand_mode == job_mode:
        return float(WEIGHT_WORK_MODE), f"Work mode matches your preference ({job.work_mode})"
    return 0.0, None


def _score_location(candidate: CandidateMatchContext, job: JobMatchContext) -> tuple[float, Optional[str]]:
    job_location = _normalize_location(job.location)
    if not job_location:
        return WEIGHT_LOCATION * 0.5, None

    # Remote jobs satisfy any location preference.
    preferred = _normalize_location(candidate.preferred_location)
    current = _normalize_location(candidate.current_location)

    for candidate_location, label in ((preferred, "preferred"), (current, "current")):
        if not candidate_location:
            continue
        if candidate_location == job_location or candidate_location in job_location or job_location in candidate_location:
            reason = f"Located in your {label} location ({job.location})"
            return float(WEIGHT_LOCATION), reason

    return 0.0, None


def _score_profile_completeness(candidate: CandidateMatchContext, job: JobMatchContext) -> tuple[float, Optional[str]]:
    pct = max(0, min(100, candidate.profile_completion_pct or 0))
    return WEIGHT_PROFILE_COMPLETENESS * (pct / 100), None


def score_job_for_candidate(
    candidate: CandidateMatchContext,
    job: JobMatchContext,
) -> MatchResult:
    """Compute a 0-100 compatibility score plus human-readable reasons.

    Each `_score_*` helper returns points earned out of that factor's
    weight, so the sum of every helper's output is naturally bounded to
    [0, 100].
    """

    breakdown: dict = {}
    reasons: List[str] = []
    total = 0.0

    for name, fn in (
        ("skills", _score_skills),
        ("title", _score_title),
        ("experience", _score_experience),
        ("salary", _score_salary),
        ("employment_type", _score_employment_type),
        ("work_mode", _score_work_mode),
        ("location", _score_location),
        ("profile_completeness", _score_profile_completeness),
    ):
        points, reason = fn(candidate, job)
        points = max(0.0, min(points, {
            "skills": WEIGHT_SKILLS,
            "title": WEIGHT_TITLE,
            "experience": WEIGHT_EXPERIENCE,
            "salary": WEIGHT_SALARY,
            "employment_type": WEIGHT_EMPLOYMENT_TYPE,
            "work_mode": WEIGHT_WORK_MODE,
            "location": WEIGHT_LOCATION,
            "profile_completeness": WEIGHT_PROFILE_COMPLETENESS,
        }[name]))
        breakdown[name] = round(points, 2)
        total += points
        if reason:
            reasons.append(reason)

    return MatchResult(
        job_id=job.job_id,
        score=round(min(100.0, total), 2),
        reasons=reasons,
        breakdown=breakdown,
    )


def rank_jobs_for_candidate(
    candidate: CandidateMatchContext,
    jobs: Sequence[JobMatchContext],
    *,
    min_score: float = DEFAULT_MIN_MATCH_SCORE,
) -> List[MatchResult]:
    """Score every job and return results sorted best-match-first.

    Ties are broken by job_id for a stable, deterministic ordering (useful
    for pagination consistency across requests).
    """

    results = [score_job_for_candidate(candidate, job) for job in jobs]
    results = [r for r in results if r.score >= min_score]
    results.sort(key=lambda r: (-r.score, r.job_id))
    return results