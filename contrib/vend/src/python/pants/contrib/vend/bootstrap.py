# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import json
import os
import re
import shutil
import subprocess
import sys
from textwrap import dedent

from pex.interpreter import PythonInterpreter


_osx_arch_pat = re.compile(r'(.+)_(\d+)_(\d+)_(.+)')

def _get_child_paths(search_paths, include_hidden_directories=False):
  all_child_paths = set()
  for parent_path in search_paths:
    curr_child_paths = set([
      os.path.join(parent_path, child_item) for child_item in os.listdir(parent_path)
      if os.path.isdir(os.path.join(parent_path, child_item)) and
         os.access(os.path.join(parent_path, child_item), os.R_OK)
    ])
    # Prune hidden directories.
    if not include_hidden_directories:
      curr_child_paths = set([
        child_path for child_path in curr_child_paths
        if not os.path.basename(os.path.normpath(child_path)).startswith('.')
      ])
    all_child_paths = all_child_paths.union(curr_child_paths)
  return all_child_paths

def _get_all_compatible_supported_platforms(supported_platform):
  """Platform-specific code cribbed from pip.pep425tags get_supported()"""
  if sys.platform == 'darwin':
    # Support macosx-10.6-intel on macosx-10.9-x86_64.
    match = _osx_arch_pat.match(supported_platform)
    if match:
      name, major, minor, actual_arch = match.groups()
      actual_arches = [actual_arch]
      if actual_arch in ('i386', 'ppc'):
        actual_arches.append('fat')
      if actual_arch in ('i386', 'x86_64'):
        actual_arches.append('intel')
      if actual_arch in ('i386', 'ppc', 'x86_64'):
        actual_arches.append('fat3')
      if actual_arch in ('ppc64', 'x86_64'):
        actual_arches.append('fat64')
      if actual_arch in ('i386', 'x86_64', 'intel', 'ppc', 'ppc64'):
        actual_arches.append('universal')
      tpl = '{0}_{1}_%i_%s'.format(name, major)
      all_compatible_platforms = []
      for m in range(int(minor) + 1):
        for a in actual_arches:
          all_compatible_platforms.append(tpl % (m, a))
    else:
      # Platform pattern didn't match(?).
      all_compatible_platforms = [supported_platform]
  else:
    all_compatible_platforms = [supported_platform]
  return all_compatible_platforms

def _attempt_to_create_venv(chosen_interpreter, supported_platforms, vend_dir):
  if chosen_interpreter == None:
    return False

  chosen_interpreter_plat, _ = subprocess.Popen(
    [
      chosen_interpreter.binary,
      '-c',
      'import distutils.util; print(distutils.util.get_platform())'
    ],
    stdout=subprocess.PIPE
  ).communicate()
  chosen_interpreter_all_compatible_plats = _get_all_compatible_supported_platforms(chosen_interpreter_plat.strip().replace('.', '_').replace('-', '_'))
  for compatible_plat in chosen_interpreter_all_compatible_plats:
    if compatible_plat in supported_platforms:
      # Create the virtual environment 'venv'.
      subprocess.check_call([
        chosen_interpreter.binary,
        os.path.join(vend_dir, 'virtualenv_source', 'virtualenv.py'),
        '--extra-search-dir',
        os.path.join(vend_dir, 'bootstrap_wheels'),
        os.path.join(vend_dir, 'venv')
      ])

      # Install all 3rd party requirements into 'venv'.
      subprocess.check_call([
        os.path.join(vend_dir, 'venv', 'bin', 'python'),
        '-m',
        'pip.__main__',
        'install',
        '-r',
        os.path.join(vend_dir, 'requirements.txt'),
        '--no-index',
        '--find-links',
        os.path.join(vend_dir, 'dep_wheels'),
        '--find-links',
        os.path.join(vend_dir, 'bootstrap_wheels'),
      ])
      return True
  return False


def _interpreter_satisfies_reqs(interpreter, bootstrap_data):

  def get_impl_abbreviation(version_string):
    if version_string[:2].lower() == 'ir':
      return 'ip' # This is IronPython.
    elif version_string[:2].lower() == 'py':
      return 'pp' # This is PyPy.
    else:
      return version_string[:2].lower() #'CPython' => 'cp' and 'Jython' => 'jy'.

  return (
    interpreter.python in bootstrap_data['supported_interpreter_versions']
    and get_impl_abbreviation(interpreter.version_string) in bootstrap_data['supported_interpreter_impls']
  )

def _only_valid_interpreters(interpreter_candidates, bootstrap_data):
  for interpreter in interpreter_candidates:
    if _interpreter_satisfies_reqs(interpreter, bootstrap_data):
      yield interpreter

def _search_for_interpreter(search_paths, bootstrap_data, vend_dir):
  chosen_interpreter = None
  interpreter_has_been_verified = False
  interpreter_candidates = list(_only_valid_interpreters(PythonInterpreter.find(search_paths), bootstrap_data))
  while interpreter_has_been_verified == False and not interpreter_candidates == []:
    chosen_interpreter = interpreter_candidates[0]
    print('Attempting to use the interpreter {} to bootstrap this Vend...'.format(chosen_interpreter.binary))
    interpreter_has_been_verified = _attempt_to_create_venv(chosen_interpreter, bootstrap_data['supported_platforms'], vend_dir)
    interpreter_candidates.remove(chosen_interpreter)
  return chosen_interpreter, interpreter_has_been_verified

def _validate_search_paths(search_paths):
  for path in search_paths:
    if os.path.exists(path):
      yield path

def bootstrap():
  # Retrieve bootstrap data from the JSON file.
  vend_dir = os.path.dirname(__file__)
  with open(os.path.join(vend_dir, 'bootstrap_data.json'), 'r') as f:
    bootstrap_data = json.load(f)

  # Initialize search paths, candidates, and chosen_interpreter.
  search_paths = list(_validate_search_paths(bootstrap_data['interpreter_search_paths']))
  interpreter_candidates = list(_only_valid_interpreters(PythonInterpreter.find(search_paths), bootstrap_data))
  chosen_interpreter, interpreter_has_been_verified = _search_for_interpreter(search_paths, bootstrap_data, vend_dir)

  while interpreter_has_been_verified == False and search_paths:
    # Probe only one level deeper at a time in the tree of currently examined directories.
    search_paths = _get_child_paths(search_paths)
    chosen_interpreter, interpreter_has_been_verified = _search_for_interpreter(search_paths, bootstrap_data, vend_dir)

  if interpreter_has_been_verified == False:
    shutil.rmtree(vend_dir)
    raise Exception(
      dedent(
        """No valid interpreters exist in given search paths "{}" that
        both satisfy python version/implementation requirements imposed by this
        library of code and that can install all of your 3rd party dependencies. Valid
        version(s) are "{}" and valid implementation(s) are "{}". Note that it is also
        possible that these paths contained at least one valid version/implementation
        of Python that satisfied these constraints, but was unable to install your 3rd
        party dependencies. This happens when there is a platform mismatch between what
        computer built your 3rd party wheels and the platform assumed by any valid
        interpreters in the specified search paths (e.g. you have macosx_X_Y_x86_64
        wheels, but the only valid interpreter found has platform macosx_X_Y_intel.)"""
      ).format(
        bootstrap_data['interpreter_search_paths'],
        bootstrap_data['supported_interpreter_versions'],
        bootstrap_data['supported_interpreter_impls'],
      )
    )
  else:
    # Add sources/ directory to venv's sys.path.
    with open(os.path.join(vend_dir, 'venv', 'lib', 'python{}'.format(chosen_interpreter.python), 'site-packages', 'sources.pth'), 'wb') as path_file:
      # Note that the Vend isn't currently in the cache, but in a uuid directory.
      # Therefore, remove the uuid from the path that is being written into the .pth file.
      final_vend_directory = os.path.join(os.path.dirname(os.path.dirname(vend_dir)), os.path.basename(vend_dir))
      path_file.write(os.path.join(os.path.realpath(final_vend_directory), 'sources'))

if __name__ == '__main__':
  bootstrap()
