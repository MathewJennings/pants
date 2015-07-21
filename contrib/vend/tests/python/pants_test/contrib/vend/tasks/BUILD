# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

target(
  name = 'tasks',
  dependencies = [
    ':vend',
    ':integration'
  ],
)

python_tests(
  name = 'vend',
  sources = ['test_vend.py'],
  dependencies = [
    'contrib/vend/src/python/pants/contrib/vend/tasks:vend',
    'tests/python/pants_test/backend/python/tasks:python_task_test',
    'src/python/pants/backend/python/targets:python',
    'src/python/pants/base:source_root',
  ],
)

python_tests(
  name = 'integration',
  sources = ['vend_integration_test.py'],
  dependencies = [
    'contrib/vend/src/python/pants/contrib/vend/tasks:vend',
    'tests/python/pants_test:int-test',
  ],
)
