"""Human strings -> Linear UUIDs, with an in-process metadata cache."""

import re

from . import format as fmt
from . import queries
from .client import LinearClient

_IDENTIFIER = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d+)$")


class ResolutionError(Exception):
    """Raised when a human string cannot be mapped to exactly one Linear entity.

    Caught at the tool boundary in server.py; never crosses the MCP boundary.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def parse_identifier(identifier: str) -> tuple[str, float]:
    """"gov-123" -> ("GOV", 123.0). Raises ResolutionError on malformed input."""
    match = _IDENTIFIER.match((identifier or "").strip())
    if not match:
        raise ResolutionError(
            f"'{identifier}' is not a Linear issue identifier. "
            "Expected a team key, a dash, and a number, e.g. GOV-123."
        )
    return match.group(1).upper(), float(match.group(2))


class Resolver:
    def __init__(self, client: LinearClient):
        self._client = client
        # Metadata only. Issue content is never cached. A restart is the
        # invalidation mechanism: teams, states and labels change rarely, and a
        # stale miss produces a clear error rather than silent wrong behaviour.
        self._teams: list[dict] | None = None
        self._users: list[dict] | None = None
        self._states: dict[str, list[dict]] = {}
        self._labels: dict[str, list[dict]] = {}

    def _execute(self, query: str, variables: dict) -> dict:
        data = self._client.execute(query, variables)
        if "error" in data:
            raise ResolutionError(data["error"])
        return data

    def issue_id(self, identifier: str) -> str:
        """Return the UUID for a human identifier. Mutations need the UUID."""
        team_key, number = parse_identifier(identifier)
        data = self._execute(
            queries.ISSUE_UUID_BY_TEAM_AND_NUMBER,
            {"teamKey": team_key, "number": number},
        )
        found = fmt.nodes(data.get("issues"))
        if not found:
            raise ResolutionError(f"No Linear issue found with identifier {identifier}.")
        issue = found[0]
        if "id" not in issue:
            raise ResolutionError(f"Linear issue {identifier} has no UUID (server returned incomplete data).")
        return issue["id"]

    def teams(self) -> list[dict]:
        if self._teams is None:
            data = self._execute(queries.TEAMS, {})
            self._teams = fmt.nodes(data.get("teams"))
        return self._teams

    def users(self) -> list[dict]:
        if self._users is None:
            data = self._execute(queries.USERS, {})
            self._users = fmt.nodes(data.get("users"))
        return self._users

    def states(self, team_id: str) -> list[dict]:
        if team_id not in self._states:
            data = self._execute(queries.TEAM_STATES, {"teamId": team_id})
            self._states[team_id] = fmt.nodes((data.get("team") or {}).get("states"))
        return self._states[team_id]

    def labels(self, team_id: str) -> list[dict]:
        if team_id not in self._labels:
            data = self._execute(queries.TEAM_LABELS, {"teamId": team_id})
            self._labels[team_id] = fmt.nodes((data.get("team") or {}).get("labels"))
        return self._labels[team_id]

    def team_id(self, team: str) -> str:
        wanted = (team or "").strip().lower()
        available = self.teams()
        for candidate in available:
            if candidate["key"].lower() == wanted:
                return candidate["id"]
        for candidate in available:
            if candidate["name"].lower() == wanted:
                return candidate["id"]
        options = ", ".join(f"{c['key']} ({c['name']})" for c in available)
        raise ResolutionError(f"No Linear team matches '{team}'. Available teams: {options}.")

    def state_id(self, team_id: str, state: str) -> str:
        wanted = (state or "").strip().lower()
        available = self.states(team_id)
        for candidate in available:
            if candidate["name"].lower() == wanted:
                return candidate["id"]
        options = ", ".join(c["name"] for c in available)
        raise ResolutionError(f"No workflow state matches '{state}'. Valid states: {options}.")

    def user_id(self, assignee: str) -> str:
        wanted = (assignee or "").strip().lower()
        active = [u for u in self.users() if u.get("active")]
        for field in ("displayName", "name", "email"):
            matches = [u for u in active if (u.get(field) or "").lower() == wanted]
            if len(matches) == 1:
                return matches[0]["id"]
            if len(matches) > 1:
                candidates = ", ".join(f"{m['name']} <{m['email']}>" for m in matches)
                raise ResolutionError(
                    f"'{assignee}' matches more than one user: {candidates}. "
                    "Use the email address instead."
                )
        options = ", ".join(u["displayName"] for u in active)
        raise ResolutionError(f"No active user matches '{assignee}'. Known users: {options}.")

    def label_ids(self, team_id: str, labels: list[str]) -> list[str]:
        if not labels:
            return []
        available = self.labels(team_id)
        by_name = {label["name"].lower(): label["id"] for label in available}
        resolved = []
        for wanted in labels:
            found = by_name.get((wanted or "").strip().lower())
            if found is None:
                options = ", ".join(label["name"] for label in available)
                raise ResolutionError(
                    f"No label matches '{wanted}' on this team. Available labels: {options}."
                )
            resolved.append(found)
        return resolved
