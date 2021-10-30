import json
import asyncio

import jinja2

from roy.utils.os import run_in_shell

from . import DeployProvider
from ..settings import SETTINGS


class VagrantProvider(DeployProvider):
    NAME = 'vagrant'
    DEFAULT = {
        'count': 1,
        'cpus': 1,
        'ram': 384,
        'image': 'generic/debian11',
        'vm': 'virtualbox'
    }
    SCHEMA = {
        'name': {'type': 'string'},
        'count': {'type': 'integer'},
        'provider': {'type': 'string'},
        'cpus': {'type': 'integer'},
        'ram': {'type': 'integer'},
        'image': {'type': 'string'},
        'vm': {'type': 'string', 'allowed': ['virtualbox', 'parallels']}
    }

    def generate_vagrant_file(self):
        template = jinja2.Template(
            (self.local_root / 'Vagrantfile').read_text())
        result = template.render(**{'provider': self})
        current_file = (self.project_dir / 'Vagrantfile')
        return current_file, result

    @staticmethod
    async def fetch_ip(server):
        ips = await run_in_shell(
            f"vagrant ssh {server['name']} --no-color "
            "--no-tty -c 'ip -j addr show dev eth1'"
        )
        public_ip = json.loads(ips)[0]['addr_info'][0]['local'].strip()
        server['public_ip'] = server['private_ip'] = public_ip
        return server

    async def initialize(self):
        # TODO: rename and convert hosts to dev.json -> as compilation
        # of settings
        old_hosts_file = SETTINGS.settings_cache_file
        if self._manager.override:
            old_hosts_file.unlink(missing_ok=True)
        if not self.servers:
            return {}

        current_hosts = {}
        hosts = {}
        vm = self.DEFAULT['vm']
        for server in self.servers:
            for component in server['components']:
                hosts.setdefault(component, []).append(server)
                current_hosts[server['name']] = server
                new_vm = server.get('vm')
                if new_vm != self.DEFAULT['vm']:
                    vm = new_vm
                server['vm'] = vm

        vagrant_file, vagrant_contents = self.generate_vagrant_file()
        if old_hosts_file.exists():
            changed = False
            vm_changed = False
            old_hosts = json.loads(old_hosts_file.read_text())
            for host_list in old_hosts.values():
                for old_host in host_list:
                    if old_host.get('vm', vm) != vm:
                        vm_changed = True
                        break
                    if old_host['name'] not in current_hosts:
                        await run_in_shell(
                            f"vagrant destroy {old_host['name']} -g -f")
                        changed = True
                    else:
                        old_host = {
                            k: v for k, v in old_host.items()
                            if k not in ('public_ip', 'private_ip')
                        }
                        if old_host != current_hosts[old_host['name']]:
                            changed = True
                if vm_changed:
                    break
            if vm_changed:
                changed = True
                print(f"** provider changed to '{vm}', destroying old servers")
                await run_in_shell('vagrant destroy -fg')

            if not changed:
                return old_hosts

        print('** updating servers')
        vagrant_file.write_text(vagrant_contents)
        await run_in_shell(f"vagrant up --provider {vm}")

        print('** servers updated, updating IPs')
        tasks = [
            self.fetch_ip(server)
            for server in self.servers
        ]
        await asyncio.gather(*tasks)

        print('** updating ssh keys')
        await self.update_ssh_keys([
            server['public_ip'] for server in self.servers
        ])

        for server in self.other_servers:
            for component in server['components']:
                hosts.setdefault(component, []).append(server)
        old_hosts_file.write_text(json.dumps(hosts, indent=2))

        print('** server setup completed')
        return hosts
