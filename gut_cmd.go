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

func GutRevParseHead(ctx *SyncContext) (commit string, err error) {
    stdout, err := ctx.GutOutput("rev-parse", "HEAD")
    if err != nil { return "", err }
    return strings.TrimSpace(stdout), nil
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
    ctx.Mkdirp(ctx.AbsSyncPath())
    exists, err := ctx.PathExists(path.Join(ctx.AbsSyncPath(), ".gut"))
    if err != nil { return err }
    if !exists {
        return ctx.GutQuote("init", "init")
    }
    return nil
}

func GutSetupOrigin(ctx *SyncContext, tailHash string, connectPort int) (err error) {
    originUrl := fmt.Sprintf("gut://localhost:%d/%s/", connectPort, tailHash)
    _, err = ctx.GutOutput("remote", "set-url", "origin", originUrl)
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

func doMerge(ctx *SyncContext) (needCommit bool, err error) {
    status := ctx.NewLogger("pull")
    status.Printf("@(dim:Merging changes to) %s@(dim:...)", ctx.NameAnsi())
    mergeArgs := []string{
        "merge",
        "origin/master",
        "--strategy=recursive",
        "--strategy-option=theirs",
        "--no-edit",
    }
    _, stderr, retCode, err := ctx.GutQuoteBuf("merge", mergeArgs...)
    if err != nil {
        status.Printf(" @(error:failed)@(dim:.)\n")
        return false, err
    }
    needCommit = retCode != 0 && strings.Contains(string(stderr), needsCommitStr)
    if needCommit {
        status.Printf(" @(error:failed due to uncommitted changes)@(dim:.)\n")
    } else {
        status.Printf(" @(dim:done.)\n")
    }
    return needCommit, nil
}

var needsCommitStr = "Your local changes to the following files would be overwritten"
func GutPull(ctx *SyncContext) (err error) {
    status := ctx.NewLogger("pull")
    status.Printf("@(dim:Downloading changes to) %s@(dim:...)", ctx.NameAnsi())
    ctx.GutQuote("fetch", "fetch", "origin")
    status.Printf("@(dim) done.\n")
    needCommit, err := doMerge(ctx)
    if err != nil { return err }
    if needCommit {
        status.Printf("@(dim:Committing outstanding changes before retrying merge...)\n")
        changed, err := GutCommit(ctx, ".", true)
        if err != nil { return err }
        if changed {
            _, err = doMerge(ctx)
            if err != nil { return err }
        }
    }
    return nil
}

func GutCommit(ctx *SyncContext, prefix string, updateUntracked bool) (changed bool, err error) {
    status := ctx.NewLogger("commit")
    headBefore, err := GutRevParseHead(ctx)
    if err != nil { return false, err }
    if updateUntracked {
        lsFiles, err := ctx.GutOutput("ls-files", "-i", "--exclude-standard", "--", prefix)
        if err != nil { return false, err }
        lsFiles = strings.TrimSpace(lsFiles)
        if lsFiles != "" {
            for _, filename := range strings.Split(lsFiles, "\n") {
                status.Printf("@(dim:Untracking newly-.gutignored) " + filename)
                rmArgs := []string{"rm", "--cached", "--ignore-unmatch", "--quiet", "--", filename}
                err = ctx.GutQuote("rm--cached", rmArgs...)
                if err != nil { return false, err }
            }
        }
    }
    status.Printf("@(dim:Checking) %s @(dim)for changes (scope=@(r)%s@(dim))...", ctx.NameAnsi(), prefix)
    err = ctx.GutQuote("add", "add", "--all", "--", prefix)
    if err != nil { return false, err }
    err = ctx.GutQuote("commit", "commit", "--message", "autocommit")
    if err != nil { return false, err }
    headAfter, err := GutRevParseHead(ctx)
    if err != nil { return false, err }
    madeACommit := headBefore != headAfter
    if madeACommit {
        status.Printf(" committed @(commit:%s)@(dim:.)\n", TrimCommit(headAfter))
    } else {
        status.Printf(" none@(dim:.)\n")
    }
    return madeACommit, nil
}

func GutEnsureInitialCommit(ctx *SyncContext) (err error) {
    return errors.New("Not implemented")
}
