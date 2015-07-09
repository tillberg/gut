def patch():
    import plumbum
    from plumbum.commands import shquote
    from plumbum.path.remote import StatRes
    def _path_getuid(self, fn):
        stat_cmd = "stat -c '%u,%U' " if self.uname != 'Darwin' else "stat -f '%u,%Su' "
        return self._session.run(stat_cmd + shquote(fn))[1].strip().split(",")
    def _path_getgid(self, fn):
        stat_cmd = "stat -c '%g,%G' " if self.uname != 'Darwin' else "stat -f '%g,%Sg' "
        return self._session.run(stat_cmd + shquote(fn))[1].strip().split(",")
    def _path_stat(self, fn):
        if self.uname != 'Darwin':
            stat_cmd = "stat -c '%F,%f,%i,%d,%h,%u,%g,%s,%X,%Y,%Z' "
        else:
            stat_cmd = "stat -f '%HT,%Xp,%i,%d,%l,%u,%g,%z,%a,%m,%c' "
        rc, out, _ = self._session.run(stat_cmd + shquote(fn), retcode = None)
        if rc != 0:
            return None
        statres = out.strip().split(",")
        text_mode = statres.pop(0).lower()
        res = StatRes((int(statres[0], 16),) + tuple(int(sr) for sr in statres[1:]))
        res.text_mode = text_mode
        return res
    def _path_link(self, src, dst, symlink):
        self._session.run("ln %s %s %s" % ("-s" if symlink else "", shquote(src), shquote(dst)))
    plumbum.machines.remote.BaseRemoteMachine._path_getuid = _path_getuid
    plumbum.machines.remote.BaseRemoteMachine._path_getgid = _path_getgid
    plumbum.machines.remote.BaseRemoteMachine._path_stat = _path_stat
    plumbum.machines.remote.BaseRemoteMachine._path_link = _path_link
