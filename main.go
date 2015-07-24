package main

import (
    "io"
    "os"
    "strings"
    "syscall"
    "github.com/jessevdk/go-flags"
    "github.com/tillberg/ansi-log"
)

var OptsCommon struct {
    Verbose bool `short:"v" long:"verbose" description:"Show verbose debug information"`
    Version bool `long:"version"`
    NoColor bool `long:"no-color"`
    InstallDeps bool `long:"install-deps"`
}

var OptsSync struct {
    IdentityFile string `short:"i" long:"identity"`
    Dev bool `long:"dev"`
    Positional struct {
        LocalPath  string
        RemotePath string
    } `positional-args:"yes" required:"yes"`
}

func EnsureBuild(local *SyncContext, ctx *SyncContext) (didSomething bool, err error) {
    status := ctx.Logger()
    desiredGitVersion := GitVersion
    if ctx.IsWindows() {
        desiredGitVersion = GitWinVersion
    }
    exists, err := ctx.PathExists(GutExePath)
    if err != nil { return false, err }
    if exists {
        actualGutVersion, err := ctx.Output(ctx.AbsPath(GutExePath), "--version")
        if err != nil { return false, err }
        if strings.Contains(string(actualGutVersion), strings.TrimLeft(desiredGitVersion, "v")) {
            return false, nil
        }
    }
    status.Printf("@(dim:Need to build gut on) %s@(dim:.)\n", ctx.NameAnsi())
    err = EnsureGutFolders(ctx)
    if err != nil { return false, err }
    err = GutBuildPrepare(local, ctx)
    if err != nil { return false, err }
    var buildPath string
    if ctx.IsLocal() {
        if ctx.IsWindows() {
            buildPath = GutWinSrcPath
        } else {
            buildPath = GutSrcPath
        }
    } else {
        buildPath = GutSrcTmpPath
        status.Printf("@(dim:Uploading) %s @(dim:to) %s@(dim:...)", local.PathAnsi(GutSrcPath), ctx.PathAnsi(buildPath))
        chanErr := make(chan error)
        stdinChan := make(chan io.Writer)
        go func() {
            Mkdirp(ctx, buildPath)
            err := ctx.QuotePipeIn("untar", stdinChan, ctx.AbsPath(buildPath), "tar", "xf", "-")
            chanErr<-err
        }()
        ctxStdin := <-stdinChan
        err = local.QuotePipeOut("tar", ctxStdin, local.AbsPath(GutSrcPath), "tar", "cf", "-", "--exclude=.git", "--exclude=t", "./")
        if err != nil { return false, err }
        err = <-chanErr
        if err != nil { return false, err }
        status.Printf("@(dim: done.)\n")
    }
    err = GutBuild(ctx, buildPath)
    if err != nil { return false, err }
    status.Printf("@(dim:Cleaning up...)")
    err = GutUnprepare(local, ctx)
    if err != nil { return false, err }
    status.Printf("@(dim: done.)\n")
    return true, nil
}

func doSession(ctx *SyncContext, done chan bool) {
    err := ctx.QuoteShell("test", "echo -n 'working... '; sleep 0.01; hostname")
    if err != nil {
        log.Fatalf("unable to connect: %s", err)
    }
    done <- true
}

func Sync(local *SyncContext, remote *SyncContext) (err error) {
    status := local.NewLogger("sync")
    status.Printf("@(dim:Syncing) %s @(dim:with) %s\n", local.SyncPathAnsi(), remote.SyncPathAnsi())

    _, err = EnsureBuild(local, local)
    if err != nil { return err }
    _, err = EnsureBuild(local, remote)
    if err != nil { return err }

    // yield from ensure_build(local)
    // yield from ensure_build(remote)

    // ports = util.find_open_ports([local, remote], 3)
    // # out(dim('Using ports ') + dim(', ').join([unicode(port) for port in ports]) +'\n')
    // gutd_bind_port, gutd_connect_port, autossh_monitor_port = ports

    // local_tail_hash = get_tail_hash(local, local_path)
    // remote_tail_hash = get_tail_hash(remote, remote_path)
    // tail_hash = None

    // yield from util.start_ssh_tunnel(local, remote, gutd_bind_port, gutd_connect_port, autossh_monitor_port)

    // @asyncio.coroutine
    // def cross_init(src_context, src_path, dest_context, dest_path):
    //     yield from gut_cmd.daemon(src_context, src_path, tail_hash, gutd_bind_port)
    //     yield from gut_cmd.init(dest_context, dest_path)
    //     gut_cmd.setup_origin(dest_context, dest_path, tail_hash, gutd_connect_port)
    //     import time
    //     time.sleep(2) # Give the gut-daemon and SSH tunnel a moment to start up
    //     yield from gut_cmd.pull(dest_context, dest_path)
    //     yield from gut_cmd.daemon(dest_context, dest_path, tail_hash, gutd_bind_port)

    // # Do we need to initialize local and/or remote gut repos?
    // if not local_tail_hash or local_tail_hash != remote_tail_hash:
    //     status.out('(@dim)Local gut repo base commit: [' + color_commit(local_tail_hash) + '(@dim)]\n')
    //     status.out('(@dim)Remote gut repo base commit: [' + color_commit(remote_tail_hash) + '(@dim)]\n')
    //     if local_tail_hash and not remote_tail_hash:
    //         tail_hash = local_tail_hash
    //         assert_folder_empty(remote, remote_path)
    //         status.out('(@dim)Initializing remote repo from local repo...\n')
    //         yield from cross_init(local, local_path, remote, remote_path, )
    //     elif remote_tail_hash and not local_tail_hash:
    //         tail_hash = remote_tail_hash
    //         assert_folder_empty(local, local_path)
    //         status.out('(@dim)Initializing local folder from remote gut repo...\n')
    //         yield from cross_init(remote, remote_path, local, local_path)
    //     elif not local_tail_hash and not remote_tail_hash:
    //         assert_folder_empty(remote, remote_path)
    //         assert_folder_empty(local, local_path)
    //         status.out('(@dim)Initializing both local and remote gut repos...\n')
    //         status.out('(@dim)Initializing local repo first...\n')
    //         yield from gut_cmd.init(local, local_path)
    //         yield from gut_cmd.ensure_initial_commit(local, local_path)
    //         tail_hash = get_tail_hash(local, local_path)
    //         status.out('(@dim)Initializing remote repo from local repo...\n')
    //         yield from cross_init(local, local_path, remote, remote_path)
    //     else:
    //         status.out('(@error)Cannot sync incompatible gut repos:\n')
    //         status.out('(@error)Local initial commit hash: [%s(@error)]\n' % (color_commit(local_tail_hash),))
    //         status.out('(@error)Remote initial commit hash: [%s(@error)]\n' % (color_commit(remote_tail_hash),))
    //         shutdown()
    // else:
    //     tail_hash = local_tail_hash
    //     yield from gut_cmd.daemon(local, local_path, tail_hash, gutd_bind_port)
    //     yield from gut_cmd.daemon(remote, remote_path, tail_hash, gutd_bind_port)
    //     # XXX The gut daemons are not necessarily listening yet, so this could result in races with commit_and_update calls below

    // gut_cmd.setup_origin(local, local_path, tail_hash, gutd_connect_port)
    // gut_cmd.setup_origin(remote, remote_path, tail_hash, gutd_connect_port)

    // @asyncio.coroutine
    // def commit_and_update(src_system, changed_paths=None, update_untracked=False):
    //     if src_system == 'local':
    //         src_context = local
    //         src_path = local_path
    //         dest_context = remote
    //         dest_path = remote_path
    //         dest_system = 'remote'
    //     else:
    //         src_context = remote
    //         src_path = remote_path
    //         dest_context = local
    //         dest_path = local_path
    //         dest_system = 'local'

    //     # Based on the set of changed paths, figure out what we need to pass to `gut add` in order to capture everything
    //     if not changed_paths:
    //         prefix = '.'
    //     # This is kind of annoying because it regularly picks up .gutignored files, e.g. the ".#." files emacs drops:
    //     # elif len(changed_paths) == 1:
    //     #     (prefix,) = changed_paths
    //     else:
    //         # commonprefix operates on strings, not paths; so lop off the last bit of the path so that if we get two files within
    //         # the same directory, e.g. "test/sarah" and "test/sally", we'll look in "test/" instead of in "test/sa".
    //         separator = '\\' if src_context._is_windows else '/'
    //         prefix = os.path.commonprefix(changed_paths).rpartition(separator)[0] or '.'
    //     # out('system: %s\npaths: %s\ncommon prefix: %s\n' % (src_system, ' '.join(changed_paths) if changed_paths else '', prefix))

    //     try:
    //         if (yield from gut_cmd.commit(src_context, src_path, prefix, update_untracked=update_untracked)):
    //             yield from gut_cmd.pull(dest_context, dest_path)
    //     except plumbum.commands.ProcessExecutionError:
    //         status.out('\n\n(@error)Error during commit-and-pull:\n')
    //         traceback.print_exc(file=sys.stderr)

    // event_queue = asyncio.Queue()
    // SHUTDOWN_STR = '3qo4c8h56t349yo57yfv534wto8i7435oi5'
    // def shutdown_watch_consumer():
    //     @asyncio.coroutine
    //     def _shutdown_watch_consumer():
    //         yield from event_queue.put(SHUTDOWN_STR)
    //     asyncio.async(_shutdown_watch_consumer())
    // on_shutdown(shutdown_watch_consumer)

    // yield from util.watch_for_changes(local, local_path, 'local', event_queue)
    // yield from util.watch_for_changes(remote, remote_path, 'remote', event_queue)
    // # The filesystem watchers are not necessarily listening to all updates yet, so we could miss file changes that occur between the
    // # commit_and_update calls below and the time that the filesystem watches are attached.

    // yield from commit_and_update('remote', update_untracked=True)
    // yield from commit_and_update('local', update_untracked=True)
    // yield from gut_cmd.pull(remote, remote_path)
    // yield from gut_cmd.pull(local, local_path)

    // changed = {}
    // changed_ignore = set()
    // while True:
    //     try:
    //         fut = event_queue.get()
    //         event = yield from (asyncio.wait_for(fut, 0.1) if changed else fut)
    //     except asyncio.TimeoutError:
    //         for system, paths in changed.items():
    //             yield from commit_and_update(system, paths, update_untracked=(system in changed_ignore))
    //         changed.clear()
    //         changed_ignore.clear()
    //     else:
    //         if event == SHUTDOWN_STR:
    //             break
    //         system, path = event
    //         # Ignore events inside the .gut folder; these should also be filtered out in inotifywait/fswatch/etc if possible
    //         path_parts = path.split(os.sep)
    //         if not '.gut' in path_parts:
    //             if system not in changed:
    //                 changed[system] = set()
    //             changed[system].add(path)
    //             if path_parts[-1] == '.gutignore':
    //                 changed_ignore.add(system)
    //                 status.out('changed_ignore %s on %s\n' % (path, system))
    //             else:
    //                 status.out('changed %s %s\n' % (system, path))
    //         else:
    //             status.out('ignoring changed %s %s\n' % (system, path))

    return nil
}

func main() {
    // log.EnableMultilineMode()
    log.EnableColorTemplate()
    log.AddAnsiColorCode("error", 31)
    log.AddAnsiColorCode("commit", 32)
    status := log.New(os.Stderr, "", 0)
    var args []string = os.Args[1:]
    if len(args) == 0 {
        status.Fatalln("You must specify a gut-command, e.g. `gut sync ...`")
    }
    var cmd = args[0]
    args = args[1:]
    if IsGitCommand(cmd) {
        var gutExe = PathInUserHome(GutExePath)
        syscall.Exec(gutExe, append([]string { gutExe }, args...), os.Environ())
        status.Fatalf("Failed to exec %s", gutExe)
    }
    var argsRemaining, err = flags.ParseArgs(&OptsCommon, args)
    if err != nil { status.Fatal(err) }
    // fmt.Printf("color: %s\n", OptsCommon.NoColor)
    if OptsCommon.Version {
        status.Print("gut-sync version XXXXX")
        os.Exit(0)
    }
    if cmd == "build" {
        var local = NewSyncContext()
        err := local.Connect()
        if err != nil { status.Fatal(err) }
        didSomething, err := EnsureBuild(local, local)
        if err != nil { status.Fatal(err) }
        if !didSomething {
            status.Printf("@(dim:gut) " + GitVersion + " @(dim:has already been built.)\n")
        }
    } else if cmd == "sync" {
        var _, err = flags.ParseArgs(&OptsSync, argsRemaining)
        if err != nil { status.Fatal(err) }

        local := NewSyncContext()
        err = local.ParseSyncPath(OptsSync.Positional.LocalPath)
        if err != nil { status.Fatal(err) }
        err = local.Connect()
        if err != nil { status.Fatal(err) }
        remote := NewSyncContext()
        err = remote.ParseSyncPath(OptsSync.Positional.RemotePath)
        if err != nil { status.Fatalln(err) }
        err = remote.Connect()
        if err != nil { status.Fatal(err) }

        err = Sync(local, remote)
        if err != nil { status.Fatal(err) }
    }

}
