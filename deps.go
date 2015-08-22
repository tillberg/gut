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
		return false
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
		if !ctx.tryRun("make", "--version") || !ctx.tryRun("gcc", "--version") {
			missing = append(missing, "build-essential")
		}
		if ctx.IsLinux() {
			// On errors, just skip this check
			exists, err := ctx.PathExists("/usr/local/include/zlib.h")
			if err == nil {
				if !exists {
					exists, err = ctx.PathExists("/usr/include/zlib.h")
					if err == nil {
						if !exists {
							missing = append(missing, "zlib1g-dev")
						}
					}
				}
			}
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

// FWIW, here's the snippet used in python-gut to install inotify-win:
// gut_build.git_clone_update(config.INOTIFY_WIN_REPO_URL, config.INOTIFY_WIN_PATH, config.INOTIFY_WIN_VERSION)
// status.out('(@dim)Building (@r)inotify-win(@dim)...')
// with context.cwd(context.path(config.INOTIFY_WIN_PATH)):
//     context['cmd']['/c', '%WINDIR%\\Microsoft.NET\\Framework\\v4.0.30319\\csc.exe /t:exe /out:inotifywait.exe src\\*.cs']()

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
		installCmd = "sudo apt-get update && sudo apt-get install"
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
	var retCode int
	for _, cmd := range strings.Split(installCmd, " && ") {
		ctx.Logger().Printf("@(dim:$) %s\n", cmd)
		retCode, err = ctx.ShellInteractive(cmd)
		if err != nil {
			logger.Bail(err)
		}
		if retCode != 0 {
			break
		}
	}
	if retCode == 0 {
		logger.Printf("@(dim:Successfully installed) %s@(dim:.)\n", depsStrLong)
		ctx.ResetHasGutInstalled()
	} else {
		logger.Printf("@(error:Installation failed.)\n")
		Shutdown("")
	}
	return nil
}
