import asyncio
import codecs
import shutil
import stat
import os

from . import config
from . import deps
from .terminal import Writer, quote_proc
from . import util

def ensure_gut_folders(context):
    util.mkdirp(context, config.GUT_SRC_PATH)
    util.mkdirp(context, config.GUT_WIN_SRC_PATH)
    util.mkdirp(context, config.GUT_DIST_PATH)

def rename_git_to_gut(s):
    return (s
        .replace('GIT', 'GUT')
        .replace('Git', 'Gut')
        .replace('git', 'gut')
        .replace('digut', 'digit')
        .replace('DIGUT', 'DIGIT')
    )

@asyncio.coroutine
def rename_git_to_gut_recursive(root_path):
    for root, folders, files in os.walk(root_path):
        for orig_filename in files:
            if orig_filename.startswith('.git'):
                # don't touch .gitignores or .gitattributes files
                continue
            orig_path = os.path.join(root, orig_filename)
            filename = rename_git_to_gut(orig_filename)
            path = os.path.join(root, filename)
            if orig_path != path:
                # print('renaming file %s -> %s' % (orig_path, path))
                os.rename(orig_path, path)
            with codecs.open(path, 'r', 'utf-8') as fd:
                try:
                    orig_contents = fd.read()
                except UnicodeDecodeError:
                    # print('Could not read UTF-8 from %s' % (path,))
                    continue
            contents = rename_git_to_gut(orig_contents)
            if filename == 'read-cache.c':
                # This is a special case super-optimized string parse for the 'i' in 'git':
                contents = contents.replace("rest[1] != 'i' && rest[1] != 'I'", "rest[1] != 'u' && rest[1] != 'U'")
            if filename == 'utf8.c':
                contents = contents.replace("if (c != 'i' && c != 'I'", "if (c != 'u' && c != 'U'")
            if filename == 'GUT-VERSION-GEN':
                # GUT-VERSION-GEN attempts to use `git` to look at the git repo's history in order to determine the version string.
                # This prevents gut-gui/GUT-VERSION-GEN from calling `gut` and causing `gut_proxy` to recursively build `gut` in an infinite loop.
                contents = contents.replace('gut ', 'git ')
            if contents != orig_contents:
                # print('rewriting %s' % (path,))
                # Force read-only files to be writable so that we can modify them
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWRITE)
                with codecs.open(path, 'w', 'utf-8') as fd:
                    fd.write(contents)
        orig_folders = tuple(folders)
        del folders[:]
        for folder in orig_folders:
            if folder == '.git':
                # don't recurse into .git
                continue
            orig_path = os.path.join(root, folder)
            folder = rename_git_to_gut(folder)
            path = os.path.join(root, folder)
            if orig_path != path:
                # print('renaming folder %s -> %s' % (orig_path, path))
                shutil.move(orig_path, path)
            folders.append(folder)

@asyncio.coroutine
def git_hard_reset_and_clean(repo_url, repo_path, version):
    local = plumbum.local
    with local.cwd(local.path(repo_path)):
        # Do a little sanity-check to make sure we're not running these (destructive) operations in some other repo:
        if not repo_url in local['git']['remote', '-v']():
            raise Exception('I think I might be trying to git-reset the wrong repo.')
        yield from quote_proc(local, '(@dim)git-reset', local['git']['reset', '--hard', version].popen(), quiet_out=True)
        yield from quote_proc(local, '(@dim)git-clean', local['git']['clean', '-fdx'].popen(), quiet_out=True)

@asyncio.coroutine
def git_clone_update(repo_url, _local_path, version):
    local = plumbum.local
    status = Writer(local)
    ensure_gut_folders(local)
    local_path = local.path(_local_path)
    if not (local_path / '.git').exists():
        status.out('(@dim)Cloning (@r)%s (@dim)into (@path)%s(@dim)...\n' % (repo_url, local_path))
        yield from quote_proc(local, '(@dim)git-clone', local['git']['clone', '--progress', repo_url, local_path].popen())
    with local.cwd(local_path):
        # Prevent windows from checking out CRLF line endings and then syncing them to a linux box, which subsequently
        # runs into weird errors due to the CRLFs:
        local['git']['config', 'core.autocrlf', 'false']()
        if not local['git']['rev-parse', version](retcode=None).strip():
            status.out('(@dim)Updating (@r)%s (@dim)in order to upgrade to (@r)%s (@dim)...' % (repo_url, version))
            yield from quote_proc(local, '(@dim)git-fetch', local['git']['fetch'].popen())
            status.out('(@dim) done.\n')
    status.out('(@dim)Checking out (@r)%s (@dim)...' % (version,))
    yield from git_hard_reset_and_clean(repo_url, local_path, version)
    status.out('(@dim) done.\n')

@asyncio.coroutine
def prepare(build_context):
    local = plumbum.local
    status = Writer(local)
    @asyncio.coroutine
    def rewrite(gut_src_path):
        status.out('(@dim)Rewriting git to gut...(@r)')
        yield from rename_git_to_gut_recursive(str(local.path(gut_src_path)))
        status.out('(@dim) done.(@r)\n')
    if build_context._is_windows:
        yield from git_clone_update(config.MSYSGIT_REPO_URL, config.MSYSGIT_PATH, config.MSYSGIT_VERSION)
        yield from git_clone_update(config.GIT_WIN_REPO_URL, config.GUT_WIN_SRC_PATH, config.GIT_WIN_VERSION)
        yield from rewrite(config.GUT_WIN_SRC_PATH)
    else:
        yield from git_clone_update(config.GIT_REPO_URL, config.GUT_SRC_PATH, config.GIT_VERSION)
        yield from rewrite(config.GUT_SRC_PATH)

@asyncio.coroutine
def unprepare(build_context):
    if build_context._is_windows:
        yield from git_hard_reset_and_clean(config.MSYSGIT_REPO_URL, config.MSYSGIT_PATH, config.MSYSGIT_VERSION)
        yield from git_hard_reset_and_clean(config.GIT_WIN_REPO_URL, config.GUT_WIN_SRC_PATH, config.GIT_WIN_VERSION)
    else:
        yield from git_hard_reset_and_clean(config.GIT_REPO_URL, config.GUT_SRC_PATH, config.GIT_VERSION)

def windows_path_to_mingw_path(path):
    return '/' + str(path).replace(':', '').replace('\\', '/')

@asyncio.coroutine
def build(context, _build_path):
    build_path = context.path(_build_path)
    gut_dist_path = context.path(config.GUT_DIST_PATH)
    install_prefix = 'prefix=%s' % (windows_path_to_mingw_path(gut_dist_path) if context._is_windows else gut_dist_path,)
    with context.cwd(build_path):
        @asyncio.coroutine
        def build():
            status = Writer(context)
            log = Writer(context, 'make')
            @asyncio.coroutine
            def make(name, args):
                if context._is_windows:
                    make_path = windows_path_to_mingw_path(context.path(config.MSYSGIT_PATH) / 'bin/make.exe')
                    context[context.path(config.MSYSGIT_PATH) / 'bin/bash.exe']['-c', ('PATH=/bin:/mingw/bin NO_GETTEXT=1 ' + ' '.join([make_path] + args))]()
                else:
                    proc = context['make'][args].popen()
                    yield from quote_proc(context, '(@dim)make_' + name, proc)
            if not context._is_windows:
                status.out('(@dim)Configuring Makefile for gut...')
                yield from make('configure', [install_prefix, 'configure'])
                yield from quote_proc(context, '(@dim)autoconf', context[build_path / 'configure'][install_prefix].popen())
                status.out('(@dim) done.\n')
            parallelism = util.get_num_cores(context)
            status.out('(@dim)Building gut using up to(@r) %s (@dim)processes...' % (parallelism,))
            yield from make('build', [install_prefix, '-j', parallelism])
            status.out('(@dim) done.\n(@dim)Installing gut to (@path)%s(@r)(@dim)...' % (gut_dist_path,))
            yield from make('install', [install_prefix, 'install'])
            status.out('(@dim) done.\n')
        yield from deps.retry_method(context, build)
