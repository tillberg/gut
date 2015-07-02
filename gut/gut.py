import config
import deps
from terminal import out, out_dim, dim, quote, color_commit, pipe_quote, kill_previous_process, active_pidfiles, get_pidfile_path

def gut(context):
    return context[context.path(config.GUT_EXE_PATH)]

def get_version(context):
    return gut(context)['--version']()

def rev_parse_head(context):
    return gut(context)['rev-parse', 'HEAD'](retcode=None).strip() or None

def init(context, _sync_path):
    sync_path = context.path(_sync_path)
    did_anything = False
    if not sync_path.exists():
        context['mkdir']['-p', sync_path]()
        did_anything = True
    with context.cwd(sync_path):
        if not (sync_path / '.gut').exists():
            out(gut(context)['init']())
            did_anything = True
        head = rev_parse_head(context)
        if head == 'HEAD':
            (sync_path / '.gutignore').write(config.DEFAULT_GUTIGNORE)
            out(gut(context)['commit']['--allow-empty', '--message', 'Initial commit']())
            did_anything = True
    if not did_anything:
        print('Already initialized gut in %s' % (sync_path,))

def commit(context, path):
    with context.cwd(context.path(path)):
        head_before = rev_parse_head(context)
        out(dim('Checking ') + context._name + dim(' for changes...'))
        gut(context)['add', '--all', './']()
        commit_out = gut(context)['commit', '--message', 'autocommit'](retcode=None)
        head_after = rev_parse_head(context)
        made_a_commit = head_before != head_after
        out(' ' + (('committed ' + color_commit(head_after)) if made_a_commit else 'none') + dim('.\n'))
        if made_a_commit:
            quote(context, commit_out)
        return made_a_commit

def pull(context, path):
    with context.cwd(context.path(path)):
        out(dim('Pulling changes to ') + context._name + dim('...'))
        gut(context)['fetch', 'origin']()
        # If the merge fails due to uncommitted changes, then we should pick them up in the next commit, which should happen very shortly thereafter
        merge_out = gut(context)['merge', 'origin/master', '--strategy=recursive', '--strategy-option=theirs', '--no-edit'](retcode=None)
        out_dim(' done.\n')
        quote(context, merge_out)

def setup_origin(context, path):
    with context.cwd(context.path(path)):
        gut(context)['remote', 'rm', 'origin'](retcode=None)
        gut(context)['remote', 'add', 'origin', 'gut://localhost:%s/' % (config.GUTD_CONNECT_PORT,)]()
        gut(context)['config', 'color.ui', 'always']()
        gut(context)['config', 'user.name', 'gut-sync']()
        gut(context)['config', 'user.email', 'gut-sync@nowhere.com']()

def run_daemon(context, path):
    """
    Start a git-daemon on the host, bound to port GUTD_BIND_PORT on the *localhost* network interface only.
    `autossh` will create a tunnel to expose this port as GUTD_CONNECT_PORT on the other host.
    """
    proc = None
    repo_path = context.path(path)
    kill_previous_process(context, 'gut-daemon')
    pidfile_opt = '--pid-file=%s' % (get_pidfile_path(context, 'gut-daemon'),)
    proc = gut(context)['daemon', '--export-all', '--base-path=%s' % (repo_path,), pidfile_opt, '--reuseaddr', '--listen=localhost', '--port=%s' % (config.GUTD_BIND_PORT,), repo_path].popen()
    active_pidfiles.append((context, 'gut-daemon')) # gut-daemon writes its own pidfile
    pipe_quote(proc.stdout, '%s_daemon_out' % (context._name,))
    pipe_quote(proc.stderr, '%s_daemon_err' % (context._name,))

