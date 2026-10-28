"""Project test runner.

Django 5.0 predates Python 3.14. In Python 3.14 ``copy.copy(super())``
returns the ``super`` object itself, which breaks Django's
``BaseContext.__copy__`` while the test client records rendered template
contexts. The shim below copies the context state directly so the suite can
run on this Python version.
"""

from django.test.runner import DiscoverRunner


def _patch_template_context_copy():
    from django.template.context import BaseContext

    if getattr(BaseContext.__copy__, '_python314_compat', False):
        return

    def __copy__(self):
        clone = object.__new__(type(self))
        clone.__dict__.update(self.__dict__)
        clone.dicts = self.dicts[:]
        return clone

    __copy__._python314_compat = True
    BaseContext.__copy__ = __copy__


_patch_template_context_copy()


class ProjectTestRunner(DiscoverRunner):
    """Standard test runner with the Python 3.14 context-copy fix."""
