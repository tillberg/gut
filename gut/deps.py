import asyncio
import sys
import traceback

from . import config
from .terminal import shutdown, Writer, quote_proc

auto_install = False

DEPENDENCY_ERROR_MAP = {
    'autoconf: not found': 'autoconf',
    'msgfmt: not found': 'gettext',
    'missing fswatch': 'fswatch',
    'missing inotifywait': 'inotify-tools',
}

BREW_DEPS = ['autoconf', 'fswatch', 'autossh']
APT_GET_DEPS = ['gettext', 'autoconf', 'inotify-tools', 'autossh']

def missing_dependency(context, name, retry_failed=None):
    status = Writer(context, '(@dim)deps-mgr')
    if context._is_windows and name == 'inotify-tools':
        from . import gut_build # late import due to circular dependency :(
        gut_build.git_clone_update(config.INOTIFY_WIN_REPO_URL, config.INOTIFY_WIN_PATH, config.INOTIFY_WIN_VERSION)
        status.out('(@dim)Building (@r)inotify-win(@dim)...')
        with context.cwd(context.path(config.INOTIFY_WIN_PATH)):
            context['cmd']['/c', '%WINDIR%\\Microsoft.NET\\Framework\\v4.0.30319\\csc.exe /t:exe /out:inotifywait.exe src\\*.cs']()
        status.out('(@dim) done.\n')
        return
    has_apt_get = not context._is_windows and context['which']['apt-get'](retcode=None) != ''
    has_homebrew = not context._is_windows and context['which']['brew'](retcode=None) != ''
    if (auto_install and not retry_failed) and (has_apt_get or has_homebrew):
        status.out('(@dim)Attempting to automatically install missing dependency (@r)%s(@dim)...\n' % (name,))
        if has_apt_get:
            # This needs to go to the foreground in case it has a password prompt
            status.out('(@dim)$ sudo apt-get install (@r)%s\n' % (name,))
            quote_proc(context, '(@dim)apt-get', context['sudo'][context['apt-get']['install', '-y', name]].popen())
        else:
            status.out('(@dim)$ brew install (@r)%s\n' % (name,))
            quote_proc(context, '(@dim)brew', context['brew']['install', name].with_env(HOMEBREW_NO_EMOJI=1).popen())
    else:
        status.out('\n(@error)You seem to be missing a required dependency, (@r)%s(@error), on (@r)%s(@r)(@error).' % (name, context._name_ansi))
        if has_apt_get or has_homebrew:
            status.out('\n(@dim)To install just this dependency, you could try running this:\n(@dim)$ ')
            if has_apt_get:
                status.out('(@dim)sudo apt-get install ' + name)
            else:
                status.out('(@dim)brew install ' + name)
            if not auto_install:
                status.out('\n\n(@dim)Or if you\'d prefer, I\'ll try to automatically install dependencies as needed with the (@r)--install-deps (@dim)flag.\n')
        # out(dim('\n\nOr to install all required dependencies, you could try running this instead:\n$ '))
        # if has_apt_get:
        #     out('sudo apt-get install ' + ' '.join(APT_GET_DEPS))
        # else:
        #     out('brew install ' + ' '.join(BREW_DEPS))
        # out('\n\n')
        shutdown()

def divine_missing_dependency(exception_text):
    for (text, name) in DEPENDENCY_ERROR_MAP.items():
        if text in exception_text:
            return name
        # Some systems say "command not found", others say "not found"
        if text.replace('not found', 'command not found') in exception_text:
            return name
    return None

@asyncio.coroutine
def retry_method(context, cb):
    status = Writer(context)
    missing_dep_name = None
    last_missing_dep_name = None
    def output_failed():
        if missing_dep_name:
            status.out('(@error) failed (missing (@r)%s(@error))(@dim).\n\n' % (missing_dep_name,))
        else:
            status.out('(@error) failed(@r)(@dim).\n\n' % (missing_dep_name,))
        traceback.print_exc(file=sys.stderr)
    while True:
        try:
            rval = yield from cb()
        except KeyboardInterrupt:
            shutdown()
        except plumbum.commands.processes.ProcessExecutionError as ex:
            missing_dep_name = divine_missing_dependency(ex.stdout + ex.stderr)
            output_failed()
        except Exception as ex:
            missing_dep_name = divine_missing_dependency(str(ex))
            output_failed()
        else:
            break
        if missing_dep_name:
            missing_dependency(context, missing_dep_name, retry_failed=(missing_dep_name == last_missing_dep_name))
            status.out('(@dim)Retrying...\n')
            last_missing_dep_name = missing_dep_name
        else:
            shutdown()
    return rval
