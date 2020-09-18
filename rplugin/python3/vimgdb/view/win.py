"""."""
from libtmux.pane import Pane
from libtmux.server import Server
from libtmux.window import Window

from contextlib import contextmanager
from vimgdb.base.common import Common
from vimgdb.model.cursor import Cursor
from vimgdb.model.breakpoint import Breakpoint
from vimgdb.base.controller import Controller
from vimgdb.base.data import *


class Win(Common):
    """Jump window management."""

    def __init__(self, common: Common, ctx: Controller):
        """ctor."""
        super().__init__(common)

        self._shows = {
                "evtGdbOnJump":      self.evt_GdbOnJump,
                "viewUpdateBt":      self.view_UpdateBacktrace,
                "viewUpdateBp":      self.view_UpdateBreakpoint,
                "viewClearAllBreak": self.view_ClearAllBreak,
                "viewSignBreak":     self.view_SignBreak,
                }

        self._ctx = ctx
        self._name = type(self).__name__

        # window number that will be displaying the current file
        self.jump_win = None
        self.break_idx = 0
        self.break_sign_begin = 0
        self.break_sign_end = 0

        #self.cursor = cursor
        #self.breakpoint = break_point
        #self.buffers = set()

        # Create the default jump window
        #self._ensure_jump_window()


    def cleanup(self):
        """Cleanup the windows and buffers."""
        for buf in self.buffers:
            try:
                self.vim.command(f"silent bdelete {buf.handle}")
            except pynvim.api.common.NvimError as ex:
                self.logger.warning("Skip cleaning up the buffer: %s", ex)

    def _has_jump_win(self):
        """Check whether the jump window is displayed."""
        return self.jump_win in self.vim.current.tabpage.windows

    def is_jump_window_active(self):
        """Check whether the current buffer is displayed in the jump window."""
        if not self._has_jump_win():
            return False
        return self.vim.current.buffer == self.jump_win.buffer

    @contextmanager
    def _saved_win(self):
        # We're going to jump to another window and return.
        # There is no need to change keymaps forth and back.
        prev_win = self.vim.current.window
        yield
        self.vim.current.window = prev_win

    @contextmanager
    def _saved_mode(self):
        mode = self.vim.api.get_mode()
        yield
        if mode['mode'] in "ti":
            self.vim.command("startinsert")

    def _ensure_jump_window(self):
        """Ensure that the jump window is available."""
        if not self._has_jump_win():
            # The jump window needs to be created first
            with self._saved_win():
                self.vim.command(self.config.get("codewin_command"))
                self.jump_win = self.vim.current.window
                # Remember the '[No name]' buffer for later cleanup
                self.buffers.add(self.vim.current.buffer)

    def jump(self, file: str, line: int):
        """Show the file and the current line in the jump window."""
        self.logger.info("jump(%s:%d)", file, line)
        # Check whether the file is already loaded or load it
        target_buf = self.vim.call("bufnr", file, 1)

        # Ensure the jump window is available
        with self._saved_mode():
            self._ensure_jump_window()
        if not self.jump_win:
            raise AssertionError("No jump window")

        if self.jump_win.buffer.handle != target_buf:
            with self._saved_mode(), self._saved_win():
                if self.jump_win != self.vim.current.window:
                    self.vim.current.window = self.jump_win
                # Hide the current line sign when navigating away.
                self.cursor.hide()
                target_buf = self._open_file(f"noswap e {file}")
                self.query_breakpoints()

        # Goto the proper line and set the cursor on it
        self.jump_win.cursor = (line, 0)
        self.cursor.set(target_buf, line)
        self.cursor.show()
        self.vim.command("redraw")

    def _open_file(self, cmd):
        open_buffers = self.vim.buffers
        self.vim.command(cmd)
        new_buffer = self.vim.current.buffer
        if new_buffer not in open_buffers:
            # A new buffer was open specifically for debugging,
            # remember it to close later.
            self.buffers.add(new_buffer)
        return new_buffer.handle

    def query_breakpoints(self):
        """Show actual breakpoints in the current window."""
        if not self._has_jump_win():
            return

        # Get the source code buffer number
        buf_num = self.jump_win.buffer.handle

        # Get the source code file name
        fname = self.vim.call("expand", f'#{buf_num}:p')

        # If no file name or a weird name with spaces, ignore it (to avoid
        # misinterpretation)
        if fname and fname.find(' ') == -1:
            # Query the breakpoints for the shown file
            self.breakpoint.query(buf_num, fname)
            self.vim.command("redraw")


    def handle_show(self, data: BaseData):
        if data._name in self._shows:
            self.logger.info(f"{data._name}()")
            self._shows[data._name](data)
        else:
            self.logger.info(f"has no {data._name}()")


    def evt_GdbOnJump(self, data: BaseData):
        self.logger.info(f"{data}")
        assert isinstance(data, DataEvtCursor)

        #self._context.vimgdb.vim.command("e " + jumpfile  + ":" + jumpline)
        #self._context.vimgdb.vim.asyn_call("VimGdbJump", jumpfile, jumpline)

        #self._context.vimgdb.vim.funcs.VimGdbJump(jumpfile, jumpline)
        #self._context.vimgdb._wrap_async(
        #        self._context.vimgdb.vim.funcs.VimGdbJump)(
        #                jumpfile, jumpline)

        vimCmdstr = f"VimGdbJump('{data.fName}', {data.fLine})"
        self.logger.debug(f"{vimCmdstr}")
        self._ctx._wrap_async(self._ctx.vim.eval)(vimCmdstr)

    def view_UpdateBacktrace(self, data: BaseData):
        vimCmdstr = "VimGdbViewBtrace()"
        self.logger.debug(f"{vimCmdstr}")
        self._ctx._wrap_async(self._ctx.vim.eval)(vimCmdstr)

    def view_UpdateBreakpoint(self, data: BaseData):
        vimCmdstr = "VimGdbViewBpoint()"
        self.logger.debug(f"{vimCmdstr}")
        self._ctx._wrap_async(self._ctx.vim.eval)(vimCmdstr)


    def view_ClearAllBreak(self, data: BaseData):
        self.logger.debug(f"{Common.vimsign_group_breakp}: Clear all breaks sign")
        self._ctx._wrap_async(self._ctx.vim.call)('sign_unplace', '*', {'group': Common.vimsign_group_breakp})

        self.break_idx = 0
        self.break_sign_begin = 5000
        self.break_sign_end = 5000

    def view_ClearAllBreak2(self, data: BaseData):
        vimCmdstr = f"VimGdbClearSign({self.break_sign_begin}, {self.break_sign_end})"
        self.logger.debug(f"{vimCmdstr}")
        self._ctx._wrap_async(self._ctx.vim.eval)(vimCmdstr)

        self.break_idx = 0
        self.break_sign_begin = 5000
        self.break_sign_end = 5000

    def view_SignBreak(self, data: BaseData):
        assert isinstance(data, DataObjBreakpoint)
        vimCmdstr = ''
        vimSignName = ''
        if self.break_idx < Common.vimsign_break_max:
            self.break_idx += 1
        if data.enable:
            vimSignName = f'GdbBreakpointEn{self.break_idx}'
        else:
            vimSignName = f'GdbBreakpointDis{self.break_idx}'

        vimCmdstr = f"VimGdbSign('{data.fName}', {data.fLine}, {self.break_sign_end}, '{Common.vimsign_group_breakp}', '{vimSignName}')"
        #self.vim.call('sign_place', sign_id, 'NvimGdb', sign_name, buf,
        #              {'lnum': line, 'priority': 10})

        self.logger.debug(f"{Common.vimsign_break_max}: {vimCmdstr}")
        self._ctx._wrap_async(self._ctx.vim.eval)(vimCmdstr)
        self.break_sign_end += 1




