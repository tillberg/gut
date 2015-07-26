package main

import (
    "bytes"
    "errors"
    "fmt"
    "math/rand"
    "strings"
)

func WindowsPathToMingwPath(p string) string {
    panic("XXX Does this work?")
    // XXX path/filepath might be better for this sort of thing
    p = strings.Replace(p, ":", "", 1)
    p = strings.Replace(p, "\\", "/", -1)
    return "/" + p
}

const defaultNumCores = "4"
func GetNumCores(ctx *SyncContext) string {
    if ctx.IsWindows() {
        out, err := ctx.Output("wmic", "CPU", "Get", "NumberOfLogicalProcessors", "/Format:List")
        if err != nil { return defaultNumCores }
        out = strings.TrimSpace(out)
        parts := strings.Split(out, "=")
        return parts[len(parts) - 1]
    } else {
        out, err := ctx.Output("getconf", "_NPROCESSORS_ONLN")
        if err != nil { return defaultNumCores }
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
        if err != nil { return nil, err }
        netstatsBuf.WriteString(output)
        netstatsBuf.WriteString(" ")
    }
    netstats := netstatsBuf.String()
    randomPorts := []int{}
    for _, n := range rand.Perm(MaxRandomPort - MinRandomPort) {
        randomPorts = append(randomPorts, MinRandomPort + n)
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

func KillPreviousProcess(ctx *SyncContext, name string) {

}

func GetCmd(ctx *SyncContext, commands ...string) string {
    for _, command := range commands {
        _, err := ctx.Output("which", command)
        if err == nil {
            return command
        }
    }
    return ""
}

func StartSshTunnel(local *SyncContext, remote *SyncContext, gutdBindPort int, gutdConnectPort int, autosshMonitorPort int) (err error) {
    cmd := GetCmd(local, "autossh", "ssh")
    if cmd == "" {
        MissingDependency(local, "ssh")
    }
    KillPreviousProcess(local, cmd)
    sshTunnelOpts := fmt.Sprintf("%d:localhost:%d", gutdConnectPort, gutdBindPort)
    args := []string{cmd}
    if cmd == "autossh" && local.IsDarwin() {
        args = append(args, "-M", fmt.Sprintf("%d", autosshMonitorPort))
    }
    args = append(args, "-N", "-L", sshTunnelOpts, "-R", sshTunnelOpts, remote.SshAddress())
    pid, _, err := local.QuoteDaemon(cmd, args...)
    local.SaveDaemonPid(cmd, pid)
    return err
}

func WatchForChanges(ctx *SyncContext, fileEventCallback func(string)) (err error) {
    return nil
}

const GutHashDisplayChars = 10
func TrimCommit(commit string) string {
    if len(commit) > GutHashDisplayChars {
        return commit[:GutHashDisplayChars]
    }
    return commit
}

func AssertSyncFolderIsEmpty(ctx *SyncContext) (err error) {
    p := ctx.AbsSyncPath()
    bail := func() {
        ctx.Logger().Printf("@(error:Refusing to initialize) @(path:%s) @(error:on) %s ", p, ctx.NameAnsi())
        ctx.Logger().Printf("@(error:as it is not an empty directory.)\n")
        ctx.Logger().Fatalf("@(error:Move or delete it manually first, the try running gut-sync again.)\n")
    }
    fileInfo, err := ctx.Stat(p)
    if err != nil { bail() }
    if fileInfo == nil { return nil }
    if !fileInfo.IsDir() { bail() }
    out, err := ctx.Output("ls", "-A", ctx.AbsSyncPath())
    if err != nil { bail() }
    if len(strings.TrimSpace(out)) > 0 { bail() }
    return nil
}

func CommonPathPrefix(paths ...string) string {
    if len(paths) == 0 { return "" }
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
                    common = common[:lastIndex + 1]
                }
            }
        }
    }
    return common
}
