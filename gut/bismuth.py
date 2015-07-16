import asyncio
import os
import shlex

import asyncssh

from .terminal import Writer, shutdown

class Channel:
    def __init__(self):
        self.queue = asyncio.Queue()

    def write(self, data):
        self.queue.put_nowait(data)

    @asyncio.coroutine
    def read(self):
        return (yield from self.queue.get())

class MySSHClientSession(asyncssh.SSHClientSession):
    def __init__(self):
        self.stdout = Channel()
        self.stderr = Channel()
        self.exit_queue = asyncio.Queue(1)
        self.channel = None

    def set_channel(self, channel):
        self.channel = channel

    def data_received(self, data, datatype):
        # print('data_received: [%r], datatype: [%r]' % (data, datatype))
        if datatype == asyncssh.EXTENDED_DATA_STDERR:
            self.stderr.write(data)
        else:
            self.stdout.write(data)

    def eof_received(self):
        # print('eof_received')
        self.stdout.write(None)
        self.stderr.write(None)

    # This doesn't always get called. Maybe a race condition in asyncssh?
    # def exit_status_received(self, status):
    #     # print('Got exit status %r' % (status,))
    #     self.exit_queue.put_nowait(status)

    # def exit_signal_received(signal, core_dumped, msg, lang):
    #     print('exit_signal_received %r %r %r %r' % (signal, core_dumped, msg, lang))

    # @asyncio.coroutine
    # def wait_for_exit(self):
    #     yield from self.exit_queue.get()

    @asyncio.coroutine
    def wait_for_close(self):
        yield from self.channel.wait_closed()

    def connection_lost(self, exc):
        if exc:
            print('SSH session error: ' + str(exc), file=sys.stderr)

FD_STDOUT = 1
FD_STDERR = 2
class LocalSessionReaderProtocol(asyncio.SubprocessProtocol):
    def __init__(self, session):
        self.session = session
        asyncio.SubprocessProtocol.__init__(self)

    def pipe_data_received(self, fd, data):
        # log.out('got %r from %r\n' % (data, fd))
        if fd == FD_STDOUT:
            self.session.stdout.write(data)
        elif fd == FD_STDERR:
            self.session.stderr.write(data)
        asyncio.SubprocessProtocol.pipe_data_received(self, fd, data)

    def pipe_connection_lost(self, fd, exc):
        self.pipe_data_received(fd, None)
        if exc:
            log.out('pipe_connection_lost %r %r\n' % (fd, exc))
        asyncio.SubprocessProtocol.pipe_connection_lost(self, fd, exc)

    def process_exited(self):
        # log.out('process exited\n')
        self.session.exit_queue.put_nowait(None)
        asyncio.SubprocessProtocol.process_exited(self)

class LocalSession:
    def __init__(self):
        self.stdout = Channel()
        self.stderr = Channel()
        self.exit_queue = asyncio.Queue(1)

    @asyncio.coroutine
    def start(self, cmd):
        loop = asyncio.get_event_loop()
        self._transport, _ = yield from loop.subprocess_shell(lambda: LocalSessionReaderProtocol(self), cmd, stdin=None)
        # stdout_reader = LocalSessionReaderProtocol(self.stdout)
        # yield from loop.connect_read_pipe(lambda: stdout_reader, self.proc.stdout)
        # stderr_reader = LocalSessionReaderProtocol(self.stderr)
        # yield from loop.connect_read_pipe(lambda: stderr_reader, self.proc.stderr)

    @asyncio.coroutine
    def wait_for_close(self):
        yield from self.exit_queue.get()
        self._transport.close()

class MySSHClient(asyncssh.SSHClient):
    def connection_made(self, conn):
        # print('Connection made to %s.' % conn.get_extra_info('peername')[0])
        pass

    def auth_completed(self):
        # print('Authentication successful.')
        pass

class Context:
    def __init__(self, path=None, host=None, user=None, keyfile=None):
        self.host = host
        self.user = user
        self.path = path
        self.keyfile = keyfile
        self._conn = None
        self._client = None
        self._name = host or 'localhost'
        self._name_ansi = '(@host)%s(@r)' % (self._name,)
        self._cache = {}

    @asyncio.coroutine
    def make_session(self, cmd):
        if self.host:
            if not self._conn:
                self._conn, self._client = yield from asyncssh.create_connection(MySSHClient, self.host, username=self.user)
            chan, session = yield from self._conn.create_session(MySSHClientSession, cmd)
            session.set_channel(chan)
        else:
            session = LocalSession()
            yield from session.start(cmd)
        return session

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
            self._client = None

    def __str__(self):
        return '<Context %s>' % (self._name,)

    @asyncio.coroutine
    def get_cached(self, args):
        if args not in self._cache:
            self._cache[args] = yield from self.call(args)
        return self._cache[args]

    @asyncio.coroutine
    def home(self):
        return (yield from self.get_cached('echo $HOME'))

    @asyncio.coroutine
    def uname(self):
        return (yield from self.get_cached(('uname',)))

    @asyncio.coroutine
    def abspath(self, path):
        if not path.startswith('/'):
            relpath = path[2:] if path.startswith('~/') else path
            path = os.path.join((yield from self.home()), relpath)
        return os.path.normpath(path)

    @asyncio.coroutine
    def __call__(self, args):
        return (yield from self.call(args))

    @asyncio.coroutine
    def call(self, args):
        _, out, _ = yield from self.run(args)
        return out.strip()

    @asyncio.coroutine
    def run(self, args):
        return (yield from self.quote(args, quiet_out=True, quiet_err=True))

    @asyncio.coroutine
    def quote(self, args, quiet_out=False, quiet_err=False):
        if isinstance(args, str):
            cmd = args
            arg0 = args.split(' ', 2)[0]
        else:
            cmd = ' '.join((shlex.quote(arg) for arg in args))
            arg0 = args[0]
        session = yield from self.make_session(cmd)
        name = os.path.basename(arg0)
        writer_stdout = Writer(self, '(@dim)%s-out' % (name,), muted=quiet_out)
        writer_stderr = Writer(self, '(@dim)%s-err' % (name,), muted=quiet_err)
        future_error = writer_stderr.quote_channel(session.stderr)
        # log.out('reading stdout\n')
        yield from writer_stdout.quote_channel(session.stdout)
        yield from future_error
        # log.out('waiting for chan close\n')
        yield from session.wait_for_close()
        # log.out('waiting for exit\n')
        exit_status = None
        # exit_status = yield from session.wait_for_exit()
        # log.out('done with %s\n' % (name,))
        return (exit_status, writer_stdout.output, writer_stderr.output)

@asyncio.coroutine
def test():
    log = Writer(None)
    log.out('Starting bismuth tests.\n')
    local = Context()
    hostname = yield from local('hostname')
    log.out('Using %r as the remote hostname.\n' % (hostname,))
    remote = Context(host=hostname)
    for context in [local, remote]:
        res = Writer(context)
        res.out('Trying %s\n' % (context,))
        yield from context.quote(['pwd'])
        # yield from context.quote(['find', '/tmp'])
        _, out, err = yield from context.run(['find', '/tmp'])
        res.out('Got %s and %s characters from find\n' % (len(out), len(err)))
        res.out('find stderr: %r\n' % (err,))
        res.out('HELLO = %r\n' % ((yield from context(['echo', 'HELLO'])),))
        res.out('my tmp: %r\n' % ((yield from context.abspath('~/tmp')),))
        res.out('my tmp: %r\n' % ((yield from context.abspath('./tmp')),))
        res.out('my tmp: %r\n' % ((yield from context.abspath('tmp')),))
        res.out('global tmp: %r\n' % ((yield from context.abspath('/tmp')),))
        yield from context.quote('echo "This is stdout"; sleep 0.5; >&2 echo "This is stderr"')
        res.out('uname = %r\n' % ((yield from context.uname())))
        context.close()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
    shutdown(exit=False)
