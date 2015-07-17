package main

import (
    // "bytes"
    // "code.google.com/p/go.crypto/ssh"
    "fmt"
    "log"
    // "io"
    // "io/ioutil"
    "os"
    "syscall"
    // "time"
    "github.com/jessevdk/go-flags"
)


var opts struct {
    // Slice of bool will append 'true' each time the option
    // is encountered (can be set multiple times, like -vvv)
    Verbose bool `short:"v" long:"verbose" description:"Show verbose debug information"`
}


func main() {
    if (IsGitCommand(os.Args[0])) {
        var gutExe = PathInUserHome(GutExePath)
        os.Args[0] = gutExe
        syscall.Exec(gutExe, os.Args, os.Environ())
        log.Fatalf("Failed to exec %s", gutExe)
    }
    var args, err = flags.ParseArgs(&opts, os.Args)
    if err != nil {
        log.Fatal(err)
    }

    fmt.Printf("%s\n", args)
    // fmt.Printf("the first positional arg is %s\n", flag.Arg(0))
    // var installDeps = flag.Bool("install-deps", false)
}
