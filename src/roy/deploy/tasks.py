import asyncio
import logging
import functools

from contextlib import contextmanager, asynccontextmanager
from pathlib import Path

import jinja2

from roy.utils.tasks import Tasks, TaskRunError, register

from .settings import DeployComponentSettings


def as_root(func):
    """Task will run from root, sets to self.user."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        with self._set_user('root'):
            return await func(self, *args, **kwargs)

    return wrapper


def nohost(task):
    task.__nohost__ = True
    return task


def onehost(task):
    task.__onehost__ = True
    return task


def firsthost(task):
    task.__firsthost__ = True
    return task


class DeployTasks(Tasks):
    SETTINGS = None

    def __init__(self, manager, lock, host):
        if self.SETTINGS is None or \
                not issubclass(self.SETTINGS, DeployComponentSettings):
            raise ValueError(
                "Provide correct 'SETTINGS' value "
                "should be an subclass of 'DeployComponentSettings' not "
                f"[{self.SETTINGS}]"
            )

        self.settings = self.SETTINGS(host=host)
        self.host_name = self.settings.host_name
        self.public_ip = self.settings.public_ip
        self.private_ip = self.settings.private_ip
        self.ssh_port = self.settings.ssh_port
        self.user = self.settings.user

        self._current_prefix = ''
        self._logger = logging.getLogger(self.__class__.__name__)
        self._lock = lock

        super().__init__(manager)

    @classmethod
    def get_namespace(cls):
        return cls.SETTINGS.NAME

    def get_all_manager_tasks(self, name: str = ''):
        for host in self._manager.hosts.values():
            if name in host.get('components', {}):
                task_class = self._manager.tasks[name]
                if issubclass(task_class, DeployTasks):
                    yield task_class(self._manager, self._lock, host)

    async def _calc_instances_count(self, count: int = 0, percent: int = 0):
        if percent:
            cpu_cores = int(await self._run('nproc --all'))
            cpu_cores = int(cpu_cores / 100.0 * percent)
            cpu_cores += count
            count = cpu_cores
        return count or 1

    @contextmanager
    def _set_user(self, user):
        old_user = self.user
        self.user = user
        try:
            yield self
        finally:
            self.user = old_user

    @contextmanager
    def _set_from_tasks(self, tasks):
        old_public_ip, old_private_ip, old_port, old_user =\
            self.public_ip, self.private_ip, self.ssh_port, self.user
        self.public_ip, self.private_ip, self.ssh_port, self.user =\
            tasks.public_ip, tasks.private_ip, tasks.ssh_port, tasks.user
        try:
            yield self
        finally:
            self.public_ip, self.private_ip, self.ssh_port, self.user =\
                old_public_ip, old_private_ip, old_port, old_user

    @contextmanager
    def _prefix(self, command):
        old_prefix = self._current_prefix
        self._current_prefix = f'{self._current_prefix} {command} '
        try:
            yield
        finally:
            self._current_prefix = old_prefix

    @asynccontextmanager
    async def _cd(self, path: Path, temporary=False):
        if temporary:
            await self._mkdir(path, delete=True)
        try:
            with self._prefix(f'cd {path} &&'):
                yield
        finally:
            if temporary:
                await self._rmrf(path)

    @as_root
    async def _sudo(self, command, strip=True):
        """Run command on server as root user."""
        return await self._run(command, strip)

    async def _wait(self, timeout: int):
        await asyncio.sleep(timeout)

    async def _reboot(self, timeout: int = 20):
        try:
            await self._sudo('reboot')
        except TaskRunError:
            pass
        await self._wait(timeout)

    async def _create_user(self):
        """Create user if not exist and sync ssh keys."""
        user = self.user
        local_ssh_public_key = Path('~/.ssh/id_rsa.pub')
        local_ssh_public_key = local_ssh_public_key.expanduser()
        keys_path = Path(
            '/', 'home' if user != 'root' else '', user, '.ssh')

        with self._set_user('root'):
            try:
                await self._run("id -u {}".format(user))
            except TaskRunError:
                await self._run(
                    "adduser --quiet --disabled-password"
                    " --gecos \"{0}\" {0}".format(user)
                )
            try:
                await self._run(f"cat {keys_path / 'authorized_keys'}")
            except TaskRunError:
                await self._mkdir(keys_path)
                await self._run(f'chown -hR {user} {keys_path}')
                await self._run('echo "{}" >> {}'.format(
                    local_ssh_public_key.read_text().strip(),
                    keys_path / 'authorized_keys'
                ))

    @as_root
    async def _apt_install(self, *packages):
        with self._prefix('DEBIAN_FRONTEND=noninteractive'):
            await self._run('apt-get update -y -q')
            await self._run(
                'apt-get install -y -q --no-install-recommends '
                '--no-install-suggests {}'.format(' '.join(packages))
            )

    async def _run(self, command, strip=True, interactive=False) -> str:
        command = str(command).replace('"', r'\"').replace('$(', r'\$(')
        interactive_flag = '-t' if interactive else ''
        if self._manager.debug:
            print(
                f"[{self.host_name}:"
                f"{self.user}@{self.public_ip}] {command}"
            )
        response = await self._local(
            f"ssh {interactive_flag} -p {self.ssh_port} "
            f"{self.user}@{self.public_ip} "
            f'"{self._current_prefix}{command}"',
            interactive=interactive, debug=False
        ) or ''
        if strip:
            response = response.strip()
        return response

    async def _rmrf(self, path: Path):
        await self._run(f'rm -rf {path}')

    async def _mkdir(self, path: Path, delete=False):
        if delete:
            await self._rmrf(path)
        await self._run(f'mkdir -p {path}')

    async def _upload(
            self, local_path: Path, path: Path = None,
            exclude=None, include=None, from_host=False):
        exclude = [f"--exclude '{path}'" for path in exclude or []]
        exclude = ' '.join(exclude)
        dir_slash = '/' if local_path.is_dir() else ''
        if not path:
            path = Path('~/', local_path.name)
        paths = [
            f"{local_path}{dir_slash}",
            f"{self.user}@{self.public_ip}:{path}"
        ]
        if from_host:
            paths.reverse()
        paths = ' '.join(paths)
        include = ' '.join(f"--include '{i}'" for i in include or [])
        if local_path.exists() or from_host:
            await self._local(
                f'rsync -rave "ssh -p {self.ssh_port}" --delete {include} '
                f'{exclude} {paths}'
            )

    async def _upload_template(
            self, local_path: Path, path: Path, context: dict = None):
        context = context or {}
        context.setdefault('deploy', self)
        context.setdefault('settings', self.settings)

        async with self._lock:
            render_path = Path(f'{local_path}.render')
            template = jinja2.Template(
                local_path.read_text(), enable_async=True)
            render_path.write_text(await template.render_async(context))
            try:
                await self._upload(render_path, path)
            finally:
                render_path.unlink()

    async def _download_and_unpack(
            self, url: str, dest_dir: Path = Path('.'),
            archive_dir_name: str = ''):
        await self._run(f'wget -q {url}')
        archive = url.split('/')[-1]
        await self._run(f'tar xf {archive}')
        archive_dir = archive_dir_name or archive.split('.tar')[0]

        if '*' in archive_dir:
            new_archive_dir = await self._run(
                f"ls -d */ | grep '{archive_dir}'")
            if not new_archive_dir:
                raise ValueError(f'No archive dir found {new_archive_dir}')
            archive_dir = new_archive_dir.rstrip('/')

        await self._mkdir(dest_dir)
        await self._run(f'mv {archive_dir}/* {dest_dir}')

        await self._rmrf(archive)
        await self._rmrf(archive_dir)

    async def _append(self, content, dest_file: Path):
        await self._run(
            f'grep -qxF "{content}" {dest_file} || '
            f'echo "{content}" >> {dest_file}'
        )

    @register
    @onehost
    async def ssh(self):
        return await self._run('bash', interactive=True)

    @register
    @onehost
    @as_root
    async def root(self):
        return await self._run('bash', interactive=True)
