package main

import (
	"errors"
	"fmt"
	"github.com/kballard/go-shellquote"
	"io/ioutil"
	"os"
	"path"
	"strings"
	"unicode/utf8"
)

func (ctx *SyncContext) EnsureGutFolders() (err error) {
	err = ctx.Mkdirp(GutSrcPath)
	if err != nil {
		return err
	}
	err = ctx.Mkdirp(GutWinSrcPath)
	if err != nil {
		return err
	}
	err = ctx.Mkdirp(GutDistPath)
	return err
}

func renameGitToGut(s string) string {
	s = strings.Replace(s, "git", "gut", -1)
	s = strings.Replace(s, "Git", "Gut", -1)
	s = strings.Replace(s, "GIT", "GUT", -1)
	s = strings.Replace(s, "digut", "digit", -1)
	s = strings.Replace(s, "DIGUT", "DIGIT", -1)
	return s
}

func rewriteGitToGutRecursive(pathRoot string) (err error) {
	entries, err := ioutil.ReadDir(pathRoot)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		origName := entry.Name()
		// Don't modify .gitignore, and don't recurse into .git
		if len(origName) >= 4 && origName[:4] == ".git" {
			continue
		}
		name := renameGitToGut(origName)
		p := path.Join(pathRoot, name)
		if origName != name {
			os.Rename(path.Join(pathRoot, origName), p)
		}
		if entry.IsDir() {
			err = rewriteGitToGutRecursive(p)
			if err != nil {
				return err
			}
		} else {
			_origContents, err := ioutil.ReadFile(p)
			if err != nil {
				return err
			}
			if !utf8.Valid(_origContents) {
				continue
			}
			origContents := string(_origContents)
			contents := renameGitToGut(origContents)
			if name == "read-cache.c" {
				// This is a special case super-optimized string parse for the 'i' in 'git':
				contents = strings.Replace(contents, "rest[1] != 'i' && rest[1] != 'I'", "rest[1] != 'u' && rest[1] != 'U'", -1)
			}
			if name == "utf8.c" {
				contents = strings.Replace(contents, "if (c != 'i' && c != 'I'", "if (c != 'u' && c != 'U'", -1)
			}
			if name == "GUT-VERSION-GEN" {
				// GUT-VERSION-GEN attempts to use `git` to look at the git repo's history in order to determine the version string.
				// This prevents gut-gui/GUT-VERSION-GEN from calling `gut` and causing `gut_proxy` to recursively build `gut` in an infinite loop.
				contents = strings.Replace(contents, "gut ", "git ", -1)
			}
			if origContents != contents {
				err = ioutil.WriteFile(p, []byte(contents), os.FileMode(0644))
				if err != nil {
					return err
				}
			}
		}
	}
	return nil
}

func RewriteGitToGut(local *SyncContext, pathRoot string) (err error) {
	status := local.NewLogger("rewrite")
	defer status.Close()
	status.Printf("@(dim:Rewriting git to gut...)")
	err = rewriteGitToGutRecursive(local.AbsPath(pathRoot))
	if err != nil {
		status.Printf("@(error: failed)@(dim:.)\n")
		return err
	}
	status.Printf("@(dim: done.)\n")
	return nil
}

func GitHardResetAndClean(local *SyncContext, localPath string, repoUrl string, version string) (err error) {
	// Do a little sanity-check to make sure we're not running these (destructive) operations in some other repo:
	gitRemoteOut, err := local.OutputCwd(localPath, "git", "remote", "-v")
	if err != nil {
		return err
	}
	if !strings.Contains(gitRemoteOut, repoUrl) {
		return errors.New("I think I might be trying to git-reset the wrong repo.")
	}
	_, err = local.QuoteCwd("git-reset", localPath, "git", "reset", "--quiet", "--hard", version)
	if err != nil {
		return err
	}
	_, err = local.QuoteCwd("git-clean", localPath, "git", "clean", "-fdxq")
	return err
}

func GitCloneUpdate(local *SyncContext, localPath string, repoUrl string, version string) (err error) {
	status := local.NewLogger("")
	defer status.Close()
	err = local.EnsureGutFolders()
	if err != nil {
		return err
	}
	exists, err := local.PathExists(path.Join(localPath, ".git"))
	if err != nil {
		return err
	}
	if !exists {
		p := local.AbsPath(localPath)
		status.Printf("@(dim:Cloning) %s @(dim:into) @(path:%s)@(dim:...)\n", repoUrl, p)
		_, err = local.Quote("git-clone", "git", "clone", "--progress", repoUrl, p)
		if err != nil {
			return err
		}
	}
	// Prevent windows from checking out CRLF line endings and then syncing them to a linux box, which subsequently
	// runs into weird errors due to the CRLFs:
	_, err = local.OutputCwd(localPath, "git", "config", "core.autocrlf", "false")
	if err != nil {
		return err
	}
	_, _, retCode, err := local.RunCwd(localPath, "git", "rev-parse", version)
	if retCode != 0 {
		status.Printf("@(dim:Fetching latest from) %s @(dim:in order to upgrade to) %s @(dim:...)", repoUrl, version)
		_, err = local.QuoteCwd("git-fetch", localPath, "git", "fetch")
		if err != nil {
			return err
		}
		status.Printf("@(dim: done.)\n")
	}
	status.Printf("@(dim:Checking out) %s @(dim:...)", version)
	err = GitHardResetAndClean(local, localPath, repoUrl, version)
	if err != nil {
		return err
	}
	status.Printf("@(dim: done.)\n")
	return nil
}

func GutBuildPrepare(local *SyncContext, ctx *SyncContext) (err error) {
	if ctx.IsWindows() {
		err = GitCloneUpdate(local, MsysgitPath, MsysgitRepoUrl, MsysgitVersion)
		if err != nil {
			return err
		}
		err = GitCloneUpdate(local, GutWinSrcPath, GitWinRepoUrl, GitWinVersion)
		if err != nil {
			return err
		}
		err = RewriteGitToGut(local, GutWinSrcPath)
	} else {
		err = GitCloneUpdate(local, GutSrcPath, GitRepoUrl, GitVersion)
		if err != nil {
			return err
		}
		err = RewriteGitToGut(local, GutSrcPath)
	}
	return err
}

func (ctx *SyncContext) GutBuild(buildPath string) (err error) {
	buildPath = ctx.AbsPath(buildPath)
	gutDistPath := ctx.AbsPath(GutDistPath)
	var installPrefix string
	if ctx.IsWindows() {
		installPrefix = "prefix=" + WindowsPathToMingwPath(gutDistPath)
	} else {
		installPrefix = "prefix=" + gutDistPath
	}
	status := ctx.NewLogger("build")
	defer status.Close()
	doMake := func(name string, args ...string) (retCode int, err error) {
		if ctx.IsWindows() {
			makePath := ctx.AbsPath(path.Join(MsysgitPath, "bin/make.exe"))
			cdCmd := shellquote.Join("cd", buildPath)
			makeCmd := "PATH=/bin:/mingw/bin NO_GETTEXT=1 " + shellquote.Join(append([]string{makePath}, args...)...)
			return ctx.QuoteShell("make-"+name, cdCmd+" && "+makeCmd)
		} else {
			return ctx.QuoteCwd("make-"+name, buildPath, append([]string{"make"}, args...)...)
		}
	}
	if !ctx.IsWindows() {
		status.Printf("@(dim:Configuring Makefile for gut...)\n")
		retCode, err := doMake("configure", installPrefix, "configure")
		if err != nil || retCode != 0 {
			Shutdown(status.Colorify("@(error:`make configure` failed during gut build.)"))
		}
		retCode, err = ctx.QuoteCwd("autoconf", buildPath, ctx.AbsPath(path.Join(buildPath, "configure")), installPrefix)
		if err != nil || retCode != 0 {
			Shutdown(status.Colorify("@(error:`configure` failed during gut build.)"))
		}
	}
	parallelism := ctx.GetNumCores()
	status.Printf("@(dim:Building gut using up to) %s @(dim:processes...)\n", parallelism)
	retCode, err := doMake("build", installPrefix, "-j", parallelism)
	if err != nil || retCode != 0 {
		Shutdown(status.Colorify("@(error:`make` failed during gut build.)"))
	}
	status.Printf("@(dim:Finished building gut.)\n")
	status.Printf("@(dim:Installing gut to) @(path:%s)@(dim:...)\n", gutDistPath)
	retCode, err = doMake("install", installPrefix, "install")
	if err != nil || retCode != 0 {
		Shutdown(status.Colorify("@(error:`make install` failed during gut build.)"))
	}
	status.Printf("@(dim:Finished installing gut to) @(path:%s)@(dim:.)\n", gutDistPath)
	return nil
}

func GutUnprepare(local *SyncContext, ctx *SyncContext) (err error) {
	if ctx.IsWindows() {
		GitHardResetAndClean(local, MsysgitPath, MsysgitRepoUrl, MsysgitVersion)
		GitHardResetAndClean(local, GutWinSrcPath, GitWinRepoUrl, GitWinVersion)
	} else {
		GitHardResetAndClean(local, GutSrcPath, GitRepoUrl, GitVersion)
	}
	if !ctx.IsLocal() {
		_, err = ctx.Quote("cleanup", "rm", "-r", ctx.AbsPath(GutSrcTmpPath))
		if err != nil {
			return err
		}
	}
	return nil
}

func BuildGut(local *SyncContext, ctx *SyncContext) (err error) {
	status := ctx.Logger()
	status.Printf("@(dim:Need to build gut on) %s@(dim:.)\n", ctx.NameAnsi())
	err = ctx.EnsureGutFolders()
	if err != nil {
		status.Bail(err)
	}
	err = GutBuildPrepare(local, ctx)
	if err != nil {
		status.Bail(err)
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
		status := ctx.NewLogger("")
		status.Printf("@(dim:Uploading) %s:@(path:%s) @(dim:to) %s:@(path:%s)@(dim:...)", local.NameAnsi(), GutSrcPath, ctx.NameAnsi(), buildPath)
		local.UploadRecursiveExcludes(GutSrcPath, ctx.ExecContext, buildPath, []string{".git", "t"})
		status.Printf(" @(dim: done.)\n")
	}
	err = ctx.GutBuild(buildPath)
	if err != nil {
		status.Bail(err)
	}
	status.Printf("@(dim:Cleaning up...)")
	err = GutUnprepare(local, ctx)
	if err != nil {
		status.Bail(err)
	}
	status.Printf(" @(dim: done.)\n")
	status.Printf("@(green:Successfully built gut commands.)\n")
	return nil
}

func InstallGut(local *SyncContext, ctx *SyncContext) (err error) {
	status := ctx.Logger()
	status.Printf("@(dim:Need to install gut on) %s@(dim:.)\n", ctx.NameAnsi())
	err = ctx.EnsureGutFolders()
	if err != nil {
		status.Bail(err)
	}
	uname := strings.ToLower(ctx.Uname())
	machine, err := ctx.Output("uname", "-m")
	if err != nil {
		status.Bail(err)
	}
	arch := "386"
	if machine == "x86_64" {
		arch = "amd64"
	}
	systemStr := uname + "-" + arch
	tarballHash, ok := gutTarballHashes[systemStr]
	if !ok {
		status.Printf("Your system appears to be %q, which doesn't have a tarball available. Falling back to building from source.\n", systemStr)
		return BuildGut(local, ctx)
	}
	filename := fmt.Sprintf("gut-%s-build-%s.tgz", GitVersion, systemStr)
	url := fmt.Sprintf("https://www.tillberg.us/c/%s/%s", tarballHash, filename)
	tarballPath := ctx.AbsPath(path.Join(GutPath, filename))
	_, err = ctx.Output("rm", "-f", tarballPath) // Just in case it's already there
	if err != nil {
		status.Bail(err)
	}
	status.Printf("Downloading %s from www.tillberg.us...\n", filename)
	retCode, err := ctx.QuoteCwd("wget", GutPath, "wget", "--progress=bar:force", url)
	if err != nil {
		status.Bail(err)
	}
	if retCode != 0 {
		return errors.New(fmt.Sprintf("Failed to download %q", url))
	}
	status.Printf("Validating SHA256 hash of %s @(dim)(sha256 %s)@(r)\n", filename, tarballHash)
	shasumStr, err := ctx.OutputCwd(GutPath, "shasum", "-a256", filename)
	if err != nil {
		status.Bail(err)
	}
	hashStr := strings.Split(shasumStr, " ")[0]
	if hashStr != tarballHash {
		return errors.New(fmt.Sprintf("Hash validation failed on %s. Got %q, but expected %q", filename, hashStr, tarballHash))
	}
	status.Printf("Validated %s. Extracting to %s.\n", filename, ctx.AbsPath(GutDistPath))
	retCode, err = ctx.QuoteCwd("untar", GutPath, "tar", "xzf", filename)
	if err != nil {
		return err
	}
	if retCode != 0 {
		return errors.New("Failed to untar gut-command tarball")
	}
	_, err = ctx.Output("rm", "-f", tarballPath)
	if err != nil {
		status.Bail(err)
	}
	status.Printf("@(green:Successfully installed gut commands.)\n")
	return nil
}

func EnsureBuild(local *SyncContext, ctx *SyncContext, buildDeps bool) (didSomething bool, err error) {
	if ctx.HasGutInstalled() {
		return false, nil
	}
	if buildDeps {
		err = BuildGut(local, ctx)
		return true, err
	}
	err = InstallGut(local, ctx)
	return true, err
}
