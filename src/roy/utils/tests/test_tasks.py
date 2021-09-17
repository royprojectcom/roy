import asyncio
import pytest

from roy.utils.tasks import TasksManager, Tasks, register, TaskRunError


class SimpleTasks(Tasks):
    NAMESPACE = 'simple'

    BEFORE_CALLED = 0
    AFTER_CALLED = 0

    async def multiply_by_2(self, param):
        await asyncio.sleep(0.1)
        return param * 2

    @register
    async def example(self, *numbers):
        result = 0
        for number in numbers:
            result += await self.multiply_by_2(int(number))
        result += 2
        return result

    @register
    async def run(self):
        return await self._local('echo "test"')

    @register
    async def somehook(self):
        return 4

    @register
    async def some_other_hook(self):
        return 6

    @register.before(somehook)
    @register.before(some_other_hook)
    async def somehook_before(self):
        self.__class__.BEFORE_CALLED += 1

    @register.after(somehook)
    @register.after(some_other_hook)
    async def somehook_after(self):
        self.__class__.AFTER_CALLED += 1

    @register
    async def will_raise(self):
        return await self._local('asdf1_123_342f')


def test_tasks_register_and_run():
    manager = TasksManager()
    manager.register(SimpleTasks)

    assert 'simple' in manager.tasks

    result = manager.run('simple.example:2')
    assert result == 6

    result = manager.run(*'simple.example:20 simple.example'.split())
    assert result == 2

    result = manager.run('simple.example')
    assert result == 2

    result = manager.run('simple.example', 'simple.example:2,4')
    assert result == 14

    result = manager.run('simple.run')
    assert result == 'test\n'

    with pytest.raises(TaskRunError):
        manager.run('simple.will_raise')


def test_tasks_hooks():
    manager = TasksManager()
    manager.register(SimpleTasks)

    result = manager.run(
        'simple.somehook', 'simple.example', 'simple.some_other_hook')
    assert result == 6
    assert SimpleTasks.BEFORE_CALLED == 2
    assert SimpleTasks.AFTER_CALLED == 2
