FROM vllm/vllm-openai:v0.11.2

ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir "mineru[core]==3.1.15" "huggingface_hub[cli]"

RUN huggingface-cli download opendatalab/MinerU2.5-Pro-2605-1.2B \
      --local-dir /models/MinerU2.5-Pro-2605-1.2B

# mineru reads ~/mineru.json — `MINERU_MODEL_PATH` is NOT a recognized var.
RUN printf '%s\n' '{"models-dir":{"vlm":"/models/MinerU2.5-Pro-2605-1.2B"}}' \
    > /root/mineru.json

ENV MINERU_MODEL_SOURCE=local

EXPOSE 30000

ENTRYPOINT []
CMD ["mineru-openai-server", "--host", "0.0.0.0", "--port", "30000", "--gpu-memory-utilization", "0.9"]
