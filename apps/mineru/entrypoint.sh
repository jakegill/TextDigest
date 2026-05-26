#!/bin/sh

set -e

mineru-openai-server \
    --host 127.0.0.1 \
    --port 30001 \
    --gpu-memory-utilization 0.9 &

exec uvicorn src.main:app --host 0.0.0.0 --port 30000
