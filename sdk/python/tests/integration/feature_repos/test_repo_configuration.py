import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from feast import FeatureStore, FeatureView, RepoConfig, driver_test_data, importer
from feast.data_source import DataSource
from tests.integration.feature_repos.universal.data_source_creator import (
    DataSourceCreator,
)
from tests.integration.feature_repos.universal.feature_views import (
    create_customer_daily_profile_feature_view,
    create_driver_hourly_stats_feature_view,
)


@dataclass(frozen=True, repr=True)
class TestRepoConfig:
    """
    This class should hold all possible parameters that may need to be varied by individual tests.
    """

    provider: str = "local"
    online_store: Union[str, Dict] = "sqlite"

    offline_store_creator: str = "tests.integration.feature_repos.universal.data_sources.file.FileDataSourceCreator"

    full_feature_names: bool = True
    infer_event_timestamp_col: bool = True
    infer_features: bool = False


def ds_creator_path(cls: str):
    return f"tests.integration.feature_repos.universal.data_sources.{cls}"


DYNAMO_CONFIG = {"type": "dynamodb", "region": "us-west-2"}
REDIS_CONFIG = {"type": "redis", "connection_string": "localhost:6379,db=0"}
FULL_REPO_CONFIGS: List[TestRepoConfig] = [
    # Local configurations
    TestRepoConfig(),
    TestRepoConfig(online_store=REDIS_CONFIG),
    # GCP configurations
    TestRepoConfig(
        provider="gcp",
        offline_store_creator=ds_creator_path("bigquery.BigQueryDataSourceCreator"),
        online_store="datastore",
    ),
    TestRepoConfig(
        provider="gcp",
        offline_store_creator=ds_creator_path("bigquery.BigQueryDataSourceCreator"),
        online_store=REDIS_CONFIG,
    ),
    # AWS configurations
    TestRepoConfig(
        provider="aws",
        offline_store_creator=ds_creator_path("redshift.RedshiftDataSourceCreator"),
        online_store=DYNAMO_CONFIG,
    ),
    TestRepoConfig(
        provider="aws",
        offline_store_creator=ds_creator_path("redshift.RedshiftDataSourceCreator"),
        online_store=REDIS_CONFIG,
    ),
]


def construct_universal_entities() -> Dict[str, List[Any]]:
    return {"customer": list(range(1001, 1110)), "driver": list(range(5001, 5110))}


def construct_universal_datasets(
    entities: Dict[str, List[Any]], start_time: datetime, end_time: datetime
) -> Dict[str, pd.DataFrame]:
    customer_df = driver_test_data.create_customer_daily_profile_df(
        entities["customer"], start_time, end_time
    )
    driver_df = driver_test_data.create_driver_hourly_stats_df(
        entities["driver"], start_time, end_time
    )
    orders_df = driver_test_data.create_orders_df(
        customers=entities["customer"],
        drivers=entities["driver"],
        start_date=end_time - timedelta(days=365),
        end_date=end_time + timedelta(days=365),
        order_count=1000,
    )

    return {"customer": customer_df, "driver": driver_df, "orders": orders_df}


def construct_universal_data_sources(
    datasets: Dict[str, pd.DataFrame], data_source_creator: DataSourceCreator
) -> Dict[str, DataSource]:
    customer_ds = data_source_creator.create_data_source(
        datasets["customer"],
        destination="customer_profile",
        event_timestamp_column="event_timestamp",
        created_timestamp_column="created",
    )
    driver_ds = data_source_creator.create_data_source(
        datasets["driver"],
        destination="driver_hourly",
        event_timestamp_column="event_timestamp",
        created_timestamp_column="created",
    )
    orders_ds = data_source_creator.create_data_source(
        datasets["orders"],
        destination="orders",
        event_timestamp_column="event_timestamp",
        created_timestamp_column="created",
    )
    return {"customer": customer_ds, "driver": driver_ds, "orders": orders_ds}


def construct_universal_feature_views(
    data_sources: Dict[str, DataSource],
) -> Dict[str, FeatureView]:
    return {
        "customer": create_customer_daily_profile_feature_view(
            data_sources["customer"]
        ),
        "driver": create_driver_hourly_stats_feature_view(data_sources["driver"]),
    }


@dataclass
class Environment:
    name: str
    test_repo_config: TestRepoConfig
    feature_store: FeatureStore
    data_source_creator: DataSourceCreator

    end_date: datetime = field(
        default=datetime.now().replace(microsecond=0, second=0, minute=0)
    )

    def __post_init__(self):
        self.start_date: datetime = self.end_date - timedelta(days=7)


def table_name_from_data_source(ds: DataSource) -> Optional[str]:
    if hasattr(ds, "table_ref"):
        return ds.table_ref
    elif hasattr(ds, "table"):
        return ds.table
    return None


def vary_full_feature_names(configs: List[TestRepoConfig]) -> List[TestRepoConfig]:
    new_configs = []
    for c in configs:
        true_c = replace(c, full_feature_names=True)
        false_c = replace(c, full_feature_names=False)
        new_configs.extend([true_c, false_c])
    return new_configs


def vary_infer_event_timestamp_col(
    configs: List[TestRepoConfig],
) -> List[TestRepoConfig]:
    new_configs = []
    for c in configs:
        true_c = replace(c, infer_event_timestamp_col=True)
        false_c = replace(c, infer_event_timestamp_col=False)
        new_configs.extend([true_c, false_c])
    return new_configs


def vary_infer_feature(configs: List[TestRepoConfig]) -> List[TestRepoConfig]:
    new_configs = []
    for c in configs:
        true_c = replace(c, infer_features=True)
        false_c = replace(c, infer_features=False)
        new_configs.extend([true_c, false_c])
    return new_configs


def vary_providers_for_offline_stores(
    configs: List[TestRepoConfig],
) -> List[TestRepoConfig]:
    new_configs = []
    for c in configs:
        if "FileDataSourceCreator" in c.offline_store_creator:
            new_configs.append(c)
        elif "RedshiftDataSourceCreator" in c.offline_store_creator:
            for p in ["local", "aws"]:
                new_configs.append(replace(c, provider=p))
        elif "BigQueryDataSourceCreator" in c.offline_store_creator:
            for p in ["local", "gcp"]:
                new_configs.append(replace(c, provider=p))
    return new_configs


@contextmanager
def construct_test_environment(
    test_repo_config: TestRepoConfig, test_suite_name: str = "integration_test"
) -> Environment:
    project = f"{test_suite_name}_{str(uuid.uuid4()).replace('-', '')[:8]}"

    module_name, config_class_name = test_repo_config.offline_store_creator.rsplit(
        ".", 1
    )

    offline_creator: DataSourceCreator = importer.get_class_from_type(
        module_name, config_class_name, "DataSourceCreator"
    )(project)

    offline_store_config = offline_creator.create_offline_store_config()
    online_store = test_repo_config.online_store

    with tempfile.TemporaryDirectory() as repo_dir_name:
        config = RepoConfig(
            registry=str(Path(repo_dir_name) / "registry.db"),
            project=project,
            provider=test_repo_config.provider,
            offline_store=offline_store_config,
            online_store=online_store,
            repo_path=repo_dir_name,
        )
        fs = FeatureStore(config=config)
        environment = Environment(
            name=project,
            test_repo_config=test_repo_config,
            feature_store=fs,
            data_source_creator=offline_creator,
        )

        try:
            yield environment
        finally:
            fs.teardown()
