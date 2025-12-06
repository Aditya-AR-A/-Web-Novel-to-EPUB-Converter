from __future__ import annotations
from datetime import datetime
from typing import Optional, List

from bson import ObjectId
from pydantic import BaseModel, Field


# ---------------------------------------
# Helper for ObjectId serialization
# ---------------------------------------
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return handler(core_schema)


# ---------------------------------------
# 1️⃣ Novel Metadata (Main)
# ---------------------------------------
class NovelMetadata(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    novel_key: Optional[str] = Field(
        default=None,
        description="Legacy slug for the novel. Prefer using the Mongo _id for new references.",
    )
    title: str
    author: Optional[str] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    source_url: Optional[str] = None
    cover_image: Optional[str] = None
    cover_image_storage_key: Optional[str] = None
    cover_image_mime: Optional[str] = None
    status: str = Field(default="ready")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        collection_name = "novels"


# ---------------------------------------
# 2️⃣ Novel Files Table (Actual Files)
# ---------------------------------------
class NovelLink(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    novel_id: PyObjectId = Field(..., description="FK to NovelMetadata._id")
    link_key: str = Field(..., description="Stable identifier for the link, derived from novel_id + file name")
    file_name: str
    file_url: Optional[str] = Field(default=None, description="Primary download URL")
    storage_key: Optional[str] = Field(default=None, description="Object key in remote storage")
    file_size: Optional[int] = Field(default=None, description="Size of the file in bytes")
    mime_type: str = Field(default="application/epub+zip")
    checksum: Optional[str] = None
    download_links: List[str] = Field(default_factory=list)
    novel_key: Optional[str] = Field(
        default=None,
        description="Legacy slug reference. Prefer novel_id in new code paths.",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        collection_name = "novel_links"
