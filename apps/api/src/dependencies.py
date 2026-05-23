import os

from google.cloud import storage

DATA_BUCKET = os.environ["DATA_BUCKET"]
MINERU_URL = os.environ["MINERU_URL"]

storage_client = storage.Client()
bucket = storage_client.bucket(DATA_BUCKET)
