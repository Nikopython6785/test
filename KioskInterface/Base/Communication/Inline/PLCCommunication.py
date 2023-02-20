# -*- coding: utf-8 -*-
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


import gom
import time
import pickle

from ...Misc import Utils, LogClass

from ..PLC import PLCfunctions as plc
from ..PLC import PLCconstants as plc_const

from .InlineConstants import *
from .InlineVariables import *


class WaitForChangeQueue(Utils.GenericLogClass):
	class Entry:
		def __init__(self, var, old_value, action):
			self.var = var
			self.old_value = old_value
			self.action = action
			
	def __init__(self, parent, logger):
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self._fifoqueue=[]
		
	def append(self, var, old_value, action = None):
		self._fifoqueue.append(WaitForChangeQueue.Entry(var,old_value, action))
	
	def clear(self):
		self._fifoqueue = []
		
	def check(self):
		if self.parent.connection is None:
			return False, 'no connection'
		while len(self._fifoqueue):
			entry = self._fifoqueue[0]
			value = entry.var.read(entry.old_value)
			if value != entry.old_value:
				if entry.action is not None:
					entry.action()
				del self._fifoqueue[0]
			else:
				return False, entry.var.name
		return True, ''
		
class PLCCommunication(Utils.GenericLogClass):
	def __init__(self, parent, logger, netID='172.17.61.55.1.1', port=851):
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.netID = netID
		self.port = port
		self.connection = None
		self.waitForChangeQueue = WaitForChangeQueue(self, self.baselog)
		self.parent.connectedState.appendAction(self.onConnectionStateChange)
		self.parent.aliveState.appendAction(self.onAliveStateChange)
		self.parent.resultState.appendAction(self.onResultStateChange)
		self._last_pulse = (None, time.time())
		self.PULSE_TIMEOUT=5
		self.reconnectTimer = 0
		self._last_debug = time.time()
		self.was_connected = False
		
	def debugSignals(self):
		if not self.parent.dialog.logSignalOverview.visible:
			return
		text=''
		try:
			for var in PLCVar._plc_vars:
				text+='{}: {}\n'.format(var.name.replace('GOM_KIOSK.',''), var.read())
			self.parent.dialog.logSignalOverview.text=text
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()

	def connect(self):
		if not plc.isADSLoaded():
			self.connection = None
			self.parent.plcState.value = State.ERROR
			return
		try:
			port = plc.adsPortOpen()
			self.connection = plc.adsGetLocalAddress()
			self.connection.setAdr(self.netID)
			self.connection.setPort(self.port)
			self.parent.plcState.value = State.OK
			PLCVariable.registerHandles(self.connection)
			if not self.was_connected:
				self.onInitialConnect()
			self.was_connected = True
		except Exception as e:
			self.log.exception('Failed to connect with PLC: {}'.format(e))
			PLCVariable.releaseHandles(self.connection)
			self.connection = None
			self.parent.plcState.value = State.ERROR

	def reconnect(self):
		if self.connection is not None:
			self.reconnectTimer = 0
			return
			
		self.reconnectTimer += 1
		if self.reconnectTimer > 10:
			self.reconnectTimer = 0
			self.connect()
			if self.connection is not None:
				self.log.info('Reconnect successfull')
			
	def onConnectionError(self):
		PLCVariable.releaseHandles(self.connection)
		try:
			if self.connection is not None:
				plc.adsPortClose()
		except:
			pass
		self.connection = None
		self.waitForChangeQueue.clear()
		self._last_pulse = (None, time.time())
		self.parent.plcState.value = State.ERROR
		self.parent.actionExit()
			
	def onConnectionStateChange(self, new_value):
		if self.parent.measuringInstanceState.value == MeasureInstanceState.NOT_STARTED:
			# NOT_STARTED is set before manual exit
			# send no signal here only once onAliveStateChange
			return
		try:
			old_value = self.parent.connectedState.value
			if new_value == State.UNKNOWN or new_value == State.ERROR:
				if old_value == State.OK:
					self.writeAndWait(PLCVariable.SEND_bExited, True)
			else: # connected
				pass
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def onInitialConnect(self):
		self.checkAndSendProtocolVersion()
		try:
			self.writeAndWait(PLCVariable.SEND_bExited, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def onAliveStateChange(self, new_value):
		try:
			old_value = self.parent.aliveState.value
			if new_value == State.UNKNOWN or new_value == State.ERROR:
				if old_value == State.OK:
					self.writeAndWait(PLCVariable.SEND_bExited, True)
			else: # alive
				# clear all warnings
				PLCVariable.SEND_wWarningID.write(0)
				PLCVariable.SEND_sWarningText1.write("")
				PLCVariable.SEND_sWarningText2.write("")
				PLCVariable.SEND_bWarning.write(True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def onResultStateChange(self, new_value):
		try:
			if type(new_value) == dict:
				if not len(new_value):
					return
				self.log.debug("result: {}".format(new_value))
				if new_value['result']:
					PLCVariable.SEND_bEvalSuccess.write(True)
					PLCVariable.SEND_bEvalFailed.write(False)
				else:
					PLCVariable.SEND_bEvalSuccess.write(False)
					PLCVariable.SEND_bEvalFailed.write(True)
				PLCVariable.SEND_bEvalWarning.write(True if len(new_value.get('out_of_tol_warning','')) else False)
				PLCVariable.SEND_bEvalQStop.write(True if len(new_value.get('out_of_tol_qstop','')) else False)
				PLCVariable.SEND_sEvalSerial.write(new_value['serial'])
				PLCVariable.SEND_sEvalAddInfo1.write(new_value['add_plc_info'][0])
				PLCVariable.SEND_sEvalAddInfo2.write(new_value['add_plc_info'][1])
				PLCVariable.SEND_sEvalAddInfo3.write(new_value['add_plc_info'][2])
				PLCVariable.SEND_bEvalResultNotNeeded.write(new_value['result_not_needed'])
				if len(new_value.get('error','')):
					PLCVariable.SEND_wEvalErrorID.write(PLCErrors.EVAL_FAILED_TO_EXPORT)
					remaining = PLCVariable.SEND_sEvalErrorText_1.write(new_value.get('error',''))
					PLCVariable.SEND_sEvalErrorText_2.write(remaining)
				else:
					PLCVariable.SEND_wEvalErrorID.write(PLCErrors.NO_ERROR)
					PLCVariable.SEND_sEvalErrorText_1.write('')
					PLCVariable.SEND_sEvalErrorText_2.write('')
				self.writeAndWait(PLCVariable.SEND_bEvalFinished, True)
			else:
				self.log.debug("NO dict as result {}".format(new_value))
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
		
	def onTemplateOpen(self):
		try:
			self.writeAndWait(PLCVariable.SEND_bReady, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
		
	def onErrorInMeasureInstance(self, error, error_desc):
		try:
			PLCVariable.SEND_wErrorID.write(error)
			remaining = PLCVariable.SEND_sErrorText1.write(error_desc)
			PLCVariable.SEND_sErrorText2.write(remaining)
			self.writeAndWait(PLCVariable.SEND_bError, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def onWarningInMeasureInstance(self, warning, warn_desc):
		try:
			PLCVariable.SEND_wWarningID.write(warning)
			remaining = PLCVariable.SEND_sWarningText1.write(warn_desc)
			PLCVariable.SEND_sWarningText2.write(remaining)
			self.writeAndWait(PLCVariable.SEND_bWarning, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
		
	def onIdleChange(self):
		self.onMeasurementPositionChanged(mlist_total=0, mlist_curr=0, measurement_total=0, measurement_curr=0)
		try:
			self.writeAndWait(PLCVariable.SEND_bIdle, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def onSensorDeInit(self):
		try:
			self.writeAndWait(PLCVariable.SEND_bSensorDeInit, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
	
	def onMoveToPosition(self, result, special_position):
		if special_position:
			self.parent.measuringInstanceState.value=MeasureInstanceState.SPECIAL_POSITION
		else:
			self.parent.measuringInstanceState.value=MeasureInstanceState.READY
		try:
			if result:
				self.writeAndWait(PLCVariable.SEND_bPositionReached, True)
			else:
				self.writeAndWait(PLCVariable.SEND_bPositionNotReached, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def onMeasurementPositionChanged(self, mlist_total=None, mlist_curr=None, measurement_total=None, measurement_curr=None):
		try:
			#no wait for reset
			if mlist_total is not None:
				PLCVariable.SEND_wMListTotalCount.write(mlist_total)
			if mlist_curr is not None:
				PLCVariable.SEND_wMListCurrentPos.write(mlist_curr)
			if measurement_total is not None:
				PLCVariable.SEND_wMeasurementTotalCount.write(measurement_total)
			if measurement_curr is not None:
				PLCVariable.SEND_wMeasurementCurrentPos.write(measurement_curr)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def checkAndSendProtocolVersion(self):
		error=False
		try:
			PLCVariable.SEND_wProtocolVersion.write(PLCVariable.PROTOCOL_VERSION)
			PLCVariable.SEND_wATOSVersion.write(
				gom.app.get ('application_name')+' '+
				gom.app.get ('application_build_information.version')+', Rev. '+
				gom.app.get ('application_build_information.revision')+', Build '+
				gom.app.get ('application_build_information.date'))
			plc_version = PLCVariable.RECV_wProtocolVersion.read(0)
			if plc_version < PLCVariable.PROTOCOL_VERSION:
				PLCVariable.SEND_wErrorID.write(PLCErrors.PROTOCOL_VERSION_ERROR)
				remaining = PLCVariable.SEND_sErrorText1.write('Protocol version mismatch Software: {} > PLC: {}'.format(PLCVariable.PROTOCOL_VERSION, plc_version))
				PLCVariable.SEND_sErrorText2.write(remaining)
				PLCVariable.SEND_bError.write(True)
				error=True
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
		if error:
			self.onConnectionError()
			raise SystemExit

	def setReady(self):
		try:
			self.writeAndWait(PLCVariable.SEND_bReady, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def onPhotogrammetryHardwareNotAvailable(self):
		try:
			self.writeAndWait(PLCVariable.SEND_bTritopNotAvailable, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
			
	def onEstimatedExecutionTime(self, value):
		try:
			#no wait for reset
			PLCVariable.SEND_wEstimatedExecutionTime.write(value)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
	
	def onAvailableSubPositions(self, value):
		try:
			sigs = [
				( PLCVariable.SEND_bSpecialPos1, PLCVariable.SEND_wSubPositionsPos1 ),
				( PLCVariable.SEND_bSpecialPos2, PLCVariable.SEND_wSubPositionsPos2 ),
				( PLCVariable.SEND_bSpecialPos3, PLCVariable.SEND_wSubPositionsPos3 ),
				( PLCVariable.SEND_bSpecialPos4, PLCVariable.SEND_wSubPositionsPos4 ),
				( PLCVariable.SEND_bSpecialPos5, PLCVariable.SEND_wSubPositionsPos5 ),
				( PLCVariable.SEND_bSpecialPos6, PLCVariable.SEND_wSubPositionsPos6 ),
				( PLCVariable.SEND_bSpecialPos7, PLCVariable.SEND_wSubPositionsPos7 ) ]
			for i in range(len(sigs)):
				countsubs = value.get(i+1, -1)
				sigs[i][0].write(countsubs != -1)
				sigs[i][1].write(countsubs if countsubs != -1 else 0)
			self.writeAndWait(PLCVariable.SEND_bSpecialPosValid, True)
		except Exception as e:
			self.log.exception('Connection lost {}'.format(e))
			self.onConnectionError()
	
	def onMeasureUserData(self, value):
		PLCVariable.SEND_sMeasureInfo.write(value)
		
	def onCalibrationDone(self):
		PLCVariable.SEND_bCalibrationDone.write(True)
	
	def onCalibrationStarted(self):
		PLCVariable.SEND_bCalibrationStarted.write(True)
		
	def onPhotogrammetryDone(self):
		PLCVariable.SEND_bPhotogrammetryDone.write(True)
	
	def onPhotogrammetryStarted(self):
		PLCVariable.SEND_bPhotogrammetryStarted.write(True)
		
	def onPhotogrammetryRecommended(self):
		PLCVariable.SEND_bPhotogrammetryRecommended.write(True)
	
	def onCalibrationRecommended(self):
		PLCVariable.SEND_bCalibrationRecommended.write(True)

	def writeAndWait(self, variable, value):
		variable.write(value)
		self.waitForChangeQueue.append(variable, value)
		
	def checkPulse(self):
		value = PLCVariable.bPulse.read()
		if (value != self._last_pulse[0]):
			self._last_pulse = (not value, time.time())
			PLCVariable.bPulse.write(not value)
		elif self._last_pulse[0] is not None:
			if time.time() > self._last_pulse[1] + self.PULSE_TIMEOUT:
				return False # timeout
		return True

	def process_signals(self):
		self.parent.cycleTimeStat.updateTick()
		
		if self.connection is None:
			self.reconnect()
			return
		
		try:
			if time.time() > self._last_debug + 60:
				self._last_debug = time.time()
				self.log.debug('STATUS started:{} state:{}'.format(self.parent.started,self.parent.measuringInstanceState.value))
				self.debugSignals()
				
			if not self.checkPulse():
				self.log.error('Pulse Variable time out')
				self.onConnectionError()
				self.reconnect()
				return
			
			queue_result, queue_varname = self.waitForChangeQueue.check()
			if not queue_result: # dont check further if one variable "hangs"
				self.log.debug('waiting for "{}" to change'.format(queue_varname))
				return
			
			if PLCVariable.RECV_bShutdown.check(False):
				self.parent.actionShutdown()
				return
			
			if PLCVariable.RECV_bStartATOS.check(False):
				self.parent.actionStartSW()
				return
		
			if not self.parent.started and self.parent.connectedState.value != State.OK:
				if PLCVariable.RECV_bStart.check(False):
					self.parent.actionStart()
					return
			else:
				if PLCVariable.RECV_bTerminate.check(False):
					self.parent.actionTerminate()
					return
				if self.parent.connectedState.value == State.OK:
					if PLCVariable.RECV_bStop.check(False):
						self.parent.actionExit()
						return
					if PLCVariable.RECV_bCreateGOMSic.check(False):
						self.parent.actionCreateGOMSic()
						return
					
			if self.parent.measuringInstanceState.value == MeasureInstanceState.IDLE or self.parent.measuringInstanceState.value == MeasureInstanceState.READY:
				if PLCVariable.RECV_bSensorDeInit.check(False):
					self.parent.actionDeInitSensor()
					return
				if PLCVariable.RECV_bTemplateIDReady.check(False):
					value = PLCVariable.RECV_sSCTemplateID.read('') # need to first look at drc slave project!
					if value:
						PLCVariable.RECV_sSCTemplateID.write('')
						self.log.info('Got SC template ID: '+value)
						self.parent.actionSerial(value, False, True)
						value1 = PLCVariable.RECV_sSCAdditionalInformation1.read('').strip()
						value2 = PLCVariable.RECV_sSCAdditionalInformation2.read('').strip()
						value3 = PLCVariable.RECV_sSCAdditionalInformation3.read('').strip()
						value = value1+value2+value3
						if len(value):
							self.parent.actionPrepareExecutionRaw2(pickle.dumps([value1, value2, value3]))
					value = PLCVariable.RECV_sTemplateID.read('')
					if value:
						PLCVariable.RECV_sTemplateID.write('')
						self.log.info('Got template ID: '+value)
						drc = PLCVariable.RECV_bDoubleRobotTemplate.check(False)
						self.parent.actionSerial(value, drc, False)
						value1 = PLCVariable.RECV_sAdditionalInformation1.read('').strip()
						value2 = PLCVariable.RECV_sAdditionalInformation2.read('').strip()
						value3 = PLCVariable.RECV_sAdditionalInformation3.read('').strip()
						value = value1+value2+value3
						if len(value):
							self.parent.actionPrepareExecutionRaw(pickle.dumps([value1, value2, value3]))
					
					return
				if PLCVariable.RECV_bCloseTemplate.check(False):	
					self.parent.actionCloseTemplate()
					return

			if self.parent.measuringInstanceState.value == MeasureInstanceState.READY:
				value = PLCVariable.RECV_bResultNotNeeded.check(False)
				if value:
					self.parent.actionSetResultNotNeeded(value)
					return
				if PLCVariable.RECV_bPrepareExecution.check(False):
					value1 = PLCVariable.RECV_sAdditionalInformation1.check('').strip()
					value2 = PLCVariable.RECV_sAdditionalInformation2.check('').strip()
					value3 = PLCVariable.RECV_sAdditionalInformation3.check('').strip()
					value = value1+value2+value3
					self.parent.actionPrepareExecutionRaw(pickle.dumps([value1, value2, value3]))
					self.parent.actionPrepareExecution(value)
					value1 = PLCVariable.RECV_sSCAdditionalInformation1.check('').strip()
					value2 = PLCVariable.RECV_sSCAdditionalInformation2.check('').strip()
					value3 = PLCVariable.RECV_sSCAdditionalInformation3.check('').strip()
					value = value1+value2+value3
					if len(value):
						self.parent.actionPrepareExecutionRaw2(pickle.dumps([value1, value2, value3]))
					return
				if PLCVariable.RECV_bMeasure.check(False):
					self.parent.actionStartEvaluation()
					return
				if PLCVariable.RECV_bSpecialPositionReady.check(False):
					pos = PLCVariable.RECV_wSpecialPosition.check(0)
					subpos = PLCVariable.RECV_wSpecialSubPosition.check(0)
					self.parent.actionMoveToPosition(pos, subpos)
					return
				if PLCVariable.RECV_bForceCalibration.check(False):
					self.parent.actionForceCalibration()
					return
				if PLCVariable.RECV_bForcePhotogrammetry.check(False):
					self.parent.actionForceTritop()
					return
				
			if self.parent.measuringInstanceState.value == MeasureInstanceState.SPECIAL_POSITION:
				if PLCVariable.RECV_bHomePosition.check(False):
					self.parent.actionMoveToHome()
					return
				if PLCVariable.RECV_bSpecialPositionReady.check(False):
					pos = PLCVariable.RECV_wSpecialPosition.check(0)
					subpos = PLCVariable.RECV_wSpecialSubPosition.check(0)
					self.parent.actionMoveToPosition(pos, subpos)
					return
				
			if self.parent.measuringInstanceState.value == MeasureInstanceState.MEASURING:
				if PLCVariable.RECV_bAbort.check(False):
					self.parent.actionAbort()
					return
			
			if self.parent.move_decision_needed.value:
				if PLCVariable.RECV_bMoveHome.check(False):
					self.parent.actionMoveDecisionAfterFault(MoveDecision.MOVE_REVERSE_HOME)
					return
				elif PLCVariable.RECV_bMoveContinue.check(False):
					self.parent.actionMoveDecisionAfterFault(MoveDecision.CONTINUE)
					return
				elif PLCVariable.RECV_bMoveAbort.check(False):
					self.parent.actionMoveDecisionAfterFault(MoveDecision.ABORT)
					return				

					
		except gom.BreakError:
			raise
		except Exception as e:
			self.log.exception('Failed to get PLC variable: {}'.format(e))
			self.onConnectionError()

	def shutdown(self):
		pass