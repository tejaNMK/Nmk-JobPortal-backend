"""seed a larger list of target roles

Revision ID: a1c6f4e0d235
Revises: e83f19aa2c07
Create Date: 2026-07-22 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1c6f4e0d235"
down_revision = "e83f19aa2c07"
branch_labels = None
depends_on = None


# Expands the original 15-role seed list (added in 9d4f1a6b8c23) with a much
# broader set of common job titles across engineering, design, data,
# product, marketing, sales, operations, HR, finance, legal, and support —
# so the "Target roles" autocomplete has more to offer out of the box.
# Candidates can still free-type any role not in this list; it gets added
# to master_target_roles on the fly (see MasterDataService.resolve_target_roles).
SEED_TARGET_ROLES = [
    # Engineering
    "Frontend Engineer", "Backend Engineer", "Full Stack Engineer",
    "Mobile Engineer (iOS)", "Mobile Engineer (Android)", "Site Reliability Engineer",
    "Cloud Engineer", "Platform Engineer", "Embedded Systems Engineer",
    "Machine Learning Engineer", "AI Engineer", "Security Engineer",
    "Automation Test Engineer", "Solutions Architect", "Technical Lead",
    "Staff Engineer", "Principal Engineer", "CTO",
    # Data
    "Data Engineer", "Analytics Engineer", "BI Analyst", "Data Architect",
    "Machine Learning Researcher", "Database Administrator",
    # Product & Design
    "Product Owner", "Associate Product Manager", "Group Product Manager",
    "UI Designer", "Interaction Designer", "Visual Designer",
    "Graphic Designer", "UX Researcher", "Design Lead",
    # Marketing
    "Digital Marketing Manager", "Content Marketing Manager", "SEO Specialist",
    "Social Media Manager", "Brand Manager", "Growth Marketing Manager",
    "Marketing Analyst", "Email Marketing Specialist", "Performance Marketing Manager",
    # Sales & Business
    "Business Development Manager", "Account Executive", "Account Manager",
    "Sales Development Representative", "Sales Manager", "Regional Sales Manager",
    "Inside Sales Representative", "Partnerships Manager",
    # Operations & Support
    "Operations Manager", "Project Manager", "Program Manager",
    "Scrum Master", "Agile Coach", "Supply Chain Manager",
    "Logistics Coordinator", "Customer Support Representative",
    "Technical Support Engineer", "Implementation Specialist",
    # HR & People
    "HR Business Partner", "Talent Acquisition Specialist", "Recruiter",
    "People Operations Manager", "Learning & Development Manager",
    "Compensation & Benefits Analyst",
    # Finance & Legal
    "Financial Analyst", "Accountant", "Controller", "Finance Manager",
    "Investment Analyst", "Auditor", "Legal Counsel", "Compliance Officer",
    "Paralegal",
    # Content & Creative
    "Content Writer", "Copywriter", "Technical Writer", "Video Editor",
    "Photographer", "Illustrator",
    # Healthcare & Other
    "Registered Nurse", "Pharmacist", "Physician",
    "Teacher", "Academic Counselor", "Research Scientist",
    "Operations Analyst", "Executive Assistant", "Office Manager",
    "Founder / Entrepreneur", "Consultant", "IT Support Specialist",
    "Network Engineer", "Systems Administrator", "ERP Consultant",
    "Salesforce Administrator", "Procurement Manager", "Store Manager",
]


def upgrade() -> None:
    conn = op.get_bind()
    for name in SEED_TARGET_ROLES:
        conn.execute(
            sa.text(
                """
                INSERT INTO master_target_roles (name)
                VALUES (:name)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": name},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name in SEED_TARGET_ROLES:
        conn.execute(
            sa.text("DELETE FROM master_target_roles WHERE name = :name"),
            {"name": name},
        )