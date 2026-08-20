import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from . import format as fmt
from . import queries
from .client import LinearClient
from .resolve import ResolutionError, Resolver, parse_identifier

load_dotenv()

mcp = FastMCP(
    "Linear",
    instructions=(
        "Reads and writes Linear issues. Issues are addressed by their human "
        "identifier (e.g. GOV-123), never by UUID. States, teams, labels, and "
        "assignees are given by name; use list_teams, list_states, list_labels, "
        "and list_users to discover valid values."
    ),
)


_client: LinearClient | None = None
_resolver: Resolver | None = None


def _get_client() -> LinearClient:
    global _client
    if _client is None:
        key = os.environ.get("LINEAR_API_KEY")
        if not key:
            raise RuntimeError("LINEAR_API_KEY environment variable is not set")
        _client = LinearClient(api_key=key)
    return _client


def _get_resolver() -> Resolver:
    global _resolver
    if _resolver is None:
        _resolver = Resolver(_get_client())
    return _resolver


def _fail(exc: ResolutionError) -> dict:
    return {"error": exc.message}


@mcp.tool()
def list_teams() -> list[dict]:
    """
    List Linear teams as {key, name}. Team keys are the prefix of issue
    identifiers, e.g. the GOV in GOV-123.
    """
    try:
        return [{"key": t["key"], "name": t["name"]} for t in _get_resolver().teams()]
    except ResolutionError as e:
        return [_fail(e)]


@mcp.tool()
def list_states(team: str) -> list[dict]:
    """
    List the workflow states for a team, in workflow order, as {name, type}.
    These names are what create_issue and update_issue accept for `state`.
    team: team key or full team name.
    """
    resolver = _get_resolver()
    try:
        team_id = resolver.team_id(team)
        return [{"name": s["name"], "type": s["type"]} for s in resolver.states(team_id)]
    except ResolutionError as e:
        return [_fail(e)]


@mcp.tool()
def list_labels(team: str | None = None) -> list[dict]:
    """
    List the issue labels available on a team, as {name}.
    team: team key or full team name. Required — labels are team-scoped.
    """
    if not team:
        return [{"error": "A team is required. Pass a team key such as GOV."}]
    resolver = _get_resolver()
    try:
        team_id = resolver.team_id(team)
        return [{"name": label["name"]} for label in resolver.labels(team_id)]
    except ResolutionError as e:
        return [_fail(e)]


@mcp.tool()
def list_users(query: str | None = None) -> list[dict]:
    """
    List active Linear users as {name, email}. `name` is the display name that
    create_issue and update_issue accept for `assignee`.
    query: optional case-insensitive substring filter over name and email.
    """
    try:
        active = [u for u in _get_resolver().users() if u.get("active")]
    except ResolutionError as e:
        return [_fail(e)]
    people = [
        {"name": u.get("displayName") or "", "email": u.get("email") or ""} for u in active
    ]
    if not query:
        return people
    needle = query.strip().lower()
    return [p for p in people if needle in p["name"].lower() or needle in p["email"].lower()]


@mcp.tool()
def get_issue(identifier: str) -> dict:
    """
    Fetch a Linear issue by its human identifier, e.g. "GOV-123".
    Returns title, description, state, assignee, team, priority, labels, URL,
    and the git branch name Linear suggests for the issue.
    """
    try:
        team_key, number = parse_identifier(identifier)
    except ResolutionError as e:
        return _fail(e)

    data = _get_client().execute(
        queries.ISSUE_BY_TEAM_AND_NUMBER, {"teamKey": team_key, "number": number}
    )
    if "error" in data:
        return {"error": data["error"]}

    found = fmt.nodes(data.get("issues"))
    if not found:
        return {"error": f"No Linear issue found with identifier {identifier}."}
    return fmt.issue(found[0])


@mcp.tool()
def list_my_issues(state: str | None = None, limit: int = 25) -> list[dict]:
    """
    List issues assigned to the owner of the configured API key, most recently
    updated first.
    state: optional state-name filter, e.g. "In Progress". Case-insensitive.
    """
    data = _get_client().execute(queries.MY_ISSUES, {"first": limit})
    if "error" in data:
        return [{"error": data["error"]}]

    issues = [
        fmt.issue(node)
        for node in fmt.nodes((data.get("viewer") or {}).get("assignedIssues"))
    ]
    if state:
        wanted = state.strip().lower()
        issues = [i for i in issues if (i["state"] or "").lower() == wanted]
    return issues


@mcp.tool()
def search_issues(
    query: str,
    team: str | None = None,
    state: str | None = None,
    assignee: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """
    Full-text search over Linear issues, with optional filters.
    team: team key, e.g. "GOV".
    state: exact state name, e.g. "In Progress".
    assignee: user display name. Use list_users to discover valid names.
    """
    issue_filter: dict = {}
    if team:
        issue_filter["team"] = {"key": {"eq": team.strip().upper()}}
    if state:
        issue_filter["state"] = {"name": {"eq": state}}
    if assignee:
        issue_filter["assignee"] = {"displayName": {"eq": assignee}}

    data = _get_client().execute(
        queries.SEARCH_ISSUES,
        {"query": query, "first": limit, "filter": issue_filter or None},
    )
    if "error" in data:
        return [{"error": data["error"]}]
    return [fmt.issue(node) for node in fmt.nodes(data.get("issueSearch"))]


@mcp.tool()
def get_comments(identifier: str) -> list[dict]:
    """
    Fetch the comments on a Linear issue, oldest first.
    identifier: human issue identifier, e.g. "GOV-123".
    """
    try:
        issue_uuid = _get_resolver().issue_id(identifier)
    except ResolutionError as e:
        return [_fail(e)]

    data = _get_client().execute(queries.ISSUE_COMMENTS, {"id": issue_uuid})
    if "error" in data:
        return [{"error": data["error"]}]
    return [
        fmt.comment(node) for node in fmt.nodes((data.get("issue") or {}).get("comments"))
    ]


@mcp.tool()
def add_comment(identifier: str, body: str) -> dict:
    """
    Post a comment on a Linear issue. Markdown is supported.
    identifier: human issue identifier, e.g. "GOV-123".
    """
    if not (body or "").strip():
        return {"error": "Comment body is empty."}
    try:
        issue_uuid = _get_resolver().issue_id(identifier)
    except ResolutionError as e:
        return _fail(e)

    data = _get_client().execute(
        queries.COMMENT_CREATE, {"input": {"issueId": issue_uuid, "body": body}}
    )
    if "error" in data:
        return {"error": data["error"]}

    payload = data.get("commentCreate") or {}
    if not payload.get("success"):
        return {"error": f"Linear rejected the comment on {identifier}."}
    return fmt.comment(payload.get("comment") or {})


_PRIORITY_HELP = "priority must be 0 (none), 1 (urgent), 2 (high), 3 (medium) or 4 (low)."


def _check_priority(priority: int | None) -> str | None:
    if priority is not None and priority not in (0, 1, 2, 3, 4):
        return f"Invalid priority {priority}. {_PRIORITY_HELP}"
    return None


@mcp.tool()
def create_issue(
    team: str,
    title: str,
    description: str = "",
    assignee: str | None = None,
    state: str | None = None,
    priority: int | None = None,
    labels: list[str] | None = None,
) -> dict:
    """
    Create a Linear issue. Returns the created issue including its new identifier.
    team: team key or name, e.g. "GOV".
    assignee: user display name or email. See list_users.
    state: workflow state name, e.g. "Backlog". See list_states.
    priority: 0 none, 1 urgent, 2 high, 3 medium, 4 low.
    labels: label names on that team. See list_labels.
    """
    if not (title or "").strip():
        return {"error": "Issue title is empty."}
    invalid = _check_priority(priority)
    if invalid:
        return {"error": invalid}

    resolver = _get_resolver()
    try:
        team_id = resolver.team_id(team)
        payload: dict = {"teamId": team_id, "title": title}
        if description:
            payload["description"] = description
        if state:
            payload["stateId"] = resolver.state_id(team_id, state)
        if assignee:
            payload["assigneeId"] = resolver.user_id(assignee)
        if priority is not None:
            payload["priority"] = priority
        if labels:
            payload["labelIds"] = resolver.label_ids(team_id, labels)
    except ResolutionError as e:
        return _fail(e)

    data = _get_client().execute(queries.ISSUE_CREATE, {"input": payload})
    if "error" in data:
        return {"error": data["error"]}

    result = data.get("issueCreate") or {}
    if not result.get("success"):
        return {"error": f"Linear rejected the new issue on team {team}."}
    return fmt.issue(result.get("issue") or {})


@mcp.tool()
def update_issue(
    identifier: str,
    title: str | None = None,
    description: str | None = None,
    state: str | None = None,
    assignee: str | None = None,
    priority: int | None = None,
    labels: list[str] | None = None,
) -> dict:
    """
    Update fields on an existing Linear issue. Only the fields you pass are changed.
    identifier: human issue identifier, e.g. "GOV-123".
    state, assignee, labels: names, resolved against the issue's own team.
    priority: 0 none, 1 urgent, 2 high, 3 medium, 4 low.
    Passing labels replaces the issue's labels entirely.
    """
    if all(
        field is None
        for field in (title, description, state, assignee, priority, labels)
    ):
        return {"error": f"Nothing to update on {identifier}. Pass at least one field."}
    invalid = _check_priority(priority)
    if invalid:
        return {"error": invalid}

    resolver = _get_resolver()
    try:
        issue_uuid = resolver.issue_id(identifier)
        payload: dict = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if priority is not None:
            payload["priority"] = priority
        if state is not None or labels is not None:
            # State and label UUIDs are team-scoped; the team comes from the
            # identifier prefix, so the caller never has to repeat it.
            team_key, _ = parse_identifier(identifier)
            team_id = resolver.team_id(team_key)
            if state is not None:
                payload["stateId"] = resolver.state_id(team_id, state)
            if labels is not None:
                payload["labelIds"] = resolver.label_ids(team_id, labels)
        if assignee is not None:
            payload["assigneeId"] = resolver.user_id(assignee)
    except ResolutionError as e:
        return _fail(e)

    data = _get_client().execute(
        queries.ISSUE_UPDATE, {"id": issue_uuid, "input": payload}
    )
    if "error" in data:
        return {"error": data["error"]}

    result = data.get("issueUpdate") or {}
    if not result.get("success"):
        return {"error": f"Linear rejected the update to {identifier}."}
    return fmt.issue(result.get("issue") or {})


def main() -> None:
    mcp.run()
