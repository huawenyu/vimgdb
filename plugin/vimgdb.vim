if exists('g:loaded_vim_gdb') || !has("nvim") || &compatible
    finish
endif
let g:loaded_vim_gdb = 1

if !exists("s:init")
    let s:init = 1
    let s:module = "vimgdb"
    silent! let s:log = logger#getLogger(expand('<sfile>:t'))

    "sign define GdbBreakpointEn  text=● texthl=Search
    "sign define GdbBreakpointDis text=● texthl=Function
    "sign define GdbBreakpointDel text=● texthl=Comment

    "sign define GdbCurrentLine   text=☛ texthl=Error
    ""sign define GdbCurrentLine text=▶ texthl=Error
    ""sign define GdbCurrentLine text=☛ texthl=Keyword
    ""sign define GdbCurrentLine text=⇒ texthl=String

    set errorformat+=#%c\ \ %.%#\ in\ %m\ \(%.%#\)\ at\ %f:%l
    set errorformat+=#%c\ \ %.%#\ in\ \ \ \ %m\ \ \ \ at\ %f:%l
    set errorformat+=#%c\ \ %m\ \(%.%#\)\ at\ %f:%l

    let s:dir = expand('<sfile>:p:h')
    let s:breakpoint_signid_start = 5000
    let s:breakpoint_signid_min = 0
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


function! s:prototype.Update_current_line_sign(add)
    " to avoid flicker when removing/adding the sign column(due to the change in
    " line width), we switch ids for the line sign and only remove the old line
    " sign after marking the new one
    let old_line_sign_id = get(self, '_line_sign_id', 4999)
    let self._line_sign_id = old_line_sign_id == 4999 ? 4998 : 4999
    if a:add && self._current_line != -1 && self._current_buf != -1
        exe 'sign place '. self._line_sign_id. ' name=GdbCurrentLine priority=30 line='
                    \. self._current_line. ' buffer='. self._current_buf
    endif
    exe 'sign unplace '.old_line_sign_id
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

    call self.Send(["toggle", file_breakpoints, type, cur_line])
    return


    call self.SaveVariable(s:breakpoints, s:brk_file)
    call self.Breaks2Qf()
    call self.RefreshBreakpointSigns(mode)
    call self.RefreshBreakpoints(mode)
    if !empty(old_value)
        let old_value['change'] = 0
    endif
endfunction


function! s:prototype.ToggleBreakAll()
    call self.Send("toggleAll")
endfunction


function! s:prototype.ClearBreak()
    call self.Send("clearAll")
endfunction


function! s:prototype.TBreak()
    let file_breakpoints = bufname('%') .':'. line('.')
    call self.Send(["tbreak", file_breakpoints])
endfunction

function! s:prototype.RunToHere()
    let file_breakpoints = bufname('%') .':'. line('.')
    call self.Send(["runto", file_breakpoints])
endfunction

function! s:prototype.FrameUp()
    call self.Send("up")
endfunction

function! s:prototype.FrameDown()
    call self.Send("down")
endfunction

function! s:prototype.Next()
    call self.Send("next")
endfunction

function! s:prototype.Step()
    call self.Send("step")
endfunction

function! s:prototype.Eval(expr)
    if g:neobugger_smart_eval
        " Enable smart-eval base-on the special project
        let s:eval_mode = 1
        let s:expr = a:expr
        call self.Send(['whatis', a:expr])
    else
        call self.Send(['print', a:expr])
    endif
endfunction

" Enable smart-eval base-on the special project
function! s:prototype.Whatis(type)
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

command! -nargs=0 GdbEvalWord call s:this.Eval(VimGdb_get_curr_expression())
command! -range -nargs=0 GdbEvalRange call s:this.Eval(VimGdb_get_visual_selection())

command! -nargs=0 GdbWatchWord call s:this.Watch(VimGdb_get_curr_expression())
command! -range -nargs=0 GdbWatchRange call s:this.Watch(VimGdb_get_visual_selection())
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

" Sign define
if !exists("g:vimgdb_sign_current")
    "sign define GdbCurrentLine   text=☛ texthl=Error
    "sign define GdbCurrentLine text=▶ texthl=Error
    "sign define GdbCurrentLine text=☛ texthl=Keyword
    "sign define GdbCurrentLine text=⇒ texthl=String

    let g:vimgdb_sign_currentline = '☛'
endif
if !exists("g:vimgdb_sign_current_color")
    let g:vimgdb_sign_currentline_color = 'Error'
endif
if !exists("g:vimgdb_sign_breakpoint")
    "sign define GdbBreakpointEn  text=● texthl=Search
    "sign define GdbBreakpointDis text=● texthl=Function
    "sign define GdbBreakpointDel text=● texthl=Comment

    let g:vimgdb_sign_breakpoints = ['●', '●²', '●³', '●⁴', '●⁵', '●⁶', '●⁷', '●⁸', '●⁹', '●ⁿ']
endif
if !exists("g:vimgdb_sign_breakp_color_en")
    let g:vimgdb_sign_breakp_color_en = 'Search'
endif
if !exists("g:vimgdb_sign_breakp_color_dis")
    let g:vimgdb_sign_breakp_color_dis = 'Function'
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

"Returns the visually selected text
function! VimGdb_get_visual_selection()
    "Shamefully stolen from http://stackoverflow.com/a/6271254/794380
    " Why is this not a built-in Vim script function?!
    let [lnum1, col1] = getpos("'<")[1:2]
    let [lnum2, col2] = getpos("'>")[1:2]
    if lnum1 == lnum2
        let curline = getline('.')
        return curline[col1-1:col2-1]
    else
        let lines = getline(lnum1, lnum2)
        let lines[-1] = lines[-1][: col2 - (&selection == 'inclusive' ? 1 : 2)]
        let lines[0] = lines[0][col1 - 1:]
        return join(lines, "\n")
    endif
endfunction

function! VimGdb_get_curr_expression()
    let save_cursor = getcurpos()

    let text = getline('.')
    normal! be
    let end_pos = getcurpos()
    call search('\s\|[,;\(\)]','b')
    call search('\S')
    let start_pos = getcurpos()

    call setpos('.', save_cursor)
    return text[ (start_pos[2] -1) : (end_pos[2] - 1)]
endfunction


function! VimGdbJump(file, line)
    call s:this.Jump(a:file, a:line)
endfunction


function! VimGdbViewBtrace()
    " Create quickfix: lgetfile, cgetfile
    if s:this._show_backtrace && win_gotoid(s:this._wid_main) == 1
        if !filereadable(s:gdb_bt_qf)
            exec "silent! vimgrep " . cword ." ". expand("%")
        else
            exec "silent cgetfile " . s:gdb_bt_qf
        endif
        "call utilquickfix#RelativePath()
        silent! copen
    endif
endfunction

function! VimGdbViewBpoint()
    if s:this._show_breakpoint && win_gotoid(s:this._wid_main) == 1
        if !filereadable(s:gdb_break_qf)
            exec "silent! lvimgrep " . cword ." ". expand("%")
        else
            exec "silent lgetfile " . s:gdb_break_qf
        endif
        silent! lopen
    endif
endfunction

function! VimGdbClearSign(istart, iend)
    if a:istart == 0
        return
    endif

    let i = a:istart
    while i <= a:iend
        exe 'sign unplace '.i
        let i += 1
    endwhile
endfunction

function! VimGdbSign(file, line, signid, signgroup, signname)
    let buf = bufnr(a:file)
    "self.vim.call('sign_place', sign_id, 'NvimGdb', sign_name, buf,
    "              {'lnum': line, 'priority': 10})
    if bufexists(buf)
        exe 'sign place '.a:signid.' group='.a:signgroup .' priority=20 name='.a:signname.' line='.a:line.' buffer='.buf
    endif
endfunction


function! VimGdbInit()
    call s:this.Init()
    call s:this.on_open()
endfunction

function! VimGdbClose()
    call s:this.Kill()
endfunction


