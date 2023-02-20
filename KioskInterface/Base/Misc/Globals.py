# -*- coding: utf-8 -*-
# Script: Default settings definition
#
# PLEASE NOTE that this file is part of the GOM Software.
# You are not allowed to distribute this file to a third party without written notice.
#
# Please, do not copy and/or modify this script.
# All modifications of KioskInterface should happen in the CustomPatches script.
# Ignoring this advice will make KioskInterface fail after Software update.
#
# Copyright (c) 2016 Carl Zeiss GOM Metrology GmbH
# All rights reserved.

# GOM-Script-Version: 7.6
#
# ChangeLog:
# 2012-05-31: Initial Creation
# 2013-01-22: Added global logger instance for easier access from eg static methods
# 2015-04-23: Additional project keywords variable added


import logging
import gom

# definition of Exit Exceptions
EXIT_EXCEPTIONS = ( SystemExit )
# global definition for async communication
ASYNC_SERVER = None
ASYNC_CLIENTS = None
CONTROL_INSTANCE = None
DRC_EXTENSION = None
# global definition for persistant settings
PERSISTENTSETTINGS = None

# additional project keywords
# specify keywords as tuples of (currently) six values
#   ('name', 'description', 'inputfield', 'optional',
#    'conversion', 'default value')
#        name: Name of your new project keyword (string)
# description: The keyword description (string)
#  inputfield: The name of the input field of the start dialog (string)
#    optional: Specify if the kiosk should allow the start button also for an empty input value
#              (True or False)
# two additional values are possible (not publicly announced):
#    conversion: If present, a function which is used to convert the input value to a string:
#                conversion ( key, field, dialog ) -> str.
#                Different signature for per-part keywords:
#                conversion ( key, field, dict(field->val) ) -> str.
# default value: If present, input field is set to this value for a new cycle.
#                Note, for per-part dialog otherwise a reset to empty string is done
ADDITIONAL_PROJECTKEYWORDS = []
ADDITIONAL_PERPARTKEYWORDS = []

DIALOGS = None
LOCALIZATION = None
SETTINGS = None
LOGGER = logging.getLogger( '' )
LOGGER.addHandler( logging.NullHandler() )  # default log to nothing
ERROR_HANDLER = gom.ErrorHandler ()
TIMER = None
IOT_CONNECTION = None

class FeatureSet:
	V8StartDialogs = True
	DRC_PRIMARY_INST = False
	DRC_SECONDARY_INST = False
	DRC_UNPAIRED = False
	DRC_ONESHOT = False           # obsolete
	DRC_SINGLE_SIDE = False
	ONESHOT_MODE = False
	ONESHOT_MSERIES = False
	MULTIROBOT_EVALUATION = False
	MULTIROBOT_MEASUREMENT = False
	MULTIROBOT_MEASUREMENT_ID = None
FEATURE_SET = FeatureSet()

def registerGlobalLogger( baselog ):
	'''
	register a logging adapter globally thus eg static methods/global functions have access to the logging instance
	'''
	global LOGGER
	LOGGER = logging.LoggerAdapter( baselog.log, {'class':'GLOBAL'} )