BEGIN;

-- Add missing candidate profile column
ALTER TABLE candidate_profiles
ADD COLUMN IF NOT EXISTS open_to_work BOOLEAN DEFAULT FALSE;

-- Backfill missing company profiles
INSERT INTO company_profiles (
    company_id,
    employer_id,
    company_name,
    website,
    description,
    industry,
    size,
    location,
    created_at,
    updated_at
)
SELECT
    CONCAT(
        'COMP',
        LPAD(
            (
                COALESCE(
                    (
                        SELECT MAX(
                            CAST(SUBSTRING(company_id FROM 5) AS INTEGER)
                        )
                        FROM company_profiles
                        WHERE company_id ~ '^COMP[0-9]+$'
                    ),
                    0
                )
                + ROW_NUMBER() OVER (ORDER BY ep.created_at)
            )::TEXT,
            3,
            '0'
        )
    ),
    ep.id,
    ep.company_name,
    ep.company_website,
    COALESCE(
        ep.company_description,
        ep.company_name || ' company profile'
    ),
    ep.industry,
    ep.company_size,
    ep.company_location,
    CURRENT_TIMESTAMP::TEXT,
    CURRENT_TIMESTAMP::TEXT
FROM employer_profiles ep
LEFT JOIN company_profiles cp
    ON cp.employer_id = ep.id
WHERE cp.employer_id IS NULL;

COMMIT;