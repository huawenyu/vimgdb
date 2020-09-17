
def _parse_response(response, fname_sym):
    """ Parse gdb 'info br' file:
        Select lines in the current file with enabled breakpoints.
    """
    pos_pattern = re.compile(r"([^:]+):(\d+)")
    enb_pattern = re.compile(r"\sy\s+0x")
    breaks = {}  # Dict[str, List[str]]
    for line in response.splitlines():
        try:
            #if enb_pattern.search(line):  # Is enabled?
            if True:
                fields = re.split(r"\s+", line)
                # file.cpp:line
                match = pos_pattern.fullmatch(fields[-1])
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

if __name__ == "__main__":
    print("Hello world")
