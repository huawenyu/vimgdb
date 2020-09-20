"""Plugin entry point."""

# pylint: disable=broad-except
import os
import os.path
import re
import logging
import logging.config
from typing import Dict
import pynvim   # type: ignore
from vimgdb.base.common import BaseCommon, Common
from vimgdb.controller.appcontroller import AppController
from vimgdb.config.logger import LOGGING_CONFIG


@pynvim.plugin
class Entry(Common):
    """Plugin implementation."""

    def __init__(self, vim):
        """ctor."""
        logging.config.dictConfig(LOGGING_CONFIG)
        common = BaseCommon(vim)
        super().__init__(common)
        self.apps: Dict[int, AppController] = {}
        self._ctx = None
        self.ansi_escaper = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')

    def _get_app(self):
        return self.apps.get(self.vim.current.tabpage.handle, None)

    @pynvim.autocmd('VimEnter', pattern='*', eval="", sync=True)
    def on_VimEnter(self):
        if os.path.exists('/tmp/vimLeave'):
            os.remove('/tmp/vimLeave')
        #if len(self.gdb_output):
        #    self.vim.command('let g:vimgdb_output = ' + self.gdb_output)
        #    #self.vim.out_write('\nneobugger_leave' + self.gdb_output + '\n')

    #@pynvim.autocmd('VimLeavePre', pattern='*.py', eval='expand("<afile>")', sync=True)
    #@pynvim.autocmd('VimLeavePre', pattern='*', eval='call writefile("\nneobugger_leave\n", g:vimgdb_output)', sync=True)
    #@pynvim.autocmd('VimLeavePre', pattern='*', eval='call writefile("\nneobugger_leave\n", g:vimgdb_output)', sync=True)
    @pynvim.autocmd('VimLeave', pattern='*', eval='expand("<afile>")', sync=True)
    def on_VimLeave(self, filename):
        #os.system('touch ' + self._outfile)
        os.system('touch /tmp/vimLeave')

        ##self.vim.out_write('\nneobugger_leave' + self.gdb_output + '\n')
        #self.logger.info("VimGdb handle VimLeave: Exiting the gdb debug %s", filename)
        #if self.tmux_win:
        #    self.tmux_win.kill_window()


    @pynvim.function('VimGdbSend')
    def handle_cmd(self, args):
        if not self._ctx:
            self.vim.command('echomsg "Please call VimGdb(\'local\', \'a.out\')"')
            return

        if len(args) < 2:
            self.logger.info("VimGdbSend('who', 'command'), but args=%s", args)
            return
        self.logger.info("VimGdbSend args=%s", args)
        self._ctx.handle_cmds(args)


    @pynvim.function('VimGdbLayout')
    def select_layout(self, args):
        if not self._ctx:
            self.vim.command('echomsg "Please call VimGdb(\'local\', \'a.out\')"')
            return

        if len(args) < 1:
            self.logger.info("VimGdbSend('who', 'command'), but args=%s", args)
            return
        self.logger.info("VimGdbLayout args=%s", args)
        self._ctx.select_layout(args[0])


    # Show help howto troubleshooting:
    #    Execute From Vim command line: call VimGdbDebug()
    @pynvim.function('VimGdbDebug')
    def show_debuginfo(self, args):
        self.logger.info("VimGdbDebug args=%s", args)
        self.vim.command('echomsg "pane1: tail -f self.logger.dut; '
                + 'pane2: tail -f /tmp/vim.log; '
                + 'pane3: tail -f /tmp/vimgdb.gdb"')


    # Execute From Vim command line: call VimGdb('local', 't1')
    @pynvim.function('VimGdb', sync=True)
    def start_app(self, args):
        """Handle the command GdbInit."""
        self.logger.info("VimGdbDebug args=%s", args)
        if self._ctx:
            self.vim.command('Cannot support double call VimGdb(\'local\', \'a.out\')"')
            return

        # Prepare configuration: keymaps, hooks, parameters etc.
        common = BaseCommon(self.vim)
        self._ctx = AppController(common, args)
        self.apps[self.vim.current.tabpage.handle] = self._ctx
        self._ctx.run(args)
        #if len(self.apps) == 1:
        #    # Initialize the UI commands, autocommands etc
        #    self.vim.call("nvimgdb#GlobalInit")

