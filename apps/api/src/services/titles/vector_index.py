import asyncio
from dataclasses import dataclass
from typing import Callable

from google import genai
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from google.genai import types
from llama_index.core.node_parser import SentenceSplitter

from ...dependencies import PROJECT_ID, firestore_client
from .constants import GEMINI_EMBEDDING_001

EMBED_DIM = 768
VERTEX_LOCATION = "us-central1"
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
EMBED_BATCH = 16
WRITE_BATCH = 400

_genai = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)
_splitter = SentenceSplitter(
    chunk_size=CHUNK_SIZE_TOKENS, chunk_overlap=CHUNK_OVERLAP_TOKENS
)


@dataclass(slots=True)
class Chunk:
    text: str
    page_idx: int
    block_idx: int
    embedding: list[float] | None = None


def _flatten_text_blocks(content_list: list[dict]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for i, b in enumerate(content_list):
        if b.get("type") not in ("text", "title"):
            continue
        t = (b.get("text") or "").strip()
        if not t:
            continue
        out.append((i, int(b.get("page_idx", 0)), t))
    return out


def chunk(content_list: list[dict]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for block_idx, page_idx, text in _flatten_text_blocks(content_list):
        for piece in _splitter.split_text(text):
            chunks.append(Chunk(text=piece, page_idx=page_idx, block_idx=block_idx))
    return chunks


def embed(
    chunks: list[Chunk],
    on_progress: Callable[[float], None] | None = None,
) -> None:
    cfg = types.EmbedContentConfig(
        task_type="RETRIEVAL_DOCUMENT", output_dimensionality=EMBED_DIM
    )
    total = len(chunks)
    for i in range(0, total, EMBED_BATCH):
        batch = chunks[i : i + EMBED_BATCH]
        resp = _genai.models.embed_content(
            model=GEMINI_EMBEDDING_001, contents=[c.text for c in batch], config=cfg  # type: ignore[arg-type]
        )
        for c, e in zip(batch, resp.embeddings):  # type: ignore[arg-type]
            c.embedding = list(e.values)  # type: ignore[arg-type]
        if on_progress and total:
            on_progress(min(1.0, (i + len(batch)) / total))


def persist(uid: str, title_id: str, chunks: list[Chunk]) -> None:
    coll = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
        .collection("chunks")
    )
    batch = firestore_client.batch()
    for i, c in enumerate(chunks):
        ref = coll.document(f"{i:05d}")
        batch.set(
            ref,
            {
                "text": c.text,
                "pageIdx": c.page_idx,
                "blockIdx": c.block_idx,
                "embedding": Vector(c.embedding or []),
            },
        )
        if (i + 1) % WRITE_BATCH == 0:
            batch.commit()
            batch = firestore_client.batch()
    batch.commit()


async def build(
    uid: str,
    title_id: str,
    content_list: list[dict],
    on_progress: Callable[[float], None] | None = None,
) -> int:
    chunks = chunk(content_list)
    await asyncio.to_thread(embed, chunks, on_progress)
    await asyncio.to_thread(persist, uid, title_id, chunks)
    return len(chunks)


def query(uid: str, title_id: str, q: str, k: int = 5) -> list[dict]:
    cfg = types.EmbedContentConfig(
        task_type="RETRIEVAL_QUERY", output_dimensionality=EMBED_DIM
    )
    resp = _genai.models.embed_content(
        model=GEMINI_EMBEDDING_001, contents=[q], config=cfg  # type: ignore[arg-type]
    )
    qv = list(resp.embeddings[0].values)  # type: ignore[index,arg-type]
    coll = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
        .collection("chunks")
    )
    return [
        doc.to_dict()
        for doc in coll.find_nearest(
            vector_field="embedding",
            query_vector=Vector(qv),
            distance_measure=DistanceMeasure.COSINE,
            limit=k,
        ).stream()
    ]
