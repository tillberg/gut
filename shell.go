package main

import (
	"fmt"
	"github.com/jessevdk/go-flags"
	"github.com/tillberg/ansi-log"
	"github.com/tillberg/bismuth"
	"os"
	"os/signal"
	"os/user"
	"path"
	"strings"
	"sync"
	"syscall"
	"time"
)

var OptsCommon struct {
	Verbose     bool `short:"v" long:"verbose" description:"Show verbose debug information"`
	Version     bool `long:"version"`
	NoColor     bool `long:"no-color"`
}

var OptsSync struct {
	IdentityFile string `short:"i" long:"identity"`
	Positional   struct {
		LocalPath string
	} `positional-args:"yes" required:"yes"`
}

const commitDebounceDuration = 100 * time.Millisecond

func Sync(local *SyncContext, remotes []*SyncContext) (err error) {
	status := local.NewLogger("sync")
	defer status.Close()
	allContexts := append([]*SyncContext{local}, remotes...)
	hostsStrs := []string{}
	for _, ctx := range allContexts {
		hostsStrs = append(hostsStrs, ctx.SyncPathAnsi())
	}
	hostsStr := JoinWithAndAndCommas(hostsStrs...)
	status.Printf("@(dim:Starting gut-sync between) %s@(dim:.)\n", hostsStr)

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
	repoName := RandSeq(8)

	// Start up gut-daemon on the local host, and create a reverse tunnel from each of the remote hosts
	// back to the local gut-daemon. All hosts can connect to gut-daemon at localhost:<gutdPort>, which
	// makes configuration a little simpler.
	ready := make(chan bool)
	numTasks := 0
	goTask := func(taskCtx *SyncContext, fn func(*SyncContext)) {
		numTasks++
		go func() {
			fn(taskCtx)
			ready <- true
		}()
	}
	joinTasks := func() {
		for numTasks > 0 {
			<-ready
			numTasks--
		}
	}
	goTask(local, func(taskCtx *SyncContext) {
		err := taskCtx.GutDaemon(repoName, gutdPort)
		if err != nil {
			status.Bail(err)
		}
	})
	for _, ctx := range remotes {
		if !ctx.IsLocal() {
			goTask(ctx, func(taskCtx *SyncContext) {
				err = taskCtx.ReverseTunnel(gutdAddr, gutdAddr)
				if err != nil {
					status.Bail(err)
				}
			})
		}
	}
	joinTasks()
	for _, ctx := range allContexts {
		goTask(ctx, func(taskCtx *SyncContext) {
			taskCtx.UpdateTailHash()
		})
	}
	joinTasks()

	// Find tailHash, if any. Bail if there are conflicting tailHashes.
	tailHash := ""
	var tailHashFoundOn *SyncContext
	localTailHash := local.GetTailHash()
	if localTailHash != "" {
		tailHash = localTailHash
		tailHashFoundOn = local
	}
	contextsNeedInit := []*SyncContext{}
	for _, ctx := range remotes {
		myTailHash := ctx.GetTailHash()
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
					status.Printf("@(commit:%s) @(error:at) %s\n",
						TrimCommit(tailHash), tailHashFoundOn.SyncPathAnsi())
					status.Printf("@(commit:%s) @(error:at) %s\n",
						TrimCommit(myTailHash), ctx.SyncPathAnsi())
					Shutdown(status.Colorify("@(error:Cannot sync incompatible gut repos.)"))
				}
				goTask(ctx, func(taskCtx *SyncContext) {
					err := taskCtx.GutSetupOrigin(repoName, gutdPort)
					if err != nil {
						status.Bail(err)
					}
				})
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
			local.UpdateTailHash()
			tailHash = local.GetTailHash()
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
			joinTasks() // Wait for GutSetupOrigin on tailHashFoundOn to finish
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
		goTask(local, func(taskCtx *SyncContext) {
			err := taskCtx.GutSetupOrigin(repoName, gutdPort)
			if err != nil {
				status.Bail(err)
			}
		})
	}
	for _, ctx := range contextsNeedInit {
		goTask(ctx, func(taskCtx *SyncContext) {
			err := taskCtx.GutInit()
			if err != nil {
				status.Bail(err)
			}
			err = taskCtx.GutSetupOrigin(repoName, gutdPort)
			if err != nil {
				status.Bail(err)
			}
			err = taskCtx.GutPull()
			if err != nil {
				status.Bail(err)
			}
		})
	}
	joinTasks()

	type FileEvent struct {
		ctx      *SyncContext
		filepath string
	}
	eventChan := make(chan FileEvent)

	commitScoped := func(src *SyncContext, changedPaths []string, updateUntracked bool) (changed bool, err error) {
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
		changed, err = src.GutCommit(prefix, updateUntracked)
		if err != nil {
			status.Bail(err)
		}
		return changed, nil
	}

	fileEventCallbackGen := func(ctx *SyncContext) func(filepath string) {
		return func(filepath string) {
			eventChan <- FileEvent{ctx, filepath}
		}
	}

	for _, ctx := range allContexts {
		goTask(ctx, func(taskCtx *SyncContext) {
			taskCtx.WatchForChanges(fileEventCallbackGen(taskCtx))
		})
	}
	joinTasks()

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
		changedCtxChan := make(chan *SyncContext)
		for ctx, pathMap := range changedPaths {
			go func(taskCtx *SyncContext, taskPathMap map[string]bool) {
				paths := []string{}
				for path := range taskPathMap {
					paths = append(paths, path)
				}
				_, changedThisIgnore := changedIgnore[taskCtx]
				changed, err := commitScoped(taskCtx, paths, changedThisIgnore)
				if err != nil {
					status.Bail(err)
				}
				if changed {
					changedCtxChan <- taskCtx
				} else {
					changedCtxChan <- nil
				}
			}(ctx, pathMap)
		}
		changedCtxs := []*SyncContext{}
		for _ = range changedPaths {
			ctx := <-changedCtxChan
			if ctx != nil {
				changedCtxs = append(changedCtxs, ctx)
			}
		}
		if len(changedCtxs) > 0 {
			for _, ctx := range changedCtxs {
				if ctx != local {
					err = ctx.GutPush()
					if err != nil {
						status.Bail(err)
					}
					err = local.GutMerge(ctx.BranchName())
					if err != nil {
						status.Bail(err)
					}
				}
			}
			localMasterCommit, err := local.GutRevParseHead()
			if err != nil {
				status.Bail(err)
			}
			// Push the update out to all the remotes
			done := make(chan error)
			for _, ctx := range remotes {
				go func(taskCtx *SyncContext) {
					myCommit, err := taskCtx.GutRevParseHead()
					if err != nil {
						done <- err
						return
					}
					if myCommit != localMasterCommit {
						err = taskCtx.GutPull()
					}
					done <- err
				}(ctx)
			}
			for _, ctx := range remotes {
				err = <-done
				if err == NeedsCommitError {
					status.Printf("@(dim:Need to commit on) %s @(dim:before it can pull.)\n", ctx.NameAnsi())
					eventChan <- FileEvent{ctx, "*"}
					err = nil
				}
				if err != nil {
					status.Bail(err)
				}
			}
		}
		clearChanges()
	}

	go func() {
		// Note: The filesystem watchers are not necessarily listening to all updates yet, so we could miss file changes that occur between
		// the commit_and_update calls below and the time that the filesystem watches are attached.
		for _, ctx := range allContexts {
			// Queue up an event to force checking for changes.
			eventChan <- FileEvent{ctx, "*"}
		}
	}()

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
			} else if part == ".gutignore" || part == "*" {
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
	// log.EnableMultilineMode()
	log.EnableColorTemplate()
	log.AddAnsiColorCode("error", 31)
	log.AddAnsiColorCode("commit", 32)
	log.AddAnsiColorCode("path", 36)
	var args []string = os.Args[1:]
	if len(args) == 0 {
		fmt.Println("You must specify a gut-command, e.g. `gut sync ...`")
		os.Exit(1)
	}
	var cmd = args[0]
	if IsGitCommand(cmd) {
		if IsDangerousGitCommand(cmd) {
			if len(args) < 2 || args[1] != "--danger" {
				status := log.New(os.Stderr, "", 0)
				status.Printf("@(dim:In order to prevent damage caused by accidentally using `)gut %s ...@(dim:`)\n", cmd)
				status.Printf("@(dim:in cases where `)git %s ...@(dim:` was intended, you must append `)--danger@(dim:`)\n", cmd)
				status.Printf("@(dim:immediately after the command, i.e. `)gut %s --danger ...@(dim:`.)\n", cmd)
				status.Printf("@(dim:Alternatively, you could invoke) gut @(dim:directly at) @(path:%s)@(dim:.)\n", GutExePath)
				status.Printf("@(dim:The commands that require this flag are:) %s\n", strings.Join(DangerousGitCommands, " "))
				os.Exit(1)
			}
			// Split the "--danger" flag out before handing off the args list to the gut-command:
			if len(args) > 2 {
				args = append(args[:1], args[2:]...)
			} else {
				args = args[:1]
			}
		}
		usr, err := user.Current()
		if err != nil {
			log.Bail(err)
		}
		var gutExe = path.Join(usr.HomeDir, GutExePath[2:])
		syscall.Exec(gutExe, append([]string{gutExe}, args...), os.Environ())
		fmt.Printf("Failed to exec %s", gutExe)
		os.Exit(1)
	}
	status := log.New(os.Stderr, "", 0)
	args = args[1:]
	var argsRemaining, err = flags.ParseArgs(&OptsCommon, args)
	if err != nil {
		status.Bail(err)
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
			status.Bail(err)
		}
		err = local.CheckLocalDeps()
		if err != nil {
			status.Bail(err)
		}
		didSomething, err := EnsureBuild(local, local)
		if err != nil {
			status.Bail(err)
		}
		if !didSomething {
			status.Printf("@(dim:gut) " + GitVersion + " @(dim:has already been built.)\n")
		}
	} else if cmd == "sync" {
		var remoteArgs, err = flags.ParseArgs(&OptsSync, argsRemaining)
		if err != nil {
			status.Bail(err)
		}

		ready := make(chan bool)

		local := NewSyncContext()
		err = local.ParseSyncPath(OptsSync.Positional.LocalPath)
		if err != nil {
			status.Bail(err)
		}
		go func() {
			err = local.Connect()
			if err != nil {
				status.Bail(err)
			}
			err = local.CheckLocalDeps()
			if err != nil {
				status.Bail(err)
			}
			local.KillAllViaPidfiles()
			ready <- true
		}()

		remotes := []*SyncContext{}
		for _, remotePath := range remoteArgs {
			remote := NewSyncContext()
			remotes = append(remotes, remote)
			err = remote.ParseSyncPath(remotePath)
			if err != nil {
				status.Bail(err)
			}
			go func(_remote *SyncContext) {
				err = _remote.Connect()
				if err != nil {
					status.Bail(err)
				}
				_remote.KillAllViaPidfiles()
				err = _remote.CheckRemoteDeps()
				if err != nil {
					status.Bail(err)
				}
				ready <- true
			}(remote)
		}

		for i := 0; i < len(remotes)+1; i++ {
			<-ready
		}

		err = Sync(local, remotes)
		if err != nil {
			status.Bail(err)
		}
	}
}
