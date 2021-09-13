import logging
import asyncio
import typing

from functools import partial

from .os import run_in_shell, RunInShellError


def register(method: typing.Any) -> typing.Any:
    method.__task__ = True

    def before(func):
        method.__task__before__ = func
        return method
    method.before = before

    def after(func):
        method.__task__after__ = func
        return method
    method.after = after

    return method


class TaskRunError(Exception):
    pass


class Tasks:
    NAMESPACE = ''

    def __init__(self, manager):
        self._manager = manager
        self._logger = logging.getLogger(self.__class__.__name__)

    @classmethod
    def get_namespace(cls) -> str:
        namespace = cls.NAMESPACE
        if not namespace:
            raise ValueError('Please define NAMESPACE for {}'.format(cls))
        return namespace

    @staticmethod
    async def _local(command, interactive=False):
        try:
            # log running command
            # log run command on RemoteManager
            return await run_in_shell(command, interactive)
        except RunInShellError as err:
            raise TaskRunError(err)


class TasksManager:
    def __init__(self):
        self.tasks = {}

    def register(self, task_class):
        self.tasks[task_class.get_namespace()] = task_class

    def run_task(self, task_class, name, args):
        task = getattr(task_class(self), name)
        return asyncio.run(task(*args))

    def run_hook(self, task_class, name, hook_name):
        instance = task_class(self)
        task = getattr(instance, name)
        task = getattr(task, f'__task__{hook_name}__')
        return asyncio.run(task(instance))

    def run(self, *commands) -> typing.Any:
        result = None
        before_hooks_to_run = []
        tasks_to_run = []
        after_hooks_to_run = []

        for command in commands:
            namespace, name = command.split('.')

            if namespace not in self.tasks:
                raise KeyError(f'No tasks registered for: "{namespace}"')
            task_class = self.tasks[namespace]
            args = []
            if ':' in name:
                name, task_args = name.split(':')
                args = task_args.split(',')

            try:
                method = getattr(task_class, name)
            except AttributeError:
                pass
                
            before_func = getattr(method, '__task__before__', None)
            after_func = getattr(method, '__task__after__', None)

            if before_func:
                before_hooks_to_run.append(
                    partial(self.run_hook, task_class, name, 'before'))
            if getattr(method, '__task__', None) and name == method.__name__:
                tasks_to_run.append(
                    partial(self.run_task, task_class, name, args))
            if after_func:
                after_hooks_to_run.append(
                    partial(self.run_hook, task_class, name, 'after'))

        for task in before_hooks_to_run:
            task()

        for task in tasks_to_run:
            result = task()

        for task in after_hooks_to_run:
            task()

        return result
