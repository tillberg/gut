package main

import (
    "fmt"
    "os"
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

func EnsureBuild(ctx *SyncContext) (bool, error) {
    status := ctx.Logger()
    desiredGitVersion := GitVersion
    if ctx.IsWindows() {
        desiredGitVersion = GitWinVersion
    }
    status.Printf("@(dim:We want git version) %s\n", desiredGitVersion)
    // if not gut_cmd.exe_path(context).exists() or desired_git_version.lstrip('v') not in gut_cmd.get_version(context):
    //     status.out('(@dim)Need to build gut on ' + context._name_ansi + '(@dim).(@r)\n')
    //     gut_build.ensure_gut_folders(context)
    //     yield from gut_build.prepare(context)
    //     if context != plumbum.local:
    //         # If we're building remotely, rsync the prepared source to the remote host
    //         build_path = config.GUT_SRC_TMP_PATH
    //         yield from util.rsync(plumbum.local, config.GUT_SRC_PATH, context, build_path, excludes=['.git', 't'])
    //     else:
    //         build_path = config.GUT_WIN_SRC_PATH if context._is_windows else config.GUT_SRC_PATH
    //     yield from gut_build.build(context, build_path)
    //     status.out('(@dim)Cleaning up...(@r)')
    //     yield from gut_build.unprepare(context)
    //     if context != plumbum.local:
    //         context['rm']['-r', context.path(config.GUT_SRC_TMP_PATH)]()
    //     status.out('(@dim) done.(@r)\n')
    //     return True
    return false, nil
}

func doSession(ctx *SyncContext, done chan bool) {
    err := ctx.RunShell("echo -n 'working... '; sleep 0.01; hostname")
    if err != nil {
        log.Fatalf("unable to connect: %s", err)
    }
    done <- true
}

func main() {
    log.EnableMultilineMode()
    log.EnableColorTemplate()
    log.AddAnsiColorCode("host", 33)
    log.AddAnsiColorCode("path", 36)
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
        local.Connect()
        didSomething, err := EnsureBuild(local)
        if err != nil { status.Fatal(err) }
        if !didSomething {
            status.Printf("@(dim:gut) " + GitVersion + " @(dim:has already been built.)\n")
        }
    } else if cmd == "sync" {
        var _, err = flags.ParseArgs(&OptsSync, argsRemaining)
        if err != nil { status.Fatal(err) }

        local := NewSyncContext()
        err = local.ParseSyncPath(OptsSync.Positional.LocalPath)
        if err != nil { status.Fatalln(err) }
        remote := NewSyncContext()
        err = remote.ParseSyncPath(OptsSync.Positional.RemotePath)
        if err != nil { status.Fatalln(err) }
        fmt.Printf("local: %s\n", local)
        fmt.Printf("remote: %s\n", remote)

        done := make(chan bool)
        num := 100
        for i := 0; i < num; i++ {
            go doSession(remote, done)
            go doSession(local, done)
        }
        for i := 0; i < num; i++ {
            <-done
            <-done
        }
    }

}
