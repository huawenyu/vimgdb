from os.path import dirname, relpath
import sys
import time

sys.path.insert(0, dirname(__file__))

import vimgdb
from context import Context
from state import State
from pattern import Pattern

import logger

log = logger.GetLogger(__name__)

thisModule = sys.modules[__name__]
thisModule.context = None

#import importlib
#module = importlib.import_module(module_name)
#class_ = getattr(module, class_name)
#instance = class_()
#_module = importlib.import_module(sys.modules[__name__])  # current module

class GdbState:
    INIT      = 'init'
    START     = 'start'
    TARGET    = 'target'
    CONN_SUCC = 'conn_succ'
    PAUSE     = 'pause'
    RUN       = 'run'


class GdbStateInit(State):

    def __repr__(self):
        from pprint import pformat
        return pformat(vars(self), indent=4, width=1)

    def __init__(self):
        global thisModule

        super(GdbStateInit, self).__init__(thisModule.context, GdbState.INIT)
        self._patts = [
                Pattern(rePatt = State.pat_shell_prompt,
                    hint = 'start shell',
                    sample = '',
                    actionCb = self.on_open,
                    nextState = GdbState.START,),
                Pattern(rePatt = State.pat_gdb_prompt1,
                    hint = 'start gdb',
                    sample = '',
                    actionCb = self.on_open,
                    nextState = GdbState.START,),
                Pattern(rePatt = State.pat_gdb_prompt2,
                    hint = 'start gdb',
                    sample = '',
                    actionCb = self.on_open,
                    nextState = GdbState.START,),
                ]

    def on_open(self, aPattern):
        self._context.vim.tmux_pane_gdb.send_keys("br main", suppress_history=True)
        self._context.vim.tmux_pane_gdb.send_keys("run", suppress_history=True)

class GdbStateStart(State):

    def __init__(self):
        global thisModule

        super(GdbStateStart, self).__init__(thisModule.context, GdbState.START)

    def on_open(self):
        self._context.trans_to(GdbState.INIT)


class Gdb(Context):
    def __init__(self, vim, outfile):
        global thisModule

        thisModule.context = self
        self.vim = vim
        self._name = "Gdb"
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

