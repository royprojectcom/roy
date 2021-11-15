from pathlib import Path

from roy.utils.collections import update_dict_recur
from roy.deploy.tasks import firsthost, onehost, register

from .python import PythonTasks, PythonSettings


class DjangoSettings(PythonSettings):
    NAME = 'django'
    # TODO: add jinja2 render here not default format
    DEFAULT = update_dict_recur(PythonSettings.DEFAULT, {
        'bin':
            "uvicorn --host {settings.listen_ip} "
            "--port {settings.port} "
            "--loop uvloop app.components.django.asgi:application "
            "--lifespan off --http httptools --no-access-log "
            "--log-level error",
        'port': 8000,
        'user': 'django'
    })


SETTINGS = DjangoSettings()


class DjangoTasks(PythonTasks):
    SETTINGS = DjangoSettings

    # TODO: mount using nfs to remote server

    @onehost
    @register
    async def shell(self, prefix: str = ''):
        return await self.manage('shell')

    @onehost
    @register
    async def manage(self, command: str = ''):
        return await self.run(f'manage {command}', interactive=True)

    @firsthost
    @register
    async def migrate(self):
        return await self.manage('migrate')

    @firsthost
    @register
    async def makemigrations(self, app: str = ''):
        await self.manage(f'makemigrations {app}')
        apps = await self._local('ls src')
        apps = [app for app in apps.split() if '.' not in app]
        for app in apps:
            await self._upload(
                Path(f'src/{app}'),
                self.settings.site_packages_abs / f'{app}/*',
                exclude=['*.*', '__pycache__'], from_host=True,
                include=['/**/migrations/*.py']
            )
