import importlib


class _LazyModule:
    def __init__(self, name):
        self.name = name
        self._mod = None

    def __getattr__(self, attr):
        if self._mod is None:
            self._mod = importlib.import_module(self.name)
        return getattr(self._mod, attr)


def lazy(module_name):
    return _LazyModule(module_name)
