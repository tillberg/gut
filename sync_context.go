package main

import (
    "errors"
    "fmt"
    "regexp"
    "github.com/tillberg/bismuth"
)

type SyncContext struct {
    *bismuth.ExecContext
    syncPath string
}

func NewSyncContext() *SyncContext {
    ctx := &SyncContext{}
    ctx.ExecContext = &bismuth.ExecContext{}
    ctx.Init()
    return ctx
}

var remotePathRegexp = regexp.MustCompile("^((([^@]+)@)?([^:]+):)?(.+)$")
func (ctx *SyncContext) ParseSyncPath(path string) error {
    parts := remotePathRegexp.FindStringSubmatch(path)
    if len(parts) == 0 {
        return errors.New(fmt.Sprintf("Could not parse remote path: [%s]\n", path))
    }
    isRemote := len(parts[1]) > 0
    if isRemote {
        if len(parts[3]) > 0 {
            ctx.SetUsername(parts[3])
        }
        ctx.SetHostname(parts[4])
    }
    ctx.syncPath = parts[5]
    return nil
}

func (ctx *SyncContext) SyncPath() string {
    return ctx.syncPath
}

func (ctx *SyncContext) String() string {
    if ctx.Hostname() != "" {
        return fmt.Sprintf("{SyncContext %s@%s:%s}", ctx.Username(), ctx.Hostname(), ctx.syncPath)
    }
    return fmt.Sprintf("{SyncContext local %s}", ctx.syncPath)
}

func (ctx *SyncContext) PathAnsi(p string) string {
    if !ctx.IsLocal() {
        return fmt.Sprintf(ctx.Logger().Colorify("%s@(dim::)@(path:%s)"), ctx.NameAnsi(), p)
    }
    return fmt.Sprintf(ctx.Logger().Colorify("@(path:%s)"), p)
}

func (ctx *SyncContext) SyncPathAnsi() string {
    return ctx.PathAnsi(ctx.syncPath)
}
