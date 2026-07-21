# Container image for the Reddit Growth MCP server (Glama / any container host).
#
# The server speaks JSON-RPC over stdio, so nothing but the protocol may be
# written to stdout — all logging goes to stderr (see src/server.py).
FROM python:3.12-slim

# uv: fast, reproducible installs (matches the project's tooling).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY . .

# Install the project; exposes the `reddit-growth-mcp` console script.
RUN uv pip install --system --no-cache .

# Reddit credentials are OPTIONAL — the server boots credential-free from the
# Arctic Shift archive. Pass them at runtime to unlock live rule checks:
#   docker run -i -e REDDIT_CLIENT_ID=... -e REDDIT_CLIENT_SECRET=... <image>
ENTRYPOINT ["reddit-growth-mcp"]
