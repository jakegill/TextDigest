import asyncio
import json
import logging

from google.cloud import tasks_v2

from ...dependencies import (
    API_SA_EMAIL,
    PROJECT_ID,
    REGION,
    STAGE,
)

logger = logging.getLogger("uvicorn.error")

QUEUE_NAME = f"td-{STAGE}-title-processing"

# Personal dev stages (anything other than staging/prod) skip Cloud Tasks
# and run the worker callback in-process. The api Cloud Run service IS the
# worker locally, so there's nothing to enqueue against.
_USE_QUEUE = STAGE in ("staging", "prod")

_client: tasks_v2.CloudTasksClient | None = (
    tasks_v2.CloudTasksClient() if _USE_QUEUE else None
)
_queue_path: str | None = (
    _client.queue_path(PROJECT_ID, REGION, QUEUE_NAME) if _client else None
)


async def enqueue_process(
    api_base_url: str,
    uid: str,
    task_id: str,
    source_key: str,
    filename: str | None,
) -> None:
    """`api_base_url` is the URL the api was reached at (derived from request
    context). Cloud Tasks dispatches to {api_base_url}/titles/process; the
    OIDC token's audience is the same URL so the receiver can validate it
    against its own request URL."""
    process_url = f"{api_base_url.rstrip('/')}/titles/process"
    body = json.dumps(
        {
            "uid": uid,
            "taskId": task_id,
            "sourceKey": source_key,
            "filename": filename,
        }
    ).encode("utf-8")

    if _USE_QUEUE and _client and _queue_path:
        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=process_url,
                headers={"Content-Type": "application/json"},
                body=body,
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=API_SA_EMAIL,
                    audience=process_url,
                ),
            ),
        )
        await asyncio.to_thread(
            _client.create_task, parent=_queue_path, task=task
        )
        logger.info("[%s] enqueued task to %s -> %s", task_id, QUEUE_NAME, process_url)
        return

    # Local dev: skip the queue, run the worker callback in-process.
    # Imported lazily to avoid a circular import (flows -> cloud_tasks -> flows).
    from . import flows

    logger.info("[%s] dev mode: running stage_process in-process", task_id)
    asyncio.create_task(
        flows.stage_process(uid, task_id, source_key, filename),
        name=f"stage_process:{task_id}",
    )
