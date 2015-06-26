#!/usr/bin/env python

import argparse
import codecs
from plumbum import local
from plumbum.cmd import sudo, git, make
import multiprocessing
import os
import shutil
import stat
import subprocess
import sys

GIT_VERSION = 'v2.4.4'

guts_path = os.path.dirname(os.path.realpath(__file__))
gut_src_path = os.path.join(guts_path, 'gut')
gut_dist_path = os.path.join(guts_path, 'gut-dist')
gut_exe_path = os.path.join(gut_dist_path, 'bin/gut')

def ensure_build():
    if not os.path.exists(gut_dist_path):
        build()

def out(s):
    sys.stderr.write(s)
    sys.stderr.flush()

def rename_git_to_gut_recursive(root_path):
    def rename_git_to_gut(s):
        return s.replace('GIT', 'GUT').replace('Git', 'Gut').replace('git', 'gut')
    for root, dirs, files in os.walk(root_path):
        for filename in files:
            if filename.startswith('.git'):
                # don't touch .gitignores or .gitattributes files
                continue
            orig_path = os.path.join(root, filename)
            path = os.path.join(root, rename_git_to_gut(filename))
            if orig_path != path:
                # print('renaming file %s -> %s' % (orig_path, path))
                os.rename(orig_path, path)
            with codecs.open(path, 'r', 'utf-8') as fd:
                try:
                    orig_contents = fd.read()
                except UnicodeDecodeError:
                    # print('Could not read UTF-8 from %s' % (path,))
                    continue
            contents = rename_git_to_gut(orig_contents)
            if contents != orig_contents:
                # print('rewriting %s' % (path,))
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
                # print('renaming folder %s -> %s' % (orig_path, path))
                shutil.move(orig_path, path)
            dirs.append(folder)

def build():
    install_prefix = 'prefix=%s' % (gut_dist_path,)
    if sys.platform == 'darwin':
        local['brew']['install', 'libyaml']()
    else:
        sudo[local['apt-get']['install', 'gettext', 'libyaml-dev', 'curl', 'libcurl4-openssl-dev', 'libexpat1-dev', 'autoconf']]() #python-pip python-dev
        sudo[local['sysctl']['fs.inotify.max_user_watches=1048576']]()
    if not os.path.exists(gut_src_path):
        out('Cloning git... ')
        git['clone', 'https://github.com/git/git.git', gut_src_path]()
        out('done.\n')
    with local.cwd(gut_src_path):
        out('Updating git... ')
        git['fetch']()
        out('done.\nRewriting git to gut... ')
        sys.stdout.flush()
        git['reset', '--hard', GIT_VERSION]()
        git['clean', '-fd']()
        make[install_prefix, 'clean']()
        rename_git_to_gut_recursive(gut_src_path)
        out('done.\nBuilding gut... ')
        sys.stdout.flush()
        make[install_prefix, '-j', multiprocessing.cpu_count()]()
        make[install_prefix, 'install']()
        out('done.\nInstalled gut into %s.\n' % (gut_dist_path,))

def gut_rev_parse(commitish):
    return local[gut_exe_path]['rev-parse', commitish](retcode=None).strip()

def init(local_path):
    did_anything = False
    with local.cwd(local_path):
        gut = local[gut_exe_path]
        ensure_build()
        if not os.path.exists(os.path.join(local_path, '.gut')):
            out(gut['init']())
            did_anything = True
        head = gut_rev_parse('HEAD')
        if head == 'HEAD':
            out(gut['commit']['--allow-empty', '--message', 'Initial commit']())
            did_anything = True
    if not did_anything:
        print('Already initialized gut in %s' % (local_path,))

def sync(local_path, remote):
    init(local_path)
    with local.cwd(local_path):
        gut = local[gut_exe_path]
    # sync(...)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'build', 'sync'])
    # parser.add_argument('--verbose', '-v', action='count')
    peek_action = sys.argv[1] if len(sys.argv) > 1 else None
    if peek_action == 'init' or peek_action == 'sync':
        parser.add_argument('local')
    if peek_action == 'sync':
        parser.add_argument('remote')
    args = parser.parse_args()
    if args.action == 'init':
        init(os.path.abspath(args.local))
    elif args.action == 'build':
        build()
    else:
        sync(os.path.abspath(args.local), os.path.abspath(args.remote))

if __name__ == '__main__':
    main()
