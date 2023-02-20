# -*- coding: utf-8 -*-
# Script: Constant definitions for Inline KioskInterface
#
# PLEASE NOTE that this file is part of the GOM Software.
# You are not allowed to distribute this file to a third party without written notice.
#
# Please, do not copy and/or modify this script.
# All modifications of KioskInterface should happen in the CustomPatches script.
# Ignoring this advice will make KioskInterface fail after Software update.
#
# Copyright (c) 2017 Carl Zeiss GOM Metrology GmbH
# All rights reserved.

from .. import Communicate
from ...Misc import Globals
import pickle


class PLCErrors:
	NO_ERROR = 0
	UNKNOWN_ERROR = 1
	PROTOCOL_VERSION_ERROR = 2
	DISC_SPACE_ERROR = 3
	FAILED_OPEN_TEMPLATE = 100
	EVAL_FAILED_TO_EXPORT = 200
	
	MEAS_INIT_SENSOR = 300
	MEAS_SYSTEM_CONFIG = 301
	MEAS_MOVE_ERROR = 302
	MEAS_MLIST_ERROR = 303
	MEAS_MLIST_USERABORT = 304
	MEAS_MLIST_CALIBRATION_COUNT = 305
	MEAS_MLIST_ABORT = 306
	MEAS_MLIST_CALIBRATION_ERROR = 307
	MEAS_MLIST_TRITOP_VERIFICATION = 308
	MEAS_MLIST_ATOS_VERIFICATION = 309
	MEAS_MLIST_ALIGNMENT_RESIDUAL = 310
	MEAS_MLIST_RETRY = 311
	
	MEAS_EMERGENCY_STOP = 400
	MEAS_FENCE_OPEN = 401
	MEAS_RESET_STATE = 402
	
class PLCWarnings:
	NO_WARNING = 0
	DISC_SPACE_WARNING = 1
	SENSOR_WARMUP = 2
	SENSOR_INIT_WARNING = 3
	
class MoveDecision:
	UNKNOWN = 0
	CONTINUE = 1
	ABORT = 2
	MOVE_REVERSE_HOME = 3
	
def sendMeasureInstanceError(plc_code, error_code, error_text, error_title=''):
	if not error_text and not error_code:
		error_text = 'User Abort'
	msg = pickle.dumps({'title':error_title, 'msg':error_text, 'code': error_code, 'plc_code': plc_code})
	if Globals.CONTROL_INSTANCE is None:
		raise Exception(error_title+' '+error_text)
	Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_ERROR, msg ) )
	
# Find a better place and remove global
last_warnings = [(0,'','','')]
def sendMeasureInstanceWarning(plc_code, error_code, error_text, error_title=''):
	msg = pickle.dumps({'title':error_title, 'msg':error_text, 'code': error_code, 'plc_code': plc_code})
	if Globals.CONTROL_INSTANCE is None:
		raise Exception(error_title+' '+error_text)
	global last_warnings
	if plc_code != PLCWarnings.SENSOR_WARMUP:
		last_warnings.append((plc_code,error_code, error_text, error_title))
	Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_WARNING, msg ) )
	
def resetMeasuringInstanceWarning(current_plc_code):
	global last_warnings
	for i in range(len(last_warnings)-1,-1,-1):
		if last_warnings[i][0] == current_plc_code:
			del last_warnings[i]
	if not len(last_warnings):
		last_warnings = [(0,'','','')]
	if Globals.CONTROL_INSTANCE is None:
		return	
	msg = pickle.dumps({'title':last_warnings[-1][3], 'msg':last_warnings[-1][2], 'code': last_warnings[-1][1], 'plc_code': last_warnings[-1][0]})
	Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_WARNING, msg ) )
	
