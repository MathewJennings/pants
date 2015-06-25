# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import json
import os
from textwrap import dedent

from pants.backend.python.python_requirement import PythonRequirement
from pants.backend.python.targets.python_binary import PythonBinary
from pants.backend.python.targets.python_library import PythonLibrary
from pants.backend.python.targets.python_requirement_library import PythonRequirementLibrary
from pants.base.address import SyntheticAddress
from pants.base.build_environment import get_buildroot
from pants.base.source_root import SourceRoot
from pants_test.backend.python.tasks.python_task_test import PythonTaskTest

from pants.contrib.vex.tasks.vex import Vex


class VexTest(PythonTaskTest):

  @classmethod
  def task_type(cls):
    return Vex

  def make_vex(self, target_roots):
    vex_task = self.create_task(self.context(target_roots=target_roots))
    self.populate_all_py_versions(vex_task)
    self.populate_wheelhouses(vex_task)
    self.populate_interpreter_searchpaths(vex_task)
    vex_task.execute()

  def populate_all_py_versions(self, vextest_run_task):
    vextest_run_task.get_options().all_py_versions = [
      '2.0', '2.1', '2.2', '2.3', '2.4', '2.5', '2.6',
      '2.7', '3.0', '3.1', '3.2', '3.3', '3.4', '3.5',
    ]

  def populate_wheelhouses(self, vextest_run_task):
    vextest_run_task.get_options().wheelhouses = [
      '/Users/mjennings/pants/contrib/vex/tests/python/pants_test/contrib/vex/test_wheelhouse/',
    ]

  def populate_interpreter_searchpaths(self, vextest_run_task):
    vextest_run_task.get_options().interpreter_search_paths = [
    '/usr/local/Cellar/python3/3.4.3/bin/python3.4',
    '/usr/local/Cellar/python/2.7.9/bin/python2.7',
    '/usr/bin/python2.6',
    '/usr/bin/python2.7',
  ]

  def create_python_binary(self, relpath, name, dependencies=(), compatibility=None, platforms=()):
    # Create source file
    source_content = dedent('''
      import sys

      if __name__ == '__main__':
        pass
    ''')
    for dep in dependencies:
      source_content += dedent('''
        from src.{0}.{0} import {0}_call
        print({0}_call())
      ''').format(dep[-1])
    self.create_file(
      relpath = os.path.join(os.path.dirname(self.build_path(relpath)),'{}.py'.format(name)),
      contents = source_content
    )
    # Create build file
    self.create_file(
      relpath=self.build_path(relpath),
      contents=dedent("""
        python_binary(
          name='{name}',
          source='{name}.py',
          dependencies=[
            {dependencies}
          ],
          compatibility={compatibility},
          platforms=[
            {platforms}
          ]
        )
      """).format(
        name=name,
        compatibility=compatibility,
        dependencies=','.join(map(repr, dependencies)),
        platforms=','.join(map(repr, platforms)),
      )
    )
    return self.target(SyntheticAddress(relpath, name).spec)

  def create_python_library(self, relpath, name, source_contents_map=None, dependencies=(), provides=None, compatibility=None):
    sources = ['__init__.py'] + source_contents_map.keys() if source_contents_map else None
    sources_strs = ["'{0}'".format(s) for s in sources] if sources else None
    self.create_file(
      relpath=self.build_path(relpath),
      contents=dedent("""
        python_library(
          name='{name}',
          {sources_clause}
          dependencies=[
            {dependencies}
          ],
          compatibility={compatibility}
          {provides_clause}
        )
      """).format(
        name=name,
        sources_clause='sources=[{0}],'.format(','.join(sources_strs)) if sources_strs else '',
        dependencies=','.join(map(repr, dependencies)),
        compatibility = compatibility,
        provides_clause='provides={0},'.format(provides) if provides else ''
      )
    )
    if source_contents_map:
      self.create_file(relpath=os.path.join(relpath, '__init__.py'))
      for source, contents in source_contents_map.items():
        self.create_file(relpath=os.path.join(relpath, source), contents=contents)
    return self.target(SyntheticAddress(relpath, name).spec)

  def setUp(self):
    super(VexTest, self).setUp()

    SourceRoot.register('python')

    self.a_library = self.create_python_library(
      relpath = 'python/src/a',
      name = 'a',
      source_contents_map = {'a.py':
        dedent("""
          def a_call():
            return 'Hello, world!'
        """)
      },
    )

    self.b_binary = self.create_python_binary(
      relpath = 'python/src/b',
      name = 'b',
      dependencies=['python/src/a'],
    )

    self.c_binary = self.create_python_binary(
      relpath = 'python/src/c',
      name = 'c',
      dependencies=['python/src/a'],
    )

    self.d_binary = self.create_python_binary(
      relpath = 'python/src/d',
      name = 'd',
      dependencies=['python/src/a'],
      compatibility=['>=2.7,<3','>=3.4'],
    )

    self.e_library = self.create_python_library(
      relpath = 'python/src/e',
      name = 'e',
      source_contents_map = {'e.py':
        dedent("""
          def e_call():
            return 'Hello, world!'
        """)
      },
      compatibility=['<2.7']
    )

    self.f_binary = self.create_python_binary(
      relpath = 'python/src/f',
      name = 'f',
      dependencies=['python/src/e'],
      compatibility=['>=2.7'],
    )

    self.g_library = self.create_python_library(
      relpath = 'python/src/g',
      name = 'g',
      source_contents_map = {'g.py':
        dedent("""
          def g_call():
            return 'Hello, world!'
        """)
      },
      compatibility=['Pypy>=2.7']
    )

    self.h_binary = self.create_python_binary(
      relpath = 'python/src/h',
      name = 'h',
      dependencies=['python/src/g'],
      compatibility=['CPython>=2.7'],
    )

    self.i_library = self.create_python_library(
      relpath = 'python/src/i',
      name = 'i',
      source_contents_map = {'i.py':
        dedent("""
          def i_call():
            return 'Hello, world!'
        """)
      },
      compatibility=['Cpython>=2.6,<3','>=3.4']
    )

    self.j_binary = self.create_python_binary(
      relpath = 'python/src/j',
      name = 'j',
      dependencies=['python/src/i'],
      compatibility=['CPython>=3'],
    )

    self.k_library = self.create_python_library(
      relpath = 'python/src/k',
      name = 'k',
      source_contents_map = {
        'k1.py':
        dedent("""
          def k1_call():
            return 'Hello, world!'
        """),
        'k2.py':
        dedent("""
          def k2_call():
            return 'Hello, world!'
        """),
        'sub_k/k3.py':
        dedent("""
          def k3_call():
            return 'Hello, world!'
        """)
      },
    )

    self.l_library = self.create_python_library(
      relpath = 'python/src/l',
      name = 'l',
      source_contents_map = {
        'sub_l/l1.py':
        dedent("""
          def l1_call():
            return 'Hello, world!'
        """),
        'sub_l/sub_l/l2.py':
        dedent("""
          def l2_call():
            return 'Hello, world!'
        """)
      },
    )

    self.m_binary = self.create_python_binary(
      relpath = 'python/src/m',
      name = 'm',
      dependencies=[
        'python/src/k',
        'python/src/l',
      ],
    )

    self.n_req_library = self.create_file(
      relpath=self.build_path('python/src/3rdpartyreqs/python'),
      contents=dedent("""
        python_requirement_library(
          name='req1',
          requirements=[
            python_requirement('wheel1==1.0'),
          ]),
        python_requirement_library(
          name='req2',
          requirements=[
            python_requirement('wheel2==1.0'),
          ]),
        python_requirement_library(
          name='req3',
          requirements=[
            python_requirement('wheel3==1.0'),
          ]),
      """),
    )

    self.o_library = self.create_python_library(
      relpath = 'python/src/o',
      name = 'o',
      source_contents_map = {'o.py':
        dedent("""
          def o_call():
            return 'Hello, world!'
        """)
      },
      dependencies=['python/src/3rdpartyreqs/python:req1'],
    )

    self.p_binary = self.create_python_binary(
      relpath = 'python/src/p',
      name = 'p',
      dependencies=[
        'python/src/o',
      ],
    )

    self.q_binary = self.create_python_binary(
      relpath = 'python/src/q',
      name = 'q',
      dependencies=[
        'python/src/o',
      ],
      platforms=['current']
    )

    self.s_library = self.create_python_library(
      relpath = 'python/src/s',
      name = 's',
      source_contents_map = {'s.py':
        dedent("""
          def s_call():
            return 'Hello, world!'
        """)
      },
      dependencies=['python/src/3rdpartyreqs/python:req2'],
    )

    self.t_binary = self.create_python_binary(
      relpath = 'python/src/t',
      name = 't',
      dependencies=[
        'python/src/s',
      ],
      platforms=[
        'macosx_10_10_x86_64',
        'linux_x86_64'
      ],
      compatibility=['==2.7'],
    )

    self.u_binary = self.create_python_binary(
      relpath = 'python/src/u',
      name = 'u',
      dependencies=[
        'python/src/s',
      ],
      platforms=[
        'unsupported_platform',
      ],
      compatibility=['==2.7'],
    )

    self.v_binary = self.create_python_binary(
      relpath = 'python/src/v',
      name = 'v',
      dependencies=[
        'python/src/s',
      ],
      platforms=[
        'macosx_10_10_x86_64',
      ],
      compatibility=['Pypy==2.7'],
    )

    self.w_library = self.create_python_library(
      relpath = 'python/src/w',
      name = 'w',
      source_contents_map = {'w.py':
        dedent("""
          def w_call():
            return 'Hello, world!'
        """)
      },
      dependencies=['python/src/3rdpartyreqs/python:req3'],
    )

    self.x_binary = self.create_python_binary(
      relpath = 'python/src/x',
      name = 'x',
      dependencies=[
        'python/src/w',
      ],
      platforms=[
        'macosx_10_10_universal',
        'linux_x86_64',
      ],
    )


  def test_smoke(self):
    self.make_vex([self.b_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//b.vex.tar.gz -C dist')
    vex_src_dir = os.path.join('dist','b.vex')
    # Assert that all components are present
    vex_dir_exists = os.path.exists(vex_src_dir)
    sources_dir_exists = os.path.exists(os.path.join(vex_src_dir, 'sources'))
    requirements_file_exists = os.path.isfile(os.path.join(vex_src_dir, 'requirements.txt'))
    log_info_exists = os.path.isfile(os.path.join(vex_src_dir, 'piplog.log'))
    dep_wheels_dir_exists = os.path.exists(os.path.join(vex_src_dir, 'dep_wheels'))
    bootstrap_wheels_dir_exists = os.path.exists(os.path.join(vex_src_dir, 'bootstrap_wheels'))
    build_script_exists = os.path.isfile(os.path.join(vex_src_dir, 'build-vex.sh'))
    bootstrap_script_exists = os.path.isfile(os.path.join(vex_src_dir, 'bootstrap.py'))
    bootstrap_data_exists = os.path.isfile(os.path.join(vex_src_dir, 'bootstrap_data.json'))
    run_script_exists = os.path.isfile(os.path.join(vex_src_dir, 'run.sh'))
    self.assertTrue(vex_dir_exists)
    self.assertTrue(sources_dir_exists)
    self.assertTrue(requirements_file_exists)
    self.assertTrue(log_info_exists)
    self.assertTrue(dep_wheels_dir_exists)
    self.assertTrue(bootstrap_wheels_dir_exists)
    self.assertTrue(build_script_exists)
    self.assertTrue(bootstrap_script_exists)
    self.assertTrue(bootstrap_data_exists)
    self.assertTrue(run_script_exists)
    # Verify all bootstrap wheels are present
    pex_wheel_exists = os.path.isfile(os.path.join(vex_src_dir, 'bootstrap_wheels', 'pex-1.0.0-py2.py3-none-any.whl'))
    setuptools_wheel_exists = os.path.isfile(os.path.join(vex_src_dir, 'bootstrap_wheels', 'setuptools-15.2-py2.py3-none-any.whl'))
    pip_wheel_exists = os.path.isfile(os.path.join(vex_src_dir, 'bootstrap_wheels', 'pip-6.1.1-py2.py3-none-any.whl'))
    virtualenv_wheel_exists = os.path.isfile(os.path.join(vex_src_dir, 'bootstrap_wheels', 'virtualenv-13.0.3-py2.py3-none-any.whl'))
    self.assertTrue(pex_wheel_exists)
    self.assertTrue(setuptools_wheel_exists)
    self.assertTrue(pip_wheel_exists)
    self.assertTrue(virtualenv_wheel_exists)
    # Build the vex
    os.system('sh {}'.format(os.path.join(vex_src_dir, 'build-vex.sh')))
    # Run the binary
    os.system('sh {}'.format(os.path.join(vex_src_dir, 'run.sh')))

  def test_bad_input_one_py_library(self):
    try:
      self.make_vex([self.a_library])
    except Exception, e:
      self.assertEquals(
        e.message,
        'Invalid target roots: must pass a single python_binary target.'
      )
      return
    raise AssertionError('Expected to raise an Exception, but did not.')

  def test_bad_input_two_py_binaries(self):
    try:
      self.make_vex([self.b_binary, self.c_binary])
    except Exception, e:
      self.assertEquals(
        e.message,
        'Invalid target roots: must pass a single target.'
      )
      return
    raise AssertionError('Expected to raise an Exception, but did not.')

  def test_bad_input_one_binary_one_library(self):
    try:
      self.make_vex([self.b_binary, self.a_library])
    except Exception, e:
      self.assertEquals(
        e.message,
        'Invalid target roots: must pass a single target.'
      )
      return
    raise AssertionError('Expected to raise an Exception, but did not.')

  def test_interpreter_intersection_simple(self):
    self.make_vex([self.b_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//b.vex.tar.gz -C dist')
    bootstrap_data_path = os.path.join('dist','b.vex', 'bootstrap_data.json')
    #Retrieve bootstrap data from the JSON file
    with open(bootstrap_data_path, 'r') as f:
      bootstrap_data = json.load(f)
    self.assertTrue(
      set(bootstrap_data['supported_interp_versions']) ==
      set([
        '2.0', '2.1', '2.2', '2.3', '2.4', '2.5', '2.6',
        '2.7', '3.0', '3.1', '3.2', '3.3', '3.4', '3.5',
      ])
    )

  def test_interpreter_intersection_simple2(self):
    self.make_vex([self.d_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//d.vex.tar.gz -C dist')
    bootstrap_data_path = os.path.join('dist','d.vex', 'bootstrap_data.json')
    #Retrieve bootstrap data from the JSON file
    with open(bootstrap_data_path, 'r') as f:
      bootstrap_data = json.load(f)
    self.assertTrue(
      set(bootstrap_data['supported_interp_versions']) ==
      set(['2.7', '3.4', '3.5',])
    )

  def test_interpreter_intersection_does_not_exist(self):
    try:
      self.make_vex([self.f_binary])
    except Exception, e:
      self.assertEquals(
        e.message,
        'No Python interpreter can satisfy the intersection of the constraints '
        'imposed by the PythonLibrary targets. Check the "compatibility" field '
        'of the PythonBinary and all of its PythonLibrary sources.'
      )
      return
    raise AssertionError('Expected to raise an Exception, but did not.')

  def test_interpreter_intersection_implementation_contradiction(self):
    try:
      self.make_vex([self.h_binary])
    except Exception, e:
      self.assertEquals(
        e.message,
        'No Python interpreter can satisfy the intersection of the constraints '
        'imposed by the PythonLibrary targets. Check the "compatibility" field '
        'of the PythonBinary and all of its PythonLibrary sources.'
      )
      return
    raise AssertionError('Expected to raise an Exception, but did not.')

  def test_interpreter_intersection_complex(self):
    self.make_vex([self.j_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//j.vex.tar.gz -C dist')
    bootstrap_data_path = os.path.join('dist','j.vex', 'bootstrap_data.json')
    #Retrieve bootstrap data from the JSON file
    with open(bootstrap_data_path, 'r') as f:
      bootstrap_data = json.load(f)
    self.assertTrue(
      set(bootstrap_data['supported_interp_versions']) ==
      set(['3.4', '3.5',])
    )
    self.assertTrue(
      set(bootstrap_data['supported_interp_impls']) ==
      set(['cp',])
    )

  def test_copy_source_files(self):
    self.make_vex([self.m_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//m.vex.tar.gz -C dist')
    source_files_path = os.path.join('dist','m.vex', 'sources', 'src')
    k1_exists = os.path.isfile(os.path.join(source_files_path, 'k', 'k1.py'))
    k2_exists = os.path.isfile(os.path.join(source_files_path, 'k', 'k2.py'))
    k3_exists = os.path.isfile(os.path.join(source_files_path, 'k', 'sub_k', 'k3.py'))
    l1_exists = os.path.isfile(os.path.join(source_files_path, 'l', 'sub_l', 'l1.py'))
    l2_exists = os.path.isfile(os.path.join(source_files_path, 'l', 'sub_l', 'sub_l', 'l2.py'))
    m_exists = os.path.isfile(os.path.join(source_files_path, 'm', 'm.py'))
    k_init1_exists = os.path.isfile(os.path.join(source_files_path, 'k', '__init__.py'))
    k_init2_exists = os.path.isfile(os.path.join(source_files_path, 'k', 'sub_k', '__init__.py'))
    l_init1_exists = os.path.isfile(os.path.join(source_files_path, 'l', '__init__.py'))
    l_init2_exists = os.path.isfile(os.path.join(source_files_path, 'l', 'sub_l', '__init__.py'))
    l_init3_exists = os.path.isfile(os.path.join(source_files_path, 'l', 'sub_l', 'sub_l', '__init__.py'))
    m_init_exists = os.path.isfile(os.path.join(source_files_path, 'm', '__init__.py'))
    src_init_exists = os.path.isfile(os.path.join(source_files_path, '__init__.py'))
    self.assertTrue(k1_exists)
    self.assertTrue(k2_exists)
    self.assertTrue(k3_exists)
    self.assertTrue(l1_exists)
    self.assertTrue(l2_exists)
    self.assertTrue(m_exists)
    self.assertTrue(k_init1_exists)
    self.assertTrue(k_init2_exists)
    self.assertTrue(l_init1_exists)
    self.assertTrue(l_init2_exists)
    self.assertTrue(l_init3_exists)
    self.assertTrue(m_init_exists)
    self.assertTrue(src_init_exists)

  def test_download_deps_smoke(self):
    self.make_vex([self.p_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//p.vex.tar.gz -C dist')
    vex_deps_dir = os.path.join('dist','p.vex', 'dep_wheels')
    dep_was_downloaded = os.path.isfile(os.path.join(vex_deps_dir, 'wheel1-1.0-py2.py3-none-any.whl'))
    self.assertTrue(dep_was_downloaded)

  def test_download_deps_explicitly_for_current_platform(self):
    self.make_vex([self.q_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//q.vex.tar.gz -C dist')
    vex_deps_dir = os.path.join('dist','q.vex', 'dep_wheels')
    dep_was_downloaded = os.path.isfile(os.path.join(vex_deps_dir, 'wheel1-1.0-py2.py3-none-any.whl'))
    self.assertTrue(dep_was_downloaded)

  def test_download_deps_multiple_platforms(self):
    self.make_vex([self.t_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//t.vex.tar.gz -C dist')
    vex_deps_dir = os.path.join('dist','t.vex', 'dep_wheels')
    mac_wheel_was_downloaded = os.path.isfile(os.path.join(vex_deps_dir, 'wheel2-1.0-cp27-none-macosx_10_10_x86_64.whl'))
    linux_wheel_was_downloaded = os.path.isfile(os.path.join(vex_deps_dir, 'wheel2-1.0-cp27-none-linux_x86_64.whl'))
    self.assertTrue(mac_wheel_was_downloaded)
    self.assertTrue(linux_wheel_was_downloaded)

  def test_download_deps_failure_unsupported_platform(self):
    try:
      self.make_vex([self.u_binary])
    except Exception, e:
      self.assertEquals(
        e.message,
        '\nCould not resolve all 3rd party dependencies. Each of the combinations '
        'of dependency, platform, and interpreter-version listed below could not be '
        'downloaded. To support these dependencies, you must either restrict your '
        'desired Python versions by adjusting the compatibility field of the '
        'PythonBinary, or drop support for the platforms that cannot be resolved:'
        '\n\nFailed to download dependency "wheel2==1.0" for Python 2.7 on platform '
        'unsupported_platform.\nPip error message was:\n"Could not find a version '
        'that satisfies the requirement wheel2==1.0 (from -r '
        'dist/u_7ce303039a6907fa05cec9022276fe2798972390/u.vex/requirements.txt '
        '(line 1)) (from versions: ) No matching distribution found for wheel2==1.0 '
        '(from -r dist/u_7ce303039a6907fa05cec9022276fe2798972390/u.vex/requirements'
        '.txt (line 1))"'
      )
      return
    raise AssertionError('Expected to raise an Exception, but did not.')

  def test_download_deps_failure_correct_platform_unsupported_interpreter_(self):
    try:
      self.maxDiff = None
      self.make_vex([self.v_binary])
    except Exception, e:
      self.assertEquals(
        e.message,
        'Attempted to download wheel dependency "wheel2" but it is not compatible '
        'with the python implementation constraints imposed by the PythonLibrary '
        'targets. It runs on Python versions with these PEP425 Python Tags: [u\'cp27\'], '
        'but the valid interpreter implementations are [u\'pp\']'
      )
      return
    raise AssertionError('Expected to raise an Exception, but did not.')

  def test_download_deps_multiple_platforms_multiple_interpreters(self):
    self.make_vex([self.x_binary])
    # Unzip the vex tar.gz
    os.system('tar zxvf dist//x.vex.tar.gz -C dist')
    vex_deps_dir = os.path.join('dist','x.vex', 'dep_wheels')
    mac_py2_wheel_was_downloaded = os.path.isfile(os.path.join(vex_deps_dir, 'wheel3-1.0-py2-none-macosx_10_10_universal.whl'))
    mac_py3_wheel_was_downloaded = os.path.isfile(os.path.join(vex_deps_dir, 'wheel3-1.0-py3-none-macosx_10_10_universal.whl'))
    linux_py2_wheel_was_downloaded = os.path.isfile(os.path.join(vex_deps_dir, 'wheel3-1.0-py2-none-linux_x86_64.whl'))
    linux_py3_wheel_was_downloaded = os.path.isfile(os.path.join(vex_deps_dir, 'wheel3-1.0-py3-none-linux_x86_64.whl'))
    self.assertTrue(mac_py2_wheel_was_downloaded)
    self.assertTrue(mac_py3_wheel_was_downloaded)
    self.assertTrue(linux_py2_wheel_was_downloaded)
    self.assertTrue(linux_py3_wheel_was_downloaded)
