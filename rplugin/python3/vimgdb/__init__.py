"""Plugin entry point."""

# pylint: disable=broad-except
import re
from contextlib import contextmanager
import logging
import logging.config
from typing import Dict
import pynvim   # type: ignore
from vimgdb.common import BaseCommon, Common
from vimgdb.app import App
from vimgdb.logger import LOGGING_CONFIG


@pynvim.plugin
class Entry(Common):
    """Plugin implementation."""

    def __init__(self, vim):
        """ctor."""
        logging.config.dictConfig(LOGGING_CONFIG)
        common = BaseCommon(vim)
        super().__init__(common)
        self.apps: Dict[int, App] = {}
        self.app = None
        self.ansi_escaper = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')

    def _get_app(self):
        return self.apps.get(self.vim.current.tabpage.handle, None)

    ##@pynvim.autocmd('VimEnter', pattern='*', eval="echomsg neobugger_enter", sync=True)
    ##def on_VimEnter(self, filename):
    ##    if len(self.gdb_output):
    ##        self.vim.command('let g:vimgdb_output = ' + self.gdb_output)
    ##        #self.vim.out_write('\nneobugger_leave' + self.gdb_output + '\n')

    ##@pynvim.autocmd('VimLeavePre', pattern='*.py', eval='expand("<afile>")', sync=True)
    ##@pynvim.autocmd('VimLeavePre', pattern='*', eval='call writefile("\nneobugger_leave\n", g:vimgdb_output)', sync=True)
    ##@pynvim.autocmd('VimLeavePre', pattern='*', eval='call writefile("\nneobugger_leave\n", g:vimgdb_output)', sync=True)
    #@pynvim.autocmd('VimLeave', pattern='*', eval='expand("<afile>")', sync=True)
    #def on_VimLeave(self, filename):
    #    #self.vim.out_write('\nneobugger_leave' + self.gdb_output + '\n')
    #    self.logger.info("VimGdb handle VimLeave: Exiting the gdb debug %s", filename)
    #    if self.tmux_win:
    #        self.tmux_win.kill_window()


    @pynvim.function('VimGdbSend')
    def sendcommand(self, args):
        if not self.app:
            self.vim.command('echomsg "Please call VimGdb(\'local\', \'a.out\')"')
            return

        if len(args) < 2:
            self.logger.info("VimGdbSend('who', 'command'), but args=%s", args)
            return
        self.logger.info("VimGdbSend args=%s", args)
        self.app.sendcommand(args)


    # Show help howto troubleshooting:
    #    Execute From Vim command line: call VimGdbDebug()
    @pynvim.function('VimGdbDebug')
    def debugVimGdb(self, args):
        self.logger.info("VimGdbDebug args=%s", args)
        self.vim.command('echomsg "pane1: tail -f self.logger.dut; '
                + 'pane2: tail -f /tmp/vim.log; '
                + 'pane3: tail -f /tmp/vimgdb.gdb"')


    # Execute From Vim command line: call VimGdb('local', 't1')
    @pynvim.function('VimGdb', sync=True)
    def startVimGdb(self, args):
        """Handle the command GdbInit."""
        self.logger.info("VimGdbDebug args=%s", args)
        if self.app:
            self.vim.command('Cannot support double call VimGdb(\'local\', \'a.out\')"')
            return

        # Prepare configuration: keymaps, hooks, parameters etc.
        common = BaseCommon(self.vim)
        self.app = App(common, args)
        self.apps[self.vim.current.tabpage.handle] = self.app
        self.app.run(args)
        #if len(self.apps) == 1:
        #    # Initialize the UI commands, autocommands etc
        #    self.vim.call("nvimgdb#GlobalInit")

