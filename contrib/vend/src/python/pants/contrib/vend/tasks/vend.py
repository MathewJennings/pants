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
from pants.util.dirutil import safe_delete, safe_mkdir
from pip.commands.install import InstallCommand
from pip.pep425tags import get_platform
from pip.status_codes import SUCCESS
from pip.wheel import Wheel


class Vend(PythonTask):
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
    register('--wheelhouses', advanced=True, action='append', default=None,
             help='Specify the locations at which pip will point its --find-links and searches for wheels')
    register('--interpreter-search-paths', advanced=True, action='append', default=None,
             help=dedent(
             """Add a location in which to search for a base python interpreter to
             use to run the PythonBinary on the deployment target. Default locations
             are added to pants.ini"""))
    register('--all-py-versions', advanced=True, action='append', default=None,
             help=dedent(
             """A list of all python versions of the form "X.Y". This is used to
             determine the intersection of valid interpreters for the PythonLibrary
             targets that make up the source code of the PythonBinary input for
             this command. This list is specified in pants.ini, and any changes
             should be made there."""))
    register('--bootstrap-requirements', advanced=True, action='append', default=None,
             help=dedent(
             """A list of all python packages necessary for different steps in the
             Vend preparation process. This list is specified in pants.ini, and
             any desired changes to the required version numbers should be made
             there."""))
    register('--set-vend-cache', default=None,
             help=dedent(
             """Specify the location at which to cache the virtualenv that this Vend
             executes out of on target computers. The environment variable
             VENDCACHE (on the target computer) takes precedence over this
             option. If neither that or this option are specified, then the
             default directory to cache Vends is chosen, which is
             'Path/to/homedirectory/.vendcache'."""))

  def _determine_supported_interpreters_intersection(self, all_source_libs):

    def resolve_implementation_constraint(curr_impls, new_implementation):
      if new_implementation == '':
        return curr_impls
      elif new_implementation.lower() == 'ironpython':
        new_implementation = 'ip'
      elif new_implementation.lower() == 'pypy':
        new_implementation = 'pp'
      else:
        #'CPython' => 'cp', 'Jython' => 'jy', and 'Python' => 'py'.
        new_implementation = new_implementation[:2].lower()

      if new_implementation == 'py': # This is generic Python.
        return curr_impls
      elif new_implementation in curr_impls: # Then we can support *only* the new implementation.
        return set([new_implementation])
      else:
        raise Exception(
          dedent(
            """A single PythonLibrary source target requires conflicting
            implementations of Python. It declares that it only runs on an
            implementation with the PEP425 Python Tag "{}" and also that it only
            runs on an implementation with the PEP425 Python Tag "{}" """
          ).format(curr_impls, new_implementation)
        )

    def parse_python_version(version_string):
      # Noe that we are choosing to only examine major and minor version numbers.
      # If micro version numbers are present, then they will be ignored.
      if version_string.count('.') == 0:
        major = version_string
        minor = 0
      elif version_string.count('.') == 1:
        major, minor = version_string.split('.')
      else:
        major, minor = version_string.split('.')[:2]
      return (int(major), int(minor))

    def parse_single_constraint(constraint, operation):
      constraint_version_index = constraint.find(operation) + len(operation)
      constraint_version = constraint[constraint_version_index:]
      constraint_implementation = constraint[:constraint_version_index - len(operation)]
      return constraint_version, constraint_implementation

    def handle_single_constraint(constraint, supported_vers, supported_impls):
      if '<=' in constraint:
        constraint_version, constraint_implementation = parse_single_constraint(constraint, '<=')
        supported_vers = [
          v for v in supported_vers if parse_python_version(v) <= parse_python_version(constraint_version)
        ]
      elif '<' in constraint:
        constraint_version, constraint_implementation = parse_single_constraint(constraint, '<')
        supported_vers = [
          v for v in supported_vers if parse_python_version(v) < parse_python_version(constraint_version)
        ]
      elif '==' in constraint:
        constraint_version, constraint_implementation = parse_single_constraint(constraint, '==')
        supported_vers = [
          v for v in supported_vers if parse_python_version(v) == parse_python_version(constraint_version)
        ]
      elif '!=' in constraint:
        constraint_version, constraint_implementation = parse_single_constraint(constraint, '!=')
        supported_vers = [
          v for v in supported_vers if parse_python_version(v) != parse_python_version(constraint_version)
        ]
      elif '>=' in constraint:
        constraint_version, constraint_implementation = parse_single_constraint(constraint, '>=')
        supported_vers = [
          v for v in supported_vers if parse_python_version(v) >= parse_python_version(constraint_version)
        ]
      elif '>' in constraint:
        constraint_version, constraint_implementation = parse_single_constraint(constraint, '>')
        supported_vers = [
          v for v in supported_vers if parse_python_version(v) > parse_python_version(constraint_version)
        ]
      elif '~=' in constraint:
        # As enforced by PEP440, a user cannot use this "compatible release"
        # clause with a single segment version number such as ~=2.
        constraint_version, constraint_implementation = parse_single_constraint(constraint, '~=')
        supported_vers = [
          v for v in supported_vers if parse_python_version(v) >= parse_python_version(constraint_version[:-2])
        ]
      else:
        raise Exception(
          dedent(
            """The constraint "{}" does not have a valid form. The logical comparison
            must be one of the following: <=, <, ==, !=, >=, >, ~=."""
          ).format(constraint)
        )
      supported_impls = resolve_implementation_constraint(supported_impls, constraint_implementation)
      return supported_vers, supported_impls

    # Initialize return values.
    final_interpreter_version_intersection = set(self.get_options().all_py_versions[:])
    final_interpreter_impl_intersection = set(['py','cp','ip','pp','jy'])

    # Take the intersection of interpreter constraints imposed by all source libraries.
    for lib in all_source_libs:
      # Examine reqs: a list of strings representing a logical OR of interpreter constraints.
      reqs = lib.compatibility
      if reqs:
        # Enforce that reqs is a compatible iterable of strings.
        if isinstance(reqs, str):
          reqs = [reqs]

        # Initialize values for this library.
        valid_interpreter_versions_for_this_lib = set()
        valid_interpreter_implementations_for_this_lib = set()

        # Resolve version constraint(s) imposed by this req. Lists of valid
        # versions across different reqs will be logical ORed together to
        # form the full list of valid interpreter versions for a single source library.
        for req in reqs:
          # Initialize values for this requirement.
          valid_interpreter_versions_for_this_req = self.get_options().all_py_versions[:]
          valid_interpreter_implementations_for_this_req = set(['py','cp','ip','pp','jy'])


          # Take the logical AND (set intersection) of all individual version
          # constraints listed in a single requirement string.
          # (e.g. '>=2.7,<3' becomes >=2.7 AND <3)
          constraints = req.split(',')
          for constraint in constraints:
            (valid_interpreter_versions_for_this_req,
            valid_interpreter_implementations_for_this_req) = handle_single_constraint(
              constraint,
              valid_interpreter_versions_for_this_req,
              valid_interpreter_implementations_for_this_req
            )

          # Add valid interpreter versions and implementations for this req to
          # the full lists of valid versions and implementations for the whole
          # library (updating the logical OR of reqs for this source library).
          for valid_interpreter_impl in valid_interpreter_implementations_for_this_req:
            valid_interpreter_implementations_for_this_lib.add(valid_interpreter_impl)
          for valid_interpreter_version in valid_interpreter_versions_for_this_req:
            valid_interpreter_versions_for_this_lib.add(valid_interpreter_version)

        # Update the intersection of requirements between source library targets.
        final_interpreter_version_intersection = final_interpreter_version_intersection.intersection(valid_interpreter_versions_for_this_lib)
        final_interpreter_impl_intersection = final_interpreter_impl_intersection.intersection(valid_interpreter_implementations_for_this_lib)

    return (list(final_interpreter_version_intersection), list(final_interpreter_impl_intersection))

  def _populate_vend_source_directory(self, all_source_items, source_dir):
    for target in all_source_items:
      for source_path in target.sources_relative_to_buildroot():
        sourceroot_relative_source_path = os.path.relpath(source_path, target.target_base)
        # Fix source_path to include the buildroot.
        source_path = os.path.join(get_buildroot(), source_path)
        dest_path = os.path.join(source_dir, sourceroot_relative_source_path)
        safe_mkdir(os.path.dirname(dest_path))
        shutil.copyfile(source_path, dest_path)
        # Ensure __init__.py files in the source tree.
        current_dir = os.path.dirname(sourceroot_relative_source_path)
        while current_dir:
          init_py = os.path.join(source_dir, current_dir, '__init__.py')
          if not os.path.exists(init_py):
            with open(init_py, 'wb'):
              pass
          current_dir = os.path.dirname(current_dir)

  def _download_third_party_dependencies(self, vend_archive_dir, dependency_wheels_dir,
    logging_path, requirements_path, python_binary, supported_interpreter_versions,
    supported_interpreter_impls
  ):
    # Ensure vend's dependency_wheels_dir.
    safe_mkdir(dependency_wheels_dir)

    # Gather vend's target platforms.
    desired_platforms = set(python_binary.platforms)
    if desired_platforms == set():
      # If none are specified, assume the current platform.
      desired_platforms = set([get_platform()])
    elif 'current' in desired_platforms:
      desired_platforms.remove('current')
      desired_platforms.add(get_platform())

    # Let error_combinations be a list of tuples (dependency, interpreter,
    # platform) that each describe a combination for which a wheel could not be
    # downloaded.
    error_combinations = []

    # Establish logging for capturing critical pip failures.
    logger = logging.getLogger('pip')
    fh = logging.FileHandler(logging_path)
    fh.setLevel(logging.CRITICAL)
    logger.addHandler(fh)

    # Prepare base arugments to the 'pip install --download' command.
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
      download_args.append('--interpreter-version')
      for supported_interpreter_version in supported_interpreter_versions:
        interpreter_string = supported_interpreter_version[0] + supported_interpreter_version[2]
        download_args.append(interpreter_string)
        # Download dependency wheels and all of their transitive dependencies.
        wheel_downloader = InstallCommand()
        output = wheel_downloader.main(download_args)
        # Collect the combinations that resulted in error.
        if not output == SUCCESS:
          with open(logging_path) as f:
            # Record the bottom line, which will always have the latest log.
            dependency = re.search('for ([\w\d\.=<>!~]+)', f.readlines()[-1]).group(1)
          error_combinations.append((dependency, supported_interpreter_version, platform))
        download_args = download_args[:-1]
      download_args = download_args[:-2]

    # Check for combination of dependency, platform, and interpreter that could not be downloaded.
    if error_combinations:
      error_string = (
        '\nCould not resolve all 3rd party dependencies. Each of the combinations '
        'of dependency, platform, and interpreter-version listed below could not be '
        'downloaded. Are you pointing to your wheelhouse by adding its path to '
        '"wheelhouses" under the [vend] section of pants.ini? If so, then to support '
        'these dependencies, you must either restrict your desired Python versions by '
        'adjusting the compatibility field of the PythonBinary, or drop support for the '
        'platforms that cannot be resolved:'
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

    # Delete piplog.log: we don't need it anymore.
    os.remove(logging_path)

    # Check that all downloaded wheels are compatible with the supported python implementations.
    for whl_file in os.listdir(dependency_wheels_dir):
      wheel = Wheel(whl_file)
      wheel_is_compatible = False
      # We only need one of the wheel's compatible pyversions to be compatible.
      for pyversion in wheel.pyversions:
        impl = pyversion[:2]
        if impl == 'py' or impl in supported_interpreter_impls:
          wheel_is_compatible = True
          break
      if not wheel_is_compatible:
        shutil.rmtree(vend_archive_dir)
        raise Exception(
          dedent(
            """Attempted to download wheel dependency "{}" but it is
            not compatible with the python implementation constraints imposed by
            the PythonLibrary targets. It runs on Python versions with these
            PEP425 Python Tags: {}, but the valid interpreter implementations are
            {}"""
          ).format(
            wheel.name,
            wheel.pyversions,
            supported_interpreter_impls
          )
        )
    # Return information we need to pass to the bootstrap_data file.
    return desired_platforms

  def _download_bootstrap_dependencies(self, bootstrap_wheels_dir, bootstrap_py_reqs):
    safe_mkdir(bootstrap_wheels_dir)

    download_args = ['--quiet', '--download', bootstrap_wheels_dir]
    for bootstrap_req in bootstrap_py_reqs:
      download_args.append(bootstrap_req)
      wheel_downloader = InstallCommand()
      wheel_downloader.main(download_args)
      download_args = download_args[:-1]

    # Determine which version of virtualenv we downloaded for the target computer.
    virtualenv_wheel_candidates = [wheel for wheel in os.listdir(bootstrap_wheels_dir) if wheel.startswith('virtualenv')]
    if virtualenv_wheel_candidates:
      # Return information we need to pass to the bootstrap_data file.
      return virtualenv_wheel_candidates[0]
    else:
      raise Exception(
        dedent(
          """Failed to download a wheel for virtualenv, so cannot
          bootstrap this Vend. Do you have a valid version of virtualenv in
          pants.ini, under the [Vend] section, in the "bootstrap_requirements"
          list?'"""
        )
      )

  def _write_bootstrap_data_to_json(self, bootstrap_data_path, vend_cache_dir,
    supported_interpreter_versions, supported_interpreter_impls, desired_platforms,
    virtualenv_wheel
  ):
    # Write the bootstrap data JSON for the __main__.py and bootstrap.py scripts.
    bootstrap_data = {
      'vend_cache_dir' : vend_cache_dir,
      'interpreter_search_paths' : self.get_options().interpreter_search_paths,
      'supported_interpreter_versions' : supported_interpreter_versions,
      'supported_interpreter_impls' : supported_interpreter_impls,
      'supported_platforms' : list(desired_platforms),
      'virtualenv_wheel' : virtualenv_wheel,
    }
    with open(bootstrap_data_path, 'w') as f:
     json.dump(bootstrap_data, f)

  def _write_vend_executable_zip_file(self, vend_name, vend_workdir, vend_archive_dir):
    # Create the .vend zip file.
    vend_zip = os.path.join(get_buildroot(), 'dist', vend_name)
    safe_delete(vend_zip)
    # Write the shebang for executing the vend directly.
    with open(vend_zip, 'ab') as vend_zipfile:
      vend_zipfile.write('#!/usr/bin/env python\n'.encode('utf-8'))
    # Write the contents of the Vend source directory.
    vend_zipfile = zipfile.ZipFile(vend_zip, 'a')
    for root, dirs, files in os.walk(vend_workdir):
      for src_file in files:
          if src_file == '__main__.py':
            write_path = os.path.relpath(os.path.join(root, src_file), vend_workdir)
          else:
            write_path = os.path.join(
              os.path.basename(vend_archive_dir),
              os.path.relpath(os.path.join(root, src_file), vend_workdir)
            )
          vend_zipfile.write(os.path.join(root, src_file), arcname=write_path)
    vend_zipfile.close()
    os.chmod(vend_zip, 0755)
    return vend_zip

  def execute(self):
    # Grab and validate the PythonBinary input target.
    if len(self.context.target_roots) != 1:
      raise Exception('Invalid target roots: must pass a single target.')
    python_binary = self.context.target_roots[0]
    if not isinstance(python_binary, PythonBinary):
      raise Exception('Invalid target roots: must pass a single python_binary target.')

    # Identify PythonLibraries, PythonRequirementLibraries, and Resources.
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

    # Generate the fingerprint for this vend using all relevant targets in the graph.
    with self.invalidated(self.context.targets()) as invalidation_check:
      global_vts = VersionedTargetSet.from_versioned_targets(invalidation_check.all_vts)

    # Setup vend directory structure.
    vend_name = '{}.vend'.format(python_binary.name)
    vend_archive_dir = os.path.join(get_buildroot(), 'dist', python_binary.name + '_' + global_vts.cache_key.hash)
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

    # Copy source files into the vend's source directory.
    self._populate_vend_source_directory(all_source_items, source_dir)

    # Find the exact intersection of Python interpreter constraints imposed by the
    # PythonBinary and PythonLibrary targets. ( [list_supported_minor_versions],
    # [list_supported_pep425_python_implementation_tags] ).
    supported_interpreter_versions, supported_interpreter_impls = self._determine_supported_interpreters_intersection(all_source_libs)

    # Assert that at least one Python interpreter satisfies the intersection of constraints.
    if not supported_interpreter_versions or not supported_interpreter_impls:
      shutil.rmtree(vend_archive_dir)
      raise Exception(
        dedent(
          """No Python interpreter can satisfy the intersection of the constraints
          imposed by the PythonLibrary targets. Check the "compatibility"
          field of the PythonBinary and all of its PythonLibrary sources."""
        )
      )

    # Establish vend's requirements.txt and fill it with dependency_reqs.
    with open(requirements_path, 'wb') as f:
      for req in sorted_py_reqs:
        f.write('{}\n'.format(str(req)))

    desired_platforms = self._download_third_party_dependencies(vend_archive_dir,
      dependency_wheels_dir, logging_path, requirements_path, python_binary,
      supported_interpreter_versions, supported_interpreter_impls
    )

    virtualenv_wheel = self._download_bootstrap_dependencies(bootstrap_wheels_dir,
      bootstrap_py_reqs
    )

    # Determine where to cache this Vend on the target computer.
    if self.get_options().set_vend_cache:
      vend_cache_dir = self.get_options().set_vend_cache
    else: # Use the default directory.
      vend_cache_dir = '~/.vendcache'

    self._write_bootstrap_data_to_json(bootstrap_data_path, vend_cache_dir,
      supported_interpreter_versions, supported_interpreter_impls, desired_platforms,
      virtualenv_wheel
    )

    # Add the main script (for executing the zip) to the vend.
    shutil.copyfile(
      'contrib/vend/src/python/pants/contrib/vend/__main__.py',
      main_path,
    )

    # Add the bootstrap script to the vend.
    shutil.copyfile(
      'contrib/vend/src/python/pants/contrib/vend/bootstrap.py',
      bootstrap_path,
    )

    # Codegen and add the entrypoint for the vend.
    run_script = dedent(
      """
      #!/bin/bash
      set -eo pipefail
      exec $(dirname $BASH_SOURCE)/venv/bin/python -m {} "$@"
      """.format(python_binary.entry_point)
    ).strip()
    with open(run_path, 'wb') as f:
      f.write(run_script)

    vend_zip = self._write_vend_executable_zip_file(vend_name, vend_workdir, vend_archive_dir)

    # Delete the archive dir.
    shutil.rmtree(vend_archive_dir)

    # Tell the user where their Vend is.
    print('\nVEND source package created at {}'.format(vend_zip), file=sys.stderr)