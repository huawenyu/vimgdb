"""."""

class Breakpoint(object):
    """Handle breakpoint signs."""

    def _parse_response(response, fname_sym):
        # Select lines in the current file with enabled breakpoints.
        pos_pattern = re.compile(r"([^:]+):(\d+)")
        enb_pattern = re.compile(r"\sy\s+0x")
        breaks = {}  # Dict[str, List[str]]
        for line in response.splitlines():
            try:
                if enb_pattern.search(line):  # Is enabled?
                    fields = re.split(r"\s+", line)
                    # file.cpp:line
                    match = pos_pattern.fullmatch(fields[-1])
                    if not match:
                        continue
                    is_end_match = fname_sym.endswith(match.group(1))
                    is_end_match_full_path = fname_sym.endswith(
                        os.path.realpath(match.group(1)))
                    if (match and
                            (is_end_match or is_end_match_full_path)):
                        line = match.group(2)
                        # If a breakpoint has multiple locations, GDB only
                        # allows to disable by the breakpoint number, not
                        # location number.  For instance, 1.4 -> 1
                        br_id = fields[0].split('.')[0]
                        try:
                            breaks[line].append(br_id)
                        except KeyError:
                            breaks[line] = [br_id]
            except IndexError:
                continue
            return breaks

    def __init__(self, common, proxy, impl):
        """ctor."""
        super().__init__(common)
        # Backend class to query breakpoints
        self.impl = impl
        # Discovered breakpoints so far: {file -> {line -> [id]}}
        self.breaks = {}    # : Dict[str, Dict[str, List[str]]]
        self.max_sign_id = 0

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

    def query(self, buf_num, fname):
        """Query actual breakpoints for the given file."""
        self.logger.info("Query breakpoints for %s", fname)
        self.breaks[fname] = self.impl.query(fname)
        self.clear_signs()
        self._set_signs(buf_num)

    def reset_signs(self):
        """Reset all known breakpoints and their signs."""
        self.breaks = {}
        self.clear_signs()

    def get_for_file(self, fname, line):
        """Get breakpoints for the given position in a file."""
        breaks = self.breaks.get(fname, {})
        return breaks.get("{line}", {})   # make sure the line is a string
