# YNAB MCP Server

An [MCP](https://modelcontextprotocol.io/) server for the [YNAB](https://www.ynab.com/) API, built with [FastMCP](https://gofastmcp.com/).

Tools are generated at startup from YNAB's published OpenAPI spec, so new YNAB endpoints show up without a new release of this package.

## Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Create a YNAB personal access token at [app.ynab.com/settings/developer](https://app.ynab.com/settings/developer) (**New Token**). Copy it right away; YNAB only shows it once.
3. Add the server to your MCP client using one of the snippets below, replacing `your-token-here` with your token.

Every snippet runs `uvx ynab-mcp-tools`, which downloads the package from PyPI and runs it in an isolated environment. You don't need to clone this repository.

### Claude Code

```bash
claude mcp add ynab --scope user \
  -e "YNAB_API_TOKEN=your-token-here" \
  -- uvx ynab-mcp-tools
```

Drop `--scope user` to add it to the current project only. See the [Claude Code MCP docs](https://code.claude.com/docs/en/mcp).

### Codex

```bash
codex mcp add ynab \
  --env "YNAB_API_TOKEN=your-token-here" \
  -- uvx ynab-mcp-tools
```

### Claude Desktop and Cursor

Both use the same JSON. Add it to:

- **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)
- **Cursor**: `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project)

```json
{
  "mcpServers": {
    "ynab": {
      "command": "uvx",
      "args": ["ynab-mcp-tools"],
      "env": {
        "YNAB_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

To find the Claude Desktop config file without typing the path, open **Settings → Desktop App → Extensions (Manage) → Local MCP Servers → Edit Config**. Finder opens with the file selected. On macOS, right-click it and choose **Open With → TextEdit**, paste the JSON above, save, then quit and reopen Claude Desktop.

### ChatGPT desktop app

1. Open **Settings**, search for "MCP", and click **MCPs / Plugins**.
2. Click **Add → Add MCP Server** and fill in:
   - **Name**: `YNAB`
   - **Command to launch**: `uvx`
   - **Arguments**: `ynab-mcp-tools`
   - **Environment Variables**: key `YNAB_API_TOKEN`, value `your-token-here`

If a desktop app reports that it can't find `uvx`, replace `uvx` with the full path printed by `which uvx` in a terminal (usually `~/.local/bin/uvx`, written out as `/Users/<you>/.local/bin/uvx`).

### OpenCode

Add to `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "servers": {
      "ynab": {
        "type": "local",
        "command": ["uvx", "ynab-mcp-tools"],
        "environment": {
          "YNAB_API_TOKEN": "your-token-here"
        }
      }
    }
  }
}
```

## Tools

YNAB's API now calls budgets **plans**, so tools and parameters use that name (`getPlans`, `plan_id`). Pass `last-used` as the `plan_id` to target your most recently opened plan.

| Area | Tools |
| --- | --- |
| User | `getUser` |
| Plans | `getPlans`, `getPlanSettingsById` |
| Accounts | `getAccounts`, `getAccountById`, `createAccount` |
| Categories | `getCategories`, `getCategoryById`, `createCategory`, `updateCategory`, `getMonthCategoryById`, `updateMonthCategory`, `createCategoryGroup`, `updateCategoryGroup` |
| Payees | `getPayeeById`, `createPayee`, `updatePayee`, `getPayeeLocations`, `getPayeeLocationById`, `getPayeeLocationsByPayee` |
| Months | `getPlanMonths`, `getPlanMonth` |
| Money movements | `getMoneyMovements`, `getMoneyMovementsByMonth`, `getMoneyMovementGroups`, `getMoneyMovementGroupsByMonth` |
| Transactions | `getTransactions`, `getTransactionById`, `createTransaction`, `updateTransaction`, `updateTransactions`, `deleteTransaction`, `getTransactionsByAccount`, `getTransactionsByCategory`, `getTransactionsByPayee`, `getTransactionsByMonth` |
| Scheduled transactions | `getScheduledTransactions`, `getScheduledTransactionById`, `createScheduledTransaction`, `updateScheduledTransaction`, `deleteScheduledTransaction` |

Two kinds of endpoints are left out on purpose:

- `getPlanById` and `getPayees`: these return an entire plan export or the full payee list, which is too large for a model's context. The narrower tools above cover the same data.
- Endpoints YNAB marks deprecated, such as `importTransactions`, which YNAB now accepts but ignores.

## Example prompts

- "Show me my unapproved transactions from the last two weeks."
- "How much have I spent on dining out this month compared to last month?"
- "Categorize my uncategorized transactions, and ask me about anything ambiguous."
- "Move $50 from Vacation to Groceries for this month."

To make your own conventions stick between sessions (how you handle Venmo duplicates, which payees map to which categories), write them into your client's skills or rules, for example a [Claude skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview).

## Resources

- [Development guide](https://github.com/rgarcia/ynab-mcp-server/blob/main/DEVELOPMENT.md)
- [YNAB API documentation](https://api.ynab.com/)
- [FastMCP documentation](https://gofastmcp.com/)

## License

MIT
