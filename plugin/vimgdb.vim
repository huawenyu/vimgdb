if exists('g:loaded_vim_gdb') || !has("nvim") || &compatible
    finish
endif
let g:loaded_vim_gdb = 1

if !exists("s:init")
    let s:init = 1
    let s:module = "vimgdb"
    silent! let s:log = logger#getLogger(expand('<sfile>:t'))

    sign define GdbBreakpointEn  text=● texthl=Search
    sign define GdbBreakpointDis text=● texthl=Function
    sign define GdbBreakpointDel text=● texthl=Comment

    sign define GdbCurrentLine   text=☛ texthl=Error
    "sign define GdbCurrentLine text=▶ texthl=Error
    "sign define GdbCurrentLine text=☛ texthl=Keyword
    "sign define GdbCurrentLine text=⇒ texthl=String

    set errorformat+=#%c\ \ %.%#\ in\ %m\ \(%.%#\)\ at\ %f:%l
    set errorformat+=#%c\ \ %.%#\ in\ \ \ \ %m\ \ \ \ at\ %f:%l
    set errorformat+=#%c\ \ %m\ \(%.%#\)\ at\ %f:%l

    let s:dir = expand('<sfile>:p:h')
    let s:gdb_port = 7778
    let s:breakpoint_signid_start = 5000
    let s:breakpoint_signid_max = 0

    let s:breakpoints = {}
    let s:toggle_all = 0
    let s:gdb_bt_qf = '/tmp/vimgdb.bt'
    let s:gdb_break_qf = '/tmp/vimgdb.break'
    let s:brk_file = './.gdb.break'
    let s:fl_file = './.gdb.file'
    let s:file_list = {}

    let s:_initialized = 0
    let s:_opened = 0
    let s:const_bash = "cat ~/.bashrc > /tmp/tmp.bashrc; 
          \ echo \"PS1='newRuntime $ '\" >> /tmp/tmp.bashrc; 
          \ echo \"+o emacs\" >> /tmp/tmp.bashrc; 
          \ echo \"+o vi\" >> /tmp/tmp.bashrc; 
          \ bash --noediting --rcfile /tmp/tmp.bashrc 
          \"
    " 0 nothing, 1 smart-eval, 2 wait watch
    let s:eval_mode = 0
endif


let s:prototype = {}
let s:this = s:prototype
let s:this.debug_mode = 0        | " debug_mode: 0 local, 1 connect server, 2 attach pid
let s:this.debug_bin  = 't1'
let s:this.debug_server = ["127.0.0.1", "9999"]
let s:this.debug_args = {}

let s:this._wid_main = 0
let s:this._show_backtrace = 1
let s:this._show_breakpoint = 1
let s:this._server_exited = 0
let s:this._reconnect = 0
let s:this._has_breakpoints = 0


" @mode 0 refresh-all, 1 only-change
function! s:prototype.RefreshBreakpointSigns(mode)
    if a:mode == 0
        let i = s:breakpoint_signid_start
        while i <= s:breakpoint_signid_max
            exe 'sign unplace '.i
            let i += 1
        endwhile
    endif

    let s:breakpoint_signid_max = 0
    let id = s:breakpoint_signid_start
    for [next_key, next_val] in items(s:breakpoints)
        let buf = bufnr(next_val['file'])
        let linenr = next_val['line']

        if buf < 0
            continue
        endif

        if a:mode == 1 && next_val['change']
           \ && has_key(next_val, 'sign_id')
            exe 'sign unplace '. next_val['sign_id']
        endif

        if a:mode == 0 || (a:mode == 1 && next_val['change'])
            if next_val['state']
                exe 'sign place '.id.' name=GdbBreakpointEn line='.linenr.' buffer='.buf
            else
                exe 'sign place '.id.' name=GdbBreakpointDis line='.linenr.' buffer='.buf
            endif
            let next_val['sign_id'] = id
            let s:breakpoint_signid_max = id
            let id += 1
        endif
    endfor
endfunction


function! s:prototype.Kill()
    call self.Map('client', "unmap")
    call self.Update_current_line_sign(0)

    if self.debug_mode == 0
        call new#util#post('client', "quit\n")
    elseif self.debug_mode == 1
        call new#util#post('client', "monitor exit\n")
    endif
endfunction


function! s:prototype.Send(data)
    "let l:__func__ = s:module. ":Send()"
    if exists("g:vimgdb_gdb")
        call VimGdbSend(g:vimgdb_gdb, a:data)
    endif
endfunction


function! s:prototype.Post(data)
    let state = new#state#CurrState('client')
    call self._Send(state, a:data, 1)
endfunction


function! s:prototype._Send(state, data, async)
    let l:stateName = new#state#GetStateNameByState(a:state)
    if l:stateName ==# "pause" || l:stateName ==# "init" || l:stateName ==# "start"
        if a:async
            call new#util#post('client', a:data."\<cr>")
        else
            call new#util#send('client', a:data."\<cr>")
        endif
    else
        let l:__func__ = s:module. ":Send()"
        silent! call s:log.error(l:__func__, ": Cann't send data when state=[", l:stateName, "]")
    endif
endfunction


function! s:prototype.Attach()
    call new#util#post('client', "target remote ". join(self.debug_server, ":"). "\n")
endfunction


function! s:prototype.Update_current_line_sign(add)
    " to avoid flicker when removing/adding the sign column(due to the change in
    " line width), we switch ids for the line sign and only remove the old line
    " sign after marking the new one
    let old_line_sign_id = get(self, '_line_sign_id', 4999)
    let self._line_sign_id = old_line_sign_id == 4999 ? 4998 : 4999
    if a:add && self._current_line != -1 && self._current_buf != -1
        exe 'sign place '. self._line_sign_id. ' name=GdbCurrentLine line='
                    \. self._current_line. ' buffer='. self._current_buf
    endif
    exe 'sign unplace '.old_line_sign_id
endfunction

" Firstly delete all breakpoints for Gdb delete breakpoints only by ref-no
" Then add breakpoints backto gdb
" @mode 0 reset-all, 1 enable-only-change, 2 delete-all
function! s:prototype.RefreshBreakpoints(mode)
    let is_running = 0
    let l:stateName = new#state#GetStateName('client')
    if l:stateName ==# "running"
        " pause first
        let is_running = 1
        "call self.Send("\<c-c>")
        call self.Send("Interrupt")
    endif

    if a:mode == 0 || a:mode == 2
        if self._has_breakpoints
            call self.Send('delete')
            let self._has_breakpoints = 0
        endif
    endif

    if a:mode == 0 || a:mode == 1
        let is_silent = 1
        if a:mode == 1
            let is_silent = 0
        endif

        for [next_key, next_val] in items(s:breakpoints)
            if next_val['state'] && !empty(next_val['cmd'])
                if is_silent == 1
                    let is_silent = 2
                    call self.Send('silent_on')
                endif

                if a:mode == 0 || (a:mode == 1 && next_val['change'])
                    let self._has_breakpoints = 1
                    call self.Send('break '. next_val['cmd'])
                endif
            endif
        endfor
        if is_silent == 2
            call self.Send('silent_off')
        endif
    endif

    if is_running
        call self.Send('next')
    endif
endfunction


function! s:prototype.Init()
    let s:this._wid_main = win_getid()
endfunction


function! s:prototype.Jump(file, line)
    let file = a:file
    if !filereadable(file) && file[0] != '/'
        let file = '/' . file
    endif
    if !filereadable(file)
        silent! call s:log.error("Jump File not exist: " . file)
    endif


    let cwindow = win_getid()
    let cbuftype = &buftype
    if cwindow != self._wid_main
        if win_gotoid(self._wid_main) != 1
            return
        endif
    endif
    stopinsert

    let self._current_buf = bufnr('%')
    let target_buf = bufnr(a:file, 1)
    if bufnr('%') != target_buf
        exe 'buffer ' target_buf
        let self._current_buf = target_buf
    endif
    exe ':' a:line | m'

    let self._current_line = a:line
    call self.Update_current_line_sign(1)
endfunction


function! s:prototype.Breakpoints(file)
    if self._show_breakpoint && filereadable(a:file)
        exec "silent lgetfile " . a:file
    endif
endfunction


function! s:prototype.Stack(file)
    if self._show_backtrace && filereadable(a:file)
        exec "silent! cgetfile " . a:file
    endif
endfunction


function! s:prototype.Interrupt()
    call jobsend(self._client_id, "\<c-c>info line\<cr>")
endfunction


function! s:prototype.SaveVariable(var, file)
    call writefile([string(a:var)], a:file)
endfunction

function! s:prototype.ReadVariable(varname, file)
    let recover = readfile(a:file)[0]
    execute "let ".a:varname." = " . recover
endfunction

function! s:prototype.Breaks2Qf()
    let list2 = []
    let i = 0
    for [next_key, next_val] in items(s:breakpoints)
        if !empty(next_val['cmd'])
            let i += 1
            call add(list2, printf('#%d  %d in    %s    at %s:%d',
                        \ i, next_val['state'], next_val['cmd'],
                        \ next_val['file'], next_val['line']))
        endif
    endfor

    call writefile(split(join(list2, "\n"), "\n"), s:gdb_break_qf)
    if self._show_breakpoint && filereadable(s:gdb_break_qf)
        exec "silent lgetfile " . s:gdb_break_qf
    endif
endfunction


function! s:prototype.GetCFunLinenr()
    let lnum = line(".")
    let col = col(".")
    let linenr = search("^[^ \t#/]\\{2}.*[^:]\s*$", 'bW')
    call search("\\%" . lnum . "l" . "\\%" . col . "c")
    return linenr
endfunction


" Key: file:line, <or> file:function
" Value: empty, <or> if condition
" @state 0 disable 1 enable, Toggle: none -> enable -> disable
" @type 0 line-break, 1 function-break
function! s:prototype.ToggleBreak()
    let filenm = bufname("%")
    let cur_line = getline('.')
    let linenr = line('.')
    let colnr = col(".")
    let cword = expand("<cword>")

    let fname = fnamemodify(filenm, ':p:.')
    let type = 0
    if s:cur_extension ==# 'py'
        " echo match("  let cur_line = getline('.')", '\v^(\W*)let')
        let idx = match(cur_line, '\v^(\W*)def')
        if idx >= 0
            let type = 1
        endif
    else
        let cfuncline = self.GetCFunLinenr()
        if linenr == cfuncline
            let type = 1
        endif
    endif

    if type == 1
        let file_breakpoints = fname .':'.cword
    else
        let file_breakpoints = fname .':'.linenr
    endif

    call self.Send(["break", file_breakpoints, type, cur_line])
    return




    " @todo wilson
    let mode = 0
    let old_value = get(s:breakpoints, file_breakpoints, {})
    if empty(old_value)
        let break_new = input("[break] ", file_breakpoints)
        if !empty(break_new)
            let old_value = {
                        \'file':fname,
                        \'type':type,
                        \'line':linenr, 'col':colnr,
                        \'fn' : '',
                        \'state' : 1,
                        \'cmd' : break_new,
                        \'change' : 1,
                        \}
            let mode = 1
            let s:breakpoints[file_breakpoints] = old_value
        endif
    elseif old_value['state']
        let break_new = input("[disable break] ", old_value['cmd'])
        if !empty(break_new)
            let old_value['state'] = 0
            let old_value['change'] = 1
        endif
    else
        let break_new = input("(delete break) ", old_value['cmd'])
        if !empty(break_new)
            call remove(s:breakpoints, file_breakpoints)
        endif
        let old_value = {}
    endif
    call self.SaveVariable(s:breakpoints, s:brk_file)
    call self.Breaks2Qf()
    call self.RefreshBreakpointSigns(mode)
    call self.RefreshBreakpoints(mode)
    if !empty(old_value)
        let old_value['change'] = 0
    endif
endfunction


function! s:prototype.ToggleBreakAll()
    let s:toggle_all = ! s:toggle_all
    let mode = 0
    for v in values(s:breakpoints)
        if s:toggle_all
            let v['state'] = 0
        else
            let v['state'] = 1
        endif
    endfor
    call self.RefreshBreakpointSigns(0)
    call self.RefreshBreakpoints(0)
endfunction


function! s:prototype.TBreak()
    let file_breakpoints = bufname('%') .':'. line('.')
    call self.Send(["tbreak", file_breakpoints])
endfunction

function! s:prototype.RunToHere()
    let file_breakpoints = bufname('%') .':'. line('.')
    call self.Send(["runto", file_breakpoints])
endfunction

function! s:prototype.ClearBreak()
    let s:breakpoints = {}
    call self.Breaks2Qf()
    call self.RefreshBreakpointSigns(0)
    call self.RefreshBreakpoints(2)
endfunction


function! s:prototype.FrameUp()
    call self.Send("up")
endfunction

function! s:prototype.FrameDown()
    call self.Send("down")
endfunction

function! s:prototype.Next()
    "let l:__func__ = s:module. ":Next() "
    call self.Send("next")
endfunction

function! s:prototype.Step()
    call self.Send("step")
endfunction

function! s:prototype.Eval(expr)
    let l:stateName = new#state#GetStateName('client')
    if l:stateName !=# "pause"
        throw 'Gdb eval only under "pause" but state="'
                \. l:stateName .'"'
    endif

    if g:neobugger_smart_eval
        " Enable smart-eval base-on the special project
        let s:eval_mode = 1
        let s:expr = a:expr
        call self.Send(printf('whatis %s', a:expr))
    else
        call self.Send(printf('p %s', a:expr))
    endif
endfunction


" Enable smart-eval base-on the special project
function! s:prototype.Whatis(type)
    if l:stateName !=# "pause"
        throw 'Gdb eval only under "pause" state'
    endif
    if empty(s:expr)
        throw 'Gdb eval expr is empty'
    endif

    if g:neobugger_smart_eval
        let s:eval_mode = 0
    else
        return
    endif

    if has_key(self, 'Symbol')
        silent! call s:log.trace("forward to getsymbol")
        let expr = self.Symbol(a:type, s:expr)
        call self.Send(expr)
    else
        call self.Send(printf('p %s', s:expr))
    endif
    let s:expr = ""
endfunction


function! s:prototype.Watch(expr)
    let l:__func__ = s:module. ":watch() "
    let expr = a:expr
    if expr[0] != '&'
        let expr = '&' . expr
    endif

    let s:eval_mode = 2
    silent! call s:log.debug(l:__func__, expr)
    call self.Eval(expr)
endfunction

function! s:prototype.ParseBacktrace()
  let s:lines = readfile('/tmp/gdb.bt')
  for s:line in s:lines
    echo s:line
  endfor
endfunction


function! s:prototype.ParseVar()
  let s:lines = readfile('/tmp/gdb.bt')
  for s:line in s:lines
    echo s:line
  endfor
endfunction


function! s:prototype.on_open() abort
    let l:__func__ = s:module. ":on_open() "
    silent! call s:log.debug(l:__func__, "dir=", s:dir)
    if s:_opened
        silent! call s:log.warn(l:__func__, "ignore re-open!")
        return
    endif
    let s:_opened = 1

    call self.Map("", "nmap")
endfunction

function! s:prototype.on_start(model, state, match_list) abort
    let l:__func__ = s:module. ":on_start() "
    "silent! call s:log.debug(l:__func__, "model=", a:model, " state=", a:state, " matched=", a:match_list)

    if s:_initialized
        silent! call s:log.warn(l:__func__, "ignore re-initial!")
        return
    endif
    let s:_initialized = 1
    let cword = expand("<cword>")


    if self.debug_mode == 0
        let self._show_backtrace = g:neobugger_local_backtrace
        let self._show_breakpoint = g:neobugger_local_breakpoint
    else
        let self._show_backtrace = g:neobugger_server_backtrace
        let self._show_breakpoint = g:neobugger_server_breakpoint
    endif

    silent! call s:log.info("Load breaks ...")
    if filereadable(s:brk_file)
        call self.ReadVariable("s:breakpoints", s:brk_file)
    endif

    silent! call s:log.info("Load set breaks ...")
    if !empty(s:breakpoints)
        call self.Breaks2Qf()
        call self.RefreshBreakpointSigns(0)
        call self.RefreshBreakpoints(0)
    endif

    if g:gdb_auto_run
        if self.debug_mode == 0
            if s:cur_extension ==# 'py'
                call new#util#post('client', "where\n")
            else
                call new#util#post('client', "start\n")
                call new#util#post('client', "parser_echo neobugger_local_start\n")
            endif
        elseif self.debug_mode == 1
            " server: dut.py -h dut -u admin -p "" -t "gdb:wad"
            call new#util#post('server', ''. g:neogdb_gdbserver . ' -h '. self.debug_server[0] . ' '. join(self.debug_args['args'][1:], ' '). "\n")
            "call new#util#post('client', "target remote ". join(self.debug_server, ":"). "\n")
        endif
    endif

    " Create quickfix: lgetfile, cgetfile
    if self._show_backtrace && win_gotoid(g:vmwRuntime.wid_main) == 1
        if !filereadable(s:gdb_bt_qf)
            exec "silent! vimgrep " . cword ." ". expand("%")
        else
            "exec "silent cgetfile " . s:gdb_bt_qf
        endif
        silent! copen
    endif

    if self._show_breakpoint && win_gotoid(g:vmwRuntime.wid_main) == 1
        if !filereadable(s:gdb_break_qf)
            exec "silent! lvimgrep " . cword ." ". expand("%")
        else
            exec "silent lgetfile " . s:gdb_break_qf
        endif
        silent! lopen
    endif

    call hw#tasklist#add(
                \ hw#functor#new(
                \    {-> execute(
                \       ['echomsg "Debug ready to go."',
                \        'call win_gotoid(g:vmwRuntime.wid_main)',
                \        'windo redraw!',
                \       ], '')
                \    }, ""
                \  )
                \)
endfunction


function! s:prototype.on_load_bt(file)
    if self._show_backtrace && filereadable(a:file)
        exec "cgetfile " . a:file
        "call utilquickfix#RelativePath()
    endif
endfunction

function! s:prototype.on_continue(...)
    call self.Update_current_line_sign(0)
endfunction

function! s:prototype.on_jump(model, state, match_list)
    let l:__func__ = s:module. ":on_jump() "
    "silent! call s:log.debug(l:__func__, "model=", a:model, " state=", a:state, " matched=", a:match_list)

    let l:file = a:match_list[1]
    let l:line = a:match_list[2]

    let l:stateName = new#state#GetStateNameByState(a:state)
    if l:stateName !=# "pause"
        call self.Send('parser_bt')
        call self.Send('info line')
    endif
    call self.Jump(l:file, l:line)
endfunction

function! s:prototype.on_print(model, state, match_list) abort
    let l:__func__ = s:module. ":on_print() "
    "silent! call s:log.debug(l:__func__, "model=", a:model, " state=", a:state, " matched=", a:match_list)

    silent! call s:log.debug(l:__func__, s:expr, a:match_list[1])
    if s:eval_mode == 2
        let s:eval_mode = 0
        call self.Send('watch *(int*)0x'. a:match_list[1])
    endif
endfunction

function! s:prototype.on_whatis(type, ...)
    call self.Whatis(a:type)
endfunction

function! s:prototype.on_parseend(...)
    call self.Whatis(a:type)
endfunction

function! s:prototype.on_retry(...)
    if self._server_exited
        return
    endif
    sleep 1
    call self.Attach()
    call self.Send('continue')
endfunction


function! s:prototype.on_server_accept(model, state, match_list) abort
    let l:__func__ = "s:module:on_server_accept() "
    "silent! call s:log.debug(l:__func__, "model=", a:model, " state=", a:state, " matched=", a:match_list)

    call self.Attach()
endfunction


function s:prototype.on_remote_debugging(...)
    let self._remote_debugging = 1
    call state#Switch('client', 'pause', 0)
endfunction


function! s:prototype.on_client_conn_succ(...)
    if g:gdb_auto_run
        if self.debug_mode == 1
            " Should not continue, and pause for customize set breakpoints
            "call new#util#post('client', "continue\n")
        else
            "
        endif
    endif
endfunction

function! s:prototype.on_remoteconn_succ(...)
    call state#Switch('client', 'pause', 0)
endfunction


function! s:prototype.on_remoteconn_fail(...)
    silent! call s:log.error("Remote connect gdbserver fail!")
endfunction


function! s:prototype.on_pause(...)
    call state#Switch('client', 'pause', 0)
endfunction


function! s:prototype.on_disconnected(...)
    if !self._server_exited && self._reconnect
        " Refresh to force a delete of all watchpoints
        "call self.RefreshBreakpoints(2)
        sleep 1
        call self.Attach()
        call self.Send('continue')
    endif
endfunction

function! s:prototype.on_exit(...)
    let self._server_exited = 1
endfunction


function! s:prototype.Map(viewname, type)
    let l:__func__ = s:module. ":Map() "
    silent! call s:log.debug(l:__func__, " type=", a:type)

    "if a:viewname
    if a:type ==# "unmap"
        exe 'unmap ' . g:gdb_keymap_refresh
        exe 'unmap ' . g:gdb_keymap_continue
        exe 'unmap ' . g:gdb_keymap_next
        exe 'unmap ' . g:gdb_keymap_step
        exe 'unmap ' . g:gdb_keymap_finish
        exe 'unmap ' . g:gdb_keymap_clear_break
        exe 'unmap ' . g:gdb_keymap_debug_stop
        exe 'unmap ' . g:gdb_keymap_until
        exe 'unmap ' . g:gdb_keymap_toggle_break
        exe 'unmap ' . g:gdb_keymap_toggle_break_all
        exe 'vunmap ' . g:gdb_keymap_toggle_break
        exe 'cunmap ' . g:gdb_keymap_toggle_break
        exe 'unmap ' . g:gdb_keymap_frame_up
        exe 'unmap ' . g:gdb_keymap_frame_down
        exe 'tunmap ' . g:gdb_keymap_refresh
        exe 'tunmap ' . g:gdb_keymap_continue
        exe 'tunmap ' . g:gdb_keymap_next
        exe 'tunmap ' . g:gdb_keymap_step
        exe 'tunmap ' . g:gdb_keymap_finish
        exe 'tunmap ' . g:gdb_keymap_toggle_break_all

        if exists("*NeogdbvimUnmapCallback")
            call NeogdbvimUnmapCallback()
        endif
    elseif a:type ==# "nmap"
        exe 'nnoremap <silent> ' . g:gdb_keymap_refresh          . ' :GdbRefresh<cr>'
        exe 'nnoremap <silent> ' . g:gdb_keymap_continue         . ' :GdbContinue<cr>'
        exe 'nnoremap <silent> ' . g:gdb_keymap_next             . ' :GdbNext<cr>'
        exe 'nnoremap <silent> ' . g:gdb_keymap_step             . ' :GdbStep<cr>'
        exe 'nnoremap <silent> ' . g:gdb_keymap_skip             . ' :GdbSkip<cr>'
        exe 'nnoremap <silent> ' . g:gdb_keymap_finish           . ' :GdbFinish<cr>'
        exe 'nnoremap <silent> ' . g:gdb_keymap_until            . ' :GdbUntil<cr>'

        let toggle_break_binding = 'nnoremap <silent> '  . g:gdb_keymap_toggle_break . ' :GdbToggleBreak<cr>'
        if !g:gdb_require_enter_after_toggling_breakpoint
            let toggle_break_binding = toggle_break_binding . '<cr>'
        endif
        exe toggle_break_binding
        exe 'cnoremap <silent> ' . g:gdb_keymap_toggle_break     . ' <cr>'

        exe 'nnoremap <silent> ' . g:gdb_keymap_toggle_break_all . ' :GdbToggleBreakAll<cr>'

        exe 'nnoremap <silent> ' . g:gdb_keymap_eval             . ' :GdbEvalWord<cr>'
        exe 'vnoremap <silent> ' . g:gdb_keymap_eval             . ' :GdbEvalRange<cr>'

        exe 'nnoremap <silent> ' . g:gdb_keymap_watch            . ' :GdbWatchWord<cr>'
        exe 'vnoremap <silent> ' . g:gdb_keymap_watch            . ' :GdbWatchRange<cr>'

        exe 'nnoremap <silent> ' . g:gdb_keymap_clear_break      . ' :GdbClearBreak<cr>'
        exe 'nnoremap <silent> ' . g:gdb_keymap_debug_stop       . ' :GdbDebugStop<cr>'

        exe 'nnoremap <silent> ' . g:gdb_keymap_frame_up         . ' :GdbFrameUp<cr>'
        exe 'nnoremap <silent> ' . g:gdb_keymap_frame_down       . ' :GdbFrameDown<cr>'

        if exists("*NeogdbvimNmapCallback")
            call NeogdbvimNmapCallback()
        endif
    endif
endfunction


" InstanceGdb {{{1

function! NeobuggerNew(mode, bin, args)
    let l:__func__ = "NeobuggerNew() "

    " mode: 0 local, 1 connect server, 2 attach pid
    let s:this.debug_mode = 0
    let s:this.debug_bin = a:bin
    let s:this.debug_args = a:args

    silent! call s:log.debug(l:__func__, "mode=", a:mode, " bin=", a:bin, " args=", a:args)

    if has_key(s:this.debug_args, 'args')
        let l:arg_list = s:this.debug_args['args']
        if len(l:arg_list) > 0
            let s:this.debug_server = split(l:arg_list[0], ":")
        endif
    else
        s:this.debug_args['args'] = ['t1']
    endif

    if a:mode ==# 'local'
        let s:this.debug_mode = 0
        if g:neobugger_local_backtrace
            call new#open('gdb_local_horiz')
        else
            call new#open('gdb_local_vert')
        endif
    elseif a:mode ==# 'server'
        let s:this.debug_mode = 1
        call new#open('gdb_remote_horiz')
    elseif a:mode ==# 'pid'
        let s:this.debug_mode = 2
    endif
endfunction


command! -nargs=+ -complete=file Nbgdb call NeobuggerNew('local', [<f-args>][0], {'args' : [<f-args>][1:]})
function! s:attachGDB(binaryFile, args)
    if len(a:args.args) >= 1
        if a:args.args[0] =~ '\v^\d+$'
            call NeobuggerNew('pid', a:binaryFile, {'pid': str2nr(a:args.args[0])})
        else
            call NeobuggerNew('server', a:binaryFile, {'args': a:args.args})
        endif
    else
        throw "Can't call Nbgdbattach with ".a:0." arguments"
    endif
endfunction
command! -nargs=+ -complete=file Nbgdbattach call s:attachGDB([<f-args>][0], {'args' : [<f-args>][1:]})


command! -nargs=0 GdbDebugStop call s:this.Kill()
command! -nargs=0 GdbToggleBreak call s:this.ToggleBreak()
command! -nargs=0 GdbToggleBreakAll call s:this.ToggleBreakAll()
command! -nargs=0 GdbClearBreak call s:this.ClearBreak()
command! -nargs=0 GdbContinue call s:this.Send('continue')
command! -nargs=0 GdbNext call s:this.Next()
command! -nargs=0 GdbStep call s:this.Step()
command! -nargs=0 GdbFinish call s:this.Send("finish")
"command! -nargs=0 GdbUntil call s:this.Send("until ". line('.'))
command! -nargs=0 GdbUntil call s:this.RunToHere()
command! -nargs=0 GdbFrameUp call s:this.FrameUp()
command! -nargs=0 GdbFrameDown call s:this.FrameDown()
command! -nargs=0 GdbInterrupt call s:this.Interrupt()
command! -nargs=0 GdbSkip call s:this.Send("skip")
command! -nargs=0 GdbRefresh call s:this.Send("info line")
command! -nargs=0 GdbInfoLocal call s:this.Send("info local")
command! -nargs=0 GdbInfoBreak call s:this.Send("info break")

command! -nargs=0 GdbEvalWord call s:this.Eval(new#util#get_curr_expression())
command! -range -nargs=0 GdbEvalRange call s:this.Eval(new#util#get_visual_selection())

command! -nargs=0 GdbWatchWord call s:this.Watch(new#util#get_curr_expression())
command! -range -nargs=0 GdbWatchRange call s:this.Watch(new#util#get_visual_selection())
" }}}

" Keymap options {{{1
"
if exists('g:neobugger_leader') && !empty(g:neobugger_leader)
        let g:gdb_keymap_refresh = g:neobugger_leader.'r'
        let g:gdb_keymap_continue = g:neobugger_leader.'c'
        let g:gdb_keymap_next = g:neobugger_leader.'n'
        let g:gdb_keymap_step = g:neobugger_leader.'i'
        let g:gdb_keymap_finish = g:neobugger_leader.'N'
        let g:gdb_keymap_until = g:neobugger_leader.'t'
        let g:gdb_keymap_toggle_break = g:neobugger_leader.'b'
        let g:gdb_keymap_toggle_break_all = g:neobugger_leader.'a'
        let g:gdb_keymap_clear_break = g:neobugger_leader.'C'
        let g:gdb_keymap_debug_stop = g:neobugger_leader.'x'
        let g:gdb_keymap_frame_up = g:neobugger_leader.'k'
        let g:gdb_keymap_frame_down = g:neobugger_leader.'j'
else
    if !exists("g:gdb_keymap_refresh")
        let g:gdb_keymap_refresh = '<f3>'
    endif

    if !exists("g:gdb_keymap_continue")
        let g:gdb_keymap_continue = '<f4>'
    endif
    if !exists("g:gdb_keymap_debug_stop")
        let g:gdb_keymap_debug_stop = '<F14>'
    endif

    if !exists("g:gdb_keymap_next")
        let g:gdb_keymap_next = '<f5>'
    endif
    if !exists("g:gdb_keymap_skip")
        let g:gdb_keymap_skip = '<F15>'
    endif

    if !exists("g:gdb_keymap_step")
        let g:gdb_keymap_step = '<f6>'
    endif
    if !exists("g:gdb_keymap_finish")
        let g:gdb_keymap_finish = '<F16>'
    endif

    if !exists("g:gdb_keymap_until")
        let g:gdb_keymap_until = '<f7>'
    endif

    if !exists("g:gdb_keymap_eval")
        let g:gdb_keymap_eval = '<f8>'
    endif
    if !exists("g:gdb_keymap_watch")
        let g:gdb_keymap_watch = '<F18>'
    endif

    if !exists("g:gdb_keymap_toggle_break")
        let g:gdb_keymap_toggle_break = '<f9>'
    endif
    if !exists("g:gdb_keymap_remove_break")
        let g:gdb_keymap_remove_break = '<F19>'
    endif

    if !exists("g:gdb_keymap_toggle_break_all")
        let g:gdb_keymap_toggle_break_all = '<f10>'
    endif
    if !exists("g:gdb_keymap_clear_break")
        let g:gdb_keymap_clear_break = '<F20>'
    endif

    if !exists("g:gdb_keymap_frame_up")
        let g:gdb_keymap_frame_up = '<c-n>'
    endif

    if !exists("g:gdb_keymap_frame_down")
        let g:gdb_keymap_frame_down = '<c-p>'
    endif

endif

" }}}


" Customization options {{{1
"
if !exists("g:neogdb_gdbserver")
    let g:neogdb_gdbserver = 'gdbserver'
endif
if !exists("g:neogdb_attach_remote_str")
    let g:neogdb_attach_remote_str = 't1 127.0.0.1:9999'
endif
if !exists("g:gdb_auto_run")
    let g:gdb_auto_run = 1
endif
if !exists("g:gdb_require_enter_after_toggling_breakpoint")
    let g:gdb_require_enter_after_toggling_breakpoint = 0
endif

if !exists("g:restart_app_if_gdb_running")
    let g:restart_app_if_gdb_running = 1
endif

if !exists("g:neobugger_smart_eval")
    let g:neobugger_smart_eval = 0
endif

if !exists("g:neobugger_local_breakpoint")
    let g:neobugger_local_breakpoint = 0
endif
if !exists("g:neobugger_local_backtrace")
    let g:neobugger_local_backtrace = 0
endif

if !exists("g:neobugger_server_breakpoint")
    let g:neobugger_server_breakpoint = 1
endif
if !exists("g:neobugger_server_backtrace")
    let g:neobugger_server_backtrace = 1
endif
" }}}


" Helper options {{{1
" call VimGdb('local', 't1')
" call VimGdb('remote', 'sysinit/init')
let s:gdb_command_state = 0
let s:cur_extension = ''
function! NeobuggerCommandStr()
    let s:cur_extension = expand('%:e')
    if s:cur_extension ==# 'py'
        return 'Nbgdb '. fnamemodify(expand("%"), ":~:.")
    else
        if s:gdb_command_state
            let s:gdb_command_state = 0
            return 'Nbgdbattach '. g:neogdb_attach_remote_str
        else
            let s:gdb_command_state = 1
            return 'Nbgdb '. expand('%:t:r')
        endif
    endif
endfunction

function! VimGdbJump(file, line)
    call s:this.Jump(a:file, a:line)
endfunction

function! VimGdbInit()
    call s:this.Init()
    call s:this.on_open()
endfunction

function! VimGdbClose()
    call s:this.Kill()
endfunction


function! VimGdbUpViewBtrace(file)
    call s:this.on_load_bt(a:file)
endfunction
