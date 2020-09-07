from vimgdb.base.common import Common


class Context(Common):
    def __init__(self, common: Common):
        super().__init__(common)
        self._name = ''
        self._outfile = ''
        self._state = None
        self._StateColl = {}

    def trans_to(self, state):
        #if self._state and self._state._name == state:
        #    self.logger.info("State '%s' trans_to itself.", state)
        #    return False
        #
        if state in self._StateColl:
            self._state = self._StateColl.get(state)
            #self.logger.debug("trans_to(%s) '%s' succ", state, self._state._name)
            return True
        else:
            self.logger.error("State '%s' not exist.", state)
        return False

    def request1(self):
        self._state.handle1()

    def request_cmd(self, cmdname, args):
        self.logger.info("%s.request_cmd: %s(args=%s)", self._name, cmdname, args)
        self._state.handle_cmd(cmdname, args)

    def parser_line(self, line):
        if self._state:
            #self.logger.debug("Ctx '%s' current State '%s'", self._name, self._state._name)
            self._state.handle_line(line)
        else:
            self.logger.error("%s.state is None: %s", self._name, line)
