from mcp_linear import format as fmt

FULL_ISSUE = {
    "id": "uuid-1",
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
    "labels": {"nodes": [{"name": "bug"}, {"name": "backend"}]},
}


def test_issue_flattens_every_field():
    assert fmt.issue(FULL_ISSUE) == {
        "identifier": "GOV-123",
        "title": "Fix the widget",
        "description": "It is broken.",
        "state": "In Progress",
        "assignee": "pius",
        "team": "GOV",
        "priority": 2,
        "labels": ["bug", "backend"],
        "url": "https://linear.app/acme/issue/GOV-123",
        "branch_name": "pius/gov-123-fix-the-widget",
        "created_at": "2026-08-01T10:00:00.000Z",
        "updated_at": "2026-08-02T11:00:00.000Z",
    }


def test_issue_never_leaks_a_uuid():
    assert "uuid-1" not in str(fmt.issue(FULL_ISSUE))
    assert "id" not in fmt.issue(FULL_ISSUE)


def test_issue_handles_an_unassigned_issue_with_no_labels():
    node = {**FULL_ISSUE, "assignee": None, "labels": {"nodes": []}}
    result = fmt.issue(node)
    assert result["assignee"] is None
    assert result["labels"] == []


def test_issue_turns_a_null_description_into_an_empty_string():
    assert fmt.issue({**FULL_ISSUE, "description": None})["description"] == ""


def test_issue_tolerates_missing_nested_objects():
    result = fmt.issue({"identifier": "GOV-1", "title": "Bare"})
    assert result["state"] is None
    assert result["team"] is None
    assert result["labels"] == []


def test_comment_flattens_author_body_and_timestamp():
    node = {
        "id": "c1",
        "body": "Looks good.",
        "createdAt": "2026-08-03T09:00:00.000Z",
        "user": {"displayName": "pius"},
    }
    assert fmt.comment(node) == {
        "author": "pius",
        "body": "Looks good.",
        "created_at": "2026-08-03T09:00:00.000Z",
    }


def test_comment_handles_a_bot_comment_with_no_user():
    assert fmt.comment({"body": "auto", "createdAt": "x", "user": None})["author"] is None


def test_nodes_unwraps_a_connection():
    assert fmt.nodes({"nodes": [{"a": 1}]}) == [{"a": 1}]


def test_nodes_returns_an_empty_list_for_none_or_missing():
    assert fmt.nodes(None) == []
    assert fmt.nodes({}) == []
