"""Common base for every class."""

import logging
import hashlib
import json


class BaseCommon:
    """Common base part of all classes."""

    def __init__(self, vim):
        """Construct to propagate context."""
        self.vim = vim
        self.logger = logging.getLogger(type(self).__name__)

    def treat_the_linter(self):
        """Let the linter be happy."""

    def treat_the_linter2(self):
        """Let the linter be happy 2."""


class Common(BaseCommon):
    """Common part of all classes with convenient constructor."""

    # debug file
    vimgdb_debugfile    = "/tmp/vimgdb.log"
    vimgdb_conffile     = "~/.vimgdb.conf"

    # So far vimgdb share the same file, means multiple-gdb may cause issue.
    md5_coll              = {}
    vimsign_break_max     = 0
    vimsign_group_breakp  = 'vimgdbBreakp'
    vimsign_group_cursor  = 'vimgdbCursor'

    tmux_vimgdb_session_name    = "__vimgdb__"
    tmux_layout_local           = "vimgdb@local"
    tmux_layout_remote          = "vimgdb@remote"
    tmux_builtin_panes          = "builtin_panes"

    tmux_pane_builtin_main      = "_builtin_main_"
    tmux_pane_builtin_gdb       = "_builtin_gdb_"
    tmux_pane_builtin_gdbserver = "_builtin_gdbserver_"

    # map output
    gdb_output            = '/tmp/vimgdb.gdb'
    gdbserver_output      = '/tmp/vimgdb.gdbserver'

    vimqf_backtrace       = '/tmp/vimgdb.bt'
    vimqf_breakpoint      = '/tmp/vimgdb.bp'
    gdb_tmp_break         = './.gdb.infobreak'
    #gdb_tmp_break         = '/tmp/vimgdb.infobreak'

    gdb_file_infolocal    = "/tmp/vimgdb.var"
    gdb_file_vimleave     = "/tmp/vimLeave"
    gdb_file_bp_fromgdb   = "./.gdb.break"
    gdb_file_bp_fromctrl  = "./.gdb.breakctrl"
    gdb_anchor_breakpoint = "_@breakpoint@_"

    def __init__(self, common):
        """ctor."""
        super().__init__(common.vim)

    @staticmethod
    def check_content(fName):
        #self.logger.warning("abstract!")
        with open(fName, "r") as f:
            md5_hash = hashlib.md5()
            rows = ''.join(f.readlines()[1:])
            digest = hashlib.md5(rows.encode("utf8")).hexdigest()
            if fName in Common.md5_coll and digest == Common.md5_coll[fName]:
                return False
            Common.md5_coll[fName] = digest
            return True

    @staticmethod
    def json_out(obj):
        return json.dumps(obj, default=lambda o: o.__dict__, indent=4)
