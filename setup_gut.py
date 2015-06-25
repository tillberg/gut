#!/usr/bin/env python

import codecs
import multiprocessing
import os
import shutil
import stat
import subprocess
from sys import platform as _platform
is_osx = _platform == 'darwin'

GIT_VERSION = 'v2.4.4'

def system(s, cwd=None):
    for line in s.strip().split('\n'):
        print('> %s' % (line,))
        subprocess.call(line, cwd=cwd, shell=True)

system("npm install")
if is_osx:
    system('brew install libyaml')
else:
    system('sudo apt-get install gettext libyaml-dev curl libcurl4-openssl-dev libexpat1-dev autoconf') #python-pip python-dev
    system('sudo sysctl fs.inotify.max_user_watches=1048576')

#echo 'kern.maxfiles=20480' | sudo tee -a /etc/sysctl.conf
#echo -e 'limit maxfiles 8192 20480\nlimit maxproc 1000 2000' | sudo tee -a /etc/launchd.conf
#echo 'ulimit -n 4096' | sudo tee -a /etc/profile

#sudo pip install -r requirements.txt
if not os.path.exists('gut'):
    system('git clone https://github.com/git/git.git gut/')
else:
    system('git fetch', 'gut/')
system('git reset --hard %s' % (GIT_VERSION,), 'gut/')
system('git clean -fd', 'gut/')

def rename_git_to_gut(s):
    return s.replace('GIT', 'GUT').replace('Git', 'Gut').replace('git', 'gut')

for root, dirs, files in os.walk('gut/'):
    for filename in files:
        if filename == '.gitignore':
            # don't touch .gitignores
            continue
        orig_path = os.path.join(root, filename)
        path = os.path.join(root, rename_git_to_gut(filename))
        if orig_path != path:
            print('renaming file %s -> %s' % (orig_path, path))
            os.rename(orig_path, path)
        with codecs.open(path, 'r', 'utf-8') as fd:
            try:
                orig_contents = fd.read()
            except UnicodeDecodeError:
                # print('Could not read UTF-8 from %s' % (path,))
                continue
        contents = rename_git_to_gut(orig_contents)
        if contents != orig_contents:
            print('rewriting %s' % (path,))
            # Force read-only files to be writable
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
            print('renaming folder %s -> %s' % (orig_path, path))
            shutil.move(orig_path, path)
        dirs.append(folder)

dist_path = os.path.abspath('gut-dist')
system('''
make prefix=%s -j %s
make prefix=%s install
''' % (dist_path, multiprocessing.cpu_count(), dist_path), 'gut/')
