import os.path

GIT_REPO_URL = 'https://github.com/git/git.git'
GIT_VERSION = 'v2.4.4'
GIT_WIN_REPO_URL = 'https://github.com/git-for-windows/git.git'
GIT_WIN_VERSION = 'v2.4.4'
MSYSGIT_REPO_URL = 'https://github.com/msysgit/msysgit.git'
MSYSGIT_VERSION = 'Git-1.9.5-preview20150319'
INOTIFY_WIN_REPO_URL = 'https://github.com/thekid/inotify-win.git'
INOTIFY_WIN_VERSION = '9b547cfde0f546df8abeebf47ec36f36d7bd91ef'

GUT_PATH = '~/.guts'
GUT_SRC_PATH = '/'.join([GUT_PATH, 'gut-src'])
GUT_SRC_TMP_PATH = '/'.join([GUT_PATH, 'gut-src-tmp'])
GUT_WIN_SRC_PATH = '/'.join([GUT_PATH, 'gut-win-src'])
MSYSGIT_PATH = '/'.join([GUT_PATH, 'msysgit'])
INOTIFY_WIN_PATH = '/'.join([GUT_PATH, 'inotify-win'])
GUT_DIST_PATH = '/'.join([GUT_PATH, 'gut-build'])
GUT_EXE_PATH = '/'.join([GUT_DIST_PATH, 'bin/gut'])
GUT_DAEMON_PATH = '/'.join([GUT_PATH, 'repos'])

MIN_RANDOM_PORT = 34000
MAX_RANDOM_PORT = 34999

# Ignore files that are probably transient by default
# You can add/remove additional globs to both the root .gutignore and to
# any other .gutignore file in the repo hierarchy.
DEFAULT_GUTIGNORE = '''
# Added by `gut sync` during repo init:
*.lock
.#*
*.pyc
'''.lstrip()

ALL_GUT_COMMANDS = (
    # These are all the names of executables in libexec/gut-core/
    'add',
    'am',
    'annotate',
    'apply',
    'archimport',
    'archive',
    'bisect',
    'blame',
    'branch',
    'bundle',
    'cat-file',
    'check-attr',
    'check-ignore',
    'check-mailmap',
    'checkout',
    'checkout-index',
    'check-ref-format',
    'cherry',
    'cherry-pick',
    'citool',
    'clean',
    'clone',
    'column',
    'commit',
    'commit-tree',
    'config',
    'count-objects',
    'credential',
    'credential-cache',
    'credential-store',
    'cvsexportcommit',
    'cvsimport',
    'cvsserver',
    'daemon',
    'describe',
    'diff',
    'diff-files',
    'diff-index',
    'difftool',
    'diff-tree',
    'fast-export',
    'fast-import',
    'fetch',
    'fetch-pack',
    'filter-branch',
    'fmt-merge-msg',
    'for-each-ref',
    'format-patch',
    'fsck',
    'fsck-objects',
    'gc',
    'get-tar-commit-id',
    'grep',
    'gui',
    'hash-object',
    'help',
    'http-backend',
    'imap-send',
    'index-pack',
    'init',
    'init-db',
    'instaweb',
    'interpret-trailers',
    'log',
    'ls-files',
    'ls-remote',
    'ls-tree',
    'mailinfo',
    'mailsplit',
    'merge',
    'merge-base',
    'merge-file',
    'merge-index',
    'merge-octopus',
    'merge-one-file',
    'merge-ours',
    'merge-recursive',
    'merge-resolve',
    'merge-subtree',
    'mergetool',
    'merge-tree',
    'mktag',
    'mktree',
    'mv',
    'name-rev',
    'notes',
    'p4',
    'pack-objects',
    'pack-redundant',
    'pack-refs',
    'parse-remote',
    'patch-id',
    'prune',
    'prune-packed',
    'pull',
    'push',
    'quiltimport',
    'read-tree',
    'rebase',
    'receive-pack',
    'reflog',
    'relink',
    'remote',
    'remote-ext',
    'remote-fd',
    'remote-testsvn',
    'repack',
    'replace',
    'request-pull',
    'rerere',
    'reset',
    'revert',
    'rev-list',
    'rev-parse',
    'rm',
    'send-email',
    'send-pack',
    'shell',
    'sh-i18n',
    'shortlog',
    'show',
    'show-branch',
    'show-index',
    'show-ref',
    'sh-setup',
    'stage',
    'stash',
    'status',
    'stripspace',
    'submodule',
    'svn',
    'symbolic-ref',
    'tag',
    'unpack-file',
    'unpack-objects',
    'update-index',
    'update-ref',
    'update-server-info',
    'upload-archive',
    'upload-pack',
    'var',
    'verify-commit',
    'verify-pack',
    'verify-tag',
    'whatchanged',
    'write-tree',
    # This is an extra special built-in (an alias for --version, I guess):
    'version',
)
