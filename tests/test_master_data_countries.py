import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.service.master_data_service import MasterDataService


def test_list_countries_preserves_currency_codes_without_fallback():
    rows = [
        SimpleNamespace(
            country_id="in",
            name="India",
            iso_code="IN",
            phone_code="+91",
            currency_code="INR",
        ),
        SimpleNamespace(
            country_id="us",
            name="United States",
            iso_code="US",
            phone_code="+1",
            currency_code="USD",
        ),
        SimpleNamespace(
            country_id="zz",
            name="No Currency",
            iso_code="ZZ",
            phone_code=None,
            currency_code=None,
        ),
    ]

    with patch(
        "app.service.master_data_service.MasterDataRepo.list_countries",
        new_callable=AsyncMock,
        return_value=rows,
    ):
        result = asyncio.run(MasterDataService.list_countries(session=None))

    by_country = {country.country_id: country for country in result}
    assert by_country["in"].currency_code == "INR"
    assert by_country["us"].currency_code == "USD"
    assert by_country["zz"].currency_code is None


def test_list_locations_passes_country_filter_to_repository():
    with patch(
        "app.service.master_data_service.MasterDataRepo.get_country",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(country_id="in"),
    ), patch(
        "app.service.master_data_service.MasterDataRepo.list_locations",
        new_callable=AsyncMock,
        return_value=[
            SimpleNamespace(location_id="hyd", country_id="in", name="Hyderabad")
        ],
    ) as list_locations:
        result = asyncio.run(
            MasterDataService.list_locations(session=None, country_id="in")
        )

    assert result[0].country_id == "in"
    list_locations.assert_awaited_once_with(None, "in")
