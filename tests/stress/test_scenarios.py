"""Tests for stress scenario definitions."""

from src.stress.scenarios import (
    HISTORICAL_SCENARIOS,
    JUNE_2022_DEPEG,
    MARCH_2020_BLACK_THURSDAY,
    MAY_2022_TERRA_LUNA,
    StressScenario,
    create_custom_scenario,
)


class TestStressScenario:
    def test_frozen(self) -> None:
        scenario = JUNE_2022_DEPEG
        try:
            scenario.eth_price_change = -0.50  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass

    def test_historical_scenarios_count(self) -> None:
        assert len(HISTORICAL_SCENARIOS) == 3

    def test_june_2022_depeg(self) -> None:
        s = JUNE_2022_DEPEG
        assert s.eth_price_change == -0.40
        assert s.steth_peg == 0.93
        assert s.utilization_shock == 0.95
        assert s.duration_days == 14

    def test_march_2020_black_thursday(self) -> None:
        s = MARCH_2020_BLACK_THURSDAY
        assert s.eth_price_change == -0.50
        assert s.steth_peg == 0.98
        assert s.utilization_shock == 0.98

    def test_may_2022_terra(self) -> None:
        s = MAY_2022_TERRA_LUNA
        assert s.eth_price_change == -0.35
        assert s.steth_peg == 0.95

    def test_create_custom_scenario(self) -> None:
        s = create_custom_scenario(
            name="Test",
            eth_price_change=-0.25,
            steth_peg=0.90,
            utilization_shock=0.99,
            duration_days=5,
        )
        assert isinstance(s, StressScenario)
        assert s.name == "Test"
        assert s.eth_price_change == -0.25
        assert s.steth_peg == 0.90
        assert s.utilization_shock == 0.99
        assert s.duration_days == 5

    def test_all_scenarios_have_negative_eth_change(self) -> None:
        for s in HISTORICAL_SCENARIOS:
            assert s.eth_price_change < 0

    def test_all_scenarios_have_peg_at_or_below_one(self) -> None:
        for s in HISTORICAL_SCENARIOS:
            assert s.steth_peg <= 1.0
