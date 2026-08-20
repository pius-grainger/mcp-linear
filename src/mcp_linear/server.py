from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

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


def main() -> None:
    mcp.run()
