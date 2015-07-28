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
import zipfile


# Take a look inside of this Vend:
vend_dir = os.path.dirname(__file__)
vend_zip = zipfile.ZipFile(vend_dir, 'r')

# Find json bootstrapping data and read cache directory from it
vend_name_and_fingerprint, _ = os.path.split(vend_zip.namelist()[1])
bootstrap_data = json.load(vend_zip.open(os.path.join(vend_name_and_fingerprint, 'bootstrap_data.json')))
vend_cache_dir = os.path.expanduser(bootstrap_data['vend_cache_dir'])
this_vend_cache_path = os.path.join(vend_cache_dir, vend_name_and_fingerprint)

# Check if the cache exists
if not os.path.exists(vend_cache_dir):
  bootstrapped = False
  os.makedirs(vend_cache_dir)
else:
  # Check if the Vend is in the cache
  if os.path.exists(this_vend_cache_path):
    bootstrapped = True
  else:
    # Cache exists at this directory, but this Vend hasn't been bootstrapped and cached there yet
    bootstrapped = False

if bootstrapped:
  vend_zip.close()
else:
  print('\nBootstrapping and caching this Vend...\n')

  # Initialze the cached Vend
  vend_zip.extractall(path=vend_cache_dir)
  # We don't want extra copies of this script floating around in the cache
  os.remove(os.path.join(vend_cache_dir, '__main__.py'))
  # Determine the name of the virtualenv wheel we're using (info we'll need during bootstrapping)
  for name in vend_zip.namelist():
    if 'virtualenv' in name:
      venv_wheel = name
      break
  vend_zip.close()

  # Extract the virtualenv wheel
  venv_wheel = os.path.join(vend_cache_dir, venv_wheel)
  venv_wheel_zf = zipfile.ZipFile(venv_wheel, 'r')
  venv_wheel_zf.extractall(path=os.path.join(this_vend_cache_path, 'virtualenv_source'))
  venv_wheel_zf.close()

  # Build the vendboot virtualenv
  subprocess.check_call(
    [
      'python',
       os.path.join(this_vend_cache_path, 'virtualenv_source', 'virtualenv.py'),
      '--extra-search-dir',
      os.path.join(this_vend_cache_path, 'bootstrap_wheels'),
      os.path.join(this_vend_cache_path, 'vendboot'),
    ],
    stderr=subprocess.STDOUT
  )

  # Install pex into vendboot
  subprocess.check_call(
    [
      os.path.join(this_vend_cache_path, 'vendboot', 'bin', 'python'),
      '-m',
      'pip',
      'install',
      '--no-index',
      '--find-links',
      os.path.join(this_vend_cache_path, 'bootstrap_wheels'),
      'pex',
    ],
    stderr=subprocess.STDOUT
  )

  # Execute bootstrap.py from inside of vendboot
  subprocess.check_call(
    [
      os.path.join(this_vend_cache_path, 'vendboot', 'bin', 'python'),
      os.path.join(this_vend_cache_path, 'bootstrap.py'),
    ],
    stderr=subprocess.STDOUT
  )

  # Ensure we have the proper permissions to execute the project
  os.chmod(os.path.join(this_vend_cache_path, 'run.sh'), 0755)
  os.chmod(os.path.join(this_vend_cache_path, 'venv', 'bin', 'python'), 0755)

  # Clean up the cached Vend
  shutil.rmtree(os.path.join(this_vend_cache_path, 'bootstrap_wheels'))
  if os.path.isdir(os.path.join(this_vend_cache_path, 'dep_wheels')):
    shutil.rmtree(os.path.join(this_vend_cache_path, 'dep_wheels'))
  os.remove(os.path.join(this_vend_cache_path, 'bootstrap.py'))
  os.remove(os.path.join(this_vend_cache_path, 'bootstrap_data.json'))
  os.remove(os.path.join(this_vend_cache_path, 'requirements.txt'))
  shutil.rmtree(os.path.join(this_vend_cache_path, 'virtualenv_source'))
  shutil.rmtree(os.path.join(this_vend_cache_path, 'vendboot'))


# Run the entrypoint for the project
run_args = [os.path.join(this_vend_cache_path, 'run.sh')]
for arg_val in sys.argv[1:]:
  run_args.append(arg_val)
subprocess.check_call(run_args, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)
