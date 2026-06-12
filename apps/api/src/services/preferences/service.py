from ...dependencies import firestore_client
from ...models.preferences import Preferences


def _doc(uid: str):
    return (
        firestore_client.collection("users")
        .document(uid)
        .collection("preferences")
        .document("default")
    )


def get_for_user(uid: str) -> Preferences:
    snap = _doc(uid).get()
    return Preferences(**(snap.to_dict() or {}))


def set_for_user(uid: str, prefs: Preferences) -> None:
    _doc(uid).set(prefs.model_dump(), merge=True)
