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

WORKSPACE_LABELS_PAYLOAD = {
    "data": {
        "issueLabels": {
            "nodes": [{"id": "wl-1", "name": "Needs Design"}, {"id": "wl-2", "name": "bug"}]
        }
    }
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
    """Linear does not promise the connection is ordered; `position` is the order."""
    unordered = {
        "data": {
            "team": {
                "states": {
                    "nodes": [
                        {"id": "st-3", "name": "Done", "type": "completed", "position": 2},
                        {"id": "st-1", "name": "Backlog", "type": "backlog", "position": 0},
                        {"id": "st-2", "name": "In Progress", "type": "started", "position": 1},
                    ]
                }
            }
        }
    }
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=unordered),
        ]
    )
    assert server.list_states("GOV") == [
        {"name": "Backlog", "type": "backlog"},
        {"name": "In Progress", "type": "started"},
        {"name": "Done", "type": "completed"},
    ]


@respx.mock
def test_list_states_reports_an_unknown_team():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=TEAMS_PAYLOAD))
    result = server.list_states("NOPE")
    assert len(result) == 1
    assert "GOV" in result[0]["error"]


@respx.mock
def test_list_labels_for_a_team_includes_workspace_labels():
    """The design resolves labels against team labels plus workspace labels."""
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=LABELS_PAYLOAD),
            httpx.Response(200, json=WORKSPACE_LABELS_PAYLOAD),
        ]
    )
    # "bug" exists in both scopes and is listed once.
    assert server.list_labels("GOV") == [{"name": "bug"}, {"name": "Needs Design"}]


@respx.mock
def test_list_labels_without_a_team_returns_workspace_labels():
    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json=WORKSPACE_LABELS_PAYLOAD)
    )
    assert server.list_labels() == [{"name": "Needs Design"}, {"name": "bug"}]
    # No team was named, so no teams lookup happened.
    assert route.call_count == 1


@respx.mock
def test_list_labels_reports_an_unknown_team():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=TEAMS_PAYLOAD))
    result = server.list_labels("NOPE")
    assert "GOV" in result[0]["error"]


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
def test_list_my_issues_over_fetches_when_filtering_by_state():
    """A match outside the naive `first: limit` window is still returned."""
    import json

    done = [
        {**ISSUE_NODE, "identifier": f"GOV-{n}", "state": {"name": "Done"}}
        for n in range(200, 203)
    ]
    match = {**ISSUE_NODE, "identifier": "GOV-300", "state": {"name": "In Progress"}}
    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"viewer": {"assignedIssues": {"nodes": done + [match]}}}},
        )
    )
    result = server.list_my_issues(state="In Progress", limit=3)
    assert [i["identifier"] for i in result] == ["GOV-300"]
    assert json.loads(route.calls.last.request.content)["variables"]["first"] == 50


@respx.mock
def test_list_my_issues_caps_the_filtered_result_at_the_limit():
    matches = [
        {**ISSUE_NODE, "identifier": f"GOV-{n}", "state": {"name": "In Progress"}}
        for n in range(400, 410)
    ]
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"viewer": {"assignedIssues": {"nodes": matches}}}}
        )
    )
    result = server.list_my_issues(state="In Progress", limit=3)
    assert [i["identifier"] for i in result] == ["GOV-400", "GOV-401", "GOV-402"]


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
def test_search_issues_normalizes_team_state_and_assignee_to_canonical_names():
    """Filters are built from resolved names, so the caller's spelling is
    accepted exactly where create_issue would accept it."""
    import json

    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=STATES_PAYLOAD),
            httpx.Response(200, json=USERS_PAYLOAD),
            httpx.Response(200, json={"data": {"issueSearch": {"nodes": []}}}),
        ]
    )
    # A full team name, a lowercased state, and a full name rather than a
    # display name: all of these used to return zero results silently.
    server.search_issues(
        "widget", team="Governance", state="in progress", assignee="Pius C"
    )
    variables = json.loads(respx.calls.last.request.content)["variables"]
    assert variables["filter"] == {
        "team": {"key": {"eq": "GOV"}},
        "state": {"name": {"eq": "In Progress"}},
        "assignee": {"displayName": {"eq": "pius"}},
    }


@respx.mock
def test_search_issues_reports_an_unknown_team_instead_of_an_empty_list():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=TEAMS_PAYLOAD))
    result = server.search_issues("widget", team="Nope")
    assert len(result) == 1
    assert "GOV" in result[0]["error"] and "PLAT" in result[0]["error"]


@respx.mock
def test_search_issues_reports_an_unknown_state_with_valid_options():
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=STATES_PAYLOAD),
        ]
    )
    result = server.search_issues("widget", team="GOV", state="Shipped")
    assert "In Progress" in result[0]["error"]


@respx.mock
def test_search_issues_reports_an_unknown_assignee_with_valid_options():
    respx.post(LINEAR_API_URL).mock(return_value=httpx.Response(200, json=USERS_PAYLOAD))
    result = server.search_issues("widget", assignee="nobody")
    assert "pius" in result[0]["error"]


@respx.mock
def test_search_issues_passes_a_state_through_when_no_team_is_given():
    """Without a team there is no workflow to resolve the state against."""
    import json

    route = respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issueSearch": {"nodes": []}}})
    )
    server.search_issues("widget", state="In Progress")
    variables = json.loads(route.calls.last.request.content)["variables"]
    assert variables["filter"] == {"state": {"name": {"eq": "In Progress"}}}
    assert route.call_count == 1


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


ISSUE_UUID_PAYLOAD = {
    "data": {"issues": {"nodes": [{"id": "uuid-1", "identifier": "GOV-123"}]}}
}

COMMENTS_PAYLOAD = {
    "data": {
        "issue": {
            "comments": {
                "nodes": [
                    {
                        "body": "Looks good.",
                        "createdAt": "2026-08-03T09:00:00.000Z",
                        "user": {"displayName": "pius"},
                    }
                ]
            }
        }
    }
}


@respx.mock
def test_get_comments_resolves_the_identifier_then_returns_comments():
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=COMMENTS_PAYLOAD),
        ]
    )
    assert server.get_comments("GOV-123") == [
        {"author": "pius", "body": "Looks good.", "created_at": "2026-08-03T09:00:00.000Z"}
    ]


@respx.mock
def test_get_comments_reports_a_missing_issue():
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issues": {"nodes": []}}})
    )
    assert "GOV-999" in server.get_comments("GOV-999")[0]["error"]


@respx.mock
def test_add_comment_posts_the_body_against_the_resolved_uuid():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(
                200,
                json={
                    "data": {
                        "commentCreate": {
                            "success": True,
                            "comment": {
                                "body": "PR is up.",
                                "createdAt": "2026-08-04T09:00:00.000Z",
                                "user": {"displayName": "pius"},
                            },
                        }
                    }
                },
            ),
        ]
    )
    result = server.add_comment("GOV-123", "PR is up.")
    variables = json.loads(route.calls.last.request.content)["variables"]
    assert variables["input"] == {"issueId": "uuid-1", "body": "PR is up."}
    assert result["body"] == "PR is up."
    assert result["author"] == "pius"


@respx.mock
def test_add_comment_rejects_an_empty_body_without_a_network_call():
    route = respx.post(LINEAR_API_URL)
    assert "error" in server.add_comment("GOV-123", "   ")
    assert route.call_count == 0


@respx.mock
def test_add_comment_reports_an_unsuccessful_mutation():
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json={"data": {"commentCreate": {"success": False, "comment": None}}}),
        ]
    )
    assert "error" in server.add_comment("GOV-123", "nope")


CREATED_PAYLOAD = {
    "data": {"issueCreate": {"success": True, "issue": ISSUE_NODE}}
}

UPDATED_PAYLOAD = {
    "data": {"issueUpdate": {"success": True, "issue": ISSUE_NODE}}
}


@respx.mock
def test_create_issue_sends_a_minimal_input():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=CREATED_PAYLOAD),
        ]
    )
    result = server.create_issue(team="GOV", title="Fix the widget")
    variables = json.loads(route.calls.last.request.content)["variables"]
    assert variables["input"] == {"teamId": "team-gov", "title": "Fix the widget"}
    assert result["identifier"] == "GOV-123"


@respx.mock
def test_create_issue_resolves_state_assignee_and_labels_to_uuids():
    import json

    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=STATES_PAYLOAD),
            httpx.Response(200, json=USERS_PAYLOAD),
            httpx.Response(200, json=LABELS_PAYLOAD),
            httpx.Response(200, json=CREATED_PAYLOAD),
        ]
    )
    server.create_issue(
        team="GOV",
        title="Fix the widget",
        description="It is broken.",
        assignee="pius",
        state="In Progress",
        priority=2,
        labels=["bug"],
    )
    variables = json.loads(respx.calls.last.request.content)["variables"]
    assert variables["input"] == {
        "teamId": "team-gov",
        "title": "Fix the widget",
        "description": "It is broken.",
        "stateId": "st-2",
        "assigneeId": "u-1",
        "priority": 2,
        "labelIds": ["lb-1"],
    }


@respx.mock
def test_create_issue_rejects_an_empty_title_without_a_network_call():
    route = respx.post(LINEAR_API_URL)
    assert "error" in server.create_issue(team="GOV", title="  ")
    assert route.call_count == 0


@respx.mock
def test_create_issue_rejects_an_out_of_range_priority():
    route = respx.post(LINEAR_API_URL)
    result = server.create_issue(team="GOV", title="x", priority=9)
    assert "0" in result["error"] and "4" in result["error"]
    assert route.call_count == 0


@respx.mock
def test_create_issue_reports_an_unknown_state_with_valid_options():
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=STATES_PAYLOAD),
        ]
    )
    result = server.create_issue(team="GOV", title="x", state="Shipped")
    assert "In Progress" in result["error"]


@respx.mock
def test_create_issue_reports_an_unsuccessful_mutation():
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json={"data": {"issueCreate": {"success": False, "issue": None}}}),
        ]
    )
    assert "error" in server.create_issue(team="GOV", title="x")


@respx.mock
def test_update_issue_sends_only_the_supplied_fields():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=UPDATED_PAYLOAD),
        ]
    )
    server.update_issue("GOV-123", title="New title")
    variables = json.loads(route.calls.last.request.content)["variables"]
    assert variables == {"id": "uuid-1", "input": {"title": "New title"}}


@respx.mock
def test_update_issue_resolves_state_against_the_issues_own_team():
    """The team is not passed in; it comes from the identifier prefix."""
    import json

    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=STATES_PAYLOAD),
            httpx.Response(200, json=UPDATED_PAYLOAD),
        ]
    )
    server.update_issue("GOV-123", state="In Progress")
    variables = json.loads(respx.calls.last.request.content)["variables"]
    assert variables["input"] == {"stateId": "st-2"}


@respx.mock
def test_update_issue_rejects_a_call_with_nothing_to_change():
    route = respx.post(LINEAR_API_URL)
    assert "error" in server.update_issue("GOV-123")
    assert route.call_count == 0


@respx.mock
def test_update_issue_allows_clearing_the_description_with_an_empty_string():
    import json

    route = respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=UPDATED_PAYLOAD),
        ]
    )
    server.update_issue("GOV-123", description="")
    assert json.loads(route.calls.last.request.content)["variables"]["input"] == {
        "description": ""
    }


@respx.mock
def test_update_issue_resolves_labels_against_the_issues_own_team():
    import json

    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=LABELS_PAYLOAD),
            httpx.Response(200, json=UPDATED_PAYLOAD),
        ]
    )
    server.update_issue("GOV-123", labels=["bug"])
    variables = json.loads(respx.calls.last.request.content)["variables"]
    assert variables == {"id": "uuid-1", "input": {"labelIds": ["lb-1"]}}


@respx.mock
def test_update_issue_clears_labels_with_an_empty_list():
    """`labels=[]` is an explicit clear, not an absent argument."""
    import json

    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=TEAMS_PAYLOAD),
            httpx.Response(200, json=UPDATED_PAYLOAD),
        ]
    )
    server.update_issue("GOV-123", labels=[])
    variables = json.loads(respx.calls.last.request.content)["variables"]
    assert variables["input"] == {"labelIds": []}


@respx.mock
def test_update_issue_resolves_the_assignee_to_a_uuid():
    import json

    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=USERS_PAYLOAD),
            httpx.Response(200, json=UPDATED_PAYLOAD),
        ]
    )
    server.update_issue("GOV-123", assignee="pius")
    variables = json.loads(respx.calls.last.request.content)["variables"]
    assert variables["input"] == {"assigneeId": "u-1"}


@respx.mock
def test_update_issue_rejects_a_blank_assignee_rather_than_reassigning():
    """A blank string used to match any user with a null display name or email."""
    respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=USERS_WITH_NULL_DISPLAY_NAME_PAYLOAD),
        ]
    )
    result = server.update_issue("GOV-123", assignee="")
    assert "empty" in result["error"]


@respx.mock
def test_update_issue_sends_priority_zero():
    """0 is a valid priority (none) and falsy; it must still reach the payload."""
    import json

    route = respx.post(LINEAR_API_URL).mock(
        side_effect=[
            httpx.Response(200, json=ISSUE_UUID_PAYLOAD),
            httpx.Response(200, json=UPDATED_PAYLOAD),
        ]
    )
    server.update_issue("GOV-123", priority=0)
    assert json.loads(route.calls.last.request.content)["variables"]["input"] == {
        "priority": 0
    }


@respx.mock
def test_update_issue_rejects_an_out_of_range_priority():
    route = respx.post(LINEAR_API_URL)
    result = server.update_issue("GOV-123", priority=9)
    assert "0" in result["error"] and "4" in result["error"]
    assert route.call_count == 0


@respx.mock
def test_update_issue_reports_a_missing_issue():
    respx.post(LINEAR_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"issues": {"nodes": []}}})
    )
    assert "GOV-999" in server.update_issue("GOV-999", title="x")["error"]
