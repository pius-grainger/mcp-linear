import httpx
import pytest
import respx

from mcp_linear import server
from mcp_linear.client import LINEAR_API_URL, LinearClient
from mcp_linear.resolve import Resolver

TEAMS_PAYLOAD = {
    "data": {
        "teams": {
            "nodes": [
                {"id": "team-gov", "key": "GOV", "name": "Governance"},
                {"id": "team-plat", "key": "PLAT", "name": "Platform"},
            ]
        }
    }
}

STATES_PAYLOAD = {
    "data": {
        "team": {
            "states": {
                "nodes": [
                    {"id": "st-1", "name": "Backlog", "type": "backlog", "position": 0},
                    {"id": "st-2", "name": "In Progress", "type": "started", "position": 1},
                ]
            }
        }
    }
}

LABELS_PAYLOAD = {
    "data": {"team": {"labels": {"nodes": [{"id": "lb-1", "name": "bug"}]}}}
}

USERS_PAYLOAD = {
    "data": {
        "users": {
            "nodes": [
                {"id": "u-1", "name": "Pius C", "displayName": "pius",
                 "email": "pius@example.com", "active": True},
                {"id": "u-9", "name": "Gone", "displayName": "gone",
                 "email": "gone@example.com", "active": False},
            ]
        }
    }
}

USERS_WITH_NULL_DISPLAY_NAME_PAYLOAD = {
    "data": {
        "users": {
            "nodes": [
                {"id": "u-1", "name": "Pius C", "displayName": "pius",
                 "email": "pius@example.com", "active": True},
                {"id": "u-2", "name": "No Display", "displayName": None,
                 "email": None, "active": True},
            ]
        }
    }
}

GRAPHQL_ERROR = {"errors": [{"message": "Authentication required"}]}


@pytest.fixture(autouse=True)
def wired_server():
    """Inject a keyless client so tools never read the environment."""
    client = LinearClient(api_key="lin_api_test")
    server._client = client
    server._resolver = Resolver(client)
    yield
    server._client = None
    server._resolver = None


@respx.mock
def test_list_teams_returns_key_and_name_without_uuids():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=TEAMS_PAYLOAD))
    result = server.list_teams()
    assert result == [
        {"key": "GOV", "name": "Governance"},
        {"key": "PLAT", "name": "Platform"},
    ]


@respx.mock
def test_list_teams_returns_an_error_list_on_api_failure():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=GRAPHQL_ERROR))
    assert server.list_teams() == [{"error": "Authentication required"}]


@respx.mock
def test_list_states_returns_states_in_workflow_order():
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=STATES_PAYLOAD),
        ]
    )
    assert server.list_states("GOV") == [
        {"name": "Backlog", "type": "backlog"},
        {"name": "In Progress", "type": "started"},
    ]


@respx.mock
def test_list_states_reports_an_unknown_team():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=TEAMS_PAYLOAD))
    result = server.list_states("NOPE")
    assert len(result) == 1
    assert "GOV" in result[0]["error"]


@respx.mock
def test_list_labels_for_a_team():
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=LABELS_PAYLOAD),
        ]
    )
    assert server.list_labels("GOV") == [{"name": "bug"}]


@respx.mock
def test_list_labels_without_a_team_requires_one():
    result = server.list_labels()
    assert "team" in result[0]["error"].lower()


@respx.mock
def test_list_users_excludes_deactivated_users():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=USERS_PAYLOAD))
    assert server.list_users() == [{"name": "pius", "email": "pius@example.com"}]


@respx.mock
def test_list_users_filters_by_substring_query():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=USERS_PAYLOAD))
    assert server.list_users("piu") == [{"name": "pius", "email": "pius@example.com"}]
    assert server.list_users("zzz") == []


@respx.mock
def test_list_users_tolerates_a_null_display_name_and_email():
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json=USERS_WITH_NULL_DISPLAY_NAME_PAYLOAD)
    )
    assert server.list_users() == [
        {"name": "pius", "email": "pius@example.com"},
        {"name": "", "email": ""},
    ]
    assert server.list_users("piu") == [{"name": "pius", "email": "pius@example.com"}]


ISSUE_NODE = {
    "identifier": "GOV-123",
    "title": "Fix the widget",
    "description": "It is broken.",
    "priority": 2,
    "url": "https://linear.app/acme/issue/GOV-123",
    "branchName": "pius/gov-123-fix-the-widget",
    "createdAt": "2026-08-01T10:00:00.000Z",
    "updatedAt": "2026-08-02T11:00:00.000Z",
    "state": {"name": "In Progress"},
    "assignee": {"displayName": "pius"},
    "team": {"key": "GOV"},
    "labels": {"nodes": [{"name": "bug"}]},
}


@respx.mock
def test_get_issue_returns_the_flattened_issue():
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issues": {"nodes": [ISSUE_NODE]}}})
    )
    result = server.get_issue("GOV-123")
    assert result["identifier"] == "GOV-123"
    assert result["state"] == "In Progress"
    assert result["branch_name"] == "pius/gov-123-fix-the-widget"


@respx.mock
def test_get_issue_sends_the_parsed_team_key_and_number():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issues": {"nodes": [ISSUE_NODE]}}})
    )
    server.get_issue("gov-123")
    assert json.loads(route.calls.last.request.content)["variables"] == {
        "teamKey": "GOV",
        "number": 123.0,
    }


def test_get_issue_rejects_a_malformed_identifier_without_a_network_call():
    with respx.mock:
        route = respx.post(LINEAR_API_URL)
        result = server.get_issue("not-an-id-at-all")
        assert "error" in result
        assert route.call_count == 0


@respx.mock
def test_get_issue_reports_a_missing_issue():
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issues": {"nodes": []}}})
    )
    assert "GOV-999" in server.get_issue("GOV-999")["error"]


@respx.mock
def test_get_issue_surfaces_an_api_error():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=GRAPHQL_ERROR))
    assert server.get_issue("GOV-1")["error"] == "Authentication required"


@respx.mock
def test_list_my_issues_returns_the_viewers_issues():
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"viewer": {"assignedIssues": {"nodes": [ISSUE_NODE]}}}}
        )
    )
    result = server.list_my_issues()
    assert [i["identifier"] for i in result] == ["GOV-123"]


@respx.mock
def test_list_my_issues_passes_the_limit_as_first():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"viewer": {"assignedIssues": {"nodes": []}}}}
        )
    )
    server.list_my_issues(limit=5)
    assert json.loads(route.calls.last.request.content)["variables"]["first"] == 5


@respx.mock
def test_list_my_issues_filters_by_state_name_case_insensitively():
    done = {**ISSUE_NODE, "identifier": "GOV-124", "state": {"name": "Done"}}
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"viewer": {"assignedIssues": {"nodes": [ISSUE_NODE, done]}}}},
        )
    )
    assert [i["identifier"] for i in server.list_my_issues(state="done")] == ["GOV-124"]


@respx.mock
def test_list_my_issues_surfaces_an_api_error():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=GRAPHQL_ERROR))
    assert server.list_my_issues() == [{"error": "Authentication required"}]


@respx.mock
def test_search_issues_sends_the_query_and_limit():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issueSearch": {"nodes": [ISSUE_NODE]}}})
    )
    result = server.search_issues("widget", limit=10)
    body = json.loads(route.calls.last.request.content)
    assert body["variables"]["query"] == "widget"
    assert body["variables"]["first"] == 10
    assert result[0]["identifier"] == "GOV-123"


@respx.mock
def test_search_issues_builds_a_filter_from_team_state_and_assignee():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issueSearch": {"nodes": []}}})
    )
    server.search_issues("widget", team="GOV", state="In Progress", assignee="pius")
    variables = json.loads(route.calls.last.request.content)["variables"]
    assert variables["filter"] == {
        "team": {"key": {"eq": "GOV"}},
        "state": {"name": {"eq": "In Progress"}},
        "assignee": {"displayName": {"eq": "pius"}},
    }


@respx.mock
def test_search_issues_omits_the_filter_when_no_filters_are_given():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issueSearch": {"nodes": []}}})
    )
    server.search_issues("widget")
    assert json.loads(route.calls.last.request.content)["variables"]["filter"] is None


@respx.mock
def test_search_issues_surfaces_an_api_error():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=GRAPHQL_ERROR))
    assert server.search_issues("x") == [{"error": "Authentication required"}]
