package main

import (
	"bufio"
	"errors"
	"fmt"
	"github.com/tillberg/ansi-log"
	"os"
	"strings"
)

func (ctx *SyncContext) listMissingLocalDeps() []string {
	missing := []string{}
	_, _, retCode, err := ctx.Run("git", "version")
	if err != nil {
		log.Bail(err)
	}
	if retCode != 0 {
		missing = append(missing, "git")
	}
	return missing
}

func (ctx *SyncContext) listMissingRemoteDeps() []string {
	missing := []string{}
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

func (ctx *SyncContext) MissingDependency(names ...string) (err error) {
	if len(names) == 0 {
		return nil
	}
	logger := ctx.Logger()
	depsStr := strings.Join(names, " ")
	depsStrLong := JoinWithAndAndCommas(names...)
	noun := "dependency"
	quantifier := "this"
	pronoun := "it"
	if len(names) > 1 {
		noun = "dependencies"
		quantifier = "these"
		pronoun = "them"
	}

	depsError := errors.New(fmt.Sprintf("Missing %s: %s", noun, depsStr))
	logger.Printf("@(error:This system appears to be missing %s %s:) %s\n", quantifier, noun, depsStr)

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
		logger.Printf("Would you like gut-sync to attempt to install these [Y/n]? ")
		reader := bufio.NewReader(os.Stdin)
		text, _ := reader.ReadString('\n')
		text = strings.TrimSpace(text)
		logger.Replacef("")
		attempts++
		if text == "" || text == "y" || text == "Y" {
			break
		} else if attempts >= 3 || text == "N" || text == "n" {
			Shutdown("")
		}
	}
	logger.Printf("@(dim:Attempting to install) %s@(dim:...)\n", depsStrLong)
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
