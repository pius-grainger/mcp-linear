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

The GraphQL field names in `src/mcp_linear/queries.py` were **verified against
the live Linear API on 2026-08-21**, by running the tools' actual query strings
(not copies of them) against a real workspace.

Verified correct:

- the `Float!` issue-number comparator
- team-scoped labels via `team { labels }`
- the root `issueLabels` connection
- `viewer.assignedIssues(orderBy: updatedAt)`
- every field the three mutations send — `IssueCreateInput`, `IssueUpdateInput`
  and `CommentCreateInput` all accept `teamId`, `title`, `description`,
  `stateId`, `assigneeId`, `priority`, `labelIds`, `issueId` and `body` as used

One divergence was found and fixed:

- **Full-text search.** `issueSearch` rejects its `query` argument as
  deprecated. Search now uses `searchIssues(term: ...)`, which returns
  `IssueSearchPayload` whose nodes are `IssueSearchResult`, **not** `Issue` — so
  it cannot spread the `IssueFields` fragment. `queries.py` declares a second
  fragment, `SearchFields`, with the identical selection on that type.
  Introspection confirmed `IssueSearchResult` carries every field `IssueFields`
  selects. **If you change one fragment, change the other.**

One thing remains unconfirmed:

- **Workspace labels.** The root `issueLabels` connection resolves, but whether
  it returns workspace-wide labels only — or also team-scoped labels belonging
  to other teams — was not established. Label resolution consults a team's own
  labels first, so a team label always wins over a same-named workspace one.

To re-verify after a Linear schema change:

```bash
LINEAR_API_KEY=lin_api_... .venv/bin/python scripts/probe_schema.py <team-key> <issue-number> <issue-uuid>
```

It takes a team key, an existing issue number on that team, and that issue's
UUID (and prompts once, interactively, for a team UUID printed by its first
probe). The probe is read-only: the mutations are checked by introspecting
their input types, never by writing to your tracker.

## Notes

- Linear personal API keys are sent as `Authorization: <key>` with **no** `Bearer`
  prefix.
- Linear reports most failures as HTTP 200 with a top-level `errors` array, so
  the client checks the response body rather than the status code.
- Team, state, label, and user metadata is cached for the lifetime of the server
  process. Restart the server after changing a team's workflow states or labels.
