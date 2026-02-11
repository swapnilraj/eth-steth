"""Contract addresses and minimal ABIs for Aave V3 on-chain data fetching."""

# ---------------------------------------------------------------------------
# Asset addresses (Ethereum mainnet)
# ---------------------------------------------------------------------------
ASSET_ADDRESSES: dict[str, str] = {
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "wstETH": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
}

# ---------------------------------------------------------------------------
# Aave V3 contract addresses
# ---------------------------------------------------------------------------
AAVE_POOL_DATA_PROVIDER = "0x0a16f2FCC0D44FaE41cc54e079281D84A363bECD"
AAVE_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
AAVE_ORACLE = "0x54586bE62E3c3580375aE3723C145253060Ca0C2"

# ---------------------------------------------------------------------------
# Chainlink / Lido
# ---------------------------------------------------------------------------
CHAINLINK_STETH_ETH_FEED = "0x86392dC19c0b719886221c78AB11eb8Cf5c52812"
WSTETH_CONTRACT = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"

# ---------------------------------------------------------------------------
# Minimal ABIs — only the view functions we call
# ---------------------------------------------------------------------------

POOL_DATA_PROVIDER_ABI = [
    {
        "inputs": [{"name": "asset", "type": "address"}],
        "name": "getReserveConfigurationData",
        "outputs": [
            {"name": "decimals", "type": "uint256"},
            {"name": "ltv", "type": "uint256"},
            {"name": "liquidationThreshold", "type": "uint256"},
            {"name": "liquidationBonus", "type": "uint256"},
            {"name": "reserveFactor", "type": "uint256"},
            {"name": "usageAsCollateralEnabled", "type": "bool"},
            {"name": "borrowingEnabled", "type": "bool"},
            {"name": "stableBorrowRateEnabled", "type": "bool"},
            {"name": "isActive", "type": "bool"},
            {"name": "isFrozen", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [
            {"name": "unbacked", "type": "uint256"},
            {"name": "accruedToTreasuryScaled", "type": "uint256"},
            {"name": "totalAToken", "type": "uint256"},
            {"name": "totalStableDebt", "type": "uint256"},
            {"name": "totalVariableDebt", "type": "uint256"},
            {"name": "liquidityRate", "type": "uint256"},
            {"name": "variableBorrowRate", "type": "uint256"},
            {"name": "stableBorrowRate", "type": "uint256"},
            {"name": "averageStableBorrowRate", "type": "uint256"},
            {"name": "liquidityIndex", "type": "uint256"},
            {"name": "variableBorrowIndex", "type": "uint256"},
            {"name": "lastUpdateTimestamp", "type": "uint40"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "asset", "type": "address"}],
        "name": "getInterestRateStrategyAddress",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

POOL_ABI = [
    {
        "inputs": [{"name": "id", "type": "uint8"}],
        "name": "getEModeCategoryData",
        "outputs": [
            {
                "components": [
                    {"name": "ltv", "type": "uint16"},
                    {"name": "liquidationThreshold", "type": "uint16"},
                    {"name": "liquidationBonus", "type": "uint16"},
                    {"name": "priceSource", "type": "address"},
                    {"name": "label", "type": "string"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

ORACLE_ABI = [
    {
        "inputs": [{"name": "asset", "type": "address"}],
        "name": "getAssetPrice",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "BASE_CURRENCY_UNIT",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Aave V3.2 rate strategy — getInterestRateDataBps(address reserve) with bps values
RATE_STRATEGY_ABI_V3 = [
    {
        "inputs": [{"name": "reserve", "type": "address"}],
        "name": "getInterestRateDataBps",
        "outputs": [
            {
                "components": [
                    {"name": "optimalUsageRatio", "type": "uint16"},
                    {"name": "baseVariableBorrowRate", "type": "uint32"},
                    {"name": "variableRateSlope1", "type": "uint32"},
                    {"name": "variableRateSlope2", "type": "uint32"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

# Aave V3.0/V3.1 rate strategy — returns a struct via getInterestRateData()
RATE_STRATEGY_ABI_V2 = [
    {
        "inputs": [],
        "name": "getInterestRateData",
        "outputs": [
            {
                "components": [
                    {"name": "optimalUsageRatio", "type": "uint256"},
                    {"name": "baseVariableBorrowRate", "type": "uint256"},
                    {"name": "variableRateSlope1", "type": "uint256"},
                    {"name": "variableRateSlope2", "type": "uint256"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

# Older Aave V3 rate strategy — individual RAY-returning getters
RATE_STRATEGY_ABI_V1 = [
    {
        "inputs": [],
        "name": "OPTIMAL_USAGE_RATIO",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getBaseVariableBorrowRate",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getVariableRateSlope1",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getVariableRateSlope2",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

CHAINLINK_FEED_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

WSTETH_ABI = [
    {
        "inputs": [],
        "name": "stEthPerToken",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]
