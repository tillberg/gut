gut-sync
========

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

**gut-sync** has been tested on and between **OSX** and **Ubuntu**.

![Animated Gif showing git folders syncing over gut](https://www.tillberg.us/c/b7d8d602e634931c50f957aeb58f9a2c5c4931545b96d6f276cb45d1eca434fe/gut-git.gif)

### Comparison with Similar Tools

There are some other really awesome (perhaps more awesome for your use case) file sync tools out
there. Here are the big differientiators (and may count as plusses or minuses for you) for
**gut-sync** as compared to others:

- **gut-sync uses git under the hood**. (*well, "gut", a [machine-renamed][machine-renamed] version of git*)
  - If you already know git, or are an expert using git, then you can use that experience to
    configure, tweak, and explore/modify the gut-sync history.
  - If you are not familiar at all with git, you may prefer another tool that exposes
    history/versions in a more user-friendly way.
  - If you want to sync a lot of large files, or large rapidly-changing files, the overhead of
    using git (which never deletes history) may be too expensive.
- **gut-sync communicates and deploys itself via SSH**.
  - If you already use SSH everywhere, then this means deploying and using **gut-sync** will be easy.
  - If you don't use SSH, then another tool may be a better fit.

Here's a short list of some other tools you might want to check out:

- [Syncthing][Syncthing]: Really fantastic cross-platform open-source (MPLv2) sync daemon built around
  its own synchronization protocol. Runs a web GUI locally for easy setup.
- [Unison][Unison], [SparkleShare][SparkleShare]: Similar, open-source yet somewhat-abandoned sync tools.
- Finally, there are [Dropbox][Dropbox], [Google Drive][Google Drive], and many other similar
  hosted file sync services. These services store and transmit through a third party, which may
  incur latency and monetary cost in addition to reduced privacy/security.

Installation via curlbash
=========================

If you have not a care for security, you could just cross your fingers and run this:

```sh
bash -c 'S="3bceab0bdc63b2dd7980161ae7d952ea821a23e693cb74961b0d41f61f557489";T="/tmp/gut.sh";set -e;wget -qO- "https://www.tillberg.us/c/$S/gut-1.0.3.sh">$T; echo "$S  $T"|shasum -a256 -c-;bash $T;rm $T'
```

This will download and install the correct `gut` Go binary to `/usr/local/bin/gut`. It verifies
the SHA256 sum of the script it downloads, and then in turn in the SHA256 sum of the binary it
subsequently downloads & installs, but it doesn't verify the integrity of the author.
But *shrug*, right?

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

With that all configured, to install **gut-sync** into $GOPATH/bin, run:

```sh
go get github.com/tillberg/gut
```

By default **gut-sync** will download (and verify) pre-built binaries for gut-commands.
You can optionally build these from source; much of the process is actually automated
but requires the same dependencies (build-essentials, autoconf, etc) required to build
git from source. To do so, use `--build-deps`, i.e. `gut sync --build-deps ...`.

Getting Started
===============

Let's say that you want to create a pair of linked folders, **~/work** locally and
**~/work2** on **my.server.com**. Fire up a terminal and run something like this:

```sh
$ gut sync ~/work username@my.server.com:~/work
```

![Animated Gif showing initial setup](https://www.tillberg.us/c/395daa91a84e82c77d5c0c874f4eb11ec58d2170f8424d34de19b155a6fc2a0c/gut-init.gif)

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

Configuration et al.
====================

#### Excluding files and folders

To exclude files from **gut-sync**, use **.gutignore** files just as you'd use **.gitignore** over in
git-world.

#### SSH Authentication

**gut-sync** connects to the ssh agent specified by `SSH_AUTH_SOCK` and uses the experimental
[golang.org/x/crypto/ssh][crypto/ssh] SSH client. This does not, for example, read any settings
in ~/.ssh/config, and it may differ in a number of other ways from using the `ssh` OpenSSH client,
such as Username settings and Hostname aliases. For many, this will work just fine (as it does
on all of my systems). If it doesn't work for you, though, please create issues and/or PRs with
as much detail as you can provide about where it breaks down (thanks!).

#### "Please increase the amount of inotify watches allowed per user"

If you see this message, it means you've run out of inotify watch slots. You can increase this limit
temporarily by writing to `/proc/sys/fs/inotify/max_user_watches`, or permanently by modifying the
`fs.inotify.max_user_watches` sysctl property. See
[this great page about inotify max_user_watches][guard/listen inotify reference] on the guard/listen
project for tips and additional details.

Alternately, you could reduce the total number of directories inside the folder you're synchronizing.
In addition to removing folders you don't wish to sync, some options include running `git gc` inside
less-used repositories, removing unused `node_modules` dependencies (which tend to span a large number
of directories), and more generally scanning the output of `find /path/to/gut/repo -type d` for cases
where a large number of directories is being used.

Note that inotifywait/fswatch don't exclude `.gutignore`d paths from being wired up for change
notifications, which would be a great way to cut down on noise and watch-slot consumption from large
directory hierarchies which we're not synchronizing, anyway.

#### Windows support?

I've done some implementation work for Windows (and had a fully-functioning Python implementation
before porting to Go -- it's definitely feasible), and so if you're interested in either using that
or helping to implement, open up an issue for discussion and/or tag https://github.com/tillberg/gut/issues/4.

Gut is like Git, but with more U and less I
===========================================

The reason it's necessary to use a modified version of git, and not git itself,
is that *stock git will refuse to traverse into .git folders*, which is critical
to using **gut-sync** to synchronize folders containing git repos. Other than the
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

[machine-renamed]: https://github.com/tillberg/gut/blob/37cbc3748d674c46b2481220afdf34dd0a4b8e34/gut_build.go#L36-L101
[Go Install]: https://golang.org/doc/install
[Go Setup]: https://golang.org/doc/code.html
[crypto/ssh]: https://godoc.org/golang.org/x/crypto/ssh
[ISC License]: https://github.com/tillberg/gut/blob/master/LICENSE.md

[Syncthing]: https://syncthing.net/
[Unison]: http://www.cis.upenn.edu/~bcpierce/unison/
[SparkleShare]: http://sparkleshare.org/
[Dropbox]: https://www.dropbox.com/
[Google Drive]: https://www.google.com/drive/
[guard/listen inotify reference]: https://github.com/guard/listen/wiki/Increasing-the-amount-of-inotify-watchers
