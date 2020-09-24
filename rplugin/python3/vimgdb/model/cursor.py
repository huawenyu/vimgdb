"""Manipulating the current line sign."""

from vimgdb.base.common import Common
from vimgdb.model.model import Model
from vimgdb.base.controller import Controller
from vimgdb.base.data import *


class Cursor(Model):
    """The current line sign operations."""

    def __init__(self, common: Common, ctx: Controller):
        """ctor."""
        super().__init__(common, type(self).__name__)
        self.buf = -1
        self.line = -1
        self.sign_id = -1

        self.fName = ''
        self.fLine = -1

        self._evts = {
                "evtGdbOnJump":     self.evt_GdbOnJump,
                }

        self._ctx = ctx

    def hide(self):
        """Hide the current line sign."""
        if self.sign_id != -1 and self.buf != -1:
            self.vim.call('sign_unplace', 'vimgdb',
                          {'id': self.sign_id, 'buffer': self.buf})
            self.sign_id = -1


    def show(self):
        """Show the current line sign."""
        # To avoid flicker when removing/adding the sign column(due to
        # the change in line width), we switch ids for the line sign
        # and only remove the old line sign after marking the new one.
        old_sign_id = self.sign_id
        self.sign_id = 4999 + (4998 - old_sign_id if old_sign_id != -1 else 0)
        if self.line != -1 and self.buf != -1:
            self.vim.call('sign_place', self.sign_id, 'vimgdb',
                          'GdbCurrentLine', self.buf,
                          {'lnum': self.line, 'priority': 20})
        if old_sign_id != -1:
            self.vim.call('sign_unplace', 'vimgdb',
                          {'id': old_sign_id, 'buffer': self.buf})


    def set(self, buf: int, line: int):
        """Set the current line sign number."""
        self.buf = buf
        self.line = int(line)


    def handle_evt(self, data: BaseData):
        if data._name in self._evts:
            self.logger.info(f"{data._name}()")
            self._evts[data._name](data)
        else:
            self.logger.info(f"ignore {data._name}()")


    def handle_cmd(self, cmdname, args):
        self.logger.info(f"handle_cmd: {cmdname}(args={args})")


    def handle_act(self, data: BaseData):
        self.logger.info(f"{data}")


    def evt_GdbOnJump(self, data: BaseData):
        self.logger.info("")
        assert isinstance(data, DataEvtCursor)
        #if self.fName != data.fName or self.fLine != data.fLine:
        if True:
            self.fName = data.fName
            self.fLine = data.fLine
            self._ctx.handle_shows(data)



