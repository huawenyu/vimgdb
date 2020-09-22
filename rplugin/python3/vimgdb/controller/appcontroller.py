import os
import sys
import re
import _thread
import time
import json
import codecs
import os.path
import subprocess
from typing import Dict, List

from libtmux.pane import Pane
from libtmux.server import Server
from libtmux.window import Window

from vimgdb.base.common import Common
from vimgdb.base.controller import Controller, GdbMode
from vimgdb.controller.workspace import Workspace
from vimgdb.model.gdb import Gdb
from vimgdb.model.gdbserver import GdbServer
from vimgdb.model.cursor import Cursor
from vimgdb.model.breakpoint import Breakpoint

from vimgdb.view.win import Win


class AppController(Controller):
    """Main application class."""

    def __init__(self, common: Common, args):
        super().__init__(common, type(self).__name__)

        self._scriptdir = os.path.dirname(os.path.abspath(__file__))
        self._common = common
        self.is_exit = False

        self.workdir = os.getcwd()
        self.file = ''
        self.debug_bin = "t1"

        self.tmux_server = None
        self.tmux_session = None
        self.tmux_pwin_idx = ''
        self.tmux_window_vim = None
        self.tmux_curr_pan_id = ''
        self.tmux_pan_vim = None
        self.tmux_pan_gdb = None
        self.tmux_pan_gdbserver = None
        self.tmux_sesname = ""
        self.tmux_sesid = ""
        self.tmux_win_def_width = 800
        self.tmux_win_def_height = 600

        self.layout_conf = {}
        self.workSpace = None
        self.workLayouts = {}
        self.helper = {}
        self.helper['worklayouts_loaded'] = False

        self.ctx_gdb = None
        self.ctx_gdbserver = None

        self.cmd_gdb = ""
        self.cmd_gdbserver = ''
        self.curr_layout = ''

        # self.breakpoint = Breakpoint(common)
        # self.cursor = Cursor(common)
        # self.win = Win(common, self.cursor)


    def _wrap_async(self, func):
        """
        Wraps `func` so that invocation of `func(args, kwargs)` happens
        from the main thread. This is a requirement of pynvim API when
        function call happens from other threads.
        Related issue: https://github.com/numirias/semshi/issues/25
        """

        def wrapper(*args, **kwargs):
            return self.vim.async_call(func, *args, **kwargs)

        return wrapper


    def create_gdb_local(self, args):
        modelGdb = Gdb(self._common,
                self,
                self.tmux_window_vim,
                self.workSpace.get_pane(self.curr_layout, Common.tmux_pane_builtin_gdb),
                self.debug_bin, self.gdb_output)
        if not modelGdb:
            return
        self.models_coll[modelGdb._name] = modelGdb

        # self.vim.command('let g:vimgdb_gdb = ' + modelGdb._name)
        self.vim.vars['vimgdb_gdb'] = modelGdb._name

        self.tmux_server._update_windows()
        self.tmux_server._update_panes()


    def create_gdb_remote(self, args):
        modelGdbserver = GdbServer(self._common, self,
                self.tmux_window_vim,
                self.workSpace.get_pane(self.curr_layout, Common.tmux_pane_builtin_gdbserver),
                self.debug_bin, self.gdbserver_output)
        if not modelGdbserver:
            return
        self.models_coll[modelGdbserver._name] = modelGdbserver
        # self.vim.command('let g:vimgdb_gdbserver = ' + modelGdbserver._name)
        self.vim.vars['vimgdb_gdbserver'] = modelGdbserver._name

        self.tmux_server._update_windows()
        self.tmux_server._update_panes()


    def _define_vimsigns(self):
        # Define the sign for current line the debugged program is executing.
        self.vim.call('sign_define', 'GdbCurrentLine',
                {'text': self.vim.vars['vimgdb_sign_currentline'],
                 'texthl': self.vim.vars['vimgdb_sign_currentline_color']})

        # Define signs for the breakpoints.
        breaks = self.vim.vars['vimgdb_sign_breakpoints']
        for i, brk in enumerate(breaks):
            #sign define GdbBreakpointEn  text=● texthl=Search
            #sign define GdbBreakpointDis text=● texthl=Function
            #sign define GdbBreakpointDel text=● texthl=Comment

            self.vim.call('sign_define', f'GdbBreakpointEn{i+1}',
                    {'text': brk,
                     'texthl': self.vim.vars['vimgdb_sign_breakp_color_en']})
            self.vim.call('sign_define', f'GdbBreakpointDis{i+1}',
                    {'text': brk,
                     'texthl': self.vim.vars['vimgdb_sign_breakp_color_dis']})
            Common.vimsign_break_max += 1


    def list_layout(self):
        names = ''
        for layoutname in self.workLayouts.keys():
            names += layoutname + ', '
        self.vim.command(f'echomsg "VimGdb layout: `{names}`"')


    def load_layout_conf(self):
        self.conf = self._scriptdir + "/../config/default.json"
        if os.path.isfile(Common.vimgdb_conffile):
            self.conf = Common.vimgdb_conffile
        #self.logger.info(f"connect config={self.conf}")
        with open(self.conf, 'r') as f:
            content = f.read()
            #decoded_data=content.encode().decode('utf-8-sig')
            self.layout_conf = json.loads(content)

    def build_workspace(self):
        self.load_layout_conf()

        tmux_builtin_panes = {}
        self.helper[Common.tmux_builtin_panes] = tmux_builtin_panes
        tmux_builtin_panes[Common.tmux_pane_builtin_main] = ''
        tmux_builtin_panes[Common.tmux_pane_builtin_gdb] = Gdb.get_cmdstr(self._scriptdir, self.debug_bin)

        # Avoid gdbserver start too ealier, waiting gdb done.
        #tmux_builtin_panes[Common.tmux_pane_builtin_gdbserver] = GdbServer.get_cmdstr(self._scriptdir, self.debug_bin)
        tmux_builtin_panes[Common.tmux_pane_builtin_gdbserver] = ''

        self.workSpace = Workspace(self._common,
                self.layout_conf,
                self.helper[Common.tmux_builtin_panes],
                self.workdir,
                self.tmux_server, self.tmux_win_def_width, self.tmux_win_def_height)

        self.build_set_current()
        if self.gdbMode == GdbMode.LOCAL:
            self.curr_layout = Common.tmux_layout_local
        elif self.gdbMode == GdbMode.REMOTE:
            self.curr_layout = Common.tmux_layout_remote

        self.build_all_layout_codes()
        self.build_layout(self.curr_layout)


    def build_all_layout_codes(self):
        if self.workLayouts and self.helper['worklayouts_loaded']:
            self.logger.info(f"connect Existed and don't need create layout={self.workLayouts}")
            return

        self.helper['worklayouts_loaded'] = True
        self.workLayouts.update(self.workSpace.build_all_layout_codes(Common.tmux_vimgdb_session_name))
        self.logger.info(f"connect layout={self.workLayouts}")


    def build_set_current(self):
        # Tmux: reuse current tmux-window, but close all other panes in current window
        #   for only current vim is the controled vim instance.
        # self.tmux_window_vim = self.tmux_session.new_window(
        #        attach=True,           # do not move to the new window
        #        window_name="VimGdb",
        #        start_directory=self.workdir,
        #        window_index='', #
        #        window_shell='', #"vim " + self.file,
        #        )
        self.tmux_window_vim = self.tmux_session.attached_window;
        assert isinstance(self.tmux_window_vim, Window)
        self.tmux_window_vim['window_name'] = self.curr_layout

        self.tmux_pane_vim = self.tmux_window_vim.attached_pane
        assert isinstance(self.tmux_pane_vim, Pane)
        self.tmux_pane_vim['pane_name'] = Common.tmux_pane_builtin_main


    def build_layout(self, layout: str):
        self.logger.info(f"connect rebuild layout '{layout}'")
        self.workSpace.build_one_layout(layout,
                self.tmux_session,
                self.tmux_window_vim,
                self.tmux_pane_vim,
                Common.tmux_pane_builtin_main)


    def layout_select(self, layout: str):
        if layout not in self.workLayouts:
            self.vim.command(f'echomsg "VimGdb layout `{layout}` not exist, check VimGdbLayoutList()"')
            return

        # But can't create new pane
        #self.tmux_window_vim.select_layout(self.workLayouts[layout]['layout'])

        self.workSpace.build_one_layout(layout,
                self.tmux_session,
                self.tmux_window_vim,
                self.tmux_pane_vim,
                Common.tmux_pane_builtin_main)


    def run(self, args):
        self.logger.info("==============================================")
        self.logger.info("==============================================")
        self.logger.info("==============================================")
        self.logger.info("==============================================")
        self.logger.info("             *** Gdb instance ***")
        self.logger.info("")
        self.logger.info("args=%s", args)
        arg_n = len(args)
        if arg_n < 2:
            self.vim.command('echomsg "Gdb start fail, should: call VimGdb(\'local\', \'<bin-file>\')"')
            return
        self.gdbMode = args[0]
        self.gdbArgs = args[1]    # 't1 dut:8888 -u admin -p "" -t "gdb:trace"'
        chunks = re.split(' +', self.gdbArgs)
        if chunks:
            self.debug_bin = chunks[0]
            self.logger.info(f"Gdb starting '{self.debug_bin}' with {chunks[1:]} ...")
        else:
            self.debug_bin = self.gdbArgs
            self.logger.info(f"Gdb starting '{self.debug_bin}' ...")

        # let s:dir = expand('<sfile>:p:h')
        self.vim.command('let g:vimgdb_file = expand("%:p")')
        self.file = self.vim.eval('g:vimgdb_file')
        if len(self.file) < 1:
            self.vim.command('echomsg "Gdb start fail, no current file"')
            return

        tmux_info = subprocess.check_output(
            ['tmux', 'display-message', '-p', '#S;#{session_id};#{window_width};#{window_height};#{window_index};#{pane_id}'])
        tmux_info = tmux_info.decode()
        [self.tmux_sesname, self.tmux_sesid, self.tmux_win_def_width, self.tmux_win_def_height, self.tmux_pwin_idx, self.tmux_curr_pan_id] = tmux_info.strip().split(';')

        # option controller: kill other pane of current tmux window
        subprocess.check_output(['tmux', 'kill-pane', '-a', '-t', self.tmux_curr_pan_id])

        self.logger.info(f"Tmux: #{self.tmux_sesid} '{self.tmux_sesname}' {self.tmux_win_def_width}x{self.tmux_win_def_height} cwd='{self.workdir}'")
        self.tmux_server = Server()
        self.tmux_session = self.tmux_server.get_by_id(self.tmux_sesid)

        self.build_workspace()

        self.vim.funcs.VimGdbInit()
        self._define_vimsigns()

        # Create model Cursor:
        _model = Cursor(self._common, self)
        if not _model:
            return
        self.models_coll[_model._name] = _model

        # Create model Breakpoint:
        _model = Breakpoint(self._common, self)
        if not _model:
            return
        self.models_coll[_model._name] = _model

        # Create view MainVimWin:
        _view = Win(self._common, self)
        if not _view:
            return
        self.views_coll[_view._name] = _view

        self.logger.error("VimGdb mode=%s not exist.", self.gdbMode)
        if self.gdbMode == GdbMode.LOCAL or self.gdbMode == GdbMode.REMOTE:
            self.create_gdb_local(args)
        if self.gdbMode == GdbMode.REMOTE:
            self.create_gdb_remote(args)

        ##self.tmux_window_vim.select_layout('main-horizontal')
        #self.tmux_window_vim.select_layout('main-vertical')

        # focus backto vim
        self.tmux_pane_vim.select_pane()
        return
