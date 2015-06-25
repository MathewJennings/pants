# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

target(
  name = 'tasks',
  dependencies = [
    ':vex',
    ':integration'
  ],
)

python_tests(
  name = 'vex',
  sources = ['test_vex.py'],
  dependencies = [
    'contrib/vex/src/python/pants/contrib/vex/tasks:vex',
    'tests/python/pants_test/backend/python/tasks:python_task_test',
    'src/python/pants/backend/python/targets:python',
    'src/python/pants/base:source_root',
  ],
)

python_tests(
  name = 'integration',
  sources = ['vex_integration_test.py'],
  dependencies = [
    'contrib/vex/src/python/pants/contrib/vex/tasks:vex',
    'tests/python/pants_test:int-test',
  ],
)
