# Vend Python Distribution System

## Why Use Vend?

When distributing python projects, the Pex format is a popular go-to solution. Having a “Python EXecutable” makes distributing projects easy, and it providing a convenient and intuitive way to execute and interact with these projects. However, we are not guaranteed a few things. For a target computer to execute a Pex, it must have a matching Python interpreter and be running on the same OS that the distributing computer is. A consequence of this is that a single Pex cannot be executed by multiple different versions of Python interpreters, even when this ought to be possible after examining the actual interpreter constraints imposed by the library code and 3rd party dependencies of the Python project. A natural desire arises to provide a convenient executable similar to a Pex where distributors can control for complex variables on their target computers like platform/OS and python interpreter versions without letting the target environments affect the proper execution of their python projects.


## What Is A Vend?

Vend is a python distribution format which can be thought of as a “Virtual ENvironment Distribution”. A Vend is an executable zip file with a .vend extension (just like a .pex file) that holds data pertinent to running your python project out of a virtual environment. By packaging your python project into a Vend, you can know and enforce the exact combination of platforms and interpreters your project will run on. Calling `./pants vend path/to/python_binary` generates a binary_name.vend file in the dist/ subdirectory within the builddir of the pants task.

Inside this binary_name.vend zip is the source code for your project, as well as all 3rd party dependency wheels required to run it on the combination of platforms and interpreters you wish to support. You specify the platforms you wish to support by typing their names into the `platforms` field of your `python_binary` target, and you can restrict the interpreters you wish to support by typing constraints into its `compatibility` field. It is also possible that the `python_library` targets your `python_binary` depends on have constraints in their compatibility fields, and these are also factored in when determining the intersection of all interpreter constraints.

## How Does A Vend Work?

You can execute the vend directly on the command line with `./binary_name.vend`, or `path/to/vend/binary_name.vend`. Doing so for the first time on a target machine bootstraps a virtual environment in a cache directory and installs all source code and 3rd party dependencies into it before executing the entrypoint for your python project. The cache location on the target computer can be specified in one of two ways. The target computer gets the ultimate say on where to cache this vend by setting the environment variable `VENDCACHE`. If this is not set, the .vend file checks if the distributor specified what directory to use as the cache with the registered option `--set-vend-cache path/to/cache` when bundling the Vend. If that is also unspecified, the default location ~/.vendcache is used. All subsequent times you execute the Vend, it will find the bootstrapped Vend in the cache and the project will be immediately executed from within the prepared virtual environment. **Note that the virtual environment used to install and execute the python project within the cache is only meant to be interacted with using the .vend file as an entrypoint. The script shebangs in its bin/ directory are not guaranteed to work if called directly.**

The advantage of using the  Vend format is that at the time of Vend generation (i.e. executing the `./pants vend` task) a distributors can specify and know exactly which platforms their projects will run on, and which interpreters are allowed/expected to execute them. No matter what combination of these variables is used across target computers, the same .vend file can be used to bootstrap a secure virtual environment and execute the distributed project within it.


## The Nitty-gritty Details

### Flow of Task Execution

The vend task is executed by passing it a single PythonBinary target. It performs the following steps:

1. Verify that a single target_root has been passed in, and that its type is PythonBinary. Identify all PythonLibrary and PythonRequirementLibrary targets in the graph.
2. Read the set of “bootstrap requirements” from pants.ini via the advanced option `--bootstrap-requirements`. The default value for this option in pants.ini is currently defined to be  `['setuptools==15.2',  'pip==6.1.1', 'virtualenv==13.0.3', and ‘pex==1.0.0’]`, but the actual version constraints are configurable per the requirements of future distributions. _Note that all four of these packages and only these four packages are supposed to be present in this list_. These are necessary for different steps in the Vend preparation process, and don’t necessarily end up in the final virtual environment.
3. Find the exact intersection of Python interpreter version and implementation constraints imposed by the PythonBinary and PythonLibrary targets. This step is discussed in great detail in the **Resolving Interpreter Constraints** section below.
4. Setup the Vend’s source directory structure (which will eventually be packaged into an executable zip file). This consists of the following components, each of which is explained in full detail in the **Inside binary_name.vend’s Source Directory** section below:
    * sources/
    * dep_wheels/
    * bootstap_wheels/
    * requirements.txt
    * piplog.log
    * bootstrap_data.json
    * \_\_main\_\_.py
    * bootstrap.py
    * run.sh
5. Copy all of the PythonLibrary targets’ source files into sources/.
6. Write all of the 3rd party dependency requirements into requirements.txt. We will use this and pip to download wheels for the 3rd party dependencies.
7. Examine the PythonBinary target and determine the exact platforms it will support. This information is taken directly from the platforms field in the PythonBinary object. If the string ‘current’ is present, it is replaced with the platform of the current computer: the distributor’s platform. If this field is blank, it is also assumed to be targeting the distributor’s platform.
8. Use Pip to download wheels for the full cross product of all 3rd party dependencies, desired platforms, and supported interpreters. I’ve written extensions to the `pip install --download` command that can be used to specify the exact platform you want to download a wheel for, and an exact interpreter you want a downloaded wheel to support. My pull request with these changes can be found here: https://github.com/pypa/pip/pull/2965. More information on this step can be found in the **Downloading Wheel Dependencies** section.
9. Use Pip to download the bootstrap dependency wheels necessary for preparing the Vend; place them in the bootstrap_wheels/ directory.
10. Write some data necessary for bootstrapping the Vend on target computers into bootstrap_data.json.
11. Add the scripts \_\_main\_\_.py, bootstrap.py, and run.sh to the vend directory structure. \_\_main\_\_.py is the entrypoint for the executable zip, and it calls the bootstrap.py module and run.sh.
12. Create an executable zip of the Vend directory structure (with the .vend extension) and place it in a subdirectory named dist/ within the builddir of the pants task.


### Inside binary_name.vend’s Source Directory

The Vend command produces an executable zip file of a directory structure used for installing and executing your python project. Peeking inside of this, we see the binary_name.vend directory with the following components:

_sources/_ : This subdirectory is itself a directory structure containing all of the project’s source code.

_dep_wheels/_ : This subdirectory holds all of the wheels of 3rd party dependencies that your source code relies on. If multiple wheel files of a single dependency are required (e.g. a version of a wheel built for macosx and another version built for linux) they will all be here.  This acts as the "universe" of wheels visible to the bootstrapper for the ultimate virtual environment, exposed via `--find-links` when using pip.

_bootstrap_wheels/_ : This subdirectory holds the four wheels necessary to prepare the Vend on target computers: pex, pip, setuptools, and virtualenv.

_requirements.txt_ : A list of all 3rd party dependencies for the vend in the expected format (e.g. `foo>=1.0`)

_bootstrap_data.json_ : This file is how the distributor computer that packaged the project conveys key information to the target computers that wish to bootstrap and run the project. It records the paths on the target computer within which the distributor specified to search for interpreters (more info on that in the **Controlling Target Interpreters** section below); it records all major.minor Python interpreter versions that the Vend supports; and it records all supported interpreter implementations, like Generic Python (which implies all implementations are supported), CPython, Pypy, etc.

_\_\_main\_\_.py_ : This script is executed every time a user executes the binary_name.vend file. The very first time it is executed, it bootstraps the whole Vend. This involves unzipping the wheel for virtualenv, creating a bootstrapping virtual environment called vendboot/, and installing Pex into it. Once Pex is installed, it runs bootstrap.py from inside this vendboot/ virtual environment. bootstrap.py requires Pex to find actual candidate Python interpreters given paths within which to search for them (more information in the **Controlling Target Interpreters** section below). bootstrap.py prepares the actual virtual environment that the project is executed out of in a subdirectory called venv/. Once __main__.py knows that venv/ is present in the Vend’s source directory, it calls run.sh -- the project’s entrypoint -- from within venv/. This happens immediately every subsequent time a user executes the .vend file.

_bootstrap.py_ : This python script is called by \_\_main\_\_.py. It is executed in the virtual environment vendboot/, where we know Pex has been installed. It reads the data stored in bootstrap_data.json, which was written by the distributing computer that executed the `./pants vend` task, and uses Pex to search through the allowed paths for an interpreter on the target computer to use to run the python project. It stops once it finds one that satisfies the supported interpreter versions and implementations, or it raises an `Exception` if none of the search paths have such an interpreter. Once it has identified an interpreter that satisfies all requirements, it uses that interpreter to build a new virtual environment: venv/. It then installs all of the contents of requirements.txt (3rd party dependencies, all of which were bundled in the Vend directory structure) into venv/, and places a .pth file into venv/’s site-packages/ directory that is pointing to the Vend’s sources/ directory. At this point, the Vend has been completely bootstrapped into venv/.

_run.sh_ : This script is called by \_\_main\_\_.py every time the binary_name.vend file is executed. It runs the python project’s entrypoint from within venv/.


### Controlling Target Interpreters

`./pants vend` has an advanced option registered called `--interpreter-search-paths`. This is meant to be prepopulated in pants.ini with a list of paths a distributor wants target computers to search through for an interpreter with which to use to install the virtual environment and run the project. Filling this like in the example below tells the vend task that you only want targets to use system Python 2.7 in particular, or any Brew Python version:
```python
interpreter_search_paths: [
    '/usr/bin/python2.7',
    '/usr/local/Cellar/python/',
  ]
```
We use the Pex classmethod `PythonInterpreter.find()` to examine these distributor-specified search paths on target computers and look for candidate interpreters. A current limitation of this classmethod is that it doesn’t recurse into subdirectories if you give it search paths outside of bin/ directories, so we manually search all subdirectories of a given search path one level at a time, recursively calling `PythonInterpreter.find()` until we retrieve an actual collection of candidate interpreters. Once a collection is found, each candidate in it is examined to see if it satisfies the constraints specified by the distributor. If one such interpreter is found then we stop and use it, else we continue searching more subdirectories. In the worst case scenario, a distributor can specify `/`  in the interpreter_search_paths to mean “search for every interpreter on the filesystem” with the implication that this one-time lookup might be very slow as a trade-off for guaranteeing you will examine the broadest collection of interpreter candidates necessary to locate a valid interpreter on your target computers.

Note that the heavy lifting here is performed by Pex’s PythonInterpreter class. It is for this reason that the bootstrap.py script must be run out of its own virtual environment vendboot/, where we know we have Pex preinstalled.


### Resolving Interpreter Constraints

We start by initializing the sets of valid interpreter versions and implementations to “all”. Here, “all” Python interpreter implementations is the set of all Python Tags defined in PEP 425: https://www.python.org/dev/peps/pep-0425/#python-tag
That is to say that the set of all python interpreter implementations is: `set(['py', 'cp', 'ip', 'pp', 'jy'])`

Additionally, “all” Python interpreter versions is a set of major.minor versions specified in pants.ini and registered as one of vend’s advanced options: `--all-py-versions`. In pants.ini under the `[vend]` section, all_py_versions is defined to be the list `['2.6', '2.7', '3.2', '3.3', '3.4',]` because these are the known interpreter versions Vend supports. If a distributor prefers to change this universe of versions (e.g. just ['2.7',], or ['2.7', '3.4']) this can be manually edited and specified here.

We then loop through all PythonLibrary targets as well as the PythonBinary root target. For each, we examine the `compatibility` field. If it’s empty, we assume the target supports all versions of all interpreters. If not, then we determine the total set of versions and the total set of implementations supported by the target, and we intersect these sets with the “all” sets we initialized. At this level, we are taking the logical AND of requirements between the PythonLibraries and PythonBinary.

Determining the total set of versions and implementations supported by a single Library or Binary is its own subproblem. Here, the compatibility field is defined in PythonTask as either a string or a set of strings. It is normalized to a set of strings, and then each string in the set (there might only be one) is taken to result in a set of valid interpreters and implementations for this Library or Binary. The union of each of these sets is taken, and this represents the whole set of versions and implementations that the Library or Binary supports. At this level, we are taking the logical OR of valid interpreter versions and implementations between strings for a single PythonLibrary or PythonBinary. In this way, each string is an option that a Library or Binary can support. For example, a PythonLibrary might have `constraints=[‘>=2.7,<3’, ‘>=3.4’]`. This is taken to mean that the PythonLibrary will run on all Python 2.7.x interpreters, and on Python3 interpreters 3.4.0 and more recent. The different strings in the list are taken to be different options, and therefore the union of the resulting sets `[‘2.7’]` and `[‘3.4’, ...,]` is taken. If an implementation is not specified (as in this example), the implementation is assumed to be generic Python (‘py’), which means “any implementation will suffice”. When an implementation is specified, it is placed before the boolean operator in any given constraint: `constraints=['CPython==2.7']`.

Finally, at the lowest level, each string is taken to be a comma-separated list of constraints. The logical AND of these constraints is taken to calculate the set of valid interpreter versions and implementations for a single string in the compatibility field. In the above example ‘>=2.7,<3’ was taken to be all Python interpreter versions >= 2.7 that are also < 3, which was simply `[‘2.7’]`. The same logic is applied to implementations. For example, `[‘Cpython>=2.7,<3’]` Is the logical AND of CPython and Generic Python. Because Generic Python is a “don’t care”, the intersection is calculated to be CPython -- or ‘cp’ in the normalized PEP425 form -- for this string.


### Downloading Wheel Dependencies

The vend task starts this step by examining the PythonBinary input, which has a `platforms` field. If this is empty, or if the string ‘current’ is present, then a string representing the platform of the current computer -- the distributor’s computer -- is used (e.g. ‘macosx_10_10_x86_64’).

Then vend prepares to use pip to download the full list of 3rd party dependencies for all desired platforms and all supported interpreters. We use the `pip install --download` command with the following additional options: `--quiet` to suppress unnecessary output, `-r requirements_path` to download from the requirements.txt file, `--no-index` to prevent pip from searching for wheels online in places like PyPI, and `--find-links=wheelhouse` to specify where to search instead.

Note that an important distinction about how pip is used here is that it doesn’t search PyPI for its wheels. PyPI doesn’t support linux wheels, for example, so searching there wouldn’t make sense in cases when a distributor wants his or her project to work on linux machines. Therefore, _a precondition for using the `./pants vend` task is to establish your universe of wheels in a wheelhouse directory_. We prefer this approach both for speed and determinism (i.e. a version bump on PyPI won't suddenly change resolution semantics without the maintained universe of wheels being explicitly updated). For more information on how we do this, see the **Establishing the Universe of Wheels** section below.

Next we loop through the desired platforms and the supported interpreter versions and make a call to `pip install --download` with all of these options specified for every such combination, recording the output. As stated in the **Flow of Task Execution** section above, I’ve written extensions to pip that add this support, and my pull request with these changes can be found here: https://github.com/pypa/pip/pull/2965. If the output is ever a value other than `pip.status_codes.SUCCESS`, then we prepare an error message that includes the names of the dependencies that could not be resolved and the platform/interpreter combinations for which their wheels could not be downloaded. Once we’ve tried all possible combinations, we raise an `Exception` and print all such combinations. It is the distributor’s job at this point to either produce a wheel for an unresolved dependency that satisfies the platform and interpreter, or decide to explicitly limit support for the flagged interpreter version, platform, or both. These limiting actions can be performed by going to the PythonBinary’s BUILD file and adjusting the `platforms` field or the `compatibility` field. An example of this is explored in the **A Wheel Dependency Case Study** section below.

After wheels have been downloaded that cover the full cross product of dependencies, desired platforms, and supported interpreter versions, we verify that each downloaded wheel has an implementation supported by the intersection of valid interpreter implementations. At this point we know we have wheels that cover the full intersection of supported python interpreter versions, and that they all are compatible with the set of supported python interpreter implementations.


### Establishing the Universe of Wheels

At Foursquare we exclusively use wheels for installing python libraries. Unfortunately, not all package maintainers distribute wheels, so we repackage their libraries before we redistribute them internally. At a high level we have a CI job building our desired 3rd party dependency wheels into a directory on our file server, which we sync into a directory called .wheelhouse/ at the root of our monorepo. This process has three distinct steps:

1. We wrote a script called wheelwright.sh that takes a requirements.txt file as input and creates a directory of wheels as output, with one wheel for each dependency ultimately resolved by pip, which might be a superset of the dependencies in the provided requirements.txt.
2. We have a CI job run on Jenkins that accepts a requirements.txt parameter and runs wheelwright.sh with it. We feed it the  requirements.txt file in our 3rdparty/python/ directory and have it run on both osx_10_9 and linux nodes, which are the two platforms we support. This is because the wheels built by wheelwright are specifically built for the current platform of the computer executing it, as opposed to being built for _any_ platform (due to how `pip install` and `pip wheel` work). The job finishes by copying all of the built wheels to a single directory on our file server, which becomes our wheelhouse.
3. We use `rsync` to keep a copy of the current wheelhouse in the .wheelhouse/ directory of our monorepo. This directory can be used by pip to build virtualenvs or by pants for building and running python targets.

We point pip at this .wheelhouse/ directory using the `--find-links` and `--no-index` options when we `pip install --download` the 3rd party dependencies. The vend task has an advanced option registered called `--wheelhouses`, which is meant to be populated with a path to a wheelhouse (or potentially several wheelhouses) by the distributor in pants.ini.

Most of the logic for preparing the wheelhouse happens in wheelwright.sh. It performs the following tasks:
1. Ensure the current computer has necessary external libraries installed and available for linking (e.g. postgresql).
2. Make a virtual environment scratch space, and install `wheel` and `delocate` into it.
3. Run `pip wheel` to build all of the desired wheels from requirements.txt. If some of your wheels depend on others (e.g. some of our wheels won’t build unless numpy is already installed), then start by manually installing those wheels into the scratch space.
4. On OSX machines, run `delocate` to relativize the built wheels. Don’t do this on Linux machines because the ABI is not well-defined.
5. Verify that all desired wheels have been properly packaged into the wheelhouse by calling `pip install -r requirements.txt` into a new empty virtualenv. If all of your wheels can be properly installed into this new virtualenv, then your wheelhouse is performing perfectly as a universe of wheels.

A copy of wheelwright.sh can be seen here for your reference: https://gist.github.com/patricklaw/32292c528b17f9eb73f9.


### A Wheel Dependency Case Study

A distributor might have a PythonBinary that depends on a PythonLibrary that has a 3rd party dependency called foo. In the distributor’s wheelhouse there might be two wheels for foo with names `foo-1.0-cp27-none-linux_x86_64.whl` and `foo-1.0-cp27-none-macosx_10_9_x86_64.whl`. **Note that these wheels only support a python interpreter with implementation Cpython and version 2.7**. Now let’s say that the PythonLibrary imposes no other constraints on the implementation (i.e. the compatibility field is either empty or omitted). Let’s say we have BUILD files of the form:
```python
python_binary(name='main',
  dependencies=[
    'bar/baz:baz',
  ],
  source='main.py',
  platforms=[
  	'linux_x86_64',
  	'macosx_10_9_x86_64',
  ],
  # No compatibility field => compatible with all interp versions and implementations
)
```
```python
python_library(name='baz',
  dependencies=[
  	'bar/3rdparty/python:foo',
  ],
  sources=globs('*.py'),
  # No compatibility field => compatible with all interp versions and implementations
)
```

Based on these PythonBinary and PythonLibrary definitions, the intersection of valid interpreter versions and implementations are both “all”. So we will try to download wheels for foo that run on all versions of Python (as defined in pants.ini) for both desired platforms. Of course, the only wheels we find support macosx_10_9_x86_64 on cp27 and linux_x86_64 on cp27. This results in the large error message seen here: https://gist.github.com/MathewJennings/75e1d4b448d93f11702c.

Essentially, every combination of interpreter and platform where the interpreter wasn’t 2.7 results in an error. This raises an `Exception` to reduce all ambiguity and enforce that the distributor is explicitly aware of exactly what interpreters and platforms the Vend of the project will support. The solution is to adjust the PythonBinary to include a compatibility field:

```python
python_binary(name='main',
  dependencies=[
    'bar/baz:baz',
  ],
  source='main.py',
  platforms=[
  	'linux_x86_64',
  	'macosx_10_9_x86_64',
  ],
  compatibility=[‘CPython==2.7’],
)
```

Now this project can be built into a Vend that can be distributed to both linux_x86_64 and macosx_10_9_x86_64 platforms (and all backwards compatible platforms) that are running CPython 2.7.


## Summary

The ./pants vend task is designed to be an alternate to Pex for developers using pants to build and distribute their python projects. It takes a PythonBinary as input and prepares all of the data necessary for distributing a project on as many different target environments as possible. It guarantees that the distributor is aware of and in control of this. The output is a .vend file which can be sent to many different target computers running on different platforms with different Python interpreters, where it can be executed directly. Using Vend, distributors can specify and guarantee at bundle time exactly what combinations of platforms and interpreters their projects support. It is designed to be a broad solution for distributors hoping to share their projects with potentially many different users each running environments potentially very different from each other.
