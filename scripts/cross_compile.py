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

systems = ['darwin', 'linux', 'freebsd']
archs = ['386', 'amd64']
targets = list(itertools.product(systems, archs))

print 'Building gut for these targets: ' + ', '.join(['%s-%s' % target for target in targets])

if not bootstrap:
    print 'Skipping bootstrap of Go cross-compilation. Use BOOTSTRAP=1 to enable.'

cmd('rm -f gut', cwd=go_src_path)
for system, arch in targets:
    if bootstrap:
        print 'Bootstrapping Go for cross-compilation to %s-%s' % (system, arch)
        cmd('GOOS=%s GOARCH=%s ./make.bash' % (system, arch), cwd=go_src_path)
    gut_version_str = 'gut-%s-%s-%s' % (gut_version, system, arch)
    print 'Building %s' % (gut_version_str,)
    cmd('GOOS=%s GOARCH=%s go build' % (system, arch), cwd=gut_src_path)
    cmd('gzip gut', cwd=gut_src_path)
    cmd('mv gut.gz "%s/%s.gz"' % (dest_path, gut_version_str))

curlbash_src_path = os.path.join(gut_src_path, "scripts/curlbash.base.sh")
curlbash_dest_path = os.path.join(dest_path, "gut-%s.sh" % (gut_version,))

print 'Writing %s ...' % (curlbash_dest_path,)

proc = subprocess.Popen('shasum -a256 gut-%s-*.gz' % (gut_version,), stdout=subprocess.PIPE, cwd=dest_path, shell=True)
shasums, _ = proc.communicate()

with open(curlbash_src_path, 'r') as f:
    curlbash = f.read()
    curlbash = curlbash.replace('__GUTVERSION__', gut_version)
    curlbash = curlbash.replace('__CHECKSUMS__', shasums.strip())
    with open(curlbash_dest_path, 'w') as f:
        f.write(curlbash)
        print '================================='
        print curlbash
        print '================================='

proc = subprocess.Popen('shasum -a256 %s' % (curlbash_dest_path,), stdout=subprocess.PIPE, cwd=dest_path, shell=True)
_curlbash_shasum, _ = proc.communicate()
curlbash_shasum = _curlbash_shasum.split(' ')[0]
print 'New curlbash script:'
print
print 'bash -c \'S="' + curlbash_shasum + '";T="/tmp/gut.sh";set -e;wget -qO- "https://www.tillberg.us/c/$S/gut-' + gut_version + '.sh">$T; echo "$S  $T"|shasum -a256 -c-;bash $T;rm $T\''
print
