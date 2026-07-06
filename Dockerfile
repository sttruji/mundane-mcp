FROM python:3.13-slim

# Unbuffered stdout is not optional here: this server speaks MCP over
# stdio, and Python's default block-buffering on a piped stdout can stall
# the JSON-RPC framing the calling agent is waiting on.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/mundane-mcp

RUN addgroup --system app && adduser --system --ingroup app appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

USER appuser

# No EXPOSE, no HEALTHCHECK: this is a one-process-per-agent stdio adapter,
# not a network service. Run it with `docker run -i` so stdin stays open --
# the calling MCP client owns the process lifecycle, not an orchestrator.
ENTRYPOINT ["mundane-mcp"]
