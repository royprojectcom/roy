import asyncio

from pathlib import Path
from typing import Generator

from watchgod import awatch

from ...tasks import DeployTasks, nohost, register
from ...settings import DeployComponentSettings, SETTINGS as DEPLOY_SETTINGS

from ..systemd import SystemdTasksMixin


class AppSettings(DeployComponentSettings):
    NAME = 'app'
    SCHEMA = {
        'instance': {'type': 'integer'},
        'bin': {'type': 'string', 'required': True},
        'listen_private_ip': {'type': 'boolean', 'required': True},
        'user': {'type': 'string', 'required': False},
        'module': {'type': 'string'},
        'systemd': SystemdTasksMixin.SCHEMA,
        'watch': {
            'type': 'list',
            'schema': {'type': 'dict', 'schema': {
                'local': {'type': 'string'},
                'remote': {'type': 'string'},
                'exclude': {'type': 'list', 'schema': {'type': 'string'}}
            }}
        },
    }
    DEFAULT = {
        'bin': 'app.sh',
        'instance': 1,
        'module': '',
        'listen_private_ip': True,
        'systemd': {
            'template': 'app.service',
            'name': '{settings.NAME}_{instance}.service',
            'boot': True,
            'type': 'simple',
            'instances': {'count': 0, 'percent': 0},
            'context': {
                'limit_nofile': 2000,
                'description': "Application description",
            }
        },
        'watch': []
    }

    @property
    def listen_private_ip(self):
        return self._data['listen_private_ip']

    @property
    def bin(self):
        bin_path = self._data['bin'].format(settings=self)
        if not bin_path.startswith('/'):
            return self.home_abs / bin_path
        return Path(bin_path)

    @property
    def module(self):
        return self._data['module']

    @property
    def instance(self):
        return self._data['instance']

    @property
    def watch_dirs(self):
        return [
            {
                'local': Path(info['local']),
                'remote': info['remote'],
                'exclude': info.get('exclude', [])
            }
            for info in self._data['watch']
        ]


SETTINGS = AppSettings()


class AppTasks(DeployTasks, SystemdTasksMixin):
    SETTINGS = AppSettings

    @register
    @nohost
    async def watch(self):
        await asyncio.gather(*[
            self._watch_and_sync_dir(dir_info, task)
            for dir_info in self.settings.watch_dirs
            for task in self.get_all_manager_tasks(self.get_namespace())
        ])

    async def _watch_and_sync_dir(self, dir_info, tasks):
        async for _ in awatch(dir_info['local']):
            with self._set_from_tasks(tasks):
                await self._upload(
                    dir_info['local'], dir_info['remote'],
                    exclude=dir_info['exclude']
                )
                await self.restart()

    async def _sync_roy_cache(self):
        await self._upload(DEPLOY_SETTINGS.settings_cache_file)

    async def build(self):
        """Define build instructions for your app"""
        await self._apt_install('rsync')
        await self._create_user()

    @register
    async def sync(self, type_=''):
        await self._upload(
            self.settings.local_root / self.settings.bin.name,
            self.settings.home_abs
        )
        await self._run(f'chmod +x {self.settings.bin}')
        await self._sync_roy_cache()
        await self._sync_systemd_units()

    @register
    async def setup(self):
        await self.build()
        await self.sync()
        await self.start()
