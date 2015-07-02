import os.path

GIT_REPO_URL = 'https://github.com/git/git.git'
GIT_VERSION = 'v2.4.5'

GUT_PATH = '~/.gut'
GUT_SRC_PATH = os.path.join(GUT_PATH, 'gut-src')
GUT_DIST_PATH = os.path.join(GUT_PATH, 'gut-build')
GUT_EXE_PATH = os.path.join(GUT_DIST_PATH, 'bin/gut')

GUTD_BIND_PORT = 34924
GUTD_CONNECT_PORT = 34925
AUTOSSH_MONITOR_PORT = 34927

# Ignore files that are probably transient by default
# You can add/remove additional globs to both the root .gutignore and to
# any other .gutignore file in the repo hierarchy.
DEFAULT_GUTIGNORE = '''
# Added by `gut sync` during repo init:
*.lock
.#*
'''.lstrip()
