gut (gut-sync)
==============

What would happen if you took git, sed, rsync, and inotify, and you mushed and kneaded
them together until smooth? You'd get **gut-sync**: *real-time bi-directional folder synchronization*.

I wrote gut so that I can edit source code locally on my desktop, have the programs I'm
working on run either in the cloud or in a VM, and then I can seamlessly transition
to a laptop -- with all of my changes synced continuously to each of these machines.
I don't want to work with flakey remote filesystems, and I do want to have inotify
(or kqueue or FSEvents or whatever) work correctly so that I can kick off builds just
by hitting Save in my editor.

**gut-sync** solves this problem for me by using a modified version of git to synchronize
changes between multiple (1 to N) systems in real-time. It's efficient and stable, written
in Go, but it's sort of like a big shell script written in Go: all the heavy lifting is done
by calling out to other utilities. It uses inotifywait (on Linux) or fswatch (on OSX) to
listen for file changes, and then orchestrates calls to gut-commands (such as gut-add or
gut-fetch) on each system in order to keep all systems up-to-date.

![Animated Gif showing git folders syncing over gut](https://www.tillberg.us/c/eb78b0141cc960b45e4651753a6486c00f4918be/gut-git.gif)

Installation via curlbash
=========================

If you have not a care for security, you could just cross your fingers and run this:

**TODO**

This will download and install the correct `gut` Go binary into `/usr/local/bin`,
and the pre-built `gut-*` C binaries and libraries into `$HOME/.guts`.

Installation from source
========================

To install from source, first you'll need the go compiler installed (v1.4 or later).
The [Go install documentation][Go Install] is a good place to start if you haven't set
up Go already.

After you have Go installed, you also need to [set your GOPATH][Go Setup]. You probably just want to
use the defaults: (add these to your `.profile`/`.bash_profile` to persist to new shell sessions)

```sh
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin
```

With that all configured, to install **gut** into $GOPATH/bin, run:

```sh
go get github.com/tillberg/gut
```

The first time you run **gut-sync** on each host, it will build its dependencies and
prompt you about extra dependencies that you need to download & install.

![Animated Gif showing dependency detection and build](https://www.tillberg.us/c/7265e7d41db88a5f2a7b1d0acefea6b22eb7e4a3/gut-build.gif)

Getting Started
===============

Let's say that you want to create a pair of linked folders, **~/work** locally and
**~/work2** on **my.server.com**. Fire up a terminal and run something like this:

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

Configuration
=============

To exclude files from gut-sync, use **.gutignore** files just as you'd use **.gitignore** over in
git-world.

SSH Authentication Issues
=========================

**gut-sync** connects to the ssh agent specified by `SSH_AUTH_SOCK` and uses the experimental
[golang.org/x/crypto/ssh][crypto/ssh] SSH client. This does not, for example, read any settings
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
is that *stock git will refuse to traverse into .git folders*, which is critical
to using gut-sync to synchronize folders containing git repos. Other than the
name-change, though, gut is the same as git.

You can use gut just like you'd use git, if you want:

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
does. So if and when **gut-sync** screws something up, you might (*might*) be
able to repair the damage by referencing the gut history and/or doing a
hard-reset to an older version.

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

License
=======

[ISC License][ISC License]

[Go Install]: https://golang.org/doc/install
[Go Setup]: https://golang.org/doc/code.html
[crypto/ssh]: https://godoc.org/golang.org/x/crypto/ssh
[ISC License]: https://github.com/tillberg/gut/blob/master/LICENSE
