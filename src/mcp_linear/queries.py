"""GraphQL documents. Strings only, no logic.

Field names below are drawn from Linear's documented schema and have NOT yet been
verified against the live API. The schema probe in `scripts/probe_schema.py`
performs that verification once a LINEAR_API_KEY is available. The three most
likely divergences are: full-text search (`issueSearch(query:)` vs `searchIssues(term:)`),
team-scoped labels (`team { labels }` vs `issueLabels(filter:)`), and the number
comparator type (`Float!` vs `Int!`). If a query starts returning "Cannot query field ...",
re-probe rather than guessing.

`WORKSPACE_LABELS` is unverified on a second axis as well: the root
`issueLabels` connection is assumed to return workspace-wide labels, but it may
also return team-scoped labels belonging to other teams. Label resolution
consults a team's own labels first for that reason, so a team label always wins
over a same-named label found in the workspace scope.
"""

ISSUE_FIELDS = """
fragment IssueFields on Issue {
  identifier
  title
  description
  priority
  url
  branchName
  createdAt
  updatedAt
  state { name }
  assignee { displayName }
  team { key }
  labels { nodes { name } }
}
"""

# `issue(id:)` takes a UUID, so lookup by human identifier goes through a filter
# on team key + issue number. NumberComparator takes a Float.
ISSUE_BY_TEAM_AND_NUMBER = (
    ISSUE_FIELDS
    + """
query IssueByTeamAndNumber($teamKey: String!, $number: Float!) {
  issues(filter: {team: {key: {eq: $teamKey}}, number: {eq: $number}}, first: 1) {
    nodes { ...IssueFields }
  }
}
"""
)

# Same filter, selecting only the UUID — used by Resolver.issue_id for mutations,
# which need the UUID Linear's own mutations require.
ISSUE_UUID_BY_TEAM_AND_NUMBER = """
query IssueUuidByTeamAndNumber($teamKey: String!, $number: Float!) {
  issues(filter: {team: {key: {eq: $teamKey}}, number: {eq: $number}}, first: 1) {
    nodes { id identifier }
  }
}
"""

MY_ISSUES = (
    ISSUE_FIELDS
    + """
query MyIssues($first: Int!) {
  viewer {
    assignedIssues(first: $first, orderBy: updatedAt) {
      nodes { ...IssueFields }
    }
  }
}
"""
)

SEARCH_ISSUES = (
    ISSUE_FIELDS
    + """
query SearchIssues($query: String!, $first: Int!, $filter: IssueFilter) {
  issueSearch(query: $query, first: $first, filter: $filter) {
    nodes { ...IssueFields }
  }
}
"""
)

ISSUE_COMMENTS = """
query IssueComments($id: String!) {
  issue(id: $id) {
    comments(first: 100) {
      nodes { body createdAt user { displayName } }
    }
  }
}
"""

TEAMS = """
query Teams {
  teams(first: 100) { nodes { id key name } }
}
"""

TEAM_STATES = """
query TeamStates($teamId: String!) {
  team(id: $teamId) {
    states(first: 100) { nodes { id name type position } }
  }
}
"""

TEAM_LABELS = """
query TeamLabels($teamId: String!) {
  team(id: $teamId) {
    labels(first: 250) { nodes { id name } }
  }
}
"""

# Workspace-wide labels, the second scope for label resolution. The design's
# match-rules table resolves a label against "team.labels plus workspace labels".
WORKSPACE_LABELS = """
query WorkspaceLabels {
  issueLabels(first: 250) { nodes { id name } }
}
"""

USERS = """
query Users {
  users(first: 250) { nodes { id name displayName email active } }
}
"""

ISSUE_CREATE = (
    ISSUE_FIELDS
    + """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { ...IssueFields }
  }
}
"""
)

ISSUE_UPDATE = (
    ISSUE_FIELDS
    + """
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { ...IssueFields }
  }
}
"""
)

COMMENT_CREATE = """
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { body createdAt user { displayName } }
  }
}
"""
