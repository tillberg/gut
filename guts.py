#!/usr/bin/env python

import argparse
import codecs
import paramiko
from plumbum import local, SshMachine, FG
from plumbum.cmd import sudo, git, make
from plumbum.machines.paramiko_machine import ParamikoMachine
import multiprocessing
import os
import Queue
import re
import shutil
import socket
import stat
import sys
from threading import Thread

GIT_REPO_URL = 'https://github.com/git/git.git'
GIT_VERSION = 'v2.4.5'
GUTS_PATH = '~/.guts'
GUT_SRC_PATH = os.path.join(GUTS_PATH, 'gut-src')
GUT_DIST_PATH = os.path.join(GUTS_PATH, 'gut-dist')

threads = []
shutting_down = False

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

# def install_build_deps():
#     if sys.platform == 'darwin':
#         local['brew']['install', 'libyaml']()
#     else:
#         sudo[local['apt-get']['install', 'gettext', 'libyaml-dev', 'curl', 'libcurl4-openssl-dev', 'libexpat1-dev', 'autoconf']]() #python-pip python-dev
#         sudo[local['sysctl']['fs.inotify.max_user_watches=1048576']]()

def gut_prepare(context):
    guts_path = context.path(GUTS_PATH)
    gut_src_path = context.path(GUT_SRC_PATH)
    context['mkdir']['-p', guts_path]
    if not gut_src_path.exists():
        out('Cloning %s into %s...' % (GIT_REPO_URL, gut_src_path,))
        context['git']['clone', GIT_REPO_URL, gut_src_path]()
        out(' done.\n')
    with context.cwd(gut_src_path):
        if not context['git']['rev-parse', GIT_VERSION](retcode=None).strip():
            out('Updating git in order to upgrade to %s...' % (GIT_VERSION,))
            context['git']['fetch']()
            out(' done.\n')
        out('Checking out fresh copy of git %s...' % (GIT_VERSION,))
        context['git']['reset', '--hard', GIT_VERSION]()
        context['git']['clean', '-fd']()
        context['make']['clean']()
        out(' done.\nRewriting git to gut...')
        rename_git_to_gut_recursive('%s' % (gut_src_path,))
        out(' done.\n')

def gut_build(context):
    gut_src_path = context.path(GUT_SRC_PATH)
    gut_dist_path = context.path(GUT_DIST_PATH)
    install_prefix = 'prefix=%s' % (gut_dist_path,)
    with context.cwd(gut_src_path):
        parallelism = context['getconf']['_NPROCESSORS_ONLN']().strip()
        out('Building gut using up to %s processes...' % (parallelism,))
        context['make'][install_prefix, '-j', parallelism]()
        context['make'][install_prefix, 'install']()
        out(' done.\nInstalled gut into %s\n' % (gut_dist_path,))

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

def watch_for_changes(context, path, event_prefix, event_queue):
    def run():
        try:
            with context.cwd(path):
                watched_root = context['pwd']().strip()
                # try inotifywait first:
                if context['which']['inotifywait'](retcode=None):
                    # for OSX: context['fswatch']['./']
                    inotify_events = ['modify', 'attrib', 'move', 'create', 'delete']
                    watcher = context['inotifywait']['--monitor', '--recursive', '--format', '%w%f']
                    for event in inotify_events:
                        watcher = watcher['--event', event]
                    watcher = watcher['./']
                    watch_type = 'inotifywait'
                elif context['which']['fswatch'](retcode=None):
                    watcher = context['fswatch']['./']
                    watch_type = 'fswatch'
                else:
                    out('guts requires inotifywait or fswatch to be installed on both the local and remote hosts (missing on %s).\n' % (event_prefix,))
                    sys.exit(1)
                wd_prefix = ('%s:' % (context.host,)) if event_prefix == 'remote' else ''
                out('Using %s to listen for changes in %s%s\n' % (watch_type, wd_prefix, watched_root,))
                proc = watcher.popen()
                while not shutting_down:
                    line = proc.stdout.readline()
                    if line != '':
                        changed_path = line.rstrip()
                        changed_path = os.path.abspath(os.path.join(watched_root, changed_path))
                        rel_path = os.path.relpath(changed_path, watched_root)
                        # out('changed_path: ' + changed_path + '\n')
                        # out('watched_root: ' + watched_root + '\n')
                        # out('changed ' + changed_path + ' -> ' + rel_path + '\n')
                        event_queue.put((event_prefix, rel_path))
                    else:
                        break
        except socket.error:
            if not shutting_down:
                raise
        # print >> sys.stderr, 'watch_for_changes exiting'
    thread = Thread(target=run)
    thread.daemon = True
    thread.start()
    return thread

def shutdown():
    # out('SHUTTING DOWN\n')
    global shutting_down
    shutting_down = True
    joinable_threads = [t for t in threads if not t.isDaemon()]
    for thread in joinable_threads:
        thread.stop()
    for thread in joinable_threads:
        thread.join()
    # out('SHUTDOWN\n')
    sys.exit(0)

def sync(local_path, remote_host, remote_path, use_openssl=False):
    init(local_path)
    out('Syncing %s with %s:%s\n' % (local_path, remote_host, remote_path))
    if use_openssl:
        remote = SshMachine(remote_host)
    else:
        # XXX paramiko doesn't seem to successfully update my known_hosts file with this setting
        remote = ParamikoMachine(remote_host, missing_host_policy=paramiko.AutoAddPolicy())

    event_queue = Queue.Queue()
    threads.append(watch_for_changes(local, local_path, 'local', event_queue))
    threads.append(watch_for_changes(remote, remote_path, 'remote', event_queue))
    while True:
        recent_changes = False
        try:
            event = event_queue.get(True, 0.1 if recent_changes else 10000)
        except Queue.Empty:
            if recent_changes:
                out('Commit changes.\n')
                recent_changes = False
        except KeyboardInterrupt:
            shutdown()
            raise
        else:
            recent_changes = False
            system, path = event
            out('changed %s %s\n' % (system, path))

    rguts_path = remote.path(remote_path)
    # if not rguts_path.exist():

    # remote['stat']['.guts'] & FG
    # run(remote['which']['git'])
    # run(remote['which']['gut'])
    with local.cwd(local_path):
        gut = local[gut_exe_path]

    # sync(...)
    out('Sync exiting.\n')

def main():
    peek_action = sys.argv[1] if len(sys.argv) > 1 else None
    # parser.add_argument('--verbose', '-v', action='count')
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'build', 'sync', 'watch'])
    if peek_action == 'init' or peek_action == 'sync' or peek_action == 'watch':
        parser.add_argument('local')
    if peek_action == 'sync':
        parser.add_argument('remote')
    parser.add_argument('--openssl', action='store_true')
    args = parser.parse_args()
    if args.action == 'build':
        # gut_exe_path = os.path.join(gut_dist_path, 'bin/gut')
        gut_prepare(local)
        gut_build(local)
    else:
        local_path = args.local
        if args.action == 'init':
            init(local_path)
        elif args.action == 'watch':
            for line in iter_fs_watch(local, local_path):
                out(line + '\n')
        else:
            if ':' not in args.remote:
                parser.error('remote must include both the hostname and path, separated by a colon')
            remote_host, remote_path = args.remote.split(':', 1)
            # Since we start at the remote home directory by default, we can replace ~/ with ./
            remote_path = re.sub(r'^~/', './', remote_path)
            sync(local_path, remote_host, remote_path, use_openssl=args.openssl)

if __name__ == '__main__':
    main()
