from pathlib import Path

from roy.utils.tasks import TaskRunError

from roy.deploy.tasks import (
    DeployComponentSettings, DeployTasks, register
)
from roy.deploy.components.systemd import SystemdTasksMixin


class PostgresSettings(DeployComponentSettings):
    NAME = 'postgres'
    SCHEMA = {
        'bin': {'type': 'string', 'required': True},
        'user': {'type': 'string', 'required': False},
        'port': {'type': 'integer', 'required': True},
        'systemd': SystemdTasksMixin.SCHEMA,
        'root': {'type': 'string', 'required': True},
        'password': {'type': 'string', 'required': True},
        'build_dir': {'type': 'string', 'required': True},
        'data_dir': {'type': 'string', 'required': True},
        'locale': {'type': 'string', 'required': True},
        'configs': {'type': 'list', 'schema': {'type': 'string'}},
        'listen_private_ip': {'type': 'boolean', 'required': False},
        'sources': {
            'type': 'dict',
            'schema': {
                'postgres': {'type': 'string', 'required': True},
            },
            'required': True
        },
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
            'name': 'postgres.service',
            'boot': True,
            'instances': {'count': 1}
        },
        'root': 'app',
        'bin': 'postgres -D {settings.data_dir}',
        'password': 'postgres',
        'build_dir': 'build',
        'data_dir': 'data',
        'port': 5432,
        'listen_private_ip': True,
        'locale': 'en_US.UTF-8',
        'sources': {
            'postgres': 'https://ftp.postgresql.org/pub/source'
                        '/v14.1/postgresql-14.1.tar.gz',
        },
        'configs': ['pg_hba.conf', 'postgresql.conf'],
        'iptables': {
            'v4': 'ipv4.rules'
        },
        # 'databases': {
        #     'user_name': 'db1'
        # }
        # 'contrib': {
        #     # https://www.postgresql.org/docs/current/adminpack.html
        #     'adminpack': {'enabled': True},

        #     # https://www.postgresql.org/docs/current/amcheck.html
        #     'amcheck': {'enabled': True},

        #     # https://www.postgresql.org/docs/current/auth-delay.html
        #     'auth_delay': {'enabled': True},

        #     # https://www.postgresql.org/docs/current/auto-explain.html
        #     'auto_explain': {'enabled': True},

        #     # https://www.postgresql.org/docs/current/bloom.html
        #     'bloom': {'enabled': True},

        #     # btree_gin, https://www.postgresql.org/docs/current/btree-gin.html
        #     # btree_gist, citext, cube
        # }
        # https://www.postgresql.org/ftp/source/
    }

    @property
    def bin(self):
        return self.root_abs / 'bin' / self._data['bin']

    @property
    def port(self):
        return self._data['port']

    @property
    def sources(self):
        return self._data['sources']

    @property
    def build_dir(self):
        return self._data['build_dir']

    @property
    def data_dir(self):
        return self.root_abs / self._data['data_dir']

    @property
    def configs(self):
        for config in self._data['configs']:
            yield config, self.local_root / config

    @property
    def locale(self):
        return self._data['locale']

    @property
    def iptables_v4_rules(self):
        return (self.local_root / self._data['iptables']['v4']).read_text()

    @property
    def listen_private_ip(self):
        return self._data.get('listen_private_ip', False)


SETTINGS = PostgresSettings()


class PostgresTasks(DeployTasks, SystemdTasksMixin):
    SETTINGS = PostgresSettings

    async def get_iptables_template(self):
        return self.settings.iptables_v4_rules

    @register
    async def build(self):
        await self._create_user()

        await self._apt_install(
            'build-essential', 'flex', 'bison', 'libreadline6-dev '
            'zlib1g-dev', 'libossp-uuid-dev', 'libsystemd-dev',
            'rsync'
        )
        async with self._cd(self.settings.build_dir, temporary=True):
            for package, url in self.settings.sources.items():
                await self._download_and_unpack(url, Path('.', package))
            async with self._cd('postgres'):
                await self._run(
                    f'./configure --with-systemd '
                    f'--prefix={self.settings.root_abs}'
                )

                async with self._cd('contrib'):
                    await self._run('make')

                # TODO: add custom contrib packages configuration
                # for contrib in str(await self._run('ls contrib')).split():
                #     if contrib
                #     async with self._cd(f'contrib/{contrib}'):
                #         await self._run('ls')

                await self._run('make -j$(nproc)')
                await self._run('make install')

    @register
    async def sync(self):
        for name, config_path in self.settings.configs:
            await self._upload_template(
                config_path, self.settings.data_dir / name)
        await self._sync_systemd_units()

    @register
    async def make_data_dir(self):
        init_db_bin = self.settings.root_abs / 'bin' / 'initdb'
        try:
            await self._run(f'ls {self.settings.data_dir}')
            init_db = False
        except TaskRunError:
            init_db = True

        if init_db:
            await self._run(
                f'{init_db_bin} -D {self.settings.data_dir} '
                f'--locale {self.settings.locale}'
            )

    @register
    async def psql(self, command: str = ''):
        if command:
            command = f' -c "{command}"'
        return await self._run(
            self.settings.root_abs / 'bin' / f'psql{command}',
            interactive=not bool(command)
        )

    @register
    async def create_user(self, name, password=''):
        password = password or ''
        await self.psql(
            f"CREATE USER {name} WITH ENCRYPTED PASSWORD '{name}';")

    @register
    async def create_database(self, name, user=''):
        user = user or name
        await self.psql(f'CREATE DATABASE {name};')
        await self.psql(f'GRANT ALL PRIVILEGES ON DATABASE {name} TO {user};')

    @register
    async def drop_database(self, name):
        await self.psql(f'DROP DATABASE IF EXISTS {name};')

    @register
    async def setup(self):
        await self.build()
        await self.make_data_dir()
        await self.sync()
        await self.start()
