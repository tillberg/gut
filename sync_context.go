package main

import (
    "errors"
    "fmt"
    "os"
    "regexp"
    "github.com/tillberg/bismuth"
    "github.com/tillberg/ansi-log"
)

type SyncContext struct {
    bismuth.ExecContext

    syncPath string
}

func NewSyncContext() *SyncContext {
    ctx := &SyncContext{}
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

func (ctx *SyncContext) String() string {
    if ctx.Hostname() != "" {
        return fmt.Sprintf("{SyncContext %s@%s:%s}", ctx.Username(), ctx.Hostname(), ctx.syncPath)
    }
    return fmt.Sprintf("{SyncContext local %s}", ctx.syncPath)
}

func (ctx *SyncContext) nameAnsi() string {
    hostname := ctx.Hostname()
    if hostname == "" { hostname = "localhost" }
    return fmt.Sprintf("@(host:%s)", hostname)
}

func (ctx *SyncContext) Logger() *log.Logger {
    logger := log.New(os.Stderr, fmt.Sprintf("@(dim)[%s] ", ctx.nameAnsi()), 0)
    logger.EnableColorTemplate()
    return logger
}
