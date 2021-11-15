from pathlib import Path

from roy.utils.tasks import register

from ...tasks import DeployTasks
from ...settings import DeployComponentSettings

from ..systemd import SystemdTasksMixin


class RedisSettings(DeployComponentSettings):
    NAME = 'redis'
    SCHEMA = {
        'user': {'type': 'string', 'required': False},
        'systemd': SystemdTasksMixin.SCHEMA,
        'config': {
            'type': 'dict',
            'schema': {
                'template': {'type': 'string', 'required': True},
                'name': {'type': 'string', 'required': True}
            }
        },
        'workdir': {'type': 'string', 'required': True},
        'port': {'type': 'integer', 'required': True},
        'maxmemory': {'type': 'string', 'required': True},
        'databases': {'type': 'integer', 'required': True},
        'root': {'type': 'string', 'required': True},
        'packages': {
            'type': 'dict',
            'schema': {
                'redis': {'type': 'string', 'required': True},
            },
            'required': True
        },
        'listen_private_ip': {'type': 'boolean', 'required': False},
        'iptables': {
            'type': 'dict',
            'schema': {
                'v4': {'type': 'string', 'required': True},
            },
            'required': True
        },
    }
    DEFAULT = {
        'systemd': {
            'template': 'server.service',
            'name': 'redis.service',
            'boot': True,
            'instances': {'count': 1}
        },
        'config': {
            # http://download.redis.io/redis-stable/redis.conf
            'template': 'server.conf',
            'name': 'redis.conf'
        },

        # TODO: move to base config (base package for this type of components)
        # https://redis.io/download
        'workdir': '.',
        'port': 6379,
        'maxmemory': '64mb',
        'databases': 16,
        'listen_private_ip': True,
        'root': 'app',
        'packages': {
            'redis': 'http://download.redis.io/releases/redis-6.2.6.tar.gz'
        },
        'iptables': {
            'v4': 'ipv4.rules'
        }
    }

    @property
    def build_dir(self):
        return self.home_abs / 'build'

    @property
    def bin(self):
        return self.root_abs / 'bin' / 'redis-server'

    @property
    def packages(self):
        return self._data['packages']

    @property
    def config_template(self):
        template = self._data['config']['template']
        if not template.startswith('/'):
            template = (self.local_root / template).resolve()
        return Path(template)

    @property
    def config_path(self):
        return self.root_abs / self._data['config']['name']

    @property
    def workdir(self):
        return self.root_abs / self._data['workdir']

    @property
    def port(self):
        return self._data['port']

    @property
    def maxmemory(self):
        return self._data['maxmemory']

    @property
    def databases(self):
        return self._data['databases']

    @property
    def iptables_v4_rules(self):
        return (self.local_root / self._data['iptables']['v4']).read_text()

    @property
    def listen_private_ip(self):
        return self._data.get('listen_private_ip', False)


SETTINGS = RedisSettings()


class RedisTasks(DeployTasks, SystemdTasksMixin):
    SETTINGS = RedisSettings

    async def get_iptables_template(self):
        return self.settings.iptables_v4_rules

    @register
    async def benchmark(self, connections: int = 200):
        print(await self._run(
            f'{self.settings.bin.parent / "redis-benchmark"} -c {connections} '
            f'-h {self.public_ip} -p {self.settings.port} '
            '-t SET,GET,INCR -n 1000000 -P 100 --csv'
        ))

    @register
    async def build(self):
        await self._apt_install(
            'build-essential', 'sysfsutils', 'libsystemd-dev',
            'libjemalloc-dev', 'rsync'
        )
        await self._create_user()

        with self._set_user('root'):
            await self._run(
                'echo "kernel/mm/transparent_hugepage/enabled = never" '
                '>> /etc/sysfs.conf'
            )
            await self._run(
                'echo "vm.overcommit_memory=1" >> /etc/sysctl.conf')
            await self._run(
                'echo "net.core.somaxconn=65535" >> /etc/sysctl.conf')
            await self._run('echo "fs.file-max=100000" >> /etc/sysctl.conf')
            await self._run('sysctl -p')
            await self._run('systemctl force-reload sysfsutils')

        async with self._cd(self.settings.build_dir, temporary=True):
            for package, url in self.settings.packages.items():
                await self._download_and_unpack(url, Path('.', package))

            async with self._cd('redis'):
                await self._run('make distclean')
                await self._run(
                    "make -j$(nproc) USE_SYSTEMD=yes MALLOC=jemalloc")
                await self._run(
                    f"make PREFIX={self.settings.root_abs} install")

    @register
    async def sync(self):
        await self._upload_template(
            self.settings.config_template, self.settings.config_path)
        await self._sync_systemd_units()

    @register
    async def setup(self):
        await self.build()
        await self.sync()
        await self.start()
