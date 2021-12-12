import json
import asyncio

from contextlib import contextmanager, asynccontextmanager

from roy.utils.tasks import TasksManager, register

from .settings import SETTINGS
from .tasks import DeployTasks


class DeployTasksManager(TasksManager):
    def __init__(self):
        super().__init__()

        self.debug = False
        self.override = False
        self.hosts = {}
        self.nohost = {
            'user': '__nohost__',
            'public_ip': None, 'private_ip': None, 'ssh_port': 22
        }

        for class_ in SETTINGS.tasks_classes:
            self.register(class_)

    def run(self, *commands):
        commands = list(commands)
        if '-f' in commands:
            commands.remove('-f')
            self.override = True

        old_hosts_file, old_hosts = SETTINGS.settings_cache_file, {}
        if self.override:
            old_hosts_file.unlink(missing_ok=True)
        elif old_hosts_file.exists():
            old_hosts = json.loads(old_hosts_file.read_text())

        for provider_class in SETTINGS.provider_classes:
            settings = SETTINGS.providers.get(provider_class.NAME, {})
            provider = provider_class(
                self, SETTINGS.hosts, old_hosts, settings)
            self.hosts.update(asyncio.run(provider.initialize()))

        SETTINGS.settings_cache_file.write_text(
            json.dumps(self.hosts, indent=2))
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
            grouped_tasks = []
            for host in current_hosts:
                task = getattr(task_class(self, lock, host), name)
                key = host['public_ip']
                task_added = False
                for group in grouped_tasks:
                    if key not in group:
                        group[key] = task
                        task_added = True
                        break
                if not task_added:
                    grouped_tasks.append({key: task})

            for tasks in grouped_tasks:
                await asyncio.gather(*[task(*args) for task in tasks.values()])

        asyncio.run(run())

    def _prepare_hosts(self, task_class, name):
        method = getattr(task_class, name)
        is_nohost = getattr(method, '__nohost__', False)
        is_onehost = getattr(method, '__onehost__', False)
        is_firsthost = getattr(method, '__firsthost__', False)

        if is_nohost:
            hosts = [self.nohost.copy()]
        else:
            hosts = [
                host
                for host in self.hosts.values()
                if task_class.get_namespace() in host['components']
            ]

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
