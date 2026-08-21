"""Retained pending a live API key: confirm Linear GraphQL field names before queries.py is trusted.

Read-only throughout. The three mutations are covered by introspecting their
input types rather than by executing them, so running this never writes to the
tracker it is pointed at.
"""
import json
import os
import sys

import httpx

URL = "https://api.linear.app/graphql"
KEY = os.environ["LINEAR_API_KEY"]

PROBES = {
    "viewer_and_teams": """
        query { viewer { id displayName } teams(first: 3) { nodes { id key name } } }
    """,
    "issue_by_team_and_number": """
        query($teamKey: String!, $number: Float!) {
          issues(filter: {team: {key: {eq: $teamKey}}, number: {eq: $number}}, first: 1) {
            nodes { id identifier title branchName priority url createdAt updatedAt
                    state { name } assignee { displayName } team { key }
                    labels { nodes { name } } }
          }
        }
    """,
    "issue_search": """
        query($query: String!) {
          issueSearch(query: $query, first: 2) { nodes { identifier title } }
        }
    """,
    "team_states_and_labels": """
        query($teamId: String!) {
          team(id: $teamId) {
            states(first: 50) { nodes { id name type position } }
            labels(first: 50) { nodes { id name } }
          }
        }
    """,
    "workspace_labels_and_users": """
        query {
          issueLabels(first: 5) { nodes { id name team { key } } }
          users(first: 5) { nodes { id name displayName email active } }
        }
    """,
    "issue_comments": """
        query($id: String!) {
          issue(id: $id) { comments(first: 5) { nodes { id body createdAt user { displayName } } } }
        }
    """,
    "my_issues": """
        query {
          viewer { assignedIssues(first: 2, orderBy: updatedAt) { nodes { identifier } } }
        }
    """,
    # The three mutations are checked by introspecting their input types rather
    # than by running them: a probe must not write to the user's tracker.
    "input_fields": """
        query($name: String!) { __type(name: $name) { inputFields { name } } }
    """,
}

# The input-object fields queries.py actually sends, per mutation.
EXPECTED_INPUT_FIELDS = {
    "IssueCreateInput": [
        "teamId", "title", "description", "stateId", "assigneeId", "priority", "labelIds",
    ],
    "IssueUpdateInput": [
        "title", "description", "stateId", "assigneeId", "priority", "labelIds",
    ],
    "CommentCreateInput": ["issueId", "body"],
}


def run(name: str, query: str, variables: dict) -> dict:
    resp = httpx.post(
        URL,
        headers={"Authorization": KEY},
        json={"query": query, "variables": variables},
        timeout=30,
    )
    body = resp.json()
    status = "ERRORS" if body.get("errors") else "ok"
    print(f"--- {name}: HTTP {resp.status_code} {status}")
    print(json.dumps(body, indent=2)[:1500])
    return body


def run_input_fields(type_name: str) -> None:
    """Read-only check that a mutation input type accepts the fields we send."""
    body = run(f"input_fields:{type_name}", PROBES["input_fields"], {"name": type_name})
    found = {
        field.get("name")
        for field in ((body.get("data") or {}).get("__type") or {}).get("inputFields") or []
    }
    missing = [f for f in EXPECTED_INPUT_FIELDS[type_name] if f not in found]
    verdict = "MISSING " + ", ".join(missing) if missing else "all sent fields accepted"
    print(f"    {type_name}: {verdict}")


if __name__ == "__main__":
    team_key, number, issue_uuid = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    run("viewer_and_teams", PROBES["viewer_and_teams"], {})
    run("issue_by_team_and_number", PROBES["issue_by_team_and_number"],
        {"teamKey": team_key, "number": number})
    run("issue_search", PROBES["issue_search"], {"query": "test"})
    run("team_states_and_labels", PROBES["team_states_and_labels"],
        {"teamId": input("team UUID from the first probe: ").strip()})
    run("workspace_labels_and_users", PROBES["workspace_labels_and_users"], {})
    run("issue_comments", PROBES["issue_comments"], {"id": issue_uuid})
    run("my_issues", PROBES["my_issues"], {})
    for type_name in EXPECTED_INPUT_FIELDS:
        run_input_fields(type_name)
