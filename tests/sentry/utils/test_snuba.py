from __future__ import absolute_import

from datetime import datetime
from mock import patch
import pytz

from sentry.models import GroupRelease, Release
from sentry.testutils import TestCase, SnubaTestCase
from sentry.testutils.helpers.datetime import iso_format, before_now
from sentry.utils.snuba import (
    get_snuba_translators,
    zerofill,
    get_json_type,
    get_snuba_column_name,
    detect_dataset,
    transform_aliases_and_query,
)


class SnubaUtilsTest(TestCase):
    def setUp(self):
        self.now = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=pytz.UTC
        )
        self.proj1 = self.create_project()
        self.proj1env1 = self.create_environment(project=self.proj1, name="prod")
        self.proj1group1 = self.create_group(self.proj1)
        self.proj1group2 = self.create_group(self.proj1)

        self.release1 = Release.objects.create(
            organization_id=self.organization.id, version="1" * 10, date_added=self.now
        )
        self.release1.add_project(self.proj1)
        self.release2 = Release.objects.create(
            organization_id=self.organization.id, version="2" * 10, date_added=self.now
        )
        self.release2.add_project(self.proj1)

        self.group1release1 = GroupRelease.objects.create(
            project_id=self.proj1.id, group_id=self.proj1group1.id, release_id=self.release1.id
        )
        self.group1release2 = GroupRelease.objects.create(
            project_id=self.proj1.id, group_id=self.proj1group1.id, release_id=self.release2.id
        )
        self.group2release1 = GroupRelease.objects.create(
            project_id=self.proj1.id, group_id=self.proj1group2.id, release_id=self.release1.id
        )

    def test_translation(self):
        # Case 1: No translation
        filter_keys = {"sdk": ["python", "js"]}
        forward, reverse = get_snuba_translators(filter_keys)
        assert forward(filter_keys) == filter_keys
        result = [{"sdk": "python", "count": 123}, {"sdk": "js", "count": 234}]
        assert all(reverse(row) == row for row in result)

        # Case 2: Environment ID -> Name and back
        filter_keys = {"environment": [self.proj1env1.id]}
        forward, reverse = get_snuba_translators(filter_keys)
        assert forward(filter_keys) == {"environment": [self.proj1env1.name]}
        row = {"environment": self.proj1env1.name, "count": 123}
        assert reverse(row) == {"environment": self.proj1env1.id, "count": 123}

        # Case 3, both Environment and Release
        filter_keys = {
            "environment": [self.proj1env1.id],
            "tags[sentry:release]": [self.release1.id],
        }
        forward, reverse = get_snuba_translators(filter_keys)
        assert forward(filter_keys) == {
            "environment": [self.proj1env1.name],
            "tags[sentry:release]": [self.release1.version],
        }
        row = {
            "environment": self.proj1env1.name,
            "tags[sentry:release]": self.release1.version,
            "count": 123,
        }
        assert reverse(row) == {
            "environment": self.proj1env1.id,
            "tags[sentry:release]": self.release1.id,
            "count": 123,
        }

        # Case 4: 2 Groups, many-to-many mapping of Groups
        # to Releases. Reverse translation depends on multiple
        # fields.
        filter_keys = {
            "issue": [self.proj1group1.id, self.proj1group2.id],
            "tags[sentry:release]": [
                self.group1release1.id,
                self.group1release2.id,
                self.group2release1.id,
            ],
        }
        forward, reverse = get_snuba_translators(filter_keys, is_grouprelease=True)
        assert forward(filter_keys) == {
            "issue": [self.proj1group1.id, self.proj1group2.id],
            "tags[sentry:release]": [
                self.release1.version,
                self.release2.version,
                self.release1.version,  # Duplicated because 2 GroupReleases refer to it
            ],
        }
        result = [
            {
                "issue": self.proj1group1.id,
                "tags[sentry:release]": self.release1.version,
                "count": 1,
            },
            {
                "issue": self.proj1group1.id,
                "tags[sentry:release]": self.release2.version,
                "count": 2,
            },
            {
                "issue": self.proj1group2.id,
                "tags[sentry:release]": self.release1.version,
                "count": 3,
            },
        ]

        result = [reverse(r) for r in result]
        assert result == [
            {
                "issue": self.proj1group1.id,
                "tags[sentry:release]": self.group1release1.id,
                "count": 1,
            },
            {
                "issue": self.proj1group1.id,
                "tags[sentry:release]": self.group1release2.id,
                "count": 2,
            },
            {
                "issue": self.proj1group2.id,
                "tags[sentry:release]": self.group2release1.id,
                "count": 3,
            },
        ]

    def test_zerofill(self):
        results = zerofill(
            {}, datetime(2019, 1, 2, 0, 0), datetime(2019, 1, 9, 23, 59, 59), 86400, "time"
        )
        results_desc = zerofill(
            {}, datetime(2019, 1, 2, 0, 0), datetime(2019, 1, 9, 23, 59, 59), 86400, "-time"
        )

        assert results == list(reversed(results_desc))

        # Bucket for the 2, 3, 4, 5, 6, 7, 8, 9
        assert len(results) == 8

        assert results[0]["time"] == 1546387200
        assert results[7]["time"] == 1546992000

    def test_get_json_type(self):
        assert get_json_type("UInt8") == "boolean"
        assert get_json_type("UInt16") == "integer"
        assert get_json_type("UInt32") == "integer"
        assert get_json_type("UInt64") == "integer"
        assert get_json_type("Float32") == "number"
        assert get_json_type("Float64") == "number"
        assert get_json_type("Nullable(Float64)") == "number"
        assert get_json_type("Array(String)") == "array"
        assert get_json_type("Char") == "string"
        assert get_json_type("unknown") == "string"
        assert get_json_type("") == "string"

    def test_get_snuba_column_name(self):
        assert get_snuba_column_name("project_id") == "project_id"
        assert get_snuba_column_name("start") == "start"
        assert get_snuba_column_name("'thing'") == "'thing'"
        assert get_snuba_column_name("id") == "event_id"
        assert get_snuba_column_name("geo.region") == "geo_region"
        assert get_snuba_column_name("organization") == "tags[organization]"
        # This is odd behavior but captures what we do currently.
        assert get_snuba_column_name("tags[sentry:user]") == "tags[tags[sentry:user]]"
        assert get_snuba_column_name("organization") == "tags[organization]"


class TransformAliasesAndQueryTest(SnubaTestCase, TestCase):
    def setUp(self):
        super(TransformAliasesAndQueryTest, self).setUp()
        self.environment = self.create_environment(self.project, name="prod")
        self.release = self.create_release(self.project, version="first-release")

        self.store_event(
            data={
                "message": "oh no",
                "release": "first-release",
                "environment": "prod",
                "platform": "python",
                "user": {"id": "99", "email": "bruce@example.com", "username": "brucew"},
                "timestamp": iso_format(before_now(minutes=1)),
            },
            project_id=self.project.id,
        )

    def test_field_aliasing_in_selected_columns(self):
        result = transform_aliases_and_query(
            selected_columns=["project.id", "user.email", "release"],
            filter_keys={"project_id": [self.project.id]},
        )
        data = result["data"]
        assert len(data) == 1
        assert data[0]["project.id"] == self.project.id
        assert data[0]["user.email"] == "bruce@example.com"
        assert data[0]["release"] == "first-release"

    def test_field_aliasing_in_aggregate_functions_and_groupby(self):
        result = transform_aliases_and_query(
            selected_columns=["project.id"],
            aggregations=[["uniq", "user.email", "uniq_email"]],
            filter_keys={"project_id": [self.project.id]},
            groupby=["project.id"],
        )
        data = result["data"]
        assert len(data) == 1
        assert data[0]["project.id"] == self.project.id
        assert data[0]["uniq_email"] == 1

    def test_field_aliasing_in_conditions(self):
        result = transform_aliases_and_query(
            selected_columns=["project.id", "user.email"],
            conditions=[["user.email", "=", "bruce@example.com"]],
            filter_keys={"project_id": [self.project.id]},
        )
        data = result["data"]
        assert len(data) == 1
        assert data[0]["project.id"] == self.project.id
        assert data[0]["user.email"] == "bruce@example.com"

    def test_autoconversion_of_time_column(self):
        result = transform_aliases_and_query(
            aggregations=[["count", "", "count"]],
            filter_keys={"project_id": [self.project.id]},
            start=before_now(minutes=5),
            end=before_now(),
            groupby=["time"],
            orderby=["time"],
            rollup=3600,
        )
        data = result["data"]
        assert isinstance(data[-1]["time"], int)
        assert data[-1]["count"] == 1

    def test_conversion_of_release_filter_key(self):
        result = transform_aliases_and_query(
            selected_columns=["id", "message"],
            filter_keys={
                "release": [self.create_release(self.project).id],
                "project_id": [self.project.id],
            },
        )
        assert len(result["data"]) == 0

        result = transform_aliases_and_query(
            selected_columns=["id", "message"],
            filter_keys={"release": [self.release.id], "project_id": [self.project.id]},
        )
        assert len(result["data"]) == 1

    def test_conversion_of_environment_filter_key(self):
        result = transform_aliases_and_query(
            selected_columns=["id", "message"],
            filter_keys={
                "environment": [self.create_environment(self.project).id],
                "project_id": [self.project.id],
            },
        )
        assert len(result["data"]) == 0

        result = transform_aliases_and_query(
            selected_columns=["id", "message"],
            filter_keys={"environment": [self.environment.id], "project_id": [self.project.id]},
        )
        assert len(result["data"]) == 1


class TransformAliasesAndQueryTransactionsTest(TestCase):
    """
    This test mocks snuba.raw_query because there is currently no
    way to insert data into the transactions dataset during tests.
    """

    @patch("sentry.utils.snuba.raw_query")
    def test_selected_columns_aliasing(self, mock_query):
        mock_query.return_value = {
            "meta": [{"name": "transaction_name"}, {"name": "duration"}],
            "data": [{"transaction_name": "api.do_things", "duration": 200}],
        }
        transform_aliases_and_query(
            selected_columns=["transaction", "transaction.duration"],
            aggregations=[
                ["argMax", ["id", "transaction.duration"], "longest"],
                ["uniq", "transaction", "uniq_transaction"],
            ],
            filter_keys={"project_id": [self.project.id]},
        )
        mock_query.assert_called_with(
            selected_columns=["transaction_name", "duration"],
            aggregations=[
                ["argMax", ["event_id", "duration"], "longest"],
                ["uniq", "transaction_name", "uniq_transaction"],
            ],
            filter_keys={"project_id": [self.project.id]},
            dataset="transactions",
            arrayjoin=None,
        )

    @patch("sentry.utils.snuba.raw_query")
    def test_conditions_and_groupby_aliasing(self, mock_query):
        mock_query.return_value = {
            "meta": [{"name": "transaction_name"}, {"name": "duration"}],
            "data": [{"transaction_name": "api.do_things", "duration": 200}],
        }
        transform_aliases_and_query(
            selected_columns=["transaction", "transaction.duration"],
            conditions=[["transaction.duration", "=", 200], ["time", ">", "2019-09-23"]],
            groupby=["transaction.op"],
            filter_keys={"project_id": [self.project.id]},
        )
        mock_query.assert_called_with(
            selected_columns=["transaction_name", "duration"],
            conditions=[["duration", "=", 200], ["bucketed_start", ">", "2019-09-23"]],
            filter_keys={"project_id": [self.project.id]},
            groupby=["transaction_op"],
            dataset="transactions",
            arrayjoin=None,
        )

    @patch("sentry.utils.snuba.raw_query")
    def test_condition_removal_skip_conditions(self, mock_query):
        mock_query.return_value = {
            "meta": [{"name": "transaction_name"}, {"name": "duration"}],
            "data": [{"transaction_name": "api.do_things", "duration": 200}],
        }
        transform_aliases_and_query(
            skip_conditions=True,
            selected_columns=["transaction", "transaction.duration"],
            conditions=[["type", "=", "transaction"], ["duration", ">", 200]],
            groupby=["transaction.op"],
            filter_keys={"project_id": [self.project.id]},
        )
        mock_query.assert_called_with(
            selected_columns=["transaction_name", "duration"],
            conditions=[["duration", ">", 200]],
            filter_keys={"project_id": [self.project.id]},
            groupby=["transaction_op"],
            dataset="transactions",
            arrayjoin=None,
        )


class DetectDatasetTest(TestCase):
    def test_dataset_key(self):
        query = {"dataset": "events", "conditions": [["event.type", "=", "transaction"]]}
        assert detect_dataset(query) == "events"

    def test_event_type_condition(self):
        query = {"conditions": [["type", "=", "transaction"]]}
        assert detect_dataset(query) == "transactions"

        query = {"conditions": [["type", "=", "error"]]}
        assert detect_dataset(query) == "events"

        query = {"conditions": [["type", "=", "transaction"]]}
        assert detect_dataset(query) == "transactions"

        query = {"conditions": [["type", "=", "error"]]}
        assert detect_dataset(query) == "events"

    def test_conditions(self):
        query = {"conditions": [["transaction", "=", "api.do_thing"]]}
        assert detect_dataset(query) == "events"

        query = {"conditions": [["transaction.name", "=", "api.do_thing"]]}
        assert detect_dataset(query) == "transactions"

        query = {"conditions": [["transaction.duration", ">", "3"]]}
        assert detect_dataset(query) == "transactions"

    def test_selected_columns(self):
        query = {"selected_columns": ["id", "message"]}
        assert detect_dataset(query) == "events"

        query = {"selected_columns": ["id", "transaction", "transaction.duration"]}
        assert detect_dataset(query) == "transactions"

    def test_aggregations(self):
        query = {"aggregations": [["argMax", ["id", "timestamp"], "latest_event"]]}
        assert detect_dataset(query) == "events"

        query = {"aggregations": [["argMax", ["id", "duration"], "longest"]]}
        assert detect_dataset(query) == "events"

        query = {"aggregations": [["quantileTiming(0.95)", "transaction.duration", "p95_duration"]]}
        assert detect_dataset(query) == "transactions"

        query = {"aggregations": [["uniq", "transaction.name", "uniq_transaction"]]}
        assert detect_dataset(query) == "transactions"
