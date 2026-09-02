import logging
from sqlalchemy.future import select

from sqlalchemy.ext.asyncio import AsyncSession
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job

logger = logging.getLogger(__name__)


class CompanyService:

    @staticmethod
    async def get_company_details(session: AsyncSession, company_id: str):

        company_query = select(
            CompanyProfile
        ).where(
            CompanyProfile.company_id == company_id
        )

        company_result = await session.execute(
            company_query
        )

        company = company_result.scalar_one_or_none()

        if not company:
            logger.warning(
                "Company details requested for invalid company_id=%s",
                company_id
            )
            return None
        
        logger.info(
            "Company details viewed successfully. company_id=%s employer_id=%s",
            company.company_id,
            company.employer_id
        )

        employer_query = select(
            EmployerProfile
        ).where(
            EmployerProfile.id == company.employer_id
        )

        employer_result = await session.execute(
            employer_query
        )

        employer = employer_result.scalar_one_or_none()

        jobs_query = (
            select(Job)
            .where(
                Job.employer_id == company.employer_id,
                Job.status == "PUBLISHED",
                Job.closed_at.is_(None),
                Job.is_deleted == False
            )
            .limit(100)
        )

        jobs_result = await session.execute(
            jobs_query
        )

        jobs = jobs_result.scalars().all()

        return {
            "company_id": company.company_id,
            "company_name": company.company_name,
            "website": company.website,
            "logo_path": company.logo_path,
            "description": company.description,
            "industry": company.industry,
            "size": company.size,
            "location": company.location,
            "company_email": employer.company_email if employer else None,
            "company_mobile": employer.company_mobile if employer else None,
            "open_jobs": [
                {
                    "job_id": job.job_id,
                    "title": job.title,
                    "location": job.location
                }
                for job in jobs
            ]
        }
