#!/usr/bin/env python

import argparse
import os
import subprocess

import lib.build_gut

verbose = None
guts_path = os.path.dirname(os.path.realpath(__file__))
gut_src_path = os.path.join(gut_path, 'gut')
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

def system(s, cwd=None):
    for line in s.strip().split('\n'):
        print('> %s' % (line,))
        subprocess.call(line, cwd=cwd, shell=True)

def build():
    if is_osx:
        system('brew install libyaml')
    else:
        system('sudo apt-get install gettext libyaml-dev curl libcurl4-openssl-dev libexpat1-dev autoconf') #python-pip python-dev
        system('sudo sysctl fs.inotify.max_user_watches=1048576')

    #echo 'kern.maxfiles=20480' | sudo tee -a /etc/sysctl.conf
    #echo -e 'limit maxfiles 8192 20480\nlimit maxproc 1000 2000' | sudo tee -a /etc/launchd.conf
    #echo 'ulimit -n 4096' | sudo tee -a /etc/profile

    #sudo pip install -r requirements.txt
    if not os.path.exists(gut_src_path):
        system('git clone https://github.com/git/git.git %s' % (gut_src_path,))
    else:
        system('git fetch', gut_src_path)
    system('git reset --hard %s' % (GIT_VERSION,), gut_src_path)
    system('git clean -fd', gut_src_path)
    system('make prefix=%s clean' % (gut_dist_path,), gut_src_path)

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

    system('''
    make prefix=%s -j %s
    make prefix=%s install
    ''' % (gut_dist_path, multiprocessing.cpu_count(), gut_dist_path), gut_src_path)

def init(local):
    ensure_build()
    if not os.path.exists(os.path.join(local, '.gut')):
        system

def sync(local, remote):
    init(local)
    # sync(...)

def main():
    global verbose
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'build', 'sync'])
    parser.add_argument('--verbose', '-v', action='count')
    parser.add_argument('local', nargs='?')
    parser.add_argument('remote', nargs='?')
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
