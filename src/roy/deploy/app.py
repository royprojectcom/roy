from .manager import DEPLOY_TASKS_MANAGER


def setup(app):
    app.register(DEPLOY_TASKS_MANAGER)
