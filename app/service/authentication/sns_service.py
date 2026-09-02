import logging
import os
import boto3
from botocore.exceptions import ClientError

from app.config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
)

logger = logging.getLogger(__name__)

# Optional: pre-registered 6-character alphabetic Sender ID (required for India).
_SENDER_ID: str | None = os.getenv("SNS_SENDER_ID")


class SNSService:
    """
    AWS SNS SMS Service.

    Designed for OTP delivery.  Every message is published as "Transactional"
    so it bypasses DND filters and is given higher delivery priority by carriers.
    """

    _client = None

    @classmethod
    def _get_client(cls):
        """
        Lazy-init the boto3 SNS client.

        boto3 clients are thread-safe for individual API calls (publish).
        The assignment `cls._client = ...` is not atomic in CPython with the GIL
        but the worst case is creating two clients on the first concurrent request –
        both are equivalent, so this is safe in practice.
        """
        if cls._client is None:
            cls._client = boto3.client(
                "sns",
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            )
        return cls._client

    @classmethod
    async def send_sms(
        cls,
        mobile_number: str,
        message: str,
    ) -> dict:
        """
        Publish an SMS via AWS SNS.

        Args:
            mobile_number: E.164 formatted number, e.g. "+919876543210"
            message:       The SMS body (keep ≤ 160 chars to avoid concatenation).

        Returns:
            The raw SNS Publish response dict (contains MessageId).

        Raises:
            ClientError: For boto3/SNS errors (auth failure, invalid number, etc.)
            Exception:   For unexpected failures.

        NOTE: An HTTP 200 response from SNS means the message was *accepted*, not
        that it was *delivered*.
        """
        # Build MessageAttributes: Transactional type ensures delivery during DND
        # and higher carrier priority over Promotional.
        message_attributes: dict = {
            "AWS.SNS.SMS.SMSType": {
                "DataType": "String",
                "StringValue": "Transactional",
            }
        }

        # Add Sender ID if configured.  Mandatory for India (TRAI DLT).
        if _SENDER_ID:
            message_attributes["AWS.SNS.SMS.SenderID"] = {
                "DataType": "String",
                "StringValue": _SENDER_ID,
            }

        try:
            response = cls._get_client().publish(
                PhoneNumber=mobile_number,
                Message=message,
                MessageAttributes=message_attributes,
            )
            logger.info(
                "SNS SMS accepted",
                extra={
                    "event": "sns_sms_accepted",
                    "provider_message_id": response.get("MessageId"),
                    "provider_status_code": response.get(
                        "ResponseMetadata",
                        {},
                    ).get("HTTPStatusCode"),
                },
            )
            return response

        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "SNS ClientError",
                extra={
                    "event": "sns_client_error",
                    "provider_error_code": error_code,
                },
            )
            # Re-raise so the caller can handle or surface a 500.
            raise

        except Exception as exc:
            logger.exception(
                "SNS unexpected failure",
                extra={
                    "event": "sns_unexpected_failure",
                    "error_type": exc.__class__.__name__,
                },
            )
            raise
