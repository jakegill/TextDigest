from google.cloud.firestore import SERVER_TIMESTAMP

from ..dependencies import firestore_client
from .toc import TocEntry


def write_title(
    uid: str,
    title_id: str,
    *,
    title: str,
    author: str,
    source_key: str,
    parsed_md_key: str,
    cover_key: str,
    content_list_key: str,
    toc_key: str,
    toc: list[TocEntry],
    toc_source: str,
) -> None:
    firestore_client.collection("users").document(uid).collection("titles").document(
        title_id
    ).set(
        {
            "title": title,
            "author": author,
            "sourceKey": source_key,
            "parsedMdKey": parsed_md_key,
            "coverKey": cover_key,
            "contentListKey": content_list_key,
            "tocKey": toc_key,
            "toc": [e.model_dump() for e in toc],
            "tocSource": toc_source,
            "createdAt": SERVER_TIMESTAMP,
        }
    )
