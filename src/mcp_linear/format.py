"""GraphQL node -> flat dict. Pure functions, no I/O.

Linear UUIDs are deliberately dropped: every tool addresses issues by their
human identifier, so a UUID in the output is noise the model cannot use.
"""


def nodes(connection: dict | None) -> list[dict]:
    """Unwrap a GraphQL `{"nodes": [...]}` connection, tolerating None."""
    if not connection:
        return []
    return connection.get("nodes") or []


def issue(node: dict) -> dict:
    return {
        "identifier": node.get("identifier"),
        "title": node.get("title"),
        "description": node.get("description") or "",
        "state": (node.get("state") or {}).get("name"),
        "assignee": (node.get("assignee") or {}).get("displayName"),
        "team": (node.get("team") or {}).get("key"),
        "priority": node.get("priority"),
        "labels": [label.get("name") for label in nodes(node.get("labels"))],
        "url": node.get("url"),
        "branch_name": node.get("branchName"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
    }


def comment(node: dict) -> dict:
    return {
        "author": (node.get("user") or {}).get("displayName"),
        "body": node.get("body"),
        "created_at": node.get("createdAt"),
    }
