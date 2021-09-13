import os
import inspect
import importlib

from pathlib import Path

import cerberus

from roy.utils.collections import update_dict_recur


def validate_schema(schema, settings):
    validator = cerberus.Validator(schema)
    if not validator.validate(settings):
        raise ValueError(f"Error validation settings {validator.errors}")
    return settings


class ComponentSettings:
    KEY = ''
    SCHEMA = {}
    DEFAULT = {}

    def __init__(self):
        key = self.__class__.KEY
        if not key:
            raise ValueError(f"Provide 'KEY' for settings")

        app_settings = {}
        if 'SETTINGS' in os.environ:
            module_path = os.environ['SETTINGS']
            try:
                module = importlib.import_module(module_path)
                app_settings = module.SETTINGS
            except ModuleNotFoundError:
                pass

        settings = update_dict_recur(
            self.__class__.DEFAULT, app_settings.get(self.__class__.KEY, {}))
        settings = validate_schema(self.__class__.SCHEMA, settings)

        self._data = settings


class AppSettings(ComponentSettings):
    KEY = 'app'
    SCHEMA = {
        'env': {
            'type': 'string',
            'allowed': ['prod', 'dev', 'test'],
            'required': True
        },
        'components': {
            'type': 'list',
            'empty': True,
            'schema': {'type': 'string'},
            'required': True
        }
    }
    DEFAULT = {
        'env': 'prod',
        'components': [],
    }

    @property
    def env(self):
        return self._data['env']

    @property
    def is_dev(self):
        return self._data['env'] == 'dev'

    @property
    def is_prod(self):
        return self._data['env'] == 'prod'

    @property
    def is_test(self):
        return self._data['env'] == 'test'

    @property
    def current_dir(self):
        try:
            current_settings = importlib.import_module(os.environ['SETTINGS'])
            dir_path = Path(inspect.getfile(current_settings)).resolve().parent
        except (KeyError, ModuleNotFoundError):
            dir_path = Path.cwd()
        return dir_path

    def get_components(self):
        for component in self._data['components']:
            component = '{}.app'.format(component)
            yield importlib.import_module(component)


SETTINGS = AppSettings()
