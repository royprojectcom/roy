import json
import asyncio

from pathlib import Path

import jinja2

from roy.utils.os import run_in_shell
from roy.utils.collections import update_dict_recur
from roy.app.settings import validate_schema

from . import DeployProvider
from ..settings import SETTINGS


# TODO: refactor this beast!!! xD
# move all cli sh*t into api calls directly
# add hiding keys when we copy json file
# add support for multiprovider setup (not completly override all hosts)


class VultrProvider(DeployProvider):
    NAME = 'vultr'
    DEFAULT = {
        'key': '',
        'count': 1,
        'name': '',
        'plan': 'vhf-1c-1gb',
        'os': 'Debian 11 x64 (bullseye)',
        'region': 'Paris',
        'backup': False,
        'ssh-key': '',
        'private_network': True,
        'notify': False
    }
    OS = {
        'Debian 11 x64 (bullseye)': 477
    }
    REGION = {
        'Paris': 'cdg'
    }
    SCHEMA = {
        'provider': {'type': 'string'},
        'name': {'type': 'string'},
        'key': {'type': 'string'},
        'count': {'type': 'integer'},
        'plan': {'type': 'string'},
        'os': {'type': 'string', 'allowed': list(OS.keys())},
        'region': {'type': 'string', 'allowed': list(REGION.keys())},
        'ssh-key': {'type': 'string'},
        'private_network': {'type': 'boolean'},
        'backup': {'type': 'boolean'},
        'notify': {'type': 'boolean'},
    }

    async def run(self, command, key=''):
        if not key:
            for server in self.servers:
                key = key or server.get('key')
        if not key:
            raise ValueError('No key provided for vultr-cli')
        return await run_in_shell(f"VULTR_API_KEY='{key}' vultr-cli {command}")

    @property
    async def remote_servers(self):
        if getattr(self, '_remote_servers', None):
            return self._remote_servers

        result = {}
        servers = await self.run('instance list')
        for server in servers.split('\n')[1:-4]:
            server = server.split()
            if server[2].startswith(f'{SETTINGS.env}-'):
                result[server[2]] = {
                    'id': server[0],
                    'public_ip': server[1],
                    'name': server[2],
                }
        servers = await asyncio.gather(*[
            self.get_server(s['id']) for s in result.values()
        ])
        for server in servers:
            result[server['name']].update(server)
        self._remote_servers = result

        return self._remote_servers

    async def destroy(self, server, remote_servers):
        if server['name'] not in remote_servers:
            return

        server = remote_servers.get(server['name'])
        if server:
            resp = input(
                f"do you want to destroy '{server['name']}"
                f":{server['public_ip']}' ? [type: y or yes]: ")
            if resp.lower() in {'y', 'yes'}:
                await self.run(f"instance destroy {server['id']}")

    async def get_server(self, server_id):
        resp = await self.run(f"instance get {server_id}")
        info = {}
        for line in resp.split('\n'):
            data = line.split()
            if not data:
                continue
            if data[0] == 'LABEL':
                info['name'] = data[-1]
            elif data[0] == 'MAIN':
                info['public_ip'] = data[-1]
            elif data[0] == 'INTERNAL':
                info['private_ip'] = data[-1]
                if info['private_ip'] == 'IP':
                    info['private_ip'] = info['public_ip']
        return info

    async def create(self, server, remote_servers):
        ssh_key = ''
        if not ssh_key:
            for s in self.servers:
                ssh_key = ssh_key or s.get('ssh-key')
        if server['name'] not in remote_servers:
            resp = await self.run(
                f"instance create --os {self.OS[server['os']]} "
                f"--plan {server['plan']} "
                f"--region {self.REGION[server['region']]} "
                f"--label {server['name']} "
                f"--host {server['name']} "
                f"--private-network={str(server['private_network']).lower()} "
                f"--notify={str(server['notify']).lower()} "
                f"--ssh-keys {ssh_key} "
                f"--auto-backup {str(server['backup']).lower()} ",
                server.get('key')
            )
            server_id = resp.split('ID')[1].split('\n')[0].strip()
        else:
            server_id = remote_servers[server['name']]['id']

        info = {}
        retries = 0

        while 'ssh' not in info:
            if retries > 20:
                raise ValueError(f"Can't initialize server {server['name']}")
            retries += 1

            info = await self.get_server(server_id)
            if info.get('public_ip', '0.0.0.0') != '0.0.0.0':
                try:
                    await asyncio.open_connection(
                        info['public_ip'], server.get('port', 22), limit=10)
                    info['ssh'] = True
                except OSError:
                    await asyncio.sleep(1)

        server.update(info)
        return server

    async def initialize(self):
        if not self.servers:
            return {}

        old_hosts = {}
        old_hosts_file = SETTINGS.settings_cache_file
        if self._manager.override:
            old_hosts_file.unlink(missing_ok=True)

        current_hosts = {}
        hosts = {}
        for server in self.servers:
            for component in server['components']:
                hosts.setdefault(component, []).append(server)
                current_hosts[server['name']] = server

        changed = False
        to_create = []

        if old_hosts_file.exists():
            old_hosts = json.loads(old_hosts_file.read_text())

        for host_list in old_hosts.values():
            for old_host in host_list:
                if not old_host['provider']:
                    continue
                if old_host['name'] not in current_hosts:
                    await self.destroy(old_host, await self.remote_servers)
                    changed = True
                else:
                    old_host = {
                        k: v for k, v in old_host.items()
                        if k not in ('public_ip', 'private_ip')
                    }
                    # what we should update here xDDD only migration
                    if 'id' in old_host:
                        current_hosts[old_host['name']]['id'] = old_host['id']
                    if old_host != current_hosts[old_host['name']]:
                        changed = True

        for host in current_hosts.values():
            old_host_names = [
                h['name']
                for host_list in old_hosts.values()
                for h in host_list
            ]
            if host['name'] not in old_host_names:
                to_create.append(self.create(host, await self.remote_servers))
                changed = True

        if to_create:
            await asyncio.gather(*to_create)

        if not changed and old_hosts_file.exists():
            return old_hosts

        self._remote_servers = None
        remote_servers = await self.remote_servers
        for host in current_hosts.values():
            host.update(remote_servers[host['name']])

        print('** updating ssh keys')
        await self.update_ssh_keys([
            server['public_ip'] for server in self.servers
        ])

        for server in self.other_servers:
            for component in server['components']:
                hosts.setdefault(component, []).append(server)

        old_hosts_file.write_text(json.dumps(hosts, indent=2))

        return hosts
