#!/bin/env python
# coding: utf8

import logging
import sys
import socket

DEBUG = logging.DEBUG
INFO = logging.INFO
WARN = logging.WARN
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

log_debug = logging.debug
log_info = logging.info
log_warn = logging.warning
log_error = logging.error
log_critical = logging.critical

def get_log(logger, level):
    if level == DEBUG:
        return logger.debug
    elif level == WARN:
        return logger.warning
    elif level == ERROR:
        return logger.error
    elif level == CRITICAL:
        return logger.critical
    else:
        return logger.info

def print_stdout(msg):
    sys.stdout.write(msg+"\n")
    sys.stdout.flush()

def print_stderr(msg):
    sys.stderr.write(msg+"\n")

FORMAT = '%(asctime)-15s|%(name)s|%(process)d|%(threadName)-10s|%(levelname)-5s|%(filename)s:%(lineno)d|%(message)s'

logging.basicConfig(stream=sys.stdout, format=FORMAT)
logger = logging.getLogger() #默认取app logger
logger.setLevel(INFO)
