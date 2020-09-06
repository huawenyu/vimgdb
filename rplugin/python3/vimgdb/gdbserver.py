from os.path import dirname, relpath
import sys
import time

from vimgdb.common import Common

from vimgdb.context import Context
from vimgdb.state import State
from vimgdb.pattern import Pattern

thisModule = sys.modules[__name__]
thisModule._name = "Gdbserver"
thisModule.common = None
thisModule.context = None

class GdbState:
    INIT      = 'init'
    START     = 'start'
    TARGET    = 'target'
    CONN_SUCC = 'conn_succ'
    PAUSE     = 'pause'
    RUN       = 'run'
    SAME      = ''

class GdbStateInit(State):

    def __repr__(self):
        from pprint import pformat
        return pformat(vars(self), indent=4, width=1)

    def __init__(self):
        global thisModule
        super().__init__(thisModule.common,
                thisModule.context,
                GdbState.INIT)

        self._patts = [
                Pattern(rePatts = [
                        State.pat_shell_prompt,
                        State.pat_gdb_prompt1,
                        State.pat_gdb_prompt2,
                        ],
                    hint = 'start shell',
                    actionCb = self.on_open,
                    nextState = GdbState.START,),
                ]

    def on_open(self, line):
        self.logger.info("run to main")
        self._context.vimgdb.tmux_pane_gdb.send_keys("br main", suppress_history=True)
        self._context.vimgdb.tmux_pane_gdb.send_keys("run", suppress_history=True)

    def handle_cmd(self, cmd):
        self.logger.info("handle_cmd: {%s}", cmd)

class GdbStateStart(State):

    def __init__(self):
        global thisModule
        super().__init__(thisModule.common,
                thisModule.context,
                GdbState.START)

        self._patts = [
                Pattern(rePatts = [
                        State.pat_jumpfile,
                        State.pat_jumpfile2,
                        State.pat_jumpfile3,
                        ],
                    hint = 'Jumpfile',
                    actionCb = self.on_jump,
                    nextState = GdbState.SAME,),
                ]
        self._cmds = {
                "next": self.cmd_next,
                "step": self.cmd_step,
                "continue": self.cmd_continue,
                "finish": self.cmd_finish,
                "skip": self.cmd_skip,
                "print": self.cmd_print,
                }

    def on_jump(self, line):
        jumpfile = '/' + self._rematch.group(1)
        jumpline = self._rematch.group(2)
        self.logger.info("%s:%s", jumpfile, jumpline)
        #self._context.vimgdb.vim.command("e " + jumpfile  + ":" + jumpline)
        #self._context.vimgdb.vim.asyn_call("VimGdbJump", jumpfile, jumpline)

        #self._context.vimgdb.vim.funcs.VimGdbJump(jumpfile, jumpline)
        #self._context.vimgdb._wrap_async(
        #        self._context.vimgdb.vim.funcs.VimGdbJump)(
        #                jumpfile, jumpline)
        self._context.vimgdb._wrap_async(
                self._context.vimgdb.vim.eval)(
                        "VimGdbJump('" + jumpfile + "', " + jumpline + ")")

    def cmd_next(self, line):
        self._context.vimgdb.tmux_pane_gdb.send_keys("n", suppress_history=True)

    def cmd_step(self, line):
        self._context.vimgdb.tmux_pane_gdb.send_keys("s", suppress_history=True)

    def cmd_continue(self, line):
        self._context.vimgdb.tmux_pane_gdb.send_keys("c", suppress_history=True)

    def cmd_finish(self, line):
        self._context.vimgdb.tmux_pane_gdb.send_keys("finish", suppress_history=True)

    def cmd_skip(self, line):
        self._context.vimgdb.tmux_pane_gdb.send_keys("skip", suppress_history=True)

    def cmd_print(self, line):
        self._context.vimgdb.tmux_pane_gdb.send_keys("print", suppress_history=True)


class GdbServer(Context):
    def __init__(self, vimgdb, outfile):
        global thisModule
        thisModule.context = self
        thisModule.common = vimgdb

        super().__init__(vimgdb)
        self.vimgdb = vimgdb
        self._name = "Gdbserver"
        self._outfile = outfile

        # Cache all state, no need create it everytime
        self._StateColl = {
                GdbState.INIT:      GdbStateInit(),
                GdbState.START:     GdbStateStart(),
                GdbState.TARGET:    GdbStateStart(),
                GdbState.CONN_SUCC: GdbStateStart(),
                GdbState.PAUSE:     GdbStateStart(),
                GdbState.RUN:       GdbStateStart(),
                }
        self.trans_to(GdbState.INIT)
