# coding=utf-8
# Copyright 2014 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import shutil

from pants.backend.jvm.subsystems.jvm_tool_mixin import JvmToolMixin
from pants.backend.jvm.targets.jar_dependency import JarDependency
from pants.backend.jvm.targets.jar_library import JarLibrary
from pants.backend.jvm.tasks.bootstrap_jvm_tools import BootstrapJvmTools
from pants.base.build_file_aliases import BuildFileAliases
from pants.ivy.bootstrapper import Bootstrapper
from pants.util.dirutil import safe_mkdtemp
from pants_test.tasks.task_test_base import TaskTestBase


class JvmToolTaskTestBase(TaskTestBase):
  """Prepares an ephemeral test build root that supports tasks that use jvm tool bootstrapping."""

  @property
  def alias_groups(self):
    # Aliases appearing in our real BUILD.tools.
    return BuildFileAliases.create(
      targets={
        'jar_library': JarLibrary,
      },
      objects={
        'jar': JarDependency,
      },
    )

  def setUp(self):
    super(JvmToolTaskTestBase, self).setUp()

    # Use a synthetic subclass for bootstrapping within the test, to isolate this from
    # any bootstrapping the pants run executing the test might need.
    self.bootstrap_task_type, bootstrap_scope = self.synthesize_task_subtype(BootstrapJvmTools)
    JvmToolMixin.reset_registered_tools()

    # Cap BootstrapJvmTools memory usage in tests.  The Xmx was empirically arrived upon using
    # -Xloggc and verifying no full gcs for a test using the full gamut of resolving a multi-jar
    # tool, constructing a fat jar and then shading that fat jar.
    self.set_options_for_scope(bootstrap_scope, jvm_options=['-Xmx128m'])

    # Tool option defaults currently point to targets in the real BUILD.tools, so we copy it
    # into our test workspace.
    shutil.copy(os.path.join(self.real_build_root, 'BUILD.tools'), self.build_root)

    Bootstrapper.reset_instance()

  def context(self, for_task_types=None, options=None, target_roots=None,
              console_outstream=None, workspace=None):
    # Add in the bootstrapper task type, so its options get registered and set.
    for_task_types = [self.bootstrap_task_type] + (for_task_types or [])
    return super(JvmToolTaskTestBase, self).context(for_task_types=for_task_types,
                                                    options=options,
                                                    target_roots=target_roots,
                                                    console_outstream=console_outstream,
                                                    workspace=workspace)

  def prepare_execute(self, context, workdir):
    """Prepares a jvm tool using task for execution, ensuring any required jvm tools are
    bootstrapped.

    NB: Other task pre-requisites will not be ensured and tests must instead setup their own product
    requirements if any.

    :returns: The prepared Task
    """
    # TODO(John Sirois): This is emulating Engine behavior - construct reverse order, then execute;
    # instead it should probably just be using an Engine.
    task = self.create_task(context, workdir)
    task.invalidate()
    bootstrap_workdir = os.path.join(workdir, '_bootstrap_jvm_tools')
    self.bootstrap_task_type(context, bootstrap_workdir).execute()
    return task

  def execute(self, context):
    """Executes the given task ensuring any required jvm tools are bootstrapped.

    NB: Other task pre-requisites will not be ensured and tests must instead setup their own product
    requirements if any.

    :returns: The Task that was executed
    """
    # TODO(John Sirois): This is emulating Engine behavior - construct reverse order, then execute;
    # instead it should probably just be using an Engine.
    workdir = safe_mkdtemp(dir=self.build_root)
    task = self.prepare_execute(context, workdir)
    task.execute()
    return task
