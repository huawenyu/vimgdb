import sys
import os

from libtmux.pane import Pane
from libtmux.server import Server
from libtmux.window import Window

from vimgdb.base.common import Common
from vimgdb.base.data import *
from vimgdb.base.controller import Controller
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


    def __init__(self, common: Common, name: str, model: Model, ctx: Controller):
        super().__init__(common, name, model, ctx)

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
        self.logger.info("run to main()")
        self._ctx.handle_evts(BaseData("evtGdbOnOpen"))


    def handle_cmd(self, cmd):
        self.logger.info("handle_cmd: {%s}", cmd)



class GdbStateStart(State):

    def __init__(self, common: Common, name: str, model: Model, ctx: Controller):
        super().__init__(common, name, model, ctx)

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
                    hint = 'ParseGdbBreakFile',
                    actionCb = self.on_parsebreak,
                    nextState = GdbState.SAME,),
                ]

        self._cmds = {
                "next":     self.cmd_next,
                "step":     self.cmd_step,
                "continue": self.cmd_continue,
                "finish":   self.cmd_finish,
                "skip":     self.cmd_skip,
                "print":    self.cmd_print,
                "runto":    self.cmd_runto,
                "break":    self.cmd_break,
                }
        model._cmds.update(self._cmds)

        self._acts = {
                "actAddBreak":     self.act_addbreak,
                "actEnableBreak":  self.act_enablebreak,
                "actDisableBreak": self.act_disablebreak,
                "actDeleteBreak":  self.act_deletebreak,
                }
        model._acts.update(self._acts)


    def update_view(self):
        self.logger.debug(self.gdb_bt_qf)
        btrace = self.gdb_bt_qf
        self._ctx.vimgdb._wrap_async(
                self._ctx.vimgdb.vim.eval)(
                        "VimGdbUpViewBtrace('" + btrace + "')")


    def on_jump(self, line):
        jumpfile = self._rematch.group(1)
        jumpline = self._rematch.group(2)
        self.logger.info("%s:%s", jumpfile, jumpline)
        self._ctx.handle_evts(DataEvtCursor("evtGdbOnJump", jumpfile, jumpline))

    def on_parsebreak(self, line):
        self.logger.info("Prepare parse breakpoint file")
        self._ctx.handle_evts(DataEvent("evtRefreshBreakpt"))

    def cmd_next(self, args):
        self._model.sendkeys("n")

    def cmd_step(self, args):
        self._model.sendkeys("s")

    def cmd_continue(self, args):
        self._model.sendkeys("c")

    def cmd_finish(self, args):
        self._model.sendkeys("finish")

    def cmd_skip(self, args):
        self._model.sendkeys("skip")

    def cmd_print(self, args):
        self._model.sendkeys("print")

    def cmd_runto(self, args):
        self._model.sendkeys("tbreak " + args[1])
        self._model.sendkeys("c")

    def cmd_break(self, args):
        self._model.sendkeys("break " + args[1])

    def act_addbreak(self, data: BaseData):
        assert isinstance(data, DataObjBreakpoint)
        self._model.sendkeys('br ' + data.cmdstr)

    def act_enablebreak(self, data: BaseData):
        assert isinstance(data, DataObjBreakpoint)
        self._model.sendkeys('enable ' + data.bp_id)

    def act_disablebreak(self, data: BaseData):
        assert isinstance(data, DataObjBreakpoint)
        self._model.sendkeys('disable ' + data.bp_id)

    def act_deletebreak(self, data: BaseData):
        assert isinstance(data, DataObjBreakpoint)
        self._model.sendkeys('delete ' + data.bp_id)

class Gdb(Model):

    def __init__(self, common: Common, ctx: Controller, win: Window, debug_bin: str, outfile: str):
        super().__init__(common, type(self).__name__, outfile)

        # Cache all state, no need create it everytime
        self._StateColl = {
                GdbState.INIT:      GdbStateInit(common, GdbState.INIT, self, ctx),
                GdbState.START:     GdbStateStart(common, GdbState.START, self, ctx),
                GdbState.TARGET:    GdbStateStart(common, GdbState.TARGET, self, ctx),
                GdbState.CONN_SUCC: GdbStateStart(common, GdbState.CONN_SUCC, self, ctx),
                GdbState.PAUSE:     GdbStateStart(common, GdbState.PAUSE, self, ctx),
                GdbState.RUN:       GdbStateStart(common, GdbState.RUN, self, ctx),
                }

        self._evts = {
                "evtGdbOnOpen":     self.evt_GdbOnOpen,
                }

        self._win = win
        self._pane = win
        self._ctx = ctx
        self._debug_bin = debug_bin
        self._outfile = outfile
        self._scriptdir = os.path.dirname(os.path.abspath(__file__))

        os.system('touch ' + self._outfile)
        os.system('truncate -s 0 ' + self._outfile)

        #           echo \"PS1='newRuntime $ '\" >> /tmp/tmp.bashrc;
        #           echo \"+o emacs\" >> /tmp/tmp.bashrc;
        #           echo \"+o vi\" >> /tmp/tmp.bashrc;
        #           bash --noediting --rcfile /tmp/tmp.bashrc
        #self._gdb_bash = """cat ~/.bashrc > /tmp/vimgdb.bashrc;
        #           echo \"PS1='newRuntime $ '\" >> /tmp/vimgdb.bashrc;
        #           bash --rcfile /tmp/vimgdb.bashrc
        #          """
        self._gdb_bash = ""
        self._cmd_gdb = "gdb --command " + self._scriptdir + "/../config/gdbinit -q -f --args " + self._debug_bin + " | tee -a " + self._outfile

        self._pane = self._win.split_window(attach=True, start_directory=self._ctx.workdir, )
        assert isinstance(self._pane, Pane)
        if self._gdb_bash:
            self._pane.send_keys(self._gdb_bash, suppress_history=True)
        self._pane.send_keys(self._cmd_gdb, suppress_history=True)

        self.run_parser(GdbState.INIT)


    def handle_evt(self, data: BaseData):
        if data._name in self._evts:
            self.logger.info(f"{data._name}()")
            self._evts[data._name](data)
        else:
            self.logger.info(f"ignore {data._name}()")


    def handle_act(self, data: BaseData):
        if self._state and data._name in self._state._acts:
            self.logger.info(f"{data._name}()")
            self._state._acts[data._name](data)
        else:
            self.logger.info(f"ignore {data._name}()")


    def handle_cmd(self, cmdname, args):
        self.logger.info(f"handle_cmd: {cmdname}(args={args})")
        if self._state and cmdname in self._state._cmds:
            self._state._cmds[cmdname](args)
        else:
            self.logger.info(f"handle_cmd {cmdname}(args={args}) fail: state is Null")


    def sendkeys(self, cmd: str):
        self._pane.send_keys(cmd, suppress_history=True)


    def evt_GdbOnOpen(self, data: BaseData):
        self.logger.info("null")
        self._pane.send_keys("br main", suppress_history=True)
        self._pane.send_keys("run", suppress_history=True)


