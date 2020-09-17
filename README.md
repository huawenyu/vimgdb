# vimgdb
Vim gdb base on Neovim + Tmux

Ref: https://github.com/sakhnik/nvim-gdb/

# Usage

# Const define

	class Common(BaseCommon)

# Troubleshooting

## Enable log

1. change vimgdb/config/logger.py:
	LOGGING_CONFIG.loggers
        '': {
            'level':     'DEBUG',    <=== change log level
            'handlers':  ['file'],   <=== Enable log by 'file', Disable log by 'null'
            'propagate': False
        },

2. monitor the debug log:
	Monitor LOGGING_CONFIG.handlers.file.filename, here is '/tmp/vimgdb.log':
	$ tail -f /tmp/vimgdb.log
