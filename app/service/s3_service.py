import logging
import re

from fastapi import HTTPException
import os


try:
    import boto3
except Exception:
    boto3 = None

try:
    from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
except Exception:
    ClientError = Exception
    BotoCoreError = Exception
    EndpointConnectionError = Exception

logger = logging.getLogger(__name__)

PROFILE_IMAGE_USER_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
PROFILE_IMAGE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PROFILE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _s3_client():
    if boto3 is None:
        raise HTTPException(
            status_code=500,
            detail="boto3 is required for S3 uploads",
        )
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )


def _bucket() -> str:
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("S3_BUCKET_NAME environment variable is required")
    return bucket


def _client_error_code(error: Exception) -> str:
    response = getattr(error, "response", {}) or {}
    code = str((response.get("Error") or {}).get("Code", ""))
    if code:
        return code
    if getattr(error, "args", None) and isinstance(error.args[0], dict):
        return str((error.args[0].get("Error") or {}).get("Code", ""))
    return ""


def _client_error_status(error: Exception) -> int | None:
    response = getattr(error, "response", {}) or {}
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    if status:
        return status
    if getattr(error, "args", None) and isinstance(error.args[0], dict):
        return error.args[0].get("ResponseMetadata", {}).get("HTTPStatusCode")
    return None


def _is_endpoint_connection_error(error: Exception) -> bool:
    return error.__class__.__name__ == "EndpointConnectionError" or hasattr(
        error,
        "endpoint_url",
    )


def build_profile_image_key(user_id: str, filename: str) -> str:
    user_id = (user_id or "").strip()
    filename = (filename or "").strip()
    if not PROFILE_IMAGE_USER_ID_PATTERN.fullmatch(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if (
        not PROFILE_IMAGE_FILENAME_PATTERN.fullmatch(filename)
        or "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
        or ".." in filename.split(".")
    ):
        raise HTTPException(status_code=400, detail="Invalid image filename")
    _, extension = os.path.splitext(filename.lower())
    if extension not in PROFILE_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid image filename")
    return f"profile-images/{user_id}/{filename}"


def object_exists(s3_key: str) -> bool:
    try:
        _s3_client().head_object(Bucket=_bucket(), Key=s3_key)
        return True
    except ClientError as e:
        if _is_endpoint_connection_error(e):
            logger.warning(
                "S3 head_object unavailable",
                extra={"event": "s3_head_object_unavailable"},
            )
            raise HTTPException(status_code=503, detail="File storage is unavailable")
        code = _client_error_code(e)
        status_code = _client_error_status(e)
        if code in ("NoSuchKey", "404", "NotFound") or status_code == 404:
            return False
        logger.warning(
            "S3 head_object failed",
            extra={"event": "s3_head_object_failed"},
        )
        raise HTTPException(status_code=502, detail="File storage request failed")
    except (EndpointConnectionError, ConnectionError, BotoCoreError):
        logger.warning(
            "S3 head_object unavailable",
            extra={"event": "s3_head_object_unavailable"},
        )
        raise HTTPException(status_code=503, detail="File storage is unavailable")
    except Exception:
        logger.exception(
            "Unexpected S3 head_object failure",
            extra={"event": "s3_head_object_unexpected_failure"},
        )
        raise HTTPException(status_code=503, detail="File storage is unavailable")


def get_object_size(s3_key: str) -> int | None:
    try:
        response = _s3_client().head_object(Bucket=_bucket(), Key=s3_key)
        return response.get("ContentLength")
    except ClientError as e:
        code = _client_error_code(e)
        status_code = _client_error_status(e)
        if code in ("NoSuchKey", "404", "NotFound") or status_code == 404:
            return None
        logger.warning(
            "S3 get_object_size failed",
            extra={"event": "s3_get_object_size_failed"},
        )
        return None
    except Exception:
        logger.warning(
            "S3 get_object_size unavailable",
            extra={"event": "s3_get_object_size_unavailable"},
        )
        return None


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_resume(contents: bytes, user_id: str, resume_id: str, extension: str, content_type: str) -> str:

    key = f"resumes/{user_id}/{resume_id}{extension}"
    try:
        _s3_client().put_object(
            Bucket=_bucket(),
            Key=key,
            Body=contents,
            ContentType=content_type,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload resume to S3: {e.response['Error']['Message']}")
    return key


def upload_profile_picture(contents: bytes, user_id: str, extension: str, content_type: str) -> str:
   
    key = f"profile-images/{user_id}/profile{extension}"
    try:
        _s3_client().put_object(
            Bucket=_bucket(),
            Key=key,
            Body=contents,
            ContentType=content_type,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload profile picture to S3: {e.response['Error']['Message']}")
    return key


def upload_employer_profile_photo(contents: bytes, employer_id: str, extension: str, content_type: str) -> str:

    key = f"employer-profile-images/{employer_id}/profile{extension}"
    try:
        _s3_client().put_object(
            Bucket=_bucket(),
            Key=key,
            Body=contents,
            ContentType=content_type,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload employer profile photo to S3: {e.response['Error']['Message']}")
    return key


def upload_company_logo(contents: bytes, company_id: str, extension: str, content_type: str) -> str:

    key = f"company-logos/{company_id}/logo{extension}"
    try:
        _s3_client().put_object(
            Bucket=_bucket(),
            Key=key,
            Body=contents,
            ContentType=content_type,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload company logo to S3: {e.response['Error']['Message']}")
    return key


def upload_cover_picture(contents: bytes, user_id: str, extension: str, content_type: str) -> str:

    key = f"profile-images/{user_id}/cover{extension}"
    try:
        _s3_client().put_object(
            Bucket=_bucket(),
            Key=key,
            Body=contents,
            ContentType=content_type,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload cover picture to S3: {e.response['Error']['Message']}")
    return key


# ---------------------------------------------------------------------------
# Pre-signed URL (for download / display)
# ---------------------------------------------------------------------------

def generate_presigned_url(s3_key: str, expiry_seconds: int = 3600, attachment_filename: str | None = None) -> str:
    """Build a short-lived GET URL for an S3 object.

    When `attachment_filename` is given, the URL carries a
    Content-Disposition: attachment header (via S3's
    response-content-disposition override), so the browser downloads the
    file directly instead of rendering it inline. This matters for
    window.open(url, "_blank") call sites: without it, browsers open a
    real new tab to *display* the file (e.g. a PDF viewer) and steal
    focus, which meant any "downloaded successfully" toast on the
    original tab went unnoticed. With it, the browser triggers a save
    and the transient blank tab closes itself, leaving focus on the
    original page. Leave this unset for URLs meant to be viewed inline
    (e.g. the resume preview iframe, profile/cover photos).
    """
    params = {"Bucket": _bucket(), "Key": s3_key}
    if attachment_filename:
        safe_name = attachment_filename.replace('"', "")
        params["ResponseContentDisposition"] = f'attachment; filename="{safe_name}"'

    try:
        url = _s3_client().generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiry_seconds,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate download URL: {e.response['Error']['Message']}")
    return url


def generate_profile_image_presigned_url(s3_key: str, expiry_seconds: int = 300) -> str:
    try:
        return generate_presigned_url(s3_key, expiry_seconds=expiry_seconds)
    except HTTPException:
        logger.warning(
            "S3 profile image presign failed",
            extra={"event": "s3_profile_image_presign_failed"},
        )
        raise HTTPException(status_code=502, detail="File storage request failed")
    except (EndpointConnectionError, ConnectionError, BotoCoreError):
        logger.warning(
            "S3 profile image presign unavailable",
            extra={"event": "s3_profile_image_presign_unavailable"},
        )
        raise HTTPException(status_code=503, detail="File storage is unavailable")
    except Exception:
        logger.exception(
            "Unexpected S3 profile image presign failure",
            extra={"event": "s3_profile_image_presign_unexpected_failure"},
        )
        raise HTTPException(status_code=503, detail="File storage is unavailable")


# ---------------------------------------------------------------------------
# Fetch bytes (server-side proxy download)
# ---------------------------------------------------------------------------

def fetch_object_bytes(s3_key: str) -> tuple[bytes, str | None]:
    """Read an object's full bytes directly via the S3 API (server-to-server,
    using our AWS credentials) rather than handing the browser a presigned
    URL. Used for downloads that the frontend needs to `await` and detect
    failures on: browsers require the S3 bucket to have a CORS policy before
    JS (fetch/XHR) can read a cross-origin response, but our own backend
    talking to S3 via boto3 has no such restriction, and the frontend then
    downloads from our own API origin, which is already CORS-configured.

    Returns (content_bytes, content_type_or_None).
    """
    try:
        obj = _s3_client().get_object(Bucket=_bucket(), Key=s3_key)
    except ClientError as e:
        if _is_endpoint_connection_error(e):
            raise HTTPException(
                status_code=503,
                detail="Could not reach file storage. Please check your connection and try again.",
            )
        # API-level error: S3 was reachable and responded, but rejected the
        # request (bad key, no permission, etc.).
        code = _client_error_code(e)
        if code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="Resume file not found")
        raise HTTPException(status_code=500, detail="Failed to fetch resume from S3")
    except (EndpointConnectionError, ConnectionError, BotoCoreError) as e:
        # Connection-level failure: we couldn't even reach S3 (DNS failure,
        # network drop, timeout, S3 outage). Distinct from ClientError above
        # -- there was no HTTP response from AWS to inspect. Surface a clean
        # 503 instead of letting this bubble up as an unhandled 500.
        raise HTTPException(
            status_code=503,
            detail="Could not reach file storage. Please check your connection and try again.",
        )
    body = obj["Body"].read()
    content_type = obj.get("ContentType")
    return body, content_type


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_object(s3_key: str) -> None:
    
    try:
        _s3_client().delete_object(Bucket=_bucket(), Key=s3_key)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code not in ("NoSuchKey", "404"):
            raise HTTPException(status_code=500, detail=f"Failed to delete S3 object: {e.response['Error']['Message']}")
