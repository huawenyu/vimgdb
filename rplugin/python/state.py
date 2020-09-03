#from abc import ABC, abstractmethod

import re
import importlib

import logger

log = logger.GetLogger(__name__)

class State(object):
    #pattern = re.compile(r"cookie")
    #sequence = "Cake and cookie"
    #pattern.search(sequence).group()

    # gdb {{{2
    pat_dummy             = re.compile(r"^dummy ")
    pat_gdb_leave          = re.compile(r'^neobugger_leave')
    pat_gdb_local_start          = re.compile(r'^neobugger_local_start')

    pat_prompt            = re.compile(r'\x1a\x1a\x1a$')
    pat_shell_prompt      = re.compile(r"^newRuntime ")

    pat_gdb_prompt1       = re.compile(r"^\(gdb\) ")
    pat_gdb_prompt2       = re.compile(r"^\(Pdb\) ")

    pat_continue          = re.compile(r'^Continuing\.')
    pat_breatpoint        = re.compile(r'^Breakpoint \d+')
    pat_tempbreatpoint        = re.compile(r'^Temporary breakpoint \d+')



    pat_inner_err = re.compile(r"\[Inferior\ +.{-}\ +exited\ +normally")

    pat_remote_err        = re.compile(r'^Remote communication error\.  Target disconnected\.:')
    pat_remote_close        = re.compile(r'^Remote connection closed\.')

    pat_no_prog_run        = re.compile(r'^The program is not being run\.')

    # "127.0.0.1:9999: Connection refused.",
    # "dut:9999: Connection refused.",
    pat_remote_con_fail        = re.compile(r'^\d+\.\d+\.\d+\.\d+:\d+: Connection refused\.')
    pat_remote_con_fail2        = re.compile(r'^\w+:\d+: Connection refused\.')



    # file {{{2
    # '[\o32]{2}([^:]+):(\d+):\d+',
    # '/([\h\d/]+):(\d+):\d+',
    # '^#\d+ .{-} \(\) at (.+):(\d+)',
    # ' at /([\h\d/]+):(\d+)',
    # '^\> ([\/\-\_\.a-zA-Z0-9]+)\((\d+)\)',
    # "/home/user/tmp/t1.c:35:414:beg:0x4011c1",
    pat_jumpfile          = re.compile(r'(^/[\w\d\._/]+):(\d+)')
    pat_jumpfile2          = re.compile(r'[\r\n]\x1a\x1a([^:]+):(\d+):\d+')
    # "> /home/user/tmp/client1.py(1)<module>()",
    pat_jumpfile3          = re.compile(r'^> /([\w\d\._/]+):\((\d+)\)')


    # helper {{{2
    # "$3 = (int *) 0x7fffffffd93c",
    pat_print          = re.compile(r'^\$\d+ .* 0x(.*)')
    pat_whatis        = re.compile(r'^type \= (\p+)')


    # gdbserver {{{2
    pat_server_listen        = re.compile(r'^Listening on port (\d+)')
    pat_server_detach        = re.compile(r'^Detaching from process \d+')
    pat_server_remote_from        = re.compile(r'^Remote debugging from host \d+\.\d+\.\d+\.\d+:\d+')

    # "127.0.0.1:444: Connection timed out.",
    # "dut:444: Connection timed out.",
    pat_remote_con_timeout        = re.compile(r'^\d+\.\d+\.\d+\.\d+:\d+:\d+: Connection timed out\.')
    pat_remote_con_timeout2        = re.compile(r'^\w+:\d+: Connection timed out\.')

    pat_remote_con_succ = re.compile(r"^Remote debugging using \d+\.\d+\.\d+\.\d+:\d+")
    pat_remote_con_succ2        = re.compile(r'^Remote debugging using \w+:\d+')


    def __init__(self, context, name):
        self._name = name
        self._context = context
        self._patts = []

    def on_dummy(self):
        pass

    #@abstractmethod
    def handle1(self):
        pass

    #@abstractmethod
    def handle2(self):
        pass

    def handle_line(self, line):
        log.info("State '%s' handle '%s'", self._context._state._name, line)
        for aPattern in self._patts:
            if aPattern.rePatt.match(line):
                log.info("  matched '%s' ", aPattern.hint)
                aPattern.actionCb(aPattern)
                if len(aPattern.nextState) > 0:
                    if self._context.trans_to(aPattern.nextState):
                        log.info("    ==> State '%s'", self._context._state._name)
                break
        return

