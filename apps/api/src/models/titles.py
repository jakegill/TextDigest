from datetime import datetime

from pydantic import BaseModel


class CoverMetadata(BaseModel):
    title: str
    author: str


class TocEntry(BaseModel):
    title: str
    level: int
    pdfPage: int
    anchor: str


class SkeletonEntry(BaseModel):
    title: str
    level: int
    pdfPage: int
    anchor: str


class DocTocEntry(BaseModel):
    title: str
    statedPage: int | None
    level: int


class TitleMetadata(BaseModel):
    titleId: str
    title: str
    author: str
    coverUrl: str
    createdAt: datetime
    isProcessing: bool
    processingError: str | None = None
    lastViewed: datetime | None = None
    pageNumber: int | None = None


class Title(TitleMetadata):
    # markdownUrl, toc, tocSource are populated once the parse + toc stages
    # complete. While isProcessing is true (or if processing failed), they may
    # still be null / empty.
    markdownUrl: str | None = None
    toc: list[TocEntry] = []
    tocSource: str | None = None
