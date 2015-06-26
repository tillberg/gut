#!/usr/bin/env python

import argparse
import codecs
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

def system(_args, cwd=None, pipe_stdout=True, pipe_stderr=True):
    if not cwd:
        raise Exception('You must always pass cwd to `system`')
    args = [str(arg) for arg in _args]
    def cmd_repr(_cmd):
        return os.path.basename(_cmd)
    def arg_repr(_arg):
        # this is not perfect, but it's good enough for logging purposes:
        return '"%s"' % (arg,) if ' ' in arg else arg
    line = '%s %s' % (cmd_repr(args[0]), ' '.join([arg_repr(arg) for arg in args[1:]]))
    print('> %s' % (line,))
    proc = subprocess.Popen(args, cwd=cwd, stdout=(None if pipe_stdout else subprocess.PIPE), stderr=(None if pipe_stderr else subprocess.PIPE))
    out, _ = proc.communicate()
    return (out.strip(), proc.returncode)

def gut_exec(cmd, args=[], cwd=None, quiet=False):
    if not isinstance(cmd, str):
        raise Exception('gut_exec requires string for first argument')
    return system([gut_exe_path] + [cmd] + args, cwd=cwd, pipe_stdout=False, pipe_stderr=(not quiet))

def build():
    install_prefix = 'prefix=%s' % (gut_dist_path,)
    if sys.platform == 'darwin':
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
    did_anything = False
    if not os.path.exists(os.path.join(local, '.gut')):
        gut_exec('init', cwd=local)
        did_anything = True
    head, code = gut_exec('rev-parse', ['HEAD'], cwd=local, quiet=True)
    if code:
        print('HEAD: %s (%s)' % (head, code))
        gut_exec('commit', ['--allow-empty', '--message', 'Initial commit'], cwd=local)
    # if not os.path.exists():
    #     pass
    if not did_anything:
        print('Already initialized gut in %s' % (local,))

def sync(local, remote):
    init(local)
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
