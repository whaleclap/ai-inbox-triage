from .base import Provider, ProviderUnavailable
from .mock import MockProvider


def get_provider(name: str, model: str | None = None) -> Provider:
    """Build a provider by name. Raises ProviderUnavailable if it can't run here."""
    if name == "mock":
        return MockProvider()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider, DEFAULT_MODEL

        return AnthropicProvider(model=model or DEFAULT_MODEL)
    if name == "claude-cli":
        from .claude_cli import ClaudeCliProvider

        return ClaudeCliProvider()
    raise ValueError(f"Unknown provider: {name!r} (expected 'anthropic', 'claude-cli', or 'mock')")


__all__ = ["Provider", "ProviderUnavailable", "MockProvider", "get_provider"]
