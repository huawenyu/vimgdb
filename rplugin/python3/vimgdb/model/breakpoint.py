import re
import json
import os.path

from vimgdb.base.common import Common
from vimgdb.model.model import Model
from vimgdb.base.controller import Controller
from vimgdb.base.data import *

class Breakpoint(Model):
    """Handle breakpoint signs."""

    def __init__(self, common: Common, ctx: Controller):
        """ctor."""
        super().__init__(common, type(self).__name__)

        # Backend class to query breakpoints
        #self.impl = impl

        # Discovered breakpoints so far: {file -> {line -> [id]}}
        self.store = Store(common)
        self.breaks = {}    # : Dict[str, Dict[str, List[str]]]
        self._ctx = ctx
        self.max_sign_id = 0
        self._newadd_bp = None

        self._evts = {
                "evtRefreshBreakpt": self.evt_RefreshBreakpoint,
                }

        self._cmds = {
                "toggle":     self.cmd_toggle,
                }

        self._acts = {
                "actLoadBreak":     self.act_loadbreak,
                }


    def dump_bp(self, info: str, data: BaseData):
        assert isinstance(data, DataObjBreakpoint)
        self.logger.info(f"{info}: status={data.status} id={data.bp_id} {data.enable} file={data.fName}:{data.fLine}: cmdstr='{data.cmdstr}'")
        self.logger.info(f"        in-function '{data.funcName}' sign={data.vim_signid} {data.vim_bufnr}:{data.vim_line}")


    def dump_vimqf(self, viewBp: BaseData, fVimqf):
        assert isinstance(viewBp, DataObjBreakpoint)
        if viewBp.cmdstr.endswith(viewBp.funcName):
            fVimqf.write(f"#{viewBp.bp_id}  0xFFFF in {'[o]' if viewBp.enable else '[x]'}{viewBp.cmdstr} () at {viewBp.fName}:{viewBp.fLine}\n")
        else:
            fVimqf.write(f"#{viewBp.bp_id}  0xFFFF in {'[o]' if viewBp.enable else '[x]'}{viewBp.cmdstr}@{viewBp.funcName} () at {viewBp.fName}:{viewBp.fLine}\n")


    def evt_RefreshBreakpoint(self, data: BaseData):
        self.logger.info(f"{data._name}")
        with open(Common.gdb_tmp_break) as f:
            content = f.readlines()
            # you may also want to remove whitespace characters like `\n` at the end of each line
            #content = [x.strip() for x in content]

            breaks = self._parse_response(content, '')
            self._ctx.handle_shows(DataAction("viewClearAllBreak"))
            if not breaks:
                self.logger.info(f"{data._name} parse the file 'info break': No breakpoints")
                self.store.deleteAll()
                with open(Common.vimqf_breakpoint, "w") as fVimqf:
                    self.dump_vimqf(DataObjBreakpoint.CreateDummy(), fVimqf)
                self.store.Save()
                self._ctx.handle_shows(viewBp.action("viewUpdateBp"))
                return


            # update the new added bp
            # oldBp = self.store.findById(str(aBp.bp_id))
            if self._newadd_bp and self._newadd_bp.status == DataObjBreakpoint.status_adding:
                for aBp in breaks:
                    if not self.store.checkExistById(str(aBp.bp_id)):
                        self._newadd_bp.update(aBp)
                        self.store.addBreakpoint(self._newadd_bp)
                        self._newadd_bp = None
                        break

            # w write+truncate, a write+append
            with open(Common.vimqf_breakpoint, "w") as fVimqf:
                for aBp in breaks[::-1]:
                    viewBp = self.store.update(aBp)
                    self.dump_vimqf(viewBp, fVimqf)
                    self._ctx.handle_shows(viewBp.action("viewSignBreak"))
            self._ctx.handle_shows(viewBp.action("viewUpdateBp"))
            self.store.Save()


    def cmd_toggle(self, args):
        self.logger.info(f"{args}")
        cmdstr        = str(args[1])
        bpType        = args[2]    # 0 line, 1 func, 10 new-reload-break
        bpId          = args[3]
        bpContextline = args[4]

        # breakpoint by manually
        if bpType < 10:
            aBreakpoint = self.store.findByCmdStr(cmdstr)
            if aBreakpoint:
                self.dump_bp("found", aBreakpoint)
                self.cook_breakpoint(aBreakpoint)
            else:
                self._newadd_bp = DataObjBreakpoint.CreateByCmdstr(cmdstr)
                self.cook_breakpoint(self._newadd_bp)
                return
        else: # initilize reload breakponts
                self._newadd_bp = DataObjBreakpoint.CreateById2(bpId, cmdstr, bpContextline)
                self.store.addBreakpoint(self._newadd_bp)
                self.cook_breakpoint(self._newadd_bp)
                self._newadd_bp = None


    def cook_breakpoint(self, bp: DataObjBreakpoint):
        if bp.status == DataObjBreakpoint.status_init:
            bp.status = DataObjBreakpoint.status_adding
            self._ctx.handle_acts(bp.action("actAddBreak"))
        elif bp.status == DataObjBreakpoint.status_enable:
            self._ctx.handle_acts(bp.action("actDisableBreak"))
        elif bp.status == DataObjBreakpoint.status_disable:
            self._ctx.handle_acts(bp.action("actDeleteBreak"))
            self.store.delete(bp)


    def _parse_response(self, response, fname_sym):
        """ Parse gdb 'info br' file:
            Select lines in the current file with enabled breakpoints.
        """
        #self.logger.debug(f"Info break: {response}")
        pos_pattern = re.compile(r"^\d.*breakpoint.*keep.* in (\w+) at ([^:]+):(\d+)")
        #enb_pattern = re.compile(r"\sy\s+0x")
        breaks = []
        for line in response:
            try:
                #if enb_pattern.search(line):  # Is enabled?
                if True:
                    fields = re.split(r"\s+", line)
                    # file.cpp:line
                    #self.logger.debug(f"match: ", fields[-1])
                    #match = pos_pattern.fullmatch(fields[-1])

                    match = pos_pattern.match(line)
                    #self.logger.debug(f"try match: {line}")
                    if not match:
                        continue

                    # Choose breakpoint for current filename
                    if fname_sym:
                        is_end_match = fname_sym.endswith(match.group(2))
                        is_end_match_full_path = fname_sym.endswith(
                            os.path.realpath(match.group(2)))
                    else:
                        is_end_match = True

                    if (match and
                            (is_end_match or is_end_match_full_path)):
                        fLine = match.group(3)
                        #fNameLine = match.group(0)
                        fName = match.group(2)
                        funcName = match.group(1)
                        enable = fields[3]

                        # If a breakpoint has multiple locations, GDB only
                        # allows to disable by the breakpoint number, not
                        # location number.  For instance, 1.4 -> 1
                        br_id = fields[0].split('.')[0]

                        breaks.append(DataObjBreakpoint.Create(fName, fLine, fName+":"+fLine, br_id, enable, funcName))
            except Exception as e:
                self.logger.error(f"exception: {str(e)}")
        # end-for
        return breaks

    def clear_signs(self):
        """Clear all breakpoint signs."""
        for i in range(5000, self.max_sign_id + 1):
            self.vim.call('sign_unplace', 'vimgdb', {'id': i})
        self.max_sign_id = 0


    def _set_signs(self, buf):
        if buf != -1:
            sign_id = 5000 - 1
            # Breakpoints need full path to the buffer (at least in lldb)
            bpath = self.vim.call("expand", "#{buf}:p")

            def _get_sign_name(count):
                max_count = len(self.config.get('sign_breakpoint'))
                idx = count if count < max_count else max_count - 1
                return "GdbBreakpoint{idx}"

            for line, ids in self.breaks.get(bpath, {}).items():
                sign_id += 1
                sign_name = _get_sign_name(len(ids))
                self.vim.call('sign_place', sign_id, 'vimgdb', sign_name, buf,
                              {'lnum': line, 'priority': 10})
            self.max_sign_id = sign_id


    def handle_evt(self, data: BaseData):
        if data._name in self._evts:
            self._evts[data._name](data)


    def handle_cmd(self, cmdname, args):
        if cmdname in self._cmds:
            self._cmds[cmdname](args)
        else:
            self.logger.info(f"ignore {cmdname}")


    def handle_act(self, data: BaseData):
        if data._name in self._acts:
            self._acts[data._name](data)
        else:
            self.logger.info(f"ignore {data._name}")


    def act_loadbreak(self, data: BaseData):
        if not self.store.Load():
            self.logger.info(f"Empty breakpoints!")
            return
        self.store.bpointsById = {}
        for aBp in self.store.bpointsByCmdStr.values():
            self._newadd_bp = aBp
            aBp.status = DataObjBreakpoint.status_init
            cook_breakpoint(aBp)


class Store(Common):

    def __init__(self, common: Common):
        super().__init__(common)
        self.breakpoints = {}
        self.bpointsById = {}
        self.bpointsByCmdStr = {}

        self.bp_ids = {}
        self.bp_idfiles = {}
        self.api = None

    @staticmethod
    def serialize(obj):
        """JSON serializer for objects not serializable by default json code"""

        if isinstance(obj, date):
            serial = obj.isoformat()
            return serial

        if isinstance(obj, time):
            serial = obj.isoformat()
            return serial

        return obj.__dict__


    def Save(self):
        # Writing JSON data
        with open(Common.gdb_file_bp_fromctrl, 'w') as outfile:
            json.dump(self.bpointsByCmdStr, outfile, default=lambda o: o.__dict__, indent=4)


    def Load(self):
        try:
            if not os.path.isfile(Common.gdb_file_bp_fromctrl):
                return False
            with open(Common.gdb_file_bp_fromctrl, 'r') as f:
                self.bpointsByCmdStr = json.loads(f.read())
                return True
        except Exception as e:
            self.logger.error(f"exception: {str(e)}")


    @staticmethod
    def LoadBreakpionts(obj):
        json_obj = None
        try:
            if not os.path.isfile(Common.gdb_file_bp_fromctrl):
                obj.logger.debug(f"Load json fail: no file '{Common.gdb_file_bp_fromctrl}'")
                return None
            with open(Common.gdb_file_bp_fromctrl, 'r') as f:
                json_obj = json.loads(f.read())
                #obj.logger.debug(f"Load json: {json_obj}")
                return
        finally:
            return json_obj


    def findByCmdStr(self, cmdstr: str):
        if cmdstr in self.bpointsByCmdStr:
            return self.bpointsByCmdStr.get(cmdstr)
        return None

    def findById(self, bp_id: str):
        if bp_id in self.bpointsById:
            return self.bpointsById.get(bp_id)
        return None

    def checkExistByCmdStr(self, cmdstr: str):
        if cmdstr in self.bpointsByCmdStr:
            return True
        return False

    def checkExistById(self, bp_id: str):
        if bp_id in self.bpointsById:
            return True
        return False


    def delete(self, bp):
        del self.bpointsById[bp.bp_id]
        del self.bpointsByCmdStr[bp.cmdstr]

    def deleteAll(self):
        self.bpointsById = {}
        self.bpointsByCmdStr = {}

    def update(self, newBp):
        oldBp = self.findById(newBp.bp_id)
        if oldBp:
            oldBp.update(newBp)
            return oldBp
        else:
            return self.addBreakpoint(newBp)

    def addBreakpoint(self, newBp: DataObjBreakpoint):
        if not newBp.cmdstr:
            self.logger.info(f"Can't add breakpoint without cmdstr: {newBp} ")
            return False
        self.bpointsByCmdStr.update({newBp.cmdstr: newBp})
        self.bpointsById.update({newBp.bp_id: newBp})
        return newBp

