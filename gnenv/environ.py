import json
import logging
import os
from typing import Union

import yaml

ENV_KEY_ENVIRONMENT = 'ENVIRONMENT'
ENV_KEY_SECRETS = 'SECRETS'

logger = logging.getLogger(__name__)


class ConfigDict:
    class DefaultValue:
        def __init__(self):
            pass

        def lower(self):
            raise NotImplementedError()

        def format(self):
            raise NotImplementedError()

    def __init__(self, params=None, override=None):
        self.params = params or dict()
        self.override = override

    def subp(self, parent):
        p = dict(parent.params)
        p.update(self.params)
        if self.override is not None:
            p.update(self.override)
        return ConfigDict(p, self.override)

    def sub(self, **params):
        p = dict(self.params)
        p.update(params)
        if self.override is not None:
            p.update(self.override)
        return ConfigDict(p, self.override)

    def set(self, key, val, domain: str=None):
        if domain is None:
            self.params[key] = val
        else:
            if domain not in self.params:
                self.params[domain] = dict()
            self.params[domain][key] = val

    def keys(self):
        return self.params.keys()

    def get(self, key, default: Union[None, object] = DefaultValue, params=None, domain=None):
        def config_format(s, _params):
            if s is None:
                return s

            if isinstance(s, list):
                return [config_format(r, _params) for r in s]

            if isinstance(s, dict):
                kw = dict()
                for k, v in s.items():
                    kw[k] = config_format(v, _params)
                return kw

            if not isinstance(s, str):
                return s

            if s.lower() == 'null' or s.lower() == 'none':
                return ''

            try:
                import re
                keydb = set('{' + key + '}')

                while True:
                    sres = re.search("{.*?}", s)
                    if sres is None:
                        break

                    # avoid using the same reference twice
                    if sres.group() in keydb:
                        raise RuntimeError(
                                "found circular dependency in config value '{0}' using reference '{1}'".format(
                                        s, sres.group()))
                    keydb.add(sres.group())
                    s = s.format(**_params)

                return s
            except KeyError as e:
                raise RuntimeError("missing configuration key: " + str(e))

        if params is None:
            params = self.params

        if domain is not None:
            if domain in self.params:
                # domain keys are allowed to be empty, e.g. for default amqp exchange etc.
                value = self.params.get(domain).get(key)
                if value is None:
                    if default is None:
                        return ''
                    return default

                return config_format(value, params)

        if key in self.params:
            return config_format(self.params.get(key), params)

        if default == ConfigDict.DefaultValue:
            raise KeyError(key)

        return config_format(default, params)

    def __contains__(self, key):
        if key in self.params:
            return True
        return False

    def __iter__(self):
        for k in sorted(self.params.keys()):
            yield k

    def __len__(self, *args, **kwargs):
        return len(self.params)


class DefaultConfigKeys(object):
    LOG_LEVEL = 'log_level'
    LOG_FORMAT = 'log_format'
    DEBUG = 'debug'
    TESTING = 'testing'
    DATE_FORMAT = 'date_format'

    # will be overwritten even if specified in config file
    ENVIRONMENT = '_environment'
    VERSION = '_version'

    DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)-18s - %(levelname)-7s - %(message)s"
    DEFAULT_DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
    DEFAULT_LOG_LEVEL = 'INFO'


class GNEnvironment(object):
    def __init__(self, root_path: Union[str, None], config: ConfigDict, skip_init=False):
        """
        Initialize the environment
        """
        # can skip when testing
        if skip_init:
            return

        self.dbman = None
        self.app = None
        self.api = None
        self.root_path = root_path
        self.config = config
        self.sql_alchemy_db = None
        self.capture_exception = lambda e: False

        self.event_handler_map = dict()
        self.event_handlers = dict()


def find_config(config_path: str = None) -> tuple:
    default_paths = ["config.yaml", "config.json"]
    config_dict = dict()

    if config_path is None:
        config_path = os.getcwd()

    for conf in default_paths:
        path = os.path.join(config_path, conf)
        logger.info('config path: {}'.format(path))

        if not os.path.isfile(path):
            continue

        try:
            if conf.endswith(".yaml"):
                config_dict = yaml.safe_load(open(path))
            elif conf.endswith(".json"):
                config_dict = json.load(open(path))
            else:
                raise RuntimeError("Unsupported file extension: {0}".format(conf))

        except Exception as e:
            raise RuntimeError("Failed to open configuration {0}: {1}".format(conf, str(e)))

        config_path = path
        break

    if not config_dict:
        raise RuntimeError('No configuration found: {0}/[{0}]\n'.format(config_path, ', '.join(default_paths)))

    return config_dict, config_path


def load_secrets_file(config_dict: dict, secrets_path: str = None, env_name: str = None) -> dict:
    from string import Template
    import ast

    if env_name is None:
        gn_env = os.getenv(ENV_KEY_ENVIRONMENT)
    else:
        gn_env = env_name

    if secrets_path is None:
        secrets_path = os.getenv(ENV_KEY_SECRETS)
        if secrets_path is None:
            secrets_path = 'secrets/{}.yaml'.format(gn_env)
    else:
        secrets_path = '{}/{}.yaml'.format(secrets_path, gn_env)

    logger.debug('loading secrets file "%s"' % secrets_path)

    # first substitute environment variables, which holds precedence over the yaml config (if it exists)
    template = Template(str(config_dict))
    template = template.safe_substitute(os.environ)

    if os.path.isfile(secrets_path):
        try:
            secrets = yaml.safe_load(open(secrets_path))
        except Exception as e:
            raise RuntimeError("Failed to open secrets configuration {0}: {1}".format(secrets_path, str(e)))
        template = Template(template)
        template = template.safe_substitute(secrets)

    return ast.literal_eval(template)


def create_env(
        config_path: str = None,
        gn_environment: str = None,
        secrets_path: str = None,
        quiet: bool = False
) -> GNEnvironment:

    if quiet:
        logging.basicConfig(level='ERROR', format=DefaultConfigKeys.DEFAULT_LOG_FORMAT)
    else:
        logging.basicConfig(level='DEBUG', format=DefaultConfigKeys.DEFAULT_LOG_FORMAT)

    if gn_environment is None:
        gn_environment = os.getenv(ENV_KEY_ENVIRONMENT)

    logger.info('using environment %s' % gn_environment)

    # assuming tests are running
    if gn_environment is None:
        logger.debug('no environment found, assuming tests are running')
        return GNEnvironment(None, ConfigDict(dict()))

    config_dict, config_path = find_config(config_path)
    config_dict = load_secrets_file(config_dict, secrets_path=secrets_path, env_name=gn_environment)

    config_dict[DefaultConfigKeys.ENVIRONMENT] = gn_environment
    log_level = config_dict.get(DefaultConfigKeys.LOG_LEVEL, DefaultConfigKeys.DEFAULT_LOG_LEVEL)

    logging.basicConfig(
            level=getattr(logging, log_level),
            format=config_dict.get(DefaultConfigKeys.LOG_FORMAT, DefaultConfigKeys.DEFAULT_LOG_FORMAT))

    if DefaultConfigKeys.DATE_FORMAT not in config_dict:
        date_format = DefaultConfigKeys.DEFAULT_DATE_FORMAT
        config_dict[DefaultConfigKeys.DATE_FORMAT] = date_format
    else:
        from datetime import datetime
        date_format = config_dict[DefaultConfigKeys.DATE_FORMAT]
        try:
            datetime.utcnow().strftime(date_format)
        except Exception as e:
            raise RuntimeError('invalid date format "{}": {}'.format(date_format, str(e)))

    if DefaultConfigKeys.LOG_FORMAT not in config_dict:
        log_format = DefaultConfigKeys.DEFAULT_LOG_FORMAT
        config_dict[DefaultConfigKeys.LOG_FORMAT] = log_format

    if DefaultConfigKeys.LOG_LEVEL not in config_dict:
        config_dict[DefaultConfigKeys.LOG_LEVEL] = DefaultConfigKeys.DEFAULT_LOG_LEVEL

    root_path = os.path.dirname(config_path)
    gn_env = GNEnvironment(root_path, ConfigDict(config_dict))

    logger.info('read config and created environment')
    return gn_env
