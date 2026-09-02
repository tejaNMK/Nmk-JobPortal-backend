from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.service import s3_service


router = APIRouter(prefix="/profile-images", tags=["profile-images"])


@router.get("/{user_id}/{filename}")
async def redirect_profile_image(user_id: str, filename: str):
    s3_key = s3_service.build_profile_image_key(user_id, filename)

    if not s3_service.object_exists(s3_key):
        raise HTTPException(status_code=404, detail="Profile image not found")

    url = s3_service.generate_profile_image_presigned_url(
        s3_key,
        expiry_seconds=300,
    )
    return RedirectResponse(
        url=url,
        status_code=307,
        headers={"Cache-Control": "private, max-age=300"},
    )
