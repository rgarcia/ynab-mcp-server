"""Verify an installed distribution has its import and command entry points."""

from importlib.metadata import distribution

from ynab_mcp_server.server import create_server, main


package = distribution("ynab-mcp-tools")
scripts = {
    entry_point.name
    for entry_point in package.entry_points
    if entry_point.group == "console_scripts"
}

assert callable(create_server)
assert callable(main)
assert {"ynab-mcp-tools", "ynab-mcp-server"} <= scripts
