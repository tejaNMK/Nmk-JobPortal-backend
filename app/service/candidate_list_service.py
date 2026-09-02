# =================
# Imports
# =================

from fastapi import HTTPException

from app.repository.candidate_repository.candidate_list_repo import (
    CandidateListRepo,
)


# ========================
# Candidate List Service
# ========================

class CandidateListService:

    @staticmethod
    async def get_candidates(
        session,
        page: int,
        page_size: int,
        search: str | None = None,
        status: str | None = None,
        skills: str | None = None,
        sort_by: str = "name",
        sort_order: str = "asc",
    ):


        # ======================
        # Page Size Validation
        # ======================

        if page_size not in [10, 25, 50]:
            raise HTTPException(
                status_code=400,
                detail="Page size must be 10, 25 or 50"
            )
        
        # =================
        # Page Validation
        # =================

        if page < 1:
            raise HTTPException(
                status_code=400,
                detail="Page must be greater than 0"
            )

        # =======================
        # Sort Order Validation
        # =======================

        allowed_sort_order = [
            "asc",
            "desc",
        ]

        if sort_order not in allowed_sort_order:
            raise HTTPException(
                status_code=400,
                detail="Invalid sort order"
            )

        # ====================================================
        # Status Validation
        # ====================================================

        allowed_status = [
    "ACTIVE",
    "INACTIVE",
]

        if status and status not in allowed_status:
            raise HTTPException(
                status_code=400,
                detail="Invalid status"
            )

        # ====================================================
        # Search Validation
        # ====================================================

        if search:
            search = search.strip()

            if len(search) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Search must contain at least 2 characters"
                )

        # ====================================================
        # Sort Validation
        # ====================================================

        allowed_sort_fields = [
            "name",
            "date",
            "status",
        ]

        if sort_by not in allowed_sort_fields:
            raise HTTPException(
                status_code=400,
                detail="Invalid sort field"
            )

        # ====================================================
        # Fetch Data
        # ====================================================

        records, total_records = (
            await CandidateListRepo.get_candidates(
                session=session,
                page=page,
                page_size=page_size,
                search=search,
                status=status,
                skills=skills,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        )

        # ====================================================
        # Build Response
        # ====================================================

        candidates = []

        for (
            profile,
            user,
            application,
            job,
        ) in records:

            candidates.append(
                {
                    "candidate_id": profile.candidate_id,
                    "name": (
                        f"{user.first_name} "
                        f"{user.last_name or ''}"
                    ).strip(),
                    "email": user.email,
                    "phone": user.mobile_number,
                    "job_applied": (
                        job.title
                        if job
                        else None
                    ),
                    "status": profile.status,
                }
            )

        return {
            "total_records": total_records,
            "page": page,
            "page_size": page_size,
            "candidates": candidates,
        }
    