import pickle
from typing import Dict

from rq import Queue as RQueue

from . import IngestConfig
from ..utils import get_graph_client
from .redis import get_redis_connection
from .redis import get_rq_queue
from .redis import keys as r_keys


class IngestManager:
    def __init__(
        self,
        config: IngestConfig,
        cache_id: str,
        graph_id: str,
        cv_path: str,
    ):
        self._config = config
        self._graph_client = None
        self._cache_id = cache_id
        self._graph_id = graph_id
        self._cv_path = cv_path
        self._redis = None
        self._task_queues = {}

    @property
    def config(self):
        return self._config

    @property
    def cache_id(self):
        return self._cache_id

    @property
    def graph_id(self):
        return self._graph_id

    @property
    def cv_path(self) -> str:
        return self._cv_path

    @property
    def graph_client(self):
        if self._graph_client is None:
            self._graph_client = get_graph_client(self._graph_id)
        return self._graph_client

    @property
    def redis(self):
        if self._redis is not None:
            return self._redis

        self._redis = get_redis_connection()
        self._redis.set(r_keys.INGESTION_MANAGER, self.serialize_info(pickled=True))
        return self._redis

    @classmethod
    def from_pickle(cls, serialized_info):
        return cls(**pickle.loads(serialized_info))

    def serialize_info(self, pickled=False):
        info = {
            "config": self._config,
            "cache_id": self._cache_id,
            "graph_id": self._graph_id,
            "cv_path": self._cv_path,
        }
        if pickled:
            return pickle.dumps(info)
        return info

    def get_task_queue(self, q_name) -> RQueue:
        if q_name in self._task_queues:
            return self._task_queues[q_name]
        self._task_queues[q_name] = get_rq_queue(q_name)
        return self._task_queues[q_name]
