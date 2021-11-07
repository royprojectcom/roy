
from pathlib import Path
from itertools import chain

import jinja2

from roy.utils.tasks import TaskRunError

from ...tasks import DeployTasks, register
from ...settings import DeployComponentSettings

from ..systemd import SystemdTasksMixin


class IPtablesSettings(DeployComponentSettings):
    NAME = 'iptables'
    SCHEMA = {
        'bin': {'type': 'string', 'required': True},
        'user': {'type': 'string', 'required': True},
        'allow': {'type': 'list', 'schema': {'type': 'string'}},
        'rules': {
            'type': 'dict',
            'schema': {
                'template': {'type': 'string', 'required': True},
                'name': {'type': 'string', 'required': True},
                'custom': {'type': 'string', 'required': True}
            }
        },
        'systemd': SystemdTasksMixin.SCHEMA
    }
    DEFAULT = {
        'bin': '/sbin/iptables-restore',
        'user': 'root',
        'allow': [],
        'rules': {
            'template': 'ipv4.rules',
            'name': 'ipv4.rules',
            'custom': 'custom.rules'
        },
        'systemd': {
            'template': 'app.service',
            'name': 'iptables.service',
            'boot': True,
            'instances': {'count': 1}
        }
    }

    @property
    def rules_template(self):
        return self.local_root / self._data['rules']['template']

    @property
    def custom_rules_template(self):
        return self.local_root / self._data['rules']['custom']

    @property
    def rules_path(self):
        return Path('/', 'etc', self._data['rules']['name'])

    @property
    def bin(self):
        return f"{self._data['bin']} {self.rules_path}"

    @property
    def allow(self):
        return self._data['allow']


SETTINGS = IPtablesSettings()


class IPtablesTasks(DeployTasks, SystemdTasksMixin):
    SETTINGS = IPtablesSettings

    @register
    async def list(self):
        print(await self._run(f'cat {self.settings.rules_path}'))

    async def get_iptables_template(self):
        return self.settings.custom_rules_template.read_text()

    @register
    async def sync(self):
        rendered = []
        access_hosts = []
        all_components = {}

        for task in self.get_all_manager_tasks():
            all_components.setdefault(task.settings.NAME, []).append(task)

        for task in chain(*all_components.values()):
            if self.host['name'] != task.host['name']:
                continue
            get_template = getattr(task, 'get_iptables_template', None)
            if get_template:
                template = jinja2.Template(
                    await get_template(), enable_async=True)
                context = {'deploy': task, 'components': all_components}
                rendered.append(await template.render_async(context))

        current_host = "\n".join(line.strip() for line in rendered if line)

        for component_name in self.settings.allow:
            for task in all_components[component_name]:
                access_hosts.append(task.host)

        await self._upload_template(
            self.settings.rules_template, self.settings.rules_path,
            {'current_host': current_host, 'access_hosts': access_hosts}
        )

        await self._sync_systemd_units()

    @register
    async def disable_ufw(self):
        try:
            await self._run('systemctl stop ufw')
            await self._run('systemctl disable ufw')
        except TaskRunError:
            pass

    @register
    async def setup(self):
        await self._apt_install('rsync', 'iptables')

        await self.disable_ufw()

        await self.sync()
        await self.start()
