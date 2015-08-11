# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

python_library(
  name='plugin',
  sources=['register.py'],
  dependencies=[
    'contrib/vend/src/python/pants/contrib/vend/tasks',
    'src/python/pants/goal:task_registrar',

  ],
  provides=contrib_setup_py(
    name='pantsbuild.pants.contrib.vend',
    description='Vend generator pants plugin.',
    additional_classifiers=[]
  )
)
