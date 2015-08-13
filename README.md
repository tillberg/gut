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

Installation from source
========================

You'll need the go compiler installed (v1.4 or later) first. The [Go Install][Go install documentation]
is a good place to start if you haven't set it up already.

After you have Go installed, you also need to [Go Setup][set your GOPATH]. You probably just want to
use the defaults: (add these to your `.profile`/`.bash_profile` to persist to new shell sessions)

```sh
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin
```

To install **gut** to $GOPATH/bin, just run:

```sh
go get github.com/tillberg/gut
```

Installation via curlbash
=========================

If you have not a care for security, you could just cross your fingers and run this:




Getting Started
===============

You want to create a pair of linked folders, **~/work** locally and **~/work2** on
**my.server.com**. Fire up a terminal and run something like this:

(Note: The first time you run this on each machine, **gut** will build its dependencies and
prompt you about anything extra that you need to install.)

```sh
$ gut sync ~/work username@my.server.com:~/work
```

![Animated Gif showing initial setup](https://www.tillberg.us/c/119d8cb31272eddb3984f9a7557a0ddce0b43580/gut-init.gif)

This command sets up a gut repo locally in ~/work and clones it to your ~/work2
directory on my.server.com, then starts watching the filesystem on both ends for
changes. When a change is made, gut-sync commits the change and then merges it
to the other server.

Open up a second terminal and make gut do some work:

```sh
$ cd ~/work
$ git clone https://github.com/tillberg/gut.git
$ cd gut
$ rm util_test.go
$ git add . --all
$ git commit -m 'made all tests pass'
```

Then hop onto the other host and take a look at what's there.

```sh
$ cd ~/work2/gut
$ git log --stat
# ... <- You should see the commit you just made
$ gut log --stat
# ... <- You should see *all* the file changes recorded here, including inside ~/work2/gut/.git/
```

![Animated Gif showing git folders syncing over gut](https://www.tillberg.us/c/eb78b0141cc960b45e4651753a6486c00f4918be/gut-git.gif)

Configuration
=============

To exclude files from gut-sync, use **.gutignore** files just as you'd use **.gitignore** over in
git-world.

SSH Authentication Issues
=========================

**gut-sync** connects to the ssh agent specified by `SSH_AUTH_SOCK` and uses the experimental
[crypto/ssh][golang.org/x/crypto/ssh] SSH client. This does not, for example, read any settings
in ~/.ssh/config, and it may differ in a number of other ways from using the `ssh` OpenSSH client,
such as Username settings and Hostname aliases. For many, this will work just fine (as it does
on all of my systems). If it doesn't work for you, though, please create issues and/or PRs with
as much detail as you can provide about where it breaks down (thanks!).

Supported OSes
==============

**gut** has been tested on **OSX** and **Ubuntu** as both the local and remote hosts.

I've done some implementation work for Windows (and had a fully-functioning Python implementation
before porting to Go -- it's definitely feasible), and so if you're interested in either using that
or helping to implement, open up an issue for discussion and/or tag https://github.com/tillberg/gut/issues/4.

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

[Go Install]: https://golang.org/doc/install
[Go Setup]: https://golang.org/doc/code.html
[crypto/ssh]: https://godoc.org/golang.org/x/crypto/ssh
