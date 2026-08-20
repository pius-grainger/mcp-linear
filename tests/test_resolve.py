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
