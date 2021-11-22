import os
import sys
import importlib

from pathlib import Path


def run():
    sys.path.append(str(Path().cwd()))
    env, commands = sys.argv[1], sys.argv[2:]
    module_path = None
    modules = ['app.settings.', 'settings.', '']
    for module in modules:
        try:
            module_path = f'{module}{env}'
            importlib.import_module(module_path)
            break
        except ImportError:
            module_path = ''
            continue

    if not module_path:
        raise ValueError(f'Settings "{env}" not found in modules {modules}')

    try:
        os.environ['SETTINGS'] = module_path
        from .manager import DEPLOY_TASKS_MANAGER
        DEPLOY_TASKS_MANAGER.run(*commands)
    except KeyboardInterrupt:
        pass
    finally:
        os.environ.pop('SETTINGS')
