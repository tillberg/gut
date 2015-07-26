package main

import (
    "errors"
    "fmt"
    "path"
    "strings"
)

// Query the gut repo for the initial commit to the repo. We use this to determine if two gut repos are compatibile.
// http://stackoverflow.com/questions/1006775/how-to-reference-the-initial-commit
func GetTailHash(ctx *SyncContext) (string, error) {
    exists, err := ctx.PathExists(path.Join(ctx.AbsSyncPath(), ".gut"))
    if err != nil { ctx.Logger().Bail(err) }
    if exists {
        output, err := ctx.GutOutput("rev-list", "--max-parents=0", "HEAD")
        if err != nil { ctx.Logger().Bail(err) }
        return strings.TrimSpace(output), nil
    }
    return "", nil
}

// Start a git-daemon on the host, bound to port gutd_bind_port on the *localhost* network interface only.
// `autossh` will create a tunnel to expose this port as gutd_connect_port on the other host.
func GutDaemon(ctx *SyncContext, tailHash string, bindPort int) (err error) {
    basePath := ctx.AbsPath(GutDaemonPath)
    ctx.Mkdirp(basePath)
    symlinkPath := path.Join(basePath, tailHash)
    exists, err := ctx.PathExists(symlinkPath)
    if err != nil { return err }
    if exists {
        err = ctx.DeleteLink(symlinkPath)
        if err != nil { return err }
    }
    err = ctx.Symlink(ctx.AbsSyncPath(), symlinkPath)
    if err != nil { return err }
    args := []string{
        "daemon",
        "--export-all",
        "--base-path=" + basePath,
        "--reuseaddr",
        "--listen=localhost",
        fmt.Sprintf("--port=%d", bindPort),
        basePath,
    }
    pid, _, err := ctx.QuoteDaemon("gut-daemon", ctx.GutArgs(args...)...)
    if err != nil { return err }
    return ctx.SaveDaemonPid("gut-daemon", pid)
}

func GutInit(ctx *SyncContext) (err error) {
    return errors.New("Not implemented")
}

func GutSetupOrigin(ctx *SyncContext, tailHash string, connectPort int) (err error) {
    _, err = ctx.GutOutput("remote", "rm", "origin")
    if err != nil { return err }
    originUrl := fmt.Sprintf("gut://localhost:%s/%s/", connectPort, tailHash)
    _, err = ctx.GutOutput("remote", "add", "origin", originUrl)
    if err != nil { return err }
    _, err = ctx.GutOutput("config", "color.ui", "always")
    if err != nil { return err }
    hostname, err := ctx.Output("hostname")
    if err != nil { return err }
    _, err = ctx.GutOutput("config", "user.name", hostname)
    if err != nil { return err }
    _, err = ctx.GutOutput("config", "user.email", "gut-sync@" + hostname)
    return err
}

func GutPull(ctx *SyncContext) (err error) {
    return errors.New("Not implemented")
}

func GutCommit(ctx *SyncContext, prefix string, updateUntracked bool) (changed bool, err error) {
    return false, errors.New("Not implemented")
}

func GutEnsureInitialCommit(ctx *SyncContext) (err error) {
    return errors.New("Not implemented")
}
