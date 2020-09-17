import re

from abc import ABC, abstractmethod
from vimgdb.base.common import Common
from vimgdb.base.controller import Controller


class State(Common, ABC):
    #pattern = re.compile(r"cookie")
    #sequence = "Cake and cookie"
    #pattern.search(sequence).group()

    # gdb {{{2
    pat_any                 = ("any", re.compile(r"(.*)"))
    pat_dummy               = ("dummy", re.compile(r"^dummy "))
    pat_gdb_leave           = ("leave", re.compile(r'^neobugger_leave'))
    pat_gdb_local_start     = ("localStart", re.compile(r'^neobugger_local_start'))

    pat_prompt              = ("prompt", re.compile(r'\x1a\x1a\x1a$'))
    pat_shell_prompt        = ("shellPrompt", re.compile(r"^newRuntime "))

    pat_gdb_prompt1         = ("gdbPrompt1", re.compile(r"^\(gdb\) "))
    pat_gdb_prompt2         = ("gdbPrompt2", re.compile(r"^\(Pdb\) "))


    # >>> br main
    # Breakpoint 1 at 0x40114a: file t1.c, line 11.
    # Breakpoint 1, main () at t1.c:11
    # Starting program: /home/test/tmp/t1/t1

    pat_continue            = ("continue", re.compile(r'^Continuing\.'))
    pat_breakpoint          = ("break", re.compile(r'^Breakpoint \d+'))
    pat_tempbreakpoint      = ("tempbreak", re.compile(r'^Temporary breakpoint \d+'))
    pat_parsebreakpoint     = ("parsebreak", re.compile(r'^neobugger_setbreakpoint'))


    pat_inner_err           = ("innerErr", re.compile(r"\[Inferior\ +.{-}\ +exited\ +normally"))

    pat_remote_err          = ("remoteErr", re.compile(r'^Remote communication error\.  Target disconnected\.:'))
    pat_remote_close        = ("remoteClose", re.compile(r'^Remote connection closed\.'))

    pat_no_prog_run         = ("noProgRun", re.compile(r'^The program is not being run\.'))

    # "127.0.0.1:9999: Connection refused.",
    # "dut:9999: Connection refused.",
    pat_remote_con_fail     = ("remoteConFail1", re.compile(r'^\d+\.\d+\.\d+\.\d+:\d+: Connection refused\.'))
    pat_remote_con_fail2    = ("remoteConFail2", re.compile(r'^\w+:\d+: Connection refused\.'))



    # file {{{2
    # '[\o32]{2}([^:]+):(\d+):\d+',
    # '/([\h\d/]+):(\d+):\d+',
    # '^#\d+ .{-} \(\) at (.+):(\d+)',
    # ' at /([\h\d/]+):(\d+)',
    # '^\> ([\/\-\_\.a-zA-Z0-9]+)\((\d+)\)',

    # "/home/user/tmp/t1.c:35:414:beg:0x4011c1",
    # group(1), group(3)
    pat_jumpfile            = ("jump1", re.compile(r'^(\/([\/\wd-z\.-]*)*\/?)?:([\d]+)?'))
    # \x1A is CTRL+Z controller character. It is also EOF marker.
    pat_jumpfile2           = ("jump2", re.compile(r'^\x1a\x1a([^:]+):(\d+):\d+'))
    # "> /home/user/tmp/client1.py(1)<module>()",
    pat_jumpfile3           = ("jump3", re.compile(r'^> /([\w\d\._/]+):\((\d+)\)'))


    # helper {{{2
    # "$3 = (int *) 0x7fffffffd93c",
    pat_print               = ("print", re.compile(r'^\$\d+ .* 0x(.*)'))
    #pat_whatis              = ("whatis", re.compile(r'^type \= (\p+)'))


    # gdbserver {{{2
    pat_server_listen       = ("listen", re.compile(r'^Listening on port (\d+)'))
    pat_server_detach       = ("detach", re.compile(r'^Detaching from process \d+'))
    pat_server_remote_from  = ("remoteFrom", re.compile(r'^Remote debugging from host \d+\.\d+\.\d+\.\d+:\d+'))

    # "127.0.0.1:444: Connection timed out.",
    # "dut:444: Connection timed out.",
    pat_remote_con_timeout  = ("remoteConTimeout", re.compile(r'^\d+\.\d+\.\d+\.\d+:\d+:\d+: Connection timed out\.'))
    pat_remote_con_timeout2 = ("remoteConTimeout2", re.compile(r'^\w+:\d+: Connection timed out\.'))

    pat_remote_con_succ     = ("remoteConSucc", re.compile(r"^Remote debugging using \d+\.\d+\.\d+\.\d+:\d+"))
    pat_remote_con_succ2    = ("remoteConSucc2", re.compile(r'^Remote debugging using \w+:\d+'))


    def __init__(self, common: Common, name: str, model, ctx: Controller):
        Common.__init__(self, common)
        self._name = name
        self._model = model
        self._ctx = ctx
        self._patts = []
        self._rematch = None
        self._cmds = {}

    def on_dummy(self):
        pass


    def handle_line(self, line):
        handled = False
        o_state = self._name
        for onePatt in self._patts:
            for patt in onePatt.rePatts:
                pattName = patt[0]
                pattRe = patt[1]
                self._rematch = pattRe.match(line)
                if self._rematch:
                    handled = True
                    self.logger.info("matched '%s' as: {%s}",
                            self._model._state._name,
                            pattName,
                            self._rematch.groups())
                    onePatt.actionCb(line)
                    if len(onePatt.nextState) > 0:
                        self._model.trans_to(onePatt.nextState)
                    self.logger.info("State '%s' -> '%s': %s",
                            o_state,
                            self._model._state._name,
                            onePatt.hint)
                    #if onePatt.update_model:
                    #    self.update_model()
                    break
            if handled:
                break

        if not handled:
            res = State.pat_any[1].match(line)
            if res:
                self.logger.info("ignore groups: %s",
                        self._model._state._name,
                        res.groups())
            else:
                self.logger.info("ignore it.",
                        self._model._state._name)
        return

