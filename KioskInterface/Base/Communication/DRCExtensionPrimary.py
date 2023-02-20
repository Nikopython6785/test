# -*- coding: utf-8 -*-
# Script: Kiosk Extension script for Double-Robot-Cell Main side
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
from ..Measuring import Verification, Measure, FixturePositionCheck
from .. import Evaluate
from .Inline import InlineConstants

# ignore failing import for Kiosk without VMR license
try:
	from MeasurementStrategy.Robogrammetry import ShowMissingReferenceCubes
except:
	pass

import os
import time
import gom_windows_utils
import gom
import json
import pickle
import sys

class DRCExtensionPrimary( Utils.GenericLogClass ):
	primary_con = None
	remote_todos = None
	connected = False
	delayed_pkts = []
	request_pair = True
	update_startdialog_text=True
	first_start=True
	single_side_secondary = False
	single_side_primary = False
	drc_refcubes_checked = False
	master_series = None
	pause_connection = False
	remote_failure = False


	def __init__(self, parent, logger):
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.primary_con = AsyncClient.DoubleRobotClient( self.baselog, self,
								Globals.SETTINGS.DoubleRobot_SecondaryHostAddress,
								Globals.SETTINGS.DoubleRobot_SecondaryHostPort, {} )
		self.remote_todos = Communicate.RemoteTodos( self.baselog )
		self.log.info("DRC Extension loaded (Main)")
		
	def PrimarySideActive(self):
		return self.primary_con is not None and not Globals.FEATURE_SET.DRC_UNPAIRED and not Globals.FEATURE_SET.DRC_SINGLE_SIDE# and self.connected
	def SecondarySideActive(self):
		return False
	def SecondarySideActiveForError(self):
		return False

	def check_connected_and_alive( self, timeout=60.0 ):
		stime = time.time()
		# clear a possibly stale alive info
		self.primary_con.clear_alive()
		request_sent = False

		while True:
			ctime = time.time()
			if ctime - stime > timeout:
				# timeout
				return False

			if not self.primary_con.connected:
				# no connection
				gom.script.sys.delay_script( time=1.0 )
				continue

			if self.primary_con.handler is None or not self.primary_con.handler.handshaked:
				# connection not handshaked
				gom.script.sys.delay_script( time=1.0 )
				continue

			if not request_sent:
				# send "alive" request
				signal = Communicate.Signal( Communicate.SIGNAL_SERVER_ALIVE )
				self.primary_con.send_signal( signal )
				request_sent = True
				gom.script.sys.delay_script( time=1.0 )
				continue

			if self.primary_con.handler is not None and self.primary_con.handler.alive_ts is not None:
				self.log.debug('Answer to alive request (time current {} alive {})'.format(
					ctime, self.primary_con.handler.alive_ts ) )
				return True

			# no answer to "alive" request
			gom.script.sys.delay_script( time=1.0 )

		return True

	def globalTimerCheck (self, value):
		try:
			self.collect_pkts()
		except:
			pass
		
	def on_first_connection(self):
		signal = Communicate.Signal( Communicate.SIGNAL_UNPAIR, '0' if self.request_pair else '1' )
		self.primary_con.send_signal( signal )
		self.remote_todos.append_todo( signal )
		self.update_startdialog_text=True
		if Globals.SETTINGS.CurrentTemplate is not None:
			Globals.SETTINGS.CurrentTemplate = None
			Globals.SETTINGS.CurrentTemplateCfg = None
			if Globals.DIALOGS.has_widget( self.parent.startup.dialog, 'buttonTemplateChoose' ):
				self.parent.startup.dialog.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
	
	def on_connection_lost(self):
		self.update_startdialog_text=True
		self.remote_todos.clear()
			
	def collect_pkts(self):
		if self.pause_connection: # after atos the connection get closed to allow a different one, dont reconnect here
			return
		while self.primary_con.check_for_activity(timeout=0):
			pass
		was_connected = self.connected
		self.connected = self.primary_con.check_first_connection()
		if not was_connected and self.connected:
			self.on_first_connection()
		elif was_connected and not self.connected:
			self.on_connection_lost()
		for last_result in self.primary_con.LastAsyncResults:
			if last_result == Communicate.SIGNAL_INLINE_DRC_SECONDARY_INST_DATA:
				if Globals.SETTINGS.Inline and self.single_side_secondary and not self.single_side_primary:
					s_key, s_value = pickle.loads(last_result.value)
					self.log.debug('Forwarding: {}: {}'.format(s_key, s_value))
					Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( s_key, s_value))
				continue
			# Ignore failure when UNPAIRED
			# TODO: Ignore all packets here except PAIR?
			if last_result == Communicate.SIGNAL_FAILURE and Globals.FEATURE_SET.DRC_UNPAIRED:
				continue
			self.delayed_pkts.append(last_result)
			if last_result == Communicate.SIGNAL_FAILURE:
				self.remote_failure = True
				if Globals.SETTINGS.AllowAsyncAbort:
					self.log.debug('triggering async abort')
					gom.app.abort = True
				else:
					self.log.debug('flagging abort')
					Globals.SETTINGS.InAsyncAbort = True
			elif last_result == Communicate.SIGNAL_INLINE_DRC_MOVEDECISION:
				error = pickle.loads(last_result.value)
				if Globals.SETTINGS.AllowAsyncAbort:
					pass
					# master will get the same error nothing todo
				else:
					InlineConstants.sendMeasureInstanceError(error[0], error[1], error[2])
				
	def todos_done(self):
		#for s in self.remote_todos.todos:
		#	print(s)
		return len(self.remote_todos.todos) == 0

	def other_side_still_active(self):
		return self.remote_todos.has_todo(Communicate.SIGNAL_SINGLE_SIDE)

	def sendStartFailure(self, text):
		pass
		
	def sendStartSuccess(self):
		pass
	
	def sendExit(self):
		self.primary_con.send_signal(Communicate.SIGNAL_FAILURE)
		self.primary_con.close()
	
	def check_start_signals(self, startup):
		self.collect_pkts()
		while len( self.delayed_pkts ) > 0:
			last_result = self.delayed_pkts.pop( 0 )
			self.log.debug( 'pop result {}'.format( last_result ) )
			connection_text = ' (Connected)' if self.connected else ' (Disconnected)'
			# client send success
			if last_result == Communicate.SIGNAL_SUCCESS:
				last_todo = self.remote_todos.finish( last_result )  # get signal from todo list
				if last_todo is not None and last_todo[0] == Communicate.SIGNAL_UNPAIR:
					if int(last_todo[0].get_value_as_string()):
						Globals.FEATURE_SET.DRC_UNPAIRED = True
						pair_text = 'Unpaired'
						self.log.debug('set to unpaired')
						self.request_pair = False
					else:
						Globals.FEATURE_SET.DRC_UNPAIRED = False
						pair_text= 'Paired'
						self.log.debug('set to paired')
						self.request_pair = True
					if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
						startup.dialog.button_extension.text = pair_text + connection_text
				elif last_todo is not None and last_todo[0] == Communicate.SIGNAL_SINGLE_SIDE:
					self.log.info('Single Side Secondary project done')
					Communicate.IOExtension.multipart_single_side_done( self.baselog )
					if Globals.SETTINGS.Inline:
						Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_IDLE, str(2) ) )
			# client send failure
			elif last_result == Communicate.SIGNAL_FAILURE:
				last_todo = self.remote_todos.get_todo( last_result )  # get signal from todo list
				self.log.error( 'client failure {}'.format( last_todo ) )  # and show error msg
				self.log.error( ' client msg: {}'.format( last_result.get_value_as_string() ) )
				# clear remaining todos
				self.remote_todos.clear()
				if Globals.SETTINGS.Inline:
					plc_error = InlineConstants.PLCErrors.UNKNOWN_ERROR
					try:
						code = int(last_result.get_value_as_string().split( '-', 1 )[0].strip())
					except:
						code = 0
					try: # can fail in some cases, but no real error
						text = last_result.get_value_as_string().split( '-', 1 )[1].strip()
					except:
						text=''
					if code in [Communicate.SIGNAL_OPEN.key, Communicate.SIGNAL_OPEN_INIT.key]:
						plc_error = InlineConstants.PLCErrors.FAILED_OPEN_TEMPLATE
					elif code in [Communicate.SIGNAL_START.key, Communicate.SIGNAL_CLOSE_TEMPLATE.key, Communicate.SIGNAL_EXPORTEDFILE.key, Communicate.SIGNAL_SAVE.key]:
						plc_error = InlineConstants.PLCErrors.DISC_SPACE_ERROR
					elif code in [Communicate.SIGNAL_MEASURE.key, Communicate.SIGNAL_SINGLE_SIDE.key]:
						plc_error = InlineConstants.PLCErrors.MEAS_MLIST_ERROR
	
					InlineConstants.sendMeasureInstanceError(plc_error, '',
															text.replace('<br/>',' '))
				else:
					if last_todo == Communicate.SIGNAL_SINGLE_SIDE:
						Communicate.IOExtension.multipart_single_side_done()
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
											Globals.LOCALIZATION.msg_DC_client_failure.format( last_result.get_value_as_string() ),
											Globals.SETTINGS.SavePath, False )
				return False
			elif last_result == Communicate.SIGNAL_UNPAIR:
				if int(last_result.get_value_as_string()):
					Globals.FEATURE_SET.DRC_UNPAIRED=True
					if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
						startup.dialog.buttonTemplateChoose.enabled = True
					pair_text = 'Unpaired'
					self.request_pair = False
				else:
					Globals.FEATURE_SET.DRC_UNPAIRED=False
					if not self.connected:
						if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
							startup.dialog.buttonTemplateChoose.enabled = False
					pair_text= 'Paired'
					self.request_pair = True
				if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
					startup.dialog.button_extension.text = pair_text + connection_text
		return False
		
	##### StartDialog part
	def start_dialog_handler(self, startup, widget):
		self.pause_connection = False # undo the connection close in the start dialog
		if self.primary_con is None:
			return True
		pair_text = 'Unpaired' if Globals.FEATURE_SET.DRC_UNPAIRED else 'Paired'
		connection_text = ' (Connected)' if self.connected else ' (Disconnected)'
		if widget == 'initialize':
			if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
				startup.dialog.button_extension.text = pair_text + connection_text
			if Globals.DIALOGS.has_widget( startup.partdialog, 'button_extension' ):
				startup.partdialog.button_extension.text = pair_text + connection_text
			if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
				if startup.dialog.buttonTemplateChoose.visible:
					startup.dialog.buttonTemplateChoose.enabled = False
			
		elif widget == 'timer':
			if self.update_startdialog_text:
				if Globals.DIALOGS.has_widget( startup.dialog, 'button_extension' ):
					startup.dialog.button_extension.text = pair_text + connection_text
				if Globals.DIALOGS.has_widget( startup.partdialog, 'button_extension' ):
					startup.partdialog.button_extension.text = pair_text + connection_text
				self.update_startdialog_text=False
			if Globals.DIALOGS.has_widget( startup.dialog, 'buttonTemplateChoose' ):
				if not Globals.FEATURE_SET.DRC_UNPAIRED:
					if self.connected:
						if self.remote_todos.has_todo(Communicate.SIGNAL_UNPAIR):
							if startup.dialog.buttonTemplateChoose.visible:
								startup.dialog.buttonTemplateChoose.enabled = False
						else:
							if startup.dialog.buttonTemplateChoose.visible:
								startup.dialog.buttonTemplateChoose.enabled = True
					else:
						if startup.dialog.buttonTemplateChoose.visible:
							startup.dialog.buttonTemplateChoose.enabled = False
				else:
					if startup.dialog.buttonTemplateChoose.visible:
						startup.dialog.buttonTemplateChoose.enabled = True

			self.check_start_signals(startup)
			
		elif isinstance(widget, str):
			pass
		elif widget.name == 'button_extension':
			self.request_pair = not self.request_pair
			if not self.request_pair:
				pair_text = 'Unpaired'
				if self.connected:
					signal = Communicate.Signal( Communicate.SIGNAL_UNPAIR, '1' )
					self.primary_con.send_signal( signal )
					self.remote_todos.append_todo( signal )
				else:
					Globals.FEATURE_SET.DRC_UNPAIRED=True
					self.request_pair = False
			else:
				pair_text= 'Paired'
				if self.connected:
					signal = Communicate.Signal( Communicate.SIGNAL_UNPAIR, '0' )
					self.primary_con.send_signal( signal )
					self.remote_todos.append_todo( signal )
				else:
					Globals.FEATURE_SET.DRC_UNPAIRED=False
					self.request_pair = True
			startup.dialog.button_extension.text = pair_text + connection_text

		return True

	def hasOtherSideMlists(self, eval):
		real_ctrl_driver, real_ctrl_params, real_ctrl_ip, real_ctrl_serial = eval.Sensor.getConnectedControllerInfo()
		other_ctrl = None
		try:
			vmr = gom.app.project.virtual_measuring_room[0]
		except:
			return False
		for ctrl in vmr.controller_info:
			if not (ctrl.driver == real_ctrl_driver and
					ctrl.parameters == real_ctrl_params and
					ctrl.serial_port == real_ctrl_serial and
					ctrl.ip_address == real_ctrl_ip):
				other_ctrl = ctrl
		if other_ctrl is None:
			return False
		wcfgnames = []
		for wcfg in gom.app.project.measuring_setups:
			wcfg_area = wcfg.get ('working_area')
			area = None
			for warea in vmr.working_area:
				if (warea.id == wcfg_area.id
					and warea.controller.driver      == other_ctrl.driver
					and warea.controller.parameters  == other_ctrl.parameters
					and warea.controller.ip_address  == other_ctrl.ip_address
					and warea.controller.serial_port == other_ctrl.serial_port):
					area = warea
					break
			if area is None:
				continue
			wcfgnames.append(wcfg.name)
		photo_series = [mseries.name for mseries in gom.app.project.measurement_series
				if mseries.get('type') == 'photogrammetry_measurement_series'
					and mseries.measuring_setup.name in wcfgnames]
		atos_series = [mseries.name for mseries in gom.app.project.measurement_series
				if mseries.get('type') == 'atos_measurement_series'
					and mseries.measuring_setup.name in wcfgnames]
		return len(photo_series) or len(atos_series)

	def after_template_opened(self, startup, opened_template, multipart):
		if Globals.SETTINGS.Inline and not Globals.DRC_EXTENSION.single_side_primary:
			while True: # blocking point if slave side isnt connected yet
				self.collect_pkts()
				if self.connected:
					break
				gom.script.sys.delay_script(time=0.1)

		Globals.FEATURE_SET.DRC_SINGLE_SIDE = False
		if not self.PrimarySideActive():
			return
	
		# master_template => opened_template
		client_template = opened_template['template_name']
		client_template_cfg = opened_template['config_level']
		if client_template is None:
			self.primary_con.send_signal( Communicate.SIGNAL_CLOSE_TEMPLATE )
			self.remote_todos.append_todo( Communicate.SIGNAL_CLOSE_TEMPLATE )
			return

		if Globals.SETTINGS.OfflineMode:
			client_template = Utils.left_right_replace( opened_template['template_name'] )
			
		if Globals.SETTINGS.Inline and Globals.DRC_EXTENSION.single_side_primary:
			Globals.FEATURE_SET.DRC_SINGLE_SIDE = True
			self.log.debug('SWITCHING to DRC_SINGLE_SIDE')
		else:
			self.log.debug('DRC project')
		
		if multipart is not None: # possible template for single side
			eval = startup.parent.eval.eval
			eval.collectCompatibleSeries()
			slave_compatible = self.hasOtherSideMlists(eval)
			self.log.debug('compatible: {} other side: {}'.format(len(eval.Compatible_wcfgs)>0, slave_compatible))
			if not len(eval.Compatible_wcfgs) and slave_compatible:
				signal = Communicate.Signal( Communicate.SIGNAL_OPEN, pickle.dumps([client_template,client_template_cfg]) )
				self.remote_todos.append_todo( signal )
				self.primary_con.send_signal( signal )
				signal = Communicate.Signal( Communicate.SIGNAL_SINGLE_SIDE, pickle.dumps(multipart))
				self.remote_todos.append_todo( signal )
				self.primary_con.send_signal( signal )
				Communicate.IOExtension.store_active_devices()
				gom.script.sys.close_project()
				return False # skip this
			elif len(eval.Compatible_wcfgs) and not slave_compatible:
				Globals.FEATURE_SET.DRC_SINGLE_SIDE = True
	
		# start client project
		if self.PrimarySideActive(): # could have changed due to multipart
			signal = Communicate.Signal( Communicate.SIGNAL_OPEN, pickle.dumps([client_template,client_template_cfg]) )
			self.remote_todos.append_todo( signal )
			self.primary_con.send_signal( signal )

		# delayed loading to decrease delay
		if 'DRC_Ext_DelayedLoading' in opened_template:
			self.log.debug('delay loading {}'.format(opened_template['template_name']))
			gom.script.sys.create_project_from_template ( 
				config_level = opened_template['config_level'],
				template_name = opened_template['template_name'] )
		self.log.debug('Current Template {}'.format(Globals.SETTINGS.CurrentTemplate))

	def check_robogrammetry_workflow( self ):
		'''Returns True, if reference cube check not active.
		Returns True, if not robogrammetry workflow.
		Returns True, if robogrammetry workflow and nominal cubes unique.
		Returns False, if robogrammetry workflow and nominal cubes not unique.
		Returns None, if robogrammetry workflow and no nominal cubes present.
		'''
		if not self.PrimarySideActive():
			return True
		if not Globals.SETTINGS.DoubleRobot_RefCubeCheck:
			return True
		try:
			use_robo = gom.app.project.robogrammetry
		except:
			use_robo = False
		if not use_robo:
			return True

		try:
			refcubes = ShowMissingReferenceCubes.ProjectData.getNominalCubeElements()
		except:
			refcubes = []
		if len( refcubes ) > 1:
			return False
		elif len( refcubes ) == 0:
			return None
		return True


	def precheck_template(self):
		robo_check_result = self.check_robogrammetry_workflow()
		if not robo_check_result:
			msg = 'Internal failure robogrammetry check'
			if robo_check_result is False:
				msg = Globals.LOCALIZATION.msg_DC_refcubes_not_unique
			elif robo_check_result is None:
				msg = Globals.LOCALIZATION.msg_DC_no_refcubes
			res = Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title, msg,
				Globals.SETTINGS.SavePath, True,
				retry_text=Globals.LOCALIZATION.dialog_DC_RefCube_template_use )
			if not res:
				self.primary_con.send_signal( Communicate.SIGNAL_FAILURE )
				return False
		return True

	##### Evaluate part
	def start_evaluation(self, workflow_eval):
		self.drc_refcubes_checked = False
		if not self.PrimarySideActive():
			return

		self.remote_failure = False
		self.remote_todos.append_todo( Communicate.SIGNAL_START )
		self.primary_con.send_signal( Communicate.SIGNAL_START )

	def reuse_photogrammetry(self, evaluate):
		if Globals.SETTINGS.AlreadyExecutionPrepared:
			return # inline can signal it explicitly
		# only reuse tritop if alignment iter is not set
		# todo for tritop if cubes are used but not a frame..
		if len( evaluate.Comp_photo_series ) and len( evaluate.Comp_atos_series ) and evaluate.alignment_mseries is None:
			master_series = gom.app.project.measurement_series[evaluate.Comp_photo_series[0]]
			for ms in evaluate.Comp_photo_series:
				if gom.app.project.measurement_series[ms].get('reference_points_master_series') is None:
					master_series = gom.app.project.measurement_series[ms]
					break
			filename = evaluate.Tritop.import_photogrammetry(master_series, dryrun=True)
			if isinstance(filename, str):
				self.log.debug('found refxml to reuse: {}'.format(filename))
				evaluate.Comp_photo_series = [] # TODO: check Backup
				# copy into transfer folder and signal file name
				dest_file = os.path.normpath(os.path.join( Globals.SETTINGS.DoubleRobot_TransferPath, os.path.basename(filename) ) )
				try:
					# remove possible sizes data file
					try:
						os.unlink( evaluate.Tritop.filename_refpoint_sizes_data( dest_file ) )
					except:
						pass

					gom_windows_utils.copy_file( filename, dest_file, False )

					# copy optional sizes data file
					try:
						gom_windows_utils.copy_file(
							evaluate.Tritop.filename_refpoint_sizes_data( filename ),
							evaluate.Tritop.filename_refpoint_sizes_data( dest_file ),
							False )
					except:
						pass
				except Exception as e:
					pass # error
				signal = Communicate.Signal( Communicate.SIGNAL_REFXML, os.path.basename(filename)  )
				self.remote_todos.append_todo( signal )
				self.primary_con.send_signal( signal )
				evaluate.Tritop.import_photogrammetry(master_series, forced_refxml=filename)
			else: # send empty signal
				signal = Communicate.Signal( Communicate.SIGNAL_REFXML, ''  )
				self.remote_todos.append_todo( signal )
				self.primary_con.send_signal( signal )
			self.wait_for_refxml_import()

	def wait_for_refxml_import(self):
		if not self.PrimarySideActive():
			return
		self._waitForSucessSignal(Communicate.SIGNAL_REFXML)


	def prepare_measurement( self, evaluate ):
		if not self.PrimarySideActive():
			return True
		if len( self.remote_todos.todos ): # wait for signal start to finish
			def check():
				self.collect_pkts()
				while len( self.delayed_pkts ) > 0:
					last_result = self.delayed_pkts.pop( 0 )
					self.log.debug( 'pop result {}'.format( last_result ) )
					# client send success
					if last_result == Communicate.SIGNAL_SUCCESS:
						last_todo = self.remote_todos.finish( last_result )
					elif last_result == Communicate.SIGNAL_FAILURE:
						last_todo = self.remote_todos.get_todo( last_result )  # get signal from todo list
						self.log.error( 'client failure {}'.format( last_todo ) )  # and show error msg
						self.log.error( ' client msg: {}'.format( last_result.get_value_as_string() ) )
						Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
							Globals.LOCALIZATION.msg_DC_client_failure.format( last_result.get_value_as_string() ),
							Globals.SETTINGS.SavePath, False )
						return False
				return True
			if not check():
				return False
			if len(self.remote_todos.todos):
				def handler(widget):
					if widget=='timer':
						if not check():
							gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=False)
						if not len(self.remote_todos.todos):
							gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=True)
				Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
				Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
				Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
				try:
					res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
				except:
					res = False
				if not res:
					return res

		return True

	def set_measurements( self, evaluate, series ):
		if not self.PrimarySideActive():
			return True

		if series is None:
			self.primary_con.send_signal(Communicate.SIGNAL_FAILURE)
			return False

		# First call to FPC in DRC mode, so init here
		FixturePositionCheck.FixturePositionCheck.init_exec_count()
		with FixturePositionCheck.FixturePositionCheck( evaluate.baselog, evaluate ) as fpc:
			fpc_mlist = FixturePositionCheck.FixturePositionCheck.get_mlist( evaluate.Comp_atos_series )
			if fpc.is_fixture_position_check_possible():
				if not fpc.check_fixture_position():
					self.primary_con.send_signal(Communicate.SIGNAL_FAILURE)
					FixturePositionCheck.FixturePositionCheck.tear_down()
					return False

		try:
			evaluate.Comp_atos_series.remove( fpc_mlist )
			# not yet in MeasureContext: Backup_atos_series not set
		except:
			pass

		self.reuse_photogrammetry( evaluate )

		client_measurements = []
		for m in evaluate.Comp_photo_series + evaluate.Comp_atos_series:
			client_measurements.append( Utils.left_right_replace( m ) )

		if not len( client_measurements ):
			if evaluate.getExecutionMode() == Evaluate.ExecutionMode.PerformAdditionalCalibration:
				evaluate.setExecutionMode( Evaluate.ExecutionMode.ForceCalibration )

		if evaluate.alignment_mseries is not None:
			self.primary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_ALIGNMENT_ITER,
				Utils.left_right_replace( evaluate.alignment_mseries ) ) )
		else:
			self.primary_con.send_signal( Communicate.Signal( Communicate.SIGNAL_ALIGNMENT_ITER, '') )
		signal = Communicate.Signal( Communicate.SIGNAL_SAVE, Communicate.MLIST_SEPARATOR.join(client_measurements) )
		self.remote_todos.append_todo( signal )
		self.primary_con.send_signal( signal )
		return True


	def signal_start(self, evaluate):
		if not self.PrimarySideActive():
			return True
		def check():
			self.collect_pkts()
			while len( self.delayed_pkts ) > 0:
				last_result = self.delayed_pkts.pop( 0 )
				self.log.debug( 'pop result {}'.format( last_result ) )
				if last_result == Communicate.SIGNAL_SUCCESS:
					last_todo = self.remote_todos.finish( last_result )
					mode = 0
					if evaluate.getExecutionMode() == Evaluate.ExecutionMode.Full:
						mode = 0
					elif evaluate.getExecutionMode() == Evaluate.ExecutionMode.ForceCalibration:
						mode = 1
					elif evaluate.getExecutionMode() == Evaluate.ExecutionMode.ForceTritop:
						mode = 2
					elif evaluate.getExecutionMode() == Evaluate.ExecutionMode.PerformAdditionalCalibration:
						mode = 3
					signal = Communicate.Signal(Communicate.SIGNAL_MEASURE, str(mode))
					self.remote_todos.append_todo( signal )
					self.primary_con.send_signal( signal )
					return True
				elif last_result == Communicate.SIGNAL_FAILURE:
					last_todo = self.remote_todos.get_todo( last_result )  # get signal from todo list
					self.log.error( 'client failure {}'.format( last_todo ) )  # and show error msg
					self.log.error( ' client msg: {}'.format( last_result.get_value_as_string() ) )
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
						Globals.LOCALIZATION.msg_DC_client_failure.format( last_result.get_value_as_string() ),
						Globals.SETTINGS.SavePath, False )
					return False
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
		if self.PrimarySideActive():
			self.log.debug( 'Failure triggered from remote: {}'.format( self.remote_failure ) )
			if Globals.SETTINGS.InAsyncAbort:
				self.primary_con.send_signal(Communicate.Signal( Communicate.SIGNAL_SUCCESS, str(Communicate.SIGNAL_FAILURE.key)  ))
			else:
				self.primary_con.send_signal(Communicate.SIGNAL_FAILURE)
				self.remote_todos.append_todo( Communicate.SIGNAL_FAILURE)
				def check():
					self.collect_pkts()
					while len( self.delayed_pkts ) > 0:
						last_result = self.delayed_pkts.pop( 0 )
						self.log.debug( 'pop result {}'.format( last_result ) )
						# client send success
						if last_result == Communicate.SIGNAL_SUCCESS:
							last_todo = self.remote_todos.finish( last_result )
							return False
						elif last_result == Communicate.SIGNAL_FAILURE:
							last_todo = self.remote_todos.get_todo( last_result )  # get signal from todo list
							return False
					return True
				if not check():
					self.remote_todos.clear() # clear all remaining todos on error
					return False
				if len(self.remote_todos.todos):
					def handler(widget):
						if widget=='timer':
							if not check():
								self.remote_todos.clear() # clear all remaining todos on error
								gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=False)
							if not len(self.remote_todos.todos):
								gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=True)
					Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
					Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
					Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
					try:
						res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
					except:
						res = False
					if not res:
						return res

	
	def reference_cube_check(self):
		if not self.PrimarySideActive():
			return True
		rcc_result = True
		# Check ref cube positions?
		try:
			ref_cube_check = (Globals.SETTINGS.DoubleRobot_RefCubeCheck
				and gom.app.project.robogrammetry)
		except:
			ref_cube_check = False
		if Globals.SETTINGS.DoubleRobot_RefCubeCheckOnce and self.drc_refcubes_checked:
			ref_cube_check = False
		if not ref_cube_check:
			return True

		# Check reference cube positions and correct errors manually
		self.drc_refcubes_checked = True

		gom.script.sys.recalculate_elements( elements=gom.app.project.measurement_series )
		# force recalc of the inital alignment
		initial_alignment = [a for a in gom.app.project.alignments
			if not a.get ( 'alignment_is_original_alignment' ) and a.get( 'alignment_is_initial' )]
		for alignment in initial_alignment:
			try:
				gom.script.sys.recalculate_alignment( alignment=alignment )
			except Globals.EXIT_EXCEPTIONS:
				raise
			except RuntimeError as e:
				self.log.error( 'failed to recalculate alignment {}'.format( e ) )

		try:
			refcubes = ShowMissingReferenceCubes.ProjectData.getNominalCubeElements()
		except:
			refcubes = []
		# execute check if refcube element unique
		if len( refcubes ) == 1:
			try:
				msg = ShowMissingReferenceCubes.get_missing_reference_cube_report( refcubes[0] )
			except Exception as e:
				self.log.exception( 'ShowMissingReferenceCubes failed to get cube report: {}'.format( str( e ) ) )
				msg = None
				rcc_result = Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
					Globals.LOCALIZATION.msg_DC_refcubes_failed, Globals.SETTINGS.SavePath, False )
			if msg is not None:
				# Dialog result: True => Use, False => Abort, None => Retry
				self.log.debug( 'ShowMissingReferenceCubes status report: ' + msg )
				rcc_result = Globals.DIALOGS.show_refcube_check_dialog( msg )
			if rcc_result is False:
				return rcc_result
			if rcc_result is None:
				try:
					# Call ShowMissingReferenceCubes script to guide correction of ref.cubes
					ShowMissingReferenceCubes.show_missing_reference_cubes( gom.app.kiosk_mode )
				except Exception as e:
					self.log.exception( 'ShowMissingReferenceCubes failed: {}'.format( str( e ) ) )
		else:
			self.log.error( 'ShowMissingReferenceCubes: nominal cube element not unique - skipping check' )

		return rcc_result
	
	def evaluate_tritop_master(self, evaluate, filename):
		filename = os.path.join(Globals.SETTINGS.DoubleRobot_TransferPath, filename)
		if gom.app.project.is_part_project:
			gom.script.sys.import_project ( file = filename, import_mode='measurement_data_only' )
		else:
			gom.script.sys.import_project ( file = filename, import_mode='replace_elements' )
		try:
			os.unlink( filename )
		except:
			pass
		try:
			gom.script.sys.save_project()
		except:
			pass
		self.master_series = gom.app.project.measurement_series[evaluate.Comp_photo_series[0]]
		if self.master_series.get('reference_points_master_series') is not None:
			self.master_series = self.master_series.get('reference_points_master_series')
		errorlog = Verification.ErrorLog()
		if evaluate.Global_Checks.checkphotogrammetry( self.master_series, errorlog, True ) == Verification.VerificationState.Failure:
			self.log.error( 'Verification failed' )
			self.primary_con.send_signal(Communicate.SIGNAL_FAILURE)
			Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
											Globals.LOCALIZATION.msg_photogrammetry_verification_failed.format( errorlog.Error ), Globals.SETTINGS.SavePath, False )
			return False

		gom.script.sys.recalculate_elements( elements=gom.app.project.measurement_series )
		return True

	def sync_for_iteration_in_tritop(self, evaluate):
		if not self.PrimarySideActive():
			return True

		def check():
			self.collect_pkts()
			while len( self.delayed_pkts ) > 0:
				last_result = self.delayed_pkts.pop( 0 )
				self.log.debug( 'pop result {}'.format( last_result ) )
				if last_result == Communicate.SIGNAL_SUCCESS:
					last_todo = self.remote_todos.finish( last_result )
					if last_todo[0] == Communicate.SIGNAL_MEASURE:
						self.log.info('tritop measure finished')
				elif last_result == Communicate.SIGNAL_FAILURE:
					last_todo = self.remote_todos.get_todo( last_result )  # get signal from todo list
					self.log.error( 'client failure {}'.format( last_todo ) )  # and show error msg
					self.log.error( ' client msg: {}'.format( last_result.get_value_as_string() ) )
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
						Globals.LOCALIZATION.msg_DC_client_failure.format( last_result.get_value_as_string() ),
						Globals.SETTINGS.SavePath, False )
					return False
				elif last_result == Communicate.SIGNAL_EXPORTEDFILE:
					return last_result.get_value_as_string()

			return 'empty'
		res = check()
		if res == False:
			return res
		if res == 'empty':
			def handler(widget):
				if widget=='timer':
					res = check()
					if not isinstance(res, str) or res != 'empty':
						gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)
	
			Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
			try:
				res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
			except:
				res = False

		self.master_series = None
		if isinstance( res, str ):
			res = self.evaluate_tritop_master( evaluate, res )

		return res

	def tritop_continuation(self, evaluate, res):
		self.log.debug( 'primary tritop_continuation status {}'.format( res ) )
		if not self.PrimarySideActive():
			return res

		if res is None: # None = Retry
			# Possibly repeat CFP for retry
			with FixturePositionCheck.FixturePositionCheck( evaluate.baselog, evaluate ) as fpc:
				if fpc.is_fixture_position_check_possible():
					if not fpc.check_fixture_position():
						self.primary_con.send_signal(Communicate.SIGNAL_FAILURE)
						return False

			self.remote_todos.append_todo( Communicate.SIGNAL_RESTART )
			self.remote_todos.append_todo( Communicate.SIGNAL_MEASURE ) # slave sends measure success
			self.primary_con.send_signal( Communicate.SIGNAL_RESTART )
			return None
		elif not res: # False = Abort
			self.primary_con.send_signal( Communicate.SIGNAL_FAILURE )
			return False

		# res == True => continue
		# force recalc of the inital alignment
		initial_alignment = [a for a in gom.app.project.alignments if not a.get ( 'alignment_is_original_alignment' ) and a.get( 'alignment_is_initial' )]
		for alignment in initial_alignment:
			try:
				gom.script.sys.recalculate_alignment( alignment=alignment )
			except Globals.EXIT_EXCEPTIONS:
				raise
			except RuntimeError as e:
				self.log.error( 'failed to recalculate alignment {}'.format( e ) )

		evaluate.Tritop.export_photogrammetry(self.master_series) # kiosk default export
		if not len(evaluate.Comp_atos_series):
			self.primary_con.send_signal( Communicate.SIGNAL_MEASURE )
			return True

		# TODO wouldn't it be better to copy the files like in reuse_photogrammetry???
		try:
			filename = os.path.join( Globals.SETTINGS.DoubleRobot_TransferPath, 'refpoints.refxml' )

			# remove an existing sizes data file
			try:
				os.unlink( evaluate.Tritop.filename_refpoint_sizes_data( filename ) )
			except:
				pass

			gom.script.sys.export_reference_points_xml (
				elements=[self.master_series],
				file=filename,
				only_selected_points=False )

			# if successful and required, also save refpoint size data
			try:
				if evaluate.Tritop.save_refpoint_sizes_data() and gom.app.project.is_part_project:
					sizes_data = evaluate.Tritop.refpoint_sizes_data()
					sfilename = evaluate.Tritop.filename_refpoint_sizes_data( filename )
					with open( sfilename, 'w', encoding='utf-8' ) as f:
						json.dump( sizes_data, f, indent=2 )
			except:
				pass

		except Exception as e:
			self.log.exception('failed to export refxml {}'.format(e))
			self.primary_con.send_signal( Communicate.SIGNAL_FAILURE )
			return False
		signal = Communicate.Signal( Communicate.SIGNAL_REFXML, 'refpoints.refxml' )

		with Measure.TemporaryWarmupDisable(evaluate.Sensor) as warmup:
			if not evaluate.Sensor.is_initialized():
				if not evaluate.Sensor.initialize():
					self.primary_con.send_signal( Communicate.SIGNAL_FAILURE )
					return False

		self.remote_todos.append_todo( signal )
		self.primary_con.send_signal( signal )
		self.wait_for_refxml_import()
		return True
		
	def signal_atos_measurement(self):
		self.remote_todos.append_todo( Communicate.SIGNAL_MEASURE )
		self.primary_con.send_signal( Communicate.SIGNAL_MEASURE )


	def import_atos_master(self, evaluate, filename):
		filename = os.path.join(Globals.SETTINGS.DoubleRobot_TransferPath, filename)
		if gom.app.project.is_part_project:
			gom.script.sys.import_project ( file=filename, import_mode='measurement_data_only', import_reference_point_parameters=False )
		else:
			gom.script.sys.import_project ( file=filename, import_mode='replace_elements')
		try:
			os.unlink( filename )
		except:
			pass
		try:
			gom.script.sys.save_project()
		except:
			pass

	def wait_for_atos(self, evaluate, measurecontext):
		if not self.PrimarySideActive():
			return True

		# primary finished atos, trigger export and close for secondary
		self.primary_con.send_signal( Communicate.SIGNAL_EXPORTEDFILE )

		def check():
			self.collect_pkts()
			while len( self.delayed_pkts ) > 0:
				last_result = self.delayed_pkts.pop( 0 )
				self.log.debug( 'pop result {}'.format( last_result ) )
				if last_result == Communicate.SIGNAL_SUCCESS:
					last_todo = self.remote_todos.finish( last_result )
					if last_todo[0] == Communicate.SIGNAL_MEASURE:
						self.log.info('atos measure finished')
						if not len(evaluate.Comp_atos_series):
							return True
				elif last_result == Communicate.SIGNAL_FAILURE:
					last_todo = self.remote_todos.get_todo( last_result )  # get signal from todo list
					self.log.error( 'client failure {}'.format( last_todo ) )  # and show error msg
					self.log.error( ' client msg: {}'.format( last_result.get_value_as_string() ) )
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
												Globals.LOCALIZATION.msg_DC_client_failure.format( last_result.get_value_as_string() ),
												Globals.SETTINGS.SavePath, False )
					return False
				elif last_result == Communicate.SIGNAL_EXPORTEDFILE:
					return last_result.get_value_as_string()
			return 'empty'
		res = check()
		if res == False:
			return res
		elif res == 'empty':
			def handler(widget):
				if widget=='timer':
					res = check()
					if not isinstance(res, str) or res != 'empty':
						gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)
	
			Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
			try:
				res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
			except:
				res = False
		if isinstance(res, str):
			if Globals.SETTINGS.Inline:
				measurecontext.measure_done_send = True
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MEASURING, str(0) ) )
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_EXECUTION_TIME, str(0) ) )
			if Globals.SETTINGS.IoTConnection:
				measurecontext.measure_done_send = True
				Globals.IOT_CONNECTION.send(template=Globals.SETTINGS.CurrentTemplate, execution_time=0)
			self.import_atos_master(evaluate, res)
			
		if not Globals.SETTINGS.Inline and not Globals.SETTINGS.BatchScan:
			self.pause_connection = True
			self.primary_con.close() # close connection to allow a different connection while evaluating
		return res


	def sync_for_iteration_in_atos(self, evaluate, atos_mlist):
		if not self.PrimarySideActive():
			return True

		def check():
			self.collect_pkts()
			while len( self.delayed_pkts ) > 0:
				last_result = self.delayed_pkts.pop( 0 )
				self.log.debug( 'pop result {}'.format( last_result ) )
				if last_result == Communicate.SIGNAL_SUCCESS:
					last_todo = self.remote_todos.finish( last_result )
					if last_todo[0] == Communicate.SIGNAL_MEASURE:
						self.log.info('atos measure finished')
				elif last_result == Communicate.SIGNAL_FAILURE:
					last_todo = self.remote_todos.get_todo( last_result )  # get signal from todo list
					self.log.error( 'client failure {}'.format( last_todo ) )  # and show error msg
					self.log.error( ' client msg: {}'.format( last_result.get_value_as_string() ) )
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
												Globals.LOCALIZATION.msg_DC_client_failure.format( last_result.get_value_as_string() ),
												Globals.SETTINGS.SavePath, False )
					return False
				elif last_result == Communicate.SIGNAL_EXPORTEDFILE:
					return last_result.get_value_as_string()
			return 'empty'
		res = check()
		if res == False:
			return res
		elif res == 'empty':
			def handler(widget):
				if widget=='timer':
					res = check()
					if not isinstance(res, str) or res != 'empty':
						gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)
	
			Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
			try:
				res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
			except:
				res = False

		if isinstance(res, str):
			self.import_atos_master(evaluate, res)
			self.log.debug('evaluating partly')
			res = True

		return res

	def atos_continuation(self, evaluate, res):
		self.log.debug( 'primary atos_continuation status {}'.format( res ) )
		if not self.PrimarySideActive():
			return res

		with Measure.TemporaryWarmupDisable(evaluate.Sensor) as warmup:
			if not evaluate.Sensor.is_initialized():
				if not evaluate.Sensor.initialize():
					return False

		if res is None: #retry
			# Possibly repeat CFP for retry
			with FixturePositionCheck.FixturePositionCheck( evaluate.baselog, evaluate ) as fpc:
				if fpc.is_fixture_position_check_possible():
					if not fpc.check_fixture_position():
						self.primary_con.send_signal(Communicate.SIGNAL_FAILURE)
						return False

			self.remote_todos.append_todo( Communicate.SIGNAL_RESTART )
			self.primary_con.send_signal( Communicate.SIGNAL_RESTART )
			self.remote_todos.append_todo( Communicate.SIGNAL_MEASURE ) # add measure also to todo
		elif res:
			self.remote_todos.append_todo( Communicate.SIGNAL_MEASURE )
			self.primary_con.send_signal( Communicate.SIGNAL_MEASURE )
			return res
		else:
			self.primary_con.send_signal( Communicate.SIGNAL_FAILURE )
			return res

		# wait for restart
		if self._waitForSucessSignal(Communicate.SIGNAL_RESTART):
			self.log.info('restart finished')
			return None
		return False

	
	def wait_for_calibration(self, evaluate):
		if not self.PrimarySideActive():
			return True
		if self._waitForSucessSignal(Communicate.SIGNAL_MEASURE):
			self.log.info('calibration finished')
			return True
		return False

	def first_start_check_project(self,workflow):
		if not self.first_start:
			return None
		self.first_start = False
		if gom.app.kiosk_mode:
			return None
		try:
			gom.app.project
		except:
			return None
		res = Globals.DIALOGS.show_drc_one_shot_dialog()
		if res==False: # abort
			return False
		elif res is not None: # clear
			for m in gom.app.project.measurement_series:
				gom.script.automation.clear_measuring_data ( measurements = m )

		def check(startup):
			self.collect_pkts()
			self.check_start_signals(startup)
			if self.connected and not Globals.FEATURE_SET.DRC_UNPAIRED:
				return True
			return False
		res = check(workflow.startup)
		if not res:
			def handler(widget):
				if widget=='timer':
					res = check(workflow.startup)
					if res:
						gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)

			Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
			try:
				res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
			except:
				return False

		tmpfile = os.path.join( Globals.SETTINGS.DoubleRobot_TransferPath, 'tempproject.ginspect' )
		try:
			gom.script.sys.export_gom_inspect_file ( file=tmpfile )
		except:
			Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
											Globals.LOCALIZATION.msg_oneshot_export_error,
											None, False )
			sys.exit(1)
		signal = Communicate.Signal( Communicate.SIGNAL_OPEN, os.path.basename(tmpfile) )
		self.remote_todos.append_todo( signal )
		self.primary_con.send_signal( signal )
		return True

	def onInlinePrepareExecution(self, startup):
		if not self.PrimarySideActive():
			return
		signal = Communicate.Signal( Communicate.SIGNAL_INLINE_PREPARE, pickle.dumps([]) )
		self.remote_todos.append_todo( signal )
		self.primary_con.send_signal( signal )
	
	def waitForInlinePrepareExecution(self, startup):
		if not self.PrimarySideActive():
			return True
		if self._waitForSucessSignal(Communicate.SIGNAL_INLINE_PREPARE):
			self.log.info('prepare finished')
			return True
		return False

	def onInlineCloseTemplate(self, startup):
		self.primary_con.send_signal( Communicate.SIGNAL_CLOSE_TEMPLATE )
		self.remote_todos.append_todo( Communicate.SIGNAL_CLOSE_TEMPLATE )
		if self.primary_con is None:
			return
		if self._waitForSucessSignal(Communicate.SIGNAL_CLOSE_TEMPLATE, True):
			self.log.info('close template finished')
			return True
		return False
	
	def onInlineDeInit(self, startup):
		self.primary_con.send_signal( Communicate.SIGNAL_DEINIT_SENSOR )
		return True
	
	def onInlineSerialSlave(self, value, only_open_and_init=False):
		self.log.debug('Secondary serial')
		if self.primary_con is None:
			return
		if only_open_and_init:
			signal = Communicate.Signal( Communicate.SIGNAL_OPEN_INIT, value )
		else:
			signal = Communicate.Signal( Communicate.SIGNAL_OPEN, value )
		self.remote_todos.append_todo( signal )
		self.primary_con.send_signal( signal )
		if only_open_and_init:
			self._waitForSucessSignal(Communicate.SIGNAL_OPEN_INIT, True)
	
	def onInlineAdditionalInfosSlave(self, value):
		if self.primary_con is None:
			return
		signal = Communicate.Signal( Communicate.SIGNAL_INLINE_PREPARE, value )
		self.remote_todos.append_todo( signal )
		self.primary_con.send_signal( signal )
	
	def onInlineStartSingleSlave(self):
		self.log.debug('Secondary start')
		if self.primary_con is None:
			return
		self.log.debug('Secondary start wait')
		if self.remote_todos.has_todo(Communicate.SIGNAL_OPEN):
			if self._waitForSucessSignal(Communicate.SIGNAL_OPEN, True):
				self.log.info('close template finished')
				#return True
			#return False
		signal = Communicate.Signal( Communicate.SIGNAL_SINGLE_SIDE, pickle.dumps({}))
		self.remote_todos.append_todo( signal )
		self.primary_con.send_signal( signal )
	
	def _waitForSucessSignal(self, signal, no_dialog = False):
		def check():
			self.collect_pkts()
			while len( self.delayed_pkts ) > 0:
				last_result = self.delayed_pkts.pop( 0 )
				self.log.debug( 'pop result {}'.format( last_result ) )
				if last_result == Communicate.SIGNAL_SUCCESS:
					last_todo = self.remote_todos.finish( last_result )
					if last_todo[0] == signal:
						return True
				elif last_result == Communicate.SIGNAL_FAILURE:
					last_todo = self.remote_todos.get_todo( last_result )  # get signal from todo list
					self.log.error( 'client failure {}'.format( last_todo ) )  # and show error msg
					self.log.error( ' client msg: {}'.format( last_result.get_value_as_string() ) )
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
												Globals.LOCALIZATION.msg_DC_client_failure.format( last_result.get_value_as_string() ),
												Globals.SETTINGS.SavePath, False )
					return False
			return 'empty'
		res = check()
		if not isinstance(res, str) or res != 'empty':
			return res
		def handler(widget):
			if widget=='timer':
				res = check()
				if not isinstance(res, str) or res != 'empty':
					gom.script.sys.close_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG, result=res)

		if not no_dialog:
			Globals.DIALOGS.DRC_WAIT_DIALOG.handler = handler
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.enabled = True
			Globals.DIALOGS.DRC_WAIT_DIALOG.timer.interval = 500
			try:
				res = gom.script.sys.show_user_defined_dialog(dialog=Globals.DIALOGS.DRC_WAIT_DIALOG)
			except Exception as e:
				self.log.exception('error '+str(e))
				res = False
		else:
			while True:
				res = check()
				if not isinstance(res, str) or res != 'empty':
					break
				gom.script.sys.delay_script(time=0.1)
		return res
		
	def onMoveDecision(self, decision):
		if self.primary_con is None:
			return
		self.primary_con.send_signal( Communicate.Signal(Communicate.SIGNAL_INLINE_DRC_MOVEDECISION, str(decision) ) )
		
	def onAbort(self):
		if self.primary_con is None:
			return
		self.primary_con.send_signal( Communicate.SIGNAL_INLINE_DRC_ABORT )
		
	def onInlineResultNotNeeded(self, value):
		if self.primary_con is None:
			return
		self.primary_con.send_signal( Communicate.Signal(Communicate.SIGNAL_CONTROL_RESULT_NOT_NEEDED, value) )
		
	def onGOMSic(self):
		if self.primary_con is None:
			return
		self.primary_con.send_signal( Communicate.SIGNAL_CONTROL_CREATE_GOMSIC )
