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

class GdbserverStateInit(State):

    def __repr__(self):
        from pprint import pformat
        return pformat(vars(self), indent=4, width=1)

    def __init__(self, common: Common, name: str, model: Model, ctx: Controller):
        super().__init__(common, name, model, ctx)

        self._model = model
        self._patts = [
                Pattern(rePatts = [
                        State.pat_server_listen,
                        ],
                    hint = 'Listen on',
                    actionCb = self.on_listen,
                    nextState = GdbState.START,
                    ),
                ]

        self._evts.update({
                "evtGdbIsReady":         self.evt_GdbIsReady,
                })
        model._evts.update(self._evts)


    def on_listen(self, line):
        port = self._rematch.group(1)
        self._ctx.gdbserverPort = port
        self.logger.info(f"gdbserver :{port} --attach <pid>")
        self.logger.info(f"Waiting gdb-client: target remote <host>:{port}")
        self._ctx.handle_evts(DataEvtParam1("evtGdbserverOnListen", port))

    def handle_cmd(self, cmd):
        self.logger.info("handle_cmd: {%s}", cmd)


    def evt_GdbIsReady(self, data: BaseData):
        self._model.start_gdbserver()


class GdbserverStateStart(State):

    def __init__(self, common: Common, name: str, model: Model, ctx: Controller):
        super().__init__(common, name, model, ctx)

        self._patts = [
                Pattern(rePatts = [
                        State.pat_server_remote_from,
                        ],
                    hint = 'Accept connect from gdb-client',
                    actionCb = self.on_accept,
                    nextState = GdbState.CONN_SUCC,
                    ),
                ]

    def on_accept(self, line):
        self.logger.info("{line}")
        pass


class GdbserverStateConnSucc(State):

    def __repr__(self):
        from pprint import pformat
        return pformat(vars(self), indent=4, width=1)

    def __init__(self, common: Common, name: str, model: Model, ctx: Controller):
        super().__init__(common, name, model, ctx)

        self._patts = [
                Pattern(rePatts = [
                        State.pat_remote_err,
                        State.pat_remote_close,
                        State.pat_client_exit,
                        State.pat_client_close
                        ],
                    hint = 'Connection closed',
                    actionCb = self.on_connect_close,
                    nextState = GdbState.INIT,
                    ),
                Pattern(rePatts = [
                        State.pat_server_listen,
                        ],
                    hint = 'Listen on',
                    actionCb = self.on_listen,
                    nextState = GdbState.START,
                    ),
                ]

    def on_connect_close(self, line):
        self.logger.info(f"{line}")

    def handle_cmd(self, cmd):
        self.logger.info(f"{cmd}")

    def on_listen(self, line):
        port = self._rematch.group(1)
        self._ctx.gdbserverPort = port
        self.logger.info(f"gdbserver :{port} --attach <pid>")
        self.logger.info(f"Waiting gdb-client: target remote <host>:{port}")
        self._ctx.handle_evts(DataEvtParam1("evtGdbserverOnListen", port))



class GdbServer(Model):
    def __init__(self, common: Common, ctx: Controller, win: Window, pane: Pane, debug_bin: str, outfile: str):
        super().__init__(common, type(self).__name__, outfile)

        # Cache all state, no need create it everytime
        self._StateColl = {
                GdbState.INIT:      GdbserverStateInit(common, GdbState.INIT, self, ctx),
                GdbState.START:     GdbserverStateStart(common, GdbState.START, self, ctx),
                GdbState.TARGET:    GdbserverStateStart(common, GdbState.TARGET, self, ctx),
                GdbState.CONN_SUCC: GdbserverStateConnSucc(common, GdbState.CONN_SUCC, self, ctx),
                GdbState.PAUSE:     GdbserverStateStart(common, GdbState.PAUSE, self, ctx),
                GdbState.RUN:       GdbserverStateStart(common, GdbState.RUN, self, ctx),
                }

        assert isinstance(win, Window)
        assert isinstance(pane, Pane)
        self._win = win
        self._pane = pane

        self._ctx = ctx
        self._debug_bin = debug_bin
        self._outfile = outfile
        self._scriptdir = os.path.dirname(os.path.abspath(__file__))

        self._cmd_gdbserver = 'cmdssh -d dut -u admin -p "" -t "gdb wad" ' + " | tee -a " + self.gdbserver_output

        #self._pane = self._win.split_window(attach=True, start_directory=self._ctx.workdir, )
        #assert isinstance(self._pane, Pane)

        self.run_parser(GdbState.INIT)


    @staticmethod
    def get_cmdstr(scriptDir: str, debugBin: str):
        os.system('touch ' + Common.gdbserver_output)
        os.system('truncate -s 0 ' + Common.gdbserver_output)
        return 'dut.py -h dut -u admin -p "" -t "gdb:wad" ' + " |& tee -ia " + Common.gdbserver_output


    def start_gdbserver(self):
        self._pane.send_keys(self._cmd_gdbserver, suppress_history=True)

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
        if self._state and data._name in self._state._acts:
            self.logger.info(f"{data._name}()")
            self._state._acts[data._name](data)
        else:
            self.logger.info(f"ignore {data._name}()")


