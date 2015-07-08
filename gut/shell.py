#!/usr/bin/env python

import argparse
import os
import Queue
import sys
import time

import plumbum
import patch_plumbum; patch_plumbum.patch_darwin_stat()

import config
import terminal as term
from terminal import shutdown, shutting_down, out, out_dim, dim, quote, color_error, color_path, color_host, color_host_path, color_commit, run_daemon_thread
import deps
import gut
import gut_build
import util

def ensure_build(context):
    desired_git_version = config.GIT_WIN_VERSION if context._is_windows else config.GIT_VERSION
    if not gut.exe_path(context).exists() or desired_git_version.lstrip('v') not in gut.get_version(context):
        out(dim('Need to build gut on ') + context._name_ansi + dim('.\n'))
        gut_build.ensure_gut_folders(context)
        gut_build.prepare(context)
        if context != plumbum.local:
            # If we're building remotely, rsync the prepared source to the remote host
            build_path = config.GUT_SRC_TMP_PATH
            util.rsync(plumbum.local, config.GUT_SRC_PATH, context, build_path, excludes=['.git', 't'])
        else:
            build_path = config.GUT_WIN_SRC_PATH if context._is_windows else config.GUT_SRC_PATH
        gut_build.build(context, build_path)
        out_dim('Cleaning up...')
        gut_build.unprepare(context)
        if context != plumbum.local:
            context['rm']['-r', context.path(config.GUT_SRC_TMP_PATH)]()
        out_dim(' done.\n')
        return True
    return False

def get_tail_hash(context, sync_path):
    """
    Query the gut repo for the initial commit to the repo. We use this to determine if two gut repos are compatibile.
    http://stackoverflow.com/questions/1006775/how-to-reference-the-initial-commit
    """
    path = context.path(sync_path)
    if (path / '.gut').exists():
        with context.cwd(path):
            return gut.gut(context)['rev-list', '--max-parents=0', 'HEAD'](retcode=None).strip() or None
    return None

def assert_folder_empty(context, _path):
    path = context.path(_path)
    if path.exists() and ((not path.isdir()) or len(path.list()) > 0):
        # If it exists, and it's not a directory or not an empty directory, then bail
        out(color_error('Refusing to initialize ') + color_path(path) + color_error(' on ') + context._name_ansi)
        out(color_error(' as it is not an empty directory. Move or delete it manually first.\n'))
        shutdown()

def init_context(context, sync_path=None, host=None, user=None):
    context._name = host or 'localhost'
    context._name_ansi = color_host(context._name)
    context._is_local = not host
    context._is_osx = context.uname == 'Darwin'
    context._is_linux = context.uname == 'Linux'
    context._is_windows = context.uname == 'Windows'
    context._ssh_address = (('%s@' % (user,) if user else '') + host) if host else ''
    context._sync_path = color_host_path(context, sync_path)
    if context._is_osx:
        # Because .profile vs .bash_profile vs .bashrc is probably not right, and this is where homebrew installs stuff, by default
        context.env['PATH'] = context.env['PATH'] + ':/usr/local/bin'
    if context._is_windows:
        context.env.path.append(context.path(config.INOTIFY_WIN_PATH))

def sync(local, local_path, remote_user, remote_host, remote_path, use_openssl=False, keyfile=None):
    def run():
        if use_openssl:
            remote = plumbum.SshMachine(
                remote_host,
                user=remote_user,
                keyfile=keyfile)
        else:
            # Import paramiko late so that one could use `--use-openssl` without even installing paramiko
            import paramiko
            from plumbum.machines.paramiko_machine import ParamikoMachine
            # XXX paramiko doesn't seem to successfully update my known_hosts file with this setting
            remote = ParamikoMachine(
                remote_host,
                user=remote_user,
                keyfile=keyfile,
                missing_host_policy=paramiko.AutoAddPolicy())
        init_context(local, sync_path=local_path)
        init_context(remote, sync_path=remote_path, host=remote_host, user=remote_user)

        out(dim('Syncing ') + local._sync_path + dim(' with ') + remote._sync_path + '\n')

        ensure_build(local)
        ensure_build(remote)

        local_tail_hash = get_tail_hash(local, local_path)
        remote_tail_hash = get_tail_hash(remote, remote_path)

        util.start_ssh_tunnel(local, remote)

        def cross_init(src_context, src_path, dest_context, dest_path):
            gut.run_daemon(src_context, src_path)
            gut.init(dest_context, dest_path)
            gut.setup_origin(dest_context, dest_path)
            import time
            time.sleep(2) # Give the gut-daemon and SSH tunnel a moment to start up
            gut.pull(dest_context, dest_path)
            gut.run_daemon(dest_context, dest_path)

        # Do we need to initialize local and/or remote gut repos?
        if not local_tail_hash or local_tail_hash != remote_tail_hash:
            out(dim('Local gut repo base commit: [') + color_commit(local_tail_hash) + dim(']\n'))
            out(dim('Remote gut repo base commit: [') + color_commit(remote_tail_hash) + dim(']\n'))
            if local_tail_hash and not remote_tail_hash:
                assert_folder_empty(remote, remote_path)
                out_dim('Initializing remote repo from local repo...\n')
                cross_init(local, local_path, remote, remote_path)
            elif remote_tail_hash and not local_tail_hash:
                assert_folder_empty(local, local_path)
                out_dim('Initializing local folder from remote gut repo...\n')
                cross_init(remote, remote_path, local, local_path)
            elif not local_tail_hash and not remote_tail_hash:
                assert_folder_empty(remote, remote_path)
                assert_folder_empty(local, local_path)
                out_dim('Initializing both local and remote gut repos...\n')
                out_dim('Initializing local repo first...\n')
                gut.init(local, local_path)
                gut.ensure_initial_commit(local, local_path)
                out_dim('Initializing remote repo from local repo...\n')
                cross_init(local, local_path, remote, remote_path)
            else:
                out(color_error('Cannot sync incompatible gut repos:\n'))
                out(color_error('Local initial commit hash: [') + color_commit(local_tail_hash) + color_error(']\n'))
                out(color_error('Remote initial commit hash: [') + color_commit(remote_tail_hash) + color_error(']\n'))
                shutdown()
        else:
            gut.run_daemon(local, local_path)
            gut.run_daemon(remote, remote_path)
            # XXX The gut daemons are not necessarily listening yet, so this could result in races with commit_and_update calls below

        gut.setup_origin(local, local_path)
        gut.setup_origin(remote, remote_path)

        def commit_and_update(src_system, update_untracked=False):
            if src_system == 'local':
                src_context = local
                src_path = local_path
                dest_context = remote
                dest_path = remote_path
                dest_system = 'remote'
            else:
                src_context = remote
                src_path = remote_path
                dest_context = local
                dest_path = local_path
                dest_system = 'local'
            if gut.commit(src_context, src_path, update_untracked=update_untracked):
                gut.pull(dest_context, dest_path)

        event_queue = Queue.Queue()
        util.watch_for_changes(local, local_path, 'local', event_queue)
        util.watch_for_changes(remote, remote_path, 'remote', event_queue)
        # The filesystem watchers are not necessarily listening to all updates yet, so we could miss file changes that occur between the
        # commit_and_update calls below and the time that the filesystem watches are attached.

        commit_and_update('remote', update_untracked=True)
        commit_and_update('local', update_untracked=True)
        gut.pull(remote, remote_path)
        gut.pull(local, local_path)

        changed = set()
        changed_ignore = set()
        while not shutting_down():
            try:
                event = event_queue.get(True, 0.1 if changed else 10000)
            except Queue.Empty:
                for system in changed:
                    commit_and_update(system, update_untracked=(system in changed_ignore))
                changed.clear()
                changed_ignore.clear()
            else:
                system, path = event
                # Ignore events inside the .gut folder; these should also be filtered out in inotifywait/fswatch/etc if possible
                path_parts = path.split(os.sep)
                if not '.gut' in path_parts:
                    changed.add(system)
                    if path_parts[-1] == '.gutignore':
                        changed_ignore.add(system)
                        # out('changed_ignore %s on %s\n' % (path, system))
                    # else:
                    #     out('changed %s %s\n' % (system, path))
                # else:
                #     out('ignoring changed %s %s\n' % (system, path))
    run_daemon_thread(run)
    while not shutting_down():
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            out(dim('\nSIGINT received. Shutting down...'))
            shutdown(exit=False)

def main():
    action = len(sys.argv) >= 2 and sys.argv[1]
    if action in config.ALL_GUT_COMMANDS:
        gut_exe_path = gut.exe_path(plumbum.local)
        # Build gut if needed
        if not plumbum.local.path(config.GUT_EXE_PATH).exists():
            local = plumbum.local
            init_context(local)
            ensure_build(local)
        os.execv(unicode(gut_exe_path), [unicode(gut_exe_path)] + sys.argv[1:])
    else:
        local = plumbum.local
        init_context(local)
        parser = argparse.ArgumentParser()
        parser.add_argument('action', choices=['build', 'sync'])
        parser.add_argument('--install-deps', action='store_true')
        parser.add_argument('--no-color', action='store_true')
        def parse_args():
            args = parser.parse_args()
            deps.auto_install_deps = args.install_deps
            if args.no_color:
                term.disable_color()
            return args
        if action == 'build':
            args = parse_args()
            if not ensure_build(local):
                out(dim('gut ') + config.GIT_VERSION + dim(' has already been built.\n'))
        else:
            parser.add_argument('local')
            parser.add_argument('remote')
            parser.add_argument('--use-openssl', action='store_true')
            parser.add_argument('--identity', '-i')
            parser.add_argument('--dev', action='store_true')
            # parser.add_argument('--verbose', '-v', action='count')
            args = parse_args()
            local_path = args.local
            if ':' not in args.remote:
                parser.error('remote must include both the hostname and path, separated by a colon')
            if args.dev:
                util.restart_on_change(os.path.abspath(__file__))
            remote_addr, remote_path = args.remote.split(':', 1)
            remote_user, remote_host = remote_addr.rsplit('@', 2) if '@' in remote_addr else (None, remote_addr)
            sync(local, local_path, remote_user, remote_host, remote_path, use_openssl=args.use_openssl, keyfile=args.identity)

if __name__ == '__main__':
    main()
