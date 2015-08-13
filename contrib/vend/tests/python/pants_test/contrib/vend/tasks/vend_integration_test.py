# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import zipfile

from pants_test.pants_run_integration_test import PantsRunIntegrationTest


class VendIntegrationTest(PantsRunIntegrationTest):
  """Integration test for vend which builds Vends of python_binary source projects."""

  def test_with_thrift(self):
    test_args = [
      'vend',
      'contrib/vend/examples/src/python/test1/test1'
    ]
    pants_run = self.run_pants(test_args)
    self.assert_success(pants_run)
    vend_zip = zipfile.ZipFile(os.path.join('dist', 'test1.vend'), 'r')
    vend_contents = vend_zip.namelist()
    vend_zip.close()
    vend_name_and_fingerprint = os.path.dirname(vend_contents[1])
    thrift_genned_py_lib = os.path.join(
      vend_name_and_fingerprint, 'sources', 'org',
      'pantsbuild', 'example', 'distance', 'ttypes.py'
    ) in vend_contents
    self.assertTrue(thrift_genned_py_lib)
