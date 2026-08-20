# mcp-linear

MCP server exposing Linear issue operations. Standalone — no dependency on the
built-in Claude Linear MCP.

Issues are addressed by their human identifier (`GOV-123`). States, teams,
labels, and assignees are given by name; the server resolves them to Linear
UUIDs and returns an error listing valid options when a name does not match.

## Tools

| Tool | Description |
|------|-------------|
| `get_issue` | Fetch an issue by identifier |
| `list_my_issues` | Issues assigned to the API key's owner |
| `search_issues` | Full-text search with team/state/assignee filters |
| `create_issue` | Create an issue on a team |
| `update_issue` | Update fields on an existing issue |
| `get_comments` | Comments on an issue |
| `add_comment` | Post a comment |
| `list_teams` | Team keys and names |
| `list_states` | Workflow states for a team |
| `list_labels` | Labels on a team plus workspace labels (team optional) |
| `list_users` | Active users |

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# Edit .env — set LINEAR_API_KEY
```

**Get an API key**: Linear → Settings → Security & access → Personal API keys.
Write operations need a key with write access.

## Add to Claude Code

```json
{
  "mcpServers": {
    "linear": {
      "command": "/Users/piuschungath/Workspace/mcp-linear/.venv/bin/mcp-linear",
      "env": { "LINEAR_API_KEY": "lin_api_..." }
    }
  }
}
```

## Tests

```bash
.venv/bin/pytest
```

All HTTP is mocked with `respx`. No API key and no network access are needed.

## With mcp-pr-assistant

The two servers compose without importing each other: fetch a ticket with
`get_issue`, pass its fields to `create_pr_from_ticket`, then post the PR URL
back with `add_comment`.

## Schema verification

The GraphQL field names in `src/mcp_linear/queries.py` come from Linear's
documented schema and have **not** been verified against the live API. No
`LINEAR_API_KEY` was available while this project was built, so that
verification never ran.

`scripts/probe_schema.py` performs the verification: point it at a real API
key and it runs one read-only probe per query shape used by the tools above,
reporting which fields Linear actually accepts. The three mutations are covered
too, by introspecting `IssueCreateInput`, `IssueUpdateInput` and
`CommentCreateInput` and checking that every field the queries send is accepted
— the probe never writes to your tracker.

```bash
LINEAR_API_KEY=lin_api_... .venv/bin/python scripts/probe_schema.py <team-key> <issue-number> <issue-uuid>
```

It takes a team key, an existing issue number on that team, and that issue's
UUID as arguments (and prompts once, interactively, for a team UUID printed by
its first probe) — see the script for details.

The three likeliest divergences, in order of suspicion:

- **Full-text search** — `queries.py` calls `issueSearch(query: ...)`; Linear
  may instead expose `searchIssues(term: ...)`.
- **Team-scoped labels** — `queries.py` reads labels via `team { labels }`;
  Linear may instead require `issueLabels(filter: ...)`.
- **Number comparator type** — `queries.py` declares the issue-number filter
  variable as `Float!`; Linear's `NumberComparator` may expect `Int!`.
- **`viewer.assignedIssues` ordering** — `queries.py` passes
  `orderBy: updatedAt`; the enum's spelling is unconfirmed.
- **Workspace labels** — `queries.py` reads them from the root `issueLabels`
  connection, which may also return other teams' labels.

The test suite mocks HTTP at the `respx` layer and constructs its own
responses, so it exercises the Python around each query but never sends a
query to Linear — it passes regardless of whether these field names are
correct. A schema mismatch would first surface on a real call, typically as
`Cannot query field "..." on type "..."`. Run the probe before relying on this
server against a live workspace.

## Notes

- Linear personal API keys are sent as `Authorization: <key>` with **no** `Bearer`
  prefix.
- Linear reports most failures as HTTP 200 with a top-level `errors` array, so
  the client checks the response body rather than the status code.
- Team, state, label, and user metadata is cached for the lifetime of the server
  process. Restart the server after changing a team's workflow states or labels.
