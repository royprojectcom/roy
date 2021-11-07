import asyncio
import importlib
import logging
import functools

from contextlib import contextmanager, asynccontextmanager
from pathlib import Path

import jinja2

from roy.utils.tasks import Tasks, TasksManager, TaskRunError, register

from .settings import SETTINGS, DeployComponentSettings
from .tasks import DeployTasks


class DeployTasksManager(TasksManager):
    def __init__(self):
        super().__init__()

        self.debug = False
        self.override = False
        self.hosts = {}
        self.nohost = {
            'user': '__nohost__',
            'public_ip': None, 'private_ip': None, 'port': 0
        }

        for class_ in SETTINGS.tasks_classes:
            self.register(class_)

    def run(self, *commands):
        commands = list(commands)
        if '-f' in commands:
            commands.remove('-f')
            self.override = True

        for provider_class in SETTINGS.provider_classes:
            provider = provider_class(self, SETTINGS.services)
            self.hosts.update(asyncio.run(provider.initialize()))

        super().run(*commands)

    def run_hooks(self, task_class, name, hook_name, instance=None):
        instance = task_class(self, None, self.nohost)
        super().run_hooks(task_class, name, hook_name, instance=instance)

    def run_task(self, task_class, name, args):
        if not issubclass(task_class, DeployTasks):
            return super().run_task(task_class, name, args)

        current_hosts = self._prepare_hosts(task_class, name)

        async def run():
            lock = asyncio.Lock()
            tasks = [
                getattr(task_class(self, lock, host), name)
                for host in current_hosts
            ]
            # return exceptions (?)
            await asyncio.gather(*[task(*args) for task in tasks])

        asyncio.run(run())

    def _prepare_hosts(self, task_class, name):
        method = getattr(task_class, name)
        is_nohost = getattr(method, '__nohost__', False)
        is_onehost = getattr(method, '__onehost__', False)
        is_firsthost = getattr(method, '__firsthost__', False)

        if is_nohost:
            hosts = [self.nohost.copy()]
        else:
            hosts = self.hosts[task_class.get_namespace()]
        
        if is_firsthost:
            return hosts[:1]

        if is_onehost and len(hosts) > 1:
            hosts_per_index = []
            for index, host in enumerate(hosts, start=1):
                hosts_per_index.append(host)
                print(f" ({index}) - {host['name']} [{host['public_ip']}]")
            chosen_index = int(input('Please choose host to run task: '))
            hosts = [hosts_per_index[chosen_index - 1]]

        return hosts


DEPLOY_TASKS_MANAGER = DeployTasksManager()
