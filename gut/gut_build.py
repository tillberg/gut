import codecs
import shutil
import stat
import os

import plumbum

from . import config
from . import deps
from .terminal import out, out_dim, dim, color_path, Writer
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

def git_hard_reset_and_clean(repo_url, repo_path, version):
    local = plumbum.local
    with local.cwd(local.path(repo_path)):
        # Do a little sanity-check to make sure we're not running these (destructive) operations in some other repo:
        if not repo_url in local['git']['remote', '-v']():
            raise Exception('I think I might be trying to git-reset the wrong repo.')
        local['git']['reset', '--hard', version]()
        local['git']['clean', '-fdx']()

def git_clone_update(repo_url, _local_path, version):
    local = plumbum.local
    ensure_gut_folders(local)
    local_path = local.path(_local_path)
    if not (local_path / '.git').exists():
        out(dim('Cloning ') + repo_url + dim(' into ') + color_path(local_path) + dim('...'))
        local['git']['clone', repo_url, local_path]()
        out_dim(' done.\n')
    with local.cwd(local_path):
        # Prevent windows from checking out CRLF line endings and then syncing them to a linux box, which subsequently
        # runs into weird errors due to the CRLFs:
        local['git']['config', 'core.autocrlf', 'false']()
        if not local['git']['rev-parse', version](retcode=None).strip():
            out(dim('Updating ') + repo_url + dim(' in order to upgrade to ') + version + dim('...'))
            local['git']['fetch']()
            out_dim(' done.\n')
    out(dim('Checking out ') + version + dim('...'))
    git_hard_reset_and_clean(repo_url, local_path, version)
    out_dim(' done.\n')

def prepare(build_context):
    def rewrite(gut_src_path):
        out_dim('Rewriting git to gut...')
        rename_git_to_gut_recursive(str(plumbum.local.path(gut_src_path)))
        out_dim(' done.\n')
    if build_context._is_windows:
        git_clone_update(config.MSYSGIT_REPO_URL, config.MSYSGIT_PATH, config.MSYSGIT_VERSION)
        git_clone_update(config.GIT_WIN_REPO_URL, config.GUT_WIN_SRC_PATH, config.GIT_WIN_VERSION)
        rewrite(config.GUT_WIN_SRC_PATH)
    else:
        git_clone_update(config.GIT_REPO_URL, config.GUT_SRC_PATH, config.GIT_VERSION)
        rewrite(config.GUT_SRC_PATH)

def unprepare(build_context):
    if build_context._is_windows:
        git_hard_reset_and_clean(config.MSYSGIT_REPO_URL, config.MSYSGIT_PATH, config.MSYSGIT_VERSION)
        git_hard_reset_and_clean(config.GIT_WIN_REPO_URL, config.GUT_WIN_SRC_PATH, config.GIT_WIN_VERSION)
    else:
        git_hard_reset_and_clean(config.GIT_REPO_URL, config.GUT_SRC_PATH, config.GIT_VERSION)

def windows_path_to_mingw_path(path):
    return '/' + str(path).replace(':', '').replace('\\', '/')

def build(context, _build_path):
    build_path = context.path(_build_path)
    gut_dist_path = context.path(config.GUT_DIST_PATH)
    install_prefix = 'prefix=%s' % (windows_path_to_mingw_path(gut_dist_path) if context._is_windows else gut_dist_path,)
    with context.cwd(build_path):
        def build():
            status = Writer(context)
            log = Writer(context, 'make')
            def make(name, args):
                if context._is_windows:
                    make_path = windows_path_to_mingw_path(context.path(config.MSYSGIT_PATH) / 'bin/make.exe')
                    context[context.path(config.MSYSGIT_PATH) / 'bin/bash.exe']['-c', ('PATH=/bin:/mingw/bin NO_GETTEXT=1 ' + ' '.join([make_path] + args))]()
                else:
                    # context['make'][args]()
                    Writer(context, 'make_' + name).quote(context['make'][args].popen())
            if not context._is_windows:
                status.out(dim('Configuring Makefile for gut...'))
                make('configure', [install_prefix, 'configure'])
                context[build_path / 'configure'][install_prefix]()
                status.out(dim(' done.\n'))
            parallelism = util.get_num_cores(context)
            status.out(dim('Building gut using up to ') + parallelism + dim(' processes...'))
            make('build', [install_prefix, '-j', parallelism])
            status.out(dim(' installing to ') + color_path(gut_dist_path) + dim('...'))
            make('install', [install_prefix, 'install'])
            status.out(dim(' done.\n'))
        deps.retry_method(context, build)
