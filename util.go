package main

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"math/rand"
	"path/filepath"
	"strings"
	"time"

	"github.com/tillberg/alog"
	"github.com/tillberg/bismuth"
	"github.com/tillberg/stringset"
	"github.com/tillberg/watcher"
)

func WindowsPathToMingwPath(p string) string {
	panic("XXX Does this work?")
	// XXX path/filepath might be better for this sort of thing
	p = strings.Replace(p, ":", "", 1)
	p = strings.Replace(p, "\\", "/", -1)
	return "/" + p
}

const defaultNumCores = "4"

func (ctx *SyncContext) GetNumCores() string {
	if ctx.IsWindows() {
		out, err := ctx.Output("wmic", "CPU", "Get", "NumberOfLogicalProcessors", "/Format:List")
		if err != nil {
			return defaultNumCores
		}
		out = strings.TrimSpace(out)
		parts := strings.Split(out, "=")
		return parts[len(parts)-1]
	} else {
		out, err := ctx.Output("getconf", "_NPROCESSORS_ONLN")
		if err != nil {
			return defaultNumCores
		}
		return strings.TrimSpace(out)
	}
}

func FindOpenPorts(numPorts int, ctxs ...*SyncContext) ([]int, error) {
	if numPorts == 0 {
		return []int{}, nil
	}
	var netstatsBuf bytes.Buffer
	for _, ctx := range ctxs {
		opt := "-anl"
		if ctx.IsWindows() {
			opt = "-an"
		}
		output, err := ctx.Output("netstat", opt)
		if err != nil {
			return nil, err
		}
		netstatsBuf.WriteString(output)
		netstatsBuf.WriteString(" ")
	}
	netstats := netstatsBuf.String()
	randomPorts := []int{}
	for _, n := range rand.Perm(MaxRandomPort - MinRandomPort) {
		randomPorts = append(randomPorts, MinRandomPort+n)
	}
	ports := []int{}
	for _, port := range randomPorts {
		portStr := fmt.Sprintf("%d", port)
		if !strings.Contains(netstats, portStr) {
			ports = append(ports, port)
			if len(ports) == numPorts {
				return ports, nil
			}
		}
	}
	return nil, errors.New("Not enough available ports found")
}

func (ctx *SyncContext) GetCmd(commands ...string) string {
	for _, command := range commands {
		_, _, retCode, err := ctx.Run("which", command)
		if err == nil && retCode == 0 {
			return command
		}
	}
	return ""
}

var letters = []rune("abcdefghijklmnopqrstuvwxyz")

func RandSeq(n int) string {
	b := make([]rune, n)
	for i := range b {
		b[i] = letters[rand.Intn(len(letters))]
	}
	return string(b)
}

var inotifyChangeEvents = []string{"modify", "attrib", "move", "create", "delete"}

func inotifyArgs(ctx *SyncContext, monitor bool) []string {
	args := []string{
		"inotifywait",
		"--quiet",
		"--recursive",
	}
	if monitor {
		args = append(args, "--monitor")
		formatStr := "%w%f"
		excludeStr := "\\.gut/"
		if ctx.IsWindows() {
			// inotify-win has slightly different semantics (and a completely different regex engine) than inotify-tools
			formatStr = "%w\\%f"
			excludeStr = "\\.gut($|\\\\)"
		}
		args = append(args, "--format", formatStr)
		args = append(args, "--exclude", excludeStr)
	}
	if ctx.IsWindows() {
		args = append(args, "--event", strings.Join(inotifyChangeEvents, ","))
	} else {
		for _, event := range inotifyChangeEvents {
			args = append(args, "--event", event)
		}
	}
	args = append(args, ".")
	return args
}

var bytesNewline = []byte{'\n'}

type LineBuf struct {
	lineCallback func([]byte)
	buf          []byte
}

func (m *LineBuf) Write(b []byte) (int, error) {
	m.buf = append(m.buf, b...)
	for {
		indexNewline := bytes.Index(m.buf, bytesNewline)
		if indexNewline < 0 {
			break
		}
		line := m.buf[:indexNewline]
		if indexNewline == len(m.buf)-1 {
			m.buf = m.buf[:0]
		} else {
			m.buf = m.buf[indexNewline+1:]
		}
		m.lineCallback(line)
	}
	return len(b), nil
}
func (m *LineBuf) Close() error {
	if len(m.buf) > 0 {
		m.Write(bytesNewline)
	}
	return nil
}
func NewLineBuf(lineCallback func([]byte)) *LineBuf {
	return &LineBuf{lineCallback, []byte{}}
}

func (ctx *SyncContext) WatchedRoot() string {
	var watchedRoot string
	var err error
	if ctx.IsWindows() {
		watchedRoot, err = ctx.OutputCwd(ctx.AbsSyncPath(), "cmd", "/c", "cd ,")
	} else {
		watchedRoot, err = ctx.OutputCwd(ctx.AbsSyncPath(), "pwd", "-P")
	}
	if err != nil {
		alog.Bail(err)
	}
	return watchedRoot
}

func (ctx *SyncContext) WatchForChanges(fileEventCallback func(string)) {
	if ctx.IsLocal() {
		ctx.watchForChangesLocal(fileEventCallback)
		return
	}
	watchType := ctx.GetCmd("inotifywait", "fswatch")
	status := ctx.NewLogger(watchType)
	args := []string{}
	if watchType == "inotifywait" {
		args = inotifyArgs(ctx, true)
	} else if watchType == "fswatch" {
		args = []string{"fswatch", "."}
	} else {
		if ctx.IsDarwin() {
			Shutdown("missing fswatch", 1)
		} else {
			Shutdown("missing inotifywait", 1)
		}
	}
	watchedRoot := ctx.WatchedRoot()
	ctx.KillViaPidfile(watchType)
	isFirstTime := true
	firstTimeChan := make(chan error)
	go func() {
		var err error
		for {
			if !isFirstTime {
				time.Sleep(2 * time.Second)
				err = ctx.KillViaPidfile(watchType)
				if err == bismuth.NotConnectedError {
					continue
				}
				if err != nil {
					status.Printf("Error killing previous %s process via pidfile: %v\n", watchType, err)
					continue
				}
			}
			buf := NewLineBuf(func(b []byte) {
				// status.Printf("Received: %q\n", string(b))
				p := string(b)
				if !filepath.IsAbs(p) {
					p = filepath.Join(watchedRoot, p)
				}
				relPath, err := filepath.Rel(watchedRoot, p)
				if err != nil {
					status.Bail(err)
				}
				// status.Printf("relPath: %q from %q\n", relPath, watchedRoot)
				fileEventCallback(relPath)
			})
			chanStdout := make(chan io.Reader)
			go func() {
				stdout := <-chanStdout
				_, err := io.Copy(buf, stdout)
				if err != nil {
					status.Printf("Error copying from stdout to buf: %s\n", err)
				}
			}()
			pid, retCodeChan, err := ctx.QuoteDaemonCwdPipeOut(watchType, watchedRoot, chanStdout, args...)
			if err != nil {
				if isFirstTime {
					firstTimeChan <- err
					return
				}
				status.Printf("Error starting %s: %v\n", watchType, err)
				continue
			}
			err = ctx.SaveDaemonPid(watchType, pid)
			if err != nil {
				if isFirstTime {
					firstTimeChan <- err
					return
				}
				status.Printf("Error saving PID for %s: %v\n", watchType, err)
				continue
			}
			if isFirstTime {
				firstTimeChan <- err
				if err != nil {
					return
				}
				isFirstTime = false
			}
			if err != nil {
				status.Printf("Error starting %s: %v\n", watchType, err)
			} else {
				ctx.Logger().Printf("@(dim:%s started, watching )%s@(dim::)@(path:%s)@(dim:.)\n", watchType, ctx.NameAnsi(), watchedRoot)
				<-retCodeChan
				ctx.Logger().Printf("@(dim:%s exited.)\n", watchType)
			}
		}
	}()
	err := <-firstTimeChan
	if err != nil {
		status.Bail(err)
	}
}

func (ctx *SyncContext) watchForChangesLocal(fileEventCallback func(string)) {
	status := ctx.NewLogger("watcher")
	listener := watcher.NewListener()
	listener.Path = ctx.syncPath
	listener.IgnorePart = stringset.New(".gut")
	err := listener.Start()
	status.BailIf(err)

	go func() {
		for pathEvent := range listener.NotifyChan {
			path := pathEvent.Path
			relPath, err := filepath.Rel(ctx.syncPath, path)
			if err != nil {
				status.Bail(err)
			}
			fileEventCallback(relPath)
		}
	}()
}

const GutHashDisplayChars = 7

func TrimCommit(commit string) string {
	if len(commit) > GutHashDisplayChars {
		return commit[:GutHashDisplayChars]
	}
	return commit
}

func (ctx *SyncContext) AssertSyncFolderIsEmpty() (err error) {
	p := ctx.AbsSyncPath()
	bail := func() {
		ctx.Logger().Printf("@(error:Refusing to initialize) @(path:%s) @(error:on) %s ", p, ctx.NameAnsi())
		ctx.Logger().Printf("@(error:as it is not an empty directory.)\n")
		ctx.Logger().Fatalf("@(error:Move or delete it manually first, the try running gut-sync again.)\n")
	}
	fileInfo, err := ctx.Stat(p)
	if err == bismuth.NotFoundError {
		return nil
	}
	if err != nil {
		bail()
	}
	if !fileInfo.IsDir() {
		bail()
	}
	out, err := ctx.Output("ls", "-A", ctx.AbsSyncPath())
	if err != nil {
		bail()
	}
	if len(strings.TrimSpace(out)) > 0 {
		bail()
	}
	return nil
}

func CommonPathPrefix(paths ...string) string {
	if len(paths) == 0 {
		return ""
	}
	common := paths[0]
	for _, path := range paths[1:] {
		for len(path) < len(common) || path[:len(common)] != common {
			if common[len(common)-1] == '/' {
				// Lop off the trailing slash, if there is one
				common = common[:len(common)-1]
			} else {
				lastIndex := strings.LastIndex(common, "/")
				if lastIndex == -1 {
					// There is no common prefix
					return ""
				} else {
					// Lop off everything after the last slash
					common = common[:lastIndex+1]
				}
			}
		}
	}
	return common
}

func JoinWithAndAndCommas(strs ...string) string {
	if len(strs) == 0 {
		return ""
	}
	var buf bytes.Buffer
	buf.WriteString(strs[0])
	if len(strs) > 1 {
		commaStr := alog.Colorify("@(dim:, )")
		andStr := alog.Colorify("@(dim:and )")
		strs = strs[1:]
		for i, str := range strs {
			if len(strs) >= 2 {
				buf.WriteString(commaStr)
			}
			if i == len(strs)-1 {
				if len(strs) < 2 {
					buf.WriteString(" ")
				}
				buf.WriteString(andStr)
			}
			buf.WriteString(str)
		}
	}
	return buf.String()
}

func IsGitCommand(s string) bool {
	for _, a := range AllGutCommands {
		if a == s {
			return true
		}
	}
	return false
}

func IsDangerousGitCommand(s string) bool {
	for _, a := range DangerousGitCommands {
		if a == s {
			return true
		}
	}
	return false
}
