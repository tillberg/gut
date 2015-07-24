package main

import (
    "github.com/tillberg/ansi-log"
)

func MissingDependency(ctx *SyncContext, name string) {
    log.Fatalf("Missing dependency: %s", name)
}
