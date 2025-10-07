from __future__ import annotations

import datetime as dt
from typing import List, Optional

from pydantic import AnyUrl, BaseModel


class EpubCreateResponse(BaseModel):
    id: int
    title: str
    author: Optional[str]
    source_url: AnyUrl
    storage_key: str
    storage_url: AnyUrl
    file_size: int
    status: str
    error_message: Optional[str]
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class EpubListResponse(BaseModel):
    epubs: List[EpubCreateResponse]


class DownloadManyRequest(BaseModel):
    keys: List[str]


class DownloadOneRequest(BaseModel):
    key: str
