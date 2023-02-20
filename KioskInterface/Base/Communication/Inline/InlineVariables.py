# -*- coding: utf-8 -*-
# PLEASE NOTE that this file is part of the GOM Software.
# You are not allowed to distribute this file to a third party without written notice.
#
# Please, do not copy and/or modify this script.
# All modifications of KioskInterface should happen in the CustomPatches script.
# Ignoring this advice will make KioskInterface fail after Software update.
#
# Copyright (c) 2017 Carl Zeiss GOM Metrology GmbH
# All rights reserved.

from ..PLC import PLCconstants as plc_const
from ..PLC import PLCfunctions
from ...Misc import Globals, Utils
import ctypes

class MeasureInstanceState (Utils.EnumStructure):
	NOT_STARTED=0
	STARTED=1
	IDLE=2
	READY=3
	MEASURING=4
	SPECIAL_POSITION=5
		
class State ( Utils.EnumStructure ):
	UNKNOWN = -1
	ERROR = 0
	OK = 1

class PLCVar:
	_plc_vars = []
	def __init__(self, name, type, decode = False):
		self.name = 'GOM_KIOSK.'+name
		self._type = type
		self._handle = None
		self._connection = None
		self._decode = decode
		PLCVar._plc_vars.append(self)
		
	def getHandle(self, adr):
		self._handle = PLCfunctions.adsGetHandle(adr, self.name)
		self._connection = adr
	
	def releaseHandle(self, adr):
		if self._handle is not None:
			try:
				PLCfunctions.adsReleaseHandle(adr, self._handle)
			except:
				pass
		self._handle = None
		self._connection = None
		
	def write(self, value):
		if self._connection is None:
			return
		if self._handle is None:
			raise Exception("Tried to write variable with invalid handle")
		if PLCVariable.bPulse.name not in self.name:
			Globals.LOGGER.debug('write {} : {}'.format(self.name, value))
		if self._decode and isinstance(value,str):
			value = str.encode(value)
		remaining = None
		try:
			remaining = ''
			length = self._type._length_
			if len(value) > length:
				seps=['\n',' ','\t']
				if self._decode:
					seps = [str.encode(s) for s in seps]
				last_sep = max([value.rfind(s,0,length) for s in seps])
				if last_sep == -1:
					remaining = value[length:]
					value = value[:length]
				else:
					remaining = value[last_sep+1:]
					value = value[:last_sep+1]	
		except:
			pass
		PLCfunctions.adsSyncWriteByHandle(self._connection, self._handle, value, self._type)
		return remaining
		
	def read(self, default=None):
		if self._connection is None:
			return default
		if self._handle is None:
			raise Exception("Tried to read variable with invalid handle")
		res = PLCfunctions.adsSyncReadByHandle(self._connection, self._handle, self._type)

		if self._decode:
			res = bytes.decode(res)
			if res != chr(0x0) and len(res.strip()):
				res = res.strip()
			else:
				res = default
		
		if PLCVariable.bPulse.name not in self.name:
			if default is None or res != default:
				Globals.LOGGER.debug('read {}={}'.format(self.name, res))
		return res
	
	def check(self, default):
		value = self.read(default)
		if value:
			self.write(default)
		return value
	
class PLCVariable:
	@staticmethod
	def registerHandles(adr):
		for h in PLCVar._plc_vars:
			try:
				h.getHandle(adr)
			except Exception as e:
				Globals.LOGGER.exception("failed to get handle {} {}".format(h.name,e))
				#raise e
	
	@staticmethod
	def releaseHandles(adr):
		for h in PLCVar._plc_vars:
			h.releaseHandle(adr)

	STRING_LEN = 80
	PROTOCOL_VERSION = 4
	
	bPulse = PLCVar('bKioskPulse', plc_const.PLCTYPE_BOOL)
	
	RECV_bStart           = PLCVar('bStart',           plc_const.PLCTYPE_BOOL)
	RECV_sTemplateID      = PLCVar('sTemplateID',      ctypes.c_wchar * 100)
	RECV_bTemplateIDReady = PLCVar('bTemplateIDReady', plc_const.PLCTYPE_BOOL)
	RECV_bDoubleRobotTemplate = PLCVar('bDoubleRobotTemplate', plc_const.PLCTYPE_BOOL)
	RECV_sSCTemplateID      = PLCVar('sSCTemplateID',      ctypes.c_wchar * 100)
	
	RECV_bMeasure       = PLCVar('bMeasure',       plc_const.PLCTYPE_BOOL)
	RECV_bStop          = PLCVar('bStop',          plc_const.PLCTYPE_BOOL)
	RECV_bTerminate     = PLCVar('bTerminate',     plc_const.PLCTYPE_BOOL) 
	RECV_bAbort         = PLCVar('bAbort',         plc_const.PLCTYPE_BOOL)
	RECV_bCloseTemplate = PLCVar('bCloseTemplate', plc_const.PLCTYPE_BOOL)
	RECV_bSensorDeInit  = PLCVar('bSensorDeInit',  plc_const.PLCTYPE_BOOL)
	RECV_bCreateGOMSic  = PLCVar('bCreateGomSic',  plc_const.PLCTYPE_BOOL)
	RECV_bShutdown      = PLCVar('bShutdown',      plc_const.PLCTYPE_BOOL)
	
	SEND_bIdle         = PLCVar('bKioskIdle',         plc_const.PLCTYPE_BOOL)
	SEND_bReady        = PLCVar('bKioskReady',        plc_const.PLCTYPE_BOOL)
	SEND_bExited       = PLCVar('bKioskExited',       plc_const.PLCTYPE_BOOL)
	SEND_bSensorDeInit = PLCVar('bKioskSensorDeInit', plc_const.PLCTYPE_BOOL)
	
	SEND_bEvalFinished        = PLCVar('bKioskEvalFinished',        plc_const.PLCTYPE_BOOL)
	SEND_sEvalSerial          = PLCVar('sKioskEvalSerial',          ctypes.c_wchar * 100)
	SEND_sEvalAddInfo1        = PLCVar('sKioskEvalUserData_1',      ctypes.c_wchar * 100)
	SEND_sEvalAddInfo2        = PLCVar('sKioskEvalUserData_2',      ctypes.c_wchar * 100)
	SEND_sEvalAddInfo3        = PLCVar('sKioskEvalUserData_3',      ctypes.c_wchar * 100)
	SEND_bEvalSuccess         = PLCVar('bKioskEvalSuccess',         plc_const.PLCTYPE_BOOL)
	SEND_bEvalFailed          = PLCVar('bKioskEvalFailed',          plc_const.PLCTYPE_BOOL)
	SEND_wEvalErrorID         = PLCVar('wKioskEvalErrorID',         plc_const.PLCTYPE_WORD)
	SEND_sEvalErrorText_1     = PLCVar('sKioskEvalErrorText_1',     ctypes.c_wchar * STRING_LEN)
	SEND_sEvalErrorText_2     = PLCVar('sKioskEvalErrorText_2',     ctypes.c_wchar * STRING_LEN)
	SEND_bEvalResultNotNeeded = PLCVar('bKioskEvalResultNotNeeded', plc_const.PLCTYPE_BOOL)
	SEND_bEvalWarning         = PLCVar('bKioskEvalWarning',         plc_const.PLCTYPE_BOOL)
	SEND_bEvalQStop           = PLCVar('bKioskEvalQStop',           plc_const.PLCTYPE_BOOL)
	
	SEND_sMeasureInfo        = PLCVar('sKioskMeasureUserData',      ctypes.c_wchar * 100)
	
	SEND_bError        = PLCVar('bKioskError',            plc_const.PLCTYPE_BOOL)
	SEND_wErrorID      = PLCVar('wKioskErrorID',          plc_const.PLCTYPE_WORD)
	SEND_sErrorText1   = PLCVar('sKioskErrorMessage_1',   ctypes.c_wchar * STRING_LEN)
	SEND_sErrorText2   = PLCVar('sKioskErrorMessage_2',   ctypes.c_wchar * STRING_LEN)
	SEND_bWarning      = PLCVar('bKioskWarning',          plc_const.PLCTYPE_BOOL)
	SEND_wWarningID    = PLCVar('wKioskWarningID',        plc_const.PLCTYPE_WORD)
	SEND_sWarningText1 = PLCVar('sKioskWarningMessage_1', ctypes.c_wchar * STRING_LEN)
	SEND_sWarningText2 = PLCVar('sKioskWarningMessage_2', ctypes.c_wchar * STRING_LEN)

	RECV_bForceCalibration    = PLCVar('bForceCalibration',    plc_const.PLCTYPE_BOOL)
	RECV_bForcePhotogrammetry = PLCVar('bForcePhotogrammetry', plc_const.PLCTYPE_BOOL)
	
	RECV_wSpecialPosition      = PLCVar('wSpecialPosition',         plc_const.PLCTYPE_WORD)
	RECV_wSpecialSubPosition   = PLCVar('wSpecialSubPosition',      plc_const.PLCTYPE_WORD)
	RECV_bSpecialPositionReady = PLCVar('bSpecialPositionReady',    plc_const.PLCTYPE_BOOL)
	RECV_bHomePosition         = PLCVar('bHomePosition',            plc_const.PLCTYPE_BOOL)
	SEND_bPositionReached      = PLCVar('bKioskPositionReached',    plc_const.PLCTYPE_BOOL)
	SEND_bPositionNotReached   = PLCVar('bKioskPositionNotReached', plc_const.PLCTYPE_BOOL)
	
	RECV_bPrepareExecution       = PLCVar('bPrepareExecution', plc_const.PLCTYPE_BOOL)
	RECV_sAdditionalInformation1 = PLCVar('sUserData_1',       ctypes.c_wchar * 100)
	RECV_sAdditionalInformation2 = PLCVar('sUserData_2',       ctypes.c_wchar * 100)
	RECV_sAdditionalInformation3 = PLCVar('sUserData_3',       ctypes.c_wchar * 100)
	RECV_sSCAdditionalInformation1 = PLCVar('sSCUserData_1',       ctypes.c_wchar * 100)
	RECV_sSCAdditionalInformation2 = PLCVar('sSCUserData_2',       ctypes.c_wchar * 100)
	RECV_sSCAdditionalInformation3 = PLCVar('sSCUserData_3',       ctypes.c_wchar * 100)
	RECV_bResultNotNeeded        = PLCVar('bResultNotNeeded',  plc_const.PLCTYPE_BOOL)
	
	SEND_wMListTotalCount        = PLCVar('wKioskMaxCount_MeasList', plc_const.PLCTYPE_WORD)
	SEND_wMListCurrentPos        = PLCVar('wKioskActive_MeasList',   plc_const.PLCTYPE_WORD)
	SEND_wMeasurementTotalCount  = PLCVar('wKioskMaxCount_MeasPos',  plc_const.PLCTYPE_WORD)
	SEND_wMeasurementCurrentPos  = PLCVar('wKioskActive_MeasPos',    plc_const.PLCTYPE_WORD)
	SEND_wEstimatedExecutionTime = PLCVar('wKioskEstimatedExecutionTime', plc_const.PLCTYPE_WORD)
	
	SEND_wProtocolVersion = PLCVar('wKioskProtocolVersion', plc_const.PLCTYPE_WORD)
	SEND_wATOSVersion     = PLCVar('sKioskATOSVersion',     ctypes.c_wchar * STRING_LEN)
	RECV_wProtocolVersion = PLCVar('wProtocolVersion',      plc_const.PLCTYPE_WORD)
	
	RECV_bMoveHome     = PLCVar('bMoveHome',     plc_const.PLCTYPE_BOOL)
	RECV_bMoveContinue = PLCVar('bMoveContinue', plc_const.PLCTYPE_BOOL)
	RECV_bMoveAbort    = PLCVar('bMoveAbort',    plc_const.PLCTYPE_BOOL)
	
	SEND_bTritopNotAvailable = PLCVar('bKioskTritopNotAvailable', plc_const.PLCTYPE_BOOL)
	
	SEND_bSpecialPosValid  = PLCVar('bKioskSpecialPositionsValid', plc_const.PLCTYPE_BOOL)
	SEND_bSpecialPos1      = PLCVar('bKioskSpecialPos1', plc_const.PLCTYPE_BOOL)
	SEND_bSpecialPos2      = PLCVar('bKioskSpecialPos2', plc_const.PLCTYPE_BOOL)
	SEND_bSpecialPos3      = PLCVar('bKioskSpecialPos3', plc_const.PLCTYPE_BOOL)
	SEND_bSpecialPos4      = PLCVar('bKioskSpecialPos4', plc_const.PLCTYPE_BOOL)
	SEND_bSpecialPos5      = PLCVar('bKioskSpecialPos5', plc_const.PLCTYPE_BOOL)
	SEND_bSpecialPos6 	   = PLCVar('bKioskSpecialPos6', plc_const.PLCTYPE_BOOL)
	SEND_bSpecialPos7 	   = PLCVar('bKioskSpecialPos7', plc_const.PLCTYPE_BOOL)
	SEND_wSubPositionsPos1 = PLCVar('wKioskSubPositionsPos1', plc_const.PLCTYPE_WORD)
	SEND_wSubPositionsPos2 = PLCVar('wKioskSubPositionsPos2', plc_const.PLCTYPE_WORD)
	SEND_wSubPositionsPos3 = PLCVar('wKioskSubPositionsPos3', plc_const.PLCTYPE_WORD)
	SEND_wSubPositionsPos4 = PLCVar('wKioskSubPositionsPos4', plc_const.PLCTYPE_WORD)
	SEND_wSubPositionsPos5 = PLCVar('wKioskSubPositionsPos5', plc_const.PLCTYPE_WORD)
	SEND_wSubPositionsPos6 = PLCVar('wKioskSubPositionsPos6', plc_const.PLCTYPE_WORD)
	SEND_wSubPositionsPos7 = PLCVar('wKioskSubPositionsPos7', plc_const.PLCTYPE_WORD)

	RECV_bStartATOS = PLCVar('bStartATOS', plc_const.PLCTYPE_BOOL)

	SEND_bCalibrationStarted = PLCVar('bKioskCalibrationStarted', plc_const.PLCTYPE_BOOL)	
	SEND_bCalibrationDone    = PLCVar('bKioskCalibrationDone', plc_const.PLCTYPE_BOOL)
	SEND_bPhotogrammetryStarted = PLCVar('bKioskPhotogrammetryStarted', plc_const.PLCTYPE_BOOL)	
	SEND_bPhotogrammetryDone    = PLCVar('bKioskPhotogrammetryDone', plc_const.PLCTYPE_BOOL)
	
	SEND_bPhotogrammetryRecommended = PLCVar('bKioskPhotogrammetryRecommended', plc_const.PLCTYPE_BOOL)
	SEND_bCalibrationRecommended    = PLCVar('bKioskCalibrationRecommended', plc_const.PLCTYPE_BOOL)