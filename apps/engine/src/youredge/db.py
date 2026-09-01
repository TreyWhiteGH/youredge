from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from youredge.config import get_settings

_engine = None
_session_factory = None

# libpq spells TLS as ?sslmode=require and asyncpg does not accept it -- it takes
# an `ssl` argument instead, and chokes on the query parameter. Every hosted
# Postgres hands out a libpq URL, so a connection string pasted from Neon,
# Supabase or RDS fails on connect with an unhelpful "unexpected keyword".
# Translated here rather than at every call site, and rather than asking whoever
# deploys this to hand-edit a URL the provider gave them.
_TLS_MODES = {"require", "verify-ca", "verify-full", "prefer", "allow"}


def _split_ssl(url: str) -> tuple[str, dict]:
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query))
    mode = params.pop("sslmode", None) or params.pop("ssl", None)
    cleaned = urlunsplit(parts._replace(query=urlencode(params)))
    if mode in _TLS_MODES and mode not in ("prefer", "allow"):
        return cleaned, {"ssl": True}
    return cleaned, {}


def get_engine():
    global _engine
    if _engine is None:
        url, connect_args = _split_ssl(get_settings().database_url)
        _engine = create_async_engine(
            url, pool_pre_ping=True, connect_args=connect_args,
            # A hosted database is a network hop away and will drop idle
            # connections; a local one never does, so this only ever mattered
            # once the database stopped living in the same compose file.
            pool_recycle=1800,
        )
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
