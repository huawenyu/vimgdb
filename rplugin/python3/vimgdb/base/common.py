"""Common base for every class."""

import logging
import hashlib


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
    gdb_file_debugfile    = "/tmp/vimgdb.log"

    # map output
    gdb_output            = '/tmp/vimgdb.gdb'
    gdbserver_output      = '/tmp/vimgdb.gdbserver'

    gdb_bt_qf             = '/tmp/vimgdb.bt'
    gdb_break_qf          = '/tmp/vimgdb.qf_bp'
    gdb_tmp_break         = './.gdb.infobreak'
    #gdb_tmp_break         = '/tmp/vimgdb.infobreak'
    gdb_bt_qf_md5         = None

    gdb_file_infolocal    = "/tmp/vimgdb.var"
    gdb_file_vimleave     = "/tmp/vimLeave"
    gdb_file_bp_fromgdb   = "./.gdb.break"
    gdb_file_bp_fromctrl   = "./.gdb.breakctrl"
    gdb_anchor_breakpoint = "neobugger_setbreakpoint"

    def __init__(self, common):
        """ctor."""
        super().__init__(common.vim)

    def update_view(self):
        #self.logger.warning("abstract!")
        pass

    def update_model(self):
        #self.logger.warning("abstract!")
        with open(self.gdb_bt_qf, "r") as f:
            md5_hash = hashlib.md5()
            rows = ''.join(f.readlines()[1:])
            digest = hashlib.md5(rows.encode("utf8")).hexdigest()
            if digest != self.gdb_bt_qf_md5:
                self.gdb_bt_qf_md5 = digest
                self.update_view()
