from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_optional
from app.dependencies.role_dependencies import candidate_only

from app.schema.common import ResponseSchema
from app.schema.candidate_job_search import (
    CandidateJobDetailsResponse,
    CandidateJobSearchResponse,
    CandidateJobSuggestionsResponse,
    CandidateJobSearchQuery,
)
from app.schema.candidate_job_recommendation import CandidateRecommendedJobsResponse
from app.schema.skill_match import SkillMatchResponse
from app.schema.job_match import JobMatchScoreResponse
from app.schema.ai_interview_question import AIInterviewQuestionsResponse
from app.schema.application_readiness import ApplicationReadinessScoreResponse
from app.service.candidate_job_recommendation_service import (
    CandidateJobRecommendationService,
)
from app.service.skill_match_service import SkillMatchService
from app.service.job_match_service import JobMatchService
from app.service.ai_interview_question_service import AIInterviewQuestionService
from app.service.application_readiness_service import ApplicationReadinessService
from app.service.candidate_job_search_service import CandidateJobSearchService
from app.service.job_application_service import JobApplicationService


router = APIRouter(prefix="/candidate", tags=["Candidate Jobs"])


# Keep this only for protected endpoints
def _get_user_id(payload: dict = Depends(candidate_only)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


@router.get(
    "/jobs",
    response_model=ResponseSchema[CandidateJobSearchResponse],
    response_model_exclude_none=True,
    summary="Search jobs",
    description=(
        "Search candidate-visible jobs. Job cards include `description_preview`, "
        "a plain-text preview capped at 120 characters, and do not include the "
        "complete job description."
    ),
)
async def search_jobs(
    search: Optional[str] = Query(default=None, max_length=100),
    location: Optional[str] = Query(default=None, max_length=100),
    company: Optional[str] = Query(default=None, max_length=100),
    employment_type: Optional[str] = Query(default=None, max_length=50),
    work_preference: Optional[str] = Query(default=None),
    experience: Optional[int] = Query(default=None, description="Years of experience (numeric)"),
    experience_level: Optional[str] = Query(default=None, description="Legacy labels"),

    salary_min: Optional[float] = Query(default=None, ge=0),
    salary_max: Optional[float] = Query(default=None, ge=0),
    skills: Optional[str] = Query(default=None, description="Comma-separated skills"),
    posted_within: Optional[str] = Query(default=None, description="24h | 7d | 30d"),
    sort: Optional[str] = Query(default="Relevance", description="Newest | Relevance"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    payload: Optional[dict] = Depends(get_jwt_payload_optional),
):
    # Public listing page, but a signed-in candidate still needs correct
    # already_applied/is_saved flags per job — see get_job_detail above for
    # why hardcoding None here silently breaks both of those flags.
    user_id = UUID(str(payload["user_id"])) if payload and payload.get("user_id") else None

    skills_list = None
    if skills:
        skills_list = [s.strip() for s in skills.split(",") if s.strip()]

    query = CandidateJobSearchQuery(
        search=search,
        location=location,
        company=company,
        employment_type=employment_type,
        work_preference=work_preference,
        experience=experience,
        experience_level=experience_level,
        salary_min=salary_min,
        salary_max=salary_max,
        skills=skills_list,
        posted_within=posted_within,
        sort=sort,
        page=page,
        page_size=page_size,
    )

    result: CandidateJobSearchResponse = await CandidateJobSearchService.search_jobs(
        session=session,
        user_id=user_id,
        search=query.search,
        location=query.location,
        work_preference=query.work_preference,
        employment_type=query.employment_type,
        candidate_experience=query.experience,
        experience_level=query.experience_level,
        salary_min=query.salary_min,
        salary_max=query.salary_max,
        skills=query.skills,
        posted_within=query.posted_within,
        company=query.company,
        sort=query.sort or "Relevance",
        page=query.page,
        page_size=query.page_size,
    )


    return ResponseSchema(
        success=True,
        status=200,
        message="Jobs fetched successfully",
        data=result.model_dump(),
    ).model_dump()


@router.get(
    "/jobs/recommended",
    response_model=ResponseSchema[CandidateRecommendedJobsResponse],
    response_model_exclude_none=True,
    summary="AI-powered recommended jobs",
    description=(
        "Returns personalized job recommendations for the logged-in candidate, "
        "ranked by AI-computed compatibility across skills, experience, title, "
        "location, salary, employment type, and work-mode preference. "
        "Expired, inactive, and already-applied jobs are excluded."
    ),
)
async def recommended_jobs(
    location: Optional[str] = Query(default=None, max_length=100),
    employment_type: Optional[str] = Query(default=None, max_length=50),
    work_preference: Optional[str] = Query(default=None),
    skills: Optional[str] = Query(default=None, description="Comma-separated skills"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    skills_list = None
    if skills:
        skills_list = [s.strip() for s in skills.split(",") if s.strip()]

    result: CandidateRecommendedJobsResponse = (
        await CandidateJobRecommendationService.get_recommended_jobs(
            session=session,
            user_id=user_id,
            location=location,
            employment_type=employment_type,
            work_preference=work_preference,
            skills=skills_list,
            page=page,
            page_size=page_size,
        )
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Recommended jobs fetched successfully",
        data=result.model_dump(),
    ).model_dump()


@router.get(
    "/jobs/suggestions",
    response_model=ResponseSchema[CandidateJobSuggestionsResponse],
    response_model_exclude_none=True,
    summary="Job suggestions",
    description=(
        "Returns matching job title suggestions and typed job cards. Suggestion "
        "cards include the same `description_preview` behavior as job search."
    ),
)
async def job_suggestions(
    q: str = Query(..., max_length=100),
    session: AsyncSession = Depends(get_db),
):
    result: CandidateJobSuggestionsResponse = (
        await CandidateJobSearchService.get_suggestions(
            session=session,
            user_id=None,
            q=q,
        )
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Suggestions fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=ResponseSchema[CandidateJobDetailsResponse],
    response_model_exclude_none=True,
    summary="Job details",
    description=(
        "Returns the complete candidate-visible job details for active, public "
        "jobs. Hidden, deleted, draft, inactive, closed, and expired jobs return "
        "404 Not Found."
    ),
)
async def get_job_detail(
    job_id: str,
    session: AsyncSession = Depends(get_db),
    payload: Optional[dict] = Depends(get_jwt_payload_optional),
):

    # their user_id, otherwise already_applied/is_saved always come back
    # False and the Apply button resets to "Apply Now" on every refresh.
    user_id = UUID(str(payload["user_id"])) if payload and payload.get("user_id") else None

    result: Optional[CandidateJobDetailsResponse] = (
        await CandidateJobSearchService.get_job_details(
            session=session,
            user_id=user_id,
            job_id=job_id,
        )
    )

    if not result:
        raise HTTPException(status_code=404, detail="Job not found")

    return ResponseSchema(
        success=True,
        status=200,
        message="Job fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/jobs/{job_id}/skill-match",
    response_model=ResponseSchema[SkillMatchResponse],
    response_model_exclude_none=True,
    summary="AI skill match for a job",
    description=(
        "Compares the logged-in candidate's skills (profile + latest resume) "
        "against a single job's listed skills. Returns matched skills, missing "
        "skills, and an overall skill-match percentage."
    ),
)
async def job_skill_match(
    job_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result: Optional[SkillMatchResponse] = await SkillMatchService.get_skill_match(
        session=session,
        user_id=user_id,
        job_id=job_id,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Job not found")

    return ResponseSchema(
        success=True,
        status=200,
        message="Skill match fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/jobs/{job_id}/ai-match-score",
    response_model=ResponseSchema[JobMatchScoreResponse],
    response_model_exclude_none=True,
    summary="AI job match score (AWS Bedrock)",
    description=(
        "Uses AWS Bedrock to generate a rich AI compatibility analysis between "
        "the logged-in candidate (profile + latest resume) and a single job: "
        "an overall 0-100 match score, matching/missing skills, an "
        "experience-fit analysis, strengths, weaknesses, a hiring "
        "recommendation (Excellent Fit / Good Fit / Moderate Fit / Low Fit), "
        "and improvement suggestions. Returns 404 if the job or candidate "
        "profile is not found, and 503 if the AI service is temporarily "
        "unavailable.\n\n"
        "Example response `data`:\n"
        "```json\n"
        "{\n"
        '  "job_id": "b7b7...",\n'
        '  "job_title": "Senior Backend Engineer",\n'
        '  "match_score": 82.5,\n'
        '  "matching_skills": ["Python", "FastAPI", "PostgreSQL"],\n'
        '  "missing_skills": ["Kubernetes"],\n'
        '  "experience_match_analysis": "The candidate\'s 6 years of backend '
        "experience closely matches the 5-8 year range required, with direct "
        'experience in the core tech stack.",\n'
        '  "strengths": ["Strong Python/FastAPI background", "Relevant '
        'domain experience"],\n'
        '  "weaknesses": ["No listed container orchestration experience"],\n'
        '  "hiring_recommendation": "Good Fit",\n'
        '  "improvement_suggestions": ["Highlight any Docker/K8s exposure '
        'on the resume", "Add measurable impact metrics to recent roles"]\n'
        "}\n"
        "```"
    ),
)
async def job_ai_match_score(
    job_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    service = JobMatchService()
    result: Optional[JobMatchScoreResponse] = await service.get_job_match_score(
        session=session,
        user_id=user_id,
        job_id=job_id,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Job not found")

    return ResponseSchema(
        success=True,
        status=200,
        message="AI job match score generated successfully",
        data=result.model_dump(),
    )


@router.get(
    "/jobs/{job_id}/readiness-score",
    response_model=ResponseSchema[ApplicationReadinessScoreResponse],
    response_model_exclude_none=True,
    summary="AI Application Readiness Score (AWS Bedrock)",
    description=(
        "Computes an overall 0-100 Application Readiness Score for the "
        "logged-in candidate against a single job, combining five factors:\n\n"
        "- **Resume Match Score** (AI) -- how well the candidate's resume "
        "content aligns with the job.\n"
        "- **Skills Match Score** (deterministic) -- reuses the same "
        "skill-overlap engine as `GET /candidate/jobs/{job_id}/skill-match`, "
        "so the two APIs never disagree.\n"
        "- **Experience Match Score** (deterministic) -- reuses the same "
        "experience-fit engine as `GET /candidate/jobs/recommended`.\n"
        "- **Profile Completeness Score** (deterministic) -- the "
        "candidate's existing profile completion percentage.\n"
        "- **Interview Readiness Score** (AI) -- how prepared the "
        "candidate appears to be for an interview for this job.\n\n"
        "`overall_score` is a deterministic weighted composite of the "
        "five factors above (never itself AI-generated), so it can't "
        "drift from the sub-scores it's computed from. The response also "
        "includes matched/missing skills, strengths, weaknesses, "
        "non-skill readiness gaps, personalized improvement suggestions, "
        "and a concise readiness explanation.\n\n"
        "Returns 404 if the job or candidate profile is not found, and "
        "502/503 if the AI service is temporarily unavailable or returns "
        "an unusable response.\n\n"
        "Example response `data`:\n"
        "```json\n"
        "{\n"
        '  "job_id": "b7b7...",\n'
        '  "job_title": "Senior Backend Engineer",\n'
        '  "overall_score": 78.4,\n'
        '  "resume_match_score": 75.0,\n'
        '  "skills_match_score": 82.5,\n'
        '  "experience_match_score": 100.0,\n'
        '  "profile_completeness_score": 60.0,\n'
        '  "interview_readiness_score": 65.0,\n'
        '  "matched_skills": ["Python", "FastAPI"],\n'
        '  "missing_skills": ["Kubernetes"],\n'
        '  "strengths": ["Strong Python/FastAPI background"],\n'
        '  "weaknesses": ["No container orchestration experience listed"],\n'
        '  "gaps": ["Resume lacks quantified achievements"],\n'
        '  "improvement_suggestions": ["Add measurable impact metrics to '
        'recent roles", "Highlight any Docker/K8s exposure"],\n'
        '  "readiness_explanation": "The candidate is a strong technical '
        'fit but the resume and profile could better showcase measurable '
        'impact before applying."\n'
        "}\n"
        "```"
    ),
)
async def job_application_readiness_score(
    job_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    service = ApplicationReadinessService()
    result: Optional[ApplicationReadinessScoreResponse] = (
        await service.get_application_readiness_score(
            session=session,
            user_id=user_id,
            job_id=job_id,
        )
    )

    if not result:
        raise HTTPException(status_code=404, detail="Job not found")

    return ResponseSchema(
        success=True,
        status=200,
        message="Application readiness score generated successfully",
        data=result.model_dump(),
    )


@router.get(
    "/jobs/{job_id}/ai-interview-questions",
    response_model=ResponseSchema[AIInterviewQuestionsResponse],
    response_model_exclude_none=True,
    summary="AI-generated, candidate-personalized interview questions for a job (AWS Bedrock)",
    description=(
        "Uses AWS Bedrock to generate 15-20 personalized interview "
        "questions for a job the logged-in candidate has applied to, "
        "grounded in both the job's title, company, description, skills, "
        "responsibilities, and requirements, and the candidate's own "
        "profile and latest resume (skills, experience, education). "
        "Questions span five categories -- Technical, Coding (only when "
        "the job calls for hands-on coding), Project-based, Behavioral, "
        "and HR -- and each carries a concise sample answer. Sample "
        "answers are grounded strictly in the candidate's own stated "
        "background and never invent experience or skills the candidate "
        "hasn't reported.\n\n"
        "Available regardless of the application's current status "
        "(Applied, Review, Shortlisted, etc.), so a candidate can use "
        "this to self-assess against a job at any point after applying.\n\n"
        "Requires candidate authentication. Returns 404 if the job or the "
        "candidate's profile is not found, 403 if the candidate has not "
        "applied to this job, and 503 if the AI service is temporarily "
        "unavailable.\n\n"
        "Example response `data`:\n"
        "```json\n"
        "{\n"
        '  "job_id": "b7b7...",\n'
        '  "jobTitle": "Senior Backend Engineer",\n'
        '  "companyName": "Globex",\n'
        '  "questions": [\n'
        "    {\n"
        '      "id": 1,\n'
        '      "category": "Technical",\n'
        '      "question": "You listed FastAPI and PostgreSQL on your '
        'resume -- how would you design this role\'s core service to '
        'scale?",\n'
        '      "sampleAnswer": "I\'d start by profiling the hot paths, '
        'then lean on async I/O and connection pooling before reaching '
        'for horizontal scaling..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    ),
)
async def job_ai_interview_questions(
    job_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    service = AIInterviewQuestionService()
    result: Optional[AIInterviewQuestionsResponse] = (
        await service.generate_interview_questions(
            session=session,
            user_id=user_id,
            job_id=job_id,
        )
    )

    if not result:
        raise HTTPException(status_code=404, detail="Job not found")

    return ResponseSchema(
        success=True,
        status=200,
        message="AI interview questions generated successfully",
        data=result.model_dump(),
    )


@router.post(
    "/applications/{application_id}/withdraw",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Withdraw job application",
)
async def withdraw_application(
    application_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await JobApplicationService.withdraw_application(
        session=session,
        user_id=user_id,
        application_id=application_id,
    )

    return {
        "success": True,
        "status": 200,
        "message": result["message"],
        "data": {
            "application_id": result.get("application_id"),
            "application_status": result.get("application_status"),
        },
    }