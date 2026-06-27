# API gateway image (light — ROS lives in the sandbox image, not here).
# Needs the docker CLI to spawn per-submission sandbox containers.
FROM python:3.11-slim

# We only need the docker CLIENT here (it talks to the host daemon via the
# mounted socket). On Debian trixie the client is the `docker-cli` package;
# on older releases it shipped inside `docker.io`. Try the client-only package
# first, fall back to docker.io, then verify the `docker` binary exists.
RUN apt-get update && \
    ( apt-get install -y --no-install-recommends docker-cli \
      || apt-get install -y --no-install-recommends docker.io ) && \
    rm -rf /var/lib/apt/lists/* && \
    docker --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
