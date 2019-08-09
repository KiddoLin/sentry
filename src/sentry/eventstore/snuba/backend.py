from __future__ import absolute_import

from sentry.utils import snuba
from sentry.models import SnubaEvent
from sentry.eventstore.base import EventStorage

DEFAULT_ORDERBY = ['-timestamp', '-event_id']
DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0


class InvalidQuery(Exception):
    pass


class SnubaEventStorage(EventStorage):
    """
    Eventstore backend backed by Snuba
    """

    def get_events(
        self,
        filter=None,
        additional_columns=None,
        orderby=DEFAULT_ORDERBY,
        limit=DEFAULT_LIMIT,
        offset=DEFAULT_OFFSET,
    ):
        """
        Get events from Snuba.
        """
        cols = self.__get_columns(additional_columns)

        if not filter:
            raise InvalidQuery('No filter provided')

        result = snuba.raw_query(
            start=filter.start,
            end=filter.end,
            conditions=filter.conditions,
            filter_keys=filter.filter_keys,
            selected_columns=cols,
            orderby=orderby,
            limit=limit,
            offset=offset,
            referrer='eventstore.get_events',
        )

        if 'error' not in result:
            return [SnubaEvent(evt) for evt in result['data']]

        return []

    def get_event_by_id(self, project_id, event_id, additional_columns=None):
        """
        Get an event given a project ID and event ID
        Returns None if an event cannot be found
        """
        cols = self.__get_columns(additional_columns)

        return SnubaEvent.get_event(project_id, event_id, snuba_cols=cols)

    def __get_columns(self, additional_columns):
        columns = EventStorage.minimal_columns

        if additional_columns:
            columns = set(columns + additional_columns)

        return [col.value for col in columns]
