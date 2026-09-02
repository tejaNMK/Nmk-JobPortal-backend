"""Tests for candidate registration endpoint"""
from uuid import uuid4
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from pydantic import ValidationError

from app.schema.employer import CandidateRegisterSchema
from app.service.authentication.auth_service import AuthService
from app.repository.authentication.users import UsersRepository
from app.repository.authentication.role import RoleRepository
from app.repository.authentication.user_role import UsersRoleRepository
from app.model.authentication.users import Users
from app.model.authentication.role import Role



# Test data
valid_candidate_data = {
    "first_name": "John",
    "middle_name": "An",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "country_code": "+91",
    "phone_number": "98765 43210",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!",
    "desired_role": "Software Engineer",
    "agree_to_terms": True
}




class TestCandidateRegisterSchema:
    """Test the CandidateRegisterSchema validation"""

    def test_valid_registration_data(self):
        """Test that valid data passes validation"""
        data = CandidateRegisterSchema(**valid_candidate_data)
        assert data.first_name == "John"
        assert data.last_name == "Doe"
        assert data.email == "john.doe@example.com"
        assert data.country_code == "+91"
        assert data.phone_number == "+919876543210"
        assert data.desired_role == "Software Engineer"
        assert data.agree_to_terms is True

    def test_missing_first_name(self):
        """Test that first name is required"""
        data = valid_candidate_data.copy()
        data["first_name"] = ""
        with pytest.raises(ValidationError, match="First name is required"):
            CandidateRegisterSchema(**data)

    def test_password_mismatch(self):
        """Test that password and confirm_password must match"""
        data = valid_candidate_data.copy()
        data["confirm_password"] = "DifferentPass123!"
        with pytest.raises(ValidationError, match="Passwords do not match"):
            CandidateRegisterSchema(**data)

    def test_missing_confirm_password(self):
        """Test that confirm_password is required"""
        data = valid_candidate_data.copy()
        del data["confirm_password"]
        with pytest.raises(ValidationError):
            CandidateRegisterSchema(**data)

    def test_missing_last_name(self):
        """Test that last name is required"""
        data = valid_candidate_data.copy()
        data["last_name"] = ""
        with pytest.raises(ValidationError, match="Last name is required"):
            CandidateRegisterSchema(**data)

    def test_missing_desired_role(self):
        """Test that desired role is required"""
        data = valid_candidate_data.copy()
        data["desired_role"] = ""
        with pytest.raises(ValidationError, match="Desired role is required"):
            CandidateRegisterSchema(**data)

    def test_password_too_short(self):
        """Test that password must be at least 8 characters"""
        data = valid_candidate_data.copy()
        data["password"] = "short"
        data["confirm_password"] = "short"
        with pytest.raises(ValidationError, match="Password must be between 8 and 25 characters"):

            CandidateRegisterSchema(**data)

    def test_password_exactly_8_chars(self):
        """Test that password with exactly 8 characters passes"""
        data = valid_candidate_data.copy()
        data["password"] = "Abcdef1!"
        data["confirm_password"] = "Abcdef1!"

        schema = CandidateRegisterSchema(**data)
        assert schema.password == "Abcdef1!"

    def test_password_empty(self):
        """Test that password required message is shown"""
        data = valid_candidate_data.copy()
        data["password"] = ""
        data["confirm_password"] = "Abcdef1!"
        with pytest.raises(ValidationError, match="Password is required"):
            CandidateRegisterSchema(**data)

    def test_confirm_password_empty(self):
        """Test that confirm_password required message is shown"""
        data = valid_candidate_data.copy()
        data["password"] = "Abcdef1!"
        data["confirm_password"] = ""
        with pytest.raises(ValidationError, match="Confirm Password is required"):
            CandidateRegisterSchema(**data)

    def test_first_name_allows_hyphen_and_apostrophe(self):
        """Test that first name allows hyphen and apostrophe"""
        data = valid_candidate_data.copy()
        data["first_name"] = "Mary-Jane"

        schema = CandidateRegisterSchema(**data)

        assert schema.first_name == "Mary-Jane"

    def test_last_name_rejects_digits(self):
        """Test that last name rejects digits"""
        data = valid_candidate_data.copy()
        data["last_name"] = "Do3"
        with pytest.raises(ValidationError, match="Last name must contain only letters, hyphens, and apostrophes"):
            CandidateRegisterSchema(**data)

    def test_phone_number_rejects_letters(self):
        """Test that phone number rejects alphabets"""
        data = valid_candidate_data.copy()
        data["phone_number"] = "98765abcde"
        with pytest.raises(ValidationError, match="Invalid phone number"):
            CandidateRegisterSchema(**data)

    def test_phone_number_rejects_invalid_phone(self):
        """Test that phone number must be valid for the selected country"""
        data = valid_candidate_data.copy()
        data["phone_number"] = "123456789"
        with pytest.raises(ValidationError, match="Invalid phone number"):
            CandidateRegisterSchema(**data)

    def test_phone_number_rejects_wrong_country(self):
        """Test that phone number must match the selected country code"""
        data = valid_candidate_data.copy()
        data["country_code"] = "+1"
        data["phone_number"] = "9876543210"
        with pytest.raises(ValidationError, match="Invalid phone number for selected country"):
            CandidateRegisterSchema(**data)

    def test_phone_number_normalizes_formatting(self):
        """Test that formatting is stripped and phone_number is normalized to E.164"""
        data = valid_candidate_data.copy()
        data["phone_number"] = " 98765-43210 "
        schema = CandidateRegisterSchema(**data)
        assert schema.phone_number == "+919876543210"

    def test_country_code_required(self):
        """Test that country_code is required"""
        data = valid_candidate_data.copy()
        del data["country_code"]
        with pytest.raises(ValidationError, match="Country code is required"):
            CandidateRegisterSchema(**data)


    def test_terms_not_agreed(self):
        """Test that agree_to_terms must be True"""
        data = valid_candidate_data.copy()
        data["agree_to_terms"] = False
        with pytest.raises(ValidationError, match="Terms of Service and Privacy Policy"):
            CandidateRegisterSchema(**data)


    def test_invalid_email_format(self):
        """Test that invalid email raises error"""
        data = valid_candidate_data.copy()
        data["email"] = "invalid-email"
        with pytest.raises(ValidationError):
            CandidateRegisterSchema(**data)

    def test_whitespace_first_name(self):
        """Test that whitespace-only first name fails"""
        data = valid_candidate_data.copy()
        data["first_name"] = "   "
        with pytest.raises(ValidationError, match="First name is required"):
            CandidateRegisterSchema(**data)

    def test_whitespace_last_name(self):
        """Test that whitespace-only last name fails"""
        data = valid_candidate_data.copy()
        data["last_name"] = "   "
        with pytest.raises(ValidationError, match="Last name is required"):
            CandidateRegisterSchema(**data)

    def test_all_fields_required(self):
        """Test that removing any field raises validation error"""
        required_fields = [
            "first_name",
            "last_name",
            "email",
            "country_code",
            "phone_number",
            "password",
            "desired_role",
            "agree_to_terms",
        ]

        for field in required_fields:
            data = valid_candidate_data.copy()
            del data[field]
            with pytest.raises(ValidationError):
                CandidateRegisterSchema(**data)


class TestCandidateRegisterValidation:
    """Additional validation edge case tests"""

    def test_email_case_normalized(self):
        """Test that email is normalized to lowercase"""
        data = valid_candidate_data.copy()
        data["email"] = "John.Doe@Example.COM"
        schema = CandidateRegisterSchema(**data)
        assert schema.email == "john.doe@example.com"

    def test_desired_role_whitespace_handling(self):
        """Test that desired role whitespace is trimmed and collapsed"""
        data = valid_candidate_data.copy()
        data["desired_role"] = "  Software   Engineer  "
        schema = CandidateRegisterSchema(**data)
        assert schema.desired_role == "Software Engineer"

    def test_invalid_desired_role(self):
        """Test that desired_role must be one of the configured dropdown values"""
        data = valid_candidate_data.copy()
        data["desired_role"] = "data scientist"
        with pytest.raises(ValidationError, match="Desired role is invalid"):
            CandidateRegisterSchema(**data)

    def test_password_unicode_characters(self):
        """Test that unicode passwords work"""
        data = valid_candidate_data.copy()
        data["password"] = "SecurePass123!®™©"
        data["confirm_password"] = "SecurePass123!®™©"
        schema = CandidateRegisterSchema(**data)
        assert len(schema.password) >= 8


class TestCandidateRegistrationUnitTests:
    """Unit tests for registration logic with mocked dependencies"""

    def test_candidate_register_assigns_role_candidate_when_desired_role_is_valid_dropdown(self):
        """desired_role is a dropdown value, but DB role must be ROLE_CANDIDATE."""
        import asyncio
        from fastapi import HTTPException

        register_data = valid_candidate_data.copy()
        register_data["desired_role"] = "Data Analyst"

        role_obj = MagicMock(spec=Role)
        role_obj.role_code = "ROLE_CANDIDATE"
        role_obj.role_id = uuid4()

        created_user = MagicMock(spec=Users)
        created_user.user_id = uuid4()

        user_role_obj = MagicMock()
        user_role_obj.user_id = created_user.user_id
        user_role_obj.role_id = role_obj.role_id

        async def fake_validate_unique_contact(*args, **kwargs):
            return None

        with patch.object(AuthService, "_validate_unique_contact", new_callable=AsyncMock, side_effect=fake_validate_unique_contact), \
             patch.object(UsersRepository, "create", new_callable=AsyncMock, return_value=created_user), \
             patch.object(RoleRepository, "find_by_role_code", new_callable=AsyncMock, return_value=role_obj), \
             patch.object(UsersRoleRepository, "create", new_callable=AsyncMock, return_value=user_role_obj):

            schema = CandidateRegisterSchema(**register_data)

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(AuthService.candidate_register_service(schema))

            assert result["desired_role"] == "Data Analyst"
            assert result["role_code"] == "ROLE_CANDIDATE"
            RoleRepository.find_by_role_code.assert_awaited_once()

            args, kwargs = (
                RoleRepository.find_by_role_code.await_args
            )

            assert (
                "ROLE_CANDIDATE" in args
                or kwargs.get("role_code") == "ROLE_CANDIDATE"
            )



    def test_validate_unique_contact_with_existing_email(self):
        """Test that duplicate email raises error"""
        existing_user = MagicMock(spec=Users)
        existing_user.email = "john.doe@example.com"

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
                    AuthService._validate_unique_contact(email="john.doe@example.com")
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
                AuthService._validate_unique_contact(email="new@example.com")
            )


class TestFieldCombinations:
    """Test various field combination scenarios"""

    def test_minimum_valid_data(self):
        """Test with minimum valid data"""
        data = {
            "first_name": "Jo",
            "middle_name": "An",
            "last_name": "Do",
            "email": "j@d.com",
            "country_code": "+1",
            "phone_number": "(415) 555-2671",
            "password": "Abcdef1!",
            "confirm_password": "Abcdef1!",
            "desired_role": "Software Engineer",
            "agree_to_terms": True
        }

        schema = CandidateRegisterSchema(**data)
        assert schema.first_name == "Jo"
        assert schema.last_name == "Do"


    def test_long_names_and_password(self):
        """Test that names longer than max length are rejected"""
        data = valid_candidate_data.copy()
        data["first_name"] = "A" * 31
        data["last_name"] = "B" * 31
        with pytest.raises(ValidationError):
            CandidateRegisterSchema(**data)



class TestSecurityValidation:
    """Security-focused validation tests"""

    def test_common_password_rejected(self):
        """Test that short passwords (< 8 chars) are rejected"""
        weak_passwords = ["pass", "1234567", "abc", "admin"]

        for pwd in weak_passwords:
            data = valid_candidate_data.copy()
            data["password"] = pwd
            with pytest.raises(ValidationError):
                CandidateRegisterSchema(**data)

    def test_sql_injection_attempt(self):
        """Test that SQL injection-like content in names is rejected by alphabets-only rule"""
        data = valid_candidate_data.copy()
        data["first_name"] = "'; DROP TABLE users; --"
        with pytest.raises(ValidationError, match="First name must contain only letters, hyphens, and apostrophes"):
            CandidateRegisterSchema(**data)



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
