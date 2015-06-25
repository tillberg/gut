#!/usr/bin/env python

import argparse
import os
import subprocess

import lib.build_gut

verbose = None
guts_path = os.path.dirname(os.path.realpath(__file__))
gut_src_path = os.path.join(guts_path, 'gut')
gut_dist_path = os.path.join(guts_path, 'gut-dist')

def ensure_build():
    if not os.path.exists(gut_dist_path):
        build()

import codecs
import multiprocessing
import os
import shutil
import stat
import subprocess
from sys import platform as _platform
is_osx = _platform == 'darwin'

GIT_VERSION = 'v2.4.4'

def system(_args, cwd=None):
    args = [str(arg) for arg in _args]
    def arg_repr(_arg):
        # this is not perfect, but it's good enough for logging purposes:
        return '"%s"' % (arg,) if ' ' in arg else arg
    line = ' '.join([arg_repr(arg) for arg in args])
    print('> %s' % (line,))
    subprocess.call(args, cwd=cwd)

def build():
    install_prefix = 'prefix=%s' % (gut_dist_path,)
    if is_osx:
        system(['brew', 'install', 'libyaml'])
    else:
        system(['sudo', 'apt-get', 'install', 'gettext', 'libyaml-dev', 'curl', 'libcurl4-openssl-dev', 'libexpat1-dev', 'autoconf']) #python-pip python-dev
        system(['sudo', 'sysctl', 'fs.inotify.max_user_watches=1048576'])
    if not os.path.exists(gut_src_path):
        system(['git', 'clone', 'https://github.com/git/git.git'], cwd=gut_src_path)
    else:
        system(['git', 'fetch'], cwd=gut_src_path)
    system(['git', 'reset', '--hard', GIT_VERSION], cwd=gut_src_path)
    system(['git', 'clean', '-fd'], cwd=gut_src_path)
    system(['make', install_prefix, 'clean'], cwd=gut_src_path)
    def rename_git_to_gut(s):
        return s.replace('GIT', 'GUT').replace('Git', 'Gut').replace('git', 'gut')

    for root, dirs, files in os.walk(gut_src_path):
        for filename in files:
            if filename.startswith('.git'):
                # don't touch .gitignores or .gitattributes files
                continue
            orig_path = os.path.join(root, filename)
            path = os.path.join(root, rename_git_to_gut(filename))
            if orig_path != path:
                print('renaming file %s -> %s' % (orig_path, path))
                os.rename(orig_path, path)
            with codecs.open(path, 'r', 'utf-8') as fd:
                try:
                    orig_contents = fd.read()
                except UnicodeDecodeError:
                    # print('Could not read UTF-8 from %s' % (path,))
                    continue
            contents = rename_git_to_gut(orig_contents)
            if contents != orig_contents:
                print('rewriting %s' % (path,))
                # Force read-only files to be writable
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWRITE)
                with codecs.open(path, 'w', 'utf-8') as fd:
                    fd.write(contents)
        orig_dirs = tuple(dirs)
        del dirs[:]
        for folder in orig_dirs:
            if folder == '.git':
                # don't recurse into .git
                continue
            orig_path = os.path.join(root, folder)
            folder = rename_git_to_gut(folder)
            path = os.path.join(root, folder)
            if orig_path != path:
                print('renaming folder %s -> %s' % (orig_path, path))
                shutil.move(orig_path, path)
            dirs.append(folder)
    system(['make', install_prefix, '-j', multiprocessing.cpu_count()], cwd=gut_src_path)
    system(['make', install_prefix, 'install'], cwd=gut_src_path)

def init(local):
    ensure_build()
    if not os.path.exists(os.path.join(local, '.gut')):
        system(['gut', 'init'], cwd=local)

def sync(local, remote):
    init(local)
    # sync(...)

def main():
    global verbose
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'build', 'sync'])
    args = parser.parse_args()
    parser.add_argument('--verbose', '-v', action='count')
    if args.action == 'init' or args.action == 'sync':
        parser.add_argument('local')
    if args.action == 'sync':
        parser.add_argument('remote')
    args = parser.parse_args()
    verbose = args.verbose != None
    if args.action == 'init':
        init(args.local)
    elif args.action == 'build':
        build()
    else:
        sync(args.local, args.remote)

if __name__ == '__main__':
    main()
