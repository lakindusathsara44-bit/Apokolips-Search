"""A DNS resolver that prevents connections to private and special-use IP ranges."""
from aiohttp.abc import AbstractResolver
from aiohttp.resolver import DefaultResolver

from .safety import validate_resolved_addresses


class PublicOnlyResolver(AbstractResolver):
    """Resolve hostnames and reject the whole answer if any address is non-public."""
    def __init__(self) -> None:
        self._delegate = DefaultResolver()

    async def resolve(self, host: str, port: int = 0, family: int = 0) -> list[dict]:
        records = await self._delegate.resolve(host, port, family)
        validate_resolved_addresses(records)
        return records

    async def close(self) -> None:
        await self._delegate.close()
