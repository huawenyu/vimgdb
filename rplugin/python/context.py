import logger
from pprint import pformat

log = logger.GetLogger(__name__)

class Context(object):
    def __init__(self):
        self._name = ''
        self._outfile = ''
        self._state = None
        self._StateColl = {}

    def trans_to(self, state):
        #if self._state and self._state._name == state:
        #    log.info("VimGdb.context state '%s' trans_to itself.", state)
        #    return False
        #
        if self._StateColl.has_key(state):
            self._state = self._StateColl.get(state)
            return True
        else:
            log.error("VimGdb.context state '%s' not exist.", state)
        return False

    def request1(self):
        self._state.handle1()

    def request2(self):
        self._state.handle2()

    def parser_line(self, line):
        if self._state:
            log.info("Ctx '%s' dispatch to State '%s'", self._name, self._state._name)
            self._state.handle_line(line)
        else:
            log.error("VimGdb.context state is None: %s", line)
