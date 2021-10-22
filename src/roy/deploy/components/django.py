from roy.utils.collections import update_dict_recur
from roy.deploy.tasks import onehost, register

from .python import PythonTasks, PythonSettings


class DjangoSettings(PythonSettings):
    NAME = 'django'
    DEFAULT = update_dict_recur(PythonSettings.DEFAULT, {
        'bin':
            "uvicorn --host {{ deploy.ip }} "
            "--port {{ settings.port + instance - 1 }} "
            "--loop uvloop app.components.django.asgi:application "
            "--lifespan off --http httptools",
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
