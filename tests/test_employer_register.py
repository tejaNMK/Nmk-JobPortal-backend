"""Tests for employer registration endpoint"""
from uuid import uuid4
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from pydantic import ValidationError

from app.schema.employer import EmployerRegisterSchema
from app.service.authentication.auth_service import AuthService
from app.repository.authentication.users import UsersRepository
from app.repository.authentication.role import RoleRepository
from app.model.authentication.users import Users
from app.model.authentication.role import Role


# Test data
valid_employer_data = {
    "company_name": "Tech Corp",
    "first_name": "John",
    "middle_name": "An",

    "last_name": "Doe",
    "website": "https://techcorp.com",
    "work_email": "hr@techcorp.com",
    "country_code": "+1",
    "phone_number": "(415) 555-2671",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!",
    "team_size": "51-200",
    "agree_to_terms": True
}



class TestEmployerRegisterSchema:
    """Test the EmployerRegisterSchema validation"""

    def test_valid_registration_data(self):
        """Test that valid data passes validation"""
        data = EmployerRegisterSchema(**valid_employer_data)
        assert data.company_name == "Tech Corp"
        assert data.website == "https://techcorp.com"
        assert data.work_email == "hr@techcorp.com"
        assert data.country_code == "+1"
        assert data.phone_number == "+14155552671"
        assert data.team_size == "51-200"
        assert data.agree_to_terms is True

    def test_missing_company_name(self):
        """Test that company name is required"""
        data = valid_employer_data.copy()
        data["company_name"] = ""
        with pytest.raises(ValidationError, match="Company name is required"):
            EmployerRegisterSchema(**data)

    def test_missing_work_email(self):
        """Test that work email is required"""
        data = valid_employer_data.copy()
        del data["work_email"]
        with pytest.raises(ValidationError):
            EmployerRegisterSchema(**data)

    def test_missing_password(self):
        """Test that password is required"""
        data = valid_employer_data.copy()
        del data["password"]
        with pytest.raises(ValidationError):
            EmployerRegisterSchema(**data)

    def test_password_mismatch(self):
        """Test that password and confirm_password must match"""
        data = valid_employer_data.copy()
        data["confirm_password"] = "DifferentPass123!"
        with pytest.raises(ValidationError, match="Passwords do not match"):
            EmployerRegisterSchema(**data)

    def test_missing_confirm_password(self):
        """Test that confirm_password is required"""
        data = valid_employer_data.copy()
        del data["confirm_password"]
        with pytest.raises(ValidationError):
            EmployerRegisterSchema(**data)

    def test_missing_agree_to_terms(self):
        """Test that agree_to_terms is required"""
        data = valid_employer_data.copy()
        del data["agree_to_terms"]
        with pytest.raises(ValidationError):
            EmployerRegisterSchema(**data)

    def test_password_too_short(self):
        """Test that password must be at least 8 characters"""
        data = valid_employer_data.copy()
        data["password"] = "short"
        data["confirm_password"] = "short"
        with pytest.raises(ValidationError, match="Password must be between 8 and 25 characters"):

            EmployerRegisterSchema(**data)

    def test_password_exactly_8_chars(self):
        """Test that password with exactly 8 characters passes"""
        data = valid_employer_data.copy()
        data["password"] = "Abcdef1!"
        data["confirm_password"] = "Abcdef1!"

        schema = EmployerRegisterSchema(**data)
        assert schema.password == "Abcdef1!"

    def test_password_empty(self):
        """Test that password required message is shown"""
        data = valid_employer_data.copy()
        data["password"] = ""
        data["confirm_password"] = "Abcdef1!"
        with pytest.raises(ValidationError, match="Password is required"):
            EmployerRegisterSchema(**data)

    def test_confirm_password_empty(self):
        """Test that confirm_password required message is shown"""
        data = valid_employer_data.copy()
        data["password"] = "Abcdef1!"
        data["confirm_password"] = ""
        with pytest.raises(ValidationError, match="Confirm Password is required"):
            EmployerRegisterSchema(**data)

    def test_first_name_rejects_digits(self):
        """Test that first name rejects digits"""
        data = valid_employer_data.copy()
        data["first_name"] = "J0hn"
        with pytest.raises(ValidationError, match="First name must contain only letters, hyphens, and apostrophes"):
            EmployerRegisterSchema(**data)

    def test_last_name_rejects_special_chars(self):
        """Test that last name rejects special characters"""
        data = valid_employer_data.copy()
        data["last_name"] = "Doe!"
        with pytest.raises(ValidationError, match="Last name must contain only letters, hyphens, and apostrophes"):
            EmployerRegisterSchema(**data)

    def test_phone_number_rejects_special_chars(self):
        """Test that phone number rejects special characters"""
        data = valid_employer_data.copy()
        data["phone_number"] = "12345@7890"
        with pytest.raises(ValidationError, match="Invalid phone number"):
            EmployerRegisterSchema(**data)

    def test_phone_number_rejects_invalid_phone(self):
        """Test that phone number must be valid for the selected country"""
        data = valid_employer_data.copy()
        data["phone_number"] = "123456789"
        with pytest.raises(ValidationError, match="Invalid phone number"):
            EmployerRegisterSchema(**data)

    def test_phone_number_rejects_wrong_country(self):
        """Test that phone number must match the selected country code"""
        data = valid_employer_data.copy()
        data["country_code"] = "+91"
        data["phone_number"] = "(415) 555-2671"
        with pytest.raises(ValidationError, match="Invalid phone number for selected country"):
            EmployerRegisterSchema(**data)

    def test_phone_number_normalizes_formatting(self):
        """Test that formatting is stripped and phone_number is normalized to E.164"""
        data = valid_employer_data.copy()
        data["phone_number"] = " 415-555-2671 "
        schema = EmployerRegisterSchema(**data)
        assert schema.phone_number == "+14155552671"

    def test_country_code_required(self):
        """Test that country_code is required"""
        data = valid_employer_data.copy()
        del data["country_code"]
        with pytest.raises(ValidationError, match="Country code is required"):
            EmployerRegisterSchema(**data)


    def test_terms_not_agreed(self):

        """Test that agree_to_terms must be True"""
        data = valid_employer_data.copy()
        data["agree_to_terms"] = False
        with pytest.raises(ValidationError, match="Terms and confirm you have hiring authority"):
            EmployerRegisterSchema(**data)

    def test_invalid_email_format(self):
        """Test that invalid email raises error"""
        data = valid_employer_data.copy()
        data["work_email"] = "invalid-email"
        with pytest.raises(ValidationError):
            EmployerRegisterSchema(**data)

    def test_whitespace_company_name(self):
        """Test that whitespace-only company name fails"""
        data = valid_employer_data.copy()
        data["company_name"] = "   "
        with pytest.raises(ValidationError, match="Company name is required"):
            EmployerRegisterSchema(**data)

    def test_all_required_fields_present(self):
        """Test that all required fields are validated"""
        required_fields = [
            "company_name",
            "work_email",
            "country_code",
            "phone_number",
            "team_size",
            "password",
            "confirm_password",
            "agree_to_terms",
        ]

        for field in required_fields:
            data = valid_employer_data.copy()
            del data[field]
            with pytest.raises(ValidationError):
                EmployerRegisterSchema(**data)


class TestEmployerRegisterOptionalFields:
    """Test optional field handling"""

    def test_website_optional(self):
        """Test that website is optional"""
        data = valid_employer_data.copy()
        del data["website"]
        schema = EmployerRegisterSchema(**data)
        assert schema.website is None

    def test_team_size_required(self):
        """Test that team_size is required"""
        data = valid_employer_data.copy()
        del data["team_size"]
        with pytest.raises(ValidationError, match="Team size is required"):
            EmployerRegisterSchema(**data)

    def test_empty_website_rejected(self):
        """Test that blank website is rejected when provided"""
        data = valid_employer_data.copy()
        data["website"] = ""
        with pytest.raises(ValidationError, match="Website must not be blank"):
            EmployerRegisterSchema(**data)


class TestEmployerRegisterEdgeCases:
    """Edge case tests for employer registration"""

    def test_minimum_valid_data(self):
        """Test with minimum valid data"""
        data = {
            "company_name": "AB",
            "first_name": "Jo",
            "middle_name": "An",
            "last_name": "Do",
            "work_email": "a@b.com",
            "country_code": "+91",
            "phone_number": "98765 43210",
            "password": "Abcdef1!",
            "confirm_password": "Abcdef1!",

            "team_size": "1-10",
            "agree_to_terms": True
        }

        schema = EmployerRegisterSchema(**data)
        assert schema.company_name == "AB"

    def test_long_company_name(self):
        """Test with very long company name"""
        data = valid_employer_data.copy()
        data["company_name"] = "A" * 200
        schema = EmployerRegisterSchema(**data)
        assert schema.company_name == "'; DROP TABLE companies; --"

    def test_various_team_sizes(self):
        """Test different team size formats"""
        team_sizes = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"]
        for size in team_sizes:
            data = valid_employer_data.copy()
            data["team_size"] = size
            schema = EmployerRegisterSchema(**data)
            assert schema.team_size == size

    def test_url_formats(self):
        """Test various website URL formats"""
        urls = [
            "https://example.com",
            "http://example.com",
            "https://www.example.com",
            "https://subdomain.example.com/path",
        ]
        for url in urls:
            data = valid_employer_data.copy()
            data["website"] = url
            schema = EmployerRegisterSchema(**data)
            assert schema.website == url


class TestEmployerRegistrationUnitTests:
    """Unit tests for registration logic with mocked dependencies"""

    def test_validate_unique_contact_with_existing_email(self):
        """Test that duplicate email raises error"""
        existing_user = MagicMock(spec=Users)
        existing_user.email = "hr@techcorp.com"

        with patch.object(UsersRepository, "find_by_email", new_callable=AsyncMock, return_value=existing_user):
            from fastapi import HTTPException
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            with pytest.raises(HTTPException, match="Email already exists"):
                loop.run_until_complete(
                    AuthService._validate_unique_contact(email="hr@techcorp.com")
                )

    def test_validate_unique_contact_with_new_email(self):
        """Test that new email passes validation"""
        with patch.object(UsersRepository, "find_by_email", new_callable=AsyncMock, return_value=None):
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Should not raise
            loop.run_until_complete(
                AuthService._validate_unique_contact(email="new@company.com")
            )


class TestSecurityValidation:
    """Security-focused validation tests"""

    def test_short_password_rejected(self):
        """Test that short passwords are rejected"""
        short_passwords = ["pass", "1234567", "abc", "admin"]

        for pwd in short_passwords:
            data = valid_employer_data.copy()
            data["password"] = pwd
            data["confirm_password"] = pwd
            with pytest.raises(ValidationError):
                EmployerRegisterSchema(**data)


    def test_sql_injection_attempt_in_company_name(self):
        """Test that SQL injection-like content in company name is handled"""
        data = valid_employer_data.copy()
        data["company_name"] = "'; DROP TABLE companies; --"
        with pytest.raises(ValidationError, match="Company name must not exceed 50 characters"):
            EmployerRegisterSchema(**data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
