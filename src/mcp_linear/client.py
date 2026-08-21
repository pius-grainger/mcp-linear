import httpx

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearClient:
    """Posts GraphQL documents to Linear. The only module that touches the network."""

    def __init__(self, api_key: str, url: str = LINEAR_API_URL, timeout: float = 30.0):
        self._url = url
        # Linear personal API keys are sent raw. A "Bearer " prefix fails auth.
        self._client = httpx.Client(
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            timeout=timeout,
        )

    def execute(self, query: str, variables: dict | None = None) -> dict:
        """Return the GraphQL `data` dict, or a dict with an "error" key on failure."""
        try:
            resp = self._client.post(
                self._url, json={"query": query, "variables": variables or {}}
            )
        except httpx.RequestError as e:
            return {"error": f"Linear request failed: {e}"}

        if resp.status_code >= 400:
            return {"error": f"Linear API error {resp.status_code}: {resp.text}"}

        try:
            payload = resp.json()
        except ValueError:
            return {"error": f"Linear returned a non-JSON response: {resp.text[:200]}"}

        if not isinstance(payload, dict):
            payload_repr = repr(payload)[:200]
            return {"error": f"Linear returned an unexpected response shape: {payload_repr}"}

        # Linear reports most failures as HTTP 200 with a top-level errors array.
        if payload.get("errors"):
            messages = "; ".join(
                e.get("message", str(e)) for e in payload["errors"]
            )
            return {"error": messages, "details": payload["errors"]}

        data = payload.get("data")
        if data is None:
            return {"error": "Linear returned no data"}
        # Callers treat `data` as a dict and probe it with `"error" in data`. A
        # list or string here would either raise AttributeError past the tool
        # boundary or silently take the error branch on a substring match.
        if not isinstance(data, dict):
            data_repr = repr(data)[:200]
            return {"error": f"Linear returned an unexpected response shape: {data_repr}"}
        return data
