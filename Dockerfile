FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir hatchling

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8000

ENTRYPOINT ["ynab-mcp-server"]
