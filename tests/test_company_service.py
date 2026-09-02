from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.service.company_service import CompanyService


class TestCompanyService:

    @pytest.mark.asyncio
    async def test_get_company_details_success(self):

        company = MagicMock()
        company.company_id = "COMP001"
        company.employer_id = "EMP001"
        company.company_name = "Pineapple"
        company.website = "https://pineapple.com"
        company.logo_path = "/logos/pineapple.png"
        company.description = "Sample company"
        company.industry = "IT"
        company.size = "100-500"
        company.location = "Hyderabad"

        employer = MagicMock()
        employer.company_email = "test@company.com"
        employer.company_mobile = "9876543210"

        job = MagicMock()
        job.job_id = "JOB001"
        job.title = "Python Developer"
        job.location = "Hyderabad"

        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = company

        employer_result = MagicMock()
        employer_result.scalar_one_or_none.return_value = employer

        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = [job]

        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[
                company_result,
                employer_result,
                jobs_result
            ]
        )

        result = await CompanyService.get_company_details(
            session=session,
            company_id="COMP001"
        )

        assert result["company_id"] == "COMP001"
        assert result["company_name"] == "Pineapple"
        assert result["company_email"] == "test@company.com"
        assert len(result["open_jobs"]) == 1

    # COMPANY NOT FOUND

    @pytest.mark.asyncio
    async def test_get_company_details_company_not_found(self):

        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = None

        session = MagicMock()
        session.execute = AsyncMock(
            return_value=company_result
        )

        result = await CompanyService.get_company_details(
            session=session,
            company_id="INVALID"
        )

        assert result is None

    # EMPLOYER NOT FOUND
    @pytest.mark.asyncio
    async def test_get_company_details_without_employer(self):

        company = MagicMock()
        company.company_id = "COMP001"
        company.employer_id = "EMP001"
        company.company_name = "Pineapple"
        company.website = "https://pineapple.com"
        company.logo_path = None
        company.description = "Sample"
        company.industry = "IT"
        company.size = "100"
        company.location = "Hyderabad"

        job = MagicMock()
        job.job_id = "JOB001"
        job.title = "Developer"
        job.location = "Hyderabad"

        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = company

        employer_result = MagicMock()
        employer_result.scalar_one_or_none.return_value = None

        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = [job]

        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[
                company_result,
                employer_result,
                jobs_result
            ]
        )

        result = await CompanyService.get_company_details(
            session=session,
            company_id="COMP001"
        )

        assert result["company_email"] is None
        assert result["company_mobile"] is None

    # JOBS NOT FOUND
    @pytest.mark.asyncio
    async def test_get_company_details_without_jobs(self):

        company = MagicMock()
        company.company_id = "COMP001"
        company.employer_id = "EMP001"
        company.company_name = "Pineapple"
        company.website = "https://pineapple.com"
        company.logo_path = None
        company.description = "Sample"
        company.industry = "IT"
        company.size = "100"
        company.location = "Hyderabad"

        employer = MagicMock()
        employer.company_email = "test@company.com"
        employer.company_mobile = "9876543210"

        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = company

        employer_result = MagicMock()
        employer_result.scalar_one_or_none.return_value = employer

        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = []

        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[
                company_result,
                employer_result,
                jobs_result
            ]
        )

        result = await CompanyService.get_company_details(
            session=session,
            company_id="COMP001"
        )

        assert result["open_jobs"] == []

    # LOGGING WARNINGS
    @pytest.mark.asyncio
    async def test_get_company_details_logs_warning_for_invalid_company(self):

        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = None

        session = MagicMock()
        session.execute = AsyncMock(
            return_value=company_result
        )

        with patch(
            "app.service.company_service.logger"
        ) as mock_logger:

            await CompanyService.get_company_details(
                session=session,
                company_id="INVALID"
            )

            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_company_details_logs_info(self):

        company = MagicMock()
        company.company_id = "COMP001"
        company.employer_id = "EMP001"
        company.company_name = "Pineapple"
        company.website = "https://pineapple.com"
        company.logo_path = None
        company.description = "Sample"
        company.industry = "IT"
        company.size = "100"
        company.location = "Hyderabad"

        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = company

        employer_result = MagicMock()
        employer_result.scalar_one_or_none.return_value = None

        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = []

        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[
                company_result,
                employer_result,
                jobs_result
            ]
        )

        with patch(
            "app.service.company_service.logger"
        ) as mock_logger:

            await CompanyService.get_company_details(
                session=session,
                company_id="COMP001"
            )

            mock_logger.info.assert_called_once()