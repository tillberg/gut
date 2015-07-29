package main

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
)

func (ctx *SyncContext) tryRun(args ...string) bool {
	_, _, retCode, err := ctx.Run(args...)
	if err != nil {
		ctx.Logger().Bail(err)
	}
	return retCode == 0
}

func (ctx *SyncContext) listMissingLocalDeps() []string {
	missing := []string{}
	if !ctx.HasGutInstalled() {
		// This is needed to build & install gut, but then aren't needed after that.
		if !ctx.tryRun("git", "version") {
			missing = append(missing, "git")
		}
	}
	return missing
}

func (ctx *SyncContext) listMissingRemoteDeps() []string {
	missing := []string{}
	if !ctx.tryRun("which", "inotifywait") {
		if !ctx.tryRun("fswatch", "--version") {
			if ctx.IsDarwin() {
				missing = append(missing, "fswatch")
			} else {
				missing = append(missing, "inotify-tools")
			}
		}
	}
	if !ctx.HasGutInstalled() {
		// These are needed to build & install gut, but then aren't needed after that.
		if !ctx.tryRun("autoconf", "--version") {
			missing = append(missing, "autoconf")
		}
		if ctx.IsLinux() && !ctx.tryRun("msgfmt", "--version") {
			missing = append(missing, "gettext")
		}
	}
	return missing
}

func (ctx *SyncContext) CheckLocalDeps() (err error) {
	missing := ctx.listMissingLocalDeps()
	missing = append(missing, ctx.listMissingRemoteDeps()...)
	return ctx.MissingDependency(missing...)
}

func (ctx *SyncContext) CheckRemoteDeps() (err error) {
	missing := ctx.listMissingRemoteDeps()
	return ctx.MissingDependency(missing...)
}

var mutex sync.Mutex

func (ctx *SyncContext) MissingDependency(names ...string) (err error) {
	if len(names) == 0 {
		return nil
	}
	// Only bombard the user with on MissingDependency dialog at a time, even though we'll do the
	// dependency checks in parallel (for fast startup).
	mutex.Lock()
	defer mutex.Unlock()
	logger := ctx.Logger()
	depsStr := strings.Join(names, " ")
	depsStrCommas := strings.Join(names, logger.Colorify("@(dim:,) "))
	depsStrLong := JoinWithAndAndCommas(names...)
	noun := "dependency"
	quantifier := "A"
	pronoun := "it"
	if len(names) > 1 {
		noun = "dependencies"
		quantifier = "These"
		pronoun = "them"
	}
	depsError := errors.New(fmt.Sprintf("Missing %s: %s", noun, depsStr))
	logger.Printf("@(error:%s %s appear to be missing on) %s@(error::) %s\n", quantifier, noun, ctx.NameAnsi(), depsStrCommas)

	installCmd := ""
	if ctx.IsLinux() {
		installCmd = "sudo apt-get install"
	} else if ctx.IsDarwin() {
		installCmd = "brew install"
	} else {
		return depsError
	}
	installCmd += " " + depsStr
	logger.Printf("I think we might be able to install %s by running this command:\n", pronoun)
	ctx.Logger().Printf("@(dim:$) %s\n", installCmd)
	attempts := 0
	for {
		logger.Printf("Would you like gut-sync to try to install %s [Y/n]? ", pronoun)
		reader := bufio.NewReader(os.Stdin)
		text, _ := reader.ReadString('\n')
		text = strings.TrimSpace(text)
		logger.Replacef("")
		attempts++
		if text == "" || text == "y" || text == "Y" {
			break
		} else if attempts >= 3 || text == "N" || text == "n" || text == "q" || text == "Q" {
			Shutdown("")
		}
	}
	logger.Printf("@(dim:Attempting to install) %s on %s@(dim:...)\n", depsStrLong, ctx.NameAnsi())
	retCode, err := ctx.ShellInteractive(installCmd)
	if err != nil {
		logger.Bail(err)
	}
	if retCode == 0 {
		logger.Printf("@(dim:Successfully installed) %s@(dim:.)\n", depsStrLong)
	} else {
		logger.Printf("@(error:Installation failed.)\n")
		Shutdown("")
	}
	return nil
}
