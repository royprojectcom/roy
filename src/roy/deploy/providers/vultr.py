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

    # TODO: add provider global settings (keys ssh etc.)
    async def run(self, command, key=''):
        if not key:
            for host in self.hosts.values():
                key = key or host.get('provider', {}).get('key')
        if not key:
            raise ValueError('No key provided for vultr-cli')
        return await run_in_shell(f"VULTR_API_KEY='{key}' vultr-cli {command}")

    async def get_remote_hosts(self):
        result = {}
        hosts = await self.run('instance list')
        for host in hosts.split('\n')[1:-4]:
            host = host.split()
            if host[2].startswith(f'{SETTINGS.prefix}-'):
                result[host[2]] = {
                    'id': host[0],
                    'public_ip': host[1],
                    'name': host[2],
                }
        hosts = await asyncio.gather(*[
            self.get(host['id']) for host in result.values()
        ])
        for host in hosts:
            result[host['name']].update(host)
        return result

    async def destroy(self, name, remote_hosts):
        host = remote_hosts.get(name)
        if host:
            resp = input(
                f"do you want to destroy '{name}'"
                f":{host['public_ip']}' ? [type: y or yes]: ")
            if resp.lower() in {'y', 'yes'}:
                await self.run(f"instance destroy {host['id']}")

    async def get(self, host_id):
        resp = await self.run(f"instance get {host_id}")
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

    async def create(self, host, remote_hosts):
        ssh_key = host.get('provider', {}).get('ssh-key')
        if host['name'] not in remote_hosts:
            provider = host['provider']
            resp = await self.run(
                f"instance create --os {self.OS[provider['os']]} "
                f"--plan {provider['plan']} "
                f"--region {self.REGION[provider['region']]} "
                f"--label {host['name']} "
                f"--host {host['name']} "
                f"--private-network={str(provider['private_network']).lower()} "
                f"--notify={str(provider['notify']).lower()} "
                f"--ssh-keys {ssh_key} "
                f"--auto-backup {str(provider['backup']).lower()} ",
                provider.get('key')
            )
            host_id = resp.split('ID')[1].split('\n')[0].strip()
        else:
            host_id = remote_hosts[host['name']]['id']

        info = {}
        retries = 0

        while 'ssh' not in info:
            if retries > 20:
                raise ValueError(f"Can't initialize host {host['name']}")
            retries += 1

            info = await self.get(host_id)
            if info.get('public_ip', '0.0.0.0') != '0.0.0.0':
                try:
                    await asyncio.open_connection(
                        info['public_ip'], host.get('ssh_port', 22), limit=10)
                    info['ssh'] = True
                except OSError:
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(1)

        host.update(info)
        return host

    async def initialize(self):
        if not self.hosts:
            return self.other_hosts

        old_hosts = self._old_hosts.copy()
        if old_hosts:
            return old_hosts

        current_hosts = self.hosts.copy()
        changed = False
        to_create = []

        remote_hosts = await self.get_remote_hosts()
        for name, host in old_hosts.items():
            if host.get('provider', {}).get('name') != self.NAME:
                continue
            if name not in current_hosts:
                await self.destroy(host, remote_hosts)
                changed = True
            else:
                old_host = {
                    k: v for k, v in host.items()
                    if k not in ('public_ip', 'private_ip', 'id')
                }
                if old_host != current_hosts[host['name']]:
                    changed = True

        for name in current_hosts:
            if name not in old_hosts:
                to_create.append(self.create(current_hosts[name].copy(), remote_hosts))
                changed = True

        if to_create:
            await asyncio.gather(*to_create)

        if not changed and old_hosts:
            return old_hosts

        remote_hosts = await self.get_remote_hosts()
        for host in current_hosts.values():
            host.update(remote_hosts[host['name']])

        print('** updating ssh keys')
        await self.update_ssh_keys([
            host['public_ip'] for host in current_hosts.values()
        ])

        current_hosts.update(self.other_hosts)
        return current_hosts
