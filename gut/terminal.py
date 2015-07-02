import config
import os
import re
import sys
import threading

GUT_HASH_DISPLAY_CHARS = 10

_shutting_down = False
_shutting_down_lock = threading.Lock()

active_pidfiles = []

def get_pidfile_path(context, process_name):
    return context.path(os.path.join(config.GUT_PATH, '%s.pid' % (process_name,)))

def kill_previous_process(context, process_name):
    # As usual, Darwin doesn't have the --pidfile flag, but it does have -F, because we like obscurity
    path = get_pidfile_path(context, process_name)
    if path.exists():
        _, stdout, stderr = context['pkill']['-F', path, process_name].run(retcode=None)
        quote(context, stdout)
        quote(context, stderr)

def save_process_pid(context, process_name, pid):
    my_path = get_pidfile_path(context, process_name)
    if not pid:
        # --newest is not supported in Darwin; -n work in both Darwin and Linux, though
        pid = context['pgrep']['-n', process_name]().strip()
        if pid:
            out(dim('Using PID of ') + pid + dim(' (from `pgrep -n ' + process_name + '`) to populate ') + color_path(my_path) + dim(' on ') + context._name_ansi + dim('.\n'))
    if pid:
        active_pidfiles.append((context, process_name))
        my_path.write('%s' % (pid,))
    else:
        out(color_error('Could not save pidfile for ') + process_name + color_error(' on ') + context._name_ansi + '\n')

def shutting_down():
    with _shutting_down_lock:
        return _shutting_down

def shutdown(exit=True):
    with _shutting_down_lock:
        global _shutting_down
        _shutting_down = True
    try:
        # out_dim('Shutting down sub-processes...\n')
        for context, process_name in active_pidfiles:
            out_dim('\nShutting down %s on %s...' % (process_name, context._name_ansi))
            retries = 3
            while True:
                try:
                    kill_previous_process(context, process_name)
                except Exception as ex:
                    retries -= 1
                    if retries <= 0:
                        out(color_error(' failed: "%s".' % (ex,)))
                        break
                    import time
                    time.sleep(1)
                else:
                    out_dim(' done.')
                    break
        out('\n')
    except KeyboardInterrupt:
        pass
    if exit:
        sys.exit(1)

def ansi(num):
    return '\033[%sm' % (num,)

RE_ANSI = re.compile('\033\[\d*m')
ANSI_RESET_ALL = ansi('')
ANSI_RESET_COLOR = ansi(39)
ANSI_BRIGHT = ansi(1)
ANSI_DIM = ansi(2)
ANSI_COLORS = {'grey': 30, 'red': 31, 'green': 32, 'yellow': 33, 'blue': 34, 'magenta': 35, 'cyan': 36, 'white': 37}

def colored(color, text):
    return ansi(ANSI_COLORS[color]) + unicode(text) + ANSI_RESET_COLOR

def colored_gen(color):
    def _colored(text):
        return colored(color, text)
    return _colored
color_path = colored_gen('cyan')
color_host = colored_gen('yellow')
color_error = colored_gen('red')

def color_commit(commitish):
    return colored('green', (commitish or 'None')[:GUT_HASH_DISPLAY_CHARS])

def dim(text):
    return ANSI_DIM + unicode(text) + ANSI_RESET_ALL

def bright(text):
    return ANSI_BRIGHT + unicode(text) + ANSI_RESET_ALL

def color_host_path(context, path):
    return (context._name_ansi + dim(':') if not context._is_local else '') + color_path(context.path(path))

def out(text):
    sys.stderr.write(text)
    sys.stderr.flush()

def out_dim(text):
    out(dim(text))

def quote(context, text):
    for line in text.strip().split('\n'):
        # Avoid outputting lines that only contain control characters and whitespace
        if RE_ANSI.sub('', line).strip():
            out(dim('[') + context._name_ansi + dim('] ') + line + '\n')

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

