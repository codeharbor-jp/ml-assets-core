"""
ランタイム依存関係のビルダー。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence, cast

from application.services import Backtester, ThetaOptimizer
from application.services.analytics import AnalyticsService
from application.services.feature_builder import FeatureBuilder, FeatureBuilderConfig
from application.services.trainer import Trainer, TrainerService
from application.services.theta_optimizer import ThetaOptimizationPlan
from application.usecases.configs import ConfigManagementService, ConfigManagementUseCase
from application.usecases.learning import LearningService, LearningUseCase
from application.usecases.ops import LoggingOpsAuditLogger, OpsService, OpsUseCase
from application.usecases.publish import ModelPublishService, NotificationService
from domain import ThetaRange
from domain.services import LabelingConfig, RuleBasedLabelingService
from infrastructure import (
    BacktestEngineHttpClient,
    BacktestEngineSettings,
    BacktestPolicy,
    BacktestRequestFactory,
    ConfigRepository,
    DeltaConstraintEvaluator,
    DataAssetsFeatureCache,
    DataAssetsFeatureGenerator,
    HistoricalThetaScorer,
    JsonSchemaRegistry,
    JsonFeatureHasher,
    LocalFileSystemStorageClient,
    PostgresConfig,
    PostgresConnectionProvider,
    PostgresMetricsRepository,
    PostgresRegistryUpdater,
    RandomOptunaStrategy,
    SlackConfig,
    SlackWebhookNotifier,
    ThresholdStressEvaluator,
    UniformGridSearchStrategy,
)
from infrastructure.cache.analytics import RedisAnalyticsCache
from infrastructure.configs.config_api_client import ConfigAPIClient, ConfigAPISettings
from infrastructure.messaging.redis_backend import RedisMessagingConfig, RedisOpsFlagRepository, RedisPublisherImpl
from infrastructure.notifications import (
    CompositePublishNotificationService,
    NoopNotificationService,
    PagerDutyConfig,
    PagerDutyNotifier,
)
from infrastructure.repositories import PostgresAuditLogger
from infrastructure.repositories.analytics import PostgresAnalyticsRepository
from infrastructure.storage.model_repository import ModelArtifactDistributor
from infrastructure.storage.path_resolver import StoragePathResolver
from infrastructure.storage.worm_archive import WormArchiveWriter
from infrastructure.theta import ThetaRequestFactory
from infrastructure.training import (
    LocalModelArtifactBuilder,
    LogisticModelTrainer,
    RollingTimeSeriesCV,
    SimpleThetaEstimator,
)
from redis import Redis

from infrastructure.notifications import (
    CompositePublishNotificationService,
    NoopNotificationService,
    PagerDutyConfig,
    PagerDutyNotifier,
)
from infrastructure.storage.model_repository import ModelArtifactDistributor
from infrastructure.storage.path_resolver import StoragePathResolver
from infrastructure.storage.worm_archive import WormArchiveWriter
from infrastructure.theta import ThetaRequestFactory


@dataclass(frozen=True)
class BacktestComponents:
    service: Backtester
    policy: BacktestPolicy
    request_factory: BacktestRequestFactory


@dataclass(frozen=True)
class ThetaComponents:
    service: ThetaOptimizer
    request_factory: ThetaRequestFactory


@dataclass(frozen=True)
class PublishComponents:
    service: ModelPublishService
    registry_updater: PostgresRegistryUpdater


@dataclass(frozen=True)
class LearningComponents:
    usecase: LearningUseCase
    trainer: TrainerService


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _environment() -> str:
    return os.getenv("SERVICE_ENV", "dev")


@lru_cache(maxsize=1)
def _config_repository() -> ConfigRepository:
    root = _project_root()
    schema_root = root / "configs" / "schemas"
    registry = JsonSchemaRegistry(schema_root)
    return ConfigRepository(root, registry)


def _section(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = mapping.get(key)
    if isinstance(value, Mapping):
        return value
    return mapping


def build_backtest_components(environment: str | None = None) -> BacktestComponents:
    env = environment or _environment()
    repo = _config_repository()

    engine_raw = repo.load("backtest_engine", environment=env)
    engine_settings = BacktestEngineSettings.from_mapping(_section(engine_raw, "backtest_engine"))
    engine_client = BacktestEngineHttpClient(engine_settings)

    policy_raw = repo.load("backtest_policy", environment=env)
    policy = BacktestPolicy.from_mapping(policy_raw)

    stress_evaluator = ThresholdStressEvaluator(policy.evaluation)
    service = Backtester(engine_client, stress_evaluator)
    request_factory = BacktestRequestFactory(policy=policy)
    return BacktestComponents(service=service, policy=policy, request_factory=request_factory)


def _to_float(value: object, *, default: float | None = None, name: str = "value") -> float:
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"{name} が指定されていません。")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            value_str: str = value
            return float(value_str)
        except ValueError as exc:
            if default is not None:
                return default
            raise ValueError(f"{name} は数値である必要があります。") from exc
    if default is not None:
        return default
    raise ValueError(f"{name} は数値である必要があります。")


def _to_int(value: object, *, default: int | None = None, name: str = "value") -> int:
    default_float = float(default) if default is not None else None
    return int(_to_float(value, default=default_float, name=name))


def _range_pair(value: object, name: str) -> tuple[float, float]:
    if value is None or not isinstance(value, Sequence) or len(value) < 2:
        raise ValueError(f"{name} は2要素の配列で指定してください。")
    return (
        _to_float(value[0], name=f"{name}[0]"),
        _to_float(value[1], name=f"{name}[1]"),
    )


def _to_bool(value: object, *, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    raise ValueError(f"{name} は真偽値で指定してください。")


def _require_mapping(source: Mapping[str, object], key: str, *, context: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}.{key} が定義されていません。")
    return value


def _float_params(mapping: Mapping[str, object], *, name: str) -> dict[str, float]:
    if not mapping:
        raise ValueError(f"{name} が空です。")
    return {str(k): _to_float(v, name=f"{name}.{k}") for k, v in mapping.items()}


def _build_theta_range(core_policy: Mapping[str, object]) -> ThetaRange:
    search = _section(core_policy, "theta_search_range")
    theta1_min, theta1_max = _range_pair(search.get("theta1"), "theta_search_range.theta1")
    theta2_min, theta2_max = _range_pair(search.get("theta2"), "theta_search_range.theta2")
    constraints = _section(core_policy, "theta_constraints")
    max_delta = _to_float(search.get("max_delta", constraints.get("max_delta", 0.1)), name="theta_search_range.max_delta")
    return ThetaRange(
        theta1_min=theta1_min,
        theta1_max=theta1_max,
        theta2_min=theta2_min,
        theta2_max=theta2_max,
        max_delta=max_delta,
    )


def _build_theta_plan(core_policy: Mapping[str, object]) -> ThetaOptimizationPlan:
    plan_raw = core_policy.get("theta_plan", {})
    if isinstance(plan_raw, Mapping):
        grid_steps_raw = plan_raw.get("grid_steps", {"theta1": 3, "theta2": 3})
        if isinstance(grid_steps_raw, Mapping):
            grid_steps = {
                str(k): _to_int(v, default=3, name=f"theta_plan.grid_steps.{k}") for k, v in grid_steps_raw.items()
            }
        else:
            grid_steps = {"theta1": 3, "theta2": 3}
        optuna_trials = _to_int(plan_raw.get("optuna_trials"), default=20, name="theta_plan.optuna_trials")
        timeout_raw = plan_raw.get("optuna_timeout_seconds")
        optuna_timeout = _to_int(timeout_raw, name="theta_plan.optuna_timeout_seconds") if timeout_raw is not None else None
        constraints_raw = plan_raw.get("constraints", {})
        if isinstance(constraints_raw, Mapping):
            constraints = {str(k): _to_float(v, name=f"theta_plan.constraints.{k}") for k, v in constraints_raw.items()}
        else:
            constraints = {}
    else:
        grid_steps = {"theta1": 3, "theta2": 3}
        optuna_trials = 20
        optuna_timeout = None
        constraints = {}
    return ThetaOptimizationPlan(
        grid_steps=grid_steps,
        optuna_trials=optuna_trials,
        optuna_timeout_seconds=optuna_timeout,
        constraints=constraints,
    )


def _build_theta_defaults(core_policy: Mapping[str, object], theta_range: ThetaRange) -> tuple[float, float, float]:
    constraints = _section(core_policy, "theta_constraints")
    max_delta = _to_float(constraints.get("max_delta"), default=theta_range.max_delta, name="theta_constraints.max_delta")
    baseline_theta1 = _to_float(
        constraints.get("baseline_theta1"),
        default=(theta_range.theta1_min + theta_range.theta1_max) / 2,
        name="theta_constraints.baseline_theta1",
    )
    baseline_theta2 = _to_float(
        constraints.get("baseline_theta2"),
        default=(theta_range.theta2_min + theta_range.theta2_max) / 2,
        name="theta_constraints.baseline_theta2",
    )
    return max_delta, baseline_theta1, baseline_theta2


def build_theta_components(environment: str | None = None) -> ThetaComponents:
    env = environment or _environment()
    repo = _config_repository()
    core_raw = repo.load("core_policy", environment=env)
    core_policy = _section(core_raw, "core_policy")

    theta_range = _build_theta_range(core_policy)
    theta_plan = _build_theta_plan(core_policy)
    max_delta, baseline_theta1, baseline_theta2 = _build_theta_defaults(core_policy, theta_range)

    grid_strategy = UniformGridSearchStrategy()
    optuna_strategy = RandomOptunaStrategy()
    constraint_evaluator = DeltaConstraintEvaluator(
        default_max_delta=max_delta,
        baseline_theta1=baseline_theta1,
        baseline_theta2=baseline_theta2,
    )

    scoring_raw = core_policy.get("theta_scoring", {})
    if isinstance(scoring_raw, Mapping):
        max_dd_target = _to_float(scoring_raw.get("max_drawdown_target"), default=0.12, name="theta_scoring.max_drawdown_target")
    else:
        max_dd_target = 0.12
    scorer = HistoricalThetaScorer(
        max_drawdown_target=max_dd_target,
        reference_theta1=baseline_theta1,
        reference_theta2=baseline_theta2,
    )

    service = ThetaOptimizer(
        grid_strategy=grid_strategy,
        optuna_strategy=optuna_strategy,
        constraint_evaluator=constraint_evaluator,
        scorer=scorer,
    )
    request_factory = ThetaRequestFactory(theta_range=theta_range, plan=theta_plan)
    return ThetaComponents(service=service, request_factory=request_factory)


def build_publish_components(environment: str | None = None) -> PublishComponents:
    env = environment or _environment()
    path_resolver = _storage_path_resolver(env)

    storage_client = LocalFileSystemStorageClient()
    distributor = ModelArtifactDistributor(storage_client=storage_client, path_resolver=path_resolver)
    worm_writer = WormArchiveWriter(storage_client=storage_client, path_resolver=path_resolver)

    registry_updater = PostgresRegistryUpdater(connection_provider=_postgres_provider(env))
    notification_service = _build_notification_service(env)

    service = ModelPublishService(
        distributor=distributor,
        registry_updater=registry_updater,
        notification_service=notification_service,
        worm_writer=worm_writer,
    )

    return PublishComponents(service=service, registry_updater=registry_updater)


@lru_cache(maxsize=None)
def _postgres_provider(env: str) -> PostgresConnectionProvider:
    repo = _config_repository()
    database_raw = repo.load("database", environment=env)
    database_section = _section(database_raw, "database")
    postgres_mapping = _section(database_section, "postgres")
    config = PostgresConfig.from_mapping(postgres_mapping)
    return PostgresConnectionProvider(config)


def _build_notification_service(environment: str) -> NotificationService:
    repo = _config_repository()
    notifications_raw = repo.load("notifications", environment=environment)
    notifications_section = _section(notifications_raw, "notifications")

    slack_notifier = _build_slack_notifier(notifications_section)
    pagerduty_notifier = _build_pagerduty_notifier(notifications_section)

    if slack_notifier is None and pagerduty_notifier is None:
        return NoopNotificationService()
    return CompositePublishNotificationService(
        slack_notifier=slack_notifier,
        pagerduty_notifier=pagerduty_notifier,
    )


def _build_slack_notifier(config: Mapping[str, object]) -> SlackWebhookNotifier | None:
    raw = config.get("slack")
    if not isinstance(raw, Mapping):
        return None
    if not bool(raw.get("enabled", True)):
        return None
    slack_config = SlackConfig.from_mapping(raw)
    return SlackWebhookNotifier(slack_config)


def _build_pagerduty_notifier(config: Mapping[str, object]) -> PagerDutyNotifier | None:
    raw = config.get("pagerduty")
    if not isinstance(raw, Mapping):
        return None
    if not bool(raw.get("enabled", True)):
        return None
    pagerduty_config = PagerDutyConfig.from_mapping(raw)
    return PagerDutyNotifier(pagerduty_config)


@lru_cache(maxsize=None)
def _redis_settings(env: str) -> RedisMessagingConfig:
    repo = _config_repository()
    messaging_raw = repo.load("messaging", environment=env)
    messaging_section = _section(messaging_raw, "messaging")
    redis_mapping = _section(messaging_section, "redis")
    return RedisMessagingConfig.from_mapping(redis_mapping)


@lru_cache(maxsize=None)
def _redis_client(env: str) -> Redis:
    settings = _redis_settings(env)
    return cast(Redis, Redis.from_url(settings.url))


@lru_cache(maxsize=None)
@lru_cache(maxsize=None)
def _storage_path_resolver(env: str) -> StoragePathResolver:
    return StoragePathResolver(config_repository=_config_repository(), environment=env)


def build_storage_resolver(environment: str | None = None) -> StoragePathResolver:
    """
    storage.yaml に基づき StoragePathResolver を構築する。
    """

    env = environment or _environment()
    return _storage_path_resolver(env)


def _training_config(env: str) -> Mapping[str, object]:
    repo = _config_repository()
    training_raw = repo.load("training", environment=env)
    return _section(training_raw, "training")


def build_learning_components(environment: str | None = None) -> LearningComponents:
    env = environment or _environment()
    training_conf = _training_config(env)
    cv_conf = _require_mapping(training_conf, "cv", context="training")
    feature_conf = _require_mapping(training_conf, "feature_builder", context="training")
    ai1_conf = _require_mapping(training_conf, "ai1_params", context="training")
    ai2_conf = _require_mapping(training_conf, "ai2_params", context="training")

    cv_strategy = RollingTimeSeriesCV(
        folds=_to_int(cv_conf.get("folds"), name="training.cv.folds"),
        min_train_size=_to_int(cv_conf.get("min_train_size"), name="training.cv.min_train_size"),
        holdout_size=_to_int(cv_conf.get("holdout_size"), name="training.cv.holdout_size"),
    )

    feature_builder_config = FeatureBuilderConfig(
        missing_threshold=_to_float(
            feature_conf.get("missing_threshold"),
            name="training.feature_builder.missing_threshold",
        ),
        outlier_threshold=_to_float(
            feature_conf.get("outlier_threshold"),
            name="training.feature_builder.outlier_threshold",
        ),
        spike_threshold=_to_float(
            feature_conf.get("spike_threshold"),
            name="training.feature_builder.spike_threshold",
        ),
        allow_warning=_to_bool(
            feature_conf.get("allow_warning"),
            name="training.feature_builder.allow_warning",
        ),
        invalidate_on_failure=_to_bool(
            feature_conf.get("invalidate_on_failure"),
            name="training.feature_builder.invalidate_on_failure",
        ),
    )

    path_resolver = _storage_path_resolver(env)
    storage_client = LocalFileSystemStorageClient()
    generator = DataAssetsFeatureGenerator(path_resolver=path_resolver, storage_client=storage_client)
    cache = DataAssetsFeatureCache(path_resolver=path_resolver, storage_client=storage_client)
    hasher = JsonFeatureHasher()

    feature_builder = FeatureBuilder(
        cache=cache,
        generator=generator,
        hasher=hasher,
        config=feature_builder_config,
    )

    labeling_service = RuleBasedLabelingService(LabelingConfig())
    artifact_builder = LocalModelArtifactBuilder(path_resolver=path_resolver, storage_client=storage_client)
    metrics_repository = PostgresMetricsRepository(connection_provider=_postgres_provider(env))
    trainer = Trainer(
        cv_strategy=cv_strategy,
        backend_ai1=LogisticModelTrainer(),
        backend_ai2=LogisticModelTrainer(),
        artifact_builder=artifact_builder,
        theta_estimator=SimpleThetaEstimator(),
        metrics_repository=metrics_repository,
    )

    learning_service = LearningService(
        feature_builder=feature_builder,
        labeling_service=labeling_service,
        trainer=trainer,
        default_ai1_params=_float_params(ai1_conf, name="training.ai1_params"),
        default_ai2_params=_float_params(ai2_conf, name="training.ai2_params"),
    )

    return LearningComponents(usecase=learning_service, trainer=trainer)


def build_ops_usecase(environment: str | None = None) -> OpsUseCase:
    env = environment or _environment()
    repo = _config_repository()
    redis_client = _redis_client(env)
    redis_settings = _redis_settings(env)
    repository = RedisOpsFlagRepository(redis_client, redis_settings.ops_flag_key)
    audit_logger = PostgresAuditLogger(connection_provider=_postgres_provider(env), event_type="ops")

    notifications_raw = repo.load("notifications", environment=env)
    notifications_section = _section(notifications_raw, "notifications")
    notifier = _build_slack_notifier(notifications_section)

    service = OpsService(
        repository=repository,
        audit_logger=audit_logger,
        event_publisher=RedisPublisherImpl(redis_client),
        ops_event_channel=redis_settings.ops_event_channel,
        notifier=notifier,
    )
    return service


def build_config_management_service(environment: str | None = None) -> ConfigManagementUseCase:
    env = environment or _environment()
    repo = _config_repository()
    config_raw = repo.load("config_api", environment=env)
    settings = ConfigAPISettings.from_mapping(_section(config_raw, "config_api"))
    client = ConfigAPIClient(settings)
    return ConfigManagementService(client)


def build_analytics_service(environment: str | None = None) -> AnalyticsService:
    env = environment or _environment()
    repository = PostgresAnalyticsRepository(connection_provider=_postgres_provider(env))
    cache = RedisAnalyticsCache(redis=_redis_client(env))
    return AnalyticsService(repository, cache=cache)
