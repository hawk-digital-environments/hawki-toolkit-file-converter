FROM neunerlei/python-nginx:3.14 as base

LABEL org.opencontainers.image.authors="HAWKI Team <ki@hawk.de>"
LABEL org.opencontainers.image.description="The HAWKI file conversion service (dev)"

ENV PYTHONUNBUFFERED=1

RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-osd \
        tesseract-ocr-spa \
        tesseract-ocr-fra \
        tesseract-ocr-deu \
        tesseract-ocr-ita \
        tesseract-ocr-por \
        tesseract-ocr-chi-sim \
        tesseract-ocr-chi-tra \
        tesseract-ocr-jpn \
        tesseract-ocr-ara \
        tesseract-ocr-rus \
        tesseract-ocr-hin \
        fontconfig \
        libssl3 \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*


FROM base as development

ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=$USER_UID

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN pip3 install pipx && python3 -m pipx ensurepath

# Install sudo and create user
RUN apt-get update \
    && apt-get install -y sudo \
    && groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

USER $USERNAME


FROM development AS test

USER root
WORKDIR /workspace

COPY . .
COPY pyproject.toml uv.lock .
RUN uv sync --all-groups

CMD ["uv", "run", "pytest", "-vvv", "-x"]


FROM development as requirements

USER root

WORKDIR /build-requirements
COPY pyproject.toml uv.lock .
RUN uv export --no-dev --no-hashes --no-emit-project -o requirements.txt > requirements.txt


FROM base as deployment 

COPY --from=requirements /build-requirements/requirements.txt /var/www/html/hawki-toolkit-file-converter-requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt -r /var/www/html/hawki-toolkit-file-converter-requirements.txt && rm /var/www/html/hawki-toolkit-file-converter-requirements.txt

COPY main.py .

COPY utils/ utils/

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost/health || exit 1


FROM deployment as test

COPY ./tests ./tests
COPY pytest.ini .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    pytest \
    httpx

FROM deployment

ENV PYTHON_APP_MODULE="main:app"
ENV GUNICORN_WORKER_CLASS="uvicorn.workers.UvicornWorker"
ENV HOME=/tmp
# See: https://github.com/kreuzberg-dev/kreuzberg/blob/2e9fdd4fe342122225c0a7ff29e1da11bd84499e/crates/kreuzberg-cli/README.md?plain=1#L827
ENV RUST_LOG=info
