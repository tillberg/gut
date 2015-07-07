import os
import sys
import time

import plumbum

import config
import deps
from terminal import out, out_dim, dim, pipe_quote, color_host_path, kill_previous_process, save_process_pid, get_pidfile_path, active_pidfiles, shutting_down, shutdown, run_daemon_thread

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

INOTIFY_CHANGE_EVENTS = ['modify', 'attrib', 'move', 'create', 'delete']
def append_inotify_change_events(watcher):
    for event in INOTIFY_CHANGE_EVENTS:
        watcher = watcher['--event', event]
    return watcher

def watch_for_changes(context, path, event_prefix, event_queue):
    proc = None
    with context.cwd(context.path(path)):
        watched_root = context['pwd']().strip()
        def run_watcher():
            watcher = None
            if context['which']['inotifywait'](retcode=None).strip():
                watcher = context['inotifywait']['--quiet', '--monitor', '--recursive', '--format', '%w%f', '--exclude', '\.gut/']
                watcher = append_inotify_change_events(watcher)
                watcher = watcher['./']
                watch_type = 'inotifywait'
            elif context['which']['fswatch'](retcode=None).strip():
                watcher = context['fswatch']['./']
                watch_type = 'fswatch'
            else:
                raise Exception('missing ' + ('fswatch' if context._is_osx else 'inotifywait'))
            out(dim('Using ') + watch_type + dim(' to listen for changes in ') + context._sync_path + '\n')
            kill_previous_process(context, watch_type)
            proc = watcher.popen()
            save_process_pid(context, watch_type, proc.pid)
            return proc
        proc = deps.retry_method(context, run_watcher)
    def run():
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
    run_daemon_thread(run)
    pipe_quote(proc.stderr, 'watch_%s_err' % (event_prefix,))

def start_ssh_tunnel(local, remote):
    if not local['which']['autossh'](retcode=None).strip():
        deps.missing_dependency(local, 'autossh')
    ssh_tunnel_opts = '%s:localhost:%s' % (config.GUTD_CONNECT_PORT, config.GUTD_BIND_PORT)
    kill_previous_process(local, 'autossh')
    autossh = local['autossh']
    if local._is_osx:
        autossh = autossh['-M', config.AUTOSSH_MONITOR_PORT]
    autossh = autossh['-N', '-L', ssh_tunnel_opts, '-R', ssh_tunnel_opts, remote._ssh_address]
    proc = autossh.popen()
    save_process_pid(local, 'autossh', proc.pid)
    # If we got something on autossh_err like: "channel_setup_fwd_listener_tcpip: cannot listen to port: 34925", we could try `fuser -k -n tcp 34925`
    pipe_quote(proc.stdout, 'autossh_out')
    pipe_quote(proc.stderr, 'autossh_err')

def restart_on_change(exe_path):
    def run():
        local = plumbum.local
        watch_path = os.path.dirname(os.path.abspath(__file__))
        changed = append_inotify_change_events(local['inotifywait'])[local.path(watch_path)]() # blocks until there's a change
        out_dim('\n(dev-mode) Restarting due to [%s]...\n' % (changed.strip(),))
        while True:
            try:
                os.execv(unicode(exe_path), sys.argv)
            except Exception as ex:
                out('error restarting: %s\n' % (ex,))
                time.sleep(1)
    run_daemon_thread(run)

def mkdirp(context, path):
    if context._is_windows:
        if context == plumbum.local:
            _path = os.path.normpath(os.path.expanduser(path))
            if not os.path.exists(_path):
                os.makedirs(_path)
        else:
            raise Exception('Remote Windows not supported')
    else:
        context['mkdir']['-p', path]()
