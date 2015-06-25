# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

python_library(
  name='plugin',
  sources=['register.py'],
  dependencies=[
    'contrib/vex/src/python/pants/contrib/vex/tasks',
    'src/python/pants/goal:task_registrar',
  ],
  provides=contrib_setup_py(
    name='pantsbuild.pants.contrib.vex',
    description='Vex tgz generator pants plugins.',
    additional_classifiers=[]
  )
)
