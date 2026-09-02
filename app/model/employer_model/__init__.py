# Employer models - use lazy imports via app.model.mapper_bootstrap
# Do not import models here to avoid duplicate table registration

from .employer_profile import EmployerProfile
from .company_profile import CompanyProfile
from .job import Job
from .ai_job_description_usage import AIJobDescriptionUsage
from .ai_candidate_match import AICandidateMatch
from .job_metrics import JobMetrics
from .shortlisted_candidate import ShortlistedCandidate
from .message_thread import MessageThread
from .message import Message
from .interview import Interview
from .interviewer import Interviewer
from .interview_interviewer import InterviewInterviewer
from .interview_history import InterviewHistory
from .candidate_recommendation import CandidateRecommendation

__all__ = [
    "EmployerProfile",
    "CompanyProfile",
    "Job",
    "AIJobDescriptionUsage",
    "AICandidateMatch",
    "JobMetrics",
    "ShortlistedCandidate",
    "MessageThread",
    "Message",
    "Interview",
    "Interviewer",
    "InterviewInterviewer",
    "InterviewHistory",
    "CandidateRecommendation",
]
