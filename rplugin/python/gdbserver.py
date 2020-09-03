from os.path import dirname, relpath
import sys
import logger
import time

sys.path.insert(0, dirname(__file__))

import vimgdb
from context import Context
from state import State
from pattern import Pattern

log = logger.GetLogger(__name__)

class GdbState:
    INIT      = 'init'
    START     = 'start'
    TARGET    = 'target'
    CONN_SUCC = 'conn_succ'
    PAUSE     = 'pause'
    RUN       = 'run'

class GdbServer(Context):
    def __init__(self, vim):
        self.vim = vim

        self.workdir = os.getcwd()
        self.scriptdir = os.path.dirname(os.path.abspath(__file__))
        self.file = ''
        self.gdb_output = '/tmp/vimgdb.gdb'
        self.gdbserver_output = '/tmp/vimgdb.gdbserver'
        self.debug_mode = GdbMode.LOCAL
        self.debug_bin = "t1"
