# Sequence Finance MCP

Read-only MCP server for Sequence's Platform API.

## What It Can Access

Sequence currently documents these useful Platform API capabilities:

- List accounts with `GET /accounts`
- Fetch account details and balances with `GET /accounts/{id}`
- Read transfer history by account with `GET /accounts/{accountId}/transfers`
- Read rules and rule executions
- Trigger rules and create manual transfers

This MCP intentionally implements only read-only tools. It does not expose rule triggers or manual transfers because those can move money.

## Setup

Create the project-root `.env`:

```bash
SEQUENCE_API_KEY=your_sequence_platform_api_key_here
```

Use the Platform API key from Sequence Settings -> API Keys. The MCP also accepts the older `SEQUENCE_ACCESS_TOKEN` env var name as a fallback.

Then install and build:

```bash
cd tools/sequence-mcp
npm install
npm run build
npm run smoke
```

## Codex MCP Config

Add this to `~/.codex/config.toml` after `.env` exists:

```toml
[mcp_servers.sequence]
command = "node"
args = ["tools/sequence-mcp/dist/index.js"]
```

The server loads the project-root `.env` automatically, so the token does not need to live in the Codex config.

## Tools

- `list_sequence_accounts` - all accounts with ids, names, types, balances, and provider errors
- `get_sequence_account` - one account by id or name text
- `summarize_sequence_balances` - total and grouped balances by account type
- `list_sequence_transfers` - transfer history for one account
- `get_sequence_transfer` - one transfer by id
- `list_sequence_rules` - readable rules
- `list_sequence_rule_executions` - execution history for one rule
- `save_sequence_snapshot` - save a timestamped JSON and Markdown snapshot under `sequence-snapshots/`
