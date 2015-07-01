#!/usr/bin/env python

import argparse
import codecs
import os
import Queue
import re
import shutil
import stat
import sys
import threading

import plumbum

GIT_REPO_URL = 'https://github.com/git/git.git'
GIT_VERSION = 'v2.4.5'
GUT_PATH = '~/.gut'
GUT_SRC_PATH = os.path.join(GUT_PATH, 'gut-src')
GUT_DIST_PATH = os.path.join(GUT_PATH, 'gut-build')
GUT_EXE_PATH = os.path.join(GUT_DIST_PATH, 'bin/gut')

GUT_HASH_DISPLAY_CHARS = 10
GUTD_BIND_PORT = 34924
GUTD_CONNECT_PORT = 34925

# Ignore files that are probably transient by default
# You can add/remove additional globs to both the root .gutignore and to
# any other .gutignore file in the repo hierarchy.
DEFAULT_GUTIGNORE = '''
# Added by `gut sync` during repo init:
*.lock
.#*
'''.lstrip()

_shutting_down = False
_shutting_down_lock = threading.Lock()
active_pidfiles = []

def shutting_down():
    with _shutting_down_lock:
        return _shutting_down

def shutdown(exit=True):
    with _shutting_down_lock:
        global _shutting_down
        _shutting_down = True
    try:
        if active_pidfiles:
            out('\n')
        # out_dim('Shutting down sub-processes...\n')
        for context, process_name in active_pidfiles:
            out_dim('Shutting down %s on %s...' % (process_name, context._name))
            retries = 3
            while True:
                try:
                    kill_via_pidfile(context, process_name)
                except Exception as ex:
                    retries -= 1
                    if retries <= 0:
                        out(color_error(' failed: "%s".\n' % (ex,)))
                        break
                    import time
                    time.sleep(1)
                else:
                    out_dim(' done.\n')
                    break
    except KeyboardInterrupt:
        pass
    if exit:
        sys.exit(1)

def ansi(num):
    return '\033[%sm' % (num,)

RE_ANSI = re.compile('\033\[\d*m')
ANSI_RESET_ALL = ansi('')
ANSI_RESET_COLOR = ansi(39)
ANSI_DIM = ansi(2)
ANSI_COLORS = {'grey': 30, 'red': 31, 'green': 32, 'yellow': 33, 'blue': 34, 'magenta': 35, 'cyan': 36, 'white': 37}

def colored(color):
    def _colored(text):
        return ansi(ANSI_COLORS[color]) + unicode(text) + ANSI_RESET_COLOR
    return _colored
color_path = colored('blue')
color_host = colored('yellow')
color_commit = colored('green')
color_error = colored('red')

def dim(text):
    return ANSI_DIM + unicode(text) + ANSI_RESET_ALL

def color_host_path(context, path):
    return (context._name + dim(':') if context != plumbum.local else '') + color_path(context.path(path))

def out(text):
    sys.stderr.write(text)
    sys.stderr.flush()

def out_dim(text):
    out(dim(text))

def quote(context, text):
    for line in text.strip().split('\n'):
        # Avoid outputting lines that only contain control characters and whitespace
        if RE_ANSI.sub('', line).strip():
            out(dim('[') + context._name + dim('] ') + line + '\n')

def rename_git_to_gut_recursive(root_path):
    def rename_git_to_gut(s):
        return s.replace('GIT', 'GUT').replace('Git', 'Gut').replace('git', 'gut')
    for root, dirs, files in os.walk(root_path):
        for orig_filename in files:
            if orig_filename.startswith('.git'):
                # don't touch .gitignores or .gitattributes files
                continue
            orig_path = os.path.join(root, orig_filename)
            filename = rename_git_to_gut(orig_filename)
            path = os.path.join(root, filename)
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
            if filename == 'read-cache.c':
                # This is a special case super-optimized string parse for the 'i' in 'git':
                contents = contents.replace("rest[1] != 'i' && rest[1] != 'I'", "rest[1] != 'u' && rest[1] != 'U'")
            if filename == 'GUT-VERSION-GEN':
                # GUT-VERSION-GEN attempts to use `git` to look at the git repo's history in order to determine the version string.
                # This prevents gut-gui/GUT-VERSION-GEN from calling `gut` and causing `gut_proxy` from recursively building `gut` in an infinite loop.
                contents = contents.replace('gut ', 'git ')
            if contents != orig_contents:
                # print('rewriting %s' % (path,))
                # Force read-only files to be writable so that we can modify them
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
    # XXX This ought to either be moved to a README or be made properly interactive.
    out_dim('Installing build dependencies...\n')
    if context['which']['apt-get'](retcode=None):
        quote(context, context['sudo'][context['apt-get']['install', '-y', 'gettext', 'libyaml-dev', 'libcurl4-openssl-dev', 'libexpat1-dev', 'autoconf', 'inotify-tools', 'autossh']]())
        # sudo[context['sysctl']['fs.inotify.max_user_watches=1048576']]()
    else:
        quote(context, context['brew']['install', 'libyaml', 'fswatch', 'autossh']())
    out_dim('Done.\n')

def ensure_gut_folders(context):
    context['mkdir']['-p', context.path(GUT_SRC_PATH)]()
    context['mkdir']['-p', context.path(GUT_DIST_PATH)]()

def gut_prepare(context):
    ensure_gut_folders(context)
    gut_src_path = context.path(GUT_SRC_PATH)
    if not (gut_src_path / '.git').exists():
        out(dim('Cloning ') + GIT_REPO_URL + dim(' into ') + color_path(gut_src_path) + dim('...'))
        context['git']['clone', GIT_REPO_URL, gut_src_path]()
        out_dim(' done.\n')
    with context.cwd(gut_src_path):
        if not context['git']['rev-parse', GIT_VERSION](retcode=None).strip():
            out(dim('Updating git in order to upgrade to ') + GIT_VERSION + dim('...'))
            context['git']['fetch']()
            out_dim(' done.\n')
        out(dim('Checking out fresh copy of git ') + GIT_VERSION + dim('...'))
        context['git']['reset', '--hard', GIT_VERSION]()
        context['git']['clean', '-fd']()
        context['make']['clean']()
        out_dim(' done.\nRewriting git to gut...')
        rename_git_to_gut_recursive('%s' % (gut_src_path,))
        out_dim(' done.\n')

def gut_build(context):
    install_build_deps(context)
    gut_src_path = context.path(GUT_SRC_PATH)
    gut_dist_path = context.path(GUT_DIST_PATH)
    install_prefix = 'prefix=%s' % (gut_dist_path,)
    with context.cwd(gut_src_path):
        parallelism = context['getconf']['_NPROCESSORS_ONLN']().strip()
        out(dim('Building gut using up to ') + parallelism + dim(' processes...'))
        context['make'][install_prefix, '-j', parallelism]()
        out(dim(' installing to ') + color_path(gut_dist_path) + dim('...'))
        context['make'][install_prefix, 'install']()
        out(dim(' done.\n'))

def gut_rev_parse_head(context):
    return gut(context)['rev-parse', 'HEAD'](retcode=None).strip() or None

def rsync(src_context, src_path, dest_context, dest_path, excludes=[]):
    def get_path_str(context, path):
        return '%s%s%s/' % (context._ssh_address, ':' if context._ssh_address else '', context.path(path),)
    src_path_str = get_path_str(src_context, src_path)
    dest_path_str = get_path_str(dest_context, dest_path)
    out(dim('rsyncing ') + color_host_path(src_context, src_path) + dim(' to ') + color_host_path(dest_context, dest_path) + dim('...'))
    dest_context['mkdir']['-p', dest_context.path(dest_path)]()
    rsync = plumbum.local['rsync']['-a']
    for exclude in excludes:
        rsync = rsync['--exclude=%s' % (exclude,)]
    rsync[src_path_str, dest_path_str]()
    out_dim(' done.\n')

def rsync_gut(src_context, src_path, dest_context, dest_path):
    # rsync just the .gut folder, then reset --hard the destination to the HEAD of the source
    # XXX This really ought to be done via starting up gut-daemon on the other host and then doing a gut-clone instead of relying on rsync.
    rsync(src_context, os.path.join(src_path, '.gut'), dest_context, os.path.join(dest_path, '.gut'))
    with src_context.cwd(src_context.path(src_path)):
        src_head = gut_rev_parse_head(src_context)
    with dest_context.cwd(dest_context.path(dest_path)):
        out(dim('Hard-resetting freshly-synced gut repo in ') + dest_context._path + dim(' to ') + color_commit(src_head[:GUT_HASH_DISPLAY_CHARS]) + dim('...'))
        output = gut(dest_context)['reset', '--hard', src_head]()
        out_dim('done.\n')
        quote(dest_context, output)

def ensure_build(context):
    if not context.path(GUT_EXE_PATH).exists() or GIT_VERSION.lstrip('v') not in gut(context)['--version']():
        out(dim('Need to build gut on ') + context._name + dim('.\n'))
        ensure_gut_folders(context)
        gut_prepare(plumbum.local) # <-- we always prepare gut source locally
        if context != plumbum.local:
            # If we're building remotely, rsync the prepared source to the remote host
            rsync(plumbum.local, GUT_SRC_PATH, context, GUT_SRC_PATH, excludes=['.git', 't'])
        gut_build(context)
        return True
    return False

def gut(context):
    return context[context.path(GUT_EXE_PATH)]

def init(context, _sync_path):
    sync_path = context.path(_sync_path)
    did_anything = False
    if not sync_path.exists():
        context['mkdir']['-p', sync_path]()
        did_anything = True
    with context.cwd(sync_path):
        ensure_build(context)
        if not (sync_path / '.gut').exists():
            out(gut(context)['init']())
            did_anything = True
        head = gut_rev_parse_head(context)
        if head == 'HEAD':
            (sync_path / '.gutignore').write(DEFAULT_GUTIGNORE)
            out(gut(context)['commit']['--allow-empty', '--message', 'Initial commit']())
            did_anything = True
    if not did_anything:
        print('Already initialized gut in %s' % (sync_path,))

def pipe_quote(stream, name):
    def run():
        try:
            while not shutting_down():
                line = stream.readline()
                if line != '' and not shutting_down():
                    out('[%s] %s' % (name, line))
                else:
                    break
        except Exception:
            if not shutting_down():
                raise
        if not shutting_down():
            out('%s exited.\n' % (name,))
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()

def watch_for_changes(context, path, event_prefix, event_queue):
    proc = None
    with context.cwd(context.path(path)):
        watched_root = context['pwd']().strip()
        watcher = None
        if context['which']['inotifywait'](retcode=None).strip():
            inotify_events = ['modify', 'attrib', 'move', 'create', 'delete']
            watcher = context['inotifywait']['--quiet', '--monitor', '--recursive', '--format', '%w%f', '--exclude', '.gut/']
            for event in inotify_events:
                watcher = watcher['--event', event]
            watcher = watcher['./']
            watch_type = 'inotifywait'
        elif context['which']['fswatch'](retcode=None).strip():
            watcher = context['fswatch']['./']
            watch_type = 'fswatch'
        else:
            out('gut-sync requires inotifywait or fswatch to be installed on both the local and remote hosts (missing on %s).\n' % (event_prefix,))
            sys.exit(1)
        out(dim('Using ') + watch_type + dim(' to listen for changes in ') + context._path + '\n')
        kill_via_pidfile(context, watch_type)
        proc = watcher.popen()
        save_pidfile(context, watch_type, proc.pid)
    def run():
        try:
            while not shutting_down():
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
        except Exception:
            if not shutting_down():
                raise
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    pipe_quote(proc.stderr, 'watch_%s_err' % (event_prefix,))

def run_gut_daemon(context, path):
    """
    Start a git-daemon on the host, bound to port GUTD_BIND_PORT on the *localhost* network interface only.
    `autossh` will create a tunnel to expose this port as GUTD_CONNECT_PORT on the other host.
    """
    proc = None
    repo_path = context.path(path)
    kill_via_pidfile(context, 'gut-daemon')
    pidfile_opt = '--pid-file=%s' % (pidfile_path(context, 'gut-daemon'),)
    proc = gut(context)['daemon', '--export-all', '--base-path=%s' % (repo_path,), pidfile_opt, '--reuseaddr', '--listen=localhost', '--port=%s' % (GUTD_BIND_PORT,), repo_path].popen()
    active_pidfiles.append((context, 'gut-daemon')) # gut-daemon writes its own pidfile
    pipe_quote(proc.stdout, '%s_daemon_out' % (context._name,))
    pipe_quote(proc.stderr, '%s_daemon_err' % (context._name,))

def pidfile_path(context, process_name):
    return context.path(os.path.join(GUT_PATH, '%s.pid' % (process_name,)))

def kill_via_pidfile(context, process_name):
    quote(context, context['pkill']['--pidfile', '%s' % (pidfile_path(context, process_name),), process_name](retcode=None))

def save_pidfile(context, process_name, pid):
    my_path = pidfile_path(context, process_name)
    if not pid:
        pid = context['pgrep']['--newest', process_name]().strip()
        if pid:
            out(dim('Using PID of ') + pid + dim(' (from `pgrep --newest ' + process_name + '`) to populate ') + color_path(my_path) + dim(' on ') + context._name + dim('.\n'))
    if pid:
        active_pidfiles.append((context, process_name))
        my_path.write('%s' % (pid,))
    else:
        out(color_error('Could not save pidfile for ') + process_name + color_error(' on ') + context._name + '\n')

def start_ssh_tunnel(local, remote):
    ssh_tunnel_opts = '%s:localhost:%s' % (GUTD_CONNECT_PORT, GUTD_BIND_PORT)
    kill_via_pidfile(local, 'autossh')
    local.env['AUTOSSH_PIDFILE'] = unicode(pidfile_path(local, 'autossh'))
    proc = local['autossh']['-N', '-L', ssh_tunnel_opts, '-R', ssh_tunnel_opts, remote._ssh_address].popen()
    active_pidfiles.append((local, 'autossh')) # autossh writes its own pidfile
    pipe_quote(proc.stdout, 'autossh_out')
    pipe_quote(proc.stderr, 'autossh_err')

def run_gut_daemons(local, local_path, remote, remote_path):
    run_gut_daemon(local, local_path)
    run_gut_daemon(remote, remote_path)
    start_ssh_tunnel(local, remote)

def get_tail_hash(context, sync_path):
    """
    Query the gut repo for the initial commit to the repo. We use this to determine if two gut repos are compatibile.
    http://stackoverflow.com/questions/1006775/how-to-reference-the-initial-commit
    """
    path = context.path(sync_path)
    if (path / '.gut').exists():
        with context.cwd(path):
            return gut(context)['rev-list', '--max-parents=0', 'HEAD'](retcode=None).strip() or None
    return None

def assert_folder_empty(context, _path):
    path = context.path(_path)
    if path.exists() and ((not path.isdir()) or len(path.list()) > 0):
        # If it exists, and it's not a directory or not an empty directory, then bail
        out(color_error('Refusing to auto-initialize ') + color_path(path) + color_error(' on ') + context._name)
        out(color_error(' as it is not an empty directory. Move or delete it manually first.\n'))
        shutdown()

def gut_commit(context, path):
    with context.cwd(context.path(path)):
        head_before = gut_rev_parse_head(context)
        out(dim('Checking ') + context._name + dim(' for changes...'))
        gut(context)['add', '--all', './']()
        commit_out = gut(context)['commit', '--message', 'autocommit'](retcode=None)
        head_after = gut_rev_parse_head(context)
        made_a_commit = head_before != head_after
        out(' ' + (('committed ' + color_commit(head_after[:GUT_HASH_DISPLAY_CHARS])) if made_a_commit else 'none') + dim('.\n'))
        if made_a_commit:
            quote(context, commit_out)
        return made_a_commit

def gut_pull(context, path):
    with context.cwd(context.path(path)):
        out(dim('Pulling changes to ') + context._name + dim('...'))
        gut(context)['fetch', 'origin']()
        # If the merge fails due to uncommitted changes, then we should pick them up in the next commit, which should happen very shortly thereafter
        merge_out = gut(context)['merge', 'origin/master', '--strategy=recursive', '--strategy-option=theirs', '--no-edit'](retcode=None)
        out_dim(' done.\n')
        quote(context, merge_out)

def setup_gut_origin(context, path):
    with context.cwd(context.path(path)):
        gut(context)['remote', 'rm', 'origin'](retcode=None)
        gut(context)['remote', 'add', 'origin', 'gut://localhost:%s/' % (GUTD_CONNECT_PORT,)]()
        gut(context)['config', 'color.ui', 'always']()
        gut(context)['config', 'user.name', 'gut-sync']()
        gut(context)['config', 'user.email', 'gut-sync@nowhere.com']()

def sync(local_path, remote_user, remote_host, remote_path, use_openssl=False):
    try:
        local = plumbum.local
        local._name = color_host('localhost')
        local._ssh_address = ''
        remote_ssh_address = ('%s@' % (remote_user,) if remote_user else '') + remote_host
        if use_openssl:
            remote = plumbum.SshMachine(remote_host, user=remote_user)
        else:
            # Import paramiko late so that one could use `--openssl` without even installing paramiko
            import paramiko
            from plumbum.machines.paramiko_machine import ParamikoMachine
            # XXX paramiko doesn't seem to successfully update my known_hosts file with this setting
            remote = ParamikoMachine(remote_host, user=remote_user, missing_host_policy=paramiko.AutoAddPolicy())
        local._path = color_host_path(local, local_path)
        remote._ssh_address = remote_ssh_address
        remote._name = color_host(remote_host)
        remote._path = color_host_path(remote, remote_path)

        out(dim('Syncing ') + local._path + dim(' with ') + remote._path + '\n')

        ensure_build(local)
        ensure_build(remote)

        local_tail_hash = get_tail_hash(local, local_path)
        remote_tail_hash = get_tail_hash(remote, remote_path)

        # Do we need to initialize local and/or remote gut repos?
        if not local_tail_hash or local_tail_hash != remote_tail_hash:
            out(dim('Local gut repo base commit: [') + color_commit(local_tail_hash and local_tail_hash[:GUT_HASH_DISPLAY_CHARS]) + dim(']\n'))
            out(dim('Remote gut repo base commit: [') + color_commit(remote_tail_hash and remote_tail_hash[:GUT_HASH_DISPLAY_CHARS]) + dim(']\n'))
            if local_tail_hash and not remote_tail_hash:
                assert_folder_empty(remote, remote_path)
                out('Initializing remote repo from local repo...\n')
                rsync_gut(local, local_path, remote, remote_path)
            elif remote_tail_hash and not local_tail_hash:
                assert_folder_empty(local, local_path)
                out('Initializing local folder from remote gut repo...\n')
                rsync_gut(remote, remote_path, local, local_path)
            elif not local_tail_hash and not remote_tail_hash:
                assert_folder_empty(remote, remote_path)
                assert_folder_empty(local, local_path)
                out('Initializing both local and remote gut repos...\n')
                out_dim('Initializing local repo first...\n')
                init(local, local_path)
                out_dim('Initializing remote repo from local repo...\n')
                rsync_gut(local, local_path, remote, remote_path)
            else:
                out(color_error('Cannot sync incompatible gut repos:\n'))
                out(color_error('Local initial commit hash: [') + color_commit(local_tail_hash[:GUT_HASH_DISPLAY_CHARS]) + color_error(']\n'))
                out(color_error('Remote initial commit hash: [') + color_commit(remote_tail_hash[:GUT_HASH_DISPLAY_CHARS]) + color_error(']\n'))
                shutdown()

        run_gut_daemons(local, local_path, remote, remote_path)
        # XXX The gut daemons are not necessarily listening yet, so this could result in races with commit_and_update calls below

        setup_gut_origin(local, local_path)
        setup_gut_origin(remote, remote_path)

        def commit_and_update(src_system):
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
            if gut_commit(src_context, src_path):
                gut_pull(dest_context, dest_path)

        event_queue = Queue.Queue()
        watch_for_changes(local, local_path, 'local', event_queue)
        watch_for_changes(remote, remote_path, 'remote', event_queue)
        # The filesystem watchers are not necessarily listening to all updates yet, so we could miss file changes that occur between the
        # commit_and_update calls below and the time that the filesystem watches are attached.

        commit_and_update('remote')
        commit_and_update('local')

        changed = set()
        while True:
            try:
                event = event_queue.get(True, 0.1 if changed else 10000)
            except Queue.Empty:
                for system in changed:
                    commit_and_update(system)
                changed.clear()
            else:
                system, path = event
                # Ignore events inside the .gut folder; these should also be filtered out in inotifywait/fswatch/etc if possible
                if not path.startswith('.gut/'):
                    changed.add(system)
                #     out('changed %s %s\n' % (system, path))
                # else:
                #     out('ignoring changed %s %s\n' % (system, path))
    except KeyboardInterrupt:
        shutdown(exit=False)
    except Exception:
        shutdown(exit=False)
        raise

def main():
    action = len(sys.argv) >= 2 and sys.argv[1]
    if action and (plumbum.local.path(GUT_DIST_PATH) / ('libexec/gut-core/gut-%s' % (action,))).exists():
        gut_exe_path = unicode(plumbum.local.path(GUT_EXE_PATH))
        args = [gut_exe_path] + sys.argv[1:]
        try:
            # Try executing gut; if we get an error on invocation, then try building gut and trying again
            os.execv(gut_exe_path, args)
        except OSError:
            local = plumbum.local
            local._name = color_host('localhost')
            ensure_build(local)
            os.execv(gut_exe_path, args)
    elif action == 'build':
        if not ensure_build(plumbum.local):
            out(dim('gut ') + GIT_VERSION + dim(' has already been built.\n'))
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument('action', choices=['sync'])
        parser.add_argument('local')
        parser.add_argument('remote')
        # parser.add_argument('--verbose', '-v', action='count')
        parser.add_argument('--openssl', action='store_true')
        args = parser.parse_args()
        local_path = args.local
        if ':' not in args.remote:
            parser.error('remote must include both the hostname and path, separated by a colon')
        remote_addr, remote_path = args.remote.split(':', 1)
        remote_user, remote_host = remote_addr.rsplit('@', 2) if '@' in remote_addr else (None, remote_addr)
        sync(local_path, remote_user, remote_host, remote_path, use_openssl=args.openssl)

if __name__ == '__main__':
    main()
