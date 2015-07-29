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
from uuid import uuid4


def bootstrap_vend(vend_cache_dir, vend_name_and_fingerprint, vend_zip):
  print('\nBootstrapping and caching this Vend...\n')
  # Initialze the cached Vend
  vend_work_dir = os.path.join(vend_cache_dir, str(uuid4()))
  vend_zip.extractall(path=vend_work_dir)
  this_vend_cache_path = os.path.join(vend_work_dir, vend_name_and_fingerprint)
  # Delete the zip file's __main__.py, it's not relevant to the cache
  os.remove(os.path.join(vend_work_dir, '__main__.py'))

  # Retrieve the bootstrap_data to determine the filename of the virtualenv bootstrap wheel
  with open(os.path.join(this_vend_cache_path, 'bootstrap_data.json'), 'r') as f:
    bootstrap_data = json.load(f)
  vend_zip.close()

  # Extract the virtualenv wheel
  venv_wheel = os.path.join(this_vend_cache_path, 'bootstrap_wheels', bootstrap_data['virtualenv_wheel'])
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
    ]
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
  )

  # Execute bootstrap.py from inside of vendboot
  subprocess.check_call(
    [
      os.path.join(this_vend_cache_path, 'vendboot', 'bin', 'python'),
      os.path.join(this_vend_cache_path, 'bootstrap.py'),
    ],
  )

  # Ensure we have the proper permissions to execute the project
  os.chmod(os.path.join(this_vend_cache_path, 'run.sh'), 0755)

  # Clean up the cached Vend
  shutil.rmtree(os.path.join(this_vend_cache_path, 'bootstrap_wheels'))
  if os.path.isdir(os.path.join(this_vend_cache_path, 'dep_wheels')):
    shutil.rmtree(os.path.join(this_vend_cache_path, 'dep_wheels'))
  os.remove(os.path.join(this_vend_cache_path, 'bootstrap.py'))
  os.remove(os.path.join(this_vend_cache_path, 'bootstrap_data.json'))
  os.remove(os.path.join(this_vend_cache_path, 'requirements.txt'))
  shutil.rmtree(os.path.join(this_vend_cache_path, 'virtualenv_source'))
  shutil.rmtree(os.path.join(this_vend_cache_path, 'vendboot'))

  # Atomically move the bootstrapped Vend to the real cache directory
  os.rename(
    os.path.join(vend_work_dir, vend_name_and_fingerprint),
    os.path.join(vend_cache_dir, vend_name_and_fingerprint)
  )
  os.rmdir(vend_work_dir)

def execute_vend():
  # Take a look inside of this Vend:
  vend_dir = os.path.dirname(__file__)
  vend_zip = zipfile.ZipFile(vend_dir, 'r')

  # Determine where we are caching Vends on the target computer
  if 'VENDCACHE' in os.environ:
    vend_cache_dir = os.environ['VENDCACHE']
  else:
    vend_name_and_fingerprint = os.path.dirname(vend_zip.namelist()[1])
    bootstrap_data = json.load(vend_zip.open(os.path.join(vend_name_and_fingerprint, 'bootstrap_data.json')))
    vend_cache_dir = os.path.expanduser(bootstrap_data['vend_cache_dir'])
  this_vend_cache_path = os.path.join(vend_cache_dir, vend_name_and_fingerprint)

  # Ensure the cache exists
  try:
    os.makedirs(vend_cache_dir)
  except OSError:
    pass

  # Check if the Vend is in the cache
  bootstrapped = os.path.exists(this_vend_cache_path)

  if bootstrapped:
    vend_zip.close()
  else:
    bootstrap_vend(vend_cache_dir, vend_name_and_fingerprint, vend_zip)

  # Run the entrypoint for the project
  run_args = [os.path.join(this_vend_cache_path, 'run.sh')]
  for arg_val in sys.argv[1:]:
    run_args.append(arg_val)
  subprocess.check_call(run_args, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)

if __name__ == '__main__':
  execute_vend()
