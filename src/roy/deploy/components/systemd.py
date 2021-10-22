from pathlib import Path

from roy.utils.tasks import register, TaskRunError


class SystemdTasksMixin:
    SCHEMA = {
        'type': 'dict',
        'schema': {
            'template': {'type': 'string'},
            'name': {'type': 'string'},
            'boot': {'type': 'boolean'},
            'type': {'type': 'string'},
            'default_config': {
                'type': 'list',
                'schema': {
                    'type': 'string'
                }
            },
            'config': {
                'type': 'list',
                'schema': {
                    'type': 'string'
                }
            },
            'instances': {
                'type': 'dict',
                'schema': {
                    'count': {'type': 'integer'},
                    'percent': {'type': 'integer'}
                }
            },
            'context': {
                'type': 'dict',
                'schema': {
                    'limit_nofile': {'type': 'integer'},
                    'description': {'type': 'string'}
                }
            }
        }
    }

    async def _get_systemd_services(self):
        systemd = self.settings.systemd
        name = systemd['name']
        count = await self._calc_instances_count(**systemd['instances'])
        for instance in range(1, count + 1):
            service = systemd.copy()
            service['name'] = name.format(
                settings=self.settings, deploy=self, instance=instance)
            service['instance'] = instance
            yield service

    async def _sync_systemd_units(self):
        """Sync systemd units, delete old once if we changed
        template or count."""
        name = self.settings.NAME
        systemd_cached_file = Path(f"~/.{name}_systemd_services")
        try:
            old_units = await self._run(f"cat {systemd_cached_file}")
            old_units = {Path(s) for s in old_units.split('\n')}
        except TaskRunError:
            old_units = set()

        services = [service async for service in self._get_systemd_services()]
        new_units = {self.settings.systemd_dir / s['name'] for s in services}

        delete_units = old_units - new_units
        if delete_units:
            with self._set_user('root'):
                names = ' '.join(u.name for u in delete_units)
                await self._run(f'systemctl disable {names}')
                await self._rmrf(' '.join(str(u) for u in delete_units))
            await self._rmrf(systemd_cached_file)

        for service in services:
            service_path = self.settings.systemd_dir / service['name']
            bin_ = str(self.settings.bin).format(
                instance=service['instance'], deploy=self, settings=self.settings
            )
            context = {'instance': service['instance'], 'bin': bin_}.copy()
            context.update(service.get('context', {}))
            path = Path(service['template'])
            if not str(path).startswith('/'):
                path = (self.settings.local_root / service['template'])
                path = path.resolve()

            with self._set_user('root'):
                await self._upload_template(path, service_path, context)

            await self._run(f'echo "{service_path}" >> {systemd_cached_file}')

        with self._set_user('root'):
            await self._run('systemctl daemon-reload')
            await self._systemctl('enable', boot_only=True)

    async def _systemctl(
            self, command: str, display=False, boot_only=False):
        results = []
        async for service in self._get_systemd_services():
            if 'manage' in service and not service['manage']:
                continue
            if boot_only and not service.get('boot', False):
                continue

            with self._set_user('root'):
                result = await self._run(
                    f'systemctl {command} {service["name"]}')
            results.append(result)
        return results

    @register
    async def start(self):
        await self._systemctl('start')

    @register
    async def stop(self):
        await self._systemctl('stop')

    @register
    async def restart(self):
        await self._systemctl('restart')

    @register
    async def status(self):
        results = await self._systemctl('status')
        for result in results:
            print(result)
