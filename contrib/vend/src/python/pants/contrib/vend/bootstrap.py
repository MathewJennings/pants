# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import json
import os
import shutil
import subprocess
import sys

from pex.interpreter import PythonInterpreter


def get_children_paths(search_paths, include_hidden_directories=False):
  all_children_paths = set()
  for parent_path in search_paths:
    curr_children_paths = set([
      os.path.join(parent_path, child_item) for child_item in os.listdir(parent_path)
      if os.path.isdir(os.path.join(parent_path, child_item))
      and os.access(os.path.join(parent_path, child_item), os.R_OK)
    ])
    # Prune hidden directories
    if not include_hidden_directories:
      curr_children_paths = set([
      child_path for child_path in curr_children_paths
      if not os.path.basename(os.path.normpath(child_path)).startswith('.')
    ])
    all_children_paths = all_children_paths.union(curr_children_paths)
  return all_children_paths


def attempt_to_create_venv(chosen_interpreter, supported_platforms):
  if chosen_interpreter == None:
    return False

  chosen_interp_plat, _ = subprocess.Popen(
    [
      chosen_interpreter.binary,
      '-c',
      'import distutils.util; print(distutils.util.get_platform())'
    ],
    stdout=subprocess.PIPE
  ).communicate()

  if chosen_interp_plat.strip().replace('.', '_').replace('-', '_') in supported_platforms:
    # Create the virtual environment 'venv'
    subprocess.check_call([
      chosen_interpreter.binary,
      os.path.join(vend_dir, 'virtualenv_source', 'virtualenv.py'),
      '--extra-search-dir',
      os.path.join(vend_dir, 'bootstrap_wheels'),
      os.path.join(vend_dir, 'venv')
    ])

    # Install all 3rd party requirements into 'venv'
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
  else:
    return False


def interp_satisfies_reqs(interp):

  def get_impl_abbreviation(version_string):
    if version_string[:2].lower() == 'ir':
      return 'ip' # IronPython
    elif version_string[:2].lower() == 'py':
      return 'pp' # PyPy
    else:
      return version_string[:2].lower() #'CPython' => 'cp', 'Jython' => 'jy'

  return (
    interp.python in bootstrap_data['supported_interp_versions']
    and get_impl_abbreviation(interp.version_string) in bootstrap_data['supported_interp_impls']
  )

def only_valid_interpreters(interpreter_candidates):
  for interpreter in interpreter_candidates:
    if interp_satisfies_reqs(interpreter):
      yield interpreter

def search_for_interpreter(search_paths, supported_platforms):
  chosen_interpreter = None
  interpreter_has_been_verified = False
  interpreter_candidates = list(only_valid_interpreters(PythonInterpreter.find(search_paths)))
  while interpreter_has_been_verified == False and not interpreter_candidates == []:
    chosen_interpreter = interpreter_candidates[0]
    print('Attempting to use the interpreter {} to bootstrap this Vend...'.format(chosen_interpreter.binary))
    interpreter_has_been_verified = attempt_to_create_venv(chosen_interpreter, supported_platforms)
    interpreter_candidates.remove(chosen_interpreter)
  return chosen_interpreter, interpreter_has_been_verified

def validate_search_paths(search_paths):
  for path in search_paths:
    if os.path.exists(path):
      yield path


# Retrieve bootstrap data from the JSON file
vend_dir = os.path.dirname(__file__)
with open(os.path.join(vend_dir, 'bootstrap_data.json'), 'r') as f:
  bootstrap_data = json.load(f)

# Initialize search paths, candidates, and chosen_interpreter
search_paths = list(validate_search_paths(bootstrap_data['interpreter_search_paths']))
interpreter_candidates = list(only_valid_interpreters(PythonInterpreter.find(search_paths)))
chosen_interpreter, interpreter_has_been_verified = search_for_interpreter(search_paths, bootstrap_data['supported_platforms'])

while interpreter_has_been_verified == False and search_paths:
  # Probe only one level deeper at a time in the tree of currently examined directories
  search_paths = get_children_paths(search_paths)
  chosen_interpreter, interpreter_has_been_verified = search_for_interpreter(search_paths, bootstrap_data['supported_platforms'])

if interpreter_has_been_verified == False:
  shutil.rmtree(vend_dir)
  raise Exception('No valid interpreters exist in given search paths "{}" that '
    'both satisfy python version/implementation requirements imposed by this '
    'library of code and that can install all of your 3rd party dependencies. Valid '
    'version(s) are "{}" and valid implementation(s) are "{}". Note that it is also '
    'possible that these paths contained at least one valid version/implementation '
    'of Python that satisfied these constraints, but was unable to install your 3rd '
    'party dependencies. This happens when there is a platform mismatch between what '
    'computer built your 3rd party wheels and the platform assumed by any valid '
    'interpreters in the specified search paths (e.g. you have macosx_X_Y_x86_64 '
    'wheels, but the only valid interpreter found has platform macosx_X_Y_intel.)'
    .format(
      bootstrap_data['interpreter_search_paths'],
      bootstrap_data['supported_interp_versions'],
      bootstrap_data['supported_interp_impls'],
    )
  )
else:
  # Add sources/ directory to venv's sys.path
  with open(os.path.join(vend_dir, 'venv', 'lib', 'python{}'.format(chosen_interpreter.python), 'site-packages', 'sources.pth'), 'wb') as path_file:
    # Note that the Vend isn't currently in the cache, but in a uuid directory
    # So remove the uuid from the path that is being written into the .pth file
    final_vend_directory = os.path.join(os.path.dirname(os.path.dirname(vend_dir)), os.path.basename(vend_dir))
    path_file.write(os.path.join(os.path.realpath(final_vend_directory), 'sources'))
