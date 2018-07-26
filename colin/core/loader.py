# -*- coding: utf-8 -*-
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
This piece of code searches for python code on specific path and
loads AbstractCheck classes from it.
"""

import inspect
import logging
import os
import sys
import warnings

import six

from ..core.checks.fmf_check import receive_fmf_metadata, FMFAbstractCheck

logger = logging.getLogger(__name__)


def path_to_module(path, top_path):
    if top_path not in path:
        raise RuntimeError("path {} is not placed in a dir {}".format(path, top_path))
    mo = path[len(top_path):]
    import_name = mo.replace("/", ".")
    # FIXME: this tbacks when path == top_path
    if import_name[0] == ".":
        import_name = import_name[1:]
    if import_name.endswith(".py"):
        import_name = import_name[:-3]
    return import_name


def _load_module(path, top_path):
    module_name = path_to_module(path, top_path)
    logger.debug("Will try to load selected file as module '%s'.", module_name)
    if six.PY3:
        from importlib.util import module_from_spec
        from importlib.util import spec_from_file_location

        s = spec_from_file_location(module_name, path)
        m = module_from_spec(s)
        s.loader.exec_module(m)
        return m

    elif six.PY2:
        import imp

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # FIXME: let's at least debug log other warnings
            m = imp.load_source(module_name, path)
        return m


def should_we_load(kls):
    """ should we load this class as a check? """
    # we don't load abstract classes
    if kls.__name__.endswith("AbstractCheck"):
        return False
    # and we only load checks
    if not kls.__name__.endswith("Check"):
        return False
    mro = kls.__mro__
    for m in mro:
        if m.__name__ == "AbstractCheck":
            return True
    return False


def load_check_classes_from_file(path, top_path):
    logger.debug("Getting check(s) from the file '{}'.".format(path))
    m = _load_module(path, top_path)

    check_classes = []
    for _, obj in inspect.getmembers(m, inspect.isclass):
        if should_we_load(obj):
            if issubclass(obj, FMFAbstractCheck):
                node_metadata = receive_fmf_metadata(name=obj.name, path=os.path.dirname(path))
                obj.metadata = node_metadata
            check_classes.append(obj)
            # Uncomment when debugging this code.
            # logger.debug("Check class '{}' found.".format(obj.__name__))
    return check_classes


class CheckLoader(object):
    """
    find recursively all checks on a given path
    """

    def __init__(self, checks_paths):
        """
        :param checks_paths: list of str, directories where the checks are present
        """
        logger.debug("Will load checks from paths '%s'.", checks_paths)
        for p in checks_paths:
            if os.path.isfile(p):
                raise RuntimeError("Provided path %s is not a directory." % p)
        self._check_classes = None
        self._mapping = None
        self.paths = checks_paths

    def obtain_check_classes(self):
        """ find children of AbstractCheck class and return them as a list """
        check_classes = set()
        for path in self.paths:
            for sys_path in sys.path:
                if sys_path and sys_path in path:
                    # this is a directory which:
                    #   1. has to be on sys.path
                    #   2. is root of the import sequence
                    top_py_path = sys_path
                    break
            else:
                top_py_path = path
                sys.path.insert(0, path)
                logger.debug("%s is not on pythonpath, added it", path)
            for root, _, files in os.walk(path):
                for fi in files:
                    if not fi.endswith(".py"):
                        continue
                    path = os.path.join(root, fi)
                    check_classes = check_classes.union(set(
                        load_check_classes_from_file(path, top_py_path)))
        return list(check_classes)

    @property
    def check_classes(self):
        if self._check_classes is None:
            self._check_classes = self.obtain_check_classes()
        return self._check_classes

    @property
    def mapping(self):
        if self._mapping is None:
            self._mapping = {}
            for c in self.check_classes:
                self._mapping[c.name] = c
        return self._mapping
