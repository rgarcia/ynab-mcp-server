# Development

## Local Setup

Clone the repository and install its locked dependencies:

```bash
git clone https://github.com/rgarcia/ynab-mcp-server.git
cd ynab-mcp-server
uv sync --locked
```

Run the development checkout with:

```bash
YNAB_API_TOKEN=your-token-here uv run ynab-mcp-server
```

## Project Structure

```
.
├── DEVELOPMENT.md
├── LICENSE
├── pyproject.toml
├── README.md
├── tests/
│   └── smoke_test.py
├── uv.lock
└── src/
    └── ynab_mcp_server/
        ├── __init__.py
        └── server.py
```

## How It Works

This server uses FastMCP's `from_openapi()` method to automatically generate
MCP tools from YNAB's OpenAPI specification. When the server starts, it:

1. Fetches the YNAB OpenAPI spec from
   `https://api.ynab.com/papi/open_api_spec.yaml`.
2. Parses the specification.
3. Creates an authenticated HTTP client with your API token.
4. Generates MCP tools for each API endpoint.

## Publishing

Releases are published to PyPI through GitHub's `pypi` environment and PyPI
Trusted Publishing. The publisher settings must use:

- PyPI project: `ynab-mcp-tools`
- GitHub owner: `rgarcia`
- Repository: `ynab-mcp-server`
- Workflow: `publish.yml`
- Environment: `pypi`

To publish a release:

1. Update the version with `uv version <version>` and merge that change.
2. Publish a GitHub release whose tag matches the version, such as `v0.1.0`.
3. The publish workflow builds and smoke-tests both distributions before
   uploading them to PyPI.
