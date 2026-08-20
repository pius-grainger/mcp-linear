"""Retained pending a live API key: confirm Linear GraphQL field names before queries.py is trusted."""
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
}


def run(name: str, query: str, variables: dict) -> None:
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
