guts
====

Synchronize a folder hierarchy with a clone of git where everything
"git" is renamed "gut".  This allows gut to synchronize .git folders.

Install
=======

- Clone this and then run `git submodule init --update`
- Install nodejs and npm (`sudo apt-get npm` on ubuntu, or `brew install npm`
  followed by `curl https://npmjs.org/install.sh | sudo sh` on OSX).
- Run `setup_gut.sh`.  This will clone and build gut and download watchdog
  and a couple other dependencies.
