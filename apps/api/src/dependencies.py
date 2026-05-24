import os

from google.cloud import firestore, storage

DATA_BUCKET = os.environ["DATA_BUCKET"]
MINERU_URL = os.environ["MINERU_URL"]
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ["PROJECT_ID"]
STAGE = os.environ["STAGE"]
FIRESTORE_DATABASE = f"td-{STAGE}"

storage_client = storage.Client()
bucket = storage_client.bucket(DATA_BUCKET)

firestore_client = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)
