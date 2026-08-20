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
