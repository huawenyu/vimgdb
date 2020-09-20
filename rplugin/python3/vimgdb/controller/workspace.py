# -*- coding: utf-8 -*-
"""Create a tmux workspace from a configuration :py:obj:`dict`.
Ref: [tmuxp.workspacebuilder](https://github.com/tmux-python/tmuxp)
"""
import re
import json
import subprocess

from libtmux.exc import TmuxSessionExists
from libtmux.pane import Pane
from libtmux.server import Server
from libtmux.session import Session
from libtmux.window import Window

from vimgdb.base.common import Common

class Workspace(Common):

    def __init__(self, common: Common, sconf, server=None, win_width=800, win_height=600):
        super().__init__(common)

        if not sconf:
            raise Exception('Layout configuration is empty.')

        # config.validate_schema(sconf)

        if isinstance(server, Server):
            self.server = server
        else:
            self.server = None

        self.sconf = sconf
        self.win_width = int(win_width)
        self.win_height = int(win_height)
        self.layouts = {}

    def session_exists(self, session_name=None):
        exists = self.server.has_session(session_name)
        if not exists:
            return exists

        self.session = self.server.find_where({'session_name': session_name})
        return True

    def buildlayout(self, sessName: str):
        session = self.server.find_where({ "session_name": f"{sessName}" })
        if session:
            session.kill_session()
            session = None
        self.build()

        # 2: layout2* (3 panes) [800x600] [layout 9102,800x600,0,0[800x300,0,0,217,800x149,0,301,218,800x149,0,451,219]] @113 (active)
        winInfo = subprocess.check_output(
            ['tmux', 'lsw', '-t', Common.tmux_session_layout])
        winInfo = winInfo.decode()
        for win_line in winInfo.split("\n"):
            m = re.search(r'\d+: (\w+).*panes.* \[(.*)x(.*)\] \[layout (.*)\]', win_line)
            if m:
                self.logger.info(f"connect window: {m.groups()}")
                layoutName = m.group(1)
                #self.win_width = m.group(2)
                #self.win_height = m.group(3)
                layoutCode = m.group(4)
                if layoutName in self.layouts:
                    self.layouts[layoutName].update({'layout': layoutCode})

        self.session.kill_session()
        return self.layouts

    def build(self, session=None):
        #self.logger.info(f"connect layouts: {self.sconf}")
        if not session:
            if not self.server:
                raise Exception(
                    'Layout.build requires server to be passed '
                    + 'on initialization, or pass in session object to here.'
                )

            if self.server.has_session(self.sconf['session_name']):
                self.session = self.server.find_where(
                    {'session_name': self.sconf['session_name']}
                )
                raise Exception(
                    'Session name %s is already running.' % self.sconf['session_name']
                )
            else:
                session = self.server.new_session(
                    session_name=self.sconf['session_name']
                )

            assert self.sconf['session_name'] == session.name
            assert len(self.sconf['session_name']) > 0

        self.session = session
        self.server = session.server

        self.server._list_sessions()
        assert self.server.has_session(session.name)
        assert session.id
        assert isinstance(session, Session)

        focus = None

        tmux_info = subprocess.check_output(
            ['tmux', 'display-message', '-t', session.name, '-p', '#{window_width};#{window_height}'])
        tmux_info = tmux_info.decode()
        [win_width, win_height] = tmux_info.strip().split(';')
        self.win_width = int(win_width)
        self.win_height = int(win_height)

        if 'options' in self.sconf:
            for option, value in self.sconf['options'].items():
                self.session.set_option(option, value)
                pass
        if 'global_options' in self.sconf:
            for option, value in self.sconf['global_options'].items():
                self.session.set_option(option, value, _global=True)
        if 'environment' in self.sconf:
            for option, value in self.sconf['environment'].items():
                self.session.set_environment(option, value)

        for winName, win, wconf in self.iter_create_windows(session):
            self.create_panes(winName, win, wconf)

        if focus:
            focus.select_window()

    def create_panes(self, winName, win: Window, wconf):
        assert isinstance(win, Window)

        focus_pane = None
        for p, pconf in self.iter_create_panes(winName, win, wconf):
            assert isinstance(p, Pane)
            p = p

            if 'layout' in wconf:
                win.select_layout(wconf['layout'])

            if 'focus' in pconf and pconf['focus']:
                focus_pane = p

        if 'focus' in wconf and wconf['focus']:
            focus = win

        self.config_after_window(win, wconf)

        if focus_pane:
            focus_pane.select_pane()

    def iter_create_windows(self, ses: Session):
        for i, wconf in enumerate(self.sconf['windows'], start=1):
            if 'window_name' not in wconf:
                window_name = 'Null'
            else:
                window_name = wconf['window_name']
            self.layouts[window_name] = {}

            w1 = None
            if i == int(1):  # if first window, use window 1
                w1 = ses.attached_window
                w1.move_window(99)
                pass

            if 'start_directory' in wconf:
                sd = wconf['start_directory']
            else:
                sd = None

            if 'window_shell' in wconf:
                ws = wconf['window_shell']
            else:
                ws = None

            win = ses.new_window(
                window_name=window_name,
                start_directory=sd,
                attach=False,  # do not move to the new window
                window_index=wconf.get('window_index', ''),
                window_shell=ws,
            )

            if i == int(1) and w1:  # if first window, use window 1
                w1.kill_window()
            assert isinstance(win, Window)
            ses.server._update_windows()
            if 'options' in wconf and isinstance(wconf['options'], dict):
                for option, value in wconf['options'].items():
                    if isinstance(value, str):
                        #  "70%"
                        if value.endswith('%'):
                            if option.endswith('-width'):
                                value = int(self.win_width * int(value.strip('%')) / 100)
                                self.logger.info(f"connect set-width {self.win_width}-{value}")
                            if option.endswith('-height'):
                                value = int(self.win_height * int(value.strip('%')) / 100)
                                self.logger.info(f"connect set-height {self.win_height}-{value}")
                        elif value.startswith('0.'):
                            if option.endswith('-width'):
                                value = int(self.win_width * float(value))
                                self.logger.info(f"connect set-width {self.win_width}-{value}")
                            if option.endswith('-height'):
                                value = int(self.win_height * float(value))
                                self.logger.info(f"connect set-height {self.win_height}-{value}")
                    if isinstance(value, float) and value < 1:
                        if option.endswith('-width'):
                            value = int(self.win_width * value)
                            self.logger.info(f"connect set-width {self.win_width}-{value}")
                        if option.endswith('-height'):
                            value = int(self.win_height * value)
                            self.logger.info(f"connect set-height {self.win_height}-{value}")

                    win.set_window_option(option, value)

            if 'focus' in wconf and wconf['focus']:
                win.select_window()

            ses.server._update_windows()

            yield window_name, win, wconf

    def iter_create_panes(self, winName, w: Window, wconf):
        assert isinstance(w, Window)
        pane_base_index = int(w.show_window_option('pane-base-index', g=True))

        p = None

        for pindex, pconf in enumerate(wconf['panes'], start=pane_base_index):
            if pindex == int(pane_base_index):
                p = w.attached_pane
            else:

                def get_pane_start_directory():

                    if 'start_directory' in pconf:
                        return pconf['start_directory']
                    elif 'start_directory' in wconf:
                        return wconf['start_directory']
                    else:
                        return None

                p = w.split_window(
                    attach=True, start_directory=get_pane_start_directory(), target=p.id
                )

            assert isinstance(p, Pane)
            if 'layout' in wconf:
                w.select_layout(wconf['layout'])

            if 'suppress_history' in pconf:
                suppress = pconf['suppress_history']
            elif 'suppress_history' in wconf:
                suppress = wconf['suppress_history']
            else:
                suppress = True

            # recursive diction/list in json
            try:
                #self.logger.info(f"connect Panes: {pconf}")
                if isinstance(pconf, str):
                    #decoded_data=pconf.encode().decode('utf-8-sig')
                    pconf1 = json.loads(pconf, strict=False)
            except Exception as e:
                self.logger.info(f"connect Panes: {str(e)}")

            for cmd in pconf['shell_command']:
                p.send_keys(cmd, suppress_history=suppress)

            if 'pane_name' in pconf:
                if winName in self.layouts:
                    view = pconf['pane_name']
                    self.layouts[winName].update({view: True})
            if 'focus' in pconf and pconf['focus']:
                w.select_pane(p['pane_id'])

            w.server._update_panes()

            yield p, pconf

    def config_after_window(self, w, wconf):
        if 'options_after' in wconf and isinstance(wconf['options_after'], dict):
            for key, val in wconf['options_after'].items():
                w.set_window_option(key, val)

    @staticmethod
    def Save(session):
        sconf = {'session_name': session['session_name'], 'windows': []}

        for w in session.windows:
            wconf = {
                'options': w.show_window_options(),
                'window_name': w.name,
                'layout': w.layout,
                'panes': [],
            }
            if w.get('window_active', '0') == '1':
                wconf['focus'] = 'true'

            # If all panes have same path, set 'start_directory' instead
            # of using 'cd' shell commands.
            def pane_has_same_path(p):
                return w.panes[0].current_path == p.current_path

            if all(pane_has_same_path(p) for p in w.panes):
                wconf['start_directory'] = w.panes[0].current_path

            for p in w.panes:
                pconf = {'shell_command': []}

                if 'start_directory' not in wconf:
                    pconf['shell_command'].append('cd ' + p.current_path)

                if p.get('pane_active', '0') == '1':
                    pconf['focus'] = 'true'

                current_cmd = p.current_command

                def filter_interpretters_and_shells():
                    return current_cmd.startswith('-') or any(
                        current_cmd.endswith(cmd) for cmd in ['python', 'ruby', 'node']
                    )

                if filter_interpretters_and_shells():
                    current_cmd = None

                if current_cmd:
                    pconf['shell_command'].append(current_cmd)
                else:
                    if not len(pconf['shell_command']):
                        pconf = 'pane'

                wconf['panes'].append(pconf)
            sconf['windows'].append(wconf)
        return sconf
