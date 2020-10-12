import re
import os
import time
import subprocess
import threading

from vimgdb.base.common import Common
from vimgdb.base.data import BaseData


class GdbMode:
    LOCAL = 'local'
    REMOTE = 'remote'


class Controller(Common):

    pat_follow_file     = re.compile(r'^==> ([\w\d\._/]+) <==$')

    def __init__(self, common: Common, name: str):
        super().__init__(common)
        self._name = name
        self._outfile = ''
        self._state = None

        self.gdbMode = GdbMode.LOCAL
        self.gdbArgs = ''
        self.gdbserverPort = 444

        #self.models_coll: Dict[str, Model] = {}
        self.models_coll = {}
        self.views_coll = {}


    def handle_evts(self, data: BaseData):
        handled = False
        for modelName, model in self.models_coll.items():
            if data._name in model._evts:
                handled = True
                self.logger.info(f"dispatch {data._name} to model '{modelName}'")
                model.handle_evt(data)
        if not handled:
            self.logger.info(f"Can't handle {data._name}")


    def handle_acts(self, data: BaseData):
        handled = False
        for modelName, model in self.models_coll.items():
            if data._name in model._acts:
                handled = True
                self.logger.info(f"dispatch {data._name} to model '{modelName}'")
                model.handle_act(data)
        if not handled:
            self.logger.info(f"Can't handle {data._name}")


    def handle_cmds(self, args):
        handled = False
        self.logger.info(f"{args}")
        if len(args) < 2:
            self.logger.info("VimGdbSend('who', 'command'), but args=%s", args)
            return
        ctxname = args[0]
        vimArgs = args[1]
        # @todo: so far the command from vim just broadcast to all models
        if False and ctxname and ctxname in self.models_coll:
            model = self.models_coll.get(ctxname)
            if model:
                if type(vimArgs) is str:
                    handled = True
                    model.handle_cmd(vimArgs, args[1:])
                elif type(vimArgs) is list and len(vimArgs) > 0:
                    handled = True
                    model.handle_cmd(vimArgs[0], vimArgs)
                else:
                    self.logger.info("handle fail: args=%s", args)
                return
        else:
            for modelName, model in self.models_coll.items():
                if type(vimArgs) is str:
                    #self.logger.info(f"'{Common.json_out(model._cmds)}'")
                    if vimArgs in model._cmds:
                        handled = True
                        self.logger.info(f"dispatch to model '{modelName}'")
                        model.handle_cmd(vimArgs, args[1:])
                elif type(vimArgs) is list and len(vimArgs) > 0:
                    if vimArgs[0] in model._cmds:
                        handled = True
                        self.logger.info(f"dispatch to model '{modelName}'")
                        model.handle_cmd(vimArgs[0], vimArgs)

        if not handled:
            self.logger.info(f"Can't handle {args}")


    def handle_shows(self, data: BaseData):
        handled = False
        self.logger.info(f"{data._name}")
        for viewName, view in self.views_coll.items():
            handled = True
            self.logger.info(f"dispatch to view '{viewName}'")
            view.handle_show(data)
        if not handled:
            self.logger.info(f"Can't handle {data._name}")


    def parser_line(self, line):
        if self._state:
            #self.logger.debug("Ctx '%s' current State '%s'", self._name, self._state._name)
            self._state.handle_line(line)
        else:
            self.logger.error("%s.state is None: %s", self._name, line)


    def tail_files(self):
        try:
            self.logger.info(f"enter")
            files = []
            file2model = {}
            cur_model = None
            for modelName, model in self.models_coll.items():
                if not os.path.exists(f'{model._outfile}'):
                    os.system(f'touch {model._outfile}')
                files.append(model._outfile)
                file2model[model._outfile] = model
                cur_model = model

            if not files:
                self.logger.info(f"connect@Exit by no tail files")
                return

            command = "tail -F" + " ".join(files)
            self.logger.info(f"connect@ '{command}'")
            #p = subprocess.Popen(command.split(), stdout=subprocess.PIPE, universal_newlines=True)
            p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            #p = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, universal_newlines=True)
            for line in iter(p.stdout.readline, ""):
                if not os.path.exists(f'{Common.vimeventVimAlive}'):
                    self.logger.info(f"connect@Exit by check '{Common.vimeventVimAlive}'")
                    p.terminate()
                    break

                line = line.rstrip('\r\n')
                if len(line) == 0:
                    continue
                #self.logger.info(f"connect@'{line}'")
                res = self.pat_follow_file.match(line)
                if res:
                    if res.group(1) in file2model:
                        cur_model = file2model[res.group(1)]
                    else:
                        self.logger.error(f"connect@tail-file '{line}' have no model")
                else:
                    try:
                        cur_model.parser_line(line)
                    except Exception as e:
                        self.logger.error(f"exception: {str(e)}")
        except Exception as e:
            self.logger.error(f"thread exception: {str(e)}")



