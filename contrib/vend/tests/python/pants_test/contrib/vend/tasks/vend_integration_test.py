# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import shutil
import subprocess

import pytest
from pants_test.pants_run_integration_test import PantsRunIntegrationTest

from pants.contrib.vend.tasks.vend import Vend


class VendIntegrationTest(PantsRunIntegrationTest):
  """Integration test for vend which builds Vends of python_binary source projects."""

  def test_with_thrift(self):
    args = [
      'vend',
      'contrib/vend/examples/src/python/test1/test1',
    ]
    pants_run = self.run_pants(args)
    unzip_dir = os.path.join('dist', 'myvend')
    if os.path.exists(unzip_dir):
      shutil.rmtree(unzip_dir)
    subprocess.check_call(
      ['unzip', os.path.join('dist', 'test1.vend'), '-d', unzip_dir],
      stderr=subprocess.STDOUT
    )
    self.assert_success(pants_run)
    fingerprint_dir_name = os.listdir(os.path.join('dist', 'myvend'))[1]
    thrift_genned_py_lib = os.path.isfile(
      os.path.join('dist', 'myvend', fingerprint_dir_name, 'sources', 'org',
        'pantsbuild', 'example', 'distance', 'ttypes.py')
    )
    self.assertTrue(thrift_genned_py_lib)
    shutil.rmtree('dist/myvend')
    os.remove(os.path.join('dist', 'test1.vend'))
