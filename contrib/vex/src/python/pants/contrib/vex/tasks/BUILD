# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

target(
  name = 'tasks',
  dependencies = [
    ':vex',
  ],
)

python_library(
  name = 'vex',
  sources = [
    'vex.py',
  ],
  dependencies = [
  	'src/python/pants/backend/python/tasks:python',
  	'3rdparty/python:pex',
    '3rdparty/python:pip',
  ],
)
