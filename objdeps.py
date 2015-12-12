"""
Utility for analysis dependencies between object files.
"""

from os import path
import argparse
import collections
import glob
import shelve
import subprocess

from graphviz import Digraph


_Library = collections.namedtuple('_Library', ['name', 'defined', 'undefined',
                                               'dependencies', 'clients'])


def _make_library(name, defined, undefined):
    return _Library(name, defined, undefined, set(), set())


def _run(command):
    pipe = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    return pipe.stdout

_GET_DEFINED_SYMBOLS_CMD = (r'nm --defined-only -C --format=posix {lib}'
                            r'| grep -v "^\({lib}\|vtable\|std\|boost\|__gnu_cxx\|typeinfo\)"'
                            r'| sed "s/\(.*\) [^ ]* [^ ]* [^ ]*\$/\1/" | sort | uniq')

_GET_UNDEFINED_SYMBOLS_CMD = (r'nm -uC --format=posix {lib}'
                              r'| grep -v "^\({lib}\|vtable\|std\|boost\|__gnu_cxx\|typeinfo\)"'
                              r'| sed "s/\(.*\) U *\$/\1/" | sort | uniq')


def _parse_lib(lib):
    defined = set(_run(_GET_DEFINED_SYMBOLS_CMD.format(lib=lib)))
    undefined = set(_run(_GET_UNDEFINED_SYMBOLS_CMD.format(lib=lib)))
    return _make_library(path.basename(lib), defined, undefined)


def _update_dependencies(target, libs):
    for lib in libs:
        if target.name == lib.name:
            continue

        if target.undefined.intersection(lib.defined):
            target.dependencies.add(lib.name)


def _init_dependencies(libs):
    for lib in libs:
        _update_dependencies(lib, libs)


def _update_clients(target, libs):
    for lib in libs:
        if target.name == lib.name:
            continue

        if target.name in lib.dependencies:
            target.clients.add(lib.name)


def _init_clients(libs):
    for lib in libs:
        _update_clients(lib, libs)


def _make_graph(libs):
    graph = Digraph()
    for lib in libs:
        graph.node(lib.name, weight=str(len(lib.dependencies)))

    for lib in libs:
        for dependency in lib.dependencies:
            graph.edge(lib.name, dependency)

    return graph


def _find_dependencies_intersection(target, libs):
    clients_count = 0
    deps_intersection = set()
    for lib in libs:
        if lib.name in target.clients:
            if not deps_intersection:
                deps_intersection = lib.dependencies
            else:
                deps_intersection = deps_intersection.intersection(lib.dependencies)
            clients_count += 1
    return (clients_count, deps_intersection)


def _main():
    parser = argparse.ArgumentParser(description='Analysis of obj files dependencies.')
    parser.add_argument('--make-db', action='store_true', default=False)
    parser.add_argument('--list-db', action='store_true', default=False)
    parser.add_argument('--print-statistics', action='store_true', default=False)
    parser.add_argument('--make-dot', action='store_true', default=False)
    parser.add_argument('--db', default='symbols.db')
    parser.add_argument('--dir')
    parser.add_argument('--libs', nargs='+')
    parser.add_argument('--exclude-libs', nargs='+')

    args = parser.parse_args()

    if args.make_db:
        if args.dir:
            if args.libs:
                libs = [path.join(args.dir, l) for l in args.libs]
            else:
                libs = glob.glob(args.dir + '/*.lib')
        else:
            libs = args.libs

        if args.exclude_libs:
            libs = [l for l in libs if path.basename(l) not in args.exclude_libs]

        print('Next libs will be parsed:\n{}'.format(libs))

        libs = [_parse_lib(l) for l in libs]
        _init_dependencies(libs)
        _init_clients(libs)
        with shelve.open(args.db) as data:
            data['libs'] = libs
    elif args.list_db:
        with shelve.open(args.db) as data:
            pattern = '{}:\n' + '  {}\n' * 2
            for lib in data['libs']:
                print(pattern.format(lib.name, lib.dependencies, lib.clients))
    elif args.print_statistics:
        with shelve.open(args.db) as data:
            pattern = '\t'.join(['{:60}'] + ['{:5}'] * 4)
            print(pattern.format('name', 'defined', 'undefined',
                                 'dependencies', 'clients'))
            for lib in data['libs']:
                print(pattern.format(lib.name, str(len(lib.defined)), str(len(lib.undefined)),
                                     str(len(lib.dependencies)), str(len(lib.clients))))
    elif args.make_dot:
        with shelve.open(args.db) as data:
            graph = _make_graph(data['libs'])
            graph.save(args.db + '.dot')


_main()
