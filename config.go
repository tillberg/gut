package main

const GitRepoUrl = "https://github.com/git/git.git"
const GitVersion = "v2.5.0"
const GitWinRepoUrl = "https://github.com/git-for-windows/git.git"
const GitWinVersion = "v2.4.4"
const MsysgitRepoUrl = "https://github.com/msysgit/msysgit.git"
const MsysgitVersion = "Git-1.9.5-preview20150319"
const InotifyWinRepoUrl = "https://github.com/thekid/inotify-win.git"
const InotifyWinVersion = "9b547cfde0f546df8abeebf47ec36f36d7bd91ef"

var gutTarballHashes = map[string]string{
	"darwin-amd64": "2cbf485213af3061a3d5ce27211295ae804d535ed4854f9da6d57418bcc39424",
	"linux-386":    "b3ee92d6147c20d154843739c5a94fe28822f835f99d3ea20821d79ce107a313",
	"linux-amd64":  "d437b2008d313974b4b5a4293bcf93b8b681e65919c74099e6016975387d7eae",
}

const GutPath = "~/.guts"
const GutSrcPath = GutPath + "/gut-src"
const GutSrcTmpPath = GutPath + "/gut-src-tmp"
const GutWinSrcPath = GutPath + "/gut-win-src"
const MsysgitPath = GutPath + "/msysgit"
const InotifyWinPath = GutPath + "/inotify-win"
const GutDistPath = GutPath + "/gut-build"
const PidfilesPath = GutPath + "/pidfiles"
const GutExePath = GutDistPath + "/bin/gut"
const GutDaemonPath = GutPath + "/repos"

const MinRandomPort = 34000
const MaxRandomPort = 34999

// Ignore files that are probably transient or machine-specific by default.
// You can add/remove additional globs to both the root .gutignore and to
// any other .gutignore file in the repo hierarchy.
const DefaultGutignore = ("# Added by `gut sync` during repo init:" + `
*.lock
.#*

# Various compiled resources:
*.pyc
*.o
*.a
*.so
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
	"whatchanged",
	"write-tree",

	// This is an extra/special built-in (an alias for --version, I presume):
	"version",
	"--version",
}

var DangerousGitCommands = []string{
	"reset",
	"checkout",
	"clean",
	"rm",
}
