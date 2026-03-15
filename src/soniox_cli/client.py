from soniox import SonioxClient

from soniox_cli.config import require_api_key

_client: SonioxClient | None = None


def get_client() -> SonioxClient:
    global _client
    if _client is None:
        _client = SonioxClient(api_key=require_api_key())
    return _client


def reset_client() -> None:
    global _client
    _client = None
