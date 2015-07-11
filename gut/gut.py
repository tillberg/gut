from datetime import datetime

import config
from terminal import out, out_dim, dim, quote, color_commit, color_error, kill_previous_process, active_pidfiles, get_pidfile_path, Writer
import util

def exe_path(context):
    return context.path(config.GUT_EXE_PATH + '.exe' if context._is_windows else config.GUT_EXE_PATH)

def gut(context):
    return context[exe_path(context)]

def get_version(context):
    return gut(context)['--version']()

def rev_parse_head(context):
    return gut(context)['rev-parse', 'HEAD'](retcode=None).strip() or None

def init(context, _sync_path):
    sync_path = context.path(_sync_path)
    util.mkdirp(context, sync_path)
    with context.cwd(sync_path):
        if not (sync_path / '.gut').exists():
            quote(context, '', gut(context)['init']())

def ensure_initial_commit(context, _sync_path):
    with context.cwd(sync_path):
        head = rev_parse_head(context)
        if head == 'HEAD':
            (sync_path / '.gutignore').write(config.DEFAULT_GUTIGNORE)
            quote(context, '', gut(context)['add']['.gutignore']())
            quote(context, '', gut(context)['commit']['--allow-empty', '--message', 'Initial commit']())

def commit(context, path, prefix, update_untracked=False):
    with context.cwd(context.path(path)):
        # start = datetime.now()
        head_before = rev_parse_head(context)
        if update_untracked:
            files_out = gut(context)['ls-files', '-i', '--exclude-standard', '--', prefix]().strip()
            if files_out:
                for filename in files_out.split('\n'):
                    quote(context, '', dim('Untracking newly-.gutignored ') + filename)
                    gut(context)['rm', '--cached', '--ignore-unmatch', '--quiet', '--', filename]()
        out(dim('Checking ') + context._name_ansi + dim(' for changes (scope=') + prefix + dim(')...'))
        gut(context)['add', '--all', '--', prefix]()
        commit_out = gut(context)['commit', '--message', 'autocommit'](retcode=None)
        head_after = rev_parse_head(context)
        made_a_commit = head_before != head_after
        out(' ' + (('committed ' + color_commit(head_after)) if made_a_commit else 'none') + dim('.\n'))
        if made_a_commit:
            quote(context, '', commit_out)
        # quote(context, '', 'gut.commit took %.2f seconds' % ((datetime.now() - start).total_seconds(),))
        return made_a_commit

def pull(context, path):
    with context.cwd(context.path(path)):
        out(dim('Downloading changes to ') + context._name_ansi + dim('...'))
        gut(context)['fetch', 'origin']()
        out(dim(' done.\n'))
    def do_merge():
        with context.cwd(context.path(path)):
            out(dim('Merging changes to ') + context._name_ansi + dim('...'))
            _, stdout, stderr = gut(context)['merge', 'origin/master', '--strategy=recursive', '--strategy-option=theirs', '--no-edit'].run(retcode=None)
            need_commit = 'Your local changes to the following files would be overwritten' in stderr
            if need_commit:
                out(color_error(' failed due to uncommitted changes.\n'))
            else:
                out(dim(' done.\n'))
            quote(context, '', stdout)
            quote(context, '', stderr)
            return need_commit
    if do_merge():
        out(dim('Committing outstanding changes before retrying merge...\n'))
        commit(context, path, './', update_untracked=True)
        do_merge()


def setup_origin(context, path, tail_hash, gutd_connect_port):
    with context.cwd(context.path(path)):
        gut(context)['remote', 'rm', 'origin'](retcode=None)
        gut(context)['remote', 'add', 'origin', 'gut://localhost:%s/%s/' % (gutd_connect_port, tail_hash)]()
        gut(context)['config', 'color.ui', 'always']()
        hostname = context['hostname']().strip()
        gut(context)['config', 'user.name', hostname]()
        gut(context)['config', 'user.email', 'gut-sync@' + hostname]()

def daemon(context, path, tail_hash, gutd_bind_port=None):
    """
    Start a git-daemon on the host, bound to port gutd_bind_port on the *localhost* network interface only.
    `autossh` will create a tunnel to expose this port as gutd_connect_port on the other host.
    """
    base_path = context.path(config.GUT_DAEMON_PATH)
    util.mkdirp(context, config.GUT_DAEMON_PATH)
    symlink_path = base_path / tail_hash
    repo_path = context.path(path)
    if symlink_path.exists():
        symlink_path.unlink()
    repo_path.symlink(symlink_path)
    proc = None
    kill_previous_process(context, 'gut-daemon')
    pidfile_opt = '--pid-file=%s' % (get_pidfile_path(context, 'gut-daemon'),)
    proc = gut(context)['daemon', '--export-all', '--base-path=%s' % (base_path,), pidfile_opt, '--reuseaddr', '--listen=localhost', '--port=%s' % (gutd_bind_port,), base_path].popen()
    active_pidfiles.append((context, 'gut-daemon')) # gut-daemon writes its own pidfile
    Writer(context, 'gut-daemon').quote(proc, wait=False)
