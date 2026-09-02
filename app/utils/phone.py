import re
from dataclasses import dataclass

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType


@dataclass(frozen=True)
class NormalizedPhoneNumber:
    country_code: str
    e164: str
    national_number: str


def normalize_phone_number(
    country_code: str | None,
    phone_number: str | None,
    country_iso2: str | None = None,
) -> NormalizedPhoneNumber:
    if country_code is None or not str(country_code).strip():
        raise ValueError("Country code is required")
    if phone_number is None or not str(phone_number).strip():
        raise ValueError("Phone number is required")

    code = str(country_code).strip()
    if not code.startswith("+"):
        code = f"+{code}"
    code = re.sub(r"[^\d+]", "", code)

    if not re.fullmatch(r"\+[1-9]\d{0,4}", code):
        raise ValueError("Invalid country code")

    calling_code = int(code[1:])
    regions = phonenumbers.region_codes_for_country_code(calling_code)
    if not regions:
        raise ValueError("Invalid country code")

    requested_region = str(country_iso2 or "").strip().upper()
    if requested_region:
        if not re.fullmatch(r"[A-Z]{2}", requested_region):
            raise ValueError("Invalid phone country")
        if requested_region not in regions:
            raise ValueError("Invalid phone country for selected country code")

    raw_phone = str(phone_number).strip()
    if re.search(r"[A-Za-z]", raw_phone):
        raise ValueError("Invalid phone number")

    cleaned_phone = re.sub(r"[^\d+]", "", raw_phone)
    if not cleaned_phone:
        raise ValueError("Phone number is required")

    if cleaned_phone.startswith("+"):
        parse_value = cleaned_phone
        parse_region = None
    else:
        parse_value = raw_phone
        parse_region = requested_region or regions[0]

    try:
        parsed = phonenumbers.parse(parse_value, parse_region)
    except NumberParseException as exc:
        raise ValueError("Invalid phone number") from exc

    if parsed.country_code != calling_code:
        raise ValueError("Invalid phone number for selected country")

    if not phonenumbers.is_possible_number(parsed):
        raise ValueError("Invalid phone number")

    # IMPORTANT: is_valid_number() alone is not enough for calling codes
    # shared by multiple countries (+1 covers US/Canada/Puerto Rico/Jamaica
    # etc, +44 covers UK/Guernsey/Jersey/Isle of Man, +7 covers Russia/
    # Kazakhstan...). A number can be a perfectly "valid" number for one of
    # those sibling countries while being invalid for the one the person
    # actually selected in the dropdown -- e.g. an Indian 10-digit mobile
    # number like 939-823-8044 is a structurally valid number for Puerto
    # Rico under the shared +1 NANP code, so is_valid_number() alone would
    # incorrectly accept it even though "United States" was selected. Region
    # here is always the "main"/primary region for that calling code
    # (regions[0]), matching the single country the dropdown item stands for.
    region_for_validation = requested_region or regions[0]
    if not phonenumbers.is_valid_number_for_region(parsed, region_for_validation):
        raise ValueError("Invalid phone number for selected country")

    # is_valid_number_for_region() accepts a number of ANY type (fixed-line,
    # mobile, toll-free, ...), not specifically a mobile number -- but this
    # field is used for OTP delivery, so it needs to actually be a mobile
    # number. Some numbering plans are broad enough that a number shaped
    # for one type also happens to match another: e.g. a US-style
    # "212XXXXXXX" number is a structurally valid Indian *fixed-line*
    # number (STD code + subscriber number), so without this check it
    # would incorrectly pass as a "valid" Indian phone number. Numbering
    # plans that don't distinguish mobile from fixed-line at all (NANP:
    # US/Canada/etc) report FIXED_LINE_OR_MOBILE and are accepted here too,
    # since there's no way to be stricter for those countries.
    number_type = phonenumbers.number_type(parsed)
    if number_type not in (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE):
        raise ValueError("Invalid phone number for selected country")

    return NormalizedPhoneNumber(
        country_code=f"+{parsed.country_code}",
        e164=phonenumbers.format_number(parsed, PhoneNumberFormat.E164),
        national_number=str(parsed.national_number),
    )