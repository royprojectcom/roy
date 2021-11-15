import logging
import asyncio
import typing

from functools import partial, wraps

from .os import run_in_shell, RunInShellError


def register(method: typing.Any) -> typing.Any:
    method.__task__ = True
    return method


def _register_hook(name: str, method: typing.Callable):
    def decorator(hook_func):
        hooks = getattr(method, name, [])
        hooks.append(hook_func)
        setattr(method, name, hooks)
        return hook_func
    return decorator


def before(method: typing.Callable):
    return _register_hook('__task__before__', method)


def after(method: typing.Callable):
    return _register_hook('__task__after__', method)


register.before = before
register.after = after


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

    async def _local(self, command, interactive=False, debug=True):
        try:
            if self._manager.debug and debug:
                print(f"[local] {command}")
            return await run_in_shell(command, interactive)
        except RunInShellError as err:
            raise TaskRunError(err)


class TasksManager:
    def __init__(self):
        self.tasks = {}
        self.debug = False

    def register(self, task_class):
        self.tasks[task_class.get_namespace()] = task_class

    def run_task(self, task_class, name, args):
        task = getattr(task_class(self), name)
        return asyncio.run(task(*args))

    def run_hooks(self, task_class, name, hook_name, instance=None):
        instance = instance or task_class(self)
        task = getattr(instance, name)
        hooks = getattr(task, f'__task__{hook_name}__', [])

        if not hooks:
            return

        async def _run_hooks_gather():
            await asyncio.gather(*[hook(instance) for hook in hooks])

        asyncio.run(_run_hooks_gather())

    def run(self, *commands) -> typing.Any:
        result = None
        before_hooks_to_run = []
        after_hooks_to_run = []
        tasks_to_run = []
        commands = list(commands)
        if '-v' in commands:
            commands.remove('-v')
            self.debug = True

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
                print(f'Method "{name}" in {task_class} not found')
                continue

            before_hooks_to_run.append(
                partial(self.run_hooks, task_class, name, 'before')
            )

            if getattr(method, '__task__', None) and name == method.__name__:
                tasks_to_run.append(
                    partial(self.run_task, task_class, name, args))

            after_hooks_to_run.append(
                partial(self.run_hooks, task_class, name, 'after')
            )

        for run_hooks in before_hooks_to_run:
            run_hooks()

        for task in tasks_to_run:
            result = task()

        for run_hooks in after_hooks_to_run:
            run_hooks()

        return result
