import asyncio
import os
import random
import sys
import time

from . import config
from . import deps
from .terminal import color_host_path, kill_previous_process, save_process_pid, get_pidfile_path, active_pidfiles, shutdown, on_shutdown, quote_proc, get_cmd, Writer

def rsync(src_context, src_path, dest_context, dest_path, excludes=[]):
    def get_path_str(context, path):
        return '%s%s%s/' % (context._ssh_address, ':' if context._ssh_address else '', context.path(path),)
    status = Writer(src_context, '(@dim)rsync')
    src_path_str = get_path_str(src_context, src_path)
    dest_path_str = get_path_str(dest_context, dest_path)
    status.out('(@dim)Uploading (@r)%s (@dim)to (@r)%s(@dim)...' % (color_host_path(src_context, src_path), color_host_path(dest_context, dest_path)))
    mkdirp(dest_context, dest_path)
    if src_context._is_windows:
        root_path = os.path.normpath(os.path.expanduser(str(src_path)))
        for root, folders, files in os.walk(root_path):
            dest_folder = dest_context.path(dest_path) / os.path.relpath(root, root_path).replace('\\', '/')
            mkdirp(dest_context, dest_folder)
            for filename in files:
                if filename not in excludes:
                    abs_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(abs_path, root_path)
                    remote_path = dest_context.path(dest_path) / rel_path.replace('\\', '/')
                    # status.out('Uploading ' + rel_path + ' to ' +  unicode(remote_path) + '...')
                    dest_context.upload(src_context.path(abs_path), remote_path)
                    if '.' not in filename  or filename.endswith('.sh'):
                        # status.out(' CHMOD +x %s' % (remote_path,))
                        dest_context['chmod']['+x', remote_path]()
                    # status.out(' done.\n')
            orig_folders = tuple(folders)
            del folders[:]
            for folder in orig_folders:
                if folder not in excludes:
                    folders.append(folder)
    else:
        rsync = plumbum.local['rsync']['-a']
        for exclude in excludes:
            rsync = rsync['--exclude=%s' % (exclude,)]
        rsync[src_path_str, dest_path_str]()
    status.out('(@dim) done.\n')

INOTIFY_CHANGE_EVENTS = ['modify', 'attrib', 'move', 'create', 'delete']
def append_inotify_change_events(context, watcher):
    if context._is_windows:
        return watcher['--event', ','.join(INOTIFY_CHANGE_EVENTS)]
    for event in INOTIFY_CHANGE_EVENTS:
        watcher = watcher['--event', event]
    return watcher

@asyncio.coroutine
def watch_for_changes(context, path, event_prefix, event_queue):
    status = None
    proc = None
    with context.cwd(context.path(path)):
        watched_root = (context['cmd']['/c', 'cd ,']() if context._is_windows else context['pwd']()).strip()
        @asyncio.coroutine
        def run_watcher():
            watch_type = get_cmd(context, ['inotifywait', 'fswatch'])
            watcher = None
            if watch_type == 'inotifywait':
                # inotify-win has slightly different semantics (and a completely different regex engine) than inotify-tools
                format_str = '%w\%f' if context._is_windows else '%w%f'
                exclude_str = '\\.gut($|\\\\)' if context._is_windows else '\.gut/'
                watcher = context['inotifywait']['--quiet', '--monitor', '--recursive', '--format', format_str, '--exclude', exclude_str]
                watcher = append_inotify_change_events(context, watcher)
                watcher = watcher['./']
            elif watch_type == 'fswatch':
                watcher = context['fswatch']['./']
            else:
                raise Exception('missing ' + ('fswatch' if context._is_osx else 'inotifywait'))
            status = Writer(context, '(@dim)' + watch_type)
            status.out('(@dim)Using (@r)%s (@dim)to listen for changes in (@r)%s\n' % (watch_type, context._sync_path))
            kill_previous_process(context, watch_type)
            _proc = watcher.popen()
            save_process_pid(context, watch_type, _proc.pid)
            return _proc
        proc = (yield from deps.retry_method(context, run_watcher))
    shutting_down = []
    @asyncio.coroutine
    def run():
        reader = asyncio.StreamReader()
        reader_protocol = asyncio.StreamReaderProtocol(reader)
        asyncio.get_event_loop().connect_read_pipe(lambda: reader_protocol, proc.stdout)
        while not shutting_down:
            line = yield from reader.readline()
            if line != '':
                changed_path = line.rstrip()
                changed_path = os.path.abspath(os.path.join(watched_root, changed_path))
                rel_path = os.path.relpath(changed_path, watched_root)
                status.out('changed_path: ' + changed_path + '\n')
                status.out('watched_root: ' + watched_root + '\n')
                status.out('changed ' + changed_path + ' -> ' + rel_path + '\n')
                yield from event_queue.put((event_prefix, rel_path))
            else:
                break
    on_shutdown(lambda: shutting_down.append(True))
    asyncio.async(run())
    asyncio.async(Writer(context, 'watch_%s' % (event_prefix,)).quote_fd(proc.stderr))

@asyncio.coroutine
def start_ssh_tunnel(local, remote, gutd_bind_port, gutd_connect_port, autossh_monitor_port):
    cmd = get_cmd(local, ['autossh', 'ssh'])
    if not cmd:
        deps.missing_dependency(local, 'ssh')
    ssh_tunnel_opts = '%s:localhost:%s' % (gutd_connect_port, gutd_bind_port)
    kill_previous_process(local, cmd)
    command = local[cmd]
    if cmd == 'autossh' and local._is_osx:
        command = command['-M', autossh_monitor_port]
    command = command['-N', '-L', ssh_tunnel_opts, '-R', ssh_tunnel_opts, remote._ssh_address]
    proc = command.popen()
    save_process_pid(local, cmd, proc.pid)
    asyncio.async(quote_proc(local, cmd + '_out', proc, wait=False))

@asyncio.coroutine
def restart_on_change(exe_path):
    local = plumbum.local
    status = Writer(local, '(@dim)dev-mode')
    watch_path = os.path.dirname(os.path.abspath(__file__))
    try:
        changed = append_inotify_change_events(local, local['inotifywait'])['--quiet', '--recursive', '--', local.path(watch_path)]() # blocks until there's a change
    except plumbum.commands.ProcessExecutionError:
        status.out('(@error)inotifywait exited with non-zero status')
    else:
        status.out('\n(@dim)Restarting due to [(@r)%s(@dim)]...\n' % (changed.strip(),))
        while True:
            try:
                os.execv(str(exe_path), sys.argv)
            except Exception as ex:
                status.out('(@error)error restarting: %s\n' % (ex,))
                time.sleep(1)

def mkdirp(context, path):
    if context._is_windows:
        if context._is_local:
            _path = os.path.normpath(os.path.expanduser(str(path)))
            if not os.path.exists(_path):
                os.makedirs(_path)
        else:
            raise Exception('Remote Windows not supported')
    else:
        context['mkdir']['-p', context.path(path)]()

def get_num_cores(context):
    if context._is_windows:
        return context['wmic']['CPU', 'Get', 'NumberOfLogicalProcessors', '/Format:List']().strip().split('=')[-1]
    else:
        return context['getconf']['_NPROCESSORS_ONLN']().strip()

def find_open_ports(contexts, num_ports):
    if not num_ports:
        return []
    netstats = ' '.join([context['netstat']['-an' if context._is_windows else '-anl']() for context in contexts])
    ports = []
    random_ports = list(range(config.MIN_RANDOM_PORT, config.MAX_RANDOM_PORT + 1))
    random.shuffle(random_ports)
    for port in random_ports:
        if not str(port) in netstats:
            ports.append(port)
        if len(ports) == num_ports:
            return ports
    raise Exception('Not enough available ports found')
