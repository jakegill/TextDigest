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


class Title(TitleMetadata):
    markdownUrl: str
    toc: list[TocEntry]
    tocSource: str
