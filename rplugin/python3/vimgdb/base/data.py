
class BaseData:
    """Common base part of all classes."""

    def __init__(self, name: str):
        """Construct to propagate context."""
        self._name = name



class DataEvent(BaseData):
    def __init__(self, name: str):
        """ctor."""
        super().__init__(name)


class DataCommand(BaseData):
    """Common part of all classes with convenient constructor."""

    def __init__(self, name: str):
        """ctor."""
        super().__init__(name)


class DataAction(BaseData):
    def __init__(self, name: str):
        """ctor."""
        super().__init__(name)


class DataEvtCursor(DataEvent):
    def __init__(self, name: str, fName: str, fLine: str):
        """ctor."""
        super().__init__(name)
        self.fName = fName
        self.fLine = fLine


class DataEvtParam1(DataEvent):
    def __init__(self, name: str, param1: str):
        """ctor."""
        super().__init__(name)
        self.param1 = param1


class DataObjBreakpoint(BaseData):
    vim_signid_start   = 5000

    status_init        = 0
    status_adding      = 1
    status_enable      = 2
    status_disable     = 3
    status_delete      = 4

    type_function      = 1
    type_line          = 2
    type_has_condition = 3

    def __init__(self, name: str, cmdstr: str, fName: str, fLine: str, bp_id: str, en: str, funcName: str):
        """ctor."""
        super().__init__(name)
        self.status = DataObjBreakpoint.status_init
        self.type = 0
        self.cmdstr = str(cmdstr)
        self.vim_signid = self.vim_signid_start
        self.vim_signid_start += 1
        self.vim_bufnr = 0
        self.vim_line = 0

        self.funcName = funcName
        self.fName = fName
        self.fLine = str(fLine)
        self.bp_id = str(bp_id)

        if en == 'y':
            self.enable = True
        else:
            self.enable = False

    @classmethod
    def from_json(cls, data):
        return cls(**data)

    @classmethod
    def CreateById(cls, bp_id: str):
        return cls('_breakpoint', '', '', '', bp_id, 'y', 'dummyFunc')

    @classmethod
    def CreateById2(cls, bp_id: str, cmdstr: str, ctxline: str):
        return cls('_breakpoint', cmdstr, '', '', bp_id, 'y', 'dummyFunc')

    @classmethod
    def CreateByFile(cls, fname: str, fline: str):
        return cls('_breakpoint', '', fname, fline, '', 'y', 'dummyFunc')

    @classmethod
    def CreateByCmdstr(cls, cmdstr: str):
        return cls('_breakpoint', cmdstr, '', '', '', 'y', 'dummyFunc')

    @classmethod
    def CreateDummy(cls):
        return cls('_breakpoint', "Empty Breakpoint", "<file>", -1, 0, 'n', 'dummyFunc')

    @classmethod
    def Create(cls, fname: str, fline: str, cmdstr: str, bp_id: str, en: str, funcName: str):
        return cls('_breakpoint', cmdstr, fname, fline, bp_id, en, funcName)

    def action(self, action: str):
        self._name = action
        return self

    def update(self, bp):
        self.bp_id = bp.bp_id
        self.enable = bp.enable
        if self.enable:
            self.status = DataObjBreakpoint.status_enable
        else:
            self.status = DataObjBreakpoint.status_disable
        self.fName = bp.fName
        self.fLine = bp.fLine
        self.funcName = bp.funcName
        if not self.cmdstr:
            self.cmdstr = bp.cmdstr

class DataCmdGdb(DataCommand):
    """Common part of all classes with convenient constructor."""

    def __init__(self, common):
        """ctor."""
        super().__init__(common.vim)

        self.gdb_output       = '/tmp/vimgdb.gdb'



class DataUpdate(BaseData):
    """Common part of all classes with convenient constructor."""

    def __init__(self, common):
        """ctor."""
        super().__init__(common.vim)

        self.gdb_output       = '/tmp/vimgdb.gdb'

