# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import json
import logging
import os
import re
import shutil
import sys
import zipfile
from textwrap import dedent

from pants.backend.core.targets.resources import Resources
from pants.backend.python.targets.python_binary import PythonBinary
from pants.backend.python.targets.python_library import PythonLibrary
from pants.backend.python.targets.python_requirement_library import PythonRequirementLibrary
from pants.backend.python.tasks.python_task import PythonTask
from pants.base.build_environment import get_buildroot
from pants.base.cache_manager import VersionedTargetSet
from pip.commands.install import InstallCommand
from pip.pep425tags import get_platform
from pip.status_codes import SUCCESS
from pip.wheel import Wheel


class Vend(PythonTask):
  def __init__(self, context, workdir):
    super(Vend, self).__init__(context, workdir)

  @classmethod
  def product_types(cls):
    return ['vend']

  @classmethod
  def prepare(cls, options, round_manager):
    super(Vend, cls).prepare(options, round_manager)
    round_manager.require_data('python')

  @classmethod
  def register_options(cls, register):
    super(Vend, cls).register_options(register)
    register(
      '--wheelhouses',
      advanced=True,
      action='append',
      default=None,
      help='Specify the locations at which pip will point its --find-links and searches for wheels'
    )
    register(
      '--interpreter-search-paths',
      advanced=True,
      action='append',
      default=None,
      help='Add a location in which to search for a base python interpreter to '
            'use to run the PythonBinary on the deployment target. Default locations '
            'are added to pants.ini'
    )
    register(
      '--all-py-versions',
      advanced=True,
      action='append',
      default=None,
      help='A list of all python versions of the form "X.Y". This is used to '
            'determine the intersection of valid interpreters for the PythonLibrary '
            'targets that make up the source code of the PythonBinary input for '
            'this command. This list is specified in pants.ini, and any changes '
            'should be made there.'
    )
    register(
      '--bootstrap-requirements',
      advanced=True,
      action='append',
      default=None,
      help='A list of all python packages necessary for different steps in the '
            'Vend preparation process. This list is specified in pants.ini, and '
            'any desired changes to the required version numbers should be made '
            'there.'
    )
    register(
      '--set-vend-cache',
      default=None,
      help='Specify the location at which to cache the virtualenv that this Vend '
            'executes out of on target computers. The environment variable '
            'VENDCACHE takes precedence over this option. If neither that or this '
            'option are specified, then the default directory to cache Vends is '
            'chosen, which is "Path/to/homedirectory/.vendcache".'
    )

  def determine_supported_interpreters_intersection(self, all_source_libs):

    def resolve_implementation_constraint(curr_impls, new_implementation):
      if new_implementation == '':
        return curr_impls
      elif new_implementation.lower() == 'ironpython':
        new_implementation = 'ip'
      elif new_implementation.lower() == 'pypy':
        new_implementation = 'pp'
      else:
        #'CPython' => 'cp', 'Jython' => 'jy', 'Python' => 'py'
        new_implementation = new_implementation[:2].lower()

      if new_implementation == 'py': # Generic Python
        return curr_impls
      elif new_implementation in curr_impls: # Can support only the new implementation
        return set([new_implementation])
      else:
        raise Exception('A single PythonLibrary source target requires conflicting '
          'implementations of Python. It declares that it only runs on an '
          'implementation with the PEP425 Python Tag "{}" and also that it only '
          'runs on an implementation with the PEP425 Python Tag "{}"'
          .format(curr_impls, new_implementation)
        )

    def parse_python_version(version_string):
      # Important: Choosing to only examine major and minor version numbers;
      # if micro version numbers are present, they will be ignored
      if version_string.count('.') == 0:
        major = version_string
        minor = 0
      elif version_string.count('.') == 1:
        major, minor = version_string.split('.')
      else:
        major, minor = version_string.split('.')[:2]
      return (int(major), int(minor))

    def handle_single_constraint(constraint, supported_vers, supported_impls):
      if '<=' in constraint:
        constraint_version_index = constraint.find('<=') + 2
        constraint_version = constraint[constraint_version_index:]
        constraint_implementation = constraint[:constraint_version_index - 2]
        supported_vers = [
          v for v in supported_vers if (
            (lambda x:
              parse_python_version(x) <= parse_python_version(constraint_version)
            )(v)
          )
        ]
      elif '<' in constraint:
        constraint_version_index = constraint.find('<') + 1
        constraint_version = constraint[constraint_version_index:]
        constraint_implementation = constraint[:constraint_version_index - 1]
        supported_vers = [
          v for v in supported_vers if (
            (lambda x:
              parse_python_version(x) < parse_python_version(constraint_version)
            )(v)
          )
        ]
      elif '==' in constraint:
        constraint_version_index = constraint.find('==') + 2
        constraint_version = constraint[constraint_version_index:]
        constraint_implementation = constraint[:constraint_version_index - 2]
        supported_vers = [
          v for v in supported_vers if (
            (lambda x:
              parse_python_version(x) == parse_python_version(constraint_version)
            )(v)
          )
        ]
      elif '!=' in constraint:
        constraint_version_index = constraint.find('!=') + 2
        constraint_version = constraint[constraint_version_index:]
        constraint_implementation = constraint[:constraint_version_index - 2]
        supported_vers = [
          v for v in supported_vers if (
            (lambda x:
              parse_python_version(x) != parse_python_version(constraint_version)
            )(v)
          )
        ]
      elif '>=' in constraint:
        constraint_version_index = constraint.find('>=') + 2
        constraint_version = constraint[constraint_version_index:]
        constraint_implementation = constraint[:constraint_version_index - 2]
        supported_vers = [
          v for v in supported_vers if (
            (lambda x:
              parse_python_version(x) >= parse_python_version(constraint_version)
            )(v)
          )
        ]
      elif '>' in constraint:
        constraint_version_index = constraint.find('>') + 1
        constraint_version = constraint[constraint_version_index:]
        constraint_implementation = constraint[:constraint_version_index - 1]
        supported_vers = [
          v for v in supported_vers if (
            (lambda x:
              parse_python_version(x) > parse_python_version(constraint_version)
            )(v)
          )
        ]
      elif '~=' in constraint:
        # As enforced by PEP440, cannot use this "compatible release"
        # clause with a single segment version number such as ~=2
        constraint_version_index = constraint.find('~=') + 2
        constraint_version = constraint[constraint_version_index:]
        constraint_implementation = constraint[:constraint_version_index - 2]
        supported_vers = [
          v for v in supported_vers if (
            (lambda x:
              parse_python_version(x) >= parse_python_version(constraint_version[:-2])
            )(v)
          )
        ]
      else:
        raise Exception('The constraint "{}" does not have a valid form. The '
          'logical comparison must be one of the following: <=, <, ==, !=, >=, '
          '>, ~=.'.format(constraint)
        )
      supported_impls = resolve_implementation_constraint(supported_impls, constraint_implementation)
      return supported_vers, supported_impls

    # Initialize return values
    final_interp_version_intersection = set(self.get_options().all_py_versions[:])
    final_interp_impl_intersection = set(['py','cp','ip','pp','jy'])

    # Take the intersection of interpreter constraints imposed by each PythonLibrary
    # and the PythonBinary
    for lib in all_source_libs:
      # Examine reqs: a list of strings representing a logical OR of interpreter
      # constraints
      reqs = lib.compatibility
      if reqs:
        # Enforce that reqs is a list of strings
        if type(reqs) != list:
          reqs = [reqs]
        # Initialize values for this library
        valid_interp_versions_for_this_lib = set()
        valid_interp_implementations_for_this_lib = set()

        for req in reqs:
          # Initialize values for this requirement
          valid_interp_versions_for_this_req = self.get_options().all_py_versions[:]
          valid_interp_implementations_for_this_req = set(['py','cp','ip','pp','jy'])

          # Resolve version constraint(s) imposed by this req. Lists of valid
          # versions across different reqs will be logical ORed together to
          # form the full list of valid interpreter versions for a single lib.
          if ',' in req:
            # Take the logical AND (set intersection) of all individual version
            # constraints listed in a single requirement string
            # e.g. '>=2.7,<3' becomes >=2.7 AND <3
            constraints = req.split(',')
            for constraint in constraints:
              (valid_interp_versions_for_this_req,
              valid_interp_implementations_for_this_req) = handle_single_constraint(
                constraint,
                valid_interp_versions_for_this_req,
                valid_interp_implementations_for_this_req
              )
          else:
              (valid_interp_versions_for_this_req,
              valid_interp_implementations_for_this_req) = handle_single_constraint(
                req,
                valid_interp_versions_for_this_req,
                valid_interp_implementations_for_this_req
              )

          # Add valid interpreter implementations for this req to full list of
          # valid interpreter implementations for the whole library (updating
          # the logical OR of reqs for this PythonLibrary)
          for valid_interp_impl in valid_interp_implementations_for_this_req:
            valid_interp_implementations_for_this_lib.add(valid_interp_impl)

          # Do the same for interpreter versions
          for valid_interp_version in valid_interp_versions_for_this_req:
            valid_interp_versions_for_this_lib.add(valid_interp_version)

        # Update the intersection of requirements between PythonLibrary targets
        final_interp_version_intersection = final_interp_version_intersection.intersection(valid_interp_versions_for_this_lib)
        final_interp_impl_intersection = final_interp_impl_intersection.intersection(valid_interp_implementations_for_this_lib)

    return (list(final_interp_version_intersection), list(final_interp_impl_intersection))


  def execute(self):
    # Grab and validate the PythonBinary input target
    if len(self.context.target_roots) != 1:
      raise Exception('Invalid target roots: must pass a single target.')
    python_binary = self.context.target_roots[0]
    if not isinstance(python_binary, PythonBinary):
      raise Exception('Invalid target roots: must pass a single python_binary target.')

    # Identify PythonLibraries, PythonRequirementLibraries, and Resources
    py_libs = set(self.context.targets(lambda t: isinstance(t, PythonLibrary)))
    py_req_libs = set(self.context.targets(
      lambda t: isinstance(t, PythonRequirementLibrary))
    )
   resource_libs = set(self.context.targets(lambda t: isinstance(t, Resources)))
    all_source_libs = py_libs | set([python_binary])
    all_source_items = all_source_libs | resource_libs
    sorted_py_reqs = sorted([
      str(py_req._requirement)
      for py_req_lib in py_req_libs
      for py_req in py_req_lib.payload.requirements
    ])
    bootstrap_py_reqs = self.get_options().bootstrap_requirements

    # Find the exact intersection of Python interpreter constraints imposed by the
    # PythonBinary and PythonLibrary targets. ( [list_supported_minor_versions],
    # [list_supported_pep425_python_implementation_tags] )
    intersection_supported_interp = self.determine_supported_interpreters_intersection(all_source_libs)
    supported_interp_versions, supported_interp_impls = intersection_supported_interp

    # Assert that at least one Python interpreter satisfies the intersection of constraints
    if supported_interp_versions == [] or supported_interp_impls == []:
      raise Exception('No Python interpreter can satisfy the intersection of '
                      'the constraints imposed by the PythonLibrary targets. '
                      'Check the "compatibility" field of the PythonBinary and '
                      'all of its PythonLibrary sources.'
      )

    # Generate the fingerprint for this vend using all relevant targets in the graph
    with self.invalidated(self.context.targets()) as invalidation_check:
      global_vts = VersionedTargetSet.from_versioned_targets(invalidation_check.all_vts)

    # Setup vend directory structure
    vend_name = '{}.vend'.format(python_binary.name)
    vend_archive_dir = os.path.join('dist', python_binary.name + '_' + global_vts.cache_key.hash)
    vend_workdir = os.path.join(vend_archive_dir, vend_name)
    if os.path.exists(vend_workdir):
      shutil.rmtree(vend_workdir)
    source_dir = os.path.join(vend_workdir, 'sources')
    requirements_path = os.path.join(vend_workdir, 'requirements.txt')
    logging_path = os.path.join(vend_workdir, 'piplog.log')
    dependency_wheels_dir = os.path.join(vend_workdir, 'dep_wheels')
    bootstrap_wheels_dir = os.path.join(vend_workdir, 'bootstrap_wheels')
    bootstrap_data_path = os.path.join(vend_workdir, 'bootstrap_data.json')
    main_path = os.path.join(vend_workdir, '__main__.py')
    bootstrap_path = os.path.join(vend_workdir, 'bootstrap.py')
    run_path = os.path.join(vend_workdir, 'run.sh')

    # Copy source files into the vend's source directory
    for target in all_source_items:
      for source_path in target.sources_relative_to_buildroot():
        sourceroot_relative_source_path = os.path.relpath(source_path, target.target_base)
        # Fix source_path to include the buildroot
        source_path = os.path.join(get_buildroot(), source_path)
        dest_path = os.path.join(source_dir, sourceroot_relative_source_path)
        if not os.path.exists(os.path.dirname(dest_path)):
          os.makedirs(os.path.dirname(dest_path))
        shutil.copyfile(source_path, dest_path)
        # Ensure __init__.py files in the source tree
        current_dir = os.path.dirname(sourceroot_relative_source_path)
        while current_dir:
          init_py = os.path.join(source_dir, current_dir, '__init__.py')
          if not os.path.exists(init_py):
            with open(init_py, 'wb'):
              pass
          current_dir = os.path.dirname(current_dir)

    # Establish vend's requirements.txt and fill it with dependency_reqs
    with open(requirements_path, 'wb') as f:
      for req in sorted_py_reqs:
        f.write('{}\n'.format(str(req)))

    # Ensure vend's dependency_wheels_dir
    if not os.path.exists(dependency_wheels_dir):
      os.makedirs(dependency_wheels_dir)
    # Gather vend's target platforms
    desired_platforms = set(python_binary.platforms)
    if desired_platforms == set():
      # If none are specified, assume the current platform
      desired_platforms = set([get_platform()])
    elif 'current' in desired_platforms:
      desired_platforms.remove('current')
      desired_platforms.add(get_platform())

    # Let error_combinations be a list of tuples (dependency, interpreter,
    # platform) that each describe a combination for which a wheel could not be
    # downloaded.
    error_combinations = []

    # Establish logging for capturing critical pip failures
    logger = logging.getLogger('pip')
    fh = logging.FileHandler(logging_path)
    fh.setLevel(logging.CRITICAL)
    logger.addHandler(fh)

    # Prepare base arugments to the 'pip install --download' command
    download_args= [
      '--quiet',
      '--download',
      dependency_wheels_dir,
      '-r',
      requirements_path,
      '--no-index'
    ]
    download_args.extend(
      '--find-links={}'.format(wheelhouse)
      for wheelhouse in self.get_options().wheelhouses
    )
    download_args.append('--platform')
    for platform in desired_platforms:
      download_args.append(platform)
      download_args.append('--supported-interpreter-version')
      for supported_interp_version in supported_interp_versions:
        interp_string = supported_interp_version[0] + supported_interp_version[2]
        download_args.append(interp_string)
        # Download dependency wheels and all of their transitive dependencies
        wheel_downloader = InstallCommand()
        output = wheel_downloader.main(download_args)
        # Collect the combinations that resulted in error
        if not output == SUCCESS:
          with open(logging_path) as f:
            # Record the bottom line, which will always have the latest log
            dependency = re.search('for ([\w\d\.=<>!~]+)', f.readlines()[-1]).group(1)
          error_combinations.append((dependency, supported_interp_version, platform))
        download_args = download_args[:-1]
      download_args = download_args[:-2]

    # Check for combination of dependency, platform, and interpreter that could not be downloaded
    if error_combinations:
      error_string = (
        '\nCould not resolve all 3rd party dependencies. Each of the combinations '
        'of dependency, platform, and interpreter-version listed below could not be '
        'downloaded. To support these dependencies, you must either restrict your '
        'desired Python versions by adjusting the compatibility field of the '
        'PythonBinary, or drop support for the platforms that cannot be resolved:'
      )
      for error_combination in error_combinations:
        error_string += ('\nFailed to resolve dependency "{}" for Python {} on '
          'platform {}.'.format(
            error_combination[0],
            error_combination[1],
            error_combination[2],
          )
        )
      error_string += ('\nSee detailed error messages logged by pip in {}'.format(
          os.path.join(get_buildroot(), logging_path)
        )
      )
      shutil.rmtree(vend_archive_dir)
      raise Exception(error_string)

    # Delete piplog.log: we don't need it anymore
    os.remove(logging_path)

    # Check that all downloaded wheels are compatible with the supported python implementations
    for whl_file in os.listdir(dependency_wheels_dir):
      wheel = Wheel(whl_file)
      wheel_is_compatible = False
      # We only need one of the wheel's compatible pyversions to be compatible
      for pyversion in wheel.pyversions:
        impl = pyversion[:2]
        if impl == 'py' or impl in supported_interp_impls:
          wheel_is_compatible = True
          break
      if not wheel_is_compatible:
        shutil.rmtree(vend_archive_dir)
        raise Exception('Attempted to download wheel dependency "{}" but it is '
          'not compatible with the python implementation constraints imposed by '
          'the PythonLibrary targets. It runs on Python versions with these '
          'PEP425 Python Tags: {}, but the valid interpreter implementations are '
          '{}'.format(
            wheel.name,
            wheel.pyversions,
            supported_interp_impls
          )
        )

    # Ensure vend's bootstrap_wheels_dir and download bootstrap wheels
    if not os.path.exists(bootstrap_wheels_dir):
      os.makedirs(bootstrap_wheels_dir)
    download_args = ['--quiet', '--download', bootstrap_wheels_dir]
    for bootstrap_req in bootstrap_py_reqs:
      download_args.append(bootstrap_req)
      wheel_downloader = InstallCommand()
      wheel_downloader.main(download_args)
      download_args = download_args[:-1]

    # Determine where to cache this Vend on the target computer
    if 'VENDCACHE' in os.environ:
      vend_cache_dir = os.environ['VENDCACHE']
    elif self.get_options().set_vend_cache:
      vend_cache_dir = self.get_options().set_vend_cache
    else: # Use the default directory
      vend_cache_dir = '~/.vendcache'

    # Write the bootstrap data JSON for the __main__.py and bootstrap.py scripts
    bootstrap_data = {
      'vend_cache_dir' : vend_cache_dir,
      'interpreter_search_paths' : self.get_options().interpreter_search_paths,
      'supported_interp_versions' : supported_interp_versions,
      'supported_interp_impls' : supported_interp_impls,
    }
    with open(bootstrap_data_path, 'w') as f:
     json.dump(bootstrap_data, f)

    # Add the main script (for executing the zip) to the vend
    shutil.copyfile(
      'contrib/vend/src/python/pants/contrib/vend/__main__.py',
      main_path,
    )

    # Add the bootstrap script to the vend
    shutil.copyfile(
      'contrib/vend/src/python/pants/contrib/vend/bootstrap.py',
      bootstrap_path,
    )

    # Codegen the entrypoint for the vend
    run_script = dedent(
      """
      #!/bin/bash
      set -eo pipefail
      exec $(dirname $BASH_SOURCE)/venv/bin/python -m {} "$@"
      """.format(python_binary.entry_point)
    ).strip()
    with open(run_path, 'wb') as f:
      f.write(run_script)

    # Create the .vend zip file
    vend_zip = os.path.join('dist', vend_name)
    if os.path.isfile(vend_zip):
      os.remove(vend_zip)
    # Write the shebang for executing the vend directly
    with open(vend_zip, 'ab') as vend_zipfile:
      vend_zipfile.write('#!/usr/bin/env python\n'.encode('utf-8'))
    # Write the contents of the Vend source directory
    vend_zipfile = zipfile.ZipFile(vend_zip, 'a')
    for root, dirs, files in os.walk(vend_workdir):
      for src_file in files:
          if src_file == '__main__.py':
            write_path = os.path.relpath(os.path.join(root, src_file), vend_workdir)
          else:
            write_path = os.path.join(os.path.basename(vend_archive_dir), os.path.relpath(os.path.join(root, src_file), vend_workdir))
          vend_zipfile.write(os.path.join(root, src_file), arcname=write_path)
    vend_zipfile.close()
    os.chmod(vend_zip, 0755)

    # Delete the archive dir
    shutil.rmtree(vend_archive_dir)

    # Tell the user where their Vend is
    print('\nVEND source package created at {}'.format(vend_zip), file=sys.stderr)
