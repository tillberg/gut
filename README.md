gut
===

Realtime bidirectional folder synchronization via modified git

Are you editing code on one machine and running it on another? Perhaps you're using
OSX to host your editor, but the application you're working on runs on Linux, and/or
is running on a remote server. Maybe you use rsync or NFS or git push/pull scripts
to synchronize your work. Or maybe you edit code in emacs-nox or vim on a remote
server but would be much happier running a graphical editor locally if only you could
quickly and easily (and safely) push changes to the remote server.

Gut solves this problem by using a modified version of git to synchronize changes
between multiple systems (it currently syncs only two at a time, but it could be
patched to support N remotes) in real-time.

Installation
============

You'll need **pip** and the python dev headers installed first in order to install **gut**.
To get **pip**, check out https://pip.pypa.io/en/latest/installing.html.

You might be able to just do one of these:

```sh
(Ubuntu) $ sudo apt-get install python-pip python-dev
(OSX w/easy_install) $ sudo easy_install pip
```

First, install **gut** via **pip**.

```sh
$ pip install gut
```

Depending on your system you may need to prepend "sudo":

```sh
$ sudo pip install gut
```

Next, to build **gut**:

```sh
$ gut build
Need to build gut on localhost.
Cloning https://github.com/git/git.git into /home/ubuntu/.gut/gut-src... done.
Checking out fresh copy of git v2.4.5... done.
Rewriting git to gut... done.
Configuring Makefile for gut... done.
Building gut using up to 4 processes... installing to /home/ubuntu/.gut/gut-build... done.
```

This clones git, rewrites it to gut, then builds it locally. **gut** will be rebuilt
the first time that you sync to each remote host, as well.

Whenever **gut** is missing any dependencies, it should spit out a message telling you what you need
to install. If you tack `--install-deps` onto commands, gut will try to install dependencies for you.
However, if any of this doesn't work for you (I only have so many system to test on), file an issue
and I'll help you figure out what's broke and how to fix it for everyone else in the future, too.

Getting Started
===============

Here's how **gut-sync** works.

```sh
$ gut sync ~/work my.server.com:~/work2
```

This command sets up a gut repo locally in ~/work and clones it to your ~/work2
directory on my.server.com, then starts watching the filesystem on both ends for
changes. When a change is made, gut-sync commits the change and then merges it
to the other server.

Open up a second terminal and make gut do some work:

```sh
$ cd ~/work
$ git clone https://github.com/tillberg/gut.git
$ cd gut
$ rm -r gut/
$ git add --all .
$ git commit -m "Fixed"
```

Then hop onto the other host and take a look at what's there.

```sh
$ cd ~/work2/gut
$ git log --stat
# ... <- You should see the commit you just made
$ gut log --stat
# ... <- You should see *all* the file changes recorded here, including inside ~/work2/gut/.git/
```

To exclude files from gut-sync, use **.gutignore** files just as you'd use **.gitignore** over in
git-world.

SSH Authentication Issues
=========================

By default, **gut-sync** uses paramiko to make the primary SSH connection to the remote host. If you
have trouble connection/authenticating, try specifying `--use-openssl`. The OpenSSL-based plumbum
machinery isn't quite as fast/efficient as paramiko, but it might work for you.

Supported OSes
==============

**gut** has been tested and runs well on **OSX** and **Ubuntu** (both as the local and remote hosts).
I expect that it should work on a lot of other Linuxes; other BSDs will probably require at least
some small **plumbum** patches. I'd love to help if anyone wanted to get it running on Windows.

Gut is like Git, but with more U and less I
===========================================

The reason it's necessary to use a modified version of git, and not git itself,
is that stock git will refuse to traverse into .git folders, which is critical
to using gut-sync to synchronize folders containing git repos.

You can use gut just like you'd use git, if you wanted, though:

```sh
$ gut init
Initialized empty Gut repository in /tmp/test/.gut/
$ touch README
$ gut add README
$ gut commit -m 'First gut commit'
[master (root-commit) f216bb4] First gut commit
 1 file changed, 0 insertions(+), 0 deletions(-)
 create mode 100644 README
```

This means that you can use the various **gut**(git) commands, e.g `gut log -p`,
`gut show HEAD`, `gut log --stat`, and even `gutk` (it's installed at
`~/.guts/gut-build/bin/gutk`) to examine the history of whatever **gut-sync**
does. So if and when **gut-sync** screws something up, you might be able to repair
the damage by referencing the gut history and/or doing a hard-reset to an older
version. (though, ahem... Legal Note: The author(s) of this software are not
liable for any damage caused by its use. See LICENSE.)

You'll probably have a tough time speaking to remote git repos, though. Github,
for one, doesn't support **gut-receive-pack**. :)

```sh
$ gut push -u origin master
Invalid command: 'gut-receive-pack 'tillberg/test.git''
  You appear to be using ssh to clone a git:// URL.
  Make sure your core.gitProxy config option and the
  GIT_PROXY_COMMAND environment variable are NOT set.
fatal: Could not read from remote repository.
```
