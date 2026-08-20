import httpx
import pytest
import respx

from mcp_linear.client import LINEAR_API_URL, LinearClient
from mcp_linear.resolve import ResolutionError, Resolver, parse_identifier


@pytest.fixture
def resolver():
    return Resolver(LinearClient(api_key="lin_api_test"))


def test_parse_identifier_splits_team_key_and_number():
    assert parse_identifier("GOV-123") == ("GOV", 123.0)


def test_parse_identifier_uppercases_the_team_key():
    assert parse_identifier("gov-123") == ("GOV", 123.0)


def test_parse_identifier_strips_surrounding_whitespace():
    assert parse_identifier("  GOV-123  ") == ("GOV", 123.0)


@pytest.mark.parametrize("bad", ["GOV123", "GOV-", "-123", "GOV-abc", "", "GOV-1-2"])
def test_parse_identifier_rejects_malformed_input_without_a_network_call(bad):
    with pytest.raises(ResolutionError) as excinfo:
        parse_identifier(bad)
    assert "GOV-123" in excinfo.value.message


@respx.mock
def test_issue_id_returns_the_uuid(resolver):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"issues": {"nodes": [{"id": "uuid-1", "identifier": "GOV-123"}]}}},
        )
    )
    assert resolver.issue_id("GOV-123") == "uuid-1"


@respx.mock
def test_issue_id_sends_the_parsed_team_key_and_number(resolver):
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"issues": {"nodes": [{"id": "uuid-1"}]}}}
        )
    )
    resolver.issue_id("gov-7")
    assert json.loads(route.calls.last.request.content)["variables"] == {
        "teamKey": "GOV",
        "number": 7.0,
    }


@respx.mock
def test_issue_id_raises_when_no_issue_matches(resolver):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issues": {"nodes": []}}})
    )
    with pytest.raises(ResolutionError) as excinfo:
        resolver.issue_id("GOV-999")
    assert "GOV-999" in excinfo.value.message


@respx.mock
def test_issue_id_surfaces_an_api_error(resolver):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "rate limited"}]})
    )
    with pytest.raises(ResolutionError) as excinfo:
        resolver.issue_id("GOV-1")
    assert "rate limited" in excinfo.value.message


@respx.mock
def test_issue_id_raises_when_id_is_missing(resolver):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"issues": {"nodes": [{"identifier": "GOV-123"}]}}}
        )
    )
    with pytest.raises(ResolutionError) as excinfo:
        resolver.issue_id("GOV-123")
    assert "GOV-123" in excinfo.value.message


@respx.mock
def test_issue_id_rejects_malformed_identifier_without_network_call(resolver):
    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"issues": {"nodes": [{"id": "uuid-1"}]}}}
        )
    )
    with pytest.raises(ResolutionError) as excinfo:
        resolver.issue_id("not-an-identifier")
    assert "GOV-123" in excinfo.value.message
    assert route.call_count == 0


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
                    {"id": "st-3", "name": "Done", "type": "completed", "position": 2},
                ]
            }
        }
    }
}

LABELS_PAYLOAD = {
    "data": {
        "team": {
            "labels": {"nodes": [{"id": "lb-1", "name": "bug"}, {"id": "lb-2", "name": "backend"}]}
        }
    }
}

USERS_PAYLOAD = {
    "data": {
        "users": {
            "nodes": [
                {"id": "u-1", "name": "Pius C", "displayName": "pius",
                 "email": "pius@example.com", "active": True},
                {"id": "u-2", "name": "Sam T", "displayName": "sam",
                 "email": "sam@example.com", "active": True},
                {"id": "u-3", "name": "Old Sam", "displayName": "sam",
                 "email": "old@example.com", "active": False},
            ]
        }
    }
}


@respx.mock
def test_team_id_matches_on_key_case_insensitively(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=TEAMS_PAYLOAD))
    assert resolver.team_id("gov") == "team-gov"


@respx.mock
def test_team_id_matches_on_full_name(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=TEAMS_PAYLOAD))
    assert resolver.team_id("Platform") == "team-plat"


@respx.mock
def test_team_id_lists_valid_options_on_a_miss(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=TEAMS_PAYLOAD))
    with pytest.raises(ResolutionError) as excinfo:
        resolver.team_id("Nope")
    assert "GOV" in excinfo.value.message and "PLAT" in excinfo.value.message


@respx.mock
def test_teams_are_fetched_once_and_cached(resolver):
    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json=TEAMS_PAYLOAD)
    )
    resolver.team_id("GOV")
    resolver.team_id("PLAT")
    assert route.call_count == 1


@respx.mock
def test_state_id_matches_case_insensitively(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=STATES_PAYLOAD))
    assert resolver.state_id("team-gov", "in progress") == "st-2"


@respx.mock
def test_state_id_lists_valid_states_on_a_miss(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=STATES_PAYLOAD))
    with pytest.raises(ResolutionError) as excinfo:
        resolver.state_id("team-gov", "Shipped")
    assert "In Progress" in excinfo.value.message


@respx.mock
def test_states_are_cached_per_team(resolver):
    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json=STATES_PAYLOAD)
    )
    resolver.state_id("team-gov", "Done")
    resolver.state_id("team-gov", "Backlog")
    assert route.call_count == 1
    resolver.state_id("team-plat", "Done")
    assert route.call_count == 2


@respx.mock
def test_user_id_matches_on_display_name(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=USERS_PAYLOAD))
    assert resolver.user_id("pius") == "u-1"


@respx.mock
def test_user_id_matches_on_email(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=USERS_PAYLOAD))
    assert resolver.user_id("sam@example.com") == "u-2"


@respx.mock
def test_user_id_ignores_deactivated_users(resolver):
    """Two users share displayName "sam"; only the active one counts, so no ambiguity."""
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=USERS_PAYLOAD))
    assert resolver.user_id("sam") == "u-2"


@respx.mock
def test_user_id_reports_ambiguity_with_the_candidates(resolver):
    payload = {
        "data": {
            "users": {
                "nodes": [
                    {"id": "u-1", "name": "Sam One", "displayName": "sam",
                     "email": "one@example.com", "active": True},
                    {"id": "u-2", "name": "Sam Two", "displayName": "sam",
                     "email": "two@example.com", "active": True},
                ]
            }
        }
    }
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(ResolutionError) as excinfo:
        resolver.user_id("sam")
    assert "one@example.com" in excinfo.value.message
    assert "two@example.com" in excinfo.value.message


@respx.mock
def test_label_ids_resolves_several_labels(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=LABELS_PAYLOAD))
    assert resolver.label_ids("team-gov", ["bug", "BACKEND"]) == ["lb-1", "lb-2"]


@respx.mock
def test_label_ids_lists_valid_labels_on_a_miss(resolver):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=LABELS_PAYLOAD))
    with pytest.raises(ResolutionError) as excinfo:
        resolver.label_ids("team-gov", ["nonsense"])
    assert "bug" in excinfo.value.message


@respx.mock
def test_label_ids_returns_an_empty_list_without_calling_the_api(resolver):
    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json=LABELS_PAYLOAD)
    )
    assert resolver.label_ids("team-gov", []) == []
    assert route.call_count == 0


@respx.mock
def test_team_id_reports_ambiguity_with_the_candidates(resolver):
    payload = {
        "data": {
            "teams": {
                "nodes": [
                    {"id": "team-1", "key": "ENG", "name": "Shared"},
                    {"id": "team-2", "key": "OPS", "name": "Shared"},
                ]
            }
        }
    }
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(ResolutionError) as excinfo:
        resolver.team_id("Shared")
    assert "ENG" in excinfo.value.message
    assert "OPS" in excinfo.value.message


@respx.mock
def test_state_id_reports_ambiguity_with_the_candidates(resolver):
    payload = {
        "data": {
            "team": {
                "states": {
                    "nodes": [
                        {"id": "st-a", "name": "Blocked", "type": "started", "position": 0},
                        {"id": "st-b", "name": "Blocked", "type": "backlog", "position": 1},
                    ]
                }
            }
        }
    }
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(ResolutionError) as excinfo:
        resolver.state_id("team-gov", "Blocked")
    assert "started" in excinfo.value.message
    assert "backlog" in excinfo.value.message


@respx.mock
def test_label_ids_reports_ambiguity_with_the_candidates(resolver):
    payload = {
        "data": {
            "team": {
                "labels": {
                    "nodes": [
                        {"id": "lb-a", "name": "bug"},
                        {"id": "lb-b", "name": "bug"},
                    ]
                }
            }
        }
    }
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(ResolutionError) as excinfo:
        resolver.label_ids("team-gov", ["bug"])
    assert "lb-a" in excinfo.value.message
    assert "lb-b" in excinfo.value.message
