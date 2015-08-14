# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import json
import os
import subprocess
import zipfile
from textwrap import dedent

from pants.base.address import SyntheticAddress
from pants.base.build_environment import get_buildroot
from pants.base.source_root import SourceRoot
from pants_test.backend.python.tasks.python_task_test import PythonTaskTest

from pants.contrib.vend.tasks.vend import Vend


class VendTest(PythonTaskTest):

  @classmethod
  def task_type(cls):
    return Vend

  def make_vend(self, target_roots):
    options = {
      'vend': {
        'all_py_versions' : [
          '2.6', '2.7', '3.2', '3.3', '3.4',
        ],
        'wheelhouses' : [
          os.path.join(self.build_root, '.wheelhouse')
        ],
        'interpreter_search_paths' : [
          '/usr/local/Cellar/python3/3.4.3/bin/python3.4',
          '/usr/local/Cellar/python/2.7.9/bin/python2.7',
          '/usr/bin/python2.6',
          '/usr/bin/python2.7',
        ],
        'bootstrap_requirements' : [
          'setuptools==15.2',
          'pip==6.1.1',
          'virtualenv==13.0.3',
          'pex==1.0.0'
        ],
      }
    }
    self.set_options(
      all_py_versions=[
        '2.6', '2.7', '3.2', '3.3', '3.4',
      ],
      wheelhouses=[
        os.path.join(self.build_root, '.wheelhouse')
      ],
      interpreter_search_paths=[
        '/usr/local/Cellar/python3/3.4.3/bin/python3.4',
        '/usr/local/Cellar/python/2.7.9/bin/python2.7',
        '/usr/bin/python2.6',
        '/usr/bin/python2.7',
      ],
      bootstrap_requirements=[
        'setuptools==15.2',
        'pip==6.1.1',
        'virtualenv==13.0.3',
        'pex==1.0.0'
      ],
    )
    vend_task = self.create_task(self.context(target_roots=target_roots))
    vend_task.execute()

  def create_python_binary(self, relpath, name, dependencies=(), compatibility=None, platforms=()):
    # Create source file.
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
    # Create build file.
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
        dependencies=','.join([repr(d) for d in dependencies]),
        platforms=','.join([repr(p) for p in platforms]),
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
        dependencies=','.join([repr(d) for d in dependencies]),
        compatibility = compatibility,
        provides_clause='provides={0},'.format(provides) if provides else ''
      )
    )
    if source_contents_map:
      self.create_file(relpath=os.path.join(relpath, '__init__.py'))
      for source, contents in source_contents_map.items():
        self.create_file(relpath=os.path.join(relpath, source), contents=contents)
    return self.target(SyntheticAddress(relpath, name).spec)

  def build_wheel(self, wheel_name, python_tag, abi_tag, platform_tag):
    wheel_dir = self.create_dir(relpath=wheel_name)
    wheel_setup = self.create_file(
      relpath = os.path.join(wheel_name, 'setup.py'),
      contents= dedent("""
        #!/usr/bin/env python
        from setuptools import setup

        setup(name='{}',
              version='1.0',
        )
      """.format(wheel_name))
    )
    p = subprocess.Popen(['python', wheel_setup, 'bdist_wheel', '-d', self.wheelhouse], cwd=wheel_dir)
    p.communicate()
    os.rename(
      os.path.join(self.wheelhouse, '{}-1.0-cp27-none-macosx_10_10_x86_64.whl'.format(wheel_name)),
      os.path.join(self.wheelhouse, '{}-1.0-{}-{}-{}.whl'.format(wheel_name, python_tag, abi_tag, platform_tag))
    )

  def build_wheelhouse(self):
    self.wheelhouse = self.create_dir(relpath='.wheelhouse')
    self.build_wheel('wheel1', 'py2.py3', 'none', 'any')
    self.build_wheel('wheel2', 'cp27', 'none', 'linux_x86_64')
    self.build_wheel('wheel2', 'cp27', 'none', 'macosx_10_10_x86_64')
    self.build_wheel('wheel3', 'py2', 'none', 'linux_x86_64')
    self.build_wheel('wheel3', 'py2', 'none', 'macosx_10_10_universal')
    self.build_wheel('wheel3', 'py3', 'none', 'linux_x86_64')
    self.build_wheel('wheel3', 'py3', 'none', 'macosx_10_10_universal')

  def setUp(self):
    super(VendTest, self).setUp()

    SourceRoot.register('python')

    self.build_wheelhouse()

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
    self.make_vend([self.b_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 'b.vend'), 'r')
    vend_contents = vend_zip.namelist()
    vend_zip.close()
    vend_src_dir = 'b_b051442ce90c205c41d869c8401cb2914c274f0a'
    # Assert that all components are present.
    sources_a_exists = os.path.join(vend_src_dir, 'sources', 'src', 'a', 'a.py') in vend_contents
    sources_b_exists = os.path.join(vend_src_dir, 'sources', 'src', 'b', 'b.py') in vend_contents
    requirements_file_exists = os.path.join(vend_src_dir, 'requirements.txt') in vend_contents
    bootstrap_script_exists = os.path.join(vend_src_dir, 'bootstrap.py') in vend_contents
    bootstrap_data_exists = os.path.join(vend_src_dir, 'bootstrap_data.json') in vend_contents
    entry_script_exists = '__main__.py' in vend_contents
    self.assertTrue(sources_a_exists)
    self.assertTrue(sources_b_exists)
    self.assertTrue(requirements_file_exists)
    self.assertTrue(bootstrap_script_exists)
    self.assertTrue(bootstrap_data_exists)
    self.assertTrue(entry_script_exists)
    # Verify all bootstrap wheels are present.
    pex_wheel_exists = os.path.join(vend_src_dir, 'bootstrap_wheels', 'pex-1.0.0-py2.py3-none-any.whl') in vend_contents
    setuptools_wheel_exists = os.path.join(vend_src_dir, 'bootstrap_wheels', 'setuptools-15.2-py2.py3-none-any.whl') in vend_contents
    pip_wheel_exists = os.path.join(vend_src_dir, 'bootstrap_wheels', 'pip-6.1.1-py2.py3-none-any.whl') in vend_contents
    virtualenv_wheel_exists = os.path.join(vend_src_dir, 'bootstrap_wheels', 'virtualenv-13.0.3-py2.py3-none-any.whl') in vend_contents
    self.assertTrue(pex_wheel_exists)
    self.assertTrue(setuptools_wheel_exists)
    self.assertTrue(pip_wheel_exists)
    self.assertTrue(virtualenv_wheel_exists)
    # Build the vend and execute it.
    subprocess.call([os.path.join(get_buildroot(), 'dist', 'b.vend')], stderr=subprocess.STDOUT)

  def test_bad_input_one_py_library(self):
    with self.assertRaises(Exception) as e_context_manager:
      self.make_vend([self.a_library])
    self.assertEquals(
      e_context_manager.exception.message,
      'Invalid target roots: must pass a single python_binary target.'
    )

  def test_bad_input_two_py_binaries(self):
    with self.assertRaises(Exception) as e_context_manager:
      self.make_vend([self.b_binary, self.c_binary])
    self.assertEquals(
      e_context_manager.exception.message,
      'Invalid target roots: must pass a single target.'
    )

  def test_bad_input_one_binary_one_library(self):
    with self.assertRaises(Exception) as e_context_manager:
      self.make_vend([self.b_binary, self.a_library])
    self.assertEquals(
      e_context_manager.exception.message,
      'Invalid target roots: must pass a single target.'
    )

  def test_interpreter_intersection_simple(self):
    self.make_vend([self.b_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 'b.vend'), 'r')
    vend_src_dir = 'b_b051442ce90c205c41d869c8401cb2914c274f0a'
    bootstrap_data = json.load(vend_zip.open(os.path.join(vend_src_dir, 'bootstrap_data.json')))
    vend_zip.close()
    self.assertTrue(
      set(bootstrap_data['supported_interpreter_versions']) ==
      set([
        '2.6', '2.7', '3.2', '3.3', '3.4',
      ])
    )

  def test_interpreter_intersection_simple2(self):
    self.make_vend([self.d_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 'd.vend'), 'r')
    vend_src_dir = 'd_75f6b441eb357710d00aecdbf7ca7498b2c70191'
    bootstrap_data = json.load(vend_zip.open(os.path.join(vend_src_dir, 'bootstrap_data.json')))
    vend_zip.close()
    self.assertTrue(
      set(bootstrap_data['supported_interpreter_versions']) ==
      set(['2.7', '3.4',])
    )

  def test_interpreter_intersection_does_not_exist(self):
    with self.assertRaises(Exception) as e_context_manager:
      self.make_vend([self.f_binary])
    self.assertEquals(
      e_context_manager.exception.message,
      dedent(
        """No Python interpreter can satisfy the intersection of the constraints
          imposed by the PythonLibrary targets. Check the "compatibility"
          field of the PythonBinary and all of its PythonLibrary sources."""
      )
    )

  def test_interpreter_intersection_implementation_contradiction(self):
    with self.assertRaises(Exception) as e_context_manager:
      self.make_vend([self.h_binary])
    self.assertEquals(
      e_context_manager.exception.message,
      dedent(
        """No Python interpreter can satisfy the intersection of the constraints
          imposed by the PythonLibrary targets. Check the "compatibility"
          field of the PythonBinary and all of its PythonLibrary sources."""
      )
    )

  def test_interpreter_intersection_complex(self):
    self.make_vend([self.j_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 'j.vend'), 'r')
    vend_src_dir = 'j_64f5a17e5ce71825c3e91d7108b5371a2ff07047'
    bootstrap_data = json.load(vend_zip.open(os.path.join(vend_src_dir, 'bootstrap_data.json')))
    vend_zip.close()
    self.assertTrue(
      set(bootstrap_data['supported_interpreter_versions']) ==
      set(['3.4'])
    )
    self.assertTrue(
      set(bootstrap_data['supported_interpreter_impls']) ==
      set(['cp',])
    )

  def test_copy_source_files(self):
    self.make_vend([self.m_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 'm.vend'), 'r')
    vend_contents = vend_zip.namelist()
    vend_zip.close()
    source_files_path = os.path.join('m_4e3977a3b5ad82187f102b2a8c0730754d13e48e', 'sources', 'src')
    k1_exists = os.path.join(source_files_path, 'k', 'k1.py') in vend_contents
    k2_exists = os.path.join(source_files_path, 'k', 'k2.py') in vend_contents
    k3_exists = os.path.join(source_files_path, 'k', 'sub_k', 'k3.py') in vend_contents
    l1_exists = os.path.join(source_files_path, 'l', 'sub_l', 'l1.py') in vend_contents
    l2_exists = os.path.join(source_files_path, 'l', 'sub_l', 'sub_l', 'l2.py') in vend_contents
    m_exists = os.path.join(source_files_path, 'm', 'm.py') in vend_contents
    k_init1_exists = os.path.join(source_files_path, 'k', '__init__.py') in vend_contents
    k_init2_exists = os.path.join(source_files_path, 'k', 'sub_k', '__init__.py') in vend_contents
    l_init1_exists = os.path.join(source_files_path, 'l', '__init__.py') in vend_contents
    l_init2_exists = os.path.join(source_files_path, 'l', 'sub_l', '__init__.py') in vend_contents
    l_init3_exists = os.path.join(source_files_path, 'l', 'sub_l', 'sub_l', '__init__.py') in vend_contents
    m_init_exists = os.path.join(source_files_path, 'm', '__init__.py') in vend_contents
    src_init_exists = os.path.join(source_files_path, '__init__.py') in vend_contents
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
    self.build_wheelhouse()
    self.make_vend([self.p_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 'p.vend'), 'r')
    vend_contents = vend_zip.namelist()
    vend_zip.close()
    vend_deps_dir = os.path.join('p_14d21a331a32914c47763adfe7dcfcd76901b848', 'dep_wheels')
    dep_was_downloaded = os.path.join(vend_deps_dir, 'wheel1-1.0-py2.py3-none-any.whl') in vend_contents
    self.assertTrue(dep_was_downloaded)

  def test_download_deps_explicitly_for_current_platform(self):
    self.build_wheelhouse()
    self.make_vend([self.q_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 'q.vend'), 'r')
    vend_contents = vend_zip.namelist()
    vend_zip.close()
    vend_deps_dir = os.path.join('q_7de93c9b98aee01931b7e1e2820087c1d17f1b8f', 'dep_wheels')
    dep_was_downloaded = os.path.join(vend_deps_dir, 'wheel1-1.0-py2.py3-none-any.whl') in vend_contents
    self.assertTrue(dep_was_downloaded)

  def test_download_deps_multiple_platforms(self):
    self.build_wheelhouse()
    self.make_vend([self.t_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 't.vend'), 'r')
    vend_contents = vend_zip.namelist()
    vend_zip.close()
    vend_deps_dir = os.path.join('t_d6fac272c964329ccf304b911a850f4416933860', 'dep_wheels')
    mac_wheel_was_downloaded = os.path.join(vend_deps_dir, 'wheel2-1.0-cp27-none-macosx_10_10_x86_64.whl') in vend_contents
    linux_wheel_was_downloaded = os.path.join(vend_deps_dir, 'wheel2-1.0-cp27-none-linux_x86_64.whl') in vend_contents
    self.assertTrue(mac_wheel_was_downloaded)
    self.assertTrue(linux_wheel_was_downloaded)

  def test_download_deps_failure_unsupported_platform(self):
    with self.assertRaises(Exception) as e_context_manager:
      self.make_vend([self.u_binary])
    self.assertEquals(
      e_context_manager.exception.message[:617],
      '\nCould not resolve all 3rd party dependencies. Each of the combinations '
      'of dependency, platform, and interpreter-version listed below could not be '
      'downloaded. Are you pointing to your wheelhouse by adding its path to '
      '"wheelhouses" under the [vend] section of pants.ini? If so, then to support '
      'these dependencies, you must either restrict your desired Python versions by '
      'adjusting the compatibility field of the PythonBinary, or drop support for the '
      'platforms that cannot be resolved:'
      '\nFailed to resolve dependency "wheel2==1.0" for Python 2.7 on platform '
      'unsupported_platform.\nSee detailed error messages logged by pip'
    )

  def test_download_deps_failure_correct_platform_unsupported_interpreter(self):
    with self.assertRaises(Exception) as e_context_manager:
      self.make_vend([self.v_binary])
    self.assertEquals(
      e_context_manager.exception.message[:494],
      dedent(
            """Attempted to download wheel dependency "wheel2" but it is
            not compatible with the python implementation constraints imposed by
            the PythonLibrary targets. It runs on Python versions with these
            PEP425 Python Tags: [u\'cp27\'], but the valid interpreter implementations are
            [u\'pp\']""")
    )

  def test_download_deps_multiple_platforms_multiple_interpreters(self):
    self.build_wheelhouse()
    self.make_vend([self.x_binary])
    vend_zip = zipfile.ZipFile(os.path.join(get_buildroot(), 'dist', 'x.vend'), 'r')
    vend_contents = vend_zip.namelist()
    vend_zip.close()
    vend_deps_dir = os.path.join('x_af07f067cc16fd7aa965396206dd75272f6e050e', 'dep_wheels')
    mac_py2_wheel_was_downloaded = os.path.join(vend_deps_dir, 'wheel3-1.0-py2-none-macosx_10_10_universal.whl') in vend_contents
    mac_py3_wheel_was_downloaded = os.path.join(vend_deps_dir, 'wheel3-1.0-py3-none-macosx_10_10_universal.whl') in vend_contents
    linux_py2_wheel_was_downloaded = os.path.join(vend_deps_dir, 'wheel3-1.0-py2-none-linux_x86_64.whl') in vend_contents
    linux_py3_wheel_was_downloaded = os.path.join(vend_deps_dir, 'wheel3-1.0-py3-none-linux_x86_64.whl') in vend_contents
    self.assertTrue(mac_py2_wheel_was_downloaded)
    self.assertTrue(mac_py3_wheel_was_downloaded)
    self.assertTrue(linux_py2_wheel_was_downloaded)
    self.assertTrue(linux_py3_wheel_was_downloaded)
