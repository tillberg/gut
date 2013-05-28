guts
====

Synchronize a folder hierarchy with a clone of git where everything
"git" is renamed "gut".  This allows gut to synchronize .git folders.

Install
=======

- Clone this and then run `git submodule update --init`
- For Ubuntu, `sudo apt-get npm` to install nodejs and npm
- For OSX, install homebrew and the XCode command line tools, then
  `brew install nodejs` followed by `curl https://npmjs.org/install.sh | sudo sh`
  to install nodejs and npm.
- Run `setup_gut.sh`.  This will clone and build gut and download watchdog
  and a couple other dependencies.
