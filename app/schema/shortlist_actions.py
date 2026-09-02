from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ShortlistCandidateRequest(BaseModel):
    # no payload needed now, but keeping as explicit schema for future extensions
    pass


class UnshortlistCandidateRequest(BaseModel):
    # no payload needed now, but keeping as explicit schema for future extensions
    pass


class BulkUnshortlistRequest(BaseModel):
    application_ids: list[str]

