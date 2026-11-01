# Raon-1 mini preview (KRAFTON, Apache 2.0) on llama.cpp's OpenAI-compatible server.
# Built from KRAFTON's llama.cpp branch at a fixed commit: upstream support for the model is pending.
# Portable CPU build: every CPU variant (SSE4 … AVX2 … AVX-512) is built as its own backend library and llama.cpp
# loads the best one the machine has when it starts, so the image runs on another server's CPU without losing speed.
# The GGUF is not in the image: it sits in ../models or /data/models (see DOCKER.md) and is mounted read-only.
# ubuntu:24.04 pinned by digest (2026-10-27) so a rebuild gets the same base.
FROM ubuntu:24.04@sha256:24737cef17f4e22b1977df7d9a05e77c4e28b7da5b8911f8d8ccda136bf3573c AS build
ARG LLAMA_REPO=https://github.com/krafton-ai/llama.cpp
ARG LLAMA_REF=fb895662d25868756a19253ca5e0688f99b18994
RUN apt-get update \
 && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates libssl-dev \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --filter=blob:none "$LLAMA_REPO" /src && git -C /src checkout "$LLAMA_REF"
RUN cmake -S /src -B /src/build -DCMAKE_BUILD_TYPE=Release \
          -DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON -DLLAMA_CURL=OFF \
          -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
 && cmake --build /src/build --config Release -j"$(nproc)"

FROM ubuntu:24.04@sha256:24737cef17f4e22b1977df7d9a05e77c4e28b7da5b8911f8d8ccda136bf3573c
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libssl3 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/bin/ /opt/llama/
ENV LD_LIBRARY_PATH=/opt/llama
RUN useradd --create-home --uid 10002 llm
USER llm
EXPOSE 8000
# loading 20 GB from disk takes a while on the first start
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 CMD curl -fs http://127.0.0.1:8000/health || exit 1
ENTRYPOINT ["/opt/llama/llama-server"]
