import pytest

from tests.integration.feature_repos.test_repo_configuration import (
    TestRepoConfig,
    construct_test_environment,
    construct_universal_feature_views,
)

# TODO: Allow integration tests to run using different credentials.
from tests.integration.feature_repos.universal.entities import customer, driver


@pytest.mark.integration
@pytest.mark.skip(
    reason="No way to run this test today. Credentials conflict with real AWS credentials in CI"
)
def test_registration_and_retrieval_from_custom_s3_endpoint(universal_data_sources):
    config = TestRepoConfig(
        offline_store_creator="tests.integration.feature_repos.universal.data_sources.file.S3FileDataSourceCreator"
    )
    import os

    if "AWS_ACCESS_KEY_ID" in os.environ:
        raise Exception(
            "AWS_ACCESS_KEY_ID has already been set in the environment. Setting it again may cause a conflict. "
            "It may be better to deduplicate AWS configuration or use sub-processes for isolation"
        )

    os.environ["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    with construct_test_environment(config) as environment:
        fs = environment.feature_store

        entities, datasets, data_sources = universal_data_sources
        feature_views = construct_universal_feature_views(data_sources)

        feast_objects = []
        feast_objects.extend(feature_views.values())
        feast_objects.extend([driver(), customer()])
        fs.apply(feast_objects)
        fs.materialize(environment.start_date, environment.end_date)

        out = fs.get_online_features(
            features=["driver_stats:conv_rate"], entity_rows=[{"driver": 5001}]
        ).to_dict()
        assert out["conv_rate"][0] is not None

    del os.environ["AWS_ACCESS_KEY_ID"]
    del os.environ["AWS_SECRET_ACCESS_KEY"]
