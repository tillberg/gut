import codecs
import shutil
import stat
import os

import plumbum

import config
import deps
from terminal import out, out_dim, dim, color_path
import util

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
    for root, dirs, files in os.walk(root_path):
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
                # This prevents gut-gui/GUT-VERSION-GEN from calling `gut` and causing `gut_proxy` from recursively building `gut` in an infinite loop.
                contents = contents.replace('gut ', 'git ')
            if contents != orig_contents:
                # print('rewriting %s' % (path,))
                # Force read-only files to be writable so that we can modify them
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWRITE)
                with codecs.open(path, 'w', 'utf-8') as fd:
                    fd.write(contents)
        orig_dirs = tuple(dirs)
        del dirs[:]
        for folder in orig_dirs:
            if folder == '.git':
                # don't recurse into .git
                continue
            orig_path = os.path.join(root, folder)
            folder = rename_git_to_gut(folder)
            path = os.path.join(root, folder)
            if orig_path != path:
                # print('renaming folder %s -> %s' % (orig_path, path))
                shutil.move(orig_path, path)
            dirs.append(folder)

def git_clone_update(repo_url, src_path, version, rewrite_gut=True):
    local = plumbum.local
    ensure_gut_folders(local)
    gut_src_path = local.path(src_path)
    if not (gut_src_path / '.git').exists():
        out(dim('Cloning ') + repo_url + dim(' into ') + color_path(gut_src_path) + dim('...'))
        local['git']['clone', repo_url, gut_src_path]()
        out_dim(' done.\n')
    if not (gut_src_path / '.git').exists():
        out(dim('Cloning ') + repo_url + dim(' into ') + color_path(gut_src_path) + dim('...'))
        local['git']['clone', repo_url, gut_src_path]()
        out_dim(' done.\n')
    with local.cwd(gut_src_path):
        if not local['git']['rev-parse', version](retcode=None).strip():
            out(dim('Updating git in order to upgrade to ') + version + dim('...'))
            local['git']['fetch']()
            out_dim(' done.\n')
        out(dim('Checking out fresh copy of git ') + version + dim('...'))
        local['git']['reset', '--hard', version]()
        local['git']['clean', '-fd']()
        if rewrite_gut:
            out_dim(' done.\nRewriting git to gut...')
            rename_git_to_gut_recursive('%s' % (gut_src_path,))
        out_dim(' done.\n')

def gut_prepare(build_context):
    if build_context._is_windows:
        git_clone_update(config.MSYSGIT_REPO_URL, config.MSYSGIT_PATH, config.MSYSGIT_VERSION, rewrite_gut=False)
        git_clone_update(config.GIT_WIN_REPO_URL, config.GUT_WIN_SRC_PATH, config.GIT_WIN_VERSION)
    else:
        git_clone_update(config.GIT_REPO_URL, config.GUT_SRC_PATH, config.GIT_VERSION)

def gut_build(context):
    gut_src_path = context.path(config.GUT_SRC_PATH)
    gut_dist_path = context.path(config.GUT_DIST_PATH)
    install_prefix = 'prefix=%s' % (gut_dist_path,)
    with context.cwd(gut_src_path):
        def build():
            out(dim('Configuring Makefile for gut...'))
            context['make'][install_prefix, 'configure']()
            context[gut_src_path / 'configure'][install_prefix]()
            parallelism = util.get_num_cores(context)
            out(dim(' done.\nBuilding gut using up to ') + parallelism + dim(' processes...'))
            context['make'][install_prefix, '-j', parallelism]()
            out(dim(' installing to ') + color_path(gut_dist_path) + dim('...'))
            context['make'][install_prefix, 'install']()
            out(dim(' done.\n'))
        deps.retry_method(context, build)
