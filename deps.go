package main

import (
	"github.com/tillberg/ansi-log"
)

func (ctx *SyncContext) MissingDependency(name string) {
	log.Fatalf("Missing dependency: %s", name)
}
