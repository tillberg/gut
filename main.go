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

func doSession(ctx *SyncContext, done chan bool) {
    err := ctx.RunShell("echo -n 'working... '; sleep 0.1; echo done.") //"/usr/bin/whoami"
    if err != nil {
        log.Fatalf("unable to connect: %s", err)
    }
    done <- true
}

func main() {
    var args []string = os.Args[1:]
    if len(args) == 0 {
        log.Fatalln("You must specify a gut-command, e.g. `gut sync ...`")
    }
    var cmd = args[0]
    args = args[1:]
    if IsGitCommand(cmd) {
        var gutExe = PathInUserHome(GutExePath)
        syscall.Exec(gutExe, append([]string { gutExe }, args...), os.Environ())
        log.Fatalf("Failed to exec %s", gutExe)
    }
    var argsRemaining, err = flags.ParseArgs(&OptsCommon, args)
    if err != nil { log.Fatal(err) }
    // fmt.Printf("color: %s\n", OptsCommon.NoColor)
    if OptsCommon.Version {
        log.Print("gut-sync version XXXXX")
        os.Exit(0)
    }
    if cmd == "build" {
        // var local = NewSyncContext()
        // if !EnsureBuild(local) {
        //     log.Printf("(@dim)gut " + GitVersion + "(@dim) has already been built.\n")
        // }
    } else if cmd == "sync" {
        var _, err = flags.ParseArgs(&OptsSync, argsRemaining)
        if err != nil { log.Fatal(err) }

        local := NewSyncContext()
        err = local.ParseSyncPath(OptsSync.Positional.LocalPath)
        if err != nil { log.Fatalln(err) }
        remote := NewSyncContext()
        err = remote.ParseSyncPath(OptsSync.Positional.RemotePath)
        if err != nil { log.Fatalln(err) }
        fmt.Printf("local: %s\n", local)
        fmt.Printf("remote: %s\n", remote)

        log.EnableMultilineMode()
        done := make(chan bool)
        num := 10
        for i := 0; i < num; i++ {
            go doSession(remote, done)
        }
        for i := 0; i < num; i++ {
            <-done
        }
    }

}
