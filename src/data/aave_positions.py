"""Fetch Aave V3 wstETH/WETH borrowing positions from The Graph subgraph."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Aave V3 Ethereum mainnet subgraph (The Graph decentralized network)
AAVE_V3_SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"

# Token addresses (lowercase for subgraph queries)
WSTETH_ADDRESS = "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"
WETH_ADDRESS = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


@dataclass(frozen=True)
class AavePosition:
    """A single Aave V3 position with wstETH collateral and WETH debt."""

    user: str
    collateral_wsteth: float  # wstETH collateral amount
    debt_weth: float          # WETH variable debt amount
    health_factor: float      # Computed HF (may be approximate)


def _build_subgraph_url(api_key: str | None = None) -> str:
    """Build the subgraph query URL."""
    key = api_key or os.environ.get("THEGRAPH_API_KEY", "")
    if key:
        return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{AAVE_V3_SUBGRAPH_ID}"
    # Fallback to free hosted service (rate-limited)
    return f"https://api.thegraph.com/subgraphs/id/{AAVE_V3_SUBGRAPH_ID}"


def _query_subgraph(url: str, query: str, variables: dict | None = None) -> dict:
    """Execute a GraphQL query against the subgraph."""
    import requests

    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"Subgraph query error: {data['errors']}")

    return data["data"]


def fetch_aave_positions(
    wsteth_price: float = 1.18,
    liquidation_threshold: float = 0.955,
    api_key: str | None = None,
    min_debt_eth: float = 0.1,
) -> list[AavePosition]:
    """Fetch all wstETH/WETH positions from the Aave V3 subgraph.

    Queries users who have both wstETH as collateral and WETH as variable
    debt. Computes an approximate health factor for each position.

    Args:
        wsteth_price: Current wstETH/ETH price for HF computation.
        liquidation_threshold: Liquidation threshold (0.955 for E-mode).
        api_key: The Graph API key (falls back to THEGRAPH_API_KEY env var).
        min_debt_eth: Minimum WETH debt to include (filters dust positions).

    Returns:
        List of AavePosition sorted by health factor (ascending).
    """
    url = _build_subgraph_url(api_key)

    # Query: get all users with wstETH supply or WETH debt
    # We paginate with first/skip to handle large result sets
    query = """
    query GetPositions($first: Int!, $skip: Int!) {
        userReserves(
            first: $first,
            skip: $skip,
            where: {
                currentVariableDebt_gt: "0"
            }
        ) {
            user {
                id
            }
            reserve {
                symbol
                underlyingAsset
            }
            currentATokenBalance
            currentVariableDebt
        }
    }
    """

    all_reserves: list[dict] = []
    skip = 0
    batch_size = 1000

    while True:
        try:
            data = _query_subgraph(url, query, {"first": batch_size, "skip": skip})
        except Exception:
            logger.warning("Subgraph query failed at skip=%d", skip, exc_info=True)
            break

        reserves = data.get("userReserves", [])
        if not reserves:
            break

        all_reserves.extend(reserves)
        if len(reserves) < batch_size:
            break
        skip += batch_size

    if not all_reserves:
        logger.warning("No positions returned from subgraph")
        return []

    # Group by user: collect wstETH collateral and WETH debt
    user_data: dict[str, dict[str, float]] = {}
    for reserve in all_reserves:
        user_id = reserve["user"]["id"]
        symbol = reserve["reserve"]["symbol"]
        underlying = reserve["reserve"]["underlyingAsset"].lower()

        if user_id not in user_data:
            user_data[user_id] = {"collateral": 0.0, "debt": 0.0}

        if underlying == WSTETH_ADDRESS:
            balance = float(reserve["currentATokenBalance"]) / 1e18
            user_data[user_id]["collateral"] += balance
        elif underlying == WETH_ADDRESS:
            debt = float(reserve["currentVariableDebt"]) / 1e18
            user_data[user_id]["debt"] += debt

    # Build position list with HF
    positions: list[AavePosition] = []
    for user_id, data in user_data.items():
        collateral = data["collateral"]
        debt = data["debt"]

        if debt < min_debt_eth or collateral <= 0:
            continue

        collateral_value = collateral * wsteth_price
        hf = (collateral_value * liquidation_threshold) / debt if debt > 0 else float("inf")

        positions.append(
            AavePosition(
                user=user_id,
                collateral_wsteth=collateral,
                debt_weth=debt,
                health_factor=hf,
            )
        )

    # Sort by HF ascending (most at-risk first)
    positions.sort(key=lambda p: p.health_factor)

    logger.info("Fetched %d wstETH/WETH positions from Aave V3 subgraph", len(positions))
    return positions
