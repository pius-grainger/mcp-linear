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
        return found[0]["id"]
