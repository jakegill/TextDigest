from google.cloud.firestore import SERVER_TIMESTAMP

from ..dependencies import firestore_client


def write_title(
    uid: str,
    title_id: str,
    *,
    title: str,
    author: str,
    source_key: str,
    parsed_md_key: str,
    cover_key: str,
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
            "createdAt": SERVER_TIMESTAMP,
        }
    )
