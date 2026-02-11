"""Factory for creating the appropriate PoolDataProvider."""

from __future__ import annotations

import logging
import os

from src.data.interfaces import PoolDataProvider
from src.data.static_params import StaticDataProvider

logger = logging.getLogger(__name__)


def create_provider(
    use_onchain: bool = False,
    rpc_url: str | None = None,
    cache_ttl: float = 60.0,
) -> PoolDataProvider:
    """Create a data provider, selecting static or on-chain.

    Parameters
    ----------
    use_onchain : bool
        If True, attempt to create an ``OnChainDataProvider``.
    rpc_url : str | None
        Ethereum JSON-RPC URL.  Falls back to the ``ETH_RPC_URL``
        environment variable when not supplied.
    cache_ttl : float
        TTL in seconds for the on-chain cache (default 60).

    Returns
    -------
    PoolDataProvider
        ``OnChainDataProvider`` when requested and available, otherwise
        ``StaticDataProvider``.
    """
    if not use_onchain:
        return StaticDataProvider()

    resolved_url = rpc_url or os.environ.get("ETH_RPC_URL")
    if not resolved_url:
        logger.warning("On-chain data requested but no RPC URL provided; using static data")
        return StaticDataProvider()

    try:
        from src.data.onchain_provider import OnChainDataProvider

        fallback = StaticDataProvider()
        return OnChainDataProvider(
            rpc_url=resolved_url,
            cache_ttl=cache_ttl,
            fallback=fallback,
        )
    except ImportError:
        logger.warning("web3 is not installed; falling back to static data")
        return StaticDataProvider()
    except Exception:
        logger.warning("Failed to create OnChainDataProvider; using static data", exc_info=True)
        return StaticDataProvider()
