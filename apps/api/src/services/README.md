# services/

Domain-driven layout. Each subdirectory owns one bounded context of the
app.

## What's in a domain folder

Every domain uses the same set of filenames. Same name = same role across
every domain. When you're adding a new feature, the matching file is obvious.

- **`service.py`** — basic read/write operations on this domain's entity.
  List, get, delete. Uses Firestore and GCS directly via the clients
  imported from `src/dependencies.py`.

- **`flows.py`** — multi-step operations that coordinate several files at
  once. The ingest pipeline (upload → render cover → extract metadata →
  parse → vectorize → write) lives here. If a function calls more than two
  sibling files, it belongs in `flows.py`.

- **`constants.py`** — names, magic numbers, model IDs. No logic.

- **One file per external integration.** Each external system or library
  we lean on gets a file named after it: `mineru.py`, `vector_index.py`,
  `cover.py` (pypdfium2 + Gemini). The filename tells you what's inside.

That's the whole vocabulary. If a new file doesn't fit one of these,
either it belongs in a different domain or the vocabulary needs to grow
deliberately — not by drift.

## Inline, don't generalize

GCP SDK calls sit inline in the file that needs them. There is no shared
infrastructure layer.

If the same one-liner shows up several times in a single file, extract a
private helper _in that file_ (`_upload_json()`, etc.). Only promote a
helper up the tree once a second domain provably needs it.

## Adding a new domain

1. Create `services/<domain>/` with an empty `__init__.py`.
2. Add `service.py` for basic operations.
3. Add `flows.py` if you have a multi-step operation.
4. Add one file per external integration as needed.
5. Add `routers/<domain>.py` that imports from `services.<domain>.service`
   (and `.flows` if applicable).

Filenames should name a _feature_ or a _specific external integration_ —
never a generic technical layer.
