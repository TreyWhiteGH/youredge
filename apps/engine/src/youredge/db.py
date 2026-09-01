import logging
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from youredge.config import get_settings

log = logging.getLogger(__name__)

_engine = None
_session_factory = None

# Hosted Postgres hands out libpq connection strings, and asyncpg accepts a
# different vocabulary. A URL pasted from Neon, Supabase or RDS therefore fails
# on connect with "connect() got an unexpected keyword argument", naming
# whichever parameter it happened to reach first.
#
# The first version of this translated ?sslmode= and stopped there, which was
# fixing one instance of a general problem: Neon also appends
# ?channel_binding=require, so the same failure simply moved along one
# parameter. These are dropped as a set, and what was dropped is logged rather
# than discarded silently -- a connection string quietly losing half its options
# is worse than one that fails loudly.
_TLS_MODES = {"require", "verify-ca", "verify-full", "prefer", "allow"}

# Understood by libpq, not by asyncpg. TLS is expressed through the `ssl`
# argument instead, which _split_ssl sets when the mode calls for it.
_LIBPQ_ONLY = {
    "channel_binding", "sslcert", "sslkey", "sslrootcert", "sslcrl",
    "gssencmode", "krbsrvname", "target_session_attrs",
}


def _split_ssl(url: str) -> tuple[str, dict]:
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query))
    mode = params.pop("sslmode", None) or params.pop("ssl", None)
    dropped = [k for k in list(params) if k in _LIBPQ_ONLY]
    for k in dropped:
        params.pop(k)
    if dropped:
        log.info("dropped libpq-only connection parameters asyncpg cannot take: %s",
                 ", ".join(sorted(dropped)))
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
