import os
import threading

import plumbum

import config
import deps
from terminal import out, out_dim, dim, pipe_quote, color_host_path, kill_previous_process, save_process_pid, get_pidfile_path, active_pidfiles, shutting_down

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

def watch_for_changes(context, path, event_prefix, event_queue):
    proc = None
    with context.cwd(context.path(path)):
        watched_root = context['pwd']().strip()
        def run_watcher():
            watcher = None
            if context['which']['inotifywait'](retcode=None).strip():
                inotify_events = ['modify', 'attrib', 'move', 'create', 'delete']
                watcher = context['inotifywait']['--quiet', '--monitor', '--recursive', '--format', '%w%f', '--exclude', '\.gut/']
                for event in inotify_events:
                    watcher = watcher['--event', event]
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
        try:
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
        except Exception:
            if not shutting_down():
                raise
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
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
