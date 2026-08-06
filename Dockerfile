# easyfbt runtime image.
#
# Supply-chain posture:
# - Base image pinned by digest (python:3.12-slim via the AWS mirror of the
#   Docker official images; the mirror also avoids Docker Hub pull limits).
# - Python dependencies installed only with pip --require-hashes.
# - ML models fetched at build time from versioned URLs with sha256
#   verification; the container makes no implicit downloads at runtime.
# - Runs as a non-root user; no build tooling in the final environment
#   (the package is used from source via PYTHONPATH).
FROM public.ecr.aws/docker/library/python:3.12-slim@sha256:646fb0bca3dd3ea1bcc6feb72c17ed16eed6e10cffc732fcc1478bd3e7f02d7b

# Native libraries needed by opencv-python (GUI-less usage still links them).
# apt packages are integrity-checked by Debian's signed repositories.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/runtime.lock requirements/
RUN pip install --no-cache-dir --require-hashes -r requirements/runtime.lock

COPY tools/fetch_models.py tools/
RUN python tools/fetch_models.py --dest /app/models

COPY LICENSE README.md pyproject.toml ./
COPY src/ src/
COPY config.container.toml /config/config.toml
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

RUN useradd --system --uid 10001 --no-create-home easyfbt
USER easyfbt

# Debug view (MJPEG/JSON); publish with e.g. -p 127.0.0.1:8089:8089.
EXPOSE 8089

ENTRYPOINT ["python", "-m", "easyfbt"]
# Mount your own config over /config/config.toml to customise.
CMD ["--config", "/config/config.toml", "--no-window"]
