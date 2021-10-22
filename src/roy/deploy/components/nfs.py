# from ..tasks import DeployTasks
# from ..settings import SERVICES_SCHEMA, DeployComponentSettings


# class NFSClientSettings(DeployComponentSettings):
#     KEY = 'nfs.client'
#     SCHEMA = {
#         'mount': {
#             'keyschema': {'type': 'string'},
#             'valueschema': {'type': 'string'},
#         }
#     }
#     DEFAULT = {
#         'mount': {}
#     }

#     @property
#     def mount(self):
#         return self._data['mount']


# CLIENT_SETTINGS = NFSClientSettings()


# class NFSServerSettings(DeployComponentSettings):
#     KEY = 'nfs.server'
#     SCHEMA = {
#         'export': {'type': 'list', 'schema': {'type': 'string'}},
#     }
#     DEFAULT = {
#         'export': []
#     }


# SERVER_SETTINGS = NFSServerSettings()


# class NFSClientDeployTasks(DeployTasks):
#     SETTINGS = CLIENT_SETTINGS

#     async def build(self):
#         await self._apt_install('rsync', 'nfs-common')
    
#     async def sync(self):
#         for ext_folder, local_folder in self.settings.mount:
#             try:
#                 items = await self._sudo("ls /nfs/data")
#             except TaskRunError:
#                 await self._sudo("mkdir -p /nfs/data")
#             if not items:
#                 await self._sudo("mount {}:/mnt/data /nfs/data")


# class NFSServerDeployTasks(DeployTasks):
#     SETTINGS = SERVER_SETTINGS

#     async def build(self):
#         await self._apt_install('rsync', 'nfs-kernel-server')
