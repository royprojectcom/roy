import os
import json
import copy
import inspect
import importlib

from pathlib import Path

import jinja2

from roy.utils.os import run_in_shell
from roy.utils.collections import update_dict_recur
from roy.app.settings import (
    ComponentSettings, validate_schema, SETTINGS as APP_SETTINGS
)


SERVICES_SCHEMA = {
    'type': 'dict',
    'keyschema': {'type': 'string'},
    'valueschema': {
        'type': 'list',
        'schema': {
            'type': 'dict',
            'schema': {
                'hosts': {
                    'type': 'dict',
                    'required': True,
                },
                'components': {'type': 'dict', 'required': False},
            }
        }
    }
}


class DeploySettings(ComponentSettings):
    KEY = 'deploy'
    SCHEMA = {
        'prefix': {'type': 'string'},
        'tasks': {'type': 'list'},
        'default_tasks': {'type': 'list'},
        'default_providers': {'type': 'list'},
        'providers': {'type': 'list'},
        'provider': {'type': 'dict', 'required': False},
        'hosts': {
            'type': 'dict',
            'keyschema': {'type': 'string'},
            'valueschema': {
                'type': 'dict',
                'schema': {
                    'provider': {'type': 'dict', 'required': False},
                    'ssh_port': {'type': 'integer', 'required': False},
                    'public_ip': {'type': 'string', 'required': False},
                    'private_ip': {'type': 'string', 'required': False},
                    'components': {'type': 'dict', 'required': False},
                }
            }
        },
    }
    DEFAULT = {
        'default_tasks': [
            'roy.deploy.components.app',
            'roy.deploy.components.python',
            'roy.deploy.components.django',
            'roy.deploy.components.iptables',
            'roy.deploy.components.nginx',
            'roy.deploy.components.postgres',
            'roy.deploy.components.redis',
            'roy.deploy.components.nfs'
        ],
        'default_providers': [
            # 'roy.deploy.providers.vagrant',
            'roy.deploy.providers.vultr'
        ],
        'providers': [],
        'provider': {},
        'tasks': [],
        'hosts': {},
    }

    @property
    def settings_cache_file(self):
        cache_app_dir = APP_SETTINGS.current_dir
        cache_settings_dir = Path(inspect.getfile(self.__class__)).parent
        cache_name = f"{self.prefix}.json"
        cache = cache_settings_dir / cache_name
        if not cache.exists():
            cache = cache_app_dir / cache_name
        return cache

    @property
    def hosts(self):
        return self._data['hosts']

    @property
    def providers(self):
        return self._data['provider']

    @property
    def prefix(self):
        return self._data.get('prefix', '')

    @property
    def tasks_classes(self):
        tasks = self._data['default_tasks'] + self._data['tasks']
        return self._find_classes(tasks, 'DeployTasks')

    @property
    def provider_classes(self):
        providers = self._data['default_providers'] + self._data['providers']
        return self._find_classes(providers, 'DeployProvider')

    def _find_classes(self, modules, subclass):
        classes = []
        for module_path in modules:
            class_path = ''
            if ':' in module_path:
                module_path, class_path = module_path.split(':')
            module = importlib.import_module(module_path)
            if not class_path:
                for name, value in module.__dict__.items():
                    if name == subclass:
                        continue

                    for mro in getattr(value, '__mro__', []):
                        if mro.__name__ == subclass:
                            class_path = name
                            break

            if not class_path:
                raise ValueError(
                    f"Can't find subclassed {subclass} in {module}")
            classes.append(getattr(module, class_path))
        return classes


SETTINGS = DeploySettings()


class DeployComponentSettings:
    NAME = ''
    DEFAULT = {}
    SCHEMA = {}

    def __init__(self, settings=None, host=None):
        """Initialize deploy component settings, overrides by host settings"""
        if not self.NAME:
            raise ValueError(f'Provide NAME for settings {self.__class__}')

        settings = settings or {}
        host_settings, host = self.get_for_host(host)

        settings = update_dict_recur(settings, host_settings)
        self._data = validate_schema(
            self.SCHEMA, update_dict_recur(self.DEFAULT, settings))

        self.local_root = Path(inspect.getfile(self._local_root_class)).parent
        self.private_ip = host.get('private_ip', '')
        self.public_ip = host.get('public_ip', '')
        self.host_name = host.get('name', 'unnamed-host')
        self.ssh_port = host.get('ssh_port', 22)

    @property
    def _local_root_class(self):
        return self.__class__

    @classmethod
    def get_for_host(cls, current=None):
        current = current or {}
        host_ips = set() if current else set(
            os.popen('hostname -I').read().split())

        for host in cls.get_for_all_hosts():
            is_valid_host = (
                'name' in current and host['name'] == current['name'] or
                host['public_ip'] in host_ips or host['private_ip'] in host_ips
            )
            if is_valid_host:
                return host['components'][cls.NAME], host
        return {}, {}

    @classmethod
    def get_for_all_hosts(cls):
        hosts_file = SETTINGS.settings_cache_file
        if hosts_file.exists():
            hosts = json.loads(hosts_file.read_text())
            return [
                host
                for host in hosts.values()
                if cls.NAME in host.get('components', {})
            ]
        return []

    def get(self, **attrs):
        return next(self.filter(**attrs), self)

    def filter(self, **attrs):
        for settings in self.get_for_all_hosts():
            instance = self.__class__(
                settings['components'][self.NAME], settings)
            settings_not_matched = next((
                key for key, value in attrs.items()
                if getattr(instance, key) != value
            ), False)
            if settings_not_matched:
                continue

            yield instance

    @property
    def listen_ip(self):
        """Listen ip for service private or public avalability"""
        if getattr(self, 'listen_private_ip', False):
            return self.private_ip
        return self.public_ip

    @property
    def user(self):
        return self._data.get('user', self.NAME)

    @property
    def home(self):
        return Path('~')

    @property
    def home_abs(self):
        return Path('/', 'home', self.user)

    @property
    def systemd(self):
        return self._data.get('systemd', {})

    @property
    def systemd_config(self):
        for line in self.systemd.get('default_config', []):
            yield line.format(settings=self)
        for line in self.systemd.get('config', []):
            yield line.format(settings=self)

    @property
    def systemd_dir(self):
        return Path('/etc', 'systemd', 'system')

    @property
    def systemd_type(self):
        return self.systemd.get('type', 'simple')

    @property
    def root(self):
        return self.home / self._data['root']

    @property
    def root_abs(self):
        return self.home_abs / self._data['root']
