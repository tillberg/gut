package main

import (
    "errors"
    "fmt"
    "path"
    "strings"
)

// Query the gut repo for the initial commit to the repo. We use this to determine if two gut repos are compatibile.
// http://stackoverflow.com/questions/1006775/how-to-reference-the-initial-commit
func (ctx *SyncContext) GetTailHash() (string, error) {
    exists, err := ctx.PathExists(path.Join(ctx.AbsSyncPath(), ".gut"))
    if err != nil { ctx.Logger().Bail(err) }
    if exists {
        output, err := ctx.GutOutput("rev-list", "--max-parents=0", "HEAD")
        if err != nil { ctx.Logger().Bail(err) }
        return strings.TrimSpace(output), nil
    }
    return "", nil
}

func (ctx *SyncContext) GutRevParseHead() (commit string, err error) {
    stdout, err := ctx.GutOutput("rev-parse", "HEAD")
    if err != nil { return "", err }
    return strings.TrimSpace(stdout), nil
}

// Start a git-daemon on the host, bound to port gutd_bind_port on the *localhost* network interface only.
// `autossh` will create a tunnel to expose this port as gutd_connect_port on the other host.
func GutDaemon(ctx *SyncContext, repoName string, bindPort int) (err error) {
    basePath := ctx.AbsPath(GutDaemonPath)
    ctx.Mkdirp(basePath)
    symlinkPath := path.Join(basePath, repoName)
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
        "--enable=receive-pack",
        fmt.Sprintf("--port=%d", bindPort),
        basePath,
    }
    pid, _, err := ctx.QuoteDaemonCwd("daemon", "", ctx.GutArgs(args...)...)
    if err != nil { return err }
    return ctx.SaveDaemonPid("daemon", pid)
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

func GutSetupOrigin(ctx *SyncContext, repoName string, connectPort int) (err error) {
    originUrl := fmt.Sprintf("gut://localhost:%d/%s/", connectPort, repoName)
    out, err := ctx.GutOutput("remote")
    if err != nil { return err }
    if strings.Contains(out, "origin") {
        _, err = ctx.GutOutput("remote", "set-url", "origin", originUrl)
    } else {
        _, err = ctx.GutOutput("remote", "add", "origin", originUrl)
    }
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

var NeedsCommitError = errors.New("Needs commit before pull.")

func GutMerge(ctx *SyncContext, branch string) (err error) {
    status := ctx.NewLogger("merge")
    status.Printf("@(dim:Merging changes to) %s@(dim:...)", ctx.NameAnsi())
    mergeArgs := []string{
        "merge",
        branch,
        "--strategy=recursive",
        "--strategy-option=theirs", // or "ours"? not sure either is better?
        "--no-edit",
    }
    _, stderr, retCode, err := ctx.GutQuoteBuf("merge", mergeArgs...)
    if err != nil {
        status.Printf(" @(error:failed)@(dim:.)\n")
        return err
    }
    needCommit := retCode != 0 && strings.Contains(string(stderr), needsCommitStr)
    if needCommit {
        status.Printf(" @(error:failed due to uncommitted changes)@(dim:.)\n")
        return NeedsCommitError
    }
    status.Printf(" @(dim:done.)\n")
    return nil
}

func GutCheckout(ctx *SyncContext, branch string) (err error) {
    status := ctx.NewLogger("checkout")
    status.Printf("@(dim:Checking out) %s @(dim:on) %s@(dim:...)\n", branch, ctx.NameAnsi())
    return ctx.GutQuote("checkout", "checkout", branch)
}

func GutPush(ctx *SyncContext) (err error) {
    status := ctx.NewLogger("push")
    status.Printf("@(dim:Pushing changes from) %s@(dim:...)\n", ctx.NameAnsi())
    return ctx.GutQuote("push", "push", "origin", "master:" + ctx.BranchName(), "--progress")
}

var needsCommitStr = "Your local changes to the following files would be overwritten"
func GutFetch(ctx *SyncContext) (err error) {
    status := ctx.NewLogger("fetch")
    status.Printf("@(dim:Fetching changes to) %s@(dim:...)\n", ctx.NameAnsi())
    _, stderr, retCode, err := ctx.GutQuoteBuf("fetch", "fetch", "origin", "--progress")
    if strings.Contains(string(stderr), "Cannot lock ref") {
        status.Printf("RETCODE LOCK FAILURE: %d\n", retCode)
    }
    return err
}

func GutCommit(ctx *SyncContext, prefix string, updateUntracked bool) (changed bool, err error) {
    status := ctx.NewLogger("commit")
    headBefore, err := ctx.GutRevParseHead()
    if err != nil { return false, err }
    if updateUntracked {
        lsFiles, err := ctx.GutOutput("ls-files", "-i", "--exclude-standard", "--", prefix)
        if err != nil { return false, err }
        lsFiles = strings.TrimSpace(lsFiles)
        if lsFiles != "" {
            for _, filename := range strings.Split(lsFiles, "\n") {
                status.Printf("@(dim:Untracking newly-.gutignored) %s\n", filename)
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
    headAfter, err := ctx.GutRevParseHead()
    if err != nil { return false, err }
    // status.Printf("before: %s, after: %s", headBefore, headAfter)
    madeACommit := headBefore != headAfter
    if madeACommit {
        status.Printf(" committed @(commit:%s)@(dim:.)\n", TrimCommit(headAfter))
    } else {
        status.Printf(" none@(dim:.)\n")
    }
    return madeACommit, nil
}

func GutEnsureInitialCommit(ctx *SyncContext) (err error) {
    status := ctx.NewLogger("firstcommit")
    status.Printf("@(dim:Writing first commit on) %s@(dim:.)\n", ctx.SyncPathAnsi())
    head, err := ctx.GutRevParseHead()
    if err != nil { return err }
    if head == "HEAD" {
        err = ctx.WriteFile(path.Join(ctx.AbsSyncPath(), ".gutignore"), []byte(DefaultGutignore))
        if err != nil { return err }
        err = ctx.GutQuote("add", "add", ".gutignore")
        if err != nil { return err }
        err = ctx.GutQuote("commit", "commit", "--message", "Inital commit")
    }
    return err
}
