import pytest

from roy.app.base import Application
from roy.app.settings import SETTINGS


class WebApplication:
    def __init__(self):
        self.called_setup = True
        self.called_run_task = False
        self.called_async_run_task = False
        self.called_from_another_setup = False
        self.components_count = 0

    def run(self, app: Application):
        self.called_run_task = True

    async def async_run(self):
        self.called_async_run_task = True

    def some_method(self):
        self.called_from_another_setup = True


def test_raise_already_registered():
    app = Application()
    with pytest.raises(ValueError):
        app.register(Application())


def test_raise_del_self():
    app = Application()
    with pytest.raises(ValueError):
        del app[Application]


def test_del():
    app = Application()
    web_app = WebApplication()
    app.register(web_app)
    del app[WebApplication]
    assert len(app.registry) == 1


class WebFakeModule:
    @staticmethod
    def link_components(app: Application):
        web_app = app[WebApplication]
        for _ in app.components:
            web_app.components_count += 1

    @classmethod
    def setup(cls, app: Application):
        web_app = WebApplication()

        app.register(web_app)
        app.register_setup_task(cls.link_components)
        app.register_run_task(web_app.run)
        app.register_run_task(web_app.async_run)
        app.register_run_task(web_app.async_run)


class AppUseWebFakeModule:
    @staticmethod
    def setup(web_app: WebApplication):
        web_app.some_method()


def test_setup_called_for_custom_app(monkeypatch):
    monkeypatch.setattr(SETTINGS, 'get_components', lambda: [
        WebFakeModule(), AppUseWebFakeModule()
    ])

    app = Application()

    web_app = app[WebApplication]
    assert web_app.called_setup
    assert web_app.called_from_another_setup

    app.run()
    assert web_app.called_run_task
    assert web_app.called_async_run_task
    assert web_app.components_count == 2
