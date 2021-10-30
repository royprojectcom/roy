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

    def __init__(self, manager, services):
        self._servers = []
        self._manager = manager

        self.services = services
        self.project_dir = Path().cwd()
        self.local_root = Path(inspect.getfile(self.__class__)).parent

    @property
    def other_servers(self):
        servers = []
        for scope, services in self.services.items():
            for info in services:
                for host in info['hosts']:
                    if host['provider'] == self.NAME:
                        continue
                    name = host['name']
                    for count in range(1, host['count'] + 1):
                        service_name = scope
                        if scope != name:
                            service_name = f"{scope}-{name}"
                        env = SETTINGS._data['env']
                        host['name'] = f"{env}-{service_name}-{count}"
                        host['components'] = info['components']
                        servers.append(host.copy())
        return servers

    @property
    def servers(self):
        if self._servers:
            return self._servers

        for scope, services in self.services.items():
            for info in services:
                for host in info['hosts']:
                    if host['provider'] != self.NAME:
                        continue
                    host = update_dict_recur(self.DEFAULT, host)
                    host = validate_schema(self.SCHEMA, host)
                    name = host['name']
                    for count in range(1, host['count'] + 1):
                        service_name = scope
                        if scope != name:
                            service_name = f"{scope}-{name}"
                        env = SETTINGS._data['env']
                        host['name'] = f"{env}-{service_name}-{count}"
                        host['components'] = info['components']
                        self._servers.append(host.copy())
        return self._servers

    async def update_ssh_keys(self, ips):
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
