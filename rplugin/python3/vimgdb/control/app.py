import os
import sys
import _thread
import time
import subprocess

from libtmux.pane import Pane
from libtmux.server import Server
from libtmux.window import Window

from vimgdb.base.common import Common
from vimgdb.view.gdb import Gdb
from vimgdb.view.gdbserver import GdbServer


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

class App(Common):
    """Main application class."""

    def __init__(self, common, args):
        super().__init__(common)

        self.is_exit = False

        self.workdir = os.getcwd()
        self.scriptdir = os.path.dirname(os.path.abspath(__file__))
        self.file = ''
        self.debug_mode = GdbMode.LOCAL
        self.debug_bin = "t1"

        self.tmux_server = None
        self.tmux_session = None
        self.tmux_pwin_idx = ''
        self.tmux_win = None
        self.tmux_curr_pan_id = ''
        self.tmux_pan_vim = None
        self.tmux_pan_gdb = None
        self.tmux_pan_gdbserver = None
        self.tmux_sesname = ""
        self.tmux_sesid = ""

        self.ctx_gdb = None
        self.ctx_gdbserver = None
        self.ctx_coll = {}

        #           echo \"PS1='newRuntime $ '\" >> /tmp/tmp.bashrc; 
        #           echo \"+o emacs\" >> /tmp/tmp.bashrc; 
        #           echo \"+o vi\" >> /tmp/tmp.bashrc; 
        #           bash --noediting --rcfile /tmp/tmp.bashrc 
        self.gdb_bash = """cat ~/.bashrc > /tmp/vimgdb.bashrc; 
                   echo \"PS1='newRuntime $ '\" >> /tmp/vimgdb.bashrc; 
                   bash --rcfile /tmp/vimgdb.bashrc 
                  """
        self.cmd_gdb = ""
        self.cmd_gdbserver = ''

        #self.breakpoint = Breakpoint(common)
        #self.cursor = Cursor(common)
        #self.win = Win(common, self.cursor)

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

    def gdbLocal(self, args):
        self.ctx_gdb = Gdb(self, self.gdb_output)
        if not self.ctx_gdb:
            return
        self.ctx_coll[self.ctx_gdb._name] = self.ctx_gdb
        #self.vim.command('let g:vimgdb_gdb = ' + self.ctx_gdb._name)
        self.vim.vars['vimgdb_gdb'] = self.ctx_gdb._name

        self.tmux_server._update_windows()
        self.tmux_server._update_panes()

        #self.tmux_win.select_layout('main-horizontal')
        self.tmux_win.select_layout('main-vertical')

        os.system('touch ' + self.gdb_output)
        self.start_thread_parser(self.ctx_gdb)

    def gdbRemote(self, args):
        self.ctx_gdb = Gdb(self, self.gdb_output)
        if not self.ctx_gdb:
            return
        self.ctx_coll[self.ctx_gdb._name] = self.ctx_gdb
        self.vim.vars['vimgdb_gdb'] = self.ctx_gdb._name
        #self.vim.command('let g:vimgdb_gdb = ' + self.ctx_gdb._name)

        self.ctx_gdbserver = GdbServer(self, self.gdbserver_output)
        if not self.ctx_gdbserver:
            return
        self.ctx_coll[self.ctx_gdbserver._name] = self.ctx_gdbserver
        #self.vim.command('let g:vimgdb_gdbserver = ' + self.ctx_gdbserver._name)
        self.vim.vars['vimgdb_gdbserver'] = self.ctx_gdbserver._name

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

    def sendcommand(self, args):
        if len(args) < 2:
            self.logger.info("VimGdbSend('who', 'command'), but args=%s", args)
            return
        self.logger.info("args=%s", args)
        ctxname = args[0]
        vimArgs = args[1]
        if ctxname in self.ctx_coll:
            ctx = self.ctx_coll.get(ctxname)
            if ctx:
                if type(vimArgs) is str:
                    ctx.request_cmd(vimArgs, args[1:])
                elif type(vimArgs) is list and len(vimArgs) > 0:
                    ctx.request_cmd(vimArgs[0], vimArgs)
                else:
                    self.logger.info("handle fail: args=%s", args)
                return
        else:
            self.logger.info("no context '%s'", ctxname)
        self.logger.error("fail: no context ", ctxname)


    def run(self, args):
        self.logger.info("args=%s", args)
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

        self.cmd_gdb = "gdb --command " + self.scriptdir + "/../config/gdbinit -q -f --args " + self.debug_bin + " | tee -a " + self.gdb_output
        self.cmd_gdbserver = 'dut.py -h dut -u admin -p "" -t "gdb:wad" ' + " | tee -a " + self.gdbserver_output

        tmux_info = subprocess.check_output(['tmux', 'display-message', '-p', '#S;#{session_id};#{window_index};#{pane_id}'])
        tmux_info = tmux_info.decode()
        [self.tmux_sesname, self.tmux_sesid, self.tmux_pwin_idx, self.tmux_curr_pan_id] = tmux_info.strip().split(';')

        # option control: kill other pane of current tmux window
        subprocess.check_output(['tmux', 'kill-pane', '-a', '-t', self.tmux_curr_pan_id])

        self.logger.info("Current tmux session name='%s' id='%s' dir='%s'",
                self.tmux_sesname,
                self.tmux_sesid,
                self.workdir)
        self.tmux_server = Server()
        self.tmux_session = self.tmux_server.get_by_id(self.tmux_sesid)

        # Tmux: reuse current tmux-window, but close all other panes in current window
        #   for only current vim is the controled vim instance.
        #self.tmux_win = self.tmux_session.new_window(
        #        attach=True,           # do not move to the new window
        #        window_name="VimGdb",
        #        start_directory=self.workdir,
        #        window_index='', #
        #        window_shell='', #"vim " + self.file,
        #        )

        self.tmux_win = self.tmux_session.attached_window;
        assert isinstance(self.tmux_win, Window)
        self.tmux_pane_vim = self.tmux_win.attached_pane
        assert isinstance(self.tmux_pane_vim, Pane)
        #self.tmux_pane_vim.enter()
        #self.tmux_pane_vim.clear()
        #self.tmux_pane_vim.send_keys("nvim " + self.file, suppress_history=True)
        self.vim.funcs.VimGdbInit()

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
            self.logger.error("VimGdb mode=%s not exist.", self.debug_mode)
        return

    def tail_file(self, name, afile, thefile):
        '''generator function that yields new lines in a file
        '''
        self.logger.info("Context '%s' tail-file '%s'", name, afile)
        thefile.seek(0, os.SEEK_END) # Go to the end of the file

        # start infinite loop
        line = ''
        while True:
            #self.logger.info("Context '%s' tail-file '%s' before", name, afile)
            part = thefile.readline()
            #self.logger.info("Context '%s' tail-file '%s' after with: '%s'", name, afile, line)
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
            self.logger.info("Context '%s' parser: '%s'", ctx._name, line)
            try:
                ctx.parser_line(line)
            except AttributeError as error:
                self.logger.info("  parser error: '%s'", error)
            except Exception as exception:
                self.logger.info("  parser exception: '%s'", exception)
            except:
                self.logger.info("  parser other: '%s'", sys.exc_info()[0])

    @staticmethod
    def handler_parser_file(vimgdb, ctx):
        vimgdb.parser_file(ctx)

    def start_thread_parser(self, ctx):
        try:
            _thread.start_new_thread(App.handler_parser_file, (self, ctx))
        except:
            self.logger.error("Error: Unable to start thread")

