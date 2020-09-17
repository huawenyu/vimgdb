import sys
import os

from libtmux.pane import Pane
from libtmux.server import Server
from libtmux.window import Window

from vimgdb.base.common import Common
from vimgdb.base.controller import Controller
from vimgdb.base.data import *

from vimgdb.model.model import Model
from vimgdb.model.state import State
from vimgdb.model.pattern import Pattern

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
                Pattern(rePatts = [
                        State.pat_parsebreakpoint,
                        ],
                    hint = 'ParseBreakpoint',
                    actionCb = self.on_parsebreak,
                    nextState = GdbState.SAME,),
                ]

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

    def on_parsebreak(self, line):
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


class GdbServer(Model):
    def __init__(self, common: Common, ctx: Controller, win: Window, debug_bin: str, outfile: str):
        super().__init__(common, type(self).__name__, outfile)

        # Cache all state, no need create it everytime
        self._StateColl = {
                GdbState.INIT:      GdbStateInit(),
                GdbState.START:     GdbStateStart(),
                GdbState.TARGET:    GdbStateStart(),
                GdbState.CONN_SUCC: GdbStateStart(),
                GdbState.PAUSE:     GdbStateStart(),
                GdbState.RUN:       GdbStateStart(),
                }

        self._win = win
        self._pane = win
        self._ctx = ctx
        self._debug_bin = debug_bin
        self._outfile = outfile
        self._scriptdir = os.path.dirname(os.path.abspath(__file__))

        os.system('touch ' + self._outfile)
        os.system('truncate -s 0 ' + self._outfile)

        self._cmd_gdbserver = 'dut.py -h dut -u admin -p "" -t "gdb:wad" ' + " | tee -a " + self.gdbserver_output

        self._pane = self._win.split_window(attach=True, start_directory=self._ctx.workdir, )
        assert isinstance(self._pane, Pane)
        self._pane.send_keys(self._cmd_gdbserver, suppress_history=True)

        self.run_parser(GdbState.INIT)


    def handle_evt(self, data: BaseData):
        if data._name in self._evts:
            self.logger.info(f"{data._name}()")
            self._evts[data._name](data)
        else:
            self.logger.info(f"ignore {data._name}()")


    def handle_cmd(self, cmdname, args):
        self.logger.info(f"handle_cmd: {cmdname}(args={args})")
        if self._state:
            self._state.handle_cmd(cmdname, args)
        else:
            self.logger.info(f"handle_cmd {cmdname}(args={args}) fail: state is Null")


    def handle_act(self, data: BaseData):
        self.logger.info(f"{data}")


