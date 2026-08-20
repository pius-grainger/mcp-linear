import httpx
import pytest
import respx

from mcp_linear.client import LINEAR_API_URL, LinearClient


@pytest.fixture
def client():
    return LinearClient(api_key="lin_api_test")


@respx.mock
def test_execute_returns_the_data_dict(client):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"teams": {"nodes": []}}})
    )
    assert client.execute("query { teams { nodes { id } } }") == {"teams": {"nodes": []}}


@respx.mock
def test_execute_sends_the_api_key_raw_without_bearer_prefix(client):
    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"viewer": {"id": "u1"}}})
    )
    client.execute("query { viewer { id } }")
    assert route.calls.last.request.headers["authorization"] == "lin_api_test"


@respx.mock
def test_execute_sends_query_and_variables_in_the_body(client):
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issue": None}})
    )
    client.execute("query($id: String!) { issue(id: $id) { id } }", {"id": "abc"})
    body = json.loads(route.calls.last.request.content)
    assert body["variables"] == {"id": "abc"}
    assert "issue(id: $id)" in body["query"]


@respx.mock
def test_execute_defaults_variables_to_an_empty_dict(client):
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"viewer": {"id": "u1"}}})
    )
    client.execute("query { viewer { id } }")
    assert json.loads(route.calls.last.request.content)["variables"] == {}


@respx.mock
def test_execute_maps_a_graphql_errors_array_despite_http_200(client):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": None, "errors": [{"message": "Entity not found"}]},
        )
    )
    result = client.execute("query { issue(id: \"nope\") { id } }")
    assert result["error"] == "Entity not found"
    assert result["details"] == [{"message": "Entity not found"}]


@respx.mock
def test_execute_joins_multiple_graphql_error_messages(client):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"errors": [{"message": "first"}, {"message": "second"}]}
        )
    )
    assert client.execute("query { x }")["error"] == "first; second"


@respx.mock
def test_execute_maps_a_non_2xx_status(client):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(401, text="Authentication required")
    )
    result = client.execute("query { viewer { id } }")
    assert result["error"] == "Linear API error 401: Authentication required"


@respx.mock
def test_execute_maps_a_non_json_response(client):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, text="<html>gateway</html>")
    )
    assert "non-JSON" in client.execute("query { viewer { id } }")["error"]


@respx.mock
def test_execute_maps_a_transport_failure(client):
    respx.post(LINEAR_API_URL).mock(side_effect=httpx.ConnectError("no route"))
    assert "Linear request failed" in client.execute("query { viewer { id } }")["error"]


@respx.mock
def test_execute_maps_a_payload_with_neither_data_nor_errors(client):
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json={}))
    assert client.execute("query { viewer { id } }")["error"] == "Linear returned no data"


@respx.mock
def test_execute_maps_a_null_response_json_payload(client):
    import json

    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, content=b"null", headers={"content-type": "application/json"}
        )
    )
    result = client.execute("query { viewer { id } }")
    assert "error" in result
    assert "unexpected response shape" in result["error"]


@pytest.mark.parametrize("non_dict_value", [[], "string", 42, True])
@respx.mock
def test_execute_maps_a_non_dict_response_shape(client, non_dict_value):
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json=non_dict_value)
    )
    result = client.execute("query { viewer { id } }")
    assert "error" in result
    assert "unexpected response shape" in result["error"]
