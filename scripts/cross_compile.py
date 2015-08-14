#!/usr/bin/env python

import itertools
import os
import subprocess

dest_path = os.environ['DEST']
go_src_path = os.path.join(os.environ['GOROOT'], 'src')
gut_src_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..')
bootstrap = os.environ.get('BOOTSTRAP', False)

def cmd(s, cwd=None):
    status = subprocess.call(s, shell=True, cwd=cwd)
    if status != 0:
        raise Exception('"%s" exited with status %s' % (s, status))

proc = subprocess.Popen(['git', 'describe', '--tags'], stdout=subprocess.PIPE, cwd=gut_src_path)
out, _ = proc.communicate()
gut_version = out and out.strip()
if not gut_version:
    raise Exception('Could not read gut version from "git describe --tags"')

oses = ['darwin', 'linux', 'freebsd']
archs = ['386', 'amd64']
targets = list(itertools.product(oses, archs))

print 'Building gut for these targets: ' + ', '.join(['%s-%s' % target for target in targets])

if not bootstrap:
    print 'Skipping bootstrap of Go cross-compilation. Use BOOTSTRAP=1 to enable.'

cmd('rm -f gut', cwd=go_src_path)
for os, arch in targets:
    if bootstrap:
        print 'Bootstrapping Go for cross-compilation to %s-%s' % (os, arch)
        cmd('GOOS=%s GOARCH=%s ./make.bash' % (os, arch), cwd=go_src_path)
    gut_version_str = 'gut-%s-%s-%s' % (gut_version, os, arch)
    print 'Building %s' % (gut_version_str,)
    cmd('GOOS=%s GOARCH=%s go build' % (os, arch), cwd=gut_src_path)
    cmd('gzip gut', cwd=gut_src_path)
    cmd('mv gut.gz "%s/%s.gz"' % (dest_path, gut_version_str))

print '============'
cmd('shasum -a256 gut-%s*' % (gut_version,), cwd=dest_path)
