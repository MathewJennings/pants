# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import json
import os
import shutil
import subprocess

from pex.interpreter import PythonInterpreter


def get_impl_abbreviation(version_string):
  if version_string[:2].lower() == 'ir':
    return 'ip' # IronPython
  elif version_string[:2].lower() == 'py':
    return 'pp' # PyPy
  else:
    return version_string[:2].lower() #'CPython' => 'cp', 'Jython' => 'jy'

def interp_satisfies_reqs(interp, bootstrap_data):
  if (
    '{}.{}'.format(interp.version[0], interp.version[1]) in bootstrap_data['supported_interp_versions']
    and get_impl_abbreviation(interp.version_string) in bootstrap_data['supported_interp_impls']
  ):
    return True
  else:
    return False

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

def search_for_valid_interp(interpreter_candidates):
  for interp in interpreter_candidates:
    if interp_satisfies_reqs(interp, bootstrap_data):
      return interp
  return None


vend_dir = os.path.dirname(__file__)

# Retrieve bootstrap data from the JSON file
with open(os.path.join(vend_dir, 'bootstrap_data.json'), 'r') as f:
  bootstrap_data = json.load(f)

# Find a valid interpreter
if not bootstrap_data['use_this_interpreter_option'] is None:
  try:
    interpreter = PythonInterpreter.find([bootstrap_data['use_this_interpreter_option']])[0]
  except IndexError:
    raise Exception('The desired interpreter passed in to the ./pants vend command '
                    'via the option --use-this-interpreter does not exist on this '
                    'target computer. Searched for an interpreter in {}'.format(
                      bootstrap_data['use_this_interpreter_option']
                    )
    )
  if not interp_satisfies_reqs(interpreter, bootstrap_data):
    raise Exception('The desired interpreter passed in to the ./pants vend command '
                    'via the option --use-this-interpreter does not satisfy python '
                    'version/implementation requirements imposed by this library of '
                    'code.')
else:
  search_paths = bootstrap_data['interpreter_search_paths']
  interpreter_candidates = PythonInterpreter.all(search_paths)
  chosen_interpreter = search_for_valid_interp(interpreter_candidates)
  while chosen_interpreter == None and search_paths:
    search_paths = get_children_paths(search_paths)
    interpreter_candidates = PythonInterpreter.all(search_paths)
    chosen_interpreter = search_for_valid_interp(interpreter_candidates)

  if chosen_interpreter is None:
    raise Exception('No valid interpreters exist in given search paths {} that '
      'satisfy python version/implementation requirements imposed by this library '
      'of code. Valid version(s) are {} and valid implementation(s) are {}'.format(
        bootstrap_data['interpreter_search_paths'],
        bootstrap_data['supported_interp_versions'],
        bootstrap_data['supported_interp_impls'],
      )
    )

# Create a virtual environment, and install all requirements into it
subprocess.call([
  chosen_interpreter.binary,
  os.path.join(vend_dir, 'virtualenv_source', 'virtualenv.py'),
  '--extra-search-dir',
  os.path.join(vend_dir, 'bootstrap_wheels'),
  os.path.join(vend_dir, 'venv')
])
subprocess.call([
  os.path.join(vend_dir, 'venv', 'bin', 'pip'),
  'install',
  '-r',
  os.path.join(vend_dir, 'requirements.txt'),
  '--no-index',
  '--find-links',
  os.path.join(vend_dir, 'dep_wheels'),
  '--find-links',
  os.path.join(vend_dir, 'bootstrap_wheels'),
])

# Add sources/ directory to venv's sys.path
with open(os.path.join(vend_dir, 'venv', 'lib', chosen_interpreter.binary.split('/')[-1], 'site-packages', 'sources.pth'), 'wb') as path_file:
  path_file.write(os.path.join(os.path.realpath(vend_dir), 'sources'))
