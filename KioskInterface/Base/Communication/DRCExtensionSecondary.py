# -*- coding: utf-8 -*-
# Script: Kiosk Extension script for Double-Robot-Cell Secondary side
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


from ..Misc import Utils, Globals
from . import AsyncClient, AsyncServer, Communicate
from ..Measuring import Verification, Measure
from .. import Evaluate

import os
import time
import gom_windows_utils
import gom
import pickle

class DRCExtensionSecondary( Utils.GenericLogClass ):
	secondary_con = None
	remote_todos = None
	connected = False
	update_startdialog_text=True
	selected_tritop_mlists = []
	selected_atos_mlists = []
	keep_project=False
	single_side_startupres = {}
	remote_failure = False


	def __init__(self, parent, logger):
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.secondary_con = AsyncServer.CommunicationServer( self.baselog, self,
			'', Globals.SETTINGS.DoubleRobot_SecondaryHostPort, {} ) # bind to all interfaces
		self.secondary_con.AllowOneOnly = True
		self.remote_todos = Communicate.RemoteTodos( self.baselog )
		self.log.info("DRC Extension loaded (Secondary)")

	def PrimarySideActive(self):
		return False
	def SecondarySideActive(self):
		return self.secondary_con is not None and not Globals.FEATURE_SET.DRC_UNPAIRED and not Globals.FEATURE_SET.DRC_SINGLE_SIDE# and self.connected
	def SecondarySideActiveForError(self):
		return self.secondary_con is not None and not Globals.FEATURE_SET.DRC_UNPAIRED# and self.connected

	def check_connected_and_alive( self, timeout=60.0 ):
		stime = time.time()
		# clear a possibly stale alive info
		self.secondary_con.clear_alive()
		request_sent = False

		while True:
			ctime = time.time()
			if ctime - stime > timeout:
				# timeout
				return False

			if len( self.secondary_con.handlers ) == 0:
				# no connection
				gom.script.sys.delay_script( time=1.0 )
				continue

			if not self.secondary_con.handlers[0].handshaked:
				# connection not handshaked
				gom.script.sys.delay_script( time=1.0 )
				continue

			if not request_sent:
				# send "alive" request
				signal = Communicate.Signal( Communicate.SIGNAL_CLIENT_ALIVE )
				self.secondary_con.send_signal( signal )
				request_sent = True
				gom.script.sys.delay_script( time=1.0 )
				continue

			if len( self.secondary_con.handlers ) > 0 and self.secondary_con.handlers[0].alive_ts is not None:
				self.log.debug('Answer to alive request (time current {} alive {})'.format(
					ctime, self.secondary_con.handlers[0].alive_ts ) )
				return True

			# no answer to "alive" request
			print('no answer')
			gom.script.sys.delay_script( time=1.0 )

		return True

	def globalTimerCheck (self, value):
		try:
			self.collect_pkts()
		except:
			pass

	def on_first_connection(self):
		self.update_startdialog_text = True
		Globals.SETTINGS.InAsyncAbort = False

	def on_connection_lost(self):
		self.update_startdialog_text=True
		self.remote_todos.clear()
		
	def collect_pkts(self):
		if self.secondary_con is None:
			return
		while self.secondary_con.process_signals():
			pass
		was_connected = self.connected
		self.connected = self.secondary_con.Handshaked
		if was_connected and not self.connected:
			self.on_connection_lost()
		elif not was_connected and self.connected:
			self.on_first_connection()
		for sig in self.secondary_con.pop_results():
			# print('collect_pkts '+str(sig))
			if sig == Communicate.SIGNAL_INLINE_DRC_MOVEDECISION:
				# no real todo
				if Globals.SETTINGS.WaitingForMoveDecision:
					Globals.SETTINGS.MoveDecisionAfterFaultState = int(sig.get_value_as_string())
					Globals.SETTINGS.InAsyncAbort = False
					self.log.debug('triggering async abort')
					gom.app.abort = True
			elif sig == Communicate.SIGNAL_INLINE_DRC_ABORT:
				if Globals.SETTINGS.AllowAsyncAbort:
					self.log.debug('direct abort')
					gom.app.abort = True
				else:
					Globals.SETTINGS.InAsyncAbort = True
			else:
				# Ignore failure when UNPAIRED
				# TODO: Ignore all packets here except PAIR?
				if sig == Communicate.SIGNAL_FAILURE and Globals.FEATURE_SET.DRC_UNPAIRED:
					continue
				self.remote_failure = True
				self.remote_todos.append_todo(sig)
				if sig == Communicate.SIGNAL_FAILURE:
					self.log.debug('got failure')
					if Globals.SETTINGS.AllowAsyncAbort:
						self.log.debug('direct abort')
						gom.app.abort = True
					else:
						Globals.SETTINGS.InAsyncAbort = True

	def other_side_still_active(self):
		# only checked in DRC Primary
		return False

	def send_inline_signal(self, signal):
		self.secondary_con.send_signal(Communicate.Signal(Communicate.SIGNAL_INLINE_DRC_SECONDARY_INST_DATA, pickle.dumps( [signal.key, signal.value] )))

	def sendStartFailure(self, text):
		if Globals.FEATURE_SET.DRC_SINGLE_SIDE:
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, text.format( Communicate.SIGNAL_SINGLE_SIDE.key ) ) )
		else:
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, text.format( Communicate.SIGNAL_START.key ) ) )

	def sendStartSuccess(self):
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_START.key ) ) )

	def sendSingleSideDone(self):
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_SINGLE_SIDE.key ) ) )

	def sendExit(self):
		if self.secondary_con is not None:
			self.secondary_con.send_signal(Communicate.SIGNAL_FAILURE)
			
	def send_software_drc_success(self):
		if self.secondary_con is not None:
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_OPEN_SOFTWARE_DRC.key ) ) )
	
	def send_software_drc_failure(self, text):
		if self.secondary_con is not None:
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, text ) )

	def check_start_signals(self, startup):
		if not len(self.remote_todos.todos):
			return False
		signal = self.remote_todos.todos[0][0]
		self.log.debug('executing signal {}'.format(signal))
		if signal == Communicate.SIGNAL_OPEN or signal == Communicate.SIGNAL_OPEN_INIT:
			try:
				gom.app.project
			except:
				Globals.SETTINGS.CurrentTemplate = None
				Globals.SETTINGS.CurrentTemplateCfg = None
			del self.remote_todos.todos[0]
			template=''
			template_cfg = ''
			serial=''
			try:
				value = pickle.loads(signal.value)
				template = value[0]
				template_cfg = value[1]
				if len(value) > 2:
					serial = value[2]
			except:
				template = signal.get_value_as_string()
			self.single_side_startupres = {'serial': serial}
			startup.dialog.inputSerial.value=serial
			self.log.debug(self.single_side_startupres)
			if Globals.SETTINGS.CurrentTemplate != template or Globals.SETTINGS.CurrentTemplateCfg != template_cfg:
				Globals.SETTINGS.CurrentTemplate = template
				Globals.SETTINGS.CurrentTemplateCfg = template_cfg
				if Globals.SETTINGS.CurrentTemplate.endswith('.ginspect'):
					gom.script.sys.close_project()
					i=0
					while i<15:
						try:
							gom.script.sys.load_project(file=os.path.join( Globals.SETTINGS.DoubleRobot_TransferPath, Globals.SETTINGS.CurrentTemplate))
							break
						except Exception as e:
							self.log.exception('Failed to load project {}'.format(e))
						gom.script.sys.delay_script (time=1)
						i+=1
					try:
						gom.app.project
					except:
						Globals.SETTINGS.CurrentTemplate = None
						Globals.SETTINGS.CurrentTemplateCfg = None
					Globals.FEATURE_SET.ONESHOT_MODE = True
					Globals.FEATURE_SET.DRC_ONESHOT = True # for compatibility
				else:
					Globals.FEATURE_SET.ONESHOT_MODE = False
					Globals.FEATURE_SET.DRC_ONESHOT = False # for compatibility
					startup.open_template(True)
			if signal == Communicate.SIGNAL_OPEN_INIT:
				with Measure.TemporaryWarmupDisable(startup.parent.eval.eval.Sensor) as warmup:
					startup.parent.eval.eval.Sensor.check_for_reinitialize()
			if Globals.SETTINGS.CurrentTemplate is not None:
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key )  ) )
				if Globals.SETTINGS.Inline:
					Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_TEMPLATE, str(1)))
			else:
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, Globals.LOCALIZATION.msg_DC_slave_failed_open.format( signal.key ) ) )

		elif signal == Communicate.SIGNAL_CLOSE_TEMPLATE:
			del self.remote_todos.todos[0]
			gom.script.sys.close_project()
			Globals.SETTINGS.CurrentTemplate = None
			Globals.SETTINGS.CurrentTemplateCfg = None
			Globals.SETTINGS.AlreadyExecutionPrepared=False
			if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
				startup.dialog.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key )  ) )
		elif signal == Communicate.SIGNAL_UNPAIR:
			connection_text = ' (Connected)' if self.connected else ' (Disconnected)'
			del self.remote_todos.todos[0]
			if int(signal.get_value_as_string()):
				Globals.FEATURE_SET.DRC_UNPAIRED=True
				pair_text = 'Unpaired'
				if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
					startup.dialog.buttonTemplateChoose.enabled = True
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key )  ) )
			else:
				Globals.FEATURE_SET.DRC_UNPAIRED=False
				pair_text= 'Paired'
				if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
					startup.dialog.buttonTemplateChoose.enabled = False
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key )  ) )
			if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
				startup.dialog.button_extension.text = pair_text + connection_text
		elif signal == Communicate.SIGNAL_START:
			del self.remote_todos.todos[0]
			# no direct reply
			return True
		elif signal == Communicate.SIGNAL_SINGLE_SIDE:
			try:
				start_values = pickle.loads(signal.value)
			except:
				start_values= {}
			self.single_side_startupres = {**self.single_side_startupres, **start_values}
			self.log.debug(self.single_side_startupres)
			del self.remote_todos.todos[0]
			Globals.FEATURE_SET.DRC_SINGLE_SIDE = True
			# no direct reply
			return True
		elif signal == Communicate.SIGNAL_FAILURE:
			del self.remote_todos.todos[0]
			# ignore
		#inline specific start
		elif signal == Communicate.SIGNAL_INLINE_PREPARE:
			try:
				value = pickle.loads(signal.value)
			except:
				value = []
			del self.remote_todos.todos[0]
			try:
				gom.app.project
			except:
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, Globals.LOCALIZATION.msg_DC_slave_failed_open.format( signal.key )  ) )
				return False
			Globals.SETTINGS.AlreadyExecutionPrepared=False
			if len(value):
				result = startup.buildAdditionalResultInformation(''.join(value))
				result = {**self.single_side_startupres, **result}
				startup.parent.eval.eval.set_project_keywords(result)
				gom.script.sys.set_project_keywords (
					keywords = {'KioskInline_PLC_INFORMATION': ''.join(value)},
					keywords_description = {'KioskInline_PLC_INFORMATION': 'KioskInterface PLC Information'} )
				gom.script.sys.set_project_keywords (
					keywords = {'KioskInline_PLC_INFORMATION_RAW1': value[0],
							'KioskInline_PLC_INFORMATION_RAW2': value[1],
							'KioskInline_PLC_INFORMATION_RAW3': value[2]},
					keywords_description = {'KioskInline_PLC_INFORMATION_RAW1': 'KioskInterface PLC Information Raw1',
										'KioskInline_PLC_INFORMATION_RAW2': 'KioskInterface PLC Information Raw2',
										'KioskInline_PLC_INFORMATION_RAW3': 'KioskInterface PLC Information Raw3'} )
			else:
				pass #startup.parent.eval.eval.set_project_keywords(dict())
			self.parent.eval.eval.save_project()
			if not startup.parent.eval.eval.Sensor.check_for_reinitialize():
				return
			startup.parent.eval.eval.prepareTritop()
			Globals.SETTINGS.AlreadyExecutionPrepared=True
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key )  ) )
		elif signal == Communicate.SIGNAL_DEINIT_SENSOR:
			del self.remote_todos.todos[0]
			startup.parent.eval.eval.Sensor.deinitialize()
		elif signal == Communicate.SIGNAL_CONTROL_RESULT_NOT_NEEDED:
			try:
				gom.script.sys.set_project_keywords (
					keywords = {'KioskInline_PLC_RESULT_NOT_NEEDED': signal.get_value_as_string()},
					keywords_description = {'KioskInline_PLC_RESULT_NOT_NEEDED': 'KioskInterface PLC Result Not Needed'} )
			except:
				pass
			del self.remote_todos.todos[0]
		elif signal == Communicate.SIGNAL_CONTROL_CREATE_GOMSIC:
			Globals.DIALOGS.createGOMSic(Globals.SETTINGS.DoubleRobot_TransferPath)
			del self.remote_todos.todos[0]
		elif signal == Communicate.SIGNAL_OPEN_SOFTWARE_DRC:
			self.log.debug('Got software DRC connection')
			gom.script.sys.close_project()
			Globals.SETTINGS.SoftwareDRCMode = signal.get_value_as_string()
			del self.remote_todos.todos[0]
			return True
		else:
			self.log.error('Invalid signal: {}'.format(signal))
			del self.remote_todos.todos[0]
		return False

	##### StartDialog part
	def start_dialog_handler(self, startup, widget):
		if self.secondary_con is None:
			return True
		pair_text = 'Unpaired' if Globals.FEATURE_SET.DRC_UNPAIRED else 'Paired'
		connection_text = ' (Connected)' if self.connected else ' (Disconnected)'
		if widget == 'initialize':
			if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
				startup.dialog.button_extension.text = pair_text + connection_text
			if Globals.DIALOGS.has_widget( startup.partdialog, 'button_extension' ):
				startup.partdialog.button_extension.text = pair_text + connection_text
			if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
				startup.dialog.buttonTemplateChoose.enabled = False
			Globals.FEATURE_SET.DRC_SINGLE_SIDE = False # always reset during start dialog

		elif widget == 'timer':
			if self.update_startdialog_text:
				if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
					startup.dialog.button_extension.text = pair_text + connection_text
				if Globals.DIALOGS.has_widget( startup.partdialog, 'button_extension' ):
					startup.partdialog.button_extension.text = pair_text + connection_text
				self.update_startdialog_text=False
			if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
				if not Globals.FEATURE_SET.DRC_UNPAIRED:
					startup.dialog.buttonTemplateChoose.enabled = False
				else:
					startup.dialog.buttonTemplateChoose.enabled = True

			if self.check_start_signals(startup):
				gom.script.sys.close_user_defined_dialog( dialog = startup.dialog, result = True )
				return False # exit handler

		elif isinstance(widget, str):
			pass
		elif widget.name == 'button_extension':
			Globals.FEATURE_SET.DRC_UNPAIRED = not Globals.FEATURE_SET.DRC_UNPAIRED
			if Globals.FEATURE_SET.DRC_UNPAIRED:
				pair_text = 'Unpaired'
				if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
					startup.dialog.buttonTemplateChoose.enabled = True
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_UNPAIR, '1' ) )
			else:
				pair_text= 'Paired'
				if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
					startup.dialog.buttonTemplateChoose.enabled = False
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_UNPAIR, '0' ) )
			startup.dialog.button_extension.text = pair_text + connection_text

		return True

	def after_template_opened(self, startup, opened_template, multipart):
		pass

	def precheck_template(self):
		return True

	##### Evaluate part
	def start_evaluation(self, workflow_eval):
		if Globals.FEATURE_SET.DRC_SINGLE_SIDE:
			self.log.debug(self.single_side_startupres)
			workflow_eval.choosed = self.single_side_startupres

		self.remote_failure = False

	def reuse_photogrammetry(self, evaluate):
		if not self.SecondarySideActive():
			return
		if not Globals.SETTINGS.Inline:
			return
		def check():
			if not self.connected:
				return None
			if len(self.remote_todos.todos):
				signal = self.remote_todos.todos[0][0]
				self.log.debug(signal)
				if signal == Communicate.SIGNAL_FAILURE:
					del self.remote_todos.todos[0]
					return None
				elif signal == Communicate.SIGNAL_REFXML:
					del self.remote_todos.todos[0]
					self.import_tritop_slave(evaluate, signal)
					return True
				elif signal == Communicate.SIGNAL_CLOSE_TEMPLATE:
					#del self.remote_todos.todos[0] # do not delete todo
					return None
				elif signal == Communicate.SIGNAL_SINGLE_SIDE:
					#del self.remote_todos.todos[0] # do not delete todo
					return None
				else:
					self.log.error('Invalid signal: {}'.format(signal))
					del self.remote_todos.todos[0]
					return None # should never happen
			return 'empty'
		res = check()
		if not isinstance(res, str):
			return res
		def handler(widget):
			if widget=='timer':
				res = check()
				if not isinstance(res, str):
					gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)

		Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
		try:
			res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
		except Exception as e:
			self.log.exception(str(e))
			self.secondary_con.send_signal(Communicate.SIGNAL_FAILURE)
			res = None
		return res


	def prepare_measurement(self, evaluate):
		self.log.debug('Globals.FEATURE_SET.DRC_SINGLE_SIDE {}'.format(Globals.FEATURE_SET.DRC_SINGLE_SIDE))
		if not self.SecondarySideActive():
			return True
		self.keep_project = False # reset keep_project flag
		# wait for save signal or failure
		def check():
			if not self.connected:
				return False
			if len(self.remote_todos.todos):
				signal = self.remote_todos.todos[0][0]
				if signal == Communicate.SIGNAL_SAVE:
					del self.remote_todos.todos[0]
					tritop_measurements=[]
					atos_measurements=[]
					mlists = signal.get_value_as_string().split(Communicate.MLIST_SEPARATOR)
					for ml in mlists:
						if not len(ml):
							# print('empty')
							continue
						if ml not in evaluate.Comp_photo_series and ml not in evaluate.Comp_atos_series:
							self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
								Globals.LOCALIZATION.msg_DC_slave_measurement_series_not_comp.format( signal.key ) ) )
							return False
						try:
							if gom.app.project.measurement_series[ml].type=='atos_measurement_series':
								atos_measurements.append(ml)
							else:
								tritop_measurements.append(ml)
						except:
							self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
								Globals.LOCALIZATION.msg_DC_slave_measurement_series_not_found.format( signal.key ) ) )
							return False

					evaluate.Comp_photo_series = tritop_measurements
					evaluate.Comp_atos_series = atos_measurements
					self.selected_tritop_mlists = tritop_measurements
					self.selected_atos_mlists = atos_measurements
					# no direct reply on success
					return True
				elif signal == Communicate.SIGNAL_FAILURE:
					del self.remote_todos.todos[0]
					return False
				elif signal == Communicate.SIGNAL_REFXML:
					del self.remote_todos.todos[0]
					self.import_tritop_slave(evaluate, signal)
				elif signal == Communicate.SIGNAL_ALIGNMENT_ITER:
					del self.remote_todos.todos[0]
					evaluate.alignment_mseries = signal.get_value_as_string()
					if not evaluate.alignment_mseries:
						evaluate.alignment_mseries = None
					else:
						try:
							gom.app.project.measurement_series[evaluate.alignment_mseries]
						except:	
							self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
								Globals.LOCALIZATION.msg_DC_slave_measurement_series_not_found.format( signal.key ) ) )
							return False
				else:
					self.log.error('Invalid signal: {}'.format(signal))
					del self.remote_todos.todos[0]

			return 'empty'
		res = check()
		if not isinstance(res, str):
			return res
		def handler(widget):
			if widget=='timer':
				res = check()
				if not isinstance(res, str):
					gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)

		Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
		try:
			res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
		except Exception as e:
			self.log.exception(str(e))
			self.secondary_con.send_signal(Communicate.SIGNAL_FAILURE)
			res = False
		return res

	def set_measurements(self, evaluate, series):
		return True

	def signal_start(self, evaluate):
		if not self.SecondarySideActive():
			return True
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_SAVE.key )  ) )
		def check():
			if not self.connected:
				return False
			if len(self.remote_todos.todos):
				signal = self.remote_todos.todos[0][0]
				if signal == Communicate.SIGNAL_MEASURE:
					execution_mode = int(signal.get_value_as_string())
					if execution_mode == 0:
						evaluate.setExecutionMode(Evaluate.ExecutionMode.Full)
					elif execution_mode == 1:
						evaluate.setExecutionMode(Evaluate.ExecutionMode.ForceCalibration)
					elif execution_mode == 2:
						evaluate.setExecutionMode(Evaluate.ExecutionMode.ForceTritop)
					elif execution_mode == 3:
						evaluate.setExecutionMode(Evaluate.ExecutionMode.PerformAdditionalCalibration)
					del self.remote_todos.todos[0]
					# no direct reply on success
					return True
				elif signal == Communicate.SIGNAL_FAILURE:
					del self.remote_todos.todos[0]
					return False
				else:
					self.log.error('Invalid signal: {}'.format(signal))
					del self.remote_todos.todos[0]
			return 'empty'
		res = check()
		if not isinstance(res, str):
			return res
		def handler(widget):
			if widget=='timer':
				res = check()
				if not isinstance(res, str):
					gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)

		Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
		try:
			res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
		except:
			res = None
		return res


	def sendMeasureFailure(self):
		if self.SecondarySideActive():
			self.log.debug( 'Failure triggered from remote: {}'.format( self.remote_failure ) )
			if Globals.SETTINGS.InAsyncAbort:
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_FAILURE.key )  ) )
			else:
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, str( Communicate.SIGNAL_MEASURE.key )  ) )
				def check():
					if not self.connected:
						return False
					if len(self.remote_todos.todos):
						signal = self.remote_todos.todos[0][0]
						if signal == Communicate.SIGNAL_SUCCESS:
							del self.remote_todos.todos[0]
							return True
						elif signal == Communicate.SIGNAL_FAILURE:
							del self.remote_todos.todos[0]
							return False
						else:
							self.log.error('Invalid signal: {}'.format(signal))
							del self.remote_todos.todos[0]
					return 'empty'
				res = check()
				if not isinstance(res, str):
					return res
				def handler(widget):
					if widget=='timer':
						res = check()
						if not isinstance(res, str):
							gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)

				Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
				Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
				Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
				try:
					res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
				except:
					res = None
				return res

	def export_tritop_slave(self,evaluate):
		if ( not os.path.exists( Globals.SETTINGS.DoubleRobot_TransferPath ) ):
			os.makedirs( Globals.SETTINGS.DoubleRobot_TransferPath )  # recreate it
		file_name = '{}-{}.gelements'.format(Globals.SETTINGS.ProjectName,time.strftime( Globals.SETTINGS.TimeFormatProject ))
		temp_file = os.path.join( Globals.SETTINGS.SavePath, file_name )
		#export measurement series locally
		mlists = [gom.app.project.measurement_series[m] for m in evaluate.Comp_photo_series]
		gom.script.sys.export_selected_elements_only(elements=mlists, file=temp_file )

		# copy into transfer folder and signal file name
		dest_file = os.path.normpath(os.path.join( Globals.SETTINGS.DoubleRobot_TransferPath, file_name ) )
		error = False
		for i in range(10):
			try:
				gom_windows_utils.copy_file( temp_file, dest_file, False )
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_EXPORTEDFILE, os.path.basename( file_name )  ) )
				os.unlink(temp_file)
				error = False
				break
			except RuntimeError as e:
				self.log.error( 'failed to copy file (retry:{})  {} to {}: {}'.format( i, temp_file, dest_file, e ) )
				error = str(e)
				gom.script.sys.delay_script(time=2)
		if error:
			self.keep_project=True
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
				Globals.LOCALIZATION.msg_DC_slave_failed_to_copy.format( Communicate.SIGNAL_EXPORTEDFILE.key, dest_file, error ) ) )
			return False
		return True

	def import_tritop_slave(self, evaluate, signal):
		filename = signal.get_value_as_string()
		if gom.app.project.is_part_project and not Globals.SETTINGS.OfflineMode:
			# use_external_reference_points below would be ignored
			#	when project also contains photogrammetry measurement data
			gom.script.automation.clear_measuring_data(
				measurements=gom.app.project.measurement_series.filter( 'type=="photogrammetry_measurement_series"' ) )
			# Do not collect further points:
			#   additional points would trigger new photogrammetry calc
			#   connection between atos mmts and new points is lost on import project on primary (producing errors)
			gom.script.atos.set_acquisition_parameters( reference_points_collection_type='dont_collect' )
		if filename and filename != 'by_robot_position': # can be empty
			filepath = os.path.join( Globals.SETTINGS.DoubleRobot_TransferPath, signal.get_value_as_string())
			master_series = None
			for ms in gom.app.project.measurement_series.filter( 'type=="photogrammetry_measurement_series"' ):
				if ms.get('reference_points_master_series') is None:
					master_series = ms
					break
			evaluate.Tritop.import_photogrammetry(master_series, forced_refxml=filepath)
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key ) ) )

	def sync_for_iteration_in_tritop(self, evaluate):
		if not self.SecondarySideActive():
			return True
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_MEASURE.key )  ) )

		if not self.export_tritop_slave(evaluate):
			return False

		return True

	def reference_cube_check(self):
		return True

	def tritop_continuation(self, evaluate, res):
		self.log.debug( 'secondary tritop_continuation status {}'.format( res ) )
		if not self.SecondarySideActive():
			return res

		self.log.info('Waiting for next measure signal')
		def check():
			if not self.connected:
				return False
			if len(self.remote_todos.todos):
				signal = self.remote_todos.todos[0][0]
				if signal == Communicate.SIGNAL_REFXML:
					del self.remote_todos.todos[0]
					self.import_tritop_slave(evaluate, signal)
				elif signal == Communicate.SIGNAL_MEASURE:
					del self.remote_todos.todos[0]
					# no direct reply on success
					return True
				elif signal == Communicate.SIGNAL_FAILURE:
					self.log.debug('failure')
					del self.remote_todos.todos[0]
					return False
				elif signal == Communicate.SIGNAL_RESTART:
					del self.remote_todos.todos[0]
					self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_RESTART.key )  ) )
					return None
				else:
					self.log.error('Invalid signal: {}'.format(signal))
					del self.remote_todos.todos[0]
			return 'empty'
		res = check()
		if res != 'empty':
			return res
		def handler(widget):
			if widget=='timer' or widget=='initialize':
				res = check()
				if res != 'empty':
					gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)

		Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
		Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
		try:
			res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
		except Exception as e:
			self.log.exception(str(e))
			self.secondary_con.send_signal(Communicate.SIGNAL_FAILURE)
			res = False
		return res


	def wait_for_export_signal( self, evaluate ):
		def check():
			if not self.connected:
				return False
			if len( self.remote_todos.todos ):
				signal = self.remote_todos.todos[0][0]
				if signal == Communicate.SIGNAL_EXPORTEDFILE:
					del self.remote_todos.todos[0]
					# no direct reply on success
					return True
				elif signal == Communicate.SIGNAL_FAILURE:
					del self.remote_todos.todos[0]
					return False
				else:
					self.log.error('Invalid signal: {}'.format(signal))
					del self.remote_todos.todos[0]
			return 'empty'
		res = check()
		if res=='empty':
			def handler( widget ):
				if widget=='timer' or widget=='initialize':
					res = check()
					if res != 'empty':
						gom.script.sys.close_user_defined_dialog( dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res )
	
			Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
			try:
				res = gom.script.sys.show_user_defined_dialog( dialog=Globals.DIALOGS.DRC_WAIT_DIALOG )
			except Exception as e:
				self.log.exception( str( e ) )
				self.secondary_con.send_signal( Communicate.SIGNAL_FAILURE )
				res = False
		return res


	def export_atos_slave(self, evaluate, final_run):
		try:
			gom.script.sys.save_project()
		except:
			pass
		if final_run and not self.wait_for_export_signal( evaluate ):
			return False
		if ( not os.path.exists( Globals.SETTINGS.DoubleRobot_TransferPath ) ):
			os.makedirs( Globals.SETTINGS.DoubleRobot_TransferPath )  # recreate it
		
		if final_run and gom.app.project.is_part_project:
			temp_file = gom.app.project.get ( 'project_file' )
			gom.script.sys.close_project()
			file_name = os.path.basename(temp_file)
		else:
			file_name = '{}-{}.gelements'.format(Globals.SETTINGS.ProjectName,time.strftime( Globals.SETTINGS.TimeFormatProject ))
			temp_file = os.path.join( Globals.SETTINGS.SavePath, file_name )
			# export measurement series locally
			mlists = [gom.app.project.measurement_series[m] for m in evaluate.Comp_atos_series]
			gom.script.sys.export_selected_elements_only(elements=mlists, file=temp_file )

		# copy into transfer folder and signal file name
		dest_file = os.path.normpath(os.path.join( Globals.SETTINGS.DoubleRobot_ClientTransferPath, file_name ) )
		error = False
		for i in range(10):
			try:
				gom_windows_utils.copy_file( temp_file, dest_file, False )
				self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_EXPORTEDFILE, os.path.basename( file_name )  ) )
				os.unlink(temp_file)
				error = False
				break
			except RuntimeError as e:
				self.log.error( 'failed to copy file (retry:{})  {} to {}: {}'.format( i, temp_file, dest_file, e ) )
				error = str(e)
				gom.script.sys.delay_script(time=2)

		if error:
			self.keep_project=True
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
				Globals.LOCALIZATION.msg_DC_slave_failed_to_copy.format( Communicate.SIGNAL_EXPORTEDFILE.key, dest_file, error ) ) )
			return False
		return True

	def wait_for_atos(self, evaluate, measurecontext):
		if not self.SecondarySideActive():
			return True

		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_MEASURE.key )  ) )
		if not len(evaluate.Comp_atos_series):
			return True

		return self.export_atos_slave( evaluate, final_run=True )

	def delete_slave_project(self, evaluate):
		if self.keep_project:
			try:
				gom.script.sys.save_project()
				gom.script.sys.close_project()
			except:
				pass
		else:
			try:
				projectfile = gom.app.project.get ( 'project_file' )
			except:
				projectfile = None
			if projectfile is not None:
				gom.script.sys.close_project()
				if not projectfile.endswith( '.project_template' ):
					if ( os.path.exists( projectfile ) ):
						os.unlink( projectfile )
		try:
			gom.app.project
		except:
			Globals.SETTINGS.CurrentTemplate = None
			Globals.SETTINGS.CurrentTemplateCfg = None


	def sync_for_iteration_in_atos(self, evaluate, atos_mlist):
		if not self.SecondarySideActive():
			return True

		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_MEASURE.key ) ) )
		self.export_atos_slave( evaluate, final_run=False )
		return True

	def atos_continuation(self, evaluate, res):
		self.log.debug( 'secondary atos_continuation status {}'.format( res ) )
		if not self.SecondarySideActive():
			return res

		self.log.info('Waiting for next measure signal')
		def check():
			if not self.connected:
				return False
			if len(self.remote_todos.todos):
				signal = self.remote_todos.todos[0][0]
				if signal == Communicate.SIGNAL_MEASURE:
					del self.remote_todos.todos[0]
					# no direct reply on success
					return True
				elif signal == Communicate.SIGNAL_FAILURE:
					del self.remote_todos.todos[0]
					return False
				elif signal == Communicate.SIGNAL_RESTART:
					del self.remote_todos.todos[0]
					return None
				else:
					self.log.error('Invalid signal: {}'.format(signal))
					del self.remote_todos.todos[0]
			return 'empty'
		res = check()
		if res=='empty':
			def handler(widget):
				if widget=='timer' or widget=='initialize':
					res = check()
					if res != 'empty':
						gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)

			Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
			try:
				res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
			except Exception as e:
				self.log.exception(str(e))
				self.secondary_con.send_signal(Communicate.SIGNAL_FAILURE)
				res = False
		if res is None:
			if not gom.app.project.is_part_project:
				#reopen complete project
				projectfile = gom.app.project.get ( 'project_file' )
				gom.script.sys.close_project()
				template = gom.script.sys.create_project_from_template (
					config_level = Globals.SETTINGS.CurrentTemplateCfg,
					template_name = Globals.SETTINGS.CurrentTemplate )
				gom.script.sys.save_project_as( file_name = projectfile )
			else:
				pass
			evaluate.Comp_photo_series = self.selected_tritop_mlists
			evaluate.Comp_atos_series = self.selected_atos_mlists
			self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_RESTART.key )  ) )

		return res


	def wait_for_calibration(self, evaluate):
		if not self.SecondarySideActive():
			return True
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( Communicate.SIGNAL_MEASURE.key )  ) )

	def onMoveDecisionNeeded(self, error, errortext1, errortext2):
		if self.secondary_con is None:
			return False
		self.secondary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_INLINE_DRC_MOVEDECISION, pickle.dumps( [error, errortext1, errortext2] ) ) )
		return True