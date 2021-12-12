from pathlib import Path

from roy.utils.tasks import register

from ...tasks import DeployTasks, as_root
from ...settings import DeployComponentSettings

from ..systemd import SystemdTasksMixin


class NginxSettings(DeployComponentSettings):
    NAME = 'nginx'
    SCHEMA = {
        'user': {'type': 'string', 'required': False},
        'systemd': SystemdTasksMixin.SCHEMA,
        'root': {'type': 'string', 'required': True},
        'master': {'type': 'boolean', 'required': True},
        'packages': {
            'type': 'dict',
            'schema': {
                'nginx': {'type': 'string', 'required': True},
                'pcre': {'type': 'string', 'required': True},
                'zlib': {'type': 'string', 'required': True},
                'openssl': {'type': 'string', 'required': True},
            },
            'required': True
        },
        'packages_dir': {
            'type': 'dict',
            'required': False
        },
        'configs': {'type': 'dict'},
        'connections': {'type': 'integer', 'required': True},
        'workers': {'type': 'integer', 'required': True},
        'aio': {'type': 'boolean', 'required': True},
        'sendfile': {'type': 'boolean', 'required': True},
        'tcp_nopush': {'type': 'boolean', 'required': True},
        'tcp_nodelay': {'type': 'boolean', 'required': True},
        'keepalive_timeout': {'type': 'integer', 'required': True},
        'include': {'type': 'string', 'required': True},
        'access_log': {'type': 'string', 'required': True},
        'error_log': {'type': 'string', 'required': True},
        'default_type': {'type': 'string', 'required': True},
        'iptables': {
            'type': 'dict',
            'schema': {
                'v4': {'type': 'string', 'required': True}
            },
            'required': True
        }
    }
    DEFAULT = {
        'systemd': {
            'template': 'server.service',
            'name': 'nginx.service',
            'boot': True,
            'instances': {'count': 1}
        },
        'master': True,
        'root': 'app',
        # https://nginx.org/
        'packages': {
            'nginx': 'http://nginx.org/download/nginx-1.21.4.tar.gz',
            'pcre': 'https://sourceforge.net/projects/pcre/files/pcre/8.45/pcre-8.45.tar.gz',
            'zlib': 'http://www.zlib.net/zlib-1.2.11.tar.gz',
            'openssl': 'https://www.openssl.org/source/openssl-1.1.1l.tar.gz',
        },
        'packages_dir': {
            'geoip2': 'ngx_http_geoip2_module-master',
        },
        'configs': {'server.conf': 'nginx.conf'},
        'connections': 1000,
        'workers': 1,
        'aio': True,
        'sendfile': True,
        'tcp_nopush': True,
        'tcp_nodelay': True,
        'keepalive_timeout': 60,
        'include': 'conf/apps/*.conf',
        'access_log': 'logs/access.log',
        'error_log': 'logs/error.log',
        'default_type': 'application/octet-stream',
        'iptables': {'v4': 'ipv4.rules'}
    }

    @property
    def bin(self):
        # TODO: move from server.service
        return ''

    @property
    def build(self):
        return self.root / 'build'

    @property
    def packages(self):
        return self._data['packages']

    @property
    def packages_dir(self):
        return self._data.get('packages_dir', {})

    @property
    def configs(self):
        for template, name in self._data['configs'].items():
            if not template.startswith('/'):
                template = (self.local_root / template).resolve()
            yield Path(template), self.root / 'conf' / name

    @property
    def include(self):
        return self.root_abs / self._data['include']

    @property
    def access_log(self):
        return self.root_abs / self._data['access_log']

    @property
    def error_log(self):
        return self.root_abs / self._data['error_log']

    @property
    def default_type(self):
        return self._data['default_type']

    @property
    def aio(self):
        return 'on' if self._data['aio'] else 'off'

    @property
    def sendfile(self):
        return self._data['sendfile']

    @property
    def tcp_nopush(self):
        return self._data['tcp_nopush']

    @property
    def tcp_nodelay(self):
        return self._data['tcp_nodelay']

    @property
    def keepalive_timeout(self):
        return self._data['keepalive_timeout']

    @property
    def workers(self):
        return self._data['workers']

    @property
    def connections(self):
        return self._data['connections']

    @property
    def master(self):
        return self._data['master']

    @property
    def iptables_v4_rules(self):
        return (self.local_root / self._data['iptables']['v4']).read_text()


SETTINGS = NginxSettings()


class NginxTasks(DeployTasks, SystemdTasksMixin):
    SETTINGS = NginxSettings

    async def get_iptables_template(self):
        return self.settings.iptables_v4_rules

    @register
    async def build(self):
        if not self.settings.master:
            print('Nginx already builded on this host, just use nginx.sync')
            return

        await self._create_user()
        await self._mkdir(self.settings.include.parent)
        await self._apt_install(
            'build-essential', 'autotools-dev', 'libexpat-dev',
            'libgd-dev', 'libgeoip-dev', 'liblua5.1-0-dev',
            'libmhash-dev', 'libpam0g-dev', 'libperl-dev',
            'libxslt1-dev', 'rsync'
        )

        async with self._cd(self.settings.build, temporary=True):
            for package, url in self.settings.packages.items():
                await self._download_and_unpack(
                    url, Path('.', package),
                    archive_dir_name=self.settings.packages_dir.get(package)
                )

            async with self._cd('nginx'):
                build_command = (
                    f"./configure --prefix={self.settings.root_abs} "
                    f"--user='{self.user}' --group='{self.user}' "
                    "--with-pcre=../pcre "
                    "--with-pcre-jit --with-zlib=../zlib "
                    "--with-openssl=../openssl --with-http_ssl_module "
                    "--with-http_v2_module --with-threads "
                    "--with-file-aio --with-http_realip_module "
                )
                await self._run(build_command)
                await self._run('make -j$(nproc)')
                await self._run('make install')

    @register
    async def sync(self):
        for template, path in self.settings.configs:
            await self._upload_template(template, path)

        # nginx configs from other projects
        for task in self.get_all_manager_tasks():
            get_configs = getattr(task, 'get_nginx_include_configs', None)
            if get_configs is None:
                continue

            configs = await get_configs()
            for template, path in configs:
                await self._upload_template(
                    template,
                    self.settings.root / self.settings.include.parent
                    / path, {'deploy': task, 'nginx_deploy': self}
                )

        await self._sync_systemd_units()

    @register
    async def setup(self):
        await self.build()
        await self.sync()
        await self.start()
