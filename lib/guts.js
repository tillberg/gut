var http = require('http');
var util = require('util');

var watch = require('watch');
var common = require('tillberg_common');
var _ = require('underscore')._;
_.mixin(require('underscore.string'));

function time() {
  return (new Date()).getTime();
}
function throttledAsync(cb, delay) {
  var timeout
    , fire = false
    , lastfire = false
    , inflight = false;
  return function() {
    if (!timeout) {
      var nextDelay = delay - (time() - lastfire);
      function callIt() {
        lastfire = time();
        inflight = true;
        cb(function() {
          inflight = false;
          if (fire) {
            fire = false;
            callIt();
          }
        });
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

var initted = false;
var changed = [];
var removed = [];

function gutUp(done) {
  if (initted) {
    var _changed = changed;
    var _removed = removed;
    changed = [];
    removed = [];
    function add() {
      if (_changed.length) {
        exec('gut', ['add'].concat(_changed), { cwd: './', pipe: true }, function(err) {
          remove();
        });
      } else {
        remove();
      }
    }
    function remove() {
      if (_removed.length) {
        exec('gut', ['rm', '--cached'].concat(_removed), { cwd: './', pipe: true }, function(err) {
          commit();
        });
      } else {
        commit();
      }
    }
    function commit() {
      exec('gut', ['commit', '-m', 'autocommit'], { cwd: './', pipe: true }, function(err) {
        done();
      });
    }
    add();
  } else {
    initted = true;
    exec('gut', ['init'], { cwd: './', pipe: true }, function(err) {
      exec('gut', ['add', '.'], { cwd: './', pipe: true }, function(err) {
        exec('gut', ['commit', '-a', '-m', 'post-walk commit'], { cwd: './', pipe: true }, function(err) {
          done();
        });
      });
    });
  }
}

var onChange = throttledAsync(gutUp, 1000);

watch.watchTree('./', function (f, curr, prev) {
  if (typeof f == "object" && prev === null && curr === null) {
    onChange();
  } else {
    if (!_.startsWith(f, '.gut/')) {
      if (prev === null) {
        changed.push(f);
        console.log('  added ' + f);
      } else if (curr.nlink === 0) {
        removed.push(f);
        console.log('removed ' + f);
        // f was removed
      } else {
        changed.push(f);
        console.log('changed ' + f);
        // f was changed
      }
      onChange();
    }
  }
});
