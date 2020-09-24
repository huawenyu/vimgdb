import sys
import os

from libtmux.pane import Pane
from libtmux.server import Server
from libtmux.window import Window

from vimgdb.base.common import Common
from vimgdb.base.data import *
from vimgdb.base.controller import Controller, GdbMode
from vimgdb.model.model import Model
from vimgdb.model.state import State
from vimgdb.model.pattern import Pattern
from vimgdb.model.breakpoint import Store


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
                        State.pat_gdb_local_start,
                        State.pat_gdb_local_start2,
                        ],
                    hint = 'start shell',
                    actionCb = self.on_open,
                    nextState = GdbState.START,),
                ]


    def on_open(self, line):
        self.logger.info("Reading bin Done!")
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
                    nextState = GdbState.SAME,
                    ),
                Pattern(rePatts = [
                    State.pat_parsebreakpoint,
                    ],
                    hint = 'ParseGdbBreakFile',
                    actionCb = self.on_parsebreak,
                    nextState = GdbState.SAME,
                    ),
                Pattern(rePatts = [
                    State.pat_continue,
                    ],
                    hint = 'Continue',
                    actionCb = self.on_running,
                    nextState = GdbState.RUN,
                    ),
                ]

        self._cmds = {
                "next":     self.cmd_next,
                "step":     self.cmd_step,
                "continue": self.cmd_continue,
                "finish":   self.cmd_finish,
                "skip":     self.cmd_skip,
                "print":    self.cmd_print,
                "whatis":   self.cmd_whatis,
                "runto":    self.cmd_runto,
                "break":    self.cmd_break,
                "up":       self.cmd_frameup,
                "down":     self.cmd_framedown,
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
        self.logger.debug(self.vimqf_backtrace)
        btrace = self.vimqf_backtrace
        self._ctx.vimgdb._wrap_async(
                self._ctx.vimgdb.vim.eval)(
                        "VimGdbUpViewBtrace('" + btrace + "')")


    def on_jump(self, line):
        jumpfile = self._rematch.group(1)
        jumpline = self._rematch.group(2)
        self.logger.info("%s:%s", jumpfile, jumpline)
        if Common.check_content(Common.vimqf_backtrace):
            self._ctx.handle_shows(DataEvent("viewUpdateBt"))
        self._ctx.handle_evts(DataEvtCursor("evtGdbOnJump", jumpfile, jumpline))

    def on_parsebreak(self, line):
        self.logger.info("Prepare parse breakpoint file")
        self._ctx.handle_evts(DataEvent("evtRefreshBreakpt"))


    def on_running(self, line):
        self.logger.info("Should clear context")
        # Cause the cursor not sign
        self._ctx._wrap_async(self._ctx.vim.call)('sign_unplace', f'{Common.vimsign_group_cursor}')

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
        self._model.sendkeys("p " + args[1])

    def cmd_whatis(self, args):
        self._model.sendkeys("whatis " + args[1])

    def cmd_frameup(self, args):
        self._model.sendkeys("up")

    def cmd_framedown(self, args):
        self._model.sendkeys("down")

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



class GdbStateRunning(State):

    def __repr__(self):
        from pprint import pformat
        return pformat(vars(self), indent=4, width=1)


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
                    nextState = GdbState.START,
                    ),
                ]


    def on_jump(self, line):
        jumpfile = self._rematch.group(1)
        jumpline = self._rematch.group(2)
        self.logger.info("%s:%s", jumpfile, jumpline)
        if Common.check_content(Common.vimqf_backtrace):
            self._ctx.handle_shows(DataEvent("viewUpdateBt"))
        self._ctx.handle_evts(DataEvtCursor("evtGdbOnJump", jumpfile, jumpline))


    def handle_cmd(self, cmd):
        self.logger.info("handle_cmd: {%s}", cmd)



class Gdb(Model):

    def __init__(self, common: Common, ctx: Controller, win: Window, pane: Pane, debug_bin: str, outfile: str):
        super().__init__(common, type(self).__name__, outfile)

        # Cache all state, no need create it everytime
        self._StateColl = {
                GdbState.INIT:      GdbStateInit(common, GdbState.INIT, self, ctx),
                GdbState.START:     GdbStateStart(common, GdbState.START, self, ctx),
                GdbState.RUN:       GdbStateRunning(common, GdbState.RUN, self, ctx),
                GdbState.TARGET:    GdbStateStart(common, GdbState.TARGET, self, ctx),
                GdbState.CONN_SUCC: GdbStateStart(common, GdbState.CONN_SUCC, self, ctx),
                GdbState.PAUSE:     GdbStateStart(common, GdbState.PAUSE, self, ctx),
                }

        self._evts.update({
                "evtGdbOnOpen":         self.evt_GdbOnOpen,
                "evtGdbserverOnListen": self.evt_GdbserverOnListen,
                })

        self._cmds2 = {
                "notify":     self.cmd_notify,
                }
        self._cmds.update(self._cmds2)

        self._acts2 = { }
        self._acts.update(self._acts2)

        assert isinstance(win, Window)
        assert isinstance(pane, Pane)
        self._win = win
        self._pane = pane

        self._ctx = ctx
        self._debug_bin = debug_bin
        self._outfile = outfile
        self._scriptdir = os.path.dirname(os.path.abspath(__file__))

        #os.system('touch ' + self._outfile)
        #os.system('truncate -s 0 ' + self._outfile)

        ##           echo \"PS1='newRuntime $ '\" >> /tmp/tmp.bashrc;
        ##           echo \"+o emacs\" >> /tmp/tmp.bashrc;
        ##           echo \"+o vi\" >> /tmp/tmp.bashrc;
        ##           bash --noediting --rcfile /tmp/tmp.bashrc
        ##self._gdb_bash = """cat ~/.bashrc > /tmp/vimgdb.bashrc;
        ##           echo \"PS1='newRuntime $ '\" >> /tmp/vimgdb.bashrc;
        ##           bash --rcfile /tmp/vimgdb.bashrc
        ##          """
        #self._gdb_bash = ""
        #self._cmd_gdb = "gdb --command " + self._scriptdir + "/../config/gdbinit -q -f --args " + self._debug_bin + " | tee -a " + self._outfile

        #self._pane = self._win.split_window(attach=True, start_directory=self._ctx.workdir, )
        #assert isinstance(self._pane, Pane)
        #if self._gdb_bash:
        #    self._pane.send_keys(self._gdb_bash, suppress_history=True)
        #self._pane.send_keys(self._cmd_gdb, suppress_history=True)

        self.run_parser(GdbState.INIT)


    @staticmethod
    def get_cmdstr(scriptDir: str, debugBin: str):
        os.system('touch ' + Common.gdb_output)
        os.system('truncate -s 0 ' + Common.gdb_output)
        return "gdb --command " + scriptDir + "/../config/gdbinit -q -f --args " + debugBin + " |& tee -ia " + Common.gdb_output


    def handle_evt(self, data: BaseData):
        if data._name in self._evts:
            self.logger.info(f"{data._name}()")
            self._evts[data._name](data)
        elif self._state:
            self.logger.info(f"State '{self._state._name}' Ignore {data._name}")
        else:
            self.logger.info(f"State is Null, Ignore {data._name}")


    def handle_cmd(self, cmdname, args):
        self.logger.info(f"{cmdname}(args={args})")
        if self._state and cmdname in self._state._cmds:
            self._state._cmds[cmdname](args)
        elif cmdname in self._cmds2:
            self._cmds2[cmdname](args)
        elif self._state:
            self.logger.info(f"State '{self._state._name}' Ignore ...")
        else:
            self.logger.info(f"State is Null, Ignore ...")


    def handle_act(self, data: BaseData):
        if self._state and data._name in self._state._acts:
            self.logger.info(f"{data._name}()")
            self._state._acts[data._name](data)
        elif data._name in self._acts2:
            self._acts2[data._name](data)
        elif self._state:
            self.logger.info(f"State '{self._state._name}' Ignore {data._name}")
        else:
            self.logger.info(f"State is Null, Ignore {data._name}")


    def sendkeys(self, cmd: str):
        self._pane.send_keys(cmd, suppress_history=True)


    def cmd_notify(self, args):
        self.logger.info(f"{args}")
        if args[1] == 'breakdone':
            if self._ctx.gdbMode == GdbMode.LOCAL:
                # local auto run
                self._pane.send_keys("run", suppress_history=True)


    def evt_GdbOnOpen(self, data: BaseData):
        bp_id = 0
        bpsDict = Store.LoadBreakpionts(self)
        if bpsDict:
            #self.logger.info(f"{data._name}: {bpsDict}")
            # Reload breakpoints: bind by id
            for cmdstr in bpsDict.keys():
                vimCmdstr = f"VimGdbNewBreak({bp_id+1}, '{cmdstr}')"
                self.logger.debug(f"{vimCmdstr}")
                bp_id += 1
                self._ctx._wrap_async(self._ctx.vim.eval)(vimCmdstr)
        else:
            self.logger.info("No saved breakponts!")

        if bp_id > 0:
            vimCmdstr = f"VimGdbFakeCmd('notify', 'breakdone', {bp_id})"
            self.logger.debug(f"{vimCmdstr}")
            self._ctx._wrap_async(self._ctx.vim.eval)(vimCmdstr)
        elif self._ctx.gdbMode == GdbMode.LOCAL:
            self._ctx._wrap_async(self._ctx.vim.eval)(f"VimGdbNewBreak(1, 'main')")
            self._ctx._wrap_async(self._ctx.vim.eval)(f"VimGdbFakeCmd('notify', 'breakdone', 1)")

        if self._ctx.gdbMode == GdbMode.REMOTE:
            self._ctx.handle_evts(DataEvent("evtGdbIsReady"))


    def evt_GdbserverOnListen(self, data: BaseData):
        assert isinstance(data, DataEvtParam1)
        self.logger.info(f"Connect to {data.param1}")
        if self._ctx.gdbMode == GdbMode.REMOTE:
            self._pane.send_keys(f"target remote dut:{data.param1}", suppress_history=True)


