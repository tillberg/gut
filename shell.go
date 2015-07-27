package main

import (
    "errors"
    "fmt"
    "io"
    "os"
    "os/signal"
    "strings"
    "sync"
    "syscall"
    "time"
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
        stdinChan := make(chan io.WriteCloser)
        go func() {
            ctx.Mkdirp(buildPath)
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

const commitDebounceDuration = 100 * time.Millisecond
func Sync(local *SyncContext, remote *SyncContext) (err error) {
    status := local.NewLogger("sync")
    defer status.Close()
    status.Printf("@(dim:Syncing) %s @(dim:with) %s\n", local.SyncPathAnsi(), remote.SyncPathAnsi())

    _, err = EnsureBuild(local, local)
    if err != nil { status.Bail(err) }
    _, err = EnsureBuild(local, remote)
    if err != nil { status.Bail(err) }

    ports, err := FindOpenPorts(3, local, remote)
    if err != nil { status.Bail(err) }
    // status.Printf("Using ports %v\n", ports)
    gutdBindPort := ports[0]
    gutdConnectPort := ports[1]
    autosshMonitorPort := ports[2]

    err = StartSshTunnel(local, remote, gutdBindPort, gutdConnectPort, autosshMonitorPort)
    if err != nil { status.Bail(err) }

    localTailHash, err := GetTailHash(local)
    if err != nil { status.Bail(err) }
    remoteTailHash, err := GetTailHash(remote)
    if err != nil { status.Bail(err) }
    tailHash := ""

    startGutDaemon := func(ctx *SyncContext) error { return GutDaemon(ctx, tailHash, gutdBindPort) }
    setupGutOrigin := func(ctx *SyncContext) error { return GutSetupOrigin(ctx, tailHash, gutdConnectPort) }
    crossInit := func(src *SyncContext, dest *SyncContext) (err error) {
        err = startGutDaemon(src)
        if err != nil { status.Bail(err) }
        err = GutInit(dest)
        if err != nil { status.Bail(err) }
        err = setupGutOrigin(dest)
        if err != nil { status.Bail(err) }
        time.Sleep(2) // Give the gut-daemon and SSH tunnel a moment to start up
        err = GutPull(dest)
        if err != nil { status.Bail(err) }
        err = startGutDaemon(dest)
        return err
    }

    if localTailHash == "" || localTailHash != remoteTailHash {
        status.Printf("@(dim:Local gut repo base commit: [)@(commit:%s)@(dim:])\n", TrimCommit(localTailHash))
        status.Printf("@(dim:Remote gut repo base commit: [)@(commit:%s)@(dim:])\n", TrimCommit(remoteTailHash))
        if localTailHash != "" && remoteTailHash == "" {
            tailHash = localTailHash
            err = AssertSyncFolderIsEmpty(remote)
            if err != nil { status.Bail(err) }
            status.Printf("@(dim)Initializing remote repo from local repo...\n")
            err = crossInit(local, remote)
            if err != nil { status.Bail(err) }
        } else if remoteTailHash != "" && localTailHash == "" {
            tailHash = remoteTailHash
            err = AssertSyncFolderIsEmpty(local)
            if err != nil { status.Bail(err) }
            status.Printf("@(dim)Initializing local repo from remote repo...\n")
            err = crossInit(remote, local)
            if err != nil { status.Bail(err) }
        } else if localTailHash == "" && remoteTailHash == "" {
            err = AssertSyncFolderIsEmpty(local)
            if err != nil { status.Bail(err) }
            err = AssertSyncFolderIsEmpty(remote)
            if err != nil { status.Bail(err) }
            status.Printf("@(dim)Initializing both local and remote gut repos...\n")
            status.Printf("@(dim)Initializing local repo first...\n")
            err = GutInit(local)
            if err != nil { status.Bail(err) }
            err = GutEnsureInitialCommit(local)
            if err != nil { status.Bail(err) }
            tailHash, err = GetTailHash(local)
            if err != nil { status.Bail(err) }
            if tailHash == "" {
                return errors.New(fmt.Sprintf("Failed to initialize new gut repo in %s", local.SyncPathAnsi()))
            }
            status.Printf("@(dim)Initializing remote repo from local repo...\n")
            err = crossInit(local, remote)
            if err != nil { status.Bail(err) }
        } else {
            Shutdown(status.Colorify("@(error:Cannot sync incompatible gut repos.)"))
        }
    } else {
        // This is the happy path where the local and remote repos are already initialized and are compatible.
        tailHash = localTailHash
        err = startGutDaemon(local)
        if err != nil { status.Bail(err) }
        err = startGutDaemon(remote)
        if err != nil { status.Bail(err) }
        // XXX The gut daemons are not necessarily listening yet, so this could result in races with commit_and_update calls below
    }

    err = setupGutOrigin(local)
    if err != nil { status.Bail(err) }
    err = setupGutOrigin(remote)
    if err != nil { status.Bail(err) }

    commitAndUpdate := func(src *SyncContext, changedPaths []string, updateUntracked bool) (err error) {
        var dest *SyncContext
        if src == local {
            dest = remote
        } else {
            dest = local
        }
        prefix := CommonPathPrefix(changedPaths...)
        if prefix != "" {
            // git is annoying if you try to git-add git-ignored files (printing a message that is very helpful when there is a human
            // attached to stdin/stderr), so let's always just target the last *folder* by lopping off everything after the last slash:
            lastIndex := strings.LastIndex(prefix, "/")
            if lastIndex == -1 {
                prefix = ""
            } else {
                prefix = prefix[:lastIndex+1]
            }
        }
        if prefix == "" {
            prefix = "."
        }
        changed, err := GutCommit(src, prefix, updateUntracked)
        if err != nil { status.Bail(err) }
        if changed {
            return GutPull(dest)
        }
        return nil
    }

    type FileEvent struct {
        ctx *SyncContext
        filepath string
    }
    eventChan := make(chan FileEvent)
    fileEventCallbackGen := func(ctx *SyncContext) func(filepath string) {
        return func(filepath string) {
            eventChan<-FileEvent{ctx, filepath}
        }
    }

    WatchForChanges(local, fileEventCallbackGen(local))
    WatchForChanges(remote, fileEventCallbackGen(remote))
    // The filesystem watchers are not necessarily listening to all updates yet, so we could miss file changes that occur between the
    // commit_and_update calls below and the time that the filesystem watches are attached.

    commitAndUpdate(remote, []string{}, true)
    commitAndUpdate(local, []string{}, true)
    GutPull(remote)
    GutPull(local)

    var haveChanges bool
    var changedPaths map[*SyncContext]map[string]bool
    var changedIgnore map[*SyncContext]bool
    clearChanges := func() {
        haveChanges = false
        changedPaths = make(map[*SyncContext]map[string]bool)
        changedIgnore = make(map[*SyncContext]bool)
    }
    clearChanges()
    flushChanges := func() {
        for ctx, pathMap := range changedPaths {
            paths := []string{}
            for path, _ := range pathMap {
                paths = append(paths, path)
            }
            _, changedThisIgnore := changedIgnore[ctx]
            commitAndUpdate(ctx, paths, changedThisIgnore)
        }
        clearChanges()
    }

    var event FileEvent
    for {
        if haveChanges {
            select {
                case event = <-eventChan:
                    break
                case <-time.After(commitDebounceDuration):
                    flushChanges()
                    continue
            }
        } else {
            event = <-eventChan
        }
        parts := strings.Split(event.filepath, "/")
        skip := false
        for _, part := range parts {
            if part == ".gut" {
                skip = true
            } else if part == ".gutignore" {
                changedIgnore[event.ctx] = true
            }
        }
        if skip { continue }
        // status.Printf("@(dim:[)%s@(dim:] changed on) %s\n", event.filepath, event.ctx.NameAnsi())
        haveChanges = true
        ctxChanged, ok := changedPaths[event.ctx]
        if !ok {
             ctxChanged = make(map[string]bool)
             changedPaths[event.ctx] = ctxChanged
        }
        ctxChanged[event.filepath] = true
    }
    status.Printf("Exiting Sync because it's not finished.\n")
    return nil
}

var shutdownLock sync.Mutex
func Shutdown(reason string) {
    shutdownLock.Lock()
    status := log.New(os.Stderr, "", 0)
    if reason != "" {
        status.Printf("%s ", reason)
    }
    status.Printf("Stopping all subprocesses...")
    done := make(chan bool)
    for _, _ctx := range AllSyncContexts {
        go func(ctx *SyncContext) {
            ctx.KillAllSessions()
            // This generally shouldn't *do* anything other than
            // clean up the PID files, as the killing would have
            // been done already in KillAllSessions.
            ctx.KillAllViaPidfiles()
            ctx.Close()
            done<-true
        }(_ctx)
    }
    for _, _ = range AllSyncContexts {
        <-done
    }
    status.Printf(" Exiting.")
    fmt.Println()
    os.Exit(1)
}

func main() {
    log.EnableMultilineMode()
    log.EnableColorTemplate()
    log.AddAnsiColorCode("error", 31)
    log.AddAnsiColorCode("commit", 32)
    status := log.New(os.Stderr, "", 0)
    status.Printf("Process ID: %d\n", os.Getpid())
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

    signalChan := make(chan os.Signal, 1)
    signal.Notify(signalChan, os.Interrupt)
    go func() {
        <-signalChan
        Shutdown("Received SIGINT.")
    }()

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
        local.KillAllViaPidfiles()

        remote := NewSyncContext()
        err = remote.ParseSyncPath(OptsSync.Positional.RemotePath)
        if err != nil { status.Fatal(err) }
        err = remote.Connect()
        if err != nil { status.Fatal(err) }
        remote.KillAllViaPidfiles()

        err = Sync(local, remote)
        if err != nil { status.Fatal(err) }
    }
}
