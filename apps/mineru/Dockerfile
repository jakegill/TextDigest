# Upstream pairs MinerU 3.4 with vLLM 0.21.0 (CUDA 13.0) — matches the
# nvidia-rtx-pro-6000 Cloud Run node (compute capability 12.x, CUDA 13).
FROM vllm/vllm-openai:v0.21.0

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# libgl1: opencv; Noto fonts: CJK glyph rendering in extracted images
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        "huggingface_hub" \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "python-multipart>=0.0.20" \
        "google-auth>=2.35.0" \
        "google-cloud-storage>=2.18.0"

RUN python3 -c "from huggingface_hub import snapshot_download; snapshot_download('opendatalab/MinerU2.5-Pro-2605-1.2B', local_dir='/models/MinerU2.5-Pro-2605-1.2B')"

# MINERU_REF is pinned in infra/gpu.ts. A pip install from a moving branch ref
# never busts the docker layer cache, so fork updates silently don't ship.
ARG MINERU_REF=master
RUN pip install --no-cache-dir \
        "mineru[pipeline] @ git+https://github.com/jakegill/MinerU.git@${MINERU_REF}"

# -m pipeline fetches the PP-OCRv6-era pipeline models (doclayout v2, formula,
# paddle ocr, table, structure) and writes models-dir.pipeline into mineru.json.
RUN mineru-models-download -s huggingface -m pipeline

# models-dir is a dict {pipeline: ..., vlm: ...} in 3.4; the download step
# wrote the pipeline key, we add the vlm key pointing at the baked weights.
RUN python3 -c "import json; p='/root/mineru.json'; d=json.load(open(p)); d['models-dir']['vlm']='/models/MinerU2.5-Pro-2605-1.2B'; json.dump(d, open(p,'w'))"

RUN echo "=== /root/mineru.json at end of build ===" && cat /root/mineru.json && echo "=== end ==="

# mineru.json lives at /root/mineru.json (written by `mineru-models-download`
# above). MinerU resolves the config path via `~/mineru.json` which expands
# through HOME; Cloud Run doesn't guarantee HOME is set on the container init
# process, so pin HOME and also pass the absolute path explicitly.
ENV HOME=/root
ENV MINERU_TOOLS_CONFIG_JSON=/root/mineru.json
ENV MINERU_MODEL_SOURCE=local

COPY src ./src

EXPOSE 30000

ENTRYPOINT []
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "30000", "--proxy-headers", "--forwarded-allow-ips", "*"]
