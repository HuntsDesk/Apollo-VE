import inspect

import pytest

import auth.service_decorator as service_decorator
import core.server as server_module
from core.server import SecureFastMCP


def _sample_sig():
    def sample_tool(user_google_email: str, query: str = "default") -> str:
        return query

    return inspect.signature(sample_tool)


def _result_text(result) -> str:
    return result.content[0].text


def test_extract_oauth20_user_email_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(service_decorator, "_ENV_USER_EMAIL", "configured@example.com")
    kwargs = {}

    user_google_email = service_decorator._extract_oauth20_user_email(
        (), kwargs, _sample_sig()
    )

    assert user_google_email == "configured@example.com"
    assert kwargs["user_google_email"] == "configured@example.com"


def test_extract_oauth20_user_email_raises_without_arg_or_env(monkeypatch):
    monkeypatch.setattr(service_decorator, "_ENV_USER_EMAIL", None)

    with pytest.raises(Exception, match="user_google_email"):
        service_decorator._extract_oauth20_user_email((), {}, _sample_sig())


@pytest.mark.asyncio
async def test_list_tools_marks_user_google_email_optional_when_default_configured(
    monkeypatch,
):
    monkeypatch.setattr(server_module, "USER_GOOGLE_EMAIL", "configured@example.com")
    monkeypatch.setattr(server_module, "is_oauth21_enabled", lambda: False)

    server = SecureFastMCP(name="test_server")

    def echo_email(user_google_email: str) -> str:
        return user_google_email

    server.tool()(echo_email)

    tool = next(
        t
        for t in await server.list_tools(run_middleware=False)
        if t.name == "echo_email"
    )

    assert "user_google_email" not in tool.parameters.get("required", [])
    assert (
        tool.parameters["properties"]["user_google_email"]["default"]
        == "configured@example.com"
    )


@pytest.mark.asyncio
async def test_list_tools_leaves_schema_unchanged_without_default(monkeypatch):
    monkeypatch.setattr(server_module, "USER_GOOGLE_EMAIL", None)
    monkeypatch.setattr(server_module, "is_oauth21_enabled", lambda: False)

    server = SecureFastMCP(name="test_server")

    def echo_email(user_google_email: str) -> str:
        return user_google_email

    server.tool()(echo_email)

    tool = next(
        t
        for t in await server.list_tools(run_middleware=False)
        if t.name == "echo_email"
    )

    assert "user_google_email" in tool.parameters.get("required", [])
    assert tool.parameters["properties"]["user_google_email"].get("default") is None


@pytest.mark.asyncio
async def test_call_tool_injects_default_email_before_validation(monkeypatch):
    monkeypatch.setattr(server_module, "USER_GOOGLE_EMAIL", "configured@example.com")
    monkeypatch.setattr(server_module, "is_oauth21_enabled", lambda: False)

    server = SecureFastMCP(name="test_server")

    def echo_email(user_google_email: str) -> str:
        return user_google_email

    server.tool()(echo_email)

    result = await server.call_tool("echo_email", None)

    assert _result_text(result) == "configured@example.com"
