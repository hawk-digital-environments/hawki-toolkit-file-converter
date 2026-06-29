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


# Pull the temporal auto-setup image at build time to extract schema files.
# The version must match TEMPORAL_SERVER_VERSION below.
FROM temporalio/auto-setup:1.29.7 AS temporal-auto-setup


FROM base AS deployment 

ARG TARGETARCH
ARG TEMPORAL_SERVER_VERSION=1.29.7
ARG TEMPORAL_CLI_VERSION=1.7.2
ARG TEMPORAL_UI_VERSION=2.51.0

RUN case "${TARGETARCH}" in amd64|arm64) ;; *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; esac
ENV TEMPORAL_RELEASE_ARCH=${TARGETARCH}

RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-17=17.* \
        curl \
        ca-certificates \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN cat > /etc/postgresql/17/main/pg_hba.conf << 'EOF'
local   all   all   trust
host    all   all   127.0.0.1/32   trust
host    all   all   ::1/128        trust
EOF

# Install Temporal server, SQL tool, CLI, and UI binaries from upstream releases.
RUN curl -fsSL "https://github.com/temporalio/temporal/releases/download/v${TEMPORAL_SERVER_VERSION}/temporal_${TEMPORAL_SERVER_VERSION}_linux_${TEMPORAL_RELEASE_ARCH}.tar.gz" \
        -o /tmp/temporal-server.tar.gz && \
    tar -xzf /tmp/temporal-server.tar.gz -C /usr/local/bin \
        temporal-server temporal-sql-tool && \
    rm /tmp/temporal-server.tar.gz && \
    chmod +x /usr/local/bin/temporal-server /usr/local/bin/temporal-sql-tool

RUN curl -fsSL "https://github.com/temporalio/cli/releases/download/v${TEMPORAL_CLI_VERSION}/temporal_cli_${TEMPORAL_CLI_VERSION}_linux_${TEMPORAL_RELEASE_ARCH}.tar.gz" \
        -o /tmp/temporal-cli.tar.gz && \
    tar -xzf /tmp/temporal-cli.tar.gz -C /usr/local/bin temporal && \
    rm /tmp/temporal-cli.tar.gz && \
    chmod +x /usr/local/bin/temporal

RUN curl -fsSL "https://github.com/temporalio/ui-server/releases/download/v${TEMPORAL_UI_VERSION}/ui-server_${TEMPORAL_UI_VERSION}_linux_${TEMPORAL_RELEASE_ARCH}.tar.gz" \
        -o /tmp/ui-server.tar.gz && \
    tar -xzf /tmp/ui-server.tar.gz -C /tmp ui-server && \
    mv /tmp/ui-server /usr/local/bin/temporal-ui-server && \
    rm -rf /tmp/ui-server.tar.gz && \
    chmod +x /usr/local/bin/temporal-ui-server

# Schema files are reused from the auto-setup image (the source repo does not ship them in the binary release)
COPY --from=temporal-auto-setup /etc/temporal/schema /etc/temporal/schema

COPY docker/custom/temporal/config/docker.yaml /etc/temporal/config/docker.yaml
COPY docker/custom/temporal/config/docker-ui.yaml /etc/temporal/config/docker-ui.yaml

COPY --from=requirements /build-requirements/requirements.txt /var/www/html/hawki-toolkit-file-converter-requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt -r /var/www/html/hawki-toolkit-file-converter-requirements.txt && rm /var/www/html/hawki-toolkit-file-converter-requirements.txt

COPY main.py task.py models.py VERSION.md ./

COPY utils/ utils/

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost/health || exit 1


FROM deployment

RUN mkdir -p /task-storage /etc/temporal/config /container/custom/supervisor/conf.d /container/custom/entrypoint && \
    chown www-data:www-data /task-storage && \
    mkdir -p /var/run/postgresql && chown postgres:postgres /var/run/postgresql

COPY docker/custom/supervisor/conf.d/*.conf /container/templates/supervisor/conf.d/
COPY docker/custom/nginx/*.conf /container/custom/nginx/
COPY docker/custom/entrypoint/*.sh /container/custom/entrypoint/
COPY docker/scripts/*.sh /container/bin/
RUN chmod +x /container/bin/*.sh

ENV PYTHON_APP_MODULE="main:app"
ENV GUNICORN_WORKER_CLASS="uvicorn.workers.UvicornWorker"

ENV POSTGRES_ENABLED=true
ENV TEMPORAL_HOME="/etc/temporal"
ENV TEMPORAL_HOST="127.0.0.1:7233"
ENV TEMPORAL_NAMESPACE="default"
ENV TEMPORAL_TASK_QUEUE="file-converter"
ENV TEMPORAL_ADDRESS="127.0.0.1:7233"
ENV POSTGRES_SEEDS="127.0.0.1"
ENV POSTGRES_USER="temporal"
ENV POSTGRES_PWD=""
ENV DBNAME="temporal"
ENV VISIBILITY_DBNAME="temporal_visibility"
ENV DB_PORT="5432"
ENV DEFAULT_NAMESPACE="default"
ENV DEFAULT_NAMESPACE_RETENTION="24h"
ENV ZIP_TTL_HOURS="24"
ENV CALLBACK_TIMEOUT_SECONDS="30"
ENV ACTIVITY_START_TO_CLOSE_TIMEOUT_MINUTES="60"
ENV TEMPORAL_MAX_CONCURRENT=5
ENV TEMPORAL_MAX_CACHED_WORKFLOWS=0

ENV HOME=/tmp
ENV RUST_LOG=info

