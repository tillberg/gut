package main

import (
    "bytes"
    "errors"
    "fmt"
    "math/rand"
    "strings"
)

func Mkdirp(ctx *SyncContext, p string) (err error) {
    _, err = ctx.Output("mkdir", "-p", ctx.AbsPath(p))
    return err
}

func WindowsPathToMingwPath(p string) string {
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
