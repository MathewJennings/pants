# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import sys

from org.pantsbuild.example.distance.ttypes import Distance


if __name__ == '__main__':
	d = Distance(Unit='ft',Number=5)
	print('Hello, world! {}'.format(d))
