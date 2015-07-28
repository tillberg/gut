package main

import (
	"fmt"
	"github.com/jessevdk/go-flags"
	"github.com/tillberg/ansi-log"
	"github.com/tillberg/bismuth"
	"io"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
)

var OptsCommon struct {
	Verbose     bool `short:"v" long:"verbose" description:"Show verbose debug information"`
	Version     bool `long:"version"`
	NoColor     bool `long:"no-color"`
	InstallDeps bool `long:"install-deps"`
}

var OptsSync struct {
	IdentityFile string `short:"i" long:"identity"`
	Dev          bool   `long:"dev"`
	Positional   struct {
		LocalPath string
	} `positional-args:"yes" required:"yes"`
}

func EnsureBuild(local *SyncContext, ctx *SyncContext) (didSomething bool, err error) {
	status := ctx.Logger()
	desiredGitVersion := GitVersion
	if ctx.IsWindows() {
		desiredGitVersion = GitWinVersion
	}
	exists, err := ctx.PathExists(GutExePath)
	if err != nil {
		return false, err
	}
	if exists {
		actualGutVersion, err := ctx.Output(ctx.AbsPath(GutExePath), "--version")
		if err != nil {
			return false, err
		}
		if strings.Contains(string(actualGutVersion), strings.TrimLeft(desiredGitVersion, "v")) {
			return false, nil
		}
	}
	status.Printf("@(dim:Need to build gut on) %s@(dim:.)\n", ctx.NameAnsi())
	err = ctx.EnsureGutFolders()
	if err != nil {
		return false, err
	}
	err = GutBuildPrepare(local, ctx)
	if err != nil {
		return false, err
	}
	var buildPath string
	if ctx.IsLocal() {
		if ctx.IsWindows() {
			buildPath = GutWinSrcPath
		} else {
			buildPath = GutSrcPath
		}
	} else {
		buildPath = GutSrcTmpPath
		status.Printf("@(dim:Uploading) %s @(dim:to) %s@(dim:...)", local.PathAnsi(GutSrcPath), ctx.PathAnsi(buildPath))
		chanErr := make(chan error)
		stdinChan := make(chan io.WriteCloser)
		go func() {
			ctx.Mkdirp(buildPath)
			err := ctx.QuotePipeIn("untar", stdinChan, ctx.AbsPath(buildPath), "tar", "xf", "-")
			chanErr <- err
		}()
		ctxStdin := <-stdinChan
		err = local.QuotePipeOut("tar", ctxStdin, local.AbsPath(GutSrcPath), "tar", "cf", "-", "--exclude=.git", "--exclude=t", "./")
		if err != nil {
			return false, err
		}
		err = <-chanErr
		if err != nil {
			return false, err
		}
		status.Printf("@(dim: done.)\n")
	}
	err = ctx.GutBuild(buildPath)
	if err != nil {
		return false, err
	}
	status.Printf("@(dim:Cleaning up...)")
	err = GutUnprepare(local, ctx)
	if err != nil {
		return false, err
	}
	status.Printf("@(dim: done.)\n")
	return true, nil
}

const commitDebounceDuration = 100 * time.Millisecond

func Sync(local *SyncContext, remotes []*SyncContext) (err error) {
	status := local.NewLogger("sync")
	defer status.Close()
	hostsStr := local.SyncPathAnsi()
	commaStr := status.Colorify("@(dim:, )")
	andStr := status.Colorify("@(dim:and )")
	for i, ctx := range remotes {
		if len(remotes) >= 2 {
			hostsStr += commaStr
		}
		if i == len(remotes)-1 {
			if len(remotes) < 2 {
				hostsStr += " "
			}
			hostsStr += andStr
		}
		hostsStr += ctx.SyncPathAnsi()
	}
	status.Printf("@(dim:Starting gut-sync between) %s@(dim:.)\n", hostsStr)

	allContexts := append([]*SyncContext{local}, remotes...)

	for _, ctx := range allContexts {
		_, err = EnsureBuild(local, ctx)
		if err != nil {
			status.Bail(err)
		}
	}

	ports, err := FindOpenPorts(1, allContexts...)
	if err != nil {
		status.Bail(err)
	}
	// status.Printf("Using ports %v\n", ports)
	gutdPort := ports[0]
	gutdAddr := fmt.Sprintf("localhost:%d", gutdPort)
	repoName := RandSeq(12)

	// Start up gut-daemon on the local host, and create a reverse tunnel from each of the remote hosts
	// back to the local gut-daemon. All hosts can connect to gut-daemon at localhost:<gutdPort>, which
	// makes configuration a little simpler.
	local.GutDaemon(repoName, gutdPort)
	for _, ctx := range remotes {
		if !ctx.IsLocal() {
			err = ctx.ReverseTunnel(gutdAddr, gutdAddr)
			if err != nil {
				status.Bail(err)
			}
		}
	}

	// Find tailHash, if any. Bail if there are conflicting tailHashes.
	tailHash := ""
	var tailHashFoundOn *SyncContext
	localTailHash, err := local.GetTailHash()
	if err != nil {
		status.Bail(err)
	}
	if localTailHash != "" {
		tailHash = localTailHash
		tailHashFoundOn = local
	}
	contextsNeedInit := []*SyncContext{}
	for _, ctx := range remotes {
		myTailHash, err := ctx.GetTailHash()
		if err != nil {
			status.Bail(err)
		}
		if myTailHash == "" {
			err = ctx.AssertSyncFolderIsEmpty()
			if err != nil {
				status.Bail(err)
			}
			contextsNeedInit = append(contextsNeedInit, ctx)
		} else {
			if tailHash == "" {
				tailHash = myTailHash
				tailHashFoundOn = ctx
			} else {
				if tailHash != myTailHash {
					status.Printf("@(error:Found different gut repo base commits:)\n")
					status.Printf("@(commit:%s) @(error:on) %s\n",
						TrimCommit(tailHash), tailHashFoundOn.SyncPathAnsi())
					status.Printf("@(commit:%s) @(error:on) %s\n",
						TrimCommit(myTailHash), ctx.SyncPathAnsi())
					Shutdown(status.Colorify("@(error:Cannot sync incompatible gut repos.)"))
				}
				err = ctx.GutSetupOrigin(repoName, gutdPort)
				if err != nil {
					status.Bail(err)
				}
			}
		}
	}
	if localTailHash == "" {
		if tailHash == "" {
			status.Printf("@(dim:No existing gut repo found. Initializing gut repo in %s.)\n", local.SyncPathAnsi())
			err = local.GutInit()
			if err != nil {
				status.Bail(err)
			}
			err = local.GutSetupOrigin(repoName, gutdPort)
			if err != nil {
				status.Bail(err)
			}
			err = local.GutEnsureInitialCommit()
			if err != nil {
				status.Bail(err)
			}
			tailHash, err = local.GetTailHash()
			if err != nil {
				status.Bail(err)
			}
			if tailHash == "" {
				Shutdown(status.Colorify("Failed to initialize new gut repo."))
			}
			tailHashFoundOn = local
		} else {
			err = local.GutInit()
			if err != nil {
				status.Bail(err)
			}
			err = local.GutSetupOrigin(repoName, gutdPort)
			if err != nil {
				status.Bail(err)
			}
			err = tailHashFoundOn.GutPush()
			if err != nil {
				status.Bail(err)
			}
			err = local.GutCheckoutAsMaster(tailHashFoundOn.BranchName())
			if err != nil {
				status.Bail(err)
			}
		}
	} else {
		err = local.GutSetupOrigin(repoName, gutdPort)
		if err != nil {
			status.Bail(err)
		}
	}
	for _, ctx := range contextsNeedInit {
		err = ctx.GutInit()
		if err != nil {
			status.Bail(err)
		}
		err = ctx.GutSetupOrigin(repoName, gutdPort)
		if err != nil {
			status.Bail(err)
		}
		err = ctx.GutPull()
		if err != nil {
			status.Bail(err)
		}
	}

	type FileEvent struct {
		ctx      *SyncContext
		filepath string
	}
	eventChan := make(chan FileEvent)

	commitAndUpdate := func(src *SyncContext, changedPaths []string, updateUntracked bool) (err error) {
		prefix := CommonPathPrefix(changedPaths...)
		if prefix != "" {
			// git is annoying if you try to git-add git-ignored files (printing a message that is very helpful when there is a human
			// attached to stdin/stderr), so let's always just target the last *folder* by lopping off everything after the last slash:
			lastIndex := strings.LastIndex(prefix, "/")
			if lastIndex == -1 {
				prefix = ""
			} else {
				prefix = prefix[:lastIndex+1]
			}
		}
		if prefix == "" {
			prefix = "."
		}
		changed, err := src.GutCommit(prefix, updateUntracked)
		if err != nil {
			status.Bail(err)
		}
		if changed {
			if src != local {
				err = src.GutPush()
				if err != nil {
					status.Bail(err)
				}
				err = local.GutMerge(src.BranchName())
				if err != nil {
					status.Bail(err)
				}
			}
			done := make(chan error)
			for _, _ctx := range remotes {
				if _ctx != src {
					go func(ctx *SyncContext) {
						done <- ctx.GutPull()
					}(_ctx)
				}
			}
			for _, ctx := range remotes {
				if ctx != src {
					err = <-done
					if err == NeedsCommitError {
						status.Printf("@(dim:Need to commit on) %s @(dim:before it can pull.)\n", ctx.NameAnsi())
						// Queue up an event to force checking for changes. Saying that
						// .gutignore changed is a kludgy way to get it to check for files
						// that should be untracked.
						eventChan <- FileEvent{ctx, ".gutignore"}
						err = nil
					}
					if err != nil {
						status.Bail(err)
					}
				}
			}
		}
		return nil
	}

	fileEventCallbackGen := func(ctx *SyncContext) func(filepath string) {
		return func(filepath string) {
			eventChan <- FileEvent{ctx, filepath}
		}
	}

	for _, ctx := range allContexts {
		ctx.WatchForChanges(fileEventCallbackGen(ctx))
	}
	// The filesystem watchers are not necessarily listening to all updates yet, so we could miss file changes that occur between the
	// commit_and_update calls below and the time that the filesystem watches are attached.
	for _, ctx := range allContexts {
		commitAndUpdate(ctx, []string{}, true)
	}

	var haveChanges bool
	var changedPaths map[*SyncContext]map[string]bool
	var changedIgnore map[*SyncContext]bool
	clearChanges := func() {
		haveChanges = false
		changedPaths = make(map[*SyncContext]map[string]bool)
		changedIgnore = make(map[*SyncContext]bool)
	}
	clearChanges()
	flushChanges := func() {
		for ctx, pathMap := range changedPaths {
			paths := []string{}
			for path := range pathMap {
				paths = append(paths, path)
			}
			_, changedThisIgnore := changedIgnore[ctx]
			commitAndUpdate(ctx, paths, changedThisIgnore)
		}
		clearChanges()
	}

	var event FileEvent
	for {
		if haveChanges {
			select {
			case event = <-eventChan:
				break
			case <-time.After(commitDebounceDuration):
				flushChanges()
				continue
			}
		} else {
			event = <-eventChan
		}
		parts := strings.Split(event.filepath, "/")
		skip := false
		for _, part := range parts {
			if part == ".gut" {
				skip = true
			} else if part == ".gutignore" {
				changedIgnore[event.ctx] = true
			}
		}
		if skip {
			continue
		}
		// status.Printf("@(dim:[)%s@(dim:] changed on) %s\n", event.filepath, event.ctx.NameAnsi())
		haveChanges = true
		ctxChanged, ok := changedPaths[event.ctx]
		if !ok {
			ctxChanged = make(map[string]bool)
			changedPaths[event.ctx] = ctxChanged
		}
		ctxChanged[event.filepath] = true
	}
	return nil
}

var shutdownLock sync.Mutex

func Shutdown(reason string) {
	shutdownLock.Lock()
	status := log.New(os.Stderr, "", 0)
	if reason != "" {
		status.Printf("%s ", reason)
	}
	status.Printf("Stopping all subprocesses...\n")
	done := make(chan bool)
	for _, _ctx := range AllSyncContexts {
		go func(ctx *SyncContext) {
			ctx.KillAllSessions()
			// This generally shouldn't *do* anything other than
			// clean up the PID files, as the killing would have
			// been done already in KillAllSessions.
			ctx.KillAllViaPidfiles()
			ctx.Close()
			done <- true
		}(_ctx)
	}
	for range AllSyncContexts {
		<-done
	}
	status.Printf("Exiting.")
	fmt.Println()
	os.Exit(1)
}

func main() {
	log.EnableMultilineMode()
	log.EnableColorTemplate()
	log.AddAnsiColorCode("error", 31)
	log.AddAnsiColorCode("commit", 32)
	status := log.New(os.Stderr, "", 0)
	var args []string = os.Args[1:]
	if len(args) == 0 {
		status.Fatalln("You must specify a gut-command, e.g. `gut sync ...`")
	}
	var cmd = args[0]
	if IsGitCommand(cmd) {
		var gutExe = PathInUserHome(GutExePath)
		syscall.Exec(gutExe, append([]string{gutExe}, args...), os.Environ())
		status.Fatalf("Failed to exec %s", gutExe)
	}
	args = args[1:]
	var argsRemaining, err = flags.ParseArgs(&OptsCommon, args)
	if err != nil {
		status.Fatal(err)
	}
	// fmt.Printf("color: %s\n", OptsCommon.NoColor)
	if OptsCommon.Version {
		status.Print("gut-sync version XXXXX")
		os.Exit(0)
	}
	bismuth.SetVerbose(OptsCommon.Verbose)

	signalChan := make(chan os.Signal, 1)
	signal.Notify(signalChan, os.Interrupt)
	go func() {
		<-signalChan
		Shutdown("Received SIGINT.")
	}()

	if cmd == "build" {
		var local = NewSyncContext()
		err := local.Connect()
		if err != nil {
			status.Fatal(err)
		}
		didSomething, err := EnsureBuild(local, local)
		if err != nil {
			status.Fatal(err)
		}
		if !didSomething {
			status.Printf("@(dim:gut) " + GitVersion + " @(dim:has already been built.)\n")
		}
	} else if cmd == "sync" {
		var remoteArgs, err = flags.ParseArgs(&OptsSync, argsRemaining)
		if err != nil {
			status.Fatal(err)
		}

		local := NewSyncContext()
		err = local.ParseSyncPath(OptsSync.Positional.LocalPath)
		if err != nil {
			status.Fatal(err)
		}
		err = local.Connect()
		if err != nil {
			status.Fatal(err)
		}
		local.KillAllViaPidfiles()

		remotes := []*SyncContext{}
		for _, remotePath := range remoteArgs {
			remote := NewSyncContext()
			err = remote.ParseSyncPath(remotePath)
			if err != nil {
				status.Fatal(err)
			}
			err = remote.Connect()
			if err != nil {
				status.Fatal(err)
			}
			remote.KillAllViaPidfiles()
			remotes = append(remotes, remote)
		}

		err = Sync(local, remotes)
		if err != nil {
			status.Fatal(err)
		}
	}
}
