from roy.app.base import Application


def multiply():
    print('multiply', 2 * 2)


def setup(app: Application):
    app.register_run_task(multiply)
