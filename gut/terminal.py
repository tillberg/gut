import asyncio
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

_SHUTDOWN_OBJECT = '3qo4c8h56t349yo57yfv534wto8i7435oi5'

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
        for writer in writers:
            writer.shutdown()
        # These kind of run in the reverse order -- the first queues a task that tells run_forever not to actually run forever, while
        # run_forever processes that task as well as all other pending tasks
        asyncio.get_event_loop().call_soon(lambda: asyncio.get_event_loop().stop())
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        pass
    if exit:
        sys.exit(1)

def ansi(num):
    return '\033[%sm' % (num,)

RE_NON_WHITESPACE = re.compile('\S')
RE_ANSI = re.compile('\033\[\d*m')
RE_ANSI_OR_TEXT = re.compile('(\033\[\d*m)|(.)')
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
    return RE_NON_WHITESPACE.match(uncolorize(text))

def trim_ansi_string(text, max_len, ellipsis):
    if len(uncolorize(text)) <= max_len:
        return text
    _max_len = max_len - len(uncolorize(ellipsis))
    def get_some_text():
        length = 0
        for match in RE_ANSI_OR_TEXT.finditer(text):
            if match.group(1):
                yield match.group(1)
            else:
                _text = match.group(2)
                if length + len(_text) >= _max_len:
                    yield _text[:(_max_len - length)]
                    break
                else:
                    length += len(_text)
                    yield _text
    return ''.join((s for s in get_some_text())) + ellipsis

def get_nameish(context, name):
    return (context._name_ansi + (':' + name if name else '')) if context else '--'

writers = []
last_temp_output = ''

_terminal_columns = None
def get_terminal_cols():
    global _terminal_columns
    if _terminal_columns == None:
        _, _terminal_columns = plumbum.local['stty']['size'](stdin=None).strip().split()
    return int(_terminal_columns)

def clear_temp_output():
    global last_temp_output
    if last_temp_output:
        sys.stderr.write('\b \b' * len(last_temp_output))
        last_temp_output = ''

TEMP_OUTPUT_ELLIPSIS = colorize(dim(' ...'))
def update_temp_output():
    global last_temp_output
    curr_lines = [writer.get_curr_line() for writer in writers]
    curr_lines = [line for line in curr_lines if line]
    clear_temp_output()
    temp_output = colorize(' | '.join(curr_lines))
    if temp_output == last_temp_output:
        return
    clear_temp_output()
    max_len = get_terminal_cols() - 1
    temp_output = trim_ansi_string(temp_output, max_len, TEMP_OUTPUT_ELLIPSIS)
    if temp_output:
        sys.stderr.write(temp_output)
    last_temp_output = temp_output

class Writer:
    def __init__(self, context, name=None):
        self.context = context
        self.name = name
        self.prefix = '(@dim)[(@r)%s(@dim)](@r) ' % (get_nameish(context, name),)
        self.curr_line = ''
        writers.append(self)
        self.out_queue = asyncio.Queue()
        self.process_out()

    def shutdown(self):
        self.out(_SHUTDOWN_OBJECT)

    def get_curr_line(self):
        return (self.prefix + self.curr_line) if has_visible_text(self.curr_line) else None

    @asyncio.coroutine
    def _process_out(self):
        while True:
            items = []
            item = yield from self.out_queue.get()
            items.append(item)
            while not self.out_queue.empty():
                items.append(self.out_queue.get_nowait())
            if _SHUTDOWN_OBJECT in items:
                break
            text = self.curr_line + ''.join(items)
            while True:
                line, sep, text = text.partition('\n')
                if sep:
                    # Avoid outputting lines that only contain control characters and whitespace
                    if has_visible_text(line):
                        clear_temp_output()
                        sys.stderr.write(colorize(self.prefix + line) + sep)
                        self.check_text_for_errors(uncolorize(line))
                else:
                    text = line
                    break
            self.curr_line = text
            update_temp_output()
            sys.stderr.flush()

    def process_out(self):
        asyncio.get_event_loop().call_soon(lambda: asyncio.async(self._process_out()))

    def out(self, text):
        @asyncio.coroutine
        def _out():
            yield from self.out_queue.put(text)
        asyncio.async(_out())

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

    @asyncio.coroutine
    def quote_fd(self, fd, block=False):
        @asyncio.coroutine
        def run():
            try:
                eof_queue = asyncio.Queue() if block else None
                @asyncio.coroutine
                def eof():
                    yield from eof_queue.put(True)
                class MyProtocol(asyncio.Protocol):
                    def data_received(_self, data):
                        self.out(data.decode()) # XXX this isn't really safe to decode here
                    def eof_received(_self):
                        self.out('\n')
                        if block:
                            asyncio.async(eof())
                reader = asyncio.StreamReader()
                reader_protocol = MyProtocol()
                yield from asyncio.get_event_loop().connect_read_pipe(lambda: reader_protocol, fd)
                if block:
                    yield from eof_queue.get()
            except Exception as ex:
                if not shutting_down():
                    raise
        if block:
            yield from run()
        else:
            asyncio.async(run())

    @asyncio.coroutine
    def quote_proc(self, proc, wait=True):
        asyncio.async(Writer(self.context, self.name).quote_fd(proc.stderr))
        if wait:
            yield from self.quote_fd(proc.stdout, block=True)
        else:
            asyncio.async(self.quote_fd(proc.stdout))

    @asyncio.coroutine
    def quote(self, thing, wait=True):
        if isinstance(thing, str):
            self.out(thing)
        elif hasattr(thing, 'stdout') and hasattr(thing, 'wait'):
            yield from self.quote_proc(thing, wait=wait)
        elif hasattr(thing, 'read'):
            yield from self.quote_fd(thing)
        else:
            raise Exception('terminal.Writer.quote doesn\'t know what to do with %s' % (thing,))

default_writer = Writer(None)

def out(text):
    default_writer.out(text)

def out_dim(text):
    default_writer.out(dim(text))

def quote(context, name, text):
    Writer(context, name).out(text)
