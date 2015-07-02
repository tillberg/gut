import codecs
import shutil
import stat
import os

import config
import deps
from terminal import out, out_dim, dim, color_path

def ensure_gut_folders(context):
    context['mkdir']['-p', context.path(config.GUT_SRC_PATH)]()
    context['mkdir']['-p', context.path(config.GUT_DIST_PATH)]()

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

def gut_prepare(context):
    ensure_gut_folders(context)
    gut_src_path = context.path(config.GUT_SRC_PATH)
    if not (gut_src_path / '.git').exists():
        out(dim('Cloning ') + config.GIT_REPO_URL + dim(' into ') + color_path(gut_src_path) + dim('...'))
        context['git']['clone', config.GIT_REPO_URL, gut_src_path]()
        out_dim(' done.\n')
    with context.cwd(gut_src_path):
        if not context['git']['rev-parse', config.GIT_VERSION](retcode=None).strip():
            out(dim('Updating git in order to upgrade to ') + config.GIT_VERSION + dim('...'))
            context['git']['fetch']()
            out_dim(' done.\n')
        out(dim('Checking out fresh copy of git ') + config.GIT_VERSION + dim('...'))
        context['git']['reset', '--hard', config.GIT_VERSION]()
        context['git']['clean', '-fd']()
        context['make']['clean']()
        out_dim(' done.\nRewriting git to gut...')
        rename_git_to_gut_recursive('%s' % (gut_src_path,))
        out_dim(' done.\n')


def gut_build(context):
    gut_src_path = context.path(config.GUT_SRC_PATH)
    gut_dist_path = context.path(config.GUT_DIST_PATH)
    install_prefix = 'prefix=%s' % (gut_dist_path,)
    with context.cwd(gut_src_path):
        def build():
            parallelism = context['getconf']['_NPROCESSORS_ONLN']().strip()
            out(dim('Configuring Makefile for gut...'))
            context['make'][install_prefix, 'configure']()
            context[gut_src_path / 'configure'][install_prefix]()
            out(dim(' done.\nBuilding gut using up to ') + parallelism + dim(' processes...'))
            context['make'][install_prefix, '-j', parallelism]()
            out(dim(' installing to ') + color_path(gut_dist_path) + dim('...'))
            context['make'][install_prefix, 'install']()
            out(dim(' done.\n'))
        deps.retry_method(context, build)
