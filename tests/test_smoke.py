from mcp_linear import server


def test_server_exposes_a_named_mcp_instance():
    assert server.mcp.name == "Linear"


def test_main_is_callable():
    assert callable(server.main)
