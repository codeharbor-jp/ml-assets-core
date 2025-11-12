from datetime import datetime, timedelta, timezone

from domain.models.signal import Signal, SignalLeg, TradeSide
from domain.services import (
    LabelingConfig,
    PositionSizingConfig,
    ProportionalPositionSizingService,
    RiskConfig,
    RuleBasedLabelingService,
    RuleBasedRiskAssessmentService,
)
from domain.services.interfaces import LabelingInput, PositionSizingRequest, RiskAssessmentRequest
from domain.models import DatasetPartition


def make_partition() -> DatasetPartition:
    return DatasetPartition(
        timeframe="1h",
        symbol="EUR/USD",
        year=2024,
        month=5,
        last_timestamp=datetime(2024, 5, 31, 23, tzinfo=timezone.utc),
        bars_written=100,
        missing_gaps=0,
        outlier_bars=0,
        spike_flags=0,
        quarantine_flag=False,
        data_hash="hash",
    )


def test_rule_based_labeling_service_generates_expected_labels() -> None:
    service = RuleBasedLabelingService(LabelingConfig(ai1_lookahead=5))
    features = [
        {
            "z": 2.4,
            "delta_z_ema": 0.05,
            "rho_var_180": 0.01,
            "atr_ratio": 1.0,
            "drawdown_recent": 0.02,
        },
        {
            "z": 1.5,
            "delta_z_ema": 0.03,
            "rho_var_180": 0.03,
            "atr_ratio": 2.0,
            "drawdown_recent": 0.05,
        },
        {
            "z": 0.4,
            "delta_z_ema": 0.01,
            "rho_var_180": 0.01,
            "atr_ratio": 1.1,
            "drawdown_recent": 0.02,
        },
    ]

    result = service.generate(LabelingInput(partition=make_partition(), features=features))

    assert result.ai1_labels == [1, 0, 0]
    assert result.ai2_labels == [0, 1, 0]
    assert result.ai3_targets[0] == 0.5  # (1 + 0) / 2 -> 0.5 risk factor -> 0.5 target
    assert result.calibration_metrics.sample_size == 3


def test_rule_based_risk_assessment_flags_conditions() -> None:
    service = RuleBasedRiskAssessmentService(RiskConfig())
    signal = Signal(
        signal_id="sig-1",
        timestamp=datetime.now(timezone.utc),
        pair_id="EURUSD",
        legs=[
            SignalLeg(symbol="EURUSD", side=TradeSide.LONG, beta_weight=1.0, notional=1000.0),
            SignalLeg(symbol="GBPUSD", side=TradeSide.SHORT, beta_weight=-1.0, notional=1000.0),
        ],
        return_prob=0.7,
        risk_score=0.2,
        theta1=0.65,
        theta2=0.3,
        position_scale=1.0,
        model_version="20240101_0000_abcd",
        valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    metrics = {
        "rho_var_180": 0.03,
        "atr_ratio": 1.5,
        "delta_z_ema": 0.2,
        "drawdown_recent": 0.02,
    }

    result = service.evaluate(RiskAssessmentRequest(signal=signal, metrics=metrics))

    assert result.flags["rho_var"] is True
    assert result.flags["speed"] is True
    assert result.flags["atr_ratio"] is False
    assert 0.0 < result.risk_score <= 1.0


def test_position_sizing_uses_risk_score_and_constraints() -> None:
    service = ProportionalPositionSizingService(PositionSizingConfig(base_position=1.0))
    signal = Signal(
        signal_id="sig-1",
        timestamp=datetime.now(timezone.utc),
        pair_id="EURUSD",
        legs=[SignalLeg(symbol="EURUSD", side=TradeSide.LONG, beta_weight=1.0, notional=1000.0)],
        return_prob=0.8,
        risk_score=0.25,
        theta1=0.7,
        theta2=0.3,
        position_scale=1.0,
        model_version="20240101_0000_abcd",
        valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    request = PositionSizingRequest(
        signal=signal,
        account_state={"equity": 100000.0},
        risk_parameters={"max_leverage": 1.2, "volatility": 1.0},
    )

    scale = service.calculate(request)

    assert service._config.min_position_scale <= scale <= 1.2
    assert scale < 1.0  # リスクスコアにより縮小される

