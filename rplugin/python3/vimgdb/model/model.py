import threading
import time
import sys
import os.path
#from typing import Dict, Tuple, Sequence
from typing import Dict, List
from abc import ABC, abstractmethod

from vimgdb.base.data import BaseData
from vimgdb.base.common import Common
from vimgdb.model.state import State

class Model(Common, ABC):

    def __init__(self, common: Common, name: str, outfile: str=""):
        Common.__init__(self, common)
        self._name = name
        self._outfile = outfile
        self._state: State = None
        self._StateColl: Dict[str, State] = {}

        self._evts = {}  # event fire by gdb/gdbserver shell output
        self._cmds = {}  # command send from vim-user
        self._acts = {}  # process the events/commands, then take action


    def trans_to(self, state: str, hint: str):
        if state in self._StateColl:
            o_state = ''
            if self._state:
                o_state = self._state._name
            self._state = self._StateColl.get(state)
            if o_state != state:
                self.logger.info(f"'{o_state}' -> '{state}': {hint}")
            return True
        else:
            self.logger.error("State '%s' not exist.", state)
        return False


    @abstractmethod
    def handle_evt(self, data: BaseData):
        pass


    @abstractmethod
    def handle_cmd(self, cmdname, args):
        pass


    @abstractmethod
    def handle_act(self, data: BaseData):
        pass


    def tail_file(self, name, afile, thefile):
        '''generator function that yields new lines in a file
        '''
        self.logger.info("Model '%s' tail-file '%s'", name, afile)
        thefile.seek(0, os.SEEK_END)  # Go to the end of the file

        # start infinite loop
        line = ''
        while True:
            #self.logger.info("Controller '%s' tail-file '%s' before", name, afile)
            if os.path.exists(f'{Common.vimeventVimLeave}'):
                break

            part = thefile.readline()
            #self.logger.info("Controller '%s' tail-file '%s' after with: '%s'", name, afile, line)
            if not part:
                time.sleep(0.1)  # Sleep briefly
                continue

            line += part
            if not part.endswith('\n'):
                continue
            line = line.rstrip('\r\n')
            if len(line) == 0:
                continue
            yield line
            line = ''


    def parser_file(self):
        try:
            thefile = open(self._outfile, 'r')
            thelines = self.tail_file(self._name, self._outfile, thefile)
            for line in thelines:
                if os.path.exists(f'{Common.vimeventVimLeave}'):
                    break
                try:
                    if self._state:
                        self.logger.info(f"connect@{self._state._name}@ '{line}'")
                        self._state.handle_line(line)
                    else:
                        self.logger.error(f"state is None: {line}")
                except AttributeError as error:
                    self.logger.error(f"  parser error: '{error}'", )
                except Exception as exception:
                    self.logger.error(f"  parser exception: '{exception}'", )
                except Exception as e:
                    self.logger.error(f"exception other: {str(e)}")
        except Exception as e:
            self.logger.error(f"exception: {str(e)}")


    def run_parser(self, state: str):
        try:
            if not self._outfile:
                self.logger.info(f"Starting {self._name} thread don't need: no monitor file")
                return
            self.logger.info(f"Starting {self._name} thread@{state} monitor file {self._outfile}")
            self.trans_to(state, "ParserInit")

            t1 = threading.Thread(target=self.parser_file)
            t1.start()
            #t1.join()
        except Exception as e:
            self.logger.error(f"thread exception: {str(e)}")

