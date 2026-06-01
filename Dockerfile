FROM neunerlei/python-nginx:3.14 AS base

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


FROM base AS development

ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=$USER_UID

COPY --from=astral/uv:latest /uv /uvx /usr/local/bin/

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

COPY pyproject.toml readme.md uv.lock .
RUN uv sync --all-groups

COPY . .

CMD ["uv", "run", "--no-sync", "pytest", "-vvv", "-x"]


FROM development AS requirements

USER root

WORKDIR /build-requirements
COPY pyproject.toml uv.lock ./
RUN uv export --no-dev --no-hashes --no-emit-project -o requirements.txt > requirements.txt


FROM base AS deployment 

RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-17=17.* \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN cat > /etc/postgresql/17/main/pg_hba.conf << 'EOF'
local   all   all   trust
host    all   all   127.0.0.1/32   trust
host    all   all   ::1/128        trust
EOF

RUN pg_ctlcluster 17 main start && \
    su - postgres -c "createuser -s prefect" && \
    su - postgres -c "createdb -O prefect prefect" && \
    pg_ctlcluster 17 main stop

COPY --from=requirements /build-requirements/requirements.txt /var/www/html/hawki-toolkit-file-converter-requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt -r /var/www/html/hawki-toolkit-file-converter-requirements.txt && rm /var/www/html/hawki-toolkit-file-converter-requirements.txt

COPY main.py task.py ./

COPY utils/ utils/

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost/health || exit 1


FROM deployment

RUN mkdir -p /var/www/.prefect /task-storage /container/custom/supervisor/conf.d /container/custom/entrypoint && \
    chown www-data:www-data /var/www/.prefect /task-storage && \
    mkdir -p /var/run/postgresql && chown postgres:postgres /var/run/postgresql

COPY docker/custom/supervisor/conf.d/*.conf /container/templates/supervisor/conf.d/
COPY docker/custom/nginx/*.conf /container/custom/nginx/
COPY docker/custom/entrypoint/*.sh /container/custom/entrypoint/
COPY docker/scripts/*.sh /container/bin/
RUN chmod +x /container/bin/*.sh

ENV PYTHON_APP_MODULE="main:app"
ENV GUNICORN_WORKER_CLASS="uvicorn.workers.UvicornWorker"

ENV POSTGRES_ENABLED=true
ENV PREFECT_HOME="/var/www/.prefect"
ENV PREFECT_SERVER_API_HOST="0.0.0.0"
ENV PREFECT_API_URL="http://127.0.0.1:4200/api"
ENV PREFECT_API_DATABASE_CONNECTION_URL="postgresql+asyncpg://prefect@127.0.0.1:5432/prefect"
ENV PREFECT_LOCAL_STORAGE_PATH="/task-storage"
ENV PREFECT_RESULTS_PERSIST_BY_DEFAULT=true
ENV PREFECT_LOGGING_LOG_PRINTS="true"
ENV PREFECT_LOGGING_TO_API_WHEN_MISSING_FLOW="ignore"
ENV PREFECT_UI_SERVE_BASE="/prefect/"
ENV PREFECT_UI_API_URL="/prefect/api"

ENV WORKER_COUNT="3"
ENV HOME=/tmp
ENV RUST_LOG=info


