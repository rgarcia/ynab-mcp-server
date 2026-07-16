# Development

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
