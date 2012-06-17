var http = require('http');
var util = require('util');

var watch = require('watch');
var common = require('tillberg_common');

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
    exec('gut', ['add'].concat(changed), { cwd: './', pipe: true }, function(err) {
      exec('gut', ['rm', '--cached'].concat(removed), { cwd: './', pipe: true }, function(err) {
        exec('gut', ['commit', '-a', '-m', 'autocommit'], { cwd: './', pipe: true }, function(err) {
          done();
        });
      });
    });
  } else {
    exec('gut', ['init'], { cwd: './', pipe: true }, function(err) {
      exec('gut', ['add', '.'], { cwd: './', pipe: true }, function(err) {
        exec('gut', ['commit', '-a', '-m', 'post-walk commit'], { cwd: './', pipe: true }, function(err) {
          done();
        });
      });
    });
  }
}

var onChange = throttledAsync(gutUp);

watch.watchTree('./', function (f, curr, prev) {
  if (typeof f == "object" && prev === null && curr === null) {
    onChange();
  } else if (prev === null) {
    changed.append(f);
    console.log('  added ' + f);
  } else if (curr.nlink === 0) {
    changed.append(f);
    console.log('removed ' + f);
    // f was removed
  } else {
    removed.append(f);
    console.log('changed ' + f);
    // f was changed
  }
});
