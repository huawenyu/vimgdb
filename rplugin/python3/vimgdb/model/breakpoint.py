import re
import json

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

        self._evts = {
                "evtRefreshBreakpt": self.evt_RefreshBreakpoint,
                }

        self._cmds = {
                "toggle":     self.cmd_toggle,
                }

        self._vim_set_bp = None


    def dump_bp(self, info: str, data: BaseData):
        self.logger.info(f"{info}: status={data.status} id={data.bp_id} {data.enable} file={data.fName}:{data.fLine}: cmdstr='{data.cmdstr}'")
        self.logger.info(f"        sign={data.vim_signid} {data.vim_bufnr}:{data.vim_line}")

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
                return


            # update the new added bp
            if self._vim_set_bp and self._vim_set_bp.status == DataObjBreakpoint.status_adding:
                for aBp in breaks:
                    if not self.store.checkExistById(str(aBp.bp_id)):
                        self._vim_set_bp.update(aBp)
                        self.store.addBreakpoint(self._vim_set_bp)
                        self._vim_set_bp = None
                        break

            for aBp in breaks:
                viewBp = self.store.update(aBp)
                self._ctx.handle_shows(viewBp.action("viewSignBreak"))


    def cmd_toggle(self, args):
        self.logger.info(f"{args}")
        cmdstr = str(args[1])
        aBreakpoint = self.store.findByCmdStr(cmdstr)
        if aBreakpoint:
            self.dump_bp("found", aBreakpoint)
            self.proc_breakpoint(aBreakpoint)
        else:
            self._vim_set_bp = DataObjBreakpoint.CreateByCmdstr(cmdstr)
            self.proc_breakpoint(self._vim_set_bp)
            return


    def proc_breakpoint(self, bp: DataObjBreakpoint):
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
        pos_pattern = re.compile(r"^\d.*breakpoint.*keep.*in.* at ([^:]+):(\d+)")
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
                        is_end_match = fname_sym.endswith(match.group(1))
                        is_end_match_full_path = fname_sym.endswith(
                            os.path.realpath(match.group(1)))
                    else:
                        is_end_match = True

                    if (match and
                            (is_end_match or is_end_match_full_path)):
                        fLine = match.group(2)
                        #fNameLine = match.group(0)
                        fName = match.group(1)
                        enable = fields[3]

                        # If a breakpoint has multiple locations, GDB only
                        # allows to disable by the breakpoint number, not
                        # location number.  For instance, 1.4 -> 1
                        br_id = fields[0].split('.')[0]

                        breaks.append(DataObjBreakpoint.Create(fName, fLine, fName+":"+fLine, br_id, enable))
            except:
                self.logger.info("exception: '%s'", sys.exc_info()[0])
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
        self.logger.info(f"{data}")



class Store(Common):

    def __init__(self, common: Common):
        super().__init__(common)
        self.breakpoints = {}
        self.bpointsById = {}
        self.bpointsByCmdStr = {}

        self.bp_ids = {}
        self.bp_idfiles = {}
        self.api = None


    def Save(self):
        # Writing JSON data
        save_dict = {
                'ById': self.bpointsById,
                'ByCmdstr': self.bpointsByCmdStr,
                }
        with open(Common.gdb_file_bp_fromctrl, 'w') as f:
            json.dump(save_dict, f)


    def Load(self):
        with open(filename, 'r') as f:
            save_dict = json.load(f)
            if 'ById' in save_dict:
                self.bpointsById = save_dict.get('ById')
            if 'ByCmdstr' in save_dict:
                self.bpointsByCmdStr = save_dict.get('ByCmdstr')


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

