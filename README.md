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

Getting Started
===============

Install gut via pip. Depending on your system you may need to prepend "sudo":

    > pip install gut

Here's how it works.


    > gut sync ~/work my.server.com:~/work

This command sets up a gut repo locally in ~/work and clones it to your ~/work
directory on my.server.com, then starts watching the filesystem on both ends for
changes. When a change is made, gut-sync commits the change and then merges it
to the other server.



