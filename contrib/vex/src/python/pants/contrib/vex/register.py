# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

from pants.contrib.vex.tasks.vex import Vex
from pants.goal.task_registrar import TaskRegistrar as task


def register_goals():
  task(name='vex', action=Vex).install()
