from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.session import Base


class EpubMetadata(Base):
    __tablename__ = "epubs"

    id: int = Column(Integer, primary_key=True, index=True)
    title: str = Column(String(255), nullable=False)
    author: Optional[str] = Column(String(255), nullable=True)
    source_url: str = Column(Text, nullable=False)
    s3_key: str = Column(String(512), nullable=False, unique=True, index=True)
    s3_url: str = Column(Text, nullable=False)
    file_size: int = Column(Integer, nullable=False)
    status: str = Column(String(50), nullable=False, default="ready")
    error_message: Optional[str] = Column(Text, nullable=True)
    created_at: dt.datetime = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at: dt.datetime = Column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )
