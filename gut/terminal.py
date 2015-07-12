import os
import re
import sys
import threading
import traceback

try:
    import colorama
except ImportError:
    pass
else:
    colorama.init()
import plumbum

from . import config

GUT_HASH_DISPLAY_CHARS = 10

_shutting_down = False
_shutting_down_lock = threading.Lock()

active_pidfiles = []

def get_cmd(context, cmds):
    for cmd in cmds:
        try:
            context.which(cmd)
        except plumbum.commands.CommandNotFound:
            pass
        else:
            return cmd
    return None

def get_pidfile_path(context, process_name):
    return context.path('/'.join([config.GUT_PATH, '%s.pid' % (process_name,)]))

def kill_previous_process(context, process_name):
    # As usual, Darwin doesn't have the --pidfile flag, but it does have -F, because we like obscurity
    path = get_pidfile_path(context, process_name)
    if path.exists():
        cmd = get_cmd(context, ['pkill'] + (['kill'] if context._is_windows else []))
        if not cmd:
            deps.missing_dependency(context, 'pkill')
        if cmd == 'pkill':
            command = context['pkill']['-F', path, process_name]
        else:
            pid = context.path(path).read().strip()
            # XXX would be good to filter on user, too?
            tasklist_out = context['tasklist']['/fi', 'PID eq ' + pid, '/fi', 'IMAGENAME eq ' + process_name + '.exe']()
            if not (process_name in tasklist_out and pid in tasklist_out and 'No tasks' not in tasklist_out):
                # This process is either not running or is something else now
                return
            command = context['kill']['-f', pid]
        _, stdout, stderr = command.run(retcode=None)
        quote(context, '', stdout)
        quote(context, '', stderr)

def save_process_pid(context, process_name, pid):
    my_path = get_pidfile_path(context, process_name)
    if not pid:
        # --newest is not supported in Darwin; -n work in both Darwin and Linux, though
        pid = context['pgrep']['-n', process_name](retcode=None).strip()
        if pid:
            out(dim('Using PID of ') + pid + dim(' (from `pgrep -n ' + process_name + '`) to populate ') + color_path(my_path) + dim(' on ') + context._name_ansi + dim('.\n'))
    if pid:
        active_pidfiles.append((context, process_name))
        my_path.write('%s' % (pid,))
    else:
        out(color_error('Could not save pidfile for ') + process_name + color_error(' on ') + context._name_ansi + '\n')

def run_daemon_thread(fn):
    def run():
        try:
            fn()
        except Exception as ex:
            if not shutting_down():
                out('\n\n')
                traceback.print_exc(file=sys.stderr)
                shutdown(exit=False)
                sys.exit(1)
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()

def shutting_down():
    with _shutting_down_lock:
        return _shutting_down

def shutdown(exit=True):
    global _shutting_down
    with _shutting_down_lock:
        _shutting_down = True
    try:
        # out_dim('Shutting down sub-processes...\n')
        for context, process_name in active_pidfiles:
            out(dim('\nShutting down ') + process_name + dim(' on ') + context._name_ansi + dim('...'))
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

RE_ANSI_MARK = re.compile('\(@(\w+)\)')

COLOR_PATH = ansi(ANSI_COLORS['cyan'])
COLOR_HOST = ansi(ANSI_COLORS['yellow'])
COLOR_ERROR = ansi(ANSI_COLORS['red'])
COLOR_COMMIT = ansi(ANSI_COLORS['green'])

def color_path(s):
    return '(@path)%s(@r)' % (s,)

def color_host(s):
    return '(@host)%s(@r)' % (s,)

def color_error(s):
    return '(@error)%s(@r)' % (s,)

def color_commit(commitish):
    return '(@commit)%s(@r)' % (commitish or 'None')[:GUT_HASH_DISPLAY_CHARS]

def dim(text):
    return '(@dim)' + str(text) + '(@r)'

def bright(text):
    return '(@bright)' + str(text) + '(@r)'

def color_host_path(context, path):
    return (context._name_ansi + dim(':') if not context._is_local else '') + '(@path)' + str(context.path(path)) + '(@r)'

no_color = False
def disable_color():
    global no_color
    no_color = True

def ansi_mark_replacer(matchobj):
    code = matchobj.group(1)
    if code == 'r':
        return ANSI_RESET_ALL
    elif code == 'error':
        return COLOR_ERROR
    elif code == 'path':
        return COLOR_PATH
    elif code == 'host':
        return COLOR_HOST
    elif code == 'commit':
        return COLOR_COMMIT
    elif code == 'dim':
        return ANSI_DIM
    elif code == 'bright':
        return ANSI_BRIGHT
    else:
        # Don't filter unrecognized text
        return '(@' + code + ')'

def uncolorize(text):
    return RE_ANSI.sub('', RE_ANSI_MARK.sub('', text))

def colorize(text):
    return uncolorize(text) if no_color else RE_ANSI_MARK.sub(ansi_mark_replacer, text)

def has_visible_text(text):
    return uncolorize(text).strip() != ''

def get_nameish(context, name):
    return (context._name_ansi + (':' + name if name else '')) if context else '--'

writers = []
last_temp_output = ''

lock = threading.RLock()

def to_stderr(s):
    with lock:
        sys.stderr.write(s)

_terminal_columns = None
def get_terminal_cols():
    global _terminal_columns
    if _terminal_columns == None:
        _, _terminal_columns = plumbum.local['stty']['size'](stdin=None).strip().split()
    return int(_terminal_columns)

def clear_temp_output():
    with lock:
        global last_temp_output
        if last_temp_output:
            to_stderr('Clear %s characters\n' % len(last_temp_output))
            # sys.stderr.write('\b \b' * len(last_temp_output))
            last_temp_output = ''

def update_temp_output():
    with lock:
        global last_temp_output
        curr_lines = [writer.get_curr_line() for writer in writers]
        # sys.stderr.write('lines: %s\n' % (curr_lines,))
        curr_lines = [line for line in curr_lines if line]
        clear_temp_output()
        temp_output = 'tmp: ' + colorize(' | '.join(curr_lines))
        if temp_output == last_temp_output:
            return
        clear_temp_output()
        max_len = get_terminal_cols()
        if len(temp_output) > max_len:
            temp_output = temp_output[:max_len - 4] + ' ...'
        if temp_output:
            to_stderr(temp_output + '\n')
        last_temp_output = temp_output

class Writer:
    def __init__(self, context, name=None):
        self.context = context
        self.name = name
        self.prefix = '(@dim)[(@r)%s(@dim)](@r) ' % (get_nameish(context, name),)
        self.curr_line = ''
        writers.append(self)

    # def __call__(self, text):
    #     self.out(text)

    # def __del__(self):
    #     if self.curr_line:
    #         self.out(' ENDLINE\n')

    def get_curr_line(self):
        with lock:
            return (self.prefix + self.curr_line) if has_visible_text(self.curr_line) else None

    def out(self, text):
        with lock:
            text = self.curr_line + text
            while True:
                line, sep, text = text.partition('\n')
                # sys.stderr.write('%s\n' % ((line, sep, text),))
                if sep:
                    # Avoid outputting lines that only contain control characters and whitespace
                    if has_visible_text(line):
                        clear_temp_output()
                        to_stderr(colorize(self.prefix + line) + sep)
                        # check_text_for_errors(context, line)
                else:
                    text = line
                    break
            self.curr_line = text
        update_temp_output()
        sys.stderr.flush()

    def check_text_for_errors(self, line):
        if 'Please increase the amount of inotify watches allowed per user' in line:
            out('(@error) *** You\'ve hit the inotify max_user_watches limit on (@r)%s(@error).\n' % (context._name_ansi,))
            current_limit = context.path('/proc/sys/fs/inotify/max_user_watches').read().strip()
            if current_limit:
                out('(@error) *** The current limit (from /proc/sys/fs/inotify/max_user_watches) is (@r)%s(@error).\n' % (current_limit,))
            if context._is_linux:
                out('(@error) *** To increase this limit, something like this might work:\n')
                out('(@error) *** echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p\n')
                out('(@error) *** Alternatively, you could also try reducing the total number of directories in your\n')
                out('(@error) *** gut repo by moving unused files to another folder.\n')

    def quote_fd(self, fd):
        def run():
            # import fcntl
            # make stdin a non-blocking file
            # fn = fd.fileno()
            # fl = fcntl.fcntl(fn, fcntl.F_GETFL)
            # fcntl.fcntl(fn, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            try:
                while True:
                    text = fd.readline()
                    if text and not shutting_down():
                        self.out(text.decode() + '\n')
                    else:
                        break
            except Exception as ex:
                if not shutting_down():
                    # self.out(str(ex))
                    raise
        run_daemon_thread(run)

    def quote_proc(self, proc, wait=True):
        self.quote_fd(proc.stdout)
        self.quote_fd(proc.stderr)
        if wait:
            proc.wait()

    def quote(self, thing, wait=True):
        if isinstance(thing, str):
            self.out(thing)
        elif hasattr(thing, 'stdout') and hasattr(thing, 'wait'):
            self.quote_proc(thing, wait=wait)
        elif hasattr(thing, 'read'):
            self.quote_fd(thing)
        else:
            raise Exception('terminal.Writer.quote doesn\'t know what to do with %s' % (thing,))


default_writer = Writer(None)

def out(text):
    default_writer.out(text)

def out_dim(text):
    default_writer.out(dim(text))

def quote(context, name, text):
    Writer(context, name).out(text)
