package main

import (
    "log"
    "os/user"
    "path"
)

const GitRepoUrl = "https://github.com/git/git.git"
const GitVersion = "v2.4.4"
const GitWinRepoUrl = "https://github.com/git-for-windows/git.git"
const GitWinVersion = "v2.4.4"
const MsysgitRepoUrl = "https://github.com/msysgit/msysgit.git"
const MsysgitVersion = "Git-1.9.5-preview20150319"
const InotifyWinRepoUrl = "https://github.com/thekid/inotify-win.git"
const InotifyWinVersion = "9b547cfde0f546df8abeebf47ec36f36d7bd91ef"

const GutPath = ".guts"
const GutSrcPath = GutPath + "/gut-src"
const GutSrcTmpPath = GutPath + "/gut-src-tmp"
const GutWinSrcPath = GutPath + "/gut-win-src"
const MsysgitPath = GutPath + "/msysgit"
const InotifyWinPath = GutPath + "/inotify-win"
const GutDistPath = GutPath + "/gut-build"
const GutExePath = GutDistPath + "/bin/gut"
const GutDaemonPath = GutPath + "/repos"

func PathInUserHome(subpath string) string {
    usr, err := user.Current()
    if err != nil {
        log.Fatal(err)
    }
    return path.Join(usr.HomeDir, subpath)
}

const MinRandomPort = 34000
const MaxRandomPort = 34999

// Ignore files that are probably transient or machine-specific by default.
// You can add/remove additional globs to both the root .gutignore and to
// any other .gutignore file in the repo hierarchy.
const DefaultGutignore = (
"# Added by `gut sync` during repo init:" + `
*.lock
.#*
*.pyc
`)

var AllGutCommands = [...]string{
    // These are all the names of executables in libexec/gut-core/
    "add",
    "am",
    "annotate",
    "apply",
    "archimport",
    "archive",
    "bisect",
    "blame",
    "branch",
    "bundle",
    "cat-file",
    "check-attr",
    "check-ignore",
    "check-mailmap",
    "checkout",
    "checkout-index",
    "check-ref-format",
    "cherry",
    "cherry-pick",
    "citool",
    "clean",
    "clone",
    "column",
    "commit",
    "commit-tree",
    "config",
    "count-objects",
    "credential",
    "credential-cache",
    "credential-store",
    "cvsexportcommit",
    "cvsimport",
    "cvsserver",
    "daemon",
    "describe",
    "diff",
    "diff-files",
    "diff-index",
    "difftool",
    "diff-tree",
    "fast-export",
    "fast-import",
    "fetch",
    "fetch-pack",
    "filter-branch",
    "fmt-merge-msg",
    "for-each-ref",
    "format-patch",
    "fsck",
    "fsck-objects",
    "gc",
    "get-tar-commit-id",
    "grep",
    "gui",
    "hash-object",
    "help",
    "http-backend",
    "imap-send",
    "index-pack",
    "init",
    "init-db",
    "instaweb",
    "interpret-trailers",
    "log",
    "ls-files",
    "ls-remote",
    "ls-tree",
    "mailinfo",
    "mailsplit",
    "merge",
    "merge-base",
    "merge-file",
    "merge-index",
    "merge-octopus",
    "merge-one-file",
    "merge-ours",
    "merge-recursive",
    "merge-resolve",
    "merge-subtree",
    "mergetool",
    "merge-tree",
    "mktag",
    "mktree",
    "mv",
    "name-rev",
    "notes",
    "p4",
    "pack-objects",
    "pack-redundant",
    "pack-refs",
    "parse-remote",
    "patch-id",
    "prune",
    "prune-packed",
    "pull",
    "push",
    "quiltimport",
    "read-tree",
    "rebase",
    "receive-pack",
    "reflog",
    "relink",
    "remote",
    "remote-ext",
    "remote-fd",
    "remote-testsvn",
    "repack",
    "replace",
    "request-pull",
    "rerere",
    "reset",
    "revert",
    "rev-list",
    "rev-parse",
    "rm",
    "send-email",
    "send-pack",
    "shell",
    "sh-i18n",
    "shortlog",
    "show",
    "show-branch",
    "show-index",
    "show-ref",
    "sh-setup",
    "stage",
    "stash",
    "status",
    "stripspace",
    "submodule",
    "svn",
    "symbolic-ref",
    "tag",
    "unpack-file",
    "unpack-objects",
    "update-index",
    "update-ref",
    "update-server-info",
    "upload-archive",
    "upload-pack",
    "var",
    "verify-commit",
    "verify-pack",
    "verify-tag",
    "version", // This is an extra/special built-in (an alias for --version, I presume):
    "whatchanged",
    "write-tree",
}

func IsGitCommand(s string) bool {
    for _, a := range AllGutCommands { if a == s { return true } }
    return false
}
