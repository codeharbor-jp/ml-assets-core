from datetime import datetime, timedelta, timezone

import pytest

from domain.models.signal import Signal, SignalLeg, TradeSide


def test_signal_leg_validation() -> None:
    with pytest.raises(ValueError):
        SignalLeg(symbol="", side=TradeSide.LONG, beta_weight=1.0, notional=1000.0)

    with pytest.raises(ValueError):
        SignalLeg(symbol="EURUSD", side=TradeSide.LONG, beta_weight=1.0, notional=0.0)


def test_signal_validation_success() -> None:
    now = datetime.now(timezone.utc)
    leg = SignalLeg(symbol="EURUSD", side=TradeSide.LONG, beta_weight=1.0, notional=1000.0)
    signal = Signal(
        signal_id="sig-1",
        timestamp=now,
        pair_id="EURUSD_GBPUSD",
        legs=[leg],
        return_prob=0.7,
        risk_score=0.2,
        theta1=0.65,
        theta2=0.3,
        position_scale=1.0,
        model_version="20240101_0000_abcd",
        valid_until=now + timedelta(minutes=5),
    )

    assert signal.signal_id == "sig-1"
    assert signal.legs[0].symbol == "EURUSD"


def test_signal_invalid_probability() -> None:
    now = datetime.now(timezone.utc)
    leg = SignalLeg(symbol="EURUSD", side=TradeSide.LONG, beta_weight=1.0, notional=1000.0)

    with pytest.raises(ValueError):
        Signal(
            signal_id="sig-1",
            timestamp=now,
            pair_id="EURUSD_GBPUSD",
            legs=[leg],
            return_prob=1.5,
            risk_score=0.2,
            theta1=0.65,
            theta2=0.3,
            position_scale=1.0,
            model_version="20240101_0000_abcd",
            valid_until=now + timedelta(minutes=5),
        )

