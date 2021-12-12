import time
import socket
import inspect

from pathlib import Path

from roy.utils.os import run_in_shell, get_homepath
from roy.utils.collections import update_dict_recur
from roy.app.settings import validate_schema

from ..settings import SETTINGS


def wait_ping(host, port, timeout=5):
    start = time.time()
    ready = False
    while time.time() - start < timeout:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(1)
        result = connection.connect_ex((host, port))
        if result == 0:
            ready = True
            break

    return ready


class DeployProvider:
    NAME = ''
    DEFAULT = {}
    SCHEMA = {}

    # TODO: add support for different providers in one list

    def __init__(self, manager, hosts, old_hosts, settings):
        self._raw_hosts = hosts
        self._old_hosts = old_hosts
        self._hosts = {}
        self._manager = manager
        self._settings = settings

        self.project_dir = Path().cwd()
        self.local_root = Path(inspect.getfile(self.__class__)).parent

    @property
    def other_hosts(self):
        other_hosts = {}
        for name, host in self._raw_hosts.items():
            if host.get('provider', {}).get('name', '') == self.NAME:
                continue

            host['name'] = name
            if 'private_ip' not in host:
                host['private_ip'] = host['public_ip']
            other_hosts[name] = host.copy()
        return other_hosts

    @property
    def hosts(self):
        """Get list of all hosts provided by deploy configuration to
        bootstrap using local or remote provider."""
        if self._hosts:
            return self._hosts

        for name, host in self._raw_hosts.items():
            provider = host.get('provider', {})
            if provider.get('name', '') != self.NAME:
                continue

            # per host -> global providers -> default settings
            provider = update_dict_recur(
                self._settings, provider)
            provider = update_dict_recur(
                self.DEFAULT, provider)
            provider = validate_schema(self.SCHEMA, provider)

            for count in range(1, provider.get('count', 1) + 1):
                prefix = SETTINGS.prefix
                name = f"{prefix}-{name}"
                if count > 1:
                    name += f'-{count}'
                host['name'] = name
                host['provider'] = provider
                self._hosts[name] = host.copy()

        return self._hosts

    async def update_ssh_keys(self, ips):
        # TODO: update only if ip is not in known hosts (!!!)
        known_hosts = get_homepath() / '.ssh' / 'known_hosts'

        for ip in ips:
            if not wait_ping(ip, 22):
                print(f"Can't setup ssh key for {ip} because host is down")
                return

        if known_hosts.exists():
            with known_hosts.open('r+') as f:
                hosts = f.readlines()
                f.seek(0)
                for host in hosts:
                    if all(ip not in host for ip in ips):
                        f.write(host)
                f.truncate()

        for ip in ips:
            await run_in_shell(f'ssh-keyscan {ip} >> {known_hosts}')

    async def initialize(self):
        raise NotImplementedError('Initialize servers from provided services')
