import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .client import LinearClient
from .resolve import ResolutionError, Resolver

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
    people = [{"name": u["displayName"], "email": u["email"]} for u in active]
    if not query:
        return people
    needle = query.strip().lower()
    return [p for p in people if needle in p["name"].lower() or needle in p["email"].lower()]


def main() -> None:
    mcp.run()
