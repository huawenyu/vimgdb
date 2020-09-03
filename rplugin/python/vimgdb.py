import getopt
from os.path import dirname, relpath
import sys
import logger
import cmd
import thread
import time
import subprocess

import neovim
# https://github.com/neovim/pynvim
#
#>>> from pynvim import attach
## Create a python API session attached to unix domain socket created above:
#>>> nvim = attach('socket', path='/tmp/nvim')
## Now do some work. 
#>>> buffer = nvim.current.buffer # Get the current buffer
#>>> buffer[0] = 'replace first line'
#>>> buffer[:] = ['replace whole buffer']
#>>> nvim.command('vsplit')
#>>> nvim.windows[1].width = 10
#>>> nvim.vars['global_var'] = [1, 2, 3]
#>>> nvim.eval('g:global_var')
#[1, 2, 3]
#
#
from libtmux.exc import TmuxSessionExists
from libtmux.pane import Pane
from libtmux.server import Server
from libtmux.session import Session
from libtmux.window import Window

# lib used login remote DUT by ssh
from dut_control import *

sys.path.insert(0, dirname(__file__))

import context
import gdb
import gdbserver

log = logger.GetLogger(__name__)

class GdbMode:
    LOCAL = 'local'
    REMOTE = 'remote'

class GdbState:
    INIT      = 'init'
    START     = 'start'
    TARGET    = 'target'
    CONN_SUCC = 'conn_succ'
    PAUSE     = 'pause'
    RUN       = 'run'

class GdbServerState:
    INIT        = 'init'
    LISTEN      = 'listen'
    WAIT        = 'wait'
    ACCEPT      = 'accept'
    REMOTE_CONN = 'remote_conn'

@neovim.plugin
class VimGdb(object):
    def __init__(self, vim):
        self.vim = vim

        self.workdir = os.getcwd()
        self.scriptdir = os.path.dirname(os.path.abspath(__file__))
        self.file = ''
        self.gdb_output = '/tmp/vimgdb.gdb'
        self.gdbserver_output = '/tmp/vimgdb.gdbserver'
        self.debug_mode = GdbMode.LOCAL
        self.debug_bin = "t1"

        self.tmux_server = None
        self.tmux_session = None
        self.tmux_win = None
        self.tmux_pan_vim = None
        self.tmux_pan_gdb = None
        self.tmux_pan_gdbserver = None
        self.tmux_sesname = ""
        self.tmux_sesid = ""

        self.ctx_gdb = None
        self.ctx_gdbserver = None

        #           echo \"PS1='newRuntime $ '\" >> /tmp/tmp.bashrc; 
        #           echo \"+o emacs\" >> /tmp/tmp.bashrc; 
        #           echo \"+o vi\" >> /tmp/tmp.bashrc; 
        #           bash --noediting --rcfile /tmp/tmp.bashrc 
        self.gdb_bash = """cat ~/.bashrc > /tmp/tmp.bashrc; 
                   echo \"PS1='newRuntime $ '\" >> /tmp/tmp.bashrc; 
                   bash --rcfile /tmp/tmp.bashrc 
                  """
        self.cmd_gdb = ""
        self.cmd_gdbserver = ''

    #@neovim.autocmd('VimEnter', pattern='*', eval="", sync=True)
    #def on_VimEnter(self, filename):
    #    self.vim.command('let g:vimgdb_output = ' + self.gdb_output)
    #    #self.vim.out_write('\nneobugger_leave' + self.gdb_output + '\n')

    #@neovim.autocmd('VimLeavePre', pattern='*.py', eval='expand("<afile>")', sync=True)
    #@neovim.autocmd('VimLeavePre', pattern='*', eval='call writefile("\nneobugger_leave\n", g:vimgdb_output)', sync=True)
    @neovim.autocmd('VimLeavePre', pattern='*', eval='echomsg "wilson leave"', sync=True)
    def on_VimLeave(self, filename):
        #self.vim.out_write('\nneobugger_leave' + self.gdb_output + '\n')
        if self.tmux_win:
            self.tmux_win.kill_window()

    def gdbLocal(self, args):
        self.ctx_gdb = gdb.Gdb(self, self.gdb_output)

        self.tmux_server._update_windows()
        self.tmux_server._update_panes()

        #self.tmux_win.select_layout('main-horizontal')
        self.tmux_win.select_layout('main-vertical')

        os.system('touch ' + self.gdb_output)
        self.start_thread_parser(self.ctx_gdb)

    def gdbRemote(self, args):
        self.ctx_gdb = gdb.Gdb(self, self.gdb_output)
        self.ctx_gdbserver = gdbserver.GdbServer(self, self.gdbserver_output)

        self.tmux_pane_gdbserver = self.tmux_win.split_window(attach=True, start_directory=self.workdir, )
        assert isinstance(self.tmux_pane_gdbserver, Pane)
        self.tmux_pane_gdbserver.send_keys(self.cmd_gdbserver, suppress_history=True)
        self.tmux_pane_gdbserver.enter()
        self.tmux_pane_gdbserver.clear()

        self.tmux_server._update_windows()
        self.tmux_server._update_panes()

        #self.tmux_win.select_layout('main-horizontal')
        self.tmux_win.select_layout('main-vertical')

        os.system('touch ' + self.gdb_output)
        os.system('touch ' + self.gdbserver_output)
        os.system('truncate -s 0 ' + self.gdb_output)
        os.system('truncate -s 0 ' + self.gdbserver_output)
        self.start_thread_parser(self.ctx_gdb)
        self.start_thread_parser(self.ctx_gdbserver)


    # Execute From Vim command line: call VimGdb('local', 't1')
    @neovim.function('VimGdb')
    def startVimGdb(self, args):
        log.info("VimGdb args=%s", args)
        arg_n = len(args)
        if arg_n < 2:
            self.vim.command('echomsg "Gdb start fail, should: call VimGdb(\'local\', \'<bin-file>\')"')
            return
        self.debug_mode = args[0]
        self.debug_bin = args[1]

        #let s:dir = expand('<sfile>:p:h')
        self.vim.command('let g:vimgdb_file = expand("%:p")')
        self.file = self.vim.eval('g:vimgdb_file')
        if len(self.file) < 1:
            self.vim.command('echomsg "Gdb start fail, no current file"')
            return

        self.cmd_gdb = "gdb --command " + self.scriptdir + "/gdbinit -q -f --args " + self.debug_bin + " | tee -a " + self.gdb_output
        self.cmd_gdbserver = 'dut.py -h dut -u admin -p "" -t "gdb:wad" ' + " | tee -a " + self.gdbserver_output

        cur_ses = subprocess.check_output(['tmux', 'display-message', '-p', '#S;#{session_id}'])
        [self.tmux_sesname, self.tmux_sesid] = cur_ses.strip().split(';')
        log.info("Current tmux session name='%s' id='%s' dir='%s'", self.tmux_sesname, self.tmux_sesid, self.workdir)
        self.tmux_server = Server()
        self.tmux_session = self.tmux_server.get_by_id(self.tmux_sesid)
        self.tmux_win = self.tmux_session.new_window(
                attach=True,           # do not move to the new window
                window_name="vim-gdb",
                start_directory=self.workdir,
                )
        assert isinstance(self.tmux_win, Window)
        self.tmux_pane_vim = self.tmux_win.attached_pane
        assert isinstance(self.tmux_pane_vim, Pane)
        self.tmux_pane_vim.enter()
        self.tmux_pane_vim.clear()
        self.tmux_pane_vim.send_keys("nvim " + self.file, suppress_history=True)

        self.tmux_pane_gdb = self.tmux_win.split_window(attach=True, start_directory=self.workdir, )
        assert isinstance(self.tmux_pane_gdb, Pane)
        self.tmux_pane_gdb.send_keys(self.gdb_bash, suppress_history=True)
        self.tmux_pane_gdb.send_keys(self.cmd_gdb, suppress_history=True)
        self.tmux_pane_gdb.enter()
        self.tmux_pane_gdb.clear()

        if self.debug_mode == GdbMode.LOCAL:
            self.gdbLocal(args)
        elif self.debug_mode == GdbMode.REMOTE:
            self.gdbRemote(args)
        else:
            log.error("VimGdb mode=%s not exist.", self.debug_mode)
        return

    def tail_file(self, name, afile, thefile):
        '''generator function that yields new lines in a file
        '''
        log.info("Context '%s' tail-file '%s'", name, afile)
        thefile.seek(0, os.SEEK_END) # Go to the end of the file

        # start infinite loop
        line = ''
        while True:
            #log.info("Context '%s' tail-file '%s' before", name, afile)
            part = thefile.readline()
            #log.info("Context '%s' tail-file '%s' after with: '%s'", name, afile, line)
            if not part:
                time.sleep(0.1) # Sleep briefly
                continue

            line += part
            if not part.endswith('\n'):
                continue
            line = line.rstrip('\r\n')
            if len(line) == 0:
                continue
            yield line
            line = ''

    def parser_file(self, ctx):
        thefile = open(ctx._outfile, 'r')
        thelines = self.tail_file(ctx._name, ctx._outfile, thefile)
        for line in thelines:
            log.info("Context '%s' parser: '%s'", ctx._name, line)
            try:
                ctx.parser_line(line)
            except:
                log.info("  parser error: '%s'", sys.exc_info()[0])

    @staticmethod
    def handler_parser_file(vimgdb, ctx):
        vimgdb.parser_file(ctx)

    def start_thread_parser(self, ctx):
        try:
            thread.start_new_thread(VimGdb.handler_parser_file, (self, ctx))
        except:
            log.error("Error: Unable to start thread")

