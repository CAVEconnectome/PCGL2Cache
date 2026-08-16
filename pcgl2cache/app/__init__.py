import datetime
import json
import logging
import os
import sys
import time

import numpy as np
import redis
from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask.logging import default_handler
from flask_cors import CORS
from rq import Queue

from . import config
from .common import bp as l2cache_bp
from .v1.routes import bp as l2cache_api_v1

# ..ingest.cli and ..ingest.rq_cli are imported lazily in configure_app, see the note there.


class CustomJsonEncoder(json.JSONEncoder):
    def __init__(self, int64_as_str=False, **kwargs):
        super().__init__(**kwargs)
        self.int64_as_str = int64_as_str

    def default(self, obj):
        if isinstance(obj, np.ndarray):
            if self.int64_as_str and obj.dtype.type in (np.int64, np.uint64):
                return obj.astype(str).tolist()
            return obj.tolist()
        elif isinstance(obj, np.generic):
            if self.int64_as_str and obj.dtype.type in (np.int64, np.uint64):
                return obj.astype(str).item()
            return obj.item()
        elif isinstance(obj, datetime.datetime):
            return obj.__str__()
        return json.JSONEncoder.default(self, obj)


class CustomJSONProvider(DefaultJSONProvider):
    def dumps(self, obj, **kwargs):
        return super().dumps(obj, default=None, cls=CustomJsonEncoder, **kwargs)


def get_app_base_path():
    return os.path.dirname(os.path.realpath(__file__))


def get_instance_folder_path():
    return os.path.join(get_app_base_path(), "instance")


def create_app(test_config=None):
    app = Flask(__name__,instance_path=get_instance_folder_path(), instance_relative_config=True)
    # app.json_encoder was removed in Flask 2.3; without the provider numpy
    # arrays raise "Object of type ndarray is not JSON serializable"
    app.json = CustomJSONProvider(app)
    CORS(app, expose_headers="WWW-Authenticate")

    configure_app(app)
    app.register_blueprint(l2cache_bp)
    app.register_blueprint(l2cache_api_v1)
    if test_config is not None:
        app.config.update(test_config)
    return app


def configure_app(app):
    # Load logging scheme from config.py
    app_settings = os.getenv("APP_SETTINGS")
    if not app_settings:
        app.config.from_object(config.BaseConfig)
    else:
        app.config.from_object(app_settings)
    app.config.from_pyfile("config.cfg", silent=True)
    # Configure logging
    # handler = logging.FileHandler(app.config['LOGGING_LOCATION'])
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(app.config["LOGGING_LEVEL"])
    app.logger.removeHandler(default_handler)
    app.logger.addHandler(handler)
    app.logger.setLevel(app.config["LOGGING_LEVEL"])
    app.logger.propagate = False

    if app.config["USE_REDIS_JOBS"]:
        # Imported here rather than at module scope: ..ingest.cli pulls in
        # pcgl2cache.core.features, and with it sklearn and scipy.ndimage -- about 76 MB
        # of interpreter memory, per uwsgi worker. Only the ingest/CLI configurations set
        # USE_REDIS_JOBS, so the API deployment (DevelopmentConfig, USE_REDIS_JOBS=False)
        # was paying that cost for commands it never registers. The API reads precomputed
        # features out of Bigtable and never computes them, so it has no need of either.
        from ..ingest.cli import init_ingest_cmds
        from ..ingest.rq_cli import init_rq_cmds

        app.redis = redis.Redis.from_url(app.config["REDIS_URL"])
        app.test_q = Queue("test", connection=app.redis)
        with app.app_context():
            init_rq_cmds(app)
            init_ingest_cmds(app)
