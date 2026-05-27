FROM vllm/vllm-openai:v0.11.2

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
        "mineru[pipeline] @ git+https://github.com/jakegill/MinerU.git@master" \
        "huggingface_hub" \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "python-multipart>=0.0.20" \
        "google-auth>=2.35.0" \
        "google-cloud-storage>=2.18.0"

RUN python3 -c "from huggingface_hub import snapshot_download; snapshot_download('opendatalab/MinerU2.5-Pro-2605-1.2B', local_dir='/models/MinerU2.5-Pro-2605-1.2B')"

RUN mineru-models-download -s huggingface -m pipeline

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
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "30000"]
