"""."""


LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'standard': {
            #'format': '%(asctime)s [%(levelname)-4.4s] %(name)-12s.%(funcName)s: %(message)s',
            #'format': '[%(asctime)s] [%(levelname)-4.4s] [%(funcName)-18s]',
            #'format':  '[%(asctime)s] [%(levelname)-4.4s] %(name)-12s.%(funcName)-18s(): %(message)s',
            'format':  '[%(asctime)s] [%(levelname)-4.4s] %(name)s.%(funcName)s(): %(message)s',
            #'datefmt': '%Y-%m-%d %H:%M:%S',
            'datefmt': '%M:%S',
        },
    },
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },

        'file': {
            'level':     'DEBUG',
            'formatter': 'standard',
            'class':     'logging.FileHandler',
            'filename':  '/tmp/vimgdb.log',
            'mode':      'a',
        },
    },

    'loggers': {
        # root logger: 'INFO', 'DEBUG'
        #   used when the <name> not exist here: logging.getLogger(<name>)
        '': {
            'level':     'DEBUG',
            'handlers':  ['file'],
            'propagate': False
        },
    }
}

