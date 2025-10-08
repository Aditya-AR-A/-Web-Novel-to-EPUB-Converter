from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from bson import ObjectId


# ---------------------------------------
# Helper for ObjectId serialization
# ---------------------------------------
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
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
    novel_key: str = Field(..., description="Primary key for the novel (PK1)")
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
# 2️⃣ Novel Links Table (EPUB Variants)
# ---------------------------------------
class NovelLinks(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    novel_key: str = Field(..., description="FK from NovelMetadata")
    link_key: str = Field(..., description="Unique key for this variant (PK2)")
    file_type: str = Field(default="epub", description="epub / mobi / pdf")
    part_name: Optional[str] = None
    download_links: List[str] = Field(default_factory=list)
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        collection_name = "novel_links"


# ---------------------------------------
# 3️⃣ Novel Files Table (Actual Files)
# ---------------------------------------
class NovelFile(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    link_key: str = Field(..., description="FK from NovelLinks.link_key")
    novel_key: str = Field(..., description="FK from NovelMetadata.novel_key")
    file_name: str
    file_url: str
    storage_key: Optional[str] = Field(default=None, description="Object key in remote storage")
    local_path: Optional[str] = Field(default=None, description="Absolute path to local file copy")
    file_size: int
    mime_type: str = Field(default="application/epub+zip")
    checksum: Optional[str] = None  # optional integrity hash
    file_data: Optional[bytes] = Field(default=None, description="Binary EPUB contents")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}
        collection_name = "novel_files"
