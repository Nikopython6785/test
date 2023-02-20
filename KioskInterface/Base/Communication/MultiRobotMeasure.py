# -*- coding: utf-8 -*-
# Script: Multirobot measure client script.
#
# PLEASE NOTE that this file is part of the GOM Software.
# You are not allowed to distribute this file to a third party without written notice.
#
# Please, do not copy and/or modify this script.
# All modifications of KioskInterface should happen in the CustomPatches script.
# Ignoring this advice will make KioskInterface fail after Software update.
#
# Copyright (c) 2021 Carl Zeiss GOM Metrology GmbH
# All rights reserved.


import gom

import os
import pickle
import psutil
import time
import sys

import gom_windows_utils
from ..Misc import Utils, Globals
from . import AsyncClient, AsyncServer, Communicate
from ..Measuring import Verification, Measure
from .. import Evaluate
import KioskInterface.Tools.StatisticalLog as StatisticalLog
# TODO home_pos_check sendet kein failure


class MultiRobotMeasure( Utils.GenericLogClass ):
	secondary_con = None
	remote_todos = None
	connected = False
	update_startdialog_text = True
	selected_tritop_mlists = []
	selected_atos_mlists = []
	robot_program_id = None
	keep_project = False

	def __init__(self, parent, logger):
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		if len( Globals.SETTINGS.MultiRobot_HostPorts) == 1:
			port = Globals.SETTINGS.MultiRobot_HostPorts[0]
		else:
			port = Globals.SETTINGS.MultiRobot_HostPorts[Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID]
		self.secondary_con = AsyncServer.CommunicationServer(
			self.baselog, self, '', port, {} ) # bind to all interfaces
		self.remote_todos = Communicate.RemoteTodos( self.baselog )
		self.log.info( "Multi Robot Extension loaded (Measurement)" )
		self.single_side_primary = False
		self.single_side_secondary = False
		self.robot_program_id = None
		self.export_path_ext = None
		self.temperature = None
		self.compatible_mseries = None
		self.startup_done = False

	def PrimarySideActive(self):
		return False
	def SecondarySideActive(self):
		return True
	def SecondarySideActiveForError(self):
		return True

	def getExternalSavePath(self):
		if len( Globals.SETTINGS.MultiRobot_ClientTransferPath) == 1:
			return Globals.SETTINGS.MultiRobot_ClientTransferPath[0]
		return Globals.SETTINGS.MultiRobot_ClientTransferPath[Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID]


	def terminate(self):
		import ctypes, ctypes.wintypes
		OpenProcess = ctypes.windll.kernel32.OpenProcess
		OpenProcess.argtypes = (ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD)
		OpenProcess.restype = ctypes.wintypes.HANDLE
		TerminateProcess = ctypes.windll.kernel32.TerminateProcess
		TerminateProcess.argtypes = (ctypes.wintypes.HANDLE, ctypes.c_uint)
		TerminateProcess.restype = ctypes.wintypes.BOOL
		CloseHandle = ctypes.windll.kernel32.CloseHandle
		CloseHandle.argtypes = (ctypes.wintypes.HANDLE,)
		CloseHandle.restype = ctypes.wintypes.BOOL
		PROCESS_TERMINATE = 1

		swpid = gom.getpid()
		self.log.debug( 'Killing pid {}'.format( swpid ) )
		handle = OpenProcess( PROCESS_TERMINATE, False, swpid )
		TerminateProcess( handle, 1 )
		CloseHandle( handle )

	### background timer call
	def globalTimerCheck (self, value):
		try:
			self.collect_pkts()
		except:
			pass

	def collect_pkts(self):
		if self.secondary_con is None:
			return
		while self.secondary_con.process_signals():
			pass
		for sig in self.secondary_con.pop_results():
			if sig == Communicate.SIGNAL_CONTROL_EXIT:
				self.terminate()
				sys.exit(0)
			self.remote_todos.append_todo( sig )
		was_connected = self.connected
		self.connected = self.secondary_con.Handshaked
		if was_connected and not self.connected:
			self.on_connection_lost()
		elif not was_connected and self.connected:
			self.on_first_connection()

#			if sig == Communicate.SIGNAL_INLINE_DRC_MOVEDECISION:
#				# no real todo
#				if Globals.SETTINGS.WaitingForMoveDecision:
#					Globals.SETTINGS.MoveDecisionAfterFaultState = int(sig.get_value_as_string())
#					Globals.SETTINGS.InAsyncAbort = False
#					self.log.debug('triggering async abort')
#					gom.app.abort = True

# TODO abort / failure signal handling necessary for teach mode?
#			elif sig == Communicate.SIGNAL_INLINE_DRC_ABORT:
#				if Globals.SETTINGS.AllowAsyncAbort:
#					self.log.debug('direct abort')
#					gom.app.abort = True
#				else:
#					Globals.SETTINGS.InAsyncAbort = True
#			else:
#				self.remote_todos.append_todo(sig)
#				if sig == Communicate.SIGNAL_FAILURE:
#					self.log.debug('got failure')
#					if Globals.SETTINGS.AllowAsyncAbort:
#						self.log.debug('direct abort')
#						gom.app.abort = True
#					else:
#						Globals.SETTINGS.InAsyncAbort = True

	def other_side_still_active(self):
		# only checked in DRC Primary
		return False

	def on_first_connection(self):
		self.update_startdialog_text = True
		Globals.SETTINGS.InAsyncAbort = False

		# send info about startup done
		if self.startup_done:
			self._send_startup_done()

	def on_connection_lost(self):
		self.update_startdialog_text = True
		self.remote_todos.clear()

	def send_inline_signal(self, signal):
		self.log.warning('Skip sending 2ndary inst data sig {}'.format(signal))

	def sendStartFailure(self, text):
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, text.format( Communicate.SIGNAL_START.key ) ) )

	def sendStartSuccess(self):
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_START.key ) ) )

	def sendExit(self):
		pass

	# setup inline
	def init_measure_client(self, startup):
		if not Globals.SETTINGS.Inline:
			return True

		Globals.SETTINGS.CurrentTemplateIsConnected = False
		Globals.SETTINGS.CurrentTemplateConnectedProjectId = ''
		Globals.SETTINGS.CurrentTemplateConnectedUrl = ''
		Globals.SETTINGS.CurrentTemplateCfg = 'shared'
		Globals.SETTINGS.CurrentTemplate = Globals.SETTINGS.MultiRobot_MeasureTemplate
		startup.open_template( True )

		if Globals.SETTINGS.CurrentTemplate is None:
			self.log.error( 'Initial open of MultiRobot template failed' )
			return False

		# offline guesses automation hardware
		if Globals.SETTINGS.OfflineMode:
			gom.script.automation.define_automation_hardware (
				controller='Fanuc {}'.format( Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID + 1 ) )

		try:
			# init sensor if needed and check warmup time
			if not startup.parent.eval.eval.Sensor.initialize():
				self.log.error( 'Failed to initialize sensor' )
				return False

			# collect compatible mmts
			mmts_res = startup.parent.eval.eval.collectCompatibleSeries()
			comp_series = startup.parent.eval.eval.Comp_atos_series[0]
			res = startup.parent.eval.eval.define_active_measuring_series(
				gom.app.project.measurement_series[comp_series] )
		except Exception as e:
			self.log.exception( 'Setting up measurements failed: {}'.format( e ) )
			return False

		startup.parent.eval.eval.save_project()
		self.compatible_mseries = (
			startup.parent.eval.eval.Compatible_wcfgs,
			startup.parent.eval.eval.Comp_photo_series,
			startup.parent.eval.eval.Comp_atos_series,
			startup.parent.eval.eval.Comp_calib_series)
		self.startup_done = True
		# send info about startup done
		if self.connected:
			self._send_startup_done()

		return True

	def _send_startup_done( self ):
		self.log.debug( 'Send "startup done"' )
		self.secondary_con.send_signal( Communicate.Signal(
			Communicate.SIGNAL_MULTIROBOT_MMT_STARTUP_DONE,
			pickle.dumps( self.compatible_mseries ) ) )


# TODO clean-up and complete for teach mode
	##### StartDialog part
	def start_dialog_handler(self, startup, widget):
		if self.secondary_con is None:
			return True
		connection_text = 'Connected' if self.connected else 'Disconnected'
		if widget == 'initialize':
			if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
				startup.dialog.button_extension.text = connection_text
			if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
				startup.dialog.buttonTemplateChoose.enabled = False

#			Globals.SETTINGS.CurrentTemplateIsConnected = False
#			Globals.SETTINGS.CurrentTemplateConnectedProjectId = ''
#			Globals.SETTINGS.CurrentTemplateConnectedUrl = ''
#			Globals.SETTINGS.CurrentTemplateCfg = 'shared'
#			Globals.SETTINGS.CurrentTemplate = Globals.SETTINGS.MultiRobot_MeasureTemplate
#			startup.open_template( True )
#
#			# XXX DEBUG TODO
#			gom.script.automation.define_automation_hardware (
#				controller='Fanuc {}'.format( Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID + 1 ) )
#
#			try:
#				# collect compatible mmts
#				mmts_res = startup.parent.eval.eval.collectCompatibleSeries()
#				res = startup.parent.eval.eval.define_active_measuring_series(
#					startup.parent.eval.eval.Comp_photo_series[0] )
#			except Exception as e:
#				self.log.exception( 'Setting up measurements failed: {}'.format( e ) )
#				# TODO further reaction? close template... just quit here at the moment
#				return True
#
#			# save_project...
#			startup.parent.eval.eval.save_project()

		elif widget == 'timer':
			if self.update_startdialog_text:
				if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
					startup.dialog.button_extension.text = connection_text
				self.update_startdialog_text=False
			if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
				if self.connected:
					startup.dialog.buttonTemplateChoose.enabled = False
				else:
					startup.dialog.buttonTemplateChoose.enabled = False

			if self.check_start_signals( startup ):
				gom.script.sys.close_user_defined_dialog( dialog = startup.dialog, result = True )
				return False # exit handler

		elif isinstance(widget, str):
			pass
		elif widget.name == 'button_extension':
			pass

		return True

	def after_template_opened(self, startup, opened_template, multipart):
		pass

	def precheck_template(self):
		return True

	def check_start_signals(self, startup):
		if not len( self.remote_todos.todos ):
			return False

		while len( self.remote_todos.todos ) > 0:
			signal = self.remote_todos.todos[0][0]
			self.log.debug( 'Executing signal {}'.format( signal ) )
# TODO reactivate the necessary signals again for teach mode
#			if signal == Communicate.SIGNAL_OPEN or signal == Communicate.SIGNAL_OPEN_INIT:
#				del self.remote_todos.todos[0]
#				# ignore template in inline mode
#				if not Globals.SETTINGS.Inline:
#					try:
#						gom.app.project
#					except:
#						Globals.SETTINGS.CurrentTemplate = None
#						Globals.SETTINGS.CurrentTemplateCfg = None
#					template=''
#					template_cfg = ''
#					serial=''
#					try:
#						value = pickle.loads(signal.value)
#						template = value[0]
#						template_cfg = value[1]
#						if len(value) > 2:
#							serial = value[2]
#					except:
#						template = signal.get_value_as_string()
#					self.single_side_startupres = {'serial': serial}
#					startup.dialog.inputSerial.value=serial
#					self.log.debug(self.single_side_startupres)
#					if Globals.SETTINGS.CurrentTemplate != template or Globals.SETTINGS.CurrentTemplateCfg != template_cfg:
#						Globals.SETTINGS.CurrentTemplate = template
#						Globals.SETTINGS.CurrentTemplateCfg = template_cfg
#						startup.open_template( True )
#					if signal == Communicate.SIGNAL_OPEN_INIT:
#						with Measure.TemporaryWarmupDisable( startup.parent.eval.eval.Sensor ) as warmup:
#							# TODO init failure?
#							startup.parent.eval.eval.Sensor.check_for_reinitialize()
#
#				mmts_res = False
#				if Globals.SETTINGS.CurrentTemplate is not None:
#					# collect compatible mmts and send back to control instance
#					mmts_res = startup.parent.eval.eval.collectCompatibleSeries()
#					if not mmts_res:
#						self.log.error( 'Failed to collect compatible mmt series' )
#						# failure is sent below
#					else:
#						self.secondary_con.send_signal(
#							Communicate.Signal( Communicate.SIGNAL_MULTIROBOT_COMP_MMTS,
#								pickle.dumps( (startup.parent.eval.eval.Compatible_wcfgs,
#											startup.parent.eval.eval.Comp_photo_series,
#											startup.parent.eval.eval.Comp_atos_series,
#											startup.parent.eval.eval.Comp_calib_series) ) ) )
#
#				if Globals.SETTINGS.CurrentTemplate is not None and mmts_res:
#					self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key ) ) )
#					if Globals.SETTINGS.Inline:
#						Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_TEMPLATE, str(1)))
#				else:
#					self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, Globals.LOCALIZATION.msg_DC_slave_failed_open.format( signal.key ) ) )
#
#			elif signal == Communicate.SIGNAL_CLOSE_TEMPLATE:
#				del self.remote_todos.todos[0]
#				gom.script.sys.close_project()
#				Globals.SETTINGS.CurrentTemplate = None
#				Globals.SETTINGS.CurrentTemplateCfg = None
#				Globals.SETTINGS.AlreadyExecutionPrepared = False
#				if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
#					startup.dialog.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
#				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key ) ) )
#			elif signal == Communicate.SIGNAL_START:
#				del self.remote_todos.todos[0]
#				# no direct reply
#
#				# first measure client: sends temperature on start
#				if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID == 0:
#					temperature = startup.parent.eval.eval.thermo.get_temperature()
#					self.secondary_con.send_signal( Communicate.Signal(
#						Communicate.SIGNAL_CONTROL_TEMPERATURE, str( temperature ) ) )
#				self.log.debug( 'START (signal start)' )
#				return True
#			elif signal == Communicate.SIGNAL_MULTIROBOT_INLINE_OPTIPREPARE:
			if signal == Communicate.SIGNAL_MULTIROBOT_INLINE_OPTIPREPARE:
				del self.remote_todos.todos[0]
				temperature = None
				try:
					data = pickle.loads( signal.value )
					self.export_path_ext = data['timestamp']
					self.log.debug( 'Prepare for measuring into folder {}'.format(
						self.export_path_ext ) )
					extpath = os.path.join( self.getExternalSavePath(), self.export_path_ext )
					if os.path.exists( extpath ):
						raise ValueError( 'Transfer path extension "{}" already exists'.format(
							self.export_path_ext ) )
					else:
						os.makedirs( extpath )
						self.log.debug( 'Export path {} created'.format( extpath ) )

					temperature = data['temperature']
					self.log.debug( 'Prepare received temperature {}'.format( temperature ) )
				except Exception as e:
					self.log.exception( 'Failed to get data/create transfer path ext from signal {}'.format( e ) )
					self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
						# TODO Globals.LOCALIZATION
						'Handling signal {} produced error {}'.format( signal.key, e ) ) )
					return False

				if temperature is None:
					self.log.warning( 'No temperature received - fallback to local temperature' )
					self.temperature = startup.parent.eval.eval.thermo.get_temperature()
				else:
					self.temperature = temperature

				# first measure client: sends temperature on start
				if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID == 0:
					self.secondary_con.send_signal( Communicate.Signal(
						Communicate.SIGNAL_CONTROL_TEMPERATURE, str( self.temperature ) ) )

				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key ) ) )
			elif signal == Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID:
				del self.remote_todos.todos[0]
				if not Globals.SETTINGS.Inline:
					self.log.error( 'NOT Inline Mode: Received inline robot program id' )
					self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, str( signal.key ) ) )
					return False
				try:
					self.robot_program_id = int( pickle.loads( signal.value ) )
				except Exception as e:
					self.log.exception ('Failed to get robot program id from signal {}'.format( e ) )
					self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
						# TODO specific message
						Globals.LOCALIZATION.msg_DC_slave_measurement_series_not_found.format( signal.key )) )
					return False

				self.log.debug( 'START (robot_program_id {})'.format( self.robot_program_id ) )
				# TODO correct place here?
				if not Globals.SETTINGS.OfflineMode:
					gom.script.atos.switch_projector_light( enable=False )
				return True
			elif signal == Communicate.SIGNAL_MULTIROBOT_STATUS:
				del self.remote_todos.todos[0]
				if self.startup_done:
					self.log.debug( 'Status request' )
					# automation hardware status
					status = gom.script.automation.get_hardware_status()
					self.log.debug( 'Automation status error {}'.format( status['error'] ) )
					self.log.debug( 'Automation status warnings {}'.format( repr( status['warnings'] ) ) )
					if status['error'] != '' or len( status['warnings'] ) > 0:
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_MULTIROBOT_STATUS, pickle.dumps( status ) ) )
				else:
					self.log.debug( 'No status request - startup not done' )

			elif signal == Communicate.SIGNAL_MULTIROBOT_DONE:
				del self.remote_todos.todos[0]
				self.log.warning( 'Unexpected Sig MULTIROBOT DONE' )
				# TODO correct place here?
				if not Globals.SETTINGS.OfflineMode:
					gom.script.atos.switch_projector_light( enable=True )
				# TODO handshake?
#				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key ) ) )
			elif signal == Communicate.SIGNAL_FAILURE:
				del self.remote_todos.todos[0]
				# ignore
				self.log.error( 'Unexpected signal (FAILURE) received {}'.format( signal ) )

#			#inline specific start
#			elif signal == Communicate.SIGNAL_INLINE_PREPARE:
#				try:
#					value = pickle.loads(signal.value)
#				except:
#					value = []
#				del self.remote_todos.todos[0]
#				try:
#					gom.app.project
#				except:
#					self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, Globals.LOCALIZATION.msg_DC_slave_failed_open.format( signal.key )  ) )
#					return False
#				Globals.SETTINGS.AlreadyExecutionPrepared=False
#				if len(value):
#					result = startup.buildAdditionalResultInformation(''.join(value))
#					result = {**self.single_side_startupres, **result}
#					startup.parent.eval.eval.set_project_keywords(result)
#					gom.script.sys.set_project_keywords (
#						keywords = {'KioskInline_PLC_INFORMATION': ''.join(value)},
#						keywords_description = {'KioskInline_PLC_INFORMATION': 'KioskInterface PLC Information'} )
#					gom.script.sys.set_project_keywords (
#						keywords = {'KioskInline_PLC_INFORMATION_RAW1': value[0],
#								'KioskInline_PLC_INFORMATION_RAW2': value[1],
#								'KioskInline_PLC_INFORMATION_RAW3': value[2]},
#						keywords_description = {'KioskInline_PLC_INFORMATION_RAW1': 'KioskInterface PLC Information Raw1',
#											'KioskInline_PLC_INFORMATION_RAW2': 'KioskInterface PLC Information Raw2',
#											'KioskInline_PLC_INFORMATION_RAW3': 'KioskInterface PLC Information Raw3'} )
#				else:
#					pass #startup.parent.eval.eval.set_project_keywords(dict())
#				self.parent.eval.eval.save_project()
#				startup.parent.eval.eval.prepareTritop()
#				Globals.SETTINGS.AlreadyExecutionPrepared=True
#				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key )  ) )
#			elif signal == Communicate.SIGNAL_DEINIT_SENSOR:
#				del self.remote_todos.todos[0]
#				startup.parent.eval.eval.Sensor.deinitialize()
#			elif signal == Communicate.SIGNAL_CONTROL_RESULT_NOT_NEEDED:
#				try:
#					gom.script.sys.set_project_keywords (
#						keywords = {'KioskInline_PLC_RESULT_NOT_NEEDED': signal.get_value_as_string()},
#						keywords_description = {'KioskInline_PLC_RESULT_NOT_NEEDED': 'KioskInterface PLC Result Not Needed'} )
#				except:
#					pass
#				del self.remote_todos.todos[0]
			elif signal == Communicate.SIGNAL_CONTROL_CREATE_GOMSIC:
				del self.remote_todos.todos[0]
				Globals.DIALOGS.createGOMSic(self.getExternalSavePath())
			else:
				del self.remote_todos.todos[0]
				self.log.error( 'Unexpected signal received {}'.format( signal ) )
			return False

		return False


	def evaluation(self, eval, start_dialog_input):
		self.log.debug( 'Evaluation ProgID {} / PathExt {}'.format(
			self.robot_program_id, self.export_path_ext ) )
		errorlog = Verification.ErrorLog()
		response_signal = None
		if Globals.SETTINGS.MultiRobot_CalibRobotProgram == self.robot_program_id:
			# prepare temperature for calibration
			calibration = gom.app.project.measurement_series[ eval.Comp_calib_series[0] ]
			gom.script.calibration.edit_measurement_series ( 
				measurement_series = [calibration],
				temperature = self.temperature,
				room_temperature = self.temperature )
			gom.script.sys.set_stage_parameters ( measurement_temperature = self.temperature )

			# no export folder for calibration
			try:
				os.rmdir( os.path.join( self.getExternalSavePath(), self.export_path_ext ) )
			except Exception as e:
				self.log.warning( 'Delete export path failed: {}'.format( e ) )
			self.export_path_ext = None

		res = self.execute_robot_program( eval, self.robot_program_id, self.export_path_ext, errorlog )
		if res:
			if Globals.SETTINGS.MultiRobot_MemoryDebug:
				pproc = psutil.Process( os.getpid() )
				meminfo1 = pproc.memory_info().vms / 1024 / 1024
				meminfo2 = str( gom.app.memory_information.total )
				response = '{} - Memory PY {} / GOM {}'.format(
					Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID.key, meminfo1, meminfo2 )
			else:
				response = str( Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID.key )
			response_signal = Communicate.Signal( Communicate.SIGNAL_SUCCESS, response )
		else:
			self.log.error( errorlog.Error )
			response_signal =  Communicate.Signal( Communicate.SIGNAL_FAILURE,
				'{} - {}'.format( Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID.key, errorlog.Error ) )

		if Globals.SETTINGS.MultiRobot_CalibRobotProgram == self.robot_program_id:
			orig_cal = 'C:/ProgramData/GOM/atos-v75.calib'
			hyper_cal = 'C:/ProgramData/GOM/hyperatos-v75.calib'
			gom_windows_utils.copy_file( orig_cal, hyper_cal, False )

		temperature = None
		while len( self.remote_todos.todos ) > 0:
			signal = self.remote_todos.todos[0][0]
			self.log.debug( 'Executing signal {}'.format( signal ) )
			if signal == Communicate.SIGNAL_CONTROL_TEMPERATURE:
				del self.remote_todos.todos[0]
				try:
					temperature = float( signal.get_value_as_string() )
					self.log.debug( 'Control temperature: {} received'.format( temperature ) )
				except:
					self.log.error( 'Control: Failed to extract temperature: {}'.format( signal ) )
					continue
			# TODO what about receiving failure/abort at this moment?
			else:
				del self.remote_todos.todos[0]
				self.log.error( 'In mmt cycle - unexpected signal {}'.format( signal ) )

		if temperature is None:
			self.log.warning( 'No temperature received - default to last temperature' )
			temperature = self.temperature
		else:
			self.temperature = temperature

		if temperature is None:
			msg = 'No valid temperature available - measurement failed'
			errorlog.Error = msg
			self.log.error( msg )
			response_signal =  Communicate.Signal( Communicate.SIGNAL_FAILURE,
				'{} - {}'.format( Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID.key, errorlog.Error ) )
			res = False

		# mmt finished for INDI before hyperscale
		self.secondary_con.send_signal( response_signal )

		self.log.debug( 'Pre hyperscale PrgID {} ID {}'.format(
			self.robot_program_id, Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID ) )
		# TODO res / errorlog handling
		hyper_res = self.hyperscale( eval, temperature, errorlog )
		self.log.debug( 'Hyperscale res {} - {}'.format( hyper_res, errorlog.Error ) )

		# wait for MULTIROBOT DONE
		self.log.debug( 'Waiting for mmt cycle finished' )
		finished = False
		while True:
			while len( self.remote_todos.todos ) > 0:
				signal = self.remote_todos.todos[0][0]
				self.log.debug( 'Executing signal {}'.format( signal ) )
				if signal == Communicate.SIGNAL_MULTIROBOT_DONE:
					del self.remote_todos.todos[0]
					self.log.debug( 'Measurement cycle finished' )
					# TODO correct place here?
					if not Globals.SETTINGS.OfflineMode:
						gom.script.atos.switch_projector_light( enable=True )
					finished = True
					break
				else:
					del self.remote_todos.todos[0]
					self.log.error( 'End of mmt cycle - unexpected signal {}'.format( signal ) )

			if finished:
				break

			gom.script.sys.delay_script( time=0.2 )

		# automation hardware status
		status = gom.script.automation.get_hardware_status()
		self.log.debug( 'Automation status error {}'.format( status['error'] ) )
		self.log.debug( 'Automation status warnings {}'.format( repr( status['warnings'] ) ) )
		if status['error'] != '' or len( status['warnings'] ) > 0:
			self.secondary_con.send_signal( Communicate.Signal(
				Communicate.SIGNAL_MULTIROBOT_STATUS, pickle.dumps( status ) ) )

		# remove info of this cycle
		self.robot_program_id = None
		self.export_path_ext = None
		# return True/False to workflow
		return res

	def hyperscale(self, eval, temperature, errorlog):
		# HyperScale robot program active?
		if int( self.robot_program_id ) not in Globals.SETTINGS.MultiRobot_HyperScaleRobotPrograms:
			return True

		res = self.execute_robot_program( eval, self.robot_program_id, None, errorlog )

		hyper = None
		for a in eval.Comp_atos_series:
			if a.endswith( '_Hyperscale' ):
				hyper = gom.app.project.measurement_series[a]
				break

		gom.script.atos.start_lamp_recalibration( fast_mode=True )
		if temperature is not None and hyper is not None and Globals.SETTINGS.MultiRobot_CalcHyperScale:
			try:
				orig_cal = 'C:/ProgramData/GOM/atos-v75.calib'
				hyper_cal = 'C:/ProgramData/GOM/hyperatos-v75.calib'
				if not os.path.exists( hyper_cal ):
					gom_windows_utils.copy_file( orig_cal, hyper_cal, False )

				gom.script.calibration.compute_hyperscale_recalibration_from_file(
					calibration_file=hyper_cal,
					calibration_object=gom.app.sys_calibration_object_name,
					computation_flags_draft=['x', 'rx', 'rz'], 
					config_level='user',
					elements=hyper.measurements,
					hyper_scale_file_draft=os.path.join( Globals.SETTINGS.SavePath, 'hyperscale.xml' ),
					temperature_draft=temperature,
					use_center_trafo_draft=True )

				# log HyperScale files
				#filename='{}_hyperatos-v75_{}.calib'.format(
				#	time.strftime( '%Y_%m_%d_%H_%M_%S' ), temperature )
				#gom_windows_utils.copy_file(
				#	orig_cal, os.path.join( Globals.SETTINGS.SavePath, filename ), False )

			except Exception as e:
				errorlog.Error = 'Failed to compute hyper scale: {}'.format( e ) 

		gom.script.atos.wait_lamp_recalibration()

		if hyper is not None:
			gom.script.automation.clear_measuring_data( measurements=hyper.measurements )
		return res


	def start_evaluation(self, workflow_eval):
		return

	# TODO clean-up/test teach mode
	def prepare_measurement(self, evaluate):
		self.keep_project=False # reset keep_project flag
		# wait for save signal or failure
		def check():
			if not self.connected:
				return False
			if len(self.remote_todos.todos):
				signal = self.remote_todos.todos[0][0]
				if signal == Communicate.SIGNAL_SAVE:
					del self.remote_todos.todos[0]
					# no direct reply on success
					return True
				elif signal == Communicate.SIGNAL_FAILURE:
					del self.remote_todos.todos[0]
					return None
			return 'empty'
		res = None
		while True:
			try:
				res = check()
			except Exception as e:
				self.log.exception(str(e))
				self.secondary_con.send_signal(Communicate.SIGNAL_FAILURE)
				res = False
			if not isinstance(res, str):
				return res
			gom.script.sys.delay_script (time=0.1)
		return res
#
#
#		res = check()
#		if not isinstance(res, str):
#			return res
#		def handler(widget):
#			if widget=='timer':
#				res = check()
#				if not isinstance(res, str):
#					gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)
#		self.log.debug('prepare_measurement')
#		Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
#		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
#		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
#		try:
#			res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
#		except Exception as e:
#			self.log.exception(str(e))
#			self.secondary_con.send_signal(Communicate.SIGNAL_FAILURE)
#			res = None
#		return res

	# TODO clean-up/test teach mode
	def get_remote_todo(self):
		def check():
			try:
				if not self.connected:
					return False
				if len(self.remote_todos.todos):
					signal = self.remote_todos.todos[0][0]
					del self.remote_todos.todos[0]
					return signal
				return None
			except Exception as e:
				self.log.exception(e)
				raise e
			return None
		res = None
		while True:
			try:
				res = check()
			except Exception as e:
				self.log.exception(str(e))
				self.secondary_con.send_signal(Communicate.SIGNAL_FAILURE)
				res = False
			if res is not None:
				return res
			gom.script.sys.delay_script (time=0.1)
		return res


	# TODO clean-up/test teach mode
	def signal_start(self, evaluate):
		# always return False - this cancels evaluation in Kiosk

		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_SAVE.key )  ) )
		# endless loop for measuring
		if Globals.SETTINGS.Inline:
			ContextClass = NoContext
		else:
			ContextClass = Evaluate.MeasuringContext
		with ContextClass(evaluate,[],[],[],False) as context:
			while True:
				signal = self.get_remote_todo()
				if signal == False: # disconnect
					return False
				if signal == Communicate.SIGNAL_FAILURE:
					return False
				if signal == Communicate.SIGNAL_MULTIROBOT_MEASUREMENTS:
					if Globals.SETTINGS.Inline:
						self.log.error( 'Inline Mode: Error - Received measurement names' )
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_FAILURE, str( Communicate.SIGNAL_MULTIROBOT_MEASUREMENTS.key ) ) )
						return False
					try:
						value = pickle.loads(signal.value)
						mlist_name = value[0]
						ms_names = value[1]
						mlist = gom.app.project.measurement_series[mlist_name]
						measurements = [mlist.measurements[m] for m in ms_names]
					except Exception as e:
						self.log.exception ('Failed to get measurements from signal {}'.format(e))
						self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
							Globals.LOCALIZATION.msg_DC_slave_measurement_series_not_found.format( signal.key )) )
						return False

					res = self.execute_measurement( evaluate, mlist, measurements )
					if res:
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_MULTIROBOT_MEASUREMENTS.key ) ) )
					else:
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_FAILURE, str( Communicate.SIGNAL_MULTIROBOT_MEASUREMENTS.key ) ) )

				if signal == Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID:
					if not Globals.SETTINGS.Inline:
						self.log.error( 'NOT Inline Mode: Received inline robot program id' )
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_FAILURE, str( Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID.key ) ) )
						return False
					try:
						robot_program_id = int( pickle.loads( signal.value ) )
					except Exception as e:
						self.log.exception ('Failed to get robot program id from signal {}'.format(e))
						self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
							# TODO specific message
							Globals.LOCALIZATION.msg_DC_slave_measurement_series_not_found.format( signal.key ) ) )
						return False

					errorlog = Verification.ErrorLog()
					res = self.execute_robot_program( evaluate, robot_program_id, self.export_path_ext, errorlog )
					self.log.debug('Post exec robprg PrgID {} ID {}'.format(robot_program_id, Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID))
					if res:
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID.key ) ) )
						if int(robot_program_id) == 21: # HyperScale
							if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID == 0:
								res = self.execute_robot_program( evaluate, robot_program_id, None, errorlog )
					else:
						self.secondary_con.send_signal(
							Communicate.Signal( Communicate.SIGNAL_FAILURE,
								'{} - {}'.format( Communicate.SIGNAL_MULTIROBOT_INLINE_PRGID.key, errorlog.Error ) ) )

				elif signal == Communicate.SIGNAL_MULTIROBOT_CALIB_SERIES:
					if Globals.SETTINGS.Inline:
						self.log.error( 'Inline Mode: Received calibration measurement series' )
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_FAILURE, str( Communicate.SIGNAL_MULTIROBOT_CALIB_SERIES.key ) ) )
						return False
					if evaluate.Calibration.MeasureList is not None:
						res = self.execute_measurement( evaluate, evaluate.Calibration.MeasureList, [] )
					else:
						res = False
					if res:
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_MULTIROBOT_CALIB_SERIES.key ) ) )
					else:
						self.secondary_con.send_signal( Communicate.Signal(
							Communicate.SIGNAL_FAILURE, str( Communicate.SIGNAL_MULTIROBOT_CALIB_SERIES.key ) ) )

				elif signal == Communicate.SIGNAL_MULTIROBOT_DONE:
					if evaluate.Statistics is not None:
						evaluate.Statistics.Logger.set_row(
							'EvaluationTime', StatisticalLog.StatisticHelper.mark_time( evaluate.Statistics ) )
						evaluate.Statistics.log_end( force_flush = False )
						evaluate.Statistics.store_values()
					break

		return False

	# TODO clean-up/test teach mode
	def execute_measurement(self, evaluate, mlist, measurements):
		if mlist is None:
			return False
		try:
			gom.script.automation.clear_measuring_data ( measurements = measurements )
		except:
			pass
		if mlist.type != 'photogrammetry_measurement_series':
			if not startup.parent.eval.eval.Sensor.check_for_reinitialize():
				return False
		if mlist.type != 'calibration_measurement_series':
			if evaluate.check_calibration_recommendation_temperature(True):
				self.secondary_con.send_signal( Communicate.SIGNAL_CONTROL_CALIBRATION_RECOMMENDED)
		if evaluate.Statistics is not None:
			StatisticalLog.StatisticHelper.mark_time( evaluate.Statistics )

		# switch to original alignment for measurements
		original_alignment = evaluate.get_original_alignment()
		gom.script.manage_alignment.set_alignment_active (
			cad_alignment=original_alignment )

		if mlist.type == 'photogrammetry_measurement_series':
			res = evaluate.Tritop.perform_measurement(mlist, measurements)
			if evaluate.Statistics is not None:
				evaluate.Statistics.log_measurement_series()
		elif mlist.type == 'atos_measurement_series':
			gom.script.atos.set_acquisition_parameters (do_transformation_check=False)
			res = evaluate.Atos.perform_measurement(mlist, measurements)
			if evaluate.Statistics is not None:
				evaluate.Statistics.log_measurement_series()
			if res == Verification.DigitizeResult.Failure:
				return False
			return True

		elif mlist.type == 'calibration_measurement_series':
			res = evaluate.Calibration.calibrate( reason = 'force' )
			if evaluate.Statistics is not None:
				evaluate.Statistics.log_measurement_series()
		return res

	def execute_robot_program(self, evaluate, robot_program_id, path_ext, errorlog=None ):
		# switch to original alignment for measurements
		original_alignment = evaluate.get_original_alignment()
		gom.script.manage_alignment.set_alignment_active (
			cad_alignment=original_alignment )

		res = evaluate.Atos.perform_robot_program( robot_program_id, path_ext, errorlog )
		if res == Verification.DigitizeResult.Failure:
			return False
		return True


	def onMoveDecisionNeeded(self, error, errortext1, errortext2):
		self.log.error( 'Move decision call not allowed' )
		return False


class NoContext:
	'''Empty MeasureContext Variant for Inline Mode
	'''
	def __init__(self, parent, comp_photo_series, comp_atos_series, comp_calib_series, will_calibration_be_performed):
		pass

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		pass