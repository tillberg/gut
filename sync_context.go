package main

import (
	"crypto/md5"
	"errors"
	"fmt"
	"github.com/tillberg/bismuth"
	"os/user"
	"path"
	"regexp"
	"strconv"
	"strings"
)

type SyncContext struct {
	*bismuth.ExecContext
	syncPath string
}

var AllSyncContexts = []*SyncContext{}

func NewSyncContext() *SyncContext {
	ctx := &SyncContext{}
	ctx.ExecContext = &bismuth.ExecContext{}
	ctx.Init()
	AllSyncContexts = append(AllSyncContexts, ctx)
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
		} else {
			currUser, err := user.Current()
			if err == nil {
				ctx.SetUsername(currUser.Username)
			}
		}
		ctx.SetHostname(parts[4])
	}
	ctx.syncPath = parts[5]
	return nil
}

func (ctx *SyncContext) AbsSyncPath() string {
	return ctx.AbsPath(ctx.syncPath)
}

func (ctx *SyncContext) String() string {
	if ctx.Hostname() != "" {
		return fmt.Sprintf("{SyncContext %s@%s:%s}", ctx.Username(), ctx.Hostname(), ctx.syncPath)
	}
	return fmt.Sprintf("{SyncContext local %s}", ctx.syncPath)
}

func (ctx *SyncContext) BranchName() string {
	hostname := ctx.Hostname()
	if hostname == "" {
		hostname = "localhost"
	}
	return fmt.Sprintf("%s-%s", hostname, fmt.Sprintf("%x", md5.Sum([]byte(ctx.String())))[:8])
}

func (ctx *SyncContext) PathAnsi(p string) string {
	if !ctx.IsLocal() {
		return fmt.Sprintf(ctx.Logger().Colorify("@(host:%s)@(dim:@)%s@(dim::)@(path:%s)"), ctx.Username(), ctx.NameAnsi(), p)
	}
	return fmt.Sprintf(ctx.Logger().Colorify("@(path:%s)"), p)
}

func (ctx *SyncContext) SyncPathAnsi() string {
	return ctx.PathAnsi(ctx.syncPath)
}

func (ctx *SyncContext) GutExe() string {
	return ctx.AbsPath(GutExePath)
}

func (ctx *SyncContext) GutArgs(otherArgs ...string) []string {
	args := []string{}
	args = append(args, ctx.GutExe())
	return append(args, otherArgs...)
}

func (ctx *SyncContext) GutRun(args ...string) ([]byte, []byte, int, error) {
	return ctx.RunCwd(ctx.AbsSyncPath(), ctx.GutArgs(args...)...)
}

func (ctx *SyncContext) GutOutput(args ...string) (string, error) {
	return ctx.OutputCwd(ctx.AbsSyncPath(), ctx.GutArgs(args...)...)
}

func (ctx *SyncContext) GutQuoteBuf(suffix string, args ...string) (stdout []byte, stderr []byte, retCode int, err error) {
	return ctx.QuoteCwdBuf(suffix, ctx.AbsSyncPath(), ctx.GutArgs(args...)...)
}

func (ctx *SyncContext) GutQuote(suffix string, args ...string) error {
	return ctx.QuoteCwd(suffix, ctx.AbsSyncPath(), ctx.GutArgs(args...)...)
}

func (ctx *SyncContext) getPidfilePath(name string) string {
	return ctx.AbsPath(path.Join(PidfilesPath, name+".pid"))
}

func (ctx *SyncContext) SaveDaemonPid(name string, pid int) (err error) {
	err = ctx.Mkdirp(PidfilesPath)
	if err != nil {
		ctx.Logger().Bail(err)
	}
	return ctx.WriteFile(ctx.getPidfilePath(name), []byte(fmt.Sprintf("%d", pid)))
}

func (ctx *SyncContext) KillAllViaPidfiles() (err error) {
	logger := ctx.Logger()
	if ctx.IsWindows() {
		logger.Bail(errors.New("Not implemented"))
	}
	files, err := ctx.ListDirectory(ctx.AbsPath(PidfilesPath))
	if err != nil {
		logger.Bail(err)
	}
	for _, filename := range files {
		parts := strings.Split(filename, ".")
		if len(parts) != 2 || parts[1] != "pid" {
			continue
		}
		name := parts[0]
		pidfilePath := ctx.getPidfilePath(name)
		valStr, err := ctx.ReadFile(pidfilePath)
		if err != nil {
			logger.Bail(err)
		}
		pid, err := strconv.ParseInt(string(valStr), 10, 32)
		if err != nil {
			logger.Bail(err)
		}
		// Is it still (presumably) running?
		_, _, retCode, err := ctx.Run("pgrep", "-F", pidfilePath, name)
		if retCode == 0 {
			logger.Printf("@(dim)Killing %s (pid %d)...@(r)", name, pid)
			err = ctx.Quote("pkill", "pkill", "-F", pidfilePath, name)
			if err != nil {
				logger.Printf(" @(error:failed, %s)@(dim:.)\n", err.Error())
			} else {
				logger.Printf(" done@(dim:.)\n")
			}
		}
		ctx.DeleteFile(pidfilePath)
	}
	return nil
}
