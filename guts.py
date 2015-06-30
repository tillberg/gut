#!/usr/bin/env python

import argparse
import codecs
import multiprocessing
import os
import Queue
import re
import shutil
import socket
import stat
import sys
from threading import Thread

import paramiko
from plumbum import local, SshMachine, FG
from plumbum.cmd import sudo, git, make
from plumbum.machines.paramiko_machine import ParamikoMachine
from termcolor import colored

GIT_REPO_URL = 'https://github.com/git/git.git'
GIT_VERSION = 'v2.4.5'
GUTS_PATH = '~/.guts'
GUT_SRC_PATH = os.path.join(GUTS_PATH, 'gut-src')
GUT_DIST_PATH = os.path.join(GUTS_PATH, 'gut-dist')
GUT_EXE_PATH = os.path.join(GUT_DIST_PATH, 'bin/gut')

threads = []
shutting_down = False

def out(s):
    sys.stderr.write(s)
    sys.stderr.flush()

def popen_fg_fix(cmd):
    # There's some sort of bug in plumbum that prevents `& FG` from working with remote sudo commands, I think?
    proc = cmd.popen()
    while True:
        line = proc.stdout.readline()
        if line != '':
            out(colored(line, 'grey', attrs=['bold']))
        else:
            break

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

def install_build_deps(context):
    out('Installing build dependencies...\n')
    if context['which']['apt-get'](retcode=None):
        popen_fg_fix(context['sudo'][context['apt-get']['install', '-y', 'gettext', 'libyaml-dev', 'libcurl4-openssl-dev', 'libexpat1-dev', 'autoconf', 'inotify-tools']]) #python-pip python-dev
        # sudo[context['sysctl']['fs.inotify.max_user_watches=1048576']]()
    else:
        context['brew']['install', 'libyaml', 'fswatch']()
    out('Done.\n')

def ensure_guts_folders(context):
    context['mkdir']['-p', context.path(GUT_SRC_PATH)]()
    context['mkdir']['-p', context.path(GUT_DIST_PATH)]()

def gut_prepare(context):
    ensure_guts_folders(context)
    gut_src_path = context.path(GUT_SRC_PATH)
    if not (gut_src_path / '.git').exists():
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
    install_build_deps(context)
    gut_src_path = context.path(GUT_SRC_PATH)
    gut_dist_path = context.path(GUT_DIST_PATH)
    install_prefix = 'prefix=%s' % (gut_dist_path,)
    with context.cwd(gut_src_path):
        parallelism = context['getconf']['_NPROCESSORS_ONLN']().strip()
        out('Building gut using up to %s processes...' % (parallelism,))
        context['make'][install_prefix, '-j', parallelism]()
        context['make'][install_prefix, '-j', parallelism]()
        context['make'][install_prefix, 'install']()
        out(' done.\nInstalled gut into %s\n' % (gut_dist_path,))

def rsync(src_context, src_path, dest_context, dest_path, excludes=[]):
    def get_path_str(context, path):
        return '%s%s/' % (context.host + ':' if context != local else '', context.path(path),)
    src_path_str = get_path_str(src_context, src_path)
    dest_path_str = get_path_str(dest_context, dest_path)
    out('rsyncing %s to %s ...' % (src_path_str, dest_path_str))
    rsync = local['rsync']['-a']
    for exclude in excludes:
        rsync = rsync['--exclude=%s' % (exclude,)]
    rsync[src_path_str, dest_path_str]()
    out(' done.\n')

def ensure_build(context):
    if not context.path(GUT_EXE_PATH).exists():
        out('Need to build gut on %s host.\n' % ('local' if context == local else 'remote',))
        ensure_guts_folders(context)
        gut_prepare(local) # <-- we always prepare gut source locally
        if context != local:
            rsync(local, GUT_SRC_PATH, context, GUT_SRC_PATH, excludes=['.git', 't'])
        gut_build(context)

def init(context, _sync_path):
    gut_exe_path = context.path(GUT_EXE_PATH)
    sync_path = context.path(_sync_path)
    did_anything = False
    with context.cwd(sync_path):
        gut = context[gut_exe_path]
        ensure_build()
        if not (sync_path / '.gut').exists():
            out(gut['init']())
            did_anything = True
        head = context[gut_exe_path]['rev-parse', 'HEAD'](retcode=None).strip()
        if head == 'HEAD':
            out(gut['commit']['--allow-empty', '--message', 'Initial commit']())
            did_anything = True
    if not did_anything:
        print('Already initialized gut in %s' % (sync_path,))

def watch_for_changes(context, path, event_prefix, event_queue):
    def run():
        try:
            with context.cwd(path):
                watched_root = context['pwd']().strip()
                watcher = None
                if context['which']['inotifywait'](retcode=None).strip():
                    inotify_events = ['modify', 'attrib', 'move', 'create', 'delete']
                    watcher = context['inotifywait']['--monitor', '--recursive', '--format', '%w%f']
                    for event in inotify_events:
                        watcher = watcher['--event', event]
                    watcher = watcher['./']
                    watch_type = 'inotifywait'
                elif context['which']['fswatch'](retcode=None).strip():
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
    # joinable_threads = [t for t in threads if not t.isDaemon()]
    # for thread in joinable_threads:
    #     thread.join()
    # out('SHUTDOWN\n')
    sys.exit(0)

def gut(context):
    return context[context.path(GUT_EXE_PATH)]

def get_tail_hash(context, sync_path):
    path = context.path(sync_path)
    if (path / '.gut').exists():
        with context.cwd(path):
            return gut(context)['rev-list', '--max-parents=0', 'HEAD']().strip()
    return None

def assert_folder_empty(context, _path):
    path = context.path(_path)
    if path.exists() and ((not path.isdir()) or len(path.list()) > 0):
        # If it exists, and it's not a directory or not an empty directory, then bail
        out('Refusing to auto-initialize %s on %s, as it is not an empty directory. Move or delete it manually first.\n' % (
            path, 'local' if context == local else 'remote'))
        shutdown()

def sync(local_path, remote_host, remote_path, use_openssl=False):
    out('Syncing %s with %s:%s\n' % (local_path, remote_host, remote_path))
    if use_openssl:
        remote = SshMachine(remote_host)
    else:
        # XXX paramiko doesn't seem to successfully update my known_hosts file with this setting
        remote = ParamikoMachine(remote_host, missing_host_policy=paramiko.AutoAddPolicy())
    ensure_build(local)
    ensure_build(remote)

    local_tail_hash = get_tail_hash(local, local_path)
    remote_tail_hash = get_tail_hash(remote, remote_path)
    out('local tail: [%s]\n' % (local_tail_hash,))
    out('remote tail: [%s]\n' % (remote_tail_hash,))
    if local_tail_hash and not remote_tail_hash:
        assert_folder_empty(remote, remote_path)
        out('Initializing remote folder from local gut repo...\n')
    elif remote_tail_hash and not local_tail_hash:
        assert_folder_empty(local, local_path)
        out('Initializing local folder from remote gut repo...\n')
    elif not local_tail_hash and not remote_tail_hash:
        assert_folder_empty(remote, remote_path)
        assert_folder_empty(local, local_path)
        out('Initializing both local and remote gut repos...\n')
    elif local_tail_hash == remote_tail_hash:
        out('Detected compatible gut repos. Yay.\n')
    else:
        out('Cannot sync incompatible gut repos. Local initial commit hash: [%s]; remote initial commit hash: [%s]\n' % (local_tail_hash, remote_tail_hash))
        shutdown()


    return
    # init(local, local_path)
    # init(remote, remote_path)

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
    # with local.cwd(local_path):
    #     gut = local[gut_exe_path]

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
