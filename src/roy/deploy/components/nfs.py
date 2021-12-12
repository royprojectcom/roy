from ..tasks import DeployTasks, TaskRunError, register
from ..settings import DeployComponentSettings


class NFSSettings(DeployComponentSettings):
    NAME = 'nfs'
    SCHEMA = {
        'user': {'type': 'string', 'required': True},
        'mount': {
            'type': 'list',
            'schema': {
                'type': 'dict',
                'schema': {
                    'from': {'type': 'string', 'required': True},
                    'dir': {'type': 'string', 'required': True},
                    'ip': {'type': 'string', 'required': False}
                }
            }
        },
        'export': {
            'type': 'list',
            'schema': {
                'type': 'dict',
                'schema': {
                    'chmod': {'type': 'integer', 'required': False},
                    'user': {'type': 'string', 'required': False},
                    'name': {'type': 'string', 'required': True},
                    'dir': {'type': 'string', 'required': True},
                    'config': {'type': 'string', 'required': True}
                }
            }
        },
        'service': {'type': 'string', 'required': True},
        'install': {'type': 'boolean', 'required': True}
    }
    DEFAULT = {
        'user': 'root',
        'mount': [],
        'export': [],
        'install': True,
        'service': 'nfs-kernel-server'
    }

    @property
    def mount(self):
        return self._data['mount']

    @property
    def export(self):
        return self._data['export']

    @property
    def service(self):
        return self._data['service']

    @property
    def install(self):
        return self._data['install']


SETTINGS = NFSSettings()


class NFSDeployTasks(DeployTasks):
    SETTINGS = NFSSettings

    @register
    async def setup(self):
        await self.install()
        await self.export()
        await self.mount()

    @register
    async def install(self):
        if not self.settings.install:
            return
        if self.settings.mount:
            await self._apt_install('rsync', 'nfs-common')
        if self.settings.export:
            await self._apt_install('rsync', self.settings.service)

    @register
    async def export(self):
        for export in self.settings.export:
            for component in self.get_all_manager_tasks(self.settings.NAME):
                for mount in component.settings.mount:
                    if mount['from'] != export['name']:
                        continue

                    public_ip = component.settings.public_ip
                    private_ip = component.settings.private_ip
                    configs = [
                        f"{export['dir']} {ip}({export['config']})"
                        for ip in (mount.get('ip'), private_ip, public_ip)
                        if ip
                    ]

                    with self._set_user(export.get('user', self.settings.user)):
                        try:
                            await self._run(f"ls {export['dir']}")
                        except TaskRunError:
                            await self._run(f"mkdir -p {export['dir']}")

                        if 'chmod' in export:
                            await self._run(
                                f"chmod -R {export['chmod']} {export['dir']}")

                    with self._set_user('root'):
                        for config in configs:
                            await self._append(config, '/etc/exports')

                    await self._sudo("exportfs -arv")
                    await self._sudo(
                        f"systemctl reload {self.settings.service}")

    @register
    async def mount(self):
        for mount in self.settings.mount:
            try:
                await self._run(f"umount {mount['dir']}")
            except TaskRunError:
                pass
            try:
                await self._run(f"rmdir {mount['dir']}")
            except TaskRunError:
                pass

            await self._run(f"mkdir -p {mount['dir']}")

            for component in self.get_all_manager_tasks(self.get_namespace()):
                for export in component.settings.export:
                    if mount['from'] == export['name']:
                        await self._run(
                            f"mount -t nfs {component.public_ip}:"
                            f"{export['dir']} {mount['dir']} -vvv"
                        )
