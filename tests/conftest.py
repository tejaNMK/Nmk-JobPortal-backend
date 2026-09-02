import sys
import types
import os
import secrets
from types import SimpleNamespace


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test",
)
os.environ.setdefault("JWT_SECRET_KEY", secrets.token_urlsafe(64))
os.environ.setdefault("ALGORITHM", "HS256")

boto3_stub = types.ModuleType("boto3")
boto3_stub.client = lambda *args, **kwargs: SimpleNamespace()

botocore_stub = types.ModuleType("botocore")
botocore_exceptions_stub = types.ModuleType("botocore.exceptions")
botocore_exceptions_stub.ClientError = Exception
botocore_exceptions_stub.BotoCoreError = Exception


class EndpointConnectionError(Exception):
    def __init__(self, endpoint_url=None):
        super().__init__(f"Could not connect to the endpoint URL: {endpoint_url}")
        self.endpoint_url = endpoint_url


botocore_exceptions_stub.EndpointConnectionError = EndpointConnectionError

sys.modules.setdefault("boto3", boto3_stub)
sys.modules.setdefault("botocore", botocore_stub)
sys.modules.setdefault("botocore.exceptions", botocore_exceptions_stub)
