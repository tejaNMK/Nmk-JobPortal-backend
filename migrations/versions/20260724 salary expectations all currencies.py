"""seed salary bands in each country's real currency (fixes candidates in
non-curated countries, e.g. Japan/France/Brazil/etc., seeing US-dollar
bands by default -- the country-agnostic fallback introduced in
5f8a3c1e9b47 only ever had "$..." labels, so anyone outside the 8
hand-curated countries from 7c2e9f4a1d68 still saw dollars)

Revision ID: 3d7c1a9f5e62
Revises: 9a1d5e7c3f82
Create Date: 2026-07-24 00:00:00.000000
"""

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3d7c1a9f5e62"
down_revision = "9a1d5e7c3f82"
branch_labels = None
depends_on = None


# Curated, realistic bands for widely-used currencies (same illustrative
# spirit as the US/UK/Canada/etc. bands in 7c2e9f4a1d68 -- adjust freely
# later, these aren't exact market benchmarks). Keyed by ISO-4217 code so
# every country sharing a currency (e.g. the ~20 Eurozone countries) gets
# the same, correctly-labeled bands instead of only the one country whose
# name happened to be hand-picked before.
CURRENCY_BANDS = {
    "USD": ["$50K - $70K", "$70K - $90K", "$90K - $120K", "$120K - $150K", "$150K+"],
    "GBP": ["£30K - £45K", "£45K - £60K", "£60K - £80K", "£80K - £100K", "£100K+"],
    "EUR": ["€40K - €55K", "€55K - €70K", "€70K - €90K", "€90K - €110K", "€110K+"],
    "CAD": ["C$50K - C$70K", "C$70K - C$90K", "C$90K - C$120K", "C$120K - C$150K", "C$150K+"],
    "AUD": ["A$60K - A$80K", "A$80K - A$100K", "A$100K - A$130K", "A$130K - A$160K", "A$160K+"],
    "SGD": ["S$50K - S$70K", "S$70K - S$90K", "S$90K - S$120K", "S$120K - S$150K", "S$150K+"],
    "AED": ["AED 120K - AED 180K", "AED 180K - AED 240K", "AED 240K - AED 300K", "AED 300K - AED 400K", "AED 400K+"],
    "NZD": ["NZ$55K - NZ$75K", "NZ$75K - NZ$95K", "NZ$95K - NZ$125K", "NZ$125K - NZ$155K", "NZ$155K+"],
    "CHF": ["CHF 70K - CHF 90K", "CHF 90K - CHF 110K", "CHF 110K - CHF 140K", "CHF 140K - CHF 170K", "CHF 170K+"],
    "ZAR": ["R300K - R450K", "R450K - R600K", "R600K - R800K", "R800K - R1M", "R1M+"],
    "HKD": ["HK$300K - HK$450K", "HK$450K - HK$600K", "HK$600K - HK$800K", "HK$800K - HK$1M", "HK$1M+"],
    "SAR": ["SAR 100K - SAR 150K", "SAR 150K - SAR 200K", "SAR 200K - SAR 260K", "SAR 260K - SAR 340K", "SAR 340K+"],
    "QAR": ["QAR 100K - QAR 150K", "QAR 150K - QAR 200K", "QAR 200K - QAR 260K", "QAR 260K - QAR 340K", "QAR 340K+"],
    "JPY": ["¥4M - ¥6M", "¥6M - ¥8M", "¥8M - ¥10M", "¥10M - ¥13M", "¥13M+"],
    "CNY": ["¥150K - ¥250K", "¥250K - ¥350K", "¥350K - ¥500K", "¥500K - ¥700K", "¥700K+"],
    "KRW": ["₩40M - ₩60M", "₩60M - ₩80M", "₩80M - ₩110M", "₩110M - ₩150M", "₩150M+"],
    "MYR": ["RM60K - RM90K", "RM90K - RM120K", "RM120K - RM160K", "RM160K - RM200K", "RM200K+"],
    "PHP": ["₱600K - ₱900K", "₱900K - ₱1.2M", "₱1.2M - ₱1.6M", "₱1.6M - ₱2M", "₱2M+"],
    "IDR": ["Rp150M - Rp250M", "Rp250M - Rp350M", "Rp350M - Rp500M", "Rp500M - Rp700M", "Rp700M+"],
    "THB": ["฿500K - ฿800K", "฿800K - ฿1.1M", "฿1.1M - ฿1.5M", "฿1.5M - ฿2M", "฿2M+"],
    "PKR": ["₨1.5M - ₨2.5M", "₨2.5M - ₨3.5M", "₨3.5M - ₨5M", "₨5M - ₨7M", "₨7M+"],
    "BDT": ["৳800K - ৳1.2M", "৳1.2M - ৳1.8M", "৳1.8M - ৳2.5M", "৳2.5M - ৳3.5M", "৳3.5M+"],
    "NGN": ["₦4M - ₦7M", "₦7M - ₦10M", "₦10M - ₦15M", "₦15M - ₦20M", "₦20M+"],
    "EGP": ["E£150K - E£250K", "E£250K - E£350K", "E£350K - E£500K", "E£500K - E£700K", "E£700K+"],
    "TRY": ["₺400K - ₺600K", "₺600K - ₺800K", "₺800K - ₺1.1M", "₺1.1M - ₺1.5M", "₺1.5M+"],
    "PLN": ["zł80K - zł120K", "zł120K - zł160K", "zł160K - zł220K", "zł220K - zł280K", "zł280K+"],
    "BRL": ["R$60K - R$90K", "R$90K - R$120K", "R$120K - R$160K", "R$160K - R$200K", "R$200K+"],
    "MXN": ["MX$300K - MX$450K", "MX$450K - MX$600K", "MX$600K - MX$800K", "MX$800K - MX$1M", "MX$1M+"],
}


def _generic_bands(currency_code: str) -> list[str]:
    """For any currency without curated bands above, fall back to the same
    K-scale as the old default -- but labeled with the country's *actual*
    currency code (e.g. "XOF 50K - XOF 70K") instead of a dollar sign, so
    the currency is always correct even where the exact scale is only a
    rough placeholder (same caveat as CTC_PLACEHOLDER_BY_CURRENCY on the
    frontend: illustrative, not a real market benchmark)."""
    return [
        f"{currency_code} 50K - {currency_code} 70K",
        f"{currency_code} 70K - {currency_code} 90K",
        f"{currency_code} 90K - {currency_code} 120K",
        f"{currency_code} 120K - {currency_code} 150K",
        f"{currency_code} 150K+",
    ]


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"

    parts = []
    ascii_buffer = []
    for char in str(value):
        if ord(char) < 128:
            ascii_buffer.append(char)
            continue

        if ascii_buffer:
            parts.append("'" + "".join(ascii_buffer).replace("'", "''") + "'")
            ascii_buffer = []
        parts.append(f"chr({ord(char)})")

    if ascii_buffer:
        parts.append("'" + "".join(ascii_buffer).replace("'", "''") + "'")

    return " || ".join(parts) if parts else "''"


def _already_seeded_clause() -> str:
    return """
        NOT EXISTS (
            SELECT 1
            FROM master_salary_expectations mse
            WHERE mse.country_id = master_countries.country_id
        )
    """


def _upgrade_offline() -> None:
    curated_codes = set(CURRENCY_BANDS)

    for currency_code, bands in CURRENCY_BANDS.items():
        for idx, label in enumerate(bands):
            op.execute(
                "INSERT INTO master_salary_expectations (country_id, label, sort_order) "
                f"SELECT country_id, {_sql_literal(label)}, {idx} "
                "FROM master_countries "
                f"WHERE is_active = true AND currency_code = {_sql_literal(currency_code)} "
                f"AND {_already_seeded_clause()} "
                "ON CONFLICT (COALESCE(country_id, ''), label) DO NOTHING"
            )

    curated_list = ", ".join(_sql_literal(code) for code in sorted(curated_codes))
    generic_ranges = [
        (" 50K - ", " 70K"),
        (" 70K - ", " 90K"),
        (" 90K - ", " 120K"),
        (" 120K - ", " 150K"),
        (" 150K+", ""),
    ]
    for idx, (middle, suffix) in enumerate(generic_ranges):
        if suffix:
            label_expr = (
                f"currency_code || {_sql_literal(middle)} || "
                f"currency_code || {_sql_literal(suffix)}"
            )
        else:
            label_expr = f"currency_code || {_sql_literal(middle)}"

        op.execute(
            "INSERT INTO master_salary_expectations (country_id, label, sort_order) "
            f"SELECT country_id, {label_expr}, {idx} "
            "FROM master_countries "
            "WHERE is_active = true "
            "AND currency_code IS NOT NULL "
            f"AND currency_code NOT IN ({curated_list}) "
            f"AND {_already_seeded_clause()} "
            "ON CONFLICT (COALESCE(country_id, ''), label) DO NOTHING"
        )


def _downgrade_offline() -> None:
    for currency_code, bands in CURRENCY_BANDS.items():
        for label in bands:
            op.execute(
                "DELETE FROM master_salary_expectations "
                "WHERE label = "
                f"{_sql_literal(label)} "
                "AND country_id IN ("
                "SELECT country_id FROM master_countries "
                f"WHERE currency_code = {_sql_literal(currency_code)}"
                ")"
            )

    curated_list = ", ".join(_sql_literal(code) for code in sorted(CURRENCY_BANDS))
    generic_ranges = [
        (" 50K - ", " 70K"),
        (" 70K - ", " 90K"),
        (" 90K - ", " 120K"),
        (" 120K - ", " 150K"),
        (" 150K+", ""),
    ]
    for middle, suffix in generic_ranges:
        if suffix:
            label_expr = (
                f"currency_code || {_sql_literal(middle)} || "
                f"currency_code || {_sql_literal(suffix)}"
            )
        else:
            label_expr = f"currency_code || {_sql_literal(middle)}"

        op.execute(
            "DELETE FROM master_salary_expectations mse "
            "USING master_countries mc "
            "WHERE mse.country_id = mc.country_id "
            "AND mc.currency_code IS NOT NULL "
            f"AND mc.currency_code NOT IN ({curated_list}) "
            f"AND mse.label = {label_expr}"
        )


def upgrade() -> None:
    if context.is_offline_mode():
        _upgrade_offline()
        return

    conn = op.get_bind()

    # Countries that already have their own dedicated rows (India's LPA
    # bands, plus the 7 curated countries from 7c2e9f4a1d68) keep exactly
    # what they have -- we only fill in the gap for every other country.
    already_seeded = {
        row[0]
        for row in conn.execute(
            sa.text("SELECT DISTINCT country_id FROM master_salary_expectations WHERE country_id IS NOT NULL")
        ).fetchall()
    }

    countries = conn.execute(
        sa.text("SELECT country_id, currency_code FROM master_countries WHERE is_active = true")
    ).fetchall()

    for country_id, currency_code in countries:
        if country_id in already_seeded or not currency_code:
            continue

        bands = CURRENCY_BANDS.get(currency_code) or _generic_bands(currency_code)
        for idx, label in enumerate(bands):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO master_salary_expectations (country_id, label, sort_order)
                    VALUES (:country_id, :label, :sort_order)
                    ON CONFLICT (COALESCE(country_id, ''), label) DO NOTHING
                    """
                ),
                {"country_id": country_id, "label": label, "sort_order": idx},
            )


def downgrade() -> None:
    if context.is_offline_mode():
        _downgrade_offline()
        return

    conn = op.get_bind()

    all_bands = set()
    for bands in CURRENCY_BANDS.values():
        all_bands.update(bands)

    countries = conn.execute(
        sa.text("SELECT country_id, currency_code FROM master_countries WHERE is_active = true")
    ).fetchall()

    for country_id, currency_code in countries:
        bands = CURRENCY_BANDS.get(currency_code) or (_generic_bands(currency_code) if currency_code else [])
        for label in bands:
            conn.execute(
                sa.text(
                    "DELETE FROM master_salary_expectations WHERE country_id = :country_id AND label = :label"
                ),
                {"country_id": country_id, "label": label},
            )
