from pathlib import Path

from roy.utils.collections import update_dict_recur
from roy.deploy.tasks import onehost, register

from .app import AppTasks, AppSettings


class PythonSettings(AppSettings):
    NAME = 'python'
    SCHEMA = update_dict_recur(AppSettings.SCHEMA, {
        'root': {'type': 'string', 'required': True},
        'version': {'type': 'string', 'required': True},
        'build': {
            'type': 'dict',
            'schema': {
                'fast': {'type': 'boolean'},
                'path': {'type': 'string'}
            },
            'required': True
        }
    })
    DEFAULT = update_dict_recur(AppSettings.DEFAULT, {
        'bin': "python3 --version",
        'user': 'python',
        'root': 'python',
        'version': '3.9.6',
        'build': {
            'fast': True,
            'path': 'build'
        },
        'systemd': {
            'config': [
                'Environment=PYTHONPATH={settings.home_abs}'
            ]
        }
    })

    @property
    def bin(self):
        return self.root_path / self._data['bin']

    @property
    def _local_root_class(self):
        return AppSettings

    @property
    def version(self):
        return self._data['version']

    @property
    def fast_build(self):
        return self._data['build']['fast']

    @property
    def build_path(self):
        return self.home_abs / self._data['build']['path']

    @property
    def site_packages_abs(self):
        return (
            self.root_abs / 'lib' /
            f'python{self.version[:3]}' / 'site-packages'
        )

    @property
    def root_path(self):
        return self.root_abs / 'bin'


SETTINGS = PythonSettings()


class PythonTasks(AppTasks):
    SETTINGS = PythonSettings

    @register
    async def pip(self, command: str):
        return await self.run(f'pip3 {command}')

    @register
    async def run(
            self, command: str, interactive: int = False, prefix: str = ''):
        if prefix:
            prefix = f'{prefix} '
        return await self._run(
            f"{prefix}{self.settings.root_path / command}",
            interactive=interactive
        )

    @onehost
    @register
    async def shell(self, prefix: str = ''):
        return await self.run('python3', interactive=True, prefix=prefix)

    @register
    async def sync(self, type_: str = ''):
        current_dir = Path.cwd()
        if not (current_dir / 'setup.py').exists():
            return

        flag = '-I' if type_ == 'force' else '-U'
        name = (await self._local('python setup.py --name')).strip()
        version = (await self._local('python setup.py --version')).strip()
        package = f'{name}-{version}.tar.gz'

        await self._upload(Path('dist', package))
        await self.pip(f'install {flag} {package}')
        await self._rmrf(Path(package))

        await self._sync_systemd_units()

    @register
    async def setup(self):
        await self.build()
        await self.sync()
        await self.start()

    @register.before(sync)
    @register.before(setup)
    async def before_sync(self):
        current_dir = Path.cwd()
        if not (current_dir / 'setup.py').exists():
            return
        await self._local('rm -rf ./build ./dist')
        await self._local('pip install -e .')
        await self._local('python setup.py sdist bdist_wheel')

    @register.after(sync)
    @register.after(setup)
    async def after_sync(self):
        await self._local('rm -rf ./build ./dist')

    @register
    async def build(self):
        await super().build()

        version = self.settings.version
        fast_build = self.settings.fast_build
        build_path = self.settings.build_path

        await self._apt_install(
            'make', 'build-essential', 'libssl-dev', 'zlib1g-dev',
            'libbz2-dev', 'libreadline-dev', 'libsqlite3-dev', 'wget', 'curl',
            'llvm', 'libncurses5-dev', 'libncursesw5-dev', 'xz-utils',
            'tk-dev', 'tcl-dev', 'libffi-dev', 'wget'
        )
        await self._mkdir(self.settings.root, delete=True)

        async with self._cd(build_path, temporary=True):
            url = 'https://www.python.org/ftp/' \
                f'python/{version}/Python-{version}.tar.xz'
            await self._download_and_unpack(url)

            await self._run(
                './configure --prefix={0} '
                '--enable-loadable-sqlite-extensions --enable-shared '
                '--with-system-expat --enable-optimizations '
                'LDFLAGS="-L{0}/extlib/lib -Wl,--rpath={0}/lib '
                '-Wl,--rpath={0}/extlib/lib" '
                'CPPFLAGS="-I{0}/extlib/include"'.format(
                    self.settings.root_abs
                )
            )
            await self._run('make -j$(nproc) {}'.format(
                'build_all' if fast_build else 'build'))
            await self._run('make install > /dev/null')

        await self.pip('install wheel')
        await self.pip('install -U pip')
        await self.pip('install -U setuptools')
