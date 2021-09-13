import signal
import inspect
import asyncio
import weakref

from .settings import SETTINGS


class Application:
    """Used for setup in other components to provide universal way
    of decomposing apps."""

    def __init__(self, setup: bool = True):
        self.registry = {type(self): weakref.proxy(self)}

        self.async_run_tasks = []
        self.async_cleanup_tasks = []

        self.run_tasks = []
        self.cleanup_tasks = []

        self.setup_tasks = []

        if setup:
            self.setup()

        # FIXME: signals need to be properly updated
        # self.cleaning = False

        # loop = asyncio.get_event_loop()

        # for sig in [signal.SIGINT, signal.SIGTERM]:
        #     loop.add_signal_handler(sig, self.cleanup)
        #     signal.signal(sig, self.cleanup)

    def register(self, app):
        type_ = type(app)
        if type_ in self.registry:
            raise ValueError(f'App type: "{type_}" already registered')
        self.registry[type_] = app

    def __getitem__(self, type_):
        return self.registry[type_]

    def __delitem__(self, type_):
        if type_ == type(self):
            raise ValueError(f'Do not unregister self-app: "{type_}"')
        self.registry.pop(type_)

    @property
    def components(self):
        return SETTINGS.get_components()

    def register_run_task(self, func):
        if inspect.iscoroutinefunction(func):
            self.async_run_tasks.append(func)
        else:
            self.run_tasks.append(func)

    def register_setup_task(self, func):
        self.setup_tasks.append(func)

    def register_cleanup_task(self, func):
        if inspect.iscoroutinefunction(func):
            self.async_cleanup_tasks.append(func)
        else:
            self.cleanup_tasks.append(func)

    def _app_call(self, func):
        annotations = inspect.getfullargspec(func).annotations
        kwargs = {
            name: self.registry[type_]
            for name, type_ in annotations.items()
            if type_ in self.registry
        }
        return func(**kwargs)

    def setup(self):
        for component in self.components:
            self._app_call(component.setup)

        for task in self.setup_tasks:
            self._app_call(task)

    def _process(self, tasks, async_tasks):
        for task in tasks:
            self._app_call(task)

        if not async_tasks:
            return

        if len(async_tasks) == 1:
            asyncio.run(self._app_call(async_tasks[0]))
        else:
            async def run_async_tasks():
                await asyncio.gather(*[
                    self._app_call(task) for task in async_tasks
                ])
            asyncio.run(run_async_tasks())

    def run(self):
        self._process(self.run_tasks, self.async_run_tasks)

    def cleanup(self):
        # import traceback
        # traceback.print_stack()
        # print('called cleanup')
        # TODO: fix signal cleanup call from cool and app
        self._process(self.cleanup_tasks, self.async_cleanup_tasks)
