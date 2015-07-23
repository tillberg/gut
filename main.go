package main

import (
    "fmt"
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
    status.Printf("@(dim:We want git version) %s\n", desiredGitVersion)
    exists, err := ctx.PathExists(GutExePath)
    if err != nil { return false, err }
    if exists {
        status.Printf("We have it\n")
        return false, nil
        actualGutVersion, err := ctx.Output(ctx.AbsPath(GutExePath), "--version")
        if err != nil { return false, err }
        if strings.Contains(strings.TrimLeft(desiredGitVersion, "v"), string(actualGutVersion)) {
            status.Printf("We have the right version\n")
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
        err = ctx.UploadRecursiveExcludes(GutSrcPath, buildPath, []string{".git", "t"})
        if err != nil { return false, err }
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

func main() {
    log.EnableMultilineMode()
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
