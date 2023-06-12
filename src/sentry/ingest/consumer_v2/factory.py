from __future__ import annotations

from typing import Any, Mapping, MutableMapping, NamedTuple

from arroyo import Topic
from arroyo.backends.kafka.configuration import build_kafka_consumer_configuration
from arroyo.backends.kafka.consumer import KafkaConsumer, KafkaPayload
from arroyo.commit import ONCE_PER_SECOND
from arroyo.processing.processor import StreamProcessor
from arroyo.processing.strategies import (
    CommitOffsets,
    ProcessingStrategy,
    ProcessingStrategyFactory,
    RunTask,
    RunTaskWithMultiprocessing,
)
from arroyo.types import Commit, Partition
from django.conf import settings

from sentry.ingest.consumer_v2.ingest import process_ingest_message
from sentry.ingest.types import ConsumerType
from sentry.processing.backpressure.arroyo import HealthChecker, create_backpressure_step
from sentry.snuba.utils import initialize_consumer_state
from sentry.utils import kafka_config


class MultiProcessConfig(NamedTuple):
    num_processes: int
    max_batch_size: int
    max_batch_time: int
    input_block_size: int
    output_block_size: int


class IngestStrategyFactory(ProcessingStrategyFactory[KafkaPayload]):
    def __init__(
        self,
        health_checker: HealthChecker,
        multi_process: MultiProcessConfig | None = None,
    ):
        self.health_checker = health_checker
        self.multi_process = multi_process

    def create_with_partitions(
        self,
        commit: Commit,
        partitions: Mapping[Partition, int],
    ) -> ProcessingStrategy[KafkaPayload]:
        if (mp := self.multi_process) is not None:
            next_step = RunTaskWithMultiprocessing(
                process_ingest_message,
                CommitOffsets(commit),
                mp.num_processes,
                mp.max_batch_size,
                mp.max_batch_time,
                mp.input_block_size,
                mp.output_block_size,
                initializer=initialize_consumer_state,
            )
        else:
            next_step = RunTask(
                function=process_ingest_message,
                next_step=CommitOffsets(commit),
            )

        return create_backpressure_step(health_checker=self.health_checker, next_step=next_step)


def get_ingest_consumer(
    consumer_type: str,
    group_id: str,
    auto_offset_reset: str,
    strict_offset_reset: bool,
    max_batch_size: int,
    max_batch_time: int,
    processes: int,
    input_block_size: int,
    output_block_size: int,
    force_topic: str | None,
    force_cluster: str | None,
) -> StreamProcessor[KafkaPayload]:
    topic = force_topic or ConsumerType.get_topic_name(consumer_type)
    consumer_config = get_config(
        topic,
        group_id,
        auto_offset_reset=auto_offset_reset,
        strict_offset_reset=strict_offset_reset,
        force_cluster=force_cluster,
    )
    consumer = KafkaConsumer(consumer_config)

    # The attachments consumer that is used for multiple message types needs
    # ordering guarantees: Attachments have to be written before the event using
    # them is being processed. We will use a simple serial `RunTask` for those
    # for now.
    multi_process = None
    if processes > 1 and consumer_type != ConsumerType.Attachments:
        multi_process = MultiProcessConfig(
            num_processes=processes,
            max_batch_size=max_batch_size,
            max_batch_time=max_batch_time,
            input_block_size=input_block_size,
            output_block_size=output_block_size,
        )

    health_checker = HealthChecker()

    return StreamProcessor(
        consumer=consumer,
        topic=Topic(topic),
        processor_factory=IngestStrategyFactory(
            health_checker=health_checker, multi_process=multi_process
        ),
        commit_policy=ONCE_PER_SECOND,
    )


def get_config(
    topic: str,
    group_id: str,
    auto_offset_reset: str,
    strict_offset_reset: bool,
    force_cluster: str | None,
) -> MutableMapping[str, Any]:
    cluster_name: str = force_cluster or settings.KAFKA_TOPICS[topic]["cluster"]
    return build_kafka_consumer_configuration(
        kafka_config.get_kafka_consumer_cluster_options(
            cluster_name,
        ),
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        strict_offset_reset=strict_offset_reset,
    )