import sys
import traceback

import plumbum

import config
from terminal import shutdown, out, out_dim, dim, quote, bright, color_error

auto_install_deps = False

DEPENDENCY_ERROR_MAP = {
    'autoconf: not found': 'autoconf',
    'msgfmt: not found': 'gettext',
    'missing fswatch': 'fswatch',
    'missing inotifywait': 'inotify-tools',
}

BREW_DEPS = ['autoconf', 'fswatch', 'autossh']
APT_GET_DEPS = ['gettext', 'autoconf', 'inotify-tools', 'autossh']

def missing_dependency(context, name, retry_failed=None):
    if context._is_windows and name == 'inotify-tools':
        import gut_build # late import due to circular dependency :(
        gut_build.git_clone_update(config.INOTIFY_WIN_REPO_URL, config.INOTIFY_WIN_PATH, config.INOTIFY_WIN_VERSION)
        out(dim('Building ') + 'inotify-win' + dim('...'))
        with context.cwd(context.path(config.INOTIFY_WIN_PATH)):
            context['cmd']['/c', '%WINDIR%\\Microsoft.NET\\Framework\\v4.0.30319\\csc.exe /t:exe /out:inotifywait.exe src\\*.cs']()
        out(' done.\n')
        return
    has_apt_get = not context._is_windows and context['which']['apt-get'](retcode=None) != ''
    has_homebrew = not context._is_windows and context['which']['brew'](retcode=None) != ''
    if (auto_install_deps and not retry_failed) and (has_apt_get or has_homebrew):
        out(dim('Attempting to automatically install missing dependency ') + name + dim('...\n'))
        if has_apt_get:
            # This needs to go to the foreground in case it has a password prompt
            out(dim('$ sudo apt-get install ') + name + '\n')
            output = context['sudo'][context['apt-get']['install', '-y', name]]()
        else:
            out(dim('$ brew install ') + name + '\n')
            output = context['brew']['install', name].with_env(HOMEBREW_NO_EMOJI=1)()
        quote(context, output)
    else:
        out(color_error('\nYou seem to be missing a required dependency, ') + name + color_error(', on ') + context._name_ansi + color_error('.'))
        if has_apt_get or has_homebrew:
            out(dim('\nTo install just this dependency, you could try running this:\n$ '))
            if has_apt_get:
                out('sudo apt-get install ' + name)
            else:
                out('brew install ' + name)
            if not auto_install_deps:
                out(dim('\n\nOr if you\'d prefer, I\'ll try to automatically install dependencies as needed with the ') +
                    bright('--install-deps') + dim(' flag.\n'))
        # out(dim('\n\nOr to install all required dependencies, you could try running this instead:\n$ '))
        # if has_apt_get:
        #     out('sudo apt-get install ' + ' '.join(APT_GET_DEPS))
        # else:
        #     out('brew install ' + ' '.join(BREW_DEPS))
        # out('\n\n')
        shutdown()

def divine_missing_dependency(exception_text):
    for (text, name) in DEPENDENCY_ERROR_MAP.iteritems():
        if text in exception_text:
            return name
        # Some systems say "command not found", others say "not found"
        if text.replace('not found', 'command not found') in exception_text:
            return name
    return None

def retry_method(context, cb):
    missing_dep_name = None
    last_missing_dep_name = None
    while True:
        try:
            rval = cb()
        except plumbum.commands.processes.ProcessExecutionError as ex:
            missing_dep_name = divine_missing_dependency(ex.stdout + ex.stderr)
        except Exception as ex:
            missing_dep_name = divine_missing_dependency(ex.message)
        else:
            break
        if missing_dep_name:
            out(color_error(' failed (missing ') + missing_dep_name + color_error(')') + dim('.\n\n'))
            traceback.print_exc(file=sys.stderr)
            missing_dependency(context, missing_dep_name, retry_failed=(missing_dep_name == last_missing_dep_name))
            out_dim('Retrying...\n')
            last_missing_dep_name = missing_dep_name
        else:
            out(color_error(' failed') + dim('.\n\n'))
            traceback.print_exc(file=sys.stderr)
            shutdown()
    return rval

