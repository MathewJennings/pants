# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import sys

from org.pantsbuild.example.distance.ttypes import Distance


if __name__ == '__main__':
  d = Distance(Unit='ft',Number=5)
  greetees = sys.argv[1:] or ['world']
  for greetee in greetees:
    print('Hello, {}!'.format(greetee))
  print('Here is a Thrift object: {}'.format(d))
