import asyncio
from datetime import datetime

from . import config
from .terminal import quote_proc, color_commit, kill_previous_process, active_pidfiles, get_pidfile_path, Writer
from . import util

@asyncio.coroutine
def exe_path(context):
    return (yield from context.abspath(config.GUT_EXE_PATH + '.exe' if context._is_windows else config.GUT_EXE_PATH))

def gut(context):
    return context[exe_path(context)]

def get_version(context):
    return gut(context)['--version']()

def rev_parse_head(context):
    return gut(context)['rev-parse', 'HEAD'](retcode=None).strip() or None

@asyncio.coroutine
def init(context, _sync_path):
    sync_path = context.path(_sync_path)
    util.mkdirp(context, sync_path)
    with context.cwd(sync_path):
        if not (sync_path / '.gut').exists():
            yield from quote_proc(context, '', gut(context)['init'].popen())

@asyncio.coroutine
def ensure_initial_commit(context, _sync_path):
    with context.cwd(sync_path):
        head = rev_parse_head(context)
        if head == 'HEAD':
            (sync_path / '.gutignore').write(config.DEFAULT_GUTIGNORE)
            yield from quote_proc(context, '', gut(context)['add']['.gutignore'].popen())
            yield from quote_proc(context, '', gut(context)['commit']['--allow-empty', '--message', 'Initial commit'].popen())

@asyncio.coroutine
def commit(context, path, prefix, update_untracked=False):
    status = Writer(context, 'commit')
    with context.cwd(context.path(path)):
        # start = datetime.now()
        head_before = rev_parse_head(context)
        if update_untracked:
            files_out = gut(context)['ls-files', '-i', '--exclude-standard', '--', prefix]().strip()
            if files_out:
                for filename in files_out.split('\n'):
                    status.out('(@dim)Untracking newly-.gutignored (@r)' + filename)
                    quote_proc(context, 'gut-rm--cached', gut(context)['rm', '--cached', '--ignore-unmatch', '--quiet', '--', filename].popen())
        status.out('(@dim)Checking %s (@dim)for changes (scope=(@r)%s(@dim))...' % (context._name_ansi, prefix))
        quote_proc(context, 'gut-add', gut(context)['add', '--all', '--', prefix].popen())
        quote_proc(context, 'gut-commit', gut(context)['commit', '--message', 'autocommit'].popen())
        head_after = rev_parse_head(context)
        made_a_commit = head_before != head_after
        status.out(' ' + (('committed ' + color_commit(head_after)) if made_a_commit else 'none') + '(@dim).\n')
        # status.out(context, '', 'gut.commit took %.2f seconds' % ((datetime.now() - start).total_seconds(),))
        return made_a_commit

@asyncio.coroutine
def pull(context, path):
    status = Writer(context, 'pull')
    with context.cwd(context.path(path)):
        status.out('(@dim)Downloading changes to (@r)%s(@dim)...' % (context._name_ansi,))
        yield from quote_proc(context, 'gut-fetch', gut(context)['fetch', 'origin'].popen())
        status.out('(@dim) done.\n')
    @asyncio.coroutine
    def do_merge():
        with context.cwd(context.path(path)):
            status.out('(@dim)Merging changes to (@r)%s(@dim)...' % (context._name_ansi,))
            proc = gut(context)['merge', 'origin/master', '--strategy=recursive', '--strategy-option=theirs', '--no-edit'].popen()
            _, _, stderr = quote_proc(context, 'gut-merge', proc)
            need_commit = 'Your local changes to the following files would be overwritten' in stderr
            if need_commit:
                status.out('(@error) failed due to uncommitted changes.\n')
            else:
                status.out('(@dim) done.\n')
            return need_commit
    if (yield from do_merge()):
        status.out('(@dim)Committing outstanding changes before retrying merge...\n')
        yield from commit(context, path, './', update_untracked=True)
        yield from do_merge()

def setup_origin(context, path, tail_hash, gutd_connect_port):
    with context.cwd(context.path(path)):
        gut(context)['remote', 'rm', 'origin'](retcode=None)
        gut(context)['remote', 'add', 'origin', 'gut://localhost:%s/%s/' % (gutd_connect_port, tail_hash)]()
        gut(context)['config', 'color.ui', 'always']()
        hostname = context['hostname']().strip()
        gut(context)['config', 'user.name', hostname]()
        gut(context)['config', 'user.email', 'gut-sync@' + hostname]()

@asyncio.coroutine
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
    asyncio.async(quote_proc(context, 'gut-daemon', proc, wait=False))
