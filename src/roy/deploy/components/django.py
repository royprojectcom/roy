from roy.utils.collections import update_dict_recur
from roy.deploy.tasks import onehost, register

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

    @onehost
    @register
    async def shell(self, prefix: str = ''):
        return await self.run('manage shell', interactive=True, prefix=prefix)
