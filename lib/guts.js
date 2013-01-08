#!/usr/bin/env node

// process.title is read-only on OSX / darwin.
// but generally, I'll be the only user on an OSX system, so whatever.
process.title = 'guts';

var http = require('http');
var util = require('util');
var fs = require('fs');
var path = require('path');
var async = require('async');

var common = require('tillberg_common');
var _ = require('underscore')._;
_.mixin(require('underscore.string'));

var remoteUser = process.argv[2];
var remoteHost = process.argv[3];
var remoteFolder = process.argv[4];

var HTTP_PORT = 3294;

if (remoteHost === 'auto') {
  remoteHost = process.env['SSH_CLIENT'].split(' ')[0];
  console.log('auto-detected original remote host of ' + remoteHost);
} else {
  var localUser = process.env['USER'];
  var cmd = 'cd ~/guts && git pull origin master; killall -q node -u ' + localUser + ';';
  cmd = cmd + 'killall -q guts -u ' + localUser + '; killall -q gutsmon -u ' + localUser + '; sleep 2; ';
  cmd = cmd + 'cd ' + remoteFolder + ' && node ~/guts/lib/guts.js ' + localUser + ' auto ' + path.resolve('./');
  console.log(cmd);
  var args = [
     '-o',
     'StrictHostKeyChecking=no',
     remoteUser + '@' + remoteHost,
     cmd
  ];
  var proc = exec('ssh', args, { cwd: './' }, function(err) {
    console.log('ssh connection terminated.');
  });
  proc.stdout.on('line', function(d) {
    console.log('[remote] ' + d);
  });
}

function time() {
  return (new Date()).getTime();
}
function throttledAsync(cb, throttleDelay, invokeDelay) {
  var timeout
    , fire = false
    , lastfire = false
    , inflight = false;
  return function() {
    if (!timeout) {
      var nextDelay = throttleDelay - (time() - lastfire);
      function callIt() {
        lastfire = time();
        inflight = true;
        setTimeout(function() {
          cb(function() {
            inflight = false;
            if (fire) {
              fire = false;
              callIt();
            }
          });
        }, invokeDelay);
      }
      function tryToCall() {
        if (inflight) {
          fire = true;
        } else {
          callIt();
        }
      }
      if (nextDelay <= 0) {
        tryToCall();
      } else {
        timeout = setTimeout(function() {
          tryToCall();
          timeout = undefined;
        }, nextDelay);
      }
    }
  };
}

function needToPull() {
  console.log('need to pull');
  pull = true;
  onChange();
}

http.createServer(function (req, res) {
  needToPull();
  res.writeHead(200, {'Content-Type': 'text/plain'});
  res.end('OK\n');
}).listen(HTTP_PORT);

var initted = false;
var changed = [];
var removed = [];
var pull = false;

function madeACommit() {
  console.log('We made a new commit');
  exec('curl', ['-s', remoteHost + ':' + HTTP_PORT + '/'], { cwd: './' }, function(err) {});
}

function gutUp(done) {
  if (!initted) {
    initted = true;
    exec('gut', ['init'], { cwd: './', pipe: true }, function(err) {
      exec('gut', ['add', '.'], { cwd: './', pipe: true }, function(err) {
        exec('gut', ['commit', '-a', '-m', 'post-walk commit'], { cwd: './', pipe: true }, function(err) {
          done();
          madeACommit();
          needToPull();
        });
      });
    });
  } else if (pull) {
    pull = false;
    console.log('pulling...');
    exec('gut', ['remote', 'rm', 'origin'], { cwd: './' }, function(err) {
      exec('gut', ['remote', 'add', 'origin', remoteUser + '@' + remoteHost + ':' + remoteFolder], { cwd: './' }, function(err) {
          exec('gut', ['pull', 'origin', 'master'], { cwd: './', env: { GUT_SSH: path.join(__dirname, 'gut-ssh.sh') } }, function(err) {
          donePulling();
        });
      });
    })
    function donePulling() {
      if (changed.length || removed.length) {
        onChange();
      }
      done();
    }
  } else {
    var _changed = _.uniq(changed);
    var _removed = _.uniq(removed);
    changed = [];
    removed = [];
    function add() {
      function _add(f, cb) {
        info('gut-adding ' + f);
        exec('gut', ['add', f], { cwd: './', pipe: true }, function(err) { cb(); });
      }
      if (_changed.length) {
        async.forEachSeries(_changed, _add, commit);
      } else {
        commit();
      }
    }
    function remove() {
      function _remove(f, cb) {
        exec('gut', ['rm', '--cached'].concat(_removed), { cwd: './', pipe: true }, cb);
      }
      if (_removed.length) {
        async.forEachSeries(_removed, _remove, add);
      } else {
        add();
      }
    }
    function commit() {
      exec('gut', ['rev-parse', 'HEAD'], { cwd: './' }, function(err, data) {
        exec('gut', ['commit', '--untracked-files=no', '-a', '-m', 'autocommit'], { cwd: './', pipe: true }, function(err) {
          exec('gut', ['rev-parse', 'HEAD'], { cwd: './' }, function(err, data2) {
            if (data !== data2) {
              madeACommit();
            } else {
              console.log('We did not actually make a commit');
            }
            done();
          });
        });
      })
    }
    remove();
  }
}

var onChange = throttledAsync(gutUp, 1000, 100);
onChange();

console.log('starting monitor');
var monitor = exec(path.join(__dirname, 'monitor.py'), [path.resolve('./')], { cwd: './' }, function(err, data) {
  error('monitor exited');
});
monitor.stdout.on('line', function(line) {
  var match = (/(\w+) (.*)/).exec(line);
  var event = match[1];
  var filename = match[2];
  if (event === 'deleted') {
    removed.push(filename);
  } else {
    changed.push(path.dirname(filename));
  }
  onChange();
  info(line);
});
