"""Tests for the interest rate model."""

import pytest

from src.protocol.interest_rate import InterestRateModel, InterestRateParams

# WETH-like params
WETH_PARAMS = InterestRateParams(
    optimal_utilization=0.92,
    base_rate=0.0,
    slope1=0.027,
    slope2=0.40,
    reserve_factor=0.15,
)


@pytest.fixture
def model() -> InterestRateModel:
    return InterestRateModel(WETH_PARAMS)


class TestVariableBorrowRate:
    def test_rate_at_zero_utilization(self, model: InterestRateModel) -> None:
        assert model.variable_borrow_rate(0.0) == pytest.approx(0.0)

    def test_rate_at_optimal_utilization(self, model: InterestRateModel) -> None:
        rate = model.variable_borrow_rate(0.92)
        assert rate == pytest.approx(0.027, rel=1e-6)

    def test_rate_below_optimal(self, model: InterestRateModel) -> None:
        # At 46% (half of optimal): should be base + 0.5 * slope1
        rate = model.variable_borrow_rate(0.46)
        expected = 0.0 + (0.46 / 0.92) * 0.027
        assert rate == pytest.approx(expected, rel=1e-6)

    def test_rate_above_optimal(self, model: InterestRateModel) -> None:
        # At 96% utilization
        rate = model.variable_borrow_rate(0.96)
        excess = (0.96 - 0.92) / (1.0 - 0.92)
        expected = 0.027 + excess * 0.40
        assert rate == pytest.approx(expected, rel=1e-6)

    def test_rate_at_100_percent(self, model: InterestRateModel) -> None:
        rate = model.variable_borrow_rate(1.0)
        expected = 0.027 + 0.40
        assert rate == pytest.approx(expected, rel=1e-6)

    def test_rate_is_continuous_at_kink(self, model: InterestRateModel) -> None:
        """Rate should be continuous at the optimal utilization point."""
        eps = 1e-10
        rate_below = model.variable_borrow_rate(0.92 - eps)
        rate_at = model.variable_borrow_rate(0.92)
        rate_above = model.variable_borrow_rate(0.92 + eps)
        assert rate_below == pytest.approx(rate_at, abs=1e-6)
        assert rate_above == pytest.approx(rate_at, abs=1e-6)

    def test_rate_monotonically_increasing(self, model: InterestRateModel) -> None:
        prev = -1.0
        for u in [i / 100 for i in range(101)]:
            rate = model.variable_borrow_rate(u)
            assert rate >= prev
            prev = rate


class TestSupplyRate:
    def test_supply_rate_at_zero(self, model: InterestRateModel) -> None:
        assert model.supply_rate(0.0) == pytest.approx(0.0)

    def test_supply_rate_formula(self, model: InterestRateModel) -> None:
        u = 0.5
        borrow = model.variable_borrow_rate(u)
        expected = borrow * u * (1.0 - 0.15)
        assert model.supply_rate(u) == pytest.approx(expected, rel=1e-6)

    def test_supply_rate_less_than_borrow(self, model: InterestRateModel) -> None:
        for u in [0.1, 0.5, 0.92, 0.99]:
            assert model.supply_rate(u) < model.variable_borrow_rate(u)


class TestRateCurve:
    def test_curve_shape(self, model: InterestRateModel) -> None:
        df = model.rate_curve(n_points=100)
        assert len(df) == 100
        assert list(df.columns) == ["utilization", "borrow_rate", "supply_rate"]
        assert df["utilization"].iloc[0] == pytest.approx(0.0)
        assert df["utilization"].iloc[-1] == pytest.approx(1.0)


class TestWithDifferentParams:
    def test_wsteth_params(self) -> None:
        params = InterestRateParams(
            optimal_utilization=0.80,
            base_rate=0.0,
            slope1=0.01,
            slope2=0.40,
            reserve_factor=0.35,
        )
        model = InterestRateModel(params)
        assert model.variable_borrow_rate(0.80) == pytest.approx(0.01, rel=1e-6)
        assert model.variable_borrow_rate(0.0) == pytest.approx(0.0)

    def test_nonzero_base_rate(self) -> None:
        params = InterestRateParams(
            optimal_utilization=0.80,
            base_rate=0.02,
            slope1=0.05,
            slope2=0.50,
            reserve_factor=0.10,
        )
        model = InterestRateModel(params)
        assert model.variable_borrow_rate(0.0) == pytest.approx(0.02)
        assert model.variable_borrow_rate(0.80) == pytest.approx(0.07)
