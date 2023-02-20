# -*- coding: utf-8 -*-
# Script: General workflow definitions
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
# 2013-01-22: added global logging instance
#             show an dialog during the wait for client exiting
# 2014-05-06: added support for BarCode scanner and batchprocessing
# 2015-04-27: handling additional project keywords from table in CustomPatches
# 2015-07-06: Empty template for input value checking, called when start button is pressed
#             Import language file at start-up.


from .Misc import LogClass, Utils, Globals, Messages, PersistentSettings, BarCode
from .Communication import (AsyncServer, Communicate, AsyncClient,
							DRCExtensionPrimary, DRCExtensionSecondary, MultiEvalServer)
from .Communication.Inline import InlineConstants
from . import Evaluate, Dialogs
from .Measuring import Measure
from .Communication import MultiRobotMeasure

import gom
import time
import sys
import os
import glob
import datetime
import re
import pickle
from functools import partial


class WorkFlow( Utils.GenericLogClass ):
	'''
		This class contains the measurement Workflow, which consists mainly of three steps:
		1. A startUp step where user information is requested through a dialog
		2. A evaluation step where the measurement and inspection is done.
		3. A confirmation step where a dialog informs the user about the results of the measurement process and requires him to confirm it.
	'''
	startup = None
	eval = None
	confirm = None

	def __init__( self ):
		'''
		Initializes function to init logging and subclasses
		'''
		gom.script.sys.set_kiosk_status_bar(show=True)
		gom.script.sys.set_kiosk_status_bar(states=['home','measurement','evaluation','confirm'])
		# init logging
		Utils.GenericLogClass.__init__( self, LogClass.Logger() )
		self.baselog.log.setLevel( Globals.SETTINGS.LoggingLevel )

		self.consolelog = self.baselog.create_console_streamhandler( strformat = Globals.SETTINGS.LoggingFormat )
		filename = 'kiosklog'
		if Globals.FEATURE_SET.DRC_SECONDARY_INST:
			filename+='_secondary'
		self.set_logging_filename(filename, Globals.SETTINGS.TimeFormatLogging)
		self.set_logging_format(Globals.SETTINGS.LoggingFormat)
		self.create_fileloghandler()
		Globals.registerGlobalLogger( self.baselog )

		# check for dubious settings
		Globals.SETTINGS.check_warnings( self.log )

		# Load Localization
		Utils.import_localization( Globals.SETTINGS.Language, self.log )

		Globals.DIALOGS.localize_measuringsetup_dialog()
		Globals.DIALOGS.localize_temperature_dialog()

		Utils.GlobalTimer.registerInstance( self.baselog )
		if Globals.SETTINGS.MultiRobot_Mode:
			Globals.SETTINGS.Async = False
			Globals.SETTINGS.BackgroundTrend = False
			if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
				# save temporary project with fixed name, no time stamp
				Globals.SETTINGS.AutoNameProject = False
				Globals.SETTINGS.ProjectName = 'TemporarySave'
				Globals.SETTINGS.TimeFormatProject = ''
				Globals.DRC_EXTENSION = MultiRobotMeasure.MultiRobotMeasure(self, self.baselog)
		else:
			if Globals.FEATURE_SET.DRC_PRIMARY_INST:
				Globals.DRC_EXTENSION = DRCExtensionPrimary.DRCExtensionPrimary(self, self.baselog)
			elif Globals.FEATURE_SET.DRC_SECONDARY_INST:
				Globals.DRC_EXTENSION = DRCExtensionSecondary.DRCExtensionSecondary(self, self.baselog)

		# create the workflow classes
		if Globals.SETTINGS.Inline:
			try:
				from .Communication.Inline import InlineUtils
			except:
				Globals.SETTINGS.Inline = False
				Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title, Globals.LOCALIZATION.msg_no_atos_inline_license, sic_path = Globals.SETTINGS.SavePath, retry_enabled = False )
				sys.exit(0)
			self.startup = InlineStartUp( self.baselog, self )
			#if not Globals.SETTINGS.Async:
			#	self.log.error("Async Evaluation needs to be enabled")
			#	sys.exit(0)
		elif Globals.SETTINGS.BarCodeScanner or Globals.SETTINGS.BatchScan or Globals.FEATURE_SET.V8StartDialogs:
			self.startup = StartUpV8( self.baselog )  # intialize new StartUp class
		else:
			if not Globals.FEATURE_SET.V8StartDialogs:
				self.log.info( 'Found StartDialog patch using old StartUp class' )
			self.startup = StartUp( self.baselog )
		self.startup.parent = self
		self.eval = Eval( self.baselog )
		self.eval.parent = self
		self.confirm = Confirm( self.baselog )
		self.confirm.parent = self

		# Detect / Setup One Shot Mode for DRC and Kiosk
		drc_one_shot_mode = False
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			drc_one_shot_mode = Globals.DRC_EXTENSION.first_start_check_project(self)
			if drc_one_shot_mode == False:# cancel
				sys.exit(0)
			if drc_one_shot_mode:
				self.log.info( 'Kiosk DRC Extension started in one-shot mode' )
		if drc_one_shot_mode or Globals.FEATURE_SET.ONESHOT_MSERIES:
			Globals.FEATURE_SET.ONESHOT_MODE = True
			Globals.FEATURE_SET.DRC_ONESHOT = True # for compatibility
			# Turn off conflicting settings for oneshot mode
			Globals.SETTINGS.BatchScan = False
			Globals.SETTINGS.CheckFixturePosition = False
			Globals.SETTINGS.Async = False
			Globals.SETTINGS.BackgroundTrend = False
			# set CurrentTemplate to satisfy all "is not None"-checks
			Globals.SETTINGS.CurrentTemplate = os.path.basename( gom.app.project.project_file )
			# also set fake cfg level, just to be consistently different to None
			Globals.SETTINGS.CurrentTemplateIsConnected = False
			Globals.SETTINGS.CurrentTemplateConnectedUrl = ''
			Globals.SETTINGS.CurrentTemplateConnectedProjectId = ''
			Globals.SETTINGS.CurrentTemplateCfg = 'oneshot_project'
		else:
			gom.script.sys.close_project()
		if Globals.FEATURE_SET.ONESHOT_MSERIES:
			self.log.info( 'Kiosk started in one-shot mode for measurement series {}'.format(
				', '.join( Globals.FEATURE_SET.ONESHOT_MSERIES ) ) )
			if not Globals.SETTINGS.OfflineMode:
				for m in Utils.real_measurement_series(
						filter='name in {}'.format( Globals.FEATURE_SET.ONESHOT_MSERIES ) ):
					gom.script.automation.clear_measuring_data ( measurements = m )

		# create SW instances for inspection
		if Globals.SETTINGS.Async:
			Globals.DIALOGS.toggleshow_wait_dialog( Globals.LOCALIZATION.waitdialog_client_setup )
			retry = 0
			while retry < 5:
				try:
					Globals.ASYNC_SERVER = AsyncServer.CommunicationServer(
						self.baselog, self, Globals.SETTINGS.HostAddress, Globals.SETTINGS.HostPort, {} )
					break
				except Exception as error:
					self.log.exception( 'AsyncServer failed to init, retry in 3 secs: {}'.format( error ) )
					gom.script.sys.delay_script( time = 3 )
					retry += 1
			if Globals.ASYNC_SERVER is None:
				self.log.error( 'AsyncServer failed to init, exiting' )
				Globals.DIALOGS.toggleshow_wait_dialog( show = False )
				Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_async_failure_title, Globals.LOCALIZATION.msg_async_failure_start_server, sic_path = Globals.SETTINGS.SavePath, retry_enabled = False )
				sys.exit( 0 )
			Globals.ASYNC_CLIENTS = Communicate.ClientRefList(
				self.baselog, 'gom.script.userscript.KioskInterface__ClientStart' )
			self.log.info( 'AsyncClient started' )
			if Globals.SETTINGS.Inline:
				for client in Globals.ASYNC_CLIENTS.client_list:
					Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_ASYNC_PID, str(client.pid) ) )
			Globals.ASYNC_SERVER.wait_for_first_connection()
			self.check_for_old_projects()
			Globals.DIALOGS.toggleshow_wait_dialog( show = False )

		# additional extension initialization
		if Globals.SETTINGS.MultiRobot_Mode and Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
			res = Globals.DRC_EXTENSION.init_measure_client( self.startup )
			if not res:
				self.log.error( 'MultiRobot Measure Client failed to init, exiting' )
				sys.exit( 0 )

		if Globals.SETTINGS.BackgroundTrend:
			self.log.info( 'starting trend background instance' )
			self.eval.eval.analysis.start_automatic_trend_creator()
			
		if Globals.SETTINGS.IoTConnection:
			Globals.IOT_CONNECTION = Communicate.IoTConnection(Globals.SETTINGS.IoTConnection_IP, Globals.SETTINGS.IoTConnection_Port)
			if not Globals.SETTINGS.Inline:
				Globals.TIMER.setTimeInterval(30000)
				Globals.TIMER.registerHandler( self._iot_position_update )

	def _iot_position_update(self, value):
		try:
			self.eval.eval.position_information.updated_position_information()
		except: # can fail during startup, due to initialization order
			pass

	def execute( self ):
		'''
		This function contains the main workflow loop that means it executes the following three steps in an endless loop:
		1. A StartUp step where user information is requested through a dialog
		2. A Evaluate step where the measurement and inspection is done.
		3. A Confirmation step where a dialog informs the user about the results of the measurement process and requires him to confirm it.
		'''
		if not self.eval.eval.Sensor.check_system_configuration():
			if not Globals.SETTINGS.Inline:
				return False
			else: # keep instance running
				pass

		while True:
			Communicate.IOExtension.io_extension_measurement_done(self.baselog)
			Globals.SETTINGS.InAsyncAbort=False
			self.log.info( gom.app.get( 'application_name') + ' '
				+ gom.app.get( 'application_build_information.version' ) + ', Rev. '
				+ gom.app.get( 'application_build_information.revision' ) + ', Build '
				+ gom.app.get( 'application_build_information.date' ) )
			self.log.info( 'starting new Evaluation' )
			gom.script.sys.set_kiosk_status_bar(text='')

			# show dialog for user,serial,...
			if not Globals.FEATURE_SET.ONESHOT_MODE:
				if not self.startup.execute():
					self.log.info( 'Workflow break' )
					break
			resultchoosen = self.startup.Result
			Globals.SETTINGS.LastStartedTemplate = Globals.SETTINGS.CurrentTemplate
			self.log.info( 'User Input: {}'.format( ' '.join(
				'{}->{}'.format( key, value ) for key, value in resultchoosen.items()
				if key != '__parts__' ) ) )
			if '__parts__' in resultchoosen:
				for part, items in resultchoosen['__parts__'].items():
					self.log.info( 'User Input Part "{}": {}'.format( part, ' '.join(
						'{}->{}'.format( input, value ) for input, value in items.items() ) ) )

			if Globals.SETTINGS.BatchScan and not (Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_SECONDARY_INST and not Globals.FEATURE_SET.DRC_UNPAIRED):
				self.multipart_execute( resultchoosen )
			else:
				text = ''
				if Globals.SETTINGS.CurrentTemplate is not None:
					text = '<center>{}</center>'.format(Globals.SETTINGS.CurrentTemplate.replace(chr(0x7),'/')[:-len( '.project_template' )])
				gom.script.sys.set_kiosk_status_bar(text=text)
				result = self.evaluate( resultchoosen )

				# quit evaluation loop for oneshot modes except DRC Secondary
				if Globals.FEATURE_SET.ONESHOT_MODE:
					if ( Globals.FEATURE_SET.DRC_PRIMARY_INST
							or Globals.FEATURE_SET.ONESHOT_MSERIES ):
						break
					else:
						Globals.FEATURE_SET.ONESHOT_MODE = False
						Globals.FEATURE_SET.DRC_ONESHOT = False
						Globals.SETTINGS.CurrentTemplateIsConnected = False
						Globals.SETTINGS.CurrentTemplateConnectedUrl = ''
						Globals.SETTINGS.CurrentTemplateConnectedProjectId = ''
						Globals.SETTINGS.CurrentTemplate = None
						Globals.SETTINGS.CurrentTemplateCfg = None

				if result:
					self.after_successful_evaluation()
				
				if not Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
					gom.script.sys.close_project()
				if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_SECONDARY_INST and Globals.FEATURE_SET.DRC_SINGLE_SIDE:
					Globals.DRC_EXTENSION.sendSingleSideDone()

			# part finished create a new logfile
			self.close_fileloghandler()
			self.create_fileloghandler()

	def evaluate( self, resultchoosen ):
		'''
		evaluate current project
		returns bool for success or error
		'''
		if Globals.IOT_CONNECTION is not None:
			calib_date, calib_exp = Globals.IOT_CONNECTION.getCalibrationInformation()
			Globals.IOT_CONNECTION.send(template=Globals.SETTINGS.CurrentTemplate, 
									exposure_time_calib=calib_exp, calib_time=calib_date)
		result = False
		try:
			result = self.eval.execute( resultchoosen )
		except gom.BreakError:
			self.log.info( 'User stopped evaluation' )
			result = False

		if result is not None:
			try:
				gom.script.sys.save_project ()
			except:
				pass
		else:  # translate no save return
			result = False
		return result

	def after_successful_evaluation( self ):
		'''
		after successful evaluation show the confirm dialog,
		or in case of async evaluation send project to second instance
		'''
		# show the report pages and let the user confirm

		# pure tritop projects with active comprehensive behaviour should not be evaluated
		if self.eval.eval.isComprehensivePhotogrammetryProject:
			project_file = gom.app.project.get( 'project_file' )
			self.confirm.after_confirmation( True )  # save into result folder
			self.confirm.cleanup_project( project_file )
			return

		if Globals.SETTINGS.Async:
			if Globals.ASYNC_CLIENTS.poll():
				self.log.error( 'No Client instance, waiting' )
				Globals.ASYNC_SERVER.wait_for_first_connection()

			projectname = gom.app.project.get ( 'project_file' )
			gom.script.sys.save_project ()
			projectname = self.eval.eval.close_and_move_measured_project_if_needed()
			Globals.ASYNC_SERVER.send_evaluateproject( os.path.normpath( projectname ) )
		else:
			# TODO SW2022-8461 Handle PartEvaluationMap: loop evaluation templates => import => recalc => confirm
			self.confirm.execute()

	def multipart_alter_current_result( self, startup_result, setting ):
		'''
		alters result dictionary based on current multipart settings
		'''
		startup_result['serial'] = setting.serial  # change the serial no
		return startup_result

	def multipart_execute( self, startup_result ):
		'''
		in case of BatchScan evaluation perform every template with given serial
		'''
		template_serials = self.startup.MultiPartResult
		max_count = 0
		for index, setting in template_serials.items():  # count number of templates
			if not setting.valid():
				continue
			max_count += 1
		progress_bar = self.eval.Process_multipart_bar
		if progress_bar is not None:  # initialize progressbar
			progress_bar.minimum = 0
			progress_bar.maximum = max_count
			progress_bar.value = 1
		current_count = 1
		text = Globals.LOCALIZATION.statusbar_text_multipart_progress.format(current_count,max_count)
		gom.script.sys.set_kiosk_status_bar(text= text)
		# evaluation loop
		first_run = True
		photogrammetry_index = None
		error_index = None
		Globals.SETTINGS.InAsyncAbort = False
		Communicate.IOExtension.final_run(False)
		while True:
			try:
				for index, setting in template_serials.items():
					if not setting.valid():
						continue
					if not first_run:  # on error perform photogrammetry and skip all templates till error
						if photogrammetry_index is not None:
							if index < error_index and index != photogrammetry_index:
								self.log.debug( 'skipping {}'.format( index ) )
								continue
					self.log.debug( 'performing template index {}'.format( index ) )
					Communicate.IOExtension.final_run(current_count == max_count)
					Globals.SETTINGS.CurrentTemplate = setting.template
					Globals.SETTINGS.CurrentTemplateCfg = setting.template_cfg
					result = False
					startup_result = self.multipart_alter_current_result( startup_result, setting )  # change result dict based on current setting
					res = self.startup.open_template( startup = True, multipart=startup_result )  # open template noninteractivly
					if res == 'skipmulti':
						if progress_bar is not None:
							progress_bar.value += 1
						current_count += 1
						self.log.debug( 'Skipping multipart scanning template {}'.format(
							Globals.SETTINGS.CurrentTemplate.split( chr( 0x7 ) )[-1][:-len( '.project_template' )] ) )
						gom.script.sys.close_project()
						Globals.SETTINGS.CurrentTemplate = None
						Globals.SETTINGS.CurrentTemplateCfg = None
						continue
					elif res == False and Globals.DRC_EXTENSION is not None:
						if progress_bar is not None:
							progress_bar.value += 1
						current_count+=1
						self.log.debug('Skipping non Main side template')
						Communicate.IOExtension.multipart_single_side_started()
						continue
					text = Globals.LOCALIZATION.statusbar_text_multipart_progress.format(
						current_count, str(max_count)+' - '+Globals.SETTINGS.CurrentTemplate.replace(chr(0x7),'/')[:-len( '.project_template' )])
					gom.script.sys.set_kiosk_status_bar(text=text)
					self.log.info( 'performing with {}'.format( setting ) )
					if index > 0 and Globals.SETTINGS.BatchScanPauseNeeded:
						if not Globals.DIALOGS.showMultiPartWaitDialog():  # show pause dialog
							self.log.error( 'Multipart execution aborted due to user abort' )
							break

					if Globals.SETTINGS.PhotogrammetryComprehensive:
						if len( Utils.real_measurement_series( filter='type=="photogrammetry_measurement_series"' ) ):
							photogrammetry_index = index
							self.log.debug( 'index of photogrammetry template {}'.format( photogrammetry_index ) )

					Globals.SETTINGS.LastStartedTemplate = Globals.SETTINGS.CurrentTemplate
					result = self.evaluate( startup_result )
					if result is None or not result:
						self.log.error( 'Multipart execution aborted due to an error' )
						break
					if result:
						self.after_successful_evaluation()
					if progress_bar is not None:
						progress_bar.value += 1
					current_count+=1
					text = Globals.LOCALIZATION.statusbar_text_multipart_progress.format(current_count,max_count)
					gom.script.sys.set_kiosk_status_bar(text= text)
			except Utils.NeedComprehensivePhotogrammetry as e:
				self.log.exception( 'restart needed {}'.format( e ) )
				if not first_run:
					Globals.DIALOGS.show_errormsg( 
						Globals.LOCALIZATION.msg_general_failure_title,
						Globals.LOCALIZATION.msg_multi_comprehensive_retries_exceeded + '<br/>' + '\n'.join(e.args),
						sic_path = Globals.SETTINGS.SavePath,
						retry_enabled = False )
					break
				first_run = False
				error_index = index
				if photogrammetry_index is not None:  # force Tritop
					self.eval.eval.Tritop.setFailedTemplate( True, template_serials[photogrammetry_index].template )
				if progress_bar is not None:
					progress_bar.maximum += 1
				max_count+=1
				text = Globals.LOCALIZATION.statusbar_text_multipart_progress.format(current_count,max_count)
				gom.script.sys.set_kiosk_status_bar(text= text)
				self.log.debug( 'index of photogrammetry error {}'.format( error_index ) )
				continue
			break

		gom.script.sys.close_project()

	def check_for_old_projects( self ):
		'''
		This function searches SavePath for projects which have been measured but not evaluated. It sends an evaluation signal for each
		of those projects.
		'''
		path = os.path.join( Globals.SETTINGS.SavePath, Globals.SETTINGS.MeasureSavePath )
		for ext in ( '.atos', '.ginspect' ):
			for old_project in glob.glob( path + '/*{}'.format( ext ) ):
				if ( not os.path.exists( old_project + '.lock' ) ):
					if len( Globals.ASYNC_CLIENTS ) < 2:
						self.log.info( 'starting extra evaluation client' )
						Globals.ASYNC_CLIENTS.append( Globals.ASYNC_CLIENTS.start_sw() )
						Globals.ASYNC_SERVER.wait_for_first_connection()
					self.log.info( 'sending evaluation for old project' )
					Globals.ASYNC_SERVER.send_evaluateproject( old_project, 0 )

	def exit_handler( self ):
		'''
		This function is called directly before the script stops (SystemExit, BreakError)
		'''
		self.log.info( 'exit handler called' )
		if Globals.DRC_EXTENSION is not None:
			Globals.DRC_EXTENSION.sendExit()
		try:
			gom.script.sys.save_project()
		except Globals.EXIT_EXCEPTIONS:
			raise
		except:
			pass

		if Globals.ASYNC_SERVER is not None:
			self.log.info( 'sending exit' )
			Globals.ASYNC_SERVER.send_exit()
			Globals.DIALOGS.toggleshow_wait_dialog( Globals.LOCALIZATION.waitdialog_clients_exit )
			# wait till all clients got killed
			while not Globals.ASYNC_CLIENTS.all_killed():
				gom.script.sys.delay_script( time = 3 )
			self.log.info( 'all clients killed' )
			Globals.ASYNC_SERVER.close_all_handlers()
			Globals.DIALOGS.toggleshow_wait_dialog( show = False )

		if hasattr( self.startup, 'barcode_instance' ) and self.startup.barcode_instance is not None:
			self.startup.barcode_instance.close()
			del self.startup.barcode_instance
		if Utils.GlobalTimer is not None:
			Utils.GlobalTimer.unregisterInstance()

		self.close_fileloghandler()
		

##############
# deprecated StartUp class
# for backward compatibility used if barcode scanner is not active
# will be removed in a later version!

class StartUp( Utils.GenericLogClass ):
	'''
	This class manages the StartUp step as mentioned in the docstring of Workflow.
	'''

	handler = None
	confirm = None
	def __init__( self, logger ):
		'''
		init logging and subclasses
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.res = []
		# if set directly open the template
		if not Globals.SETTINGS.ShowTemplateDialog:
			Globals.SETTINGS.CurrentTemplate = Globals.SETTINGS.TemplateName
		Globals.DIALOGS.localize_startdialog()

		if Globals.SETTINGS.UseLoginName:
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'userlist' ):
				Globals.DIALOGS.STARTDIALOG.userlist.items = [gom.app.get ( 'current_user' )]
				Globals.DIALOGS.STARTDIALOG.userlist.enabled = False
		Globals.DIALOGS.STARTDIALOG.handler = self.start_dialog_handler
		if Globals.SETTINGS.Async:
			Globals.DIALOGS.STARTDIALOG.timer.interval = 5000  # every 5s
			Globals.DIALOGS.STARTDIALOG.timer.enabled = True

	def execute( self ):
		'''
		This function shows the dialog and creates results
		Returns:
		True - if the dialog was shown and was left by clicking the start button.
		False - Otherwise
		'''
		if Globals.SETTINGS.CurrentTemplate is not None:
			self.log.info( 'preopening last template "{}"'.format( Globals.SETTINGS.CurrentTemplate ) )
			self.open_template( True )
			self.log.info( 'finished preopening' )
		else:
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'buttonTemplateChoose' ):
				Globals.DIALOGS.STARTDIALOG.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
			gom.script.sys.close_project ()

		# create and show startup dialog
		result = self.show_dialog()
		return result

	def show_dialog( self ):
		'''
		This function shows the start dialog Globals.DIALOGS.STARTDIALOG
		Returns:
		True - if the dialog was left by the Start button
		False - otherwise
		'''
		try:
			return gom.script.sys.show_user_defined_dialog ( dialog = Globals.DIALOGS.STARTDIALOG )
		except Globals.EXIT_EXCEPTIONS:
			self.log.exception( 'SystemExit' )
			raise
		except gom.BreakError:
			self.log.info( 'BreakError catched' )
			return False
		except Exception as error:
			self.log.exception( str( error ) )
			return False

	@property
	def Result( self ):
		'''
		This function creates a dictionary containing the user input from the start dialog GlOBALS.DIALOGS.STARTDIALOG

		Returns:
		The dictionary containing the user input from the start dialog.
		'''
		res = {'user':'', 'serial':''}
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'userlist' ):
			res['user'] = Globals.DIALOGS.STARTDIALOG.userlist.value
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'inputSerial' ):
			res['serial'] = Globals.DIALOGS.STARTDIALOG.inputSerial.value
		self.log.info( 'collecting result: {}'.format( str( res ) ) )
		return res

	@property
	def Template_filter( self ):
		'''
		filter definition for open_template
		'''
		return ['*']

	def open_template( self, startup = False ):
		'''
		create a project from template
		if startup is given directly opens last used template
		'''
		gom.script.sys.close_project ()
		try:
			# called directly after dialog show
			if startup:
				template = gom.script.sys.create_project_from_template ( 
					config_level = Globals.SETTINGS.TemplateConfigLevel,
					template_name = Globals.SETTINGS.CurrentTemplate )
				Globals.SETTINGS.IsPhotogrammetryNeeded = False
			# show the template dialog
			elif Globals.SETTINGS.ShowTemplateDialog:
				template = gom.interactive.sys.create_project_from_template ( 
					config_levels = [Globals.SETTINGS.TemplateConfigLevel],
					template_name = Globals.SETTINGS.TemplateName,
					filters = self.Template_filter )
				if Globals.SETTINGS.PhotogrammetryOnlyIfRequired:
					if Globals.SETTINGS.CurrentTemplate != template['template_name']:
						Globals.SETTINGS.IsPhotogrammetryNeeded = True
					else:
						Globals.SETTINGS.IsPhotogrammetryNeeded = False
				Globals.SETTINGS.CurrentTemplate = template['template_name']
			# dont show the template dialog
			else:
				template = gom.script.sys.create_project_from_template ( 
					config_level = Globals.SETTINGS.TemplateConfigLevel,
					template_name = Globals.SETTINGS.TemplateName )
				if Globals.SETTINGS.PhotogrammetryOnlyIfRequired:
					if Globals.SETTINGS.CurrentTemplate != Globals.SETTINGS.TemplateName:
						Globals.SETTINGS.IsPhotogrammetryNeeded = True
					else:
						Globals.SETTINGS.IsPhotogrammetryNeeded = False
				Globals.SETTINGS.CurrentTemplate = Globals.SETTINGS.TemplateName
		except Globals.EXIT_EXCEPTIONS:
			raise
		except Exception as error:
			self.log.exception( str( error ) )
			Globals.SETTINGS.CurrentTemplate = None
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'buttonTemplateChoose' ):
				Globals.DIALOGS.STARTDIALOG.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
			return None
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'buttonTemplateChoose' ):
			display_name = ''
			try:
				display_name = template['template_description']
			except:  # if it fails the non interactive cmd was called
				display_name = Globals.SETTINGS.CurrentTemplate.split( chr( 0x7 ) )[-1]

			if display_name.endswith('.project_template'):
				display_name = display_name[:-len( '.project_template' )]

			Globals.DIALOGS.STARTDIALOG.buttonTemplateChoose.text = display_name
		self.log.info( 'opened template "{}"'.format( Globals.SETTINGS.CurrentTemplate ) )

	def _enable_start_button( self ):
		'''
		This function is responsible to enable or disable the Start button depending on the user input.
		It enables the start button only when each input field of the default start dialog is not empty and the user chose a project template.
		'''
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'buttonNext' ):
			if ( ( Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'inputSerial' ) and ( len( Globals.DIALOGS.STARTDIALOG.inputSerial.value ) > 0 ) ) and
				( Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'userlist' ) and ( len( Globals.DIALOGS.STARTDIALOG.userlist.value ) > 0 ) )
				and Globals.SETTINGS.CurrentTemplate is not None ):
				Globals.DIALOGS.STARTDIALOG.buttonNext.enabled = True
			else:
				Globals.DIALOGS.STARTDIALOG.buttonNext.enabled = False

	def async_process_signals( self ):
		'''
		process async signals
		'''
		for last_result in Globals.ASYNC_SERVER.pop_results():
			if last_result == Communicate.SIGNAL_PROCESS:
				self.log.info( str( last_result.value ) )
			elif last_result == Communicate.SIGNAL_RESULT:
				self.log.info( str( last_result.value ) )

	def start_dialog_handler( self, widget ):
		'''
		The function is the dialog handler function
		'''
		# handler is called directly after first show
		if widget == 'initialize':
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'inputSerial' ):
				Globals.DIALOGS.STARTDIALOG.inputSerial.value = ''  # dont keep the serial
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'buttonNext' ):
				Globals.DIALOGS.STARTDIALOG.buttonNext.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'inputSerial' ):
				Globals.DIALOGS.STARTDIALOG.inputSerial.focus = True

		if Globals.SETTINGS.Async:
			while Globals.ASYNC_SERVER.process_signals():
				pass
			self.async_process_signals()

		if isinstance( widget, gom.Widget ) and widget.name == 'inputSerial':
			pass
		elif isinstance( widget, gom.Widget ) and widget.name == 'userlist':
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.STARTDIALOG, 'inputSerial' ):
				if ( len( Globals.DIALOGS.STARTDIALOG.inputSerial.value ) == 0 ):
					Globals.DIALOGS.STARTDIALOG.inputSerial.focus = True
		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonTemplateChoose':
			Globals.DIALOGS.STARTDIALOG.enabled = False
			self.open_template()
			Globals.DIALOGS.STARTDIALOG.enabled = True
		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonNext':
			gom.script.sys.close_user_defined_dialog( dialog = Globals.DIALOGS.STARTDIALOG, result = True )
		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonExit':
			gom.script.sys.close_user_defined_dialog( dialog = Globals.DIALOGS.STARTDIALOG, result = False )
			sys.exit( 0 )  # throw SystemExit
		self._enable_start_button()

###########
# V8 StartUp class

class MultiPartSerial:
	'''
	container class to store per multipart input serial and corresponding project template
	'''
	def __init__( self, serial = '', template = '', template_cfg = '' ):
		self._serial = serial
		self._template = template
		self._template_cfg = template_cfg
	@property
	def serial( self ):
		return self._serial
	@serial.setter
	def serial( self, value ):
		self._serial = value
		return self._serial
	@property
	def template( self ):
		return self._template
	@template.setter
	def template( self, value ):
		self._template = value
		return self._template
	@property
	def template_cfg( self ):
		return self._template_cfg
	@template_cfg.setter
	def template_cfg( self, value ):
		self._template_cfg = value
		return self._template_cfg
	def valid( self ):
		if not len( self.serial ) or not len( self.template ):
			return False
		return True
	def __repr__( self ):
		return 'serial: {} template: {} template_cfg: {}'.format( self.serial, self.template, self.template_cfg )

class StartUpV8( Utils.GenericLogClass ):
	'''
	This class manages the StartUp step as mentioned in the docstring of Workflow.
	'''

	def __init__( self, logger ):
		'''
		init logging and subclasses
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.barcode_instance = None
		# batch process
		self._multipart_serials = {}
		self._multipart_max_serials = 0
		# multipart scanning
		self.multi_mode_template = None
		self.parts = []
		self.part_results = {}
		self.page = None

		# if set directly open the template
		if (not Globals.SETTINGS.ShowTemplateDialog
			and len(Globals.SETTINGS.TemplateName)
			and not Globals.SETTINGS.BatchScan):
			Globals.SETTINGS.CurrentTemplateIsConnected = False
			Globals.SETTINGS.CurrentTemplateConnectedUrl = ''
			Globals.SETTINGS.CurrentTemplateConnectedProjectId = ''
			Globals.SETTINGS.CurrentTemplate = Globals.SETTINGS.TemplateName
			Globals.SETTINGS.CurrentTemplateCfg = Globals.SETTINGS.TemplateConfigLevel
		Globals.DIALOGS.localize_startdialog()

		self.dialog = Globals.DIALOGS.STARTDIALOG_FIXTURE
		self.partdialog = Globals.DIALOGS.STARTDIALOG_PER_PART

		if Globals.SETTINGS.BatchScan:
			if Globals.DIALOGS.has_widget( self.dialog, 'buttonNext' ):
				self.dialog.buttonNext.text = Globals.LOCALIZATION.multipart_wizard_button_next
				self.dialog.buttonNext.icon_system_type = 'arrow_right'
			if Globals.DIALOGS.has_widget( self.dialog, 'label_template' ):
				self.dialog.label_template.visible = False
				self.dialog.label_template.enabled = False
			if Globals.DIALOGS.has_widget( self.dialog, 'buttonTemplateChoose' ):
				self.dialog.buttonTemplateChoose.visible = False
				self.dialog.buttonTemplateChoose.enabled = False
			if Globals.DIALOGS.has_widget( self.dialog, 'label_serial' ):
				self.dialog.label_serial.visible = False
				self.dialog.label_serial.enabled = False
			if Globals.DIALOGS.has_widget( self.dialog, 'inputSerial' ):
				self.dialog.inputSerial.visible = False
				self.dialog.inputSerial.enabled = False

		if not Globals.SETTINGS.BarCodeScanner or not Globals.SETTINGS.SeparatedFixtureRegEx:
			if Globals.DIALOGS.has_widget( self.dialog, 'label_fixture' ):
				self.dialog.label_fixture.visible = False
				self.dialog.label_fixture.enabled = False
			if Globals.DIALOGS.has_widget( self.dialog, 'inputFixture' ):
				self.dialog.inputFixture.visible = False
				self.dialog.inputFixture.enabled = False

		if Globals.SETTINGS.UseLoginName:
			if Globals.DIALOGS.has_widget( self.dialog, 'userlist' ):
				self.dialog.userlist.items = [gom.app.get ( 'current_user' )]
				self.dialog.userlist.enabled = False

		if Globals.SETTINGS.LogoImage == "":
			if Globals.DIALOGS.has_widget( self.dialog, 'image' ):
				self.dialog.image.visible = False
				self.dialog.image.enabled = False
			if Globals.DIALOGS.has_widget( self.partdialog, 'image' ):
				self.partdialog.image.visible = False
				self.partdialog.image.enabled = False
			if Globals.DIALOGS.has_widget(
					Globals.DIALOGS.MULTIPART_WIZARD, 'image' ):
				Globals.DIALOGS.MULTIPART_WIZARD.image.visible = False
				Globals.DIALOGS.MULTIPART_WIZARD.image.enabled = False
			if Globals.DIALOGS.has_widget(
					Globals.DIALOGS.MULTIPARTWAIT_DIALOG, 'image' ):
				Globals.DIALOGS.MULTIPARTWAIT_DIALOG.image.visible = False
				Globals.DIALOGS.MULTIPARTWAIT_DIALOG.image.enabled = False
			if Globals.DIALOGS.has_widget(
					Globals.DIALOGS.TEMPERATURE_DIALOG, 'image' ):
				Globals.DIALOGS.TEMPERATURE_DIALOG.image.visible = False
				Globals.DIALOGS.TEMPERATURE_DIALOG.image.enabled = False
				
		if not Globals.FEATURE_SET.DRC_PRIMARY_INST and not Globals.FEATURE_SET.DRC_SECONDARY_INST:
			if Globals.DIALOGS.has_widget( self.dialog, 'button_extension' ):
				self.dialog.button_extension.enabled = False
				self.dialog.button_extension.visible = False
			if Globals.DIALOGS.has_widget( self.partdialog, 'button_extension' ):
				self.partdialog.button_extension.enabled = False
				self.partdialog.button_extension.visible = False

		# reduce start dialog
		if Globals.DIALOGS.has_widget( self.dialog, 'label_part' ):
			self.dialog.label_part.visible = False
		if Globals.DIALOGS.has_widget( self.dialog, 'buttonPrev' ):
			self.dialog.buttonPrev.enabled = False
			self.dialog.buttonPrev.visible = False
		
		# reduce per part dialog
		if Globals.DIALOGS.has_widget( self.partdialog, 'label_title' ):
			self.partdialog.label_title.visible = False
		if Globals.DIALOGS.has_widget( self.partdialog, 'label_user' ):
			self.partdialog.label_user.visible = False
		if Globals.DIALOGS.has_widget( self.partdialog, 'userlist' ):
			self.partdialog.userlist.enabled = False
			self.partdialog.userlist.visible = False
		if Globals.DIALOGS.has_widget( self.partdialog, 'label_fixture' ):
			self.partdialog.label_fixture.visible = False
		if Globals.DIALOGS.has_widget( self.partdialog, 'inputFixture' ):
			self.partdialog.inputFixture.enabled = False
			self.partdialog.inputFixture.visible = False
		if Globals.DIALOGS.has_widget( self.partdialog, 'label_template' ):
			self.partdialog.label_template.visible = False
		if Globals.DIALOGS.has_widget( self.partdialog, 'buttonTemplateChoose' ):
			self.partdialog.buttonTemplateChoose.enabled = False
			self.partdialog.buttonTemplateChoose.visible = False
		if Globals.DIALOGS.has_widget( self.partdialog, 'button_extension' ):
			self.partdialog.button_extension.enabled = False

		self.dialog.handler = self.start_dialog_handler
		self.partdialog.handler = self.multi_handler

		if Globals.SETTINGS.BarCodeScanner:
			self.barcode_instance = BarCode.BarCode( self.baselog, Globals.SETTINGS.BarCodeCOMPort, Globals.SETTINGS.BarCodeDelimiter )
			if not self.barcode_instance.connected:
				self.log.exception( 'Failed to connect to BarCodeScanner' )
				if not Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
											Globals.LOCALIZATION.msg_barcode_connectionfailed.format( Globals.SETTINGS.BarCodeCOMPort + 1 ),
											sic_path = Globals.SETTINGS.SavePath, retry_enabled = True, retry_text = Globals.LOCALIZATION.errordialog_button_continue ):
					sys.exit( 0 )
				self.barcode_instance = None
			else:
				self.dialog.timer.interval = 500
				self.dialog.timer.enabled = True
				self.partdialog.timer.interval = 500
				self.partdialog.timer.enabled = True
		elif Globals.SETTINGS.Async:
			self.dialog.timer.interval = 5000  # every 5s
			self.dialog.timer.enabled = True
			self.partdialog.timer.interval = 5000  # every 5s
			self.partdialog.timer.enabled = True

		if Globals.FEATURE_SET.DRC_PRIMARY_INST or Globals.FEATURE_SET.DRC_SECONDARY_INST:
			self.dialog.timer.interval = 500
			self.dialog.timer.enabled = True
			self.partdialog.timer.interval = 500
			self.partdialog.timer.enabled = True
			Globals.TIMER.registerHandler( Globals.DRC_EXTENSION.globalTimerCheck )
		if Globals.FEATURE_SET.DRC_SECONDARY_INST:
			if Globals.DIALOGS.has_widget( self.dialog, 'buttonTemplateChoose' ):
				self.dialog.buttonTemplateChoose.enabled = False

		self.template_match = BarCode.CodeToTemplateAssignments( self.baselog, Globals.SETTINGS.TEMPLATE_MATCH_FILE )

	def is_widget_available( self, widget_name ):
		'''
		checks if a given widget name is available inside of the startup dialog
		'''
		if Globals.DIALOGS.has_widget( self.dialog, widget_name ):
			return getattr( self.dialog, widget_name ).enabled
		return False

	def execute( self ):
		'''
		This function shows the dialog and creates results
		Returns:
		True - if the dialog was shown and was left by clicking the start button.
		False - Otherwise
		'''
		gom.script.sys.set_kiosk_status_bar(status=1)
		# get and check table of additional keywords
		self.set_additional_project_keywords()
		if not self.check_additional_project_keywords( self.dialog ):
			return False
		if not self.check_additional_perpart_keywords( self.partdialog ):
			return False

		if Globals.SETTINGS.CurrentTemplate is not None:
			# dont reopen in multi part mode
			if not Globals.SETTINGS.BatchScan:
				# dont reopen template if a csv file exists (could be the wrong template for the next run)
				if len( self.template_match.templateDefinitions ):
					Globals.SETTINGS.CurrentTemplate = None
					Globals.SETTINGS.CurrentTemplateCfg = None
					if Globals.DIALOGS.has_widget( self.dialog, 'buttonTemplateChoose' ):
						self.dialog.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
				else:
					self.log.info( 'preopening last template "{}"'.format( Globals.SETTINGS.CurrentTemplate ) )
					self.open_template( True )
					self.log.info( 'finished preopening' )
		else:
			if Globals.DIALOGS.has_widget( self.dialog, 'buttonTemplateChoose' ):
				self.dialog.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template

		# create and show startup dialog
		if Globals.DIALOGS.has_widget( self.dialog, 'inputSerial' ):
			self.dialog.inputSerial.value = ''  # dont keep the serial
		if Globals.DIALOGS.has_widget( self.partdialog, 'inputSerial' ):
			self.partdialog.inputSerial.value = ''  # dont keep the serial
		# reset input values of additional project keywords
		try:
			for (_, _, field, _, *rest) in Globals.ADDITIONAL_PROJECTKEYWORDS:
				# rest [1] is the default value, if present
				# other keywords keep their value
				if field is not None and len( rest ) >= 2 and rest[1] is not None:
					getattr( self.dialog, field ).value = rest[1]
		except Exception as e:
			self.log.exception( 'Reset of input field failed: ' + str( e ))

		if Globals.DIALOGS.has_widget( self.dialog, 'buttonNext' ):
			self.dialog.buttonNext.enabled = False

		# cleanup multipart serial/template storage
		self._multipart_serials = {}
		# reset multiple scanning parts
		self.multi_mode_template = None
		self.parts = []
		self.part_results = {}
		self.page = None

		result = self.show_dialog()
		return result
	
	def run_software_drc(self):
		try:
			self.log.debug('starting software drc')
			Globals.DIALOGS.toggleshow_wait_dialog(Globals.LOCALIZATION.waitdialog_software_execute)
			args = Globals.SETTINGS.SoftwareDRCMode.split(Communicate.MLIST_SEPARATOR)
			if len(args) and args[0] == 'interactive':
				execute_cmd = gom.interactive.automation.execute_measurement_series_on_secondary_side
			elif len(args) and args[0] == 'script':
				execute_cmd = gom.script.automation.execute_measurement_series_on_secondary_side
			else:
				raise Exception ('Invalid command arguments: ' + Globals.SETTINGS.SoftwareDRCMode)
			if len(args) >= 2:
				series = args[1:-1]
				skip = [int(x) for x in args[-1].split(',') if len(x)]
				execute_cmd (measurement_series=series, skip_measurements=skip)
			else:
				execute_cmd ()
			Globals.DRC_EXTENSION.send_software_drc_success()
		except gom.BreakError as e:
			Globals.DRC_EXTENSION.send_software_drc_failure( 'ERROR=GAPP-0011' )
		except gom.RequestError as e:
			errstr = e.args[0]
			if len(e.args[1]): errstr += '\n' + e.args[1]
			Globals.DRC_EXTENSION.send_software_drc_failure( 'ERROR={}'.format(errstr) )
		except Exception as e:
			self.log.exception( repr(e) )
			Globals.DRC_EXTENSION.send_software_drc_failure( repr(e) )
		finally:
			gom.script.sys.close_project()
			Globals.SETTINGS.SoftwareDRCMode = None
			Globals.DIALOGS.toggleshow_wait_dialog(show=False)

	def show_dialog( self ):
		'''
		This function shows the start dialog Globals.DIALOGS.STARTDIALOG
		Returns:
		True - if the dialog was left by the Start button
		False - otherwise
		'''
		try:
			while True:
				result = gom.script.sys.show_user_defined_dialog ( dialog = self.dialog )
				if Globals.FEATURE_SET.DRC_SECONDARY_INST and Globals.SETTINGS.SoftwareDRCMode:
					self.run_software_drc()
					continue
				if result and Globals.SETTINGS.BatchScan:
					if Globals.FEATURE_SET.DRC_SECONDARY_INST and not Globals.FEATURE_SET.DRC_UNPAIRED:
						return True
					result = self.show_multipart_wizard()
					if result is None:  # special treatment None means back to start screen
						continue
					return result
				elif result == 'parts':
					result = gom.script.sys.show_user_defined_dialog ( dialog = self.partdialog )
					if result is None:
						continue
					return result
				else:
					return result
		except Globals.EXIT_EXCEPTIONS:
			self.log.exception( 'SystemExit' )
			raise
		except gom.BreakError:
			self.log.info( 'BreakError catched' )
			return False
		except Exception as error:
			self.log.exception( str( error ) )
			return False

	@property
	def Result( self ):
		'''
		This function creates a dictionary containing the user input from the start dialog GlOBALS.DIALOGS.STARTDIALOG

		Returns:
		The dictionary containing the user input from the start dialog.
		'''
		try:
			res = {'user':'', 'serial':''}
			if Globals.DIALOGS.has_widget( self.dialog, 'userlist' ):  # will be disabled for windows login name
				res['user'] = self.dialog.userlist.value
			if self.is_widget_available( 'inputSerial' ):
				res['serial'] = self.dialog.inputSerial.value
			if self.is_widget_available( 'inputFixture' ):
				res['fixture'] = self.dialog.inputFixture.value

			# get user input for additional project keywords
			for (key, _, field, _, *rest) in Globals.ADDITIONAL_PROJECTKEYWORDS:
				if key is None or field is None:
					continue
				# rest[0] is a string conversion function, if present
				if len( rest ) >= 1 and rest[0] is not None:
					val = rest[0]( key, field, self.dialog )
					if type( val ) != str:
						raise TypeError( 'String conversion function (' + key
							+ ') from ADDITIONAL_PROJECTKEYWORDS did not return a string.' )
				else:
					val = getattr( self.dialog, field ).value
					if type( val ) != str:
						val = str( val )

				res[key] = val

			if self.part_results != {}:
				# mapping info - user/fixture are never per part (I hope)
				map = {'inputSerial': 'serial'}
				for (key, _, field, _, *rest) in Globals.ADDITIONAL_PERPARTKEYWORDS:
					map[field] = key

					# apply string conversion function
					for (part, items) in self.part_results.items():
						# rest[0] is a string conversion function, if present
						if len( rest ) >= 1 and rest[0] is not None:
							val = rest[0]( key, field, items )
							if type( val ) != str:
								raise TypeError( 'String conversion function (' + key
									+ ') from ADDITIONAL_PERPARTKEYWORDS did not return a string.' )
							self.part_results[part][field] = val

				# map input fields to res keys
				res['__parts__'] = {
					part: {map.get( input, input ): val for (input, val) in items.items()}
					for (part, items) in self.part_results.items()}
		except Exception as e:
			self.log.exception( 'Error in Result collection: ' + str( e ))

		return res

	@property
	def MultiPartResult( self ):
		'''
		returns a dictionary with serial and project template as values
		'''
		return self._multipart_serials

	@property
	def Template_filter( self ):
		'''
		filter definition for open_template
		'''
		serial = None
		input = self.input_for_template_match()
		if self.is_widget_available( input ):
			serial = getattr( self.dialog, input ).value
		if serial:
			filters = self.template_match.findMatching( serial )
			if filters is not None:
				return filters
			else:
				if Globals.SETTINGS.Inline: # try directly the serial number as template name
					return [serial.replace('/', chr(0x7)) + '.project_template']
		return ['.*']

	def input_for_template_match( self ):
		'''
		Determine which input field should be used for template matching.
		Input field need not exist.
		Use self.dialog for access to the currently opened dialog.
		'''
		if len( Globals.SETTINGS.SeparatedFixtureRegEx ):
			return 'inputFixture'
		else:
			return 'inputSerial'

	def open_template( self, startup = False, multipart = None ):
		'''
		create a project from template
		if startup is given directly opens last used template
		'''
		if not startup:
			# if the filter is unique (only one template would match)
			# directly open the project template
			unique_template, unique_cfg = self.is_template_filter_unique()
			if unique_template is not None and unique_template == Globals.SETTINGS.CurrentTemplate and Globals.SETTINGS.CurrentTemplateCfg == unique_cfg:
				self.log.debug( 'already open' )
				self._after_template_opened( opened_template = { 'template_name': unique_template, 'config_level': unique_cfg } )
				return
			elif unique_template is not None:
				gom.script.sys.close_project ()
				if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.PrimarySideActive():
					template = dict()
					template['template_name'] = unique_template
					template['config_level'] = unique_cfg
					template['DRC_Ext_DelayedLoading'] = True
				else:
					template = gom.script.sys.create_project_from_template ( 
						config_level = unique_cfg,
						template_name = unique_template )
					self.log.debug( 'opened automatically {}'.format( unique_template ) )
					template['template_name'] = unique_template
					template['config_level'] = unique_cfg
				self._after_template_opened( template )
				return
			elif Globals.SETTINGS.Inline:
				opened_template = { 'template_name': None, 'config_level': None }
				self._after_template_opened( opened_template )
				return

		gom.script.sys.close_project ()
		opened_template = { 'template_name': None, 'config_level': None }
		try:
			template_categories = [Globals.SETTINGS.TemplateCategory]
			if template_categories[0] == 'both':
				template_categories = ['connected_project', 'project_template']

			cfg_level = [Globals.SETTINGS.TemplateConfigLevel]
			if cfg_level[0] == 'both':
				cfg_level = ['shared', 'user']

			# called directly after dialog show or for multipart
			if startup:
				if Globals.SETTINGS.CurrentTemplateIsConnected:
					gom.script.sys.open_connected_project_draft (
						mode_draft='add_scan_data', 
						project_id_draft=Globals.SETTINGS.CurrentTemplateConnectedProjectId, 
						url_draft=Globals.SETTINGS.CurrentTemplateConnectedUrl
					)
				else:
					template = gom.script.sys.create_project_from_template ( 
						config_level = Globals.SETTINGS.CurrentTemplateCfg,
						template_name = Globals.SETTINGS.CurrentTemplate )
				opened_template['is_connected_project'] = Globals.SETTINGS.CurrentTemplateIsConnected
				opened_template['connected_project_id'] = Globals.SETTINGS.CurrentTemplateConnectedProjectId
				opened_template['connected_url'] = Globals.SETTINGS.CurrentTemplateConnectedUrl
				opened_template['template_name'] = Globals.SETTINGS.CurrentTemplate
				opened_template['config_level'] = Globals.SETTINGS.CurrentTemplateCfg
			# show the template dialog
			elif Globals.SETTINGS.ShowTemplateDialog:
				filter = self.Template_filter  # first get the filter before deactivating the dialog
				self.dialog.enabled = False
				if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.PrimarySideActive():
					# open script later
					visible_templates = gom.interactive.sys.get_visible_project_templates ( 
						config_levels = cfg_level,
						regex_filters = filter )
					opened_template['is_connected_project'] = False
					opened_template['connected_url'] = ''
					opened_template['connected_project_id'] = ''
					opened_template['template_name'] = visible_templates['template_name']
					opened_template['config_level'] = visible_templates['config_level']
					opened_template['DRC_Ext_DelayedLoading'] = True
				else:
					opened_template = gom.interactive.sys.create_project_from_template ( 
						project_template_categories_draft = template_categories,
						connected_project_sources_draft = Globals.SETTINGS.ConnectedProjectSources,
						config_levels = cfg_level,
						template_name = Globals.SETTINGS.TemplateName,
						regex_filters = filter )
			# dont show the template dialog
			else:
				template = gom.script.sys.create_project_from_template ( 
					config_level = Globals.SETTINGS.TemplateConfigLevel,
					template_name = Globals.SETTINGS.TemplateName )
				opened_template['is_connected_project'] = False
				opened_template['template_name'] = Globals.SETTINGS.TemplateName
				opened_template['config_level'] = Globals.SETTINGS.TemplateConfigLevel
		except Globals.EXIT_EXCEPTIONS:
			raise
		except gom.BreakError:
			pass
		except Exception as error:
			self.log.exception( str( error ) )
		finally:
			self.dialog.enabled = True

		res = self._after_template_opened( opened_template, multipart )
		self.log.info( 'opened template "{}"'.format( Globals.SETTINGS.CurrentTemplate ) )
		return res

	def _after_template_opened( self, opened_template, multipart = None ):
		'''
		after opening a prj template
		change button name, set global variables
		'''
		if (multipart is not None and opened_template['template_name'] is not None
			and 'DRC_Ext_DelayedLoading' not in opened_template):
			# skip multipart scanning templates in multipart (batchscan) mode
			if Utils.multi_part_evaluation_status():
				return 'skipmulti'

		Globals.SETTINGS.TemplateWasChanged = Globals.SETTINGS.LastStartedTemplate != opened_template['template_name']
		if Globals.SETTINGS.PhotogrammetryOnlyIfRequired:
			if Globals.SETTINGS.TemplateWasChanged:
				Globals.SETTINGS.IsPhotogrammetryNeeded = True
			else:
				Globals.SETTINGS.IsPhotogrammetryNeeded = False

		Globals.SETTINGS.CurrentTemplateIsConnected = opened_template['is_connected_project'] if 'is_connected_project' in opened_template else False
		Globals.SETTINGS.CurrentTemplateConnectedUrl = opened_template['connected_url'] if 'connected_url' in opened_template else ''
		Globals.SETTINGS.CurrentTemplateConnectedProjectId = opened_template['connected_project_id'] if 'connected_project_id' in opened_template else ''
		Globals.SETTINGS.CurrentTemplate = opened_template['template_name']
		Globals.SETTINGS.CurrentTemplateCfg = opened_template['config_level'] if 'config_level' in opened_template else ''

		if Globals.DIALOGS.has_widget( self.dialog, 'buttonTemplateChoose' ):
			if Globals.SETTINGS.CurrentTemplate is None:
				self.dialog.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
				return

			display_name = ''
			try:
				display_name = opened_template['template_description']
			except:  # if it fails the non interactive cmd was called
				display_name = Globals.SETTINGS.CurrentTemplate.split( chr( 0x7 ) )[-1]
		
			if display_name.endswith('.project_template'):
				display_name = display_name[:-len( '.project_template' )]

			self.dialog.buttonTemplateChoose.text = display_name

		if Globals.DRC_EXTENSION is not None:
			try:
				return Globals.DRC_EXTENSION.after_template_opened(self, opened_template, multipart)
			except Exception as e:
				self.log.exception(e)


	def _enable_start_button_ext( self ):
		if Globals.DIALOGS.has_widget( self.dialog, 'buttonNext' ):
			if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.PrimarySideActive():
				if not Globals.DRC_EXTENSION.todos_done():
					self.dialog.buttonNext.enabled = False
				if not Globals.FEATURE_SET.DRC_UNPAIRED and not Globals.DRC_EXTENSION.connected:
					self.dialog.buttonNext.enabled = False
			if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActive():
				self.dialog.buttonNext.enabled = False

	def _enable_start_button( self ):
		'''
		This function is responsible to enable or disable the Start button depending on the user input.
		It enables the start button only when each input field of the default start dialog is not empty and the user chose a project template.
		'''
		if Globals.DIALOGS.has_widget( self.dialog, 'buttonNext' ):
			serial_filled = True if not self.is_widget_available( 'inputSerial' ) else ( len( self.dialog.inputSerial.value ) > 0 )
			fixture_filled = True if not self.is_widget_available( 'inputFixture' ) else ( len( self.dialog.inputFixture.value ) > 0 )
			user_filled = True if not self.is_widget_available( 'userlist' ) else ( len( self.dialog.userlist.value ) > 0 )
			if Globals.SETTINGS.BatchScan:
				template_filled = True
			else:
				template_filled = True if not self.is_widget_available( 'buttonTemplateChoose' ) else Globals.SETTINGS.CurrentTemplate is not None

			pks_filled = True
			for (_, _, field, opt, *_) in Globals.ADDITIONAL_PROJECTKEYWORDS:
				# optional project keyword
				if opt or field is None:
					continue

				val = getattr( self.dialog, field ).value
				# no check possible if field is not a string value
				if type( val ) != str:
					continue

				if val == '':
					pks_filled = False
					break

			self.dialog.buttonNext.enabled = (
				template_filled
				and serial_filled
				and fixture_filled
				and user_filled
				and pks_filled
			)

			self._enable_start_button_ext()

	def _multi_buttons( self ):
		# prev / next
		if Globals.DIALOGS.has_widget( self.partdialog, 'buttonNext' ):
			if self.page == self.parts[-1]:
				self.partdialog.buttonNext.text = Globals.LOCALIZATION.startdialog_button_start
				self.partdialog.buttonNext.icon_system_type = 'ok'
			else:
				self.partdialog.buttonNext.text = Globals.LOCALIZATION.startdialog_button_next
				self.partdialog.buttonNext.icon_system_type = 'arrow_right'
				self.partdialog.buttonNext.enabled = True

		if Globals.DIALOGS.has_widget( self.dialog, 'buttonPrev' ):
			self.dialog.buttonPrev.enabled = True

		# enable start from std start dialog + serial number inputs per part condition
		if Globals.DIALOGS.has_widget( self.partdialog, 'buttonNext' ) and self.page == self.parts[-1]:
			# compute start button state from std start dialog
			self._enable_start_button()
			std_enabled = self.dialog.buttonNext.enabled

			# modify start button state with per part check
			if std_enabled:
				inputs_set = True
				inputs = [field for (_, _, field, opt, *_) in Globals.ADDITIONAL_PERPARTKEYWORDS if not opt]
				if not Globals.SETTINGS.MultiPartBatchSerial:
					inputs = ['inputSerial'] + inputs
				for part in self.parts:
					for input in inputs:
						# last part looks at input field, the other at cached result
						# no check possible if field contains not a string value
						input_filled = False
						if part == self.parts[-1]:
							if Globals.DIALOGS.has_widget( self.partdialog, input ):
								val = getattr( self.partdialog, input ).value
								input_filled = type( val ) != str or val != ''
						else:
							val = ''
							try:
								val = self.part_results[part][input]
							except:
								pass
							input_filled = type( val ) != str or val != ''

						if not input_filled:
							inputs_set = False
							break
					if not inputs_set:
						break

				if inputs_set:
					self.partdialog.buttonNext.enabled = True
				else:
					self.partdialog.buttonNext.enabled = False
			else:
				self.partdialog.buttonNext.enabled = False


	def _check_input_values( self, dialog ):
		'''
		Empty template function for plausibility checks on input values.
		This function is called when the start button is pressed.
		In case of an error use the commented example below
		to show an error message and return False to abort the start.
		'''

		# template for showing an error dialog:
		# if input_value != ...:
		#	Globals.DIALOGS.show_simple_errormsg("Dialog title", "Error message")
		#	return False

		return True

	def async_process_signals( self ):
		'''
		process async signals
		'''
		for last_result in Globals.ASYNC_SERVER.pop_results():
			if last_result == Communicate.SIGNAL_PROCESS:
				self.log.info( str( last_result.value ) )
			elif last_result == Communicate.SIGNAL_RESULT:
				self.log.info( str( last_result.value ) )

	def get_last_barcodes( self ):
		'''
		returns last scanned bar codes
		'''
		if self.barcode_instance is not None:
			code = self.barcode_instance.pop_codes()
			if len( code ):
				self.log.info( 'scanned barcodes: {}'.format( code ) )
				return code
		return None

	def is_template_filter_unique( self ):
		'''
		returns the prj template name if the current template filter would only result in one visible project
		else returns None
		'''
		cfg_level = [Globals.SETTINGS.TemplateConfigLevel]
		if cfg_level[0] == 'both':
			cfg_level = ['shared', 'user']
		visible_templates = gom.script.sys.get_visible_project_templates ( 
			config_levels = cfg_level,
			regex_filters = self.Template_filter )
		if len( visible_templates ) == 1:
			return visible_templates[0]['template_name'], visible_templates[0]['config_level']
		return None, None

	def barcode_target( self, code ):
		'''
		Determine the name of an input field where the barcode should go.
		Also, determine if the template match mechanism should be triggered for this code,
		See also "input_for_template_match" which determines the input field used for matching.

		Returns a pair of "name of input field" (str), "trigger template selection" (bool)
		'''
		target = 'inputSerial'
		trigger_template_selection = False
		if len( Globals.SETTINGS.SeparatedFixtureRegEx ):
			if re.match( Globals.SETTINGS.SeparatedFixtureRegEx, code ):
				target = 'inputFixture'

		# in non-BatchScan mode, fixture input also trigger template selection
		if not Globals.SETTINGS.BatchScan:
			if target == 'inputFixture':
				trigger_template_selection = True
			if target == 'inputSerial' and len( Globals.SETTINGS.SeparatedFixtureRegEx ) == 0:
				trigger_template_selection = True

		return target, trigger_template_selection

	def fill_from_barcodes( self ):
		'''
		get latest barcodes from scanner and fill it into serial/fixture fields
		will also open template dialog
		'''
		if self.barcode_instance is None:
			return
		codes = self.get_last_barcodes()
		if codes is None:
			return

		new_serial = False
		used_targets = set()
		codes.reverse()  # iterate in reverse order
		for code in codes[:]:
			input_target, trigger_selection = self.barcode_target( code )
			if trigger_selection:
				new_serial = True
			if input_target not in used_targets and self.is_widget_available( input_target ):
				getattr( self.dialog, input_target ).value = code
				codes.remove( code )
			# track target input fields, so only last code is assigned
			used_targets.add( input_target )

		# for multipart mode only fill the fixture input field and place the remaining codes into the wizard
		if Globals.SETTINGS.BatchScan:
			self.fill_multipart_serials( codes )
		elif new_serial:
			self.open_template()


	def toggle_single_or_multi_mode( self, widget, initial=False ):
		if self.is_multi_mode():
			self.switch_to_multi( widget )
		elif initial or self.multi_mode_template:
			self.switch_to_single( widget )

	def is_multi_mode( self ):
		if self.multi_mode_template and self.multi_mode_template == Globals.SETTINGS.CurrentTemplate:
			return True

		if (Utils.multi_part_evaluation_status() and
			(not Globals.SETTINGS.MultiPartBatchSerial or len( Globals.ADDITIONAL_PERPARTKEYWORDS ) > 0)):
			self.parts = Utils.multi_part_evaluation_parts()
			self.parts = [p.name for p in self.parts]
			self.parts.sort()
			return True

		# always update label_serial for single mode
		self._update_serial_label()

		return False

	def _update_serial_label( self ):
		if Globals.DIALOGS.has_widget( self.dialog, 'label_serial' ):
			if Utils.multi_part_evaluation_status() and not Globals.SETTINGS.MultiPartBatchSerial:
				self.dialog.label_serial.text = Globals.LOCALIZATION.startdialog_label_batch
			else:
				self.dialog.label_serial.text = Globals.LOCALIZATION.startdialog_label_serial
		if Globals.DIALOGS.has_widget( self.partdialog, 'label_serial' ):
			if Utils.multi_part_evaluation_status() and Globals.SETTINGS.MultiPartBatchSerial:
				self.partdialog.label_serial.visible = False
				self.partdialog.inputSerial.visible = False
			else:
				self.partdialog.label_serial.visible = True
				self.partdialog.inputSerial.visible = True

	def switch_to_single( self, widget ):
		if Globals.SETTINGS.BatchScan:
			return

		if Globals.DIALOGS.has_widget( self.dialog, 'buttonNext' ):
			self.dialog.buttonNext.text = Globals.LOCALIZATION.startdialog_button_start
			self.dialog.buttonNext.icon_system_type = 'ok'
			self.dialog.buttonNext.visible = True
			self.dialog.buttonNext.enabled = True

		# forget multi stuff...
		self.multi_mode_template = None
		self.parts = []
		self.part_results = {}
		self.page = None

	def switch_to_multi( self, widget ):
		if self.multi_mode_template == Globals.SETTINGS.CurrentTemplate:
			return
		self.multi_mode_template = Globals.SETTINGS.CurrentTemplate

		# init results
		self.part_results = {part: {} for part in self.parts}
		if not Globals.SETTINGS.MultiPartBatchSerial:
			self.part_results = {part: {'inputSerial':''} for part in self.parts}
		# add default values of additional per-part keywords
		try:
			for (_, _, field, _, *rest) in Globals.ADDITIONAL_PERPARTKEYWORDS:
				# rest[1] is the default value, if present
				# other keywords are reset to ''
				if field is not None and len( rest ) >= 2 and rest[1] is not None:
					val = rest[1]
				else:
					val = ''
				for part in self.parts:
					self.part_results[part][field] = val
		except Exception as e:
			self.log.exception( 'Setting default value for per-part keyword failed: ' + str( e ) )
		
		self._update_serial_label()

		if Globals.DIALOGS.has_widget( self.dialog, 'buttonNext' ) and len( self.parts ) > 0:
			self.dialog.buttonNext.text = Globals.LOCALIZATION.startdialog_button_next
			self.dialog.buttonNext.icon_system_type = 'arrow_right'
			self.dialog.buttonNext.enabled = True

		# init page
		self.page = None

	def multi_switch_page( self, page ):
		# old page: copy inputs to results
		input_values = {}
		if self.page is not None:
			inputs = [field for (_,_, field,_,*_) in Globals.ADDITIONAL_PERPARTKEYWORDS]
			if not Globals.SETTINGS.MultiPartBatchSerial:
				inputs = ['inputSerial'] + inputs
			input_values = self.part_dialog_to_results( self.page, inputs )

		self.page = page

		# new page: copy results to input fields
		if self.page is not None:
			if Globals.DIALOGS.has_widget( self.partdialog, 'label_part' ):
				self.partdialog.label_part.text = Globals.LOCALIZATION.startdialog_label_part.format( self.page )

			inputs = [field for (_,_, field,_,*_) in Globals.ADDITIONAL_PERPARTKEYWORDS]
			if not Globals.SETTINGS.MultiPartBatchSerial:
				inputs = ['inputSerial'] + inputs
			input_values = self.part_results_to_dialog( self.page, inputs )

	def part_dialog_to_results( self, partname, inputs ):
		input_values = {}
		for input in inputs:
			val = ''
			if Globals.DIALOGS.has_widget( self.partdialog, input ):
				val = getattr( self.partdialog, input ).value
			input_values[input] = val

		self.part_results[partname] = input_values
		return input_values

	def part_results_to_dialog( self, partname, inputs ):
		input_values = self.part_results[partname]
		for i,v in input_values.items():
			if Globals.DIALOGS.has_widget( self.partdialog, i ):
				getattr( self.partdialog, i ).value = v

		return input_values


	def start_dialog_handler( self, widget ):
		'''
		The function is the dialog handler function
		'''
		# handler is called directly after first show
		if widget == 'initialize':
			if self.is_widget_available( 'inputSerial' ):
				self.dialog.inputSerial.focus = True
		
			# initial configure view for single/multi
			self.toggle_single_or_multi_mode( widget, initial=True )

		if Globals.SETTINGS.Async:
			while Globals.ASYNC_SERVER.process_signals():
				pass
			self.async_process_signals()
		
		if Globals.DRC_EXTENSION is not None:
			if not Globals.DRC_EXTENSION.start_dialog_handler(self, widget):
				return
			self.toggle_single_or_multi_mode( widget, initial=False )

		if self.is_widget_available( 'inputSerial' ) or self.is_widget_available( 'inputFixture' ):
			self.fill_from_barcodes()
			self.toggle_single_or_multi_mode( widget, initial=False )

		if isinstance( widget, str ):
			pass
		elif widget.name == 'inputSerial':
			pass
		elif widget.name == 'inputFixture':
			pass
		elif widget.name == 'userlist':
			if self.is_widget_available( 'inputSerial' ):
				if ( len( self.dialog.inputSerial.value ) == 0 ):
					self.dialog.inputSerial.focus = True
		elif widget.name == 'buttonTemplateChoose':
			self.open_template()
			self.toggle_single_or_multi_mode( widget, initial=False )
		elif widget.name == 'buttonNext':
			if self.multi_mode_template and len( self.parts ) > 0:
				gom.script.sys.close_user_defined_dialog( dialog = self.dialog, result = 'parts' )
			elif self._check_input_values( self.dialog ):
				gom.script.sys.close_user_defined_dialog( dialog = self.dialog, result = True )
		elif widget.name == 'buttonExit':
			gom.script.sys.close_user_defined_dialog( dialog = self.dialog, result = False )
			raise gom.BreakError()

		if self.multi_mode_template is None or len( self.parts ) == 0:
			self._enable_start_button()
		else:
			# for multi mode allow next always, unless extension protests
			if Globals.DIALOGS.has_widget( self.dialog, 'buttonNext' ):
				self.dialog.buttonNext.enabled = True
			self._enable_start_button_ext()

	def multi_handler( self, widget ):
		'''
		start dialog handler function - multiple scanning parts
		'''
		if widget == 'initialize':
			# init page for first part
			self.multi_switch_page( self.parts[0] )

		if Globals.SETTINGS.Async:
			while Globals.ASYNC_SERVER.process_signals():
				pass
			self.async_process_signals()

		# DRC connection display
		if Globals.DRC_EXTENSION is not None:
			if not Globals.DRC_EXTENSION.start_dialog_handler(self, widget):
				return

		# button handling
		if isinstance( widget, str ):
			pass
		elif widget.name == 'buttonPrev':
			if self.page == self.parts[0]:
				self.multi_switch_page( None )
				gom.script.sys.close_user_defined_dialog( dialog = self.partdialog, result = None )
			else:
				self.multi_switch_page( self.parts[self.parts.index( self.page ) - 1] )
		elif widget.name == 'buttonNext':
			if self.page != self.parts[-1]:
				self.multi_switch_page( self.parts[self.parts.index( self.page ) + 1] )
			else:
				self.multi_switch_page( None )
				if self._check_input_values( self.dialog ):
					gom.script.sys.close_user_defined_dialog( dialog = self.partdialog, result = True )
				else:
					# restore current page
					self.multi_switch_page( self.parts[-1] )
		elif widget.name == 'buttonExit':
			gom.script.sys.close_user_defined_dialog( dialog = self.partdialog, result = False )
			raise gom.BreakError()

		# activate/deactivate prev/next
		self._multi_buttons()


	def set_additional_project_keywords( self ):
		'''
		Dummy assignment of additional project keywords.
		To be overridden in CustomPatches.
		'''
		Globals.ADDITIONAL_PROJECTKEYWORDS = []
		Globals.ADDITIONAL_PERPARTKEYWORDS = []

	def _check_additional_keyword_table( self, dialog, pks, name ):
		'''
		Check the information in keyword table 'pks' (table name 'name')
		return True if:
		- list of at least 4-tuples
		- for each tuple: first 3 elements strings (or None), 4th boolean
		- element 1 (keyword name) must not be one of the four predefined ones
		- if 5th element in tuple: must be a callable (string conversion) or None
		- if 6th element in tuple: not checked (default value)
		Otherwise return False
		'''
		if type( pks ) != list:
			self.log.error( name + ' is not a list.' )
			return False
		for pk in pks:
			if type( pk ) != tuple:
				self.log.error( name + ' not a tuple element ' + str( type( pk ) ) )
				return False
			if len( pk ) < 4:
				self.log.error( name + ' tuple element too short ' + str( len( pk ) ) )
				return False
			if ( ( type( pk[0] ) != str and pk[0] is not None )
				or ( type( pk[1] ) != str and pk[1] is not None )
				or ( type( pk[2] ) != str and pk[2] is not None )
				or type( pk[3] ) != bool ):
				self.log.error( name + ' wrong element type '
					+ str( type( pk[0] ) ) + ',' + str( type( pk[1] ) ) + ','
					+ str( type( pk[2] ) ) + ',' + str( type( pk[3] ) ) )
				return False
			if pk[0] in ['inspector', 'part_nr', 'fixture_no', 'date']:
				self.log.error( name + ' predefined keyword not allowed '
					+ str( pk[0] ) )
				return False
			if pk[2] is not None and not Globals.DIALOGS.has_widget( dialog, pk[2] ):
				self.log.error( name + ' dialog does not contain the widget ' + pk[2] )
				return False
			if len( pk ) >= 5 and not callable( pk[4] ) and pk[4] is not None:
				self.log.error( name + ' string conversion function is not callable or not None ' + str( pk[4] ) )
				return False
			# pk[5] (default value) not checked

		return True

	def check_additional_project_keywords( self, dialog ):
		'''
		Check the information in Globals.ADDITIONAL_PROJECTKEYWORDS.
		'''
		res = self._check_additional_keyword_table(
			dialog, Globals.ADDITIONAL_PROJECTKEYWORDS, 'ADDITIONAL_PROJECTKEYWORDS' )
		self.log.debug( 'ADDITIONAL_PROJECTKEYWORDS: '
			+ ', '.join( [str( pk[0] ) for pk in Globals.ADDITIONAL_PROJECTKEYWORDS] ) )
		return res
	def check_additional_perpart_keywords( self, dialog ):
		'''
		Check the information in Globals.ADDITIONAL_PERPARTKEYWORDS.
		'''
		res = self._check_additional_keyword_table(
			dialog, Globals.ADDITIONAL_PERPARTKEYWORDS, 'ADDITIONAL_PERPARTKEYWORDS' )
		self.log.debug( 'ADDITIONAL_PERPARTKEYWORDS: '
			+ ', '.join( [str( pk[0] ) for pk in Globals.ADDITIONAL_PERPARTKEYWORDS] ) )
		return res

	# multipart functions

	def toggle_multipart_row( self, dialog, counter, visible ):
		'''
		set widgets at given position visible/invisible
		'''
		if Globals.DIALOGS.has_widget( dialog, 'label_serial{}'.format( counter ) ):
			getattr( dialog, 'label_serial{}'.format( counter ) ).visible = visible
		if Globals.DIALOGS.has_widget( dialog, 'inputSerial{}'.format( counter ) ):
			getattr( dialog, 'inputSerial{}'.format( counter ) ).visible = visible
			getattr( dialog, 'inputSerial{}'.format( counter ) ).value = ''
		if Globals.DIALOGS.has_widget( dialog, 'del_button{}'.format( counter ) ):
			getattr( dialog, 'del_button{}'.format( counter ) ).visible = visible
		if Globals.DIALOGS.has_widget( dialog, 'label_template{}'.format( counter ) ):
			getattr( dialog, 'label_template{}'.format( counter ) ).visible = visible
		if Globals.DIALOGS.has_widget( dialog, 'button_template{}'.format( counter ) ):
			getattr( dialog, 'button_template{}'.format( counter ) ).visible = visible
			getattr( dialog, 'button_template{}'.format( counter ) ).text = Globals.LOCALIZATION.startdialog_button_template

	def fill_multipart_widget( self, dialog, index, serials ):
		'''
		fills given widget index with given serial data
		'''
		if Globals.DIALOGS.has_widget( dialog, 'inputSerial{}'.format( index ) ):
			getattr( dialog, 'inputSerial{}'.format( index ) ).value = serials[index].serial
		templ_name = Globals.LOCALIZATION.startdialog_button_template
		if len( serials[index].template ):
			templ_name = serials[index].template.split( chr( 0x7 ) )[-1][:-len( '.project_template' )]
		if Globals.DIALOGS.has_widget( dialog, 'button_template{}'.format( index ) ):
			getattr( dialog, 'button_template{}'.format( index ) ).text = templ_name

	def update_multipart_dialog( self, dialog, serials, newline ):
		'''
		fill multipart wizard with given values
		'''
		if newline and len( serials ) == self._multipart_max_serials:  # limit reached
			# set current index to max value
			total_pages = ( len( self._multipart_serials ) // self._multipart_max_serials )
			self._start_serial_counter = total_pages * self._multipart_max_serials
			serials = self.get_current_multipart_data( self._start_serial_counter )  # get last serials

		for i in range( self._multipart_max_serials ):
			if i >= len( serials ):  # hide all fields which would be empty
				self.toggle_multipart_row( dialog, i, False )
			else:  # fill with values
				self.toggle_multipart_row( dialog, i, True )
				self.fill_multipart_widget( dialog, i, serials )
		self.toggle_multipart_row( dialog, len( serials ), True )  # show a empty line

		if Globals.DIALOGS.has_widget( dialog, 'label_multipages' ):
			total_pages = ( len( self._multipart_serials ) // self._multipart_max_serials ) + 1
			current_page = ( self._start_serial_counter // self._multipart_max_serials ) + 1
			dialog.label_multipages.text = Globals.LOCALIZATION.multipart_wizard_label_page.format( current_page, total_pages )
		for w in dialog.widgets:
			if w.name.startswith( 'inputSerial' ) and not len( w.value ) and w.visible:
				w.focus = True  # place the focus onto the first empty field
				break


	def show_multipart_wizard( self ):
		'''
		show wizard dialog for multipart serials
		'''
		# prefill dialog with all barcodes
		codes = self.get_last_barcodes()
		self.fill_multipart_serials( codes )
		self._start_serial_counter = 0
		dialog = Globals.DIALOGS.MULTIPART_WIZARD

		self._multipart_max_serials = 0  # store the max available count of fields per page
		for i in range( 20 ):
			if Globals.DIALOGS.has_widget( dialog, 'inputSerial{}'.format( i ) ):
				self._multipart_max_serials = i + 1
			else:
				break
		serials = self.get_current_multipart_data( self._start_serial_counter )
		self.update_multipart_dialog( dialog, serials, False )

		dialog.handler = partial( self._multipart_serial_dialog_handler, dialog = dialog )
		dialog.timer.interval = 500
		dialog.timer.enabled = True

		try:
			result = gom.script.sys.show_user_defined_dialog ( dialog = dialog )
		except Globals.EXIT_EXCEPTIONS:
			self.log.exception( 'SystemExit' )
			raise
		except gom.BreakError:
			self.log.info( 'BreakError catched' )
			return False
		except Exception as error:
			self.log.exception( str( error ) )
			return False
		return result

	def get_current_multipart_data( self, start_index ):
		'''
		returns current entries from start_index up to max display count
		'''
		serials = [s for i, s in self._multipart_serials.items()
						if i >= start_index and i < start_index + self._multipart_max_serials]
		return serials

	def fill_multipart_serials( self, codes ):
		'''
		appends new serials
		'''
		if codes is None:
			codes = []
		if len( self._multipart_serials.keys() ):
			max_index = max( self._multipart_serials.keys() )
		else:
			max_index = -1
		for i in range( len( codes ) ):
			template, cfg = self.get_multipart_template( codes[i], None )
			self._multipart_serials[max_index + i + 1] = MultiPartSerial( codes[i], template, cfg )

	def get_multipart_template( self, serial, dialog ):
		'''
		select template corresponding to given serial
		returns a pair of
			- empty string or template_name
			- empty string or configuration level of template
		'''
		filter = ['.*']
		if serial:
			filters = self.template_match.findMatching( serial )
			if filters is not None:
				filter = filters
		cfg_level = [Globals.SETTINGS.TemplateConfigLevel]
		if cfg_level[0] == 'both':
			cfg_level = ['shared', 'user']
		visible_templates = gom.script.sys.get_visible_project_templates ( 
			config_levels = cfg_level,
			regex_filters = filter )
		if len( visible_templates ) == 1:  # template is unique
			return visible_templates[0]['template_name'], visible_templates[0]['config_level']
		if dialog is None:
			return '',''
		dialog.enabled = False
		try:
			visible_templates = gom.interactive.sys.get_visible_project_templates ( 
				config_levels = cfg_level,
				regex_filters = filter )
			return visible_templates['template_name'], visible_templates['config_level']
		except:
			return '',''
		finally:
			dialog.enabled = True


	def _multipart_enable_startbutton( self, dialog ):
		if not Globals.DIALOGS.has_widget( dialog, 'buttonFinish' ):
			return
		if not len( self._multipart_serials ):
			dialog.buttonFinish.enabled = False
		for index in self._multipart_serials:
			if self._multipart_serials[index].valid():
				dialog.buttonFinish.enabled = True
				return
		dialog.buttonFinish.enabled = False

	def _multipart_serial_dialog_handler( self, widget, dialog ):
		'''
		dynamic dialog handler for multipart serial no.
		'''
		if self.barcode_instance is not None:
			# grep all barcodes
			codes = self.get_last_barcodes()
			if codes is not None and len( codes ):
				# append new codes and create a new dialog
				self.fill_multipart_serials( codes )
				serials = self.get_current_multipart_data( self._start_serial_counter )
				self.update_multipart_dialog( dialog, serials, True )

		if isinstance( widget, str ):
			pass
		elif widget.name.startswith( 'del_button' ):
			index = int( widget.name[len( 'del_button' ):] ) + self._start_serial_counter
			if index in self._multipart_serials:
				# remove entry and move all following entries
				self._multipart_serials[index] = None
				no_serials = len( self._multipart_serials.keys() )
				for i in range( index + 1, no_serials ):
					self._multipart_serials[i - 1] = self._multipart_serials[i]
				del self._multipart_serials[no_serials - 1]
			serials = self.get_current_multipart_data( self._start_serial_counter )
			self.update_multipart_dialog( dialog, serials, True )
			return
		elif widget.name.startswith( 'inputSerial' ):
			index = int( widget.name[len( 'inputSerial' ):] ) + self._start_serial_counter
			if not len( widget.value ) and index not in self._multipart_serials:
				return  # nothing to update
			elif index in self._multipart_serials and self._multipart_serials[index].serial == widget.value:
				return  # nothing to update
			elif not widget.visible:
				return
			template, template_cfg = self.get_multipart_template( widget.value, None )
			if index in self._multipart_serials:
				self._multipart_serials[index].serial = widget.value
			else:
				self._multipart_serials[index] = MultiPartSerial( serial = widget.value )
			self._multipart_serials[index].template = template
			self._multipart_serials[index].template_cfg = template_cfg
			template_button = 'button_template{}'.format( index - self._start_serial_counter )
			if Globals.DIALOGS.has_widget( dialog, template_button ):
				if len( template ):
					getattr( dialog, template_button ).text = template.split( chr( 0x7 ) )[-1][:-len( '.project_template' )]
				else:
					getattr( dialog, template_button ).text = Globals.LOCALIZATION.startdialog_button_template
		elif widget.name.startswith( 'button_template' ):
			index = int( widget.name[len( 'button_template' ):] ) + self._start_serial_counter
			template, template_cfg = self.get_multipart_template( self._multipart_serials.get( index, MultiPartSerial() ).serial, dialog )
			if index in self._multipart_serials:
				self._multipart_serials[index].template = template
				self._multipart_serials[index].template_cfg = template_cfg
			else:
				self._multipart_serials[index] = MultiPartSerial( template = template, template_cfg = template_cfg )
			if len( template ):
				widget.text = template.split( chr( 0x7 ) )[-1][:-len( '.project_template' )]
			else:
				widget.text = Globals.LOCALIZATION.startdialog_button_template

		elif widget.name == 'buttonPrev':
			if self._start_serial_counter >= self._multipart_max_serials:
				self._start_serial_counter -= self._multipart_max_serials
			else:
				gom.script.sys.close_user_defined_dialog( dialog = dialog, result = None )  # show startdialog
				return
			serials = self.get_current_multipart_data( self._start_serial_counter )
			self.update_multipart_dialog( dialog, serials, False )
		elif widget.name == 'buttonNext':
			# show a new dialog if limit reached
			if len( self._multipart_serials ) >= self._start_serial_counter + self._multipart_max_serials:
				self._start_serial_counter += self._multipart_max_serials
			serials = self.get_current_multipart_data( self._start_serial_counter )
			self.update_multipart_dialog( dialog, serials, False )
			return
		elif widget.name == 'buttonFinish':
			gom.script.sys.close_user_defined_dialog( dialog = dialog, result = True )
			return
		elif widget.name == 'buttonExit':
			raise gom.BreakError()

		self._multipart_enable_startbutton( dialog )


class InlineStartUp( StartUpV8 ):
	'''
	This class manages the StartUp step as mentioned in the docstring of Workflow.
	'''

	def __init__( self, logger, parent ):
		'''
		init logging and subclasses
		'''
		StartUpV8.__init__(self,logger)
		self.parent = parent
		#Control Instance does not connect for DRC Slave
		if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
			Globals.CONTROL_INSTANCE = AsyncClient.DeadClient( self.baselog, '127.0.0.1', 6543, {} )
		else:	
			Globals.CONTROL_INSTANCE = AsyncClient.InlineClient( self.baselog, '127.0.0.1', 6543, {} )
		if not Globals.FEATURE_SET.DRC_SECONDARY_INST:
			Globals.CONTROL_INSTANCE.wait_till_connected()
		Globals.TIMER.setTimeInterval(200)
		Globals.TIMER.registerHandler( self._clientProcessCheck )
		self._delayed_pkts=[]
		self._currentSpecialPosition = []
		self._userdata={}
		if Globals.FEATURE_SET.DRC_PRIMARY_INST or Globals.FEATURE_SET.DRC_SECONDARY_INST:
			Globals.TIMER.registerHandler( Globals.DRC_EXTENSION.globalTimerCheck )
		
			
	def execute (self):
		self.set_additional_project_keywords()
		self._currentSpecialPosition = []
		
		class IdleContext:
			def __init__(self):
				pass
			def __enter__(self):
				if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.other_side_still_active():
					return # dont send idle when other side is still working
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_IDLE, str(1) ) )
			def __exit__(self, exc_type, exc_value, traceback):
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_IDLE, str(0) ) )

		if Globals.SETTINGS.CurrentTemplate is not None:
			if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_SECONDARY_INST and Globals.FEATURE_SET.DRC_SINGLE_SIDE:
				Globals.DRC_EXTENSION.sendSingleSideDone()
				Globals.SETTINGS.CurrentTemplate = None
				Globals.SETTINGS.CurrentTemplateCfg = None
				Globals.FEATURE_SET.DRC_SINGLE_SIDE = False

		with IdleContext() as idlecontext:
			if Globals.SETTINGS.CurrentTemplate is not None and not Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
				self.log.info( 'preopening last template "{}"'.format( Globals.SETTINGS.CurrentTemplate ) )
				self.open_template( True )
				self.log.info( 'finished preopening' )
			if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
				if not self.parent.eval.eval.Sensor.is_initialized():
					self.parent.eval.eval.Sensor.initialize()

			def handler():
				try:
					while Globals.CONTROL_INSTANCE.check_for_activity():
						pass
					if Globals.SETTINGS.ShouldExit:
						return False
					if Globals.DRC_EXTENSION is not None:
						if Globals.DRC_EXTENSION.check_start_signals( self ):
							return True
					while len( self._delayed_pkts ) > 0:
						last_result = self._delayed_pkts.pop( 0 )
						self.log.debug(last_result)

						if last_result == Communicate.SIGNAL_CONTROL_SERIAL:
							self.onSignalSerial(last_result)
						elif last_result == Communicate.SIGNAL_CONTROL_SERIAL2:
							self.onSignalSerial2(last_result)
							
						elif last_result == Communicate.SIGNAL_CONTROL_START:
							self.log.debug('got start')
							if self.onSignalStart(last_result):
								return True
						
						elif last_result == Communicate.SIGNAL_CONTROL_EXIT:
							if self.onSignalExit(last_result):
								return False
						
						elif last_result == Communicate.SIGNAL_CONTROL_RESULT_NOT_NEEDED:
							self.onSignalResultNotNeeded(last_result)
						
						elif last_result == Communicate.SIGNAL_CONTROL_ADDITION_INFO:
							self.onSignalAdditionalInformation(last_result)
						elif last_result == Communicate.SIGNAL_CONTROL_ADDITION_INFO_RAW:
							self.onSignalAdditionalInformationRaw(last_result)
						elif last_result == Communicate.SIGNAL_CONTROL_ADDITION_INFO_RAW2:
							self.onSignalAdditionalInformationRaw2(last_result)

						elif last_result == Communicate.SIGNAL_CONTROL_CLOSETEMPLATE:
							self.onSignalCloseTemplate(last_result)
							
						elif last_result == Communicate.SIGNAL_CONTROL_DEINIT_SENSOR:
							self.onSignalDeInitSensor(last_result)
							
						elif last_result == Communicate.SIGNAL_CONTROL_MOVE_HOME:
							self.onSignalMoveHome(last_result)
								
						elif last_result == Communicate.SIGNAL_CONTROL_MOVE_POSITION:
							self.onSignalMoveToPosition(last_result)
									
						elif last_result == Communicate.SIGNAL_CONTROL_CREATE_GOMSIC:
							self.onSignalCreateGOMSic(last_result)
							
						elif last_result == Communicate.SIGNAL_CONTROL_FORCE_CALIBRATION:
							if self.onSignalForceCalibration(last_result):
								return True
						
						elif last_result == Communicate.SIGNAL_CONTROL_FORCE_TRITOP:
							if self.onSignalForcePhotogrammetry(last_result):
								return True
						
						elif last_result == Communicate.SIGNAL_CONTROL_MOVE_DECISION_AFTER_FAULT:
							pass # already handled
				except Exception as e:
					self.log.exception(str(e))
					return str(e)

			while True:
				res = handler()
				if isinstance(res, str):
					raise res
				if res is None:
					gom.script.sys.delay_script(time=0.2)
					continue
				return res

	def onSignalSerial(self, value):
		Globals.SETTINGS.InAsyncAbort = False
		self._userdata={}
		try:
			value = pickle.loads(value.value)
		except:
			value={'serial': value.get_value_as_string()}
			if Globals.DRC_EXTENSION is not None:
				value['drc'] = True
		self.dialog.inputSerial.value = value['serial']
		if Globals.DRC_EXTENSION is not None:
			if not value['drc'] and not Globals.SETTINGS.MultiRobot_Mode:
				Globals.DRC_EXTENSION.single_side_primary = True
				self.log.debug('DRC MAIN ONLY project')
			else:
				Globals.DRC_EXTENSION.single_side_primary = False
				Globals.DRC_EXTENSION.single_side_secondary = False
				self.log.debug('DRC project')
		self.open_template()
		
		if Globals.SETTINGS.CurrentTemplate is None:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.FAILED_OPEN_TEMPLATE, '',
													'Failed to load template ID:{}'.format(value['serial']))
			return
		if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.single_side_primary and not Globals.DRC_EXTENSION.single_side_secondary: # onSignalSerial2 get send before
			Globals.DRC_EXTENSION.onInlineSerialSlave(pickle.dumps(self.is_template_filter_unique()), True) # only open and init sensor

		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_TEMPLATE, str(1)))
		# reset project keywords
		existing_kws = gom.app.project.get ('project_keywords')
		existing_kws = [kw[5:] for kw in existing_kws]
		if 'KioskInline_PLC_RESULT_NOT_NEEDED' in existing_kws:
			gom.script.sys.set_project_keywords ( 
				keywords = {'KioskInline_PLC_RESULT_NOT_NEEDED': ''},
				keywords_description = {'KioskInline_PLC_RESULT_NOT_NEEDED': 'KioskInterface PLC Result Not Needed'} )
		if 'KioskInline_PLC_INFORMATION' in existing_kws:
			gom.script.sys.set_project_keywords ( 
				keywords = {'KioskInline_PLC_INFORMATION': ''},
				keywords_description = {'KioskInline_PLC_INFORMATION': 'KioskInterface PLC Information'} )
		self.sendAvailableSpecialPositions()

	def onSignalSerial2(self, value):
		Globals.SETTINGS.InAsyncAbort = False
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			self.dialog.inputSerial.value = value.get_value_as_string() # since its get called first keep the serial number
			slave_template, slave_cfg = self.is_template_filter_unique()
			Globals.DRC_EXTENSION.onInlineSerialSlave(pickle.dumps([slave_template,slave_cfg, value.get_value_as_string()]))
			Globals.DRC_EXTENSION.single_side_secondary = True
	
	def onSignalStart(self, value):
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			if Globals.DRC_EXTENSION.single_side_secondary:
				if not Globals.DRC_EXTENSION.single_side_primary: # due to MultiSensorSync a template needs to be open and the sensor initialized
					try:
						gom.app.project
					except:
						template, cfg = self.is_template_filter_unique()
						gom.script.sys.create_project_from_template ( 
							config_level = cfg,
							template_name = template )
						with Measure.TemporaryWarmupDisable(self.parent.eval.eval.Sensor) as warmup:
							self.parent.eval.eval.Sensor.check_for_reinitialize()
				Globals.DRC_EXTENSION.onInlineStartSingleSlave()
				if not Globals.DRC_EXTENSION.single_side_primary:
					return False
		return True
	
	def onSignalExit(self, value):
		return True
	
	def onSignalResultNotNeeded(self, value):
		try:
			gom.script.sys.set_project_keywords (
				keywords = {'KioskInline_PLC_RESULT_NOT_NEEDED': value.get_value_as_string()},
				keywords_description = {'KioskInline_PLC_RESULT_NOT_NEEDED': 'KioskInterface PLC Result Not Needed'} )
		except:
			pass
		if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.single_side_secondary:
			Globals.DRC_EXTENSION.onInlineResultNotNeeded(value.get_value_as_string())

	def onSignalAdditionalInformation(self, value):
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			Globals.DRC_EXTENSION.onInlinePrepareExecution(self)
		if Globals.SETTINGS.CurrentTemplate is None:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.FAILED_OPEN_TEMPLATE, '',
													'Failed to load template')
			return
		result = self.buildAdditionalResultInformation(value.get_value_as_string())
		Globals.SETTINGS.AlreadyExecutionPrepared=False
		self.parent.eval.eval.set_project_keywords(result)
		gom.script.sys.set_project_keywords (
			keywords = {'KioskInline_PLC_INFORMATION': value.get_value_as_string()},
			keywords_description = {'KioskInline_PLC_INFORMATION': 'KioskInterface PLC Information'} )

		self.parent.eval.eval.save_project()
		if not self.parent.eval.eval.Sensor.check_for_reinitialize():
			return
		self.parent.eval.eval.prepareTritop()
		Globals.SETTINGS.AlreadyExecutionPrepared = True
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			Globals.DRC_EXTENSION.waitForInlinePrepareExecution(self)

	def onSignalAdditionalInformationRaw(self, value): # can also occur when template is given without explicit prepare measurement
		try:
			value = pickle.loads(value.value)
		except:
			value = ['','','']
		if Globals.SETTINGS.CurrentTemplate is None:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.FAILED_OPEN_TEMPLATE, '',
													'Failed to load template')
			return
		gom.script.sys.set_project_keywords ( 
			keywords = {'KioskInline_PLC_INFORMATION_RAW1': value[0],
					'KioskInline_PLC_INFORMATION_RAW2': value[1],
					'KioskInline_PLC_INFORMATION_RAW3': value[2],
					'KioskInline_PLC_INFORMATION' : ''.join(value)},
			keywords_description = {'KioskInline_PLC_INFORMATION_RAW1': 'KioskInterface PLC Information Raw1',
								'KioskInline_PLC_INFORMATION_RAW2': 'KioskInterface PLC Information Raw2',
								'KioskInline_PLC_INFORMATION_RAW3': 'KioskInterface PLC Information Raw3',
								'KioskInline_PLC_INFORMATION': 'KioskInterface PLC Information'} )
		self._userdata = self.buildAdditionalResultInformation(''.join(value))
		

	def onSignalAdditionalInformationRaw2(self, value):
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			Globals.DRC_EXTENSION.onInlineAdditionalInfosSlave(value.value)

	def onSignalCloseTemplate(self, value):
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			Globals.DRC_EXTENSION.onInlineCloseTemplate(self)
		gom.script.sys.close_project()
		if Globals.DRC_EXTENSION is not None:
			Globals.DRC_EXTENSION.single_side_secondary = False
			Globals.DRC_EXTENSION.single_side_primary = False
		Globals.SETTINGS.CurrentTemplate = None
		Globals.SETTINGS.CurrentTemplateCfg = None
		Globals.SETTINGS.AlreadyExecutionPrepared = False
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_IDLE, str(1) ) )
	
	def onSignalDeInitSensor(self, value):
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			Globals.DRC_EXTENSION.onInlineDeInit(self)
		self.parent.eval.eval.Sensor.deinitialize()
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_DEINIT_SENSOR, str(1) ) )
						
	def onSignalMoveHome(self, value):
		if not gom.app.project.is_part_project:
			active_mlist = Utils.real_measurement_series( filter='is_active==True' )
		else:
			active_mlist = gom.app.project.measurement_paths.filter('is_active==True')
		if not len(active_mlist):
			Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MOVE_HOME, str(1) ) )
		else:
			if not gom.app.project.is_part_project:
				pos = active_mlist[0].measurements.filter( 'type=="home_position"' )[-1]
			else:
				pos = active_mlist[0].path_positions.filter( 'type=="home_position"' )[-1]
			if self.parent.eval.eval.move_to_position(pos):
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MOVE_HOME, str(1) ) )
				self._currentSpecialPosition = []
			else:
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MOVE_HOME, str(0) ) )
	
	def onSignalMoveToPosition(self, value):
		try:
			value = pickle.loads(value.value)
			position = value['special']
			subposition = value['sub']
		except Exception as e:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MOVE_ERROR, '', 'Failed to read special position signal')
			return
		measurement = None
		try:
			mlist = None
			for ml in Utils.real_measurement_series( filter='type=="atos_measurement_series"' ):
				mlname = ml.name.lower()
				if mlname == 'pos{}'.format(position) or mlname.startswith('pos{} '.format(position)):
					mlist = ml
					break
			if not gom.app.project.is_part_project:
				intermediate = mlist.measurements.filter('type == "intermediate_position"')
			else:
				intermediate = mlist.measurement_path.path_positions.filter( 'type == "intermediate_position"' )

			if subposition == 0 and len(intermediate) == 1:
				measurement = intermediate[0]
			else:
				if subposition == 0:
					for m in intermediate:
						mname = m.name.lower()
						if mname == 'pos{}'.format(position) or mname.startswith('pos{} '.format(position)):
							measurement = m
				else:
					for m in intermediate:
						mname = m.name.lower()
						if mname == 'sub{}'.format(subposition) or mname.startswith('sub{} '.format(subposition)):
							measurement = m
		except:
			pass
		if measurement is not None:
			if len(self._currentSpecialPosition):
				if self._currentSpecialPosition[0] != position or self._currentSpecialPosition[1] > subposition:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MOVE_ERROR, '', 'Invalid order of special position signals')
					Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MOVE_POSITION, str(0) ) )
					return
			
			if self.parent.eval.eval.move_to_position(measurement):
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MOVE_POSITION, str(1) ) )
				self._currentSpecialPosition = [position, subposition]
			else:
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MOVE_POSITION, str(0) ) )
		else:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MOVE_ERROR, '', 'Position not defined')
			Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MOVE_POSITION, str(0) ) )
			
	def sendAvailableSpecialPositions(self):
		subs={}
		for ml in Utils.real_measurement_series( filter='type=="atos_measurement_series"' ):
			try:
				mlname = ml.name.lower()
				if mlname.startswith('pos'):
					pos = ml.name[3:].split(' ')[0]
					pos = int(pos)
					if not gom.app.project.is_part_project:
						intermediate = ml.measurements.filter('type == "intermediate_position"')
					else:
						intermediate = ml.measurement_path.path_positions.filter( 'type == "intermediate_position"' )
					if not len(intermediate):
						continue
					if len(intermediate) == 1:
						subs[pos]=0
						continue
					subsub=-1
					for m in intermediate:
						mname = m.name.lower()
						if mname.startswith('sub'):
							spos = m.name[3:].split(' ')[0]
							spos = int(spos)
							if spos > subsub:
								subsub=spos
						elif mname.startswith('pos'):
							spos = m.name[3:].split(' ')[0]
							spos = int(spos)
							if spos == pos:
								subsub=0
								break
					if subsub < 0:
						continue
					subs[pos]=subsub
			except Exception as e:
				pass
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_AVAILABLE_SUBPOSITIONS, pickle.dumps(subs) ) )
				
				
	def onSignalCreateGOMSic(self, value):
		if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
			Globals.DRC_EXTENSION.onGOMSic()
		Globals.DIALOGS.createGOMSic(Globals.SETTINGS.SavePath)
		
	def onSignalForceCalibration(self, value):
		self.parent.eval.eval.setExecutionMode(Evaluate.ExecutionMode.ForceCalibration)
		return True
	
	def onSignalForcePhotogrammetry(self, value):
		if Globals.SETTINGS.AlreadyExecutionPrepared:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.UNKNOWN_ERROR, '', 'Workflow ERROR, got Force Tritop but prepareProject already done!')
			return False
		if Globals.SETTINGS.PhotogrammetryOnlyIfRequired:
			Globals.SETTINGS.IsPhotogrammetryNeeded = True
		self.parent.eval.eval.setExecutionMode(Evaluate.ExecutionMode.ForceTritop)
		return True

	def async_process_signals( self ):
		'''
		process async signals of client instance
		'''
		for last_result in Globals.ASYNC_SERVER.pop_results():
			if last_result == Communicate.SIGNAL_PROCESS:
				self.log.info( str( last_result.value ) )
			elif last_result == Communicate.SIGNAL_RESULT:
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_RESULT, last_result.value ) )
				self.log.info( str( last_result.value ) )
			
	@property
	def Result(self):
		res = {'user':'Inline', 'serial': self.dialog.inputSerial.value}
		res = {**res, **self._userdata}
		return res
	
	def buildAdditionalResultInformation(self, infos):
		result = self.Result
		infos=infos.split(';')
		if not len(infos):
			return result
		if not len(infos[-1].strip()):
			del infos[-1]
		for i in range(len(infos)):
			if i < len(Globals.ADDITIONAL_PROJECTKEYWORDS):
				result[Globals.ADDITIONAL_PROJECTKEYWORDS[i][0]] = infos[i].strip()
		return result
	
	def _clientProcessCheck(self, value):
		'''
		async call to check for client pkts and pass them to control instance if needed
		in addition allow exit signal to abort the measurement process
		'''
		if Globals.ASYNC_SERVER is not None: # may not yet exist on first call(s)
			while Globals.ASYNC_SERVER.process_signals(timeout = 0):
				pass
			self.async_process_signals()
		
		if Globals.CONTROL_INSTANCE is None:
			return

		while Globals.CONTROL_INSTANCE.check_for_activity(timeout = 0):
			pass
		try:
			self.parent.eval.eval.position_information.updated_position_information()
		except: # can fail during startup, due to initialization order
			pass

		for last_result in Globals.CONTROL_INSTANCE.LastAsyncResults:
			self._delayed_pkts.append(last_result)
			if last_result == Communicate.SIGNAL_CONTROL_EXIT:
				if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
					Globals.DRC_EXTENSION.onAbort() # dont exit Slave Instance
				if Globals.SETTINGS.AllowAsyncAbort:
					self.log.debug('triggering async abort')
					gom.app.abort = True
				else:
					Globals.SETTINGS.InAsyncAbort = True
				Globals.SETTINGS.ShouldExit = True
			elif last_result == Communicate.SIGNAL_CONTROL_ABORT:
				if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
					Globals.DRC_EXTENSION.onAbort()
				if Globals.SETTINGS.AllowAsyncAbort:
					self.log.debug('triggering async abort')
					gom.app.abort = True
				else:
					Globals.SETTINGS.InAsyncAbort = True
			elif last_result == Communicate.SIGNAL_CONTROL_MOVE_DECISION_AFTER_FAULT:
				if not Globals.SETTINGS.AllowAsyncAbort:
					if Globals.DRC_EXTENSION is None:
						self.log.error("Got out of sync signal move decision")
						continue
				decision = int(last_result.value)
				if Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_PRIMARY_INST:
					Globals.DRC_EXTENSION.onMoveDecision(decision)
				if Globals.SETTINGS.AllowAsyncAbort: # master also needs the signal
					Globals.SETTINGS.MoveDecisionAfterFaultState = decision
					Globals.SETTINGS.InAsyncAbort = False
					self.log.debug('triggering async abort')
					gom.app.abort = True
				

class Eval( Utils.GenericLogClass ):
	'''
	This class manages the evaluation step as mentioned in the docstring of workflow.
	'''
	process = None
	choosed = None
	eval = None
	processmsg = None
	step = 1
	maxstep = 1
	def __init__( self, logger ):
		'''
		Initialize function for logging and child classes
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.eval = Evaluate.Evaluate( self.baselog, self )
		Globals.DIALOGS.localize_progessdialog()
		if not Globals.SETTINGS.BatchScan:
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'labelMultipart' ):
				Globals.DIALOGS.PROGRESSDIALOG.labelMultipart.visible = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'progressbarMultipart' ):
				Globals.DIALOGS.PROGRESSDIALOG.progressbarMultipart.visible = False

		if Globals.SETTINGS.LogoImage == "":
			if Globals.DIALOGS.has_widget(
					Globals.DIALOGS.MEASURINGSETUP_DIALOG, 'image' ):
				Globals.DIALOGS.MEASURINGSETUP_DIALOG.image.enabled = False
				Globals.DIALOGS.MEASURINGSETUP_DIALOG.image.visible = False

	def execute( self, resultchoosen ):
		'''
		This function displays the dialog and starts the evaluation.
		'''
		self.choosed = resultchoosen
		self.process_image( Globals.SETTINGS.InitializeImageBinary )
		self.open_progressdialog()  # open dialog
		Communicate.IOExtension.store_active_devices()
		return self.evaluate()

	def open_progressdialog( self ):
		'''
		DEPRECATED: show dialog
		'''
		pass
	def close_progressdialog( self ):
		'''
		DEPRECATED: close the dialog
		'''
		pass

	def show_measuringsetup_dialog( self, active_ms_series, first_ms = False ):
		'''
		show confirm dialog for switching measuring setup
		returns False on ok pressed, else False
		'''
		self.close_progressdialog()
		if not Globals.DIALOGS.showMeasuringSetupDialog( active_ms_series, first_ms ):
			self.log.info( 'user denied measuringsetup switch: {}'.format( active_ms_series.get( 'name' ) ) )
			return False
		self.open_progressdialog()
		return True

	@property
	def Processbar_step( self ):
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'progressbar' ):
			return Globals.DIALOGS.PROGRESSDIALOG.progressbar.step
		return 0
	@property
	def Processbar_maxstep( self ):
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'progressbar' ):
			return Globals.DIALOGS.PROGRESSDIALOG.progressbar.parts
		return 0
	@property
	def Process_msg_step( self ):
		return self.step
	@property
	def Process_msg_maxstep( self ):
		return self.maxstep
	@property
	def Process_get_msg_detail( self ):
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'labelProgress2' ):
			return Globals.DIALOGS.PROGRESSDIALOG.labelProgress2.text
		return ''

	@property
	def Process_multipart_bar( self ):
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'progressbarMultipart' ):
			return Globals.DIALOGS.PROGRESSDIALOG.progressbarMultipart
		return None


	def process_msg( self, msg = None, step = None, maxstep = None ):
		'''
		This function modifies the progress bar status message of the progress dialog Globals.PROGRESSDIALOG.

		Arguments:
		msg - A string which is displayed as status message in the Progress dialog. It may contain the substring {0} which will be replaced
		by the content of the step argument or {1} which will be replaced by the argument maxstep. For instance "This is step {0} of {1} steps" would be a valid string.
		step - The current evaluation step.
		maxstep - The number of evalutation steps.
		'''
		if msg is not None:
			self.processmsg = msg
		if step is not None:
			self.step = step
		if maxstep is not None:
			self.maxstep = maxstep
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'labelProgress' ):
			Globals.DIALOGS.PROGRESSDIALOG.labelProgress.text = self.processmsg.format( self.step, self.maxstep )

	def process_msg_detail( self, msg ):
		'''
		This function modifies the detailed progress bar status message of the progress dialog Globals.PROGRESSDIALOG.

		Arguments:
			msg = A string containing the message.
		'''
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'labelProgress2' ):
			Globals.DIALOGS.PROGRESSDIALOG.labelProgress2.text = msg
	def processbar_step( self, step = None ):
		'''
		set/step the process bar
		'''
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'progressbar' ):
			if step is not None:
				Globals.DIALOGS.PROGRESSDIALOG.progressbar.step = step
			else:
				Globals.DIALOGS.PROGRESSDIALOG.progressbar.step += 1

	def processbar_max_steps( self, maxsteps = None ):
		'''
		set/step the maximum steps of the process bar
		'''
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'progressbar' ):
			if maxsteps is not None:
				Globals.DIALOGS.PROGRESSDIALOG.progressbar.parts = maxsteps
			else:
				Globals.DIALOGS.PROGRESSDIALOG.progressbar.parts += 1

	def process_image( self, img ):
		'''
		set the image of the process dialog
		'''
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.PROGRESSDIALOG, 'processimage' ):
			Globals.DIALOGS.PROGRESSDIALOG.processimage.data = img

	def evaluate( self ):
		'''
		This function starts the evaluation

		Returns:
		True  - if successful, i.e. measurement went right, no deviations out of their tolerance
		False - otherwise
		'''
		if Globals.DRC_EXTENSION is not None:
			Globals.DRC_EXTENSION.start_evaluation(self)
		self.process_msg()
		result = None
		try:
			result = self.eval.perform( self.choosed )
		except Globals.EXIT_EXCEPTIONS:
			raise
		finally:
			self.close_progressdialog()
		return result


class Confirm( Utils.GenericLogClass ):
	'''
	This class manages the confirmation step as mentioned in the docstring of Workflow.
	'''
	def __init__( self, logger ):
		'''
		Constructor function to init logging and child class
		'''
		Utils.GenericLogClass.__init__( self, logger )
		Globals.DIALOGS.CONFIRMDIALOG.handler = self.dialog_event_handler
		Globals.DIALOGS.localize_confirmdialog()
		if (Globals.SETTINGS.LogoImage == ""
				and Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'image' )):
			Globals.DIALOGS.CONFIRMDIALOG.image.visible = False

	def inline_result( self, result, partname ):
		'''
		Template function for building the result message for inline kiosk evaluation
		You can use the partname to extend the serial number information
		or add it in the add_plc_info field.
		'''
		return result

	def inline_send_result( self, result, part_id=None, partname=None, overall_result=False ):
		'''
		Builds the result signal based on the result dictionary and sends it
		'''
		if part_id is None:
			try:
				part_id = gom.app.project.get ( 'user_part_nr' )
			except:
				part_id = 'Unknown'
		add_info = ''
		result_not_needed = 0
		try:
			add_info = [gom.app.project.get ( 'user_KioskInline_PLC_INFORMATION_RAW1' ),
			gom.app.project.get ( 'user_KioskInline_PLC_INFORMATION_RAW2' ),
			gom.app.project.get ( 'user_KioskInline_PLC_INFORMATION_RAW3' )]
		except:
			add_info = ['','','']
		try:
			result_not_needed = int(gom.app.project.get( 'user_KioskInline_PLC_RESULT_NOT_NEEDED' ))
		except:
			result_not_needed = 0

		if add_info[2] == '':
			add_info[2] = Evaluate.EvaluationAnalysis.getRelativePDFPath( overall_result, part_id, partname )

		result['serial'] = part_id
		result['add_plc_info'] = add_info
		result['result_not_needed'] = result_not_needed
		if partname is not None:
			result = self.inline_result( result, partname )

		self.log.info( 'automatic evaluation result {}'.format( result ) )
		msg = pickle.dumps(result)
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_RESULT, msg ) )


	def execute( self ):
		'''
		start the handler
		'''
		# no confirm dialog on drc slave side
		if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActive():
			return True
		if Globals.SETTINGS.Inline:
			result = self.parent.eval.eval.analysis.perform_automatic_result_check()
			overall_result = {}
			overall_result[None] = result
			project_file = gom.app.project.get( 'project_file' )
			gom.script.sys.set_project_keywords ( 
				keywords = {'result_all_checked_elements': len( result['all'] ),
							'result_all_uncomputed_elements': len( result['uncomputed'] ),
							'result_all_out_of_tolerance': len( result['out_of_tol'] ),
							'result_all_out_of_warning_tolerance': len( result['out_of_tol_warning'] ),
							'result_all_out_of_qstop_tolerance': len( result['out_of_tol_qstop'] ),							
							'result':result['result'],
							'result_additional':result['additional']},
				keywords_description = {'result_all_checked_elements': 'Count of all checked elements',
								'result_all_uncomputed_elements': 'Count of all uncomputed elements',
								'result_all_out_of_tolerance': 'Count of all out of tolerance elements',
								'result_all_out_of_warning_tolerance': 'Count of all out of warning tolerance elements',
								'result_all_out_of_qstop_tolerance': 'Count of all out of Q-Stop tolerance elements',
								'result':'Result',
								'result_additional':'Additional Result Information'} )

			if Utils.multi_part_evaluation_status():
				reports_per_part = Evaluate.EvaluationAnalysis.scan_report_for_parts( Evaluate.EvaluationAnalysis.scan_parts )
				for partname in reports_per_part.keys():
					part = gom.app.project.parts[partname]
					shadow_kws = Evaluate.EvaluationAnalysis.activate_part_keywords( part )
					gom.script.sys.recalculate_elements (
						elements=gom.ElementSelection( reports_per_part[partname] ) )
					result = self.parent.eval.eval.analysis.perform_automatic_result_check( reports_per_part[partname] )
					overall_result[partname] = result
					Evaluate.EvaluationAnalysis.restore_keywords( shadow_kws )

			result = overall_result
			self.after_confirmation( result[None]['result'] )

			if list( result.keys() ) == [None]:
				self.inline_send_result( result[None] )
			else:
				for partname in result.keys():
					if partname is None:
						continue

					try:
						part_id = gom.app.project.parts[partname].nominal.get( 'user_part_nr' )
					except:
						# Fallback: use overall project part_nr keyword and partname as additional info
						try:
							part_id = gom.app.project.get ( 'user_part_nr' )
						except:
							part_id = 'Unknown'
					res_partname = partname
					self.inline_send_result( result[partname], part_id=part_id, partname=res_partname,
						overall_result=result[None]['result'] )

			self.cleanup_project( project_file )
			return True

		gom.script.sys.set_kiosk_status_bar(status=4)
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
			Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = True
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
			Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = True
		# Prev/Next buttons are removed in KioskInterface
		# Code is left for compatibility with patched confirm dialogs
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonPrev' ):
			Globals.DIALOGS.CONFIRMDIALOG.buttonPrev.enabled = True
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonNext' ):
			Globals.DIALOGS.CONFIRMDIALOG.buttonNext.enabled = True

		try:
			gom.script.sys.switch_to_report_workspace()
			gom.script.explorer.apply_selection( selection=gom.app.project.reports[0] )
		except:
			pass

		result = False
		try:
			result = gom.script.sys.show_user_defined_dialog( dialog=Globals.DIALOGS.CONFIRMDIALOG )
		except Globals.EXIT_EXCEPTIONS:
			raise
		except:
			pass

		return result

	def dialog_event_handler ( self, widget ):
		'''
		dialog handler function
		'''
		# Prev/Next buttons are removed in KioskInterface
		# Code is left for compatibility with patched confirm dialogs
		if isinstance( widget, gom.Widget ) and widget.name == 'buttonPrev':
			try:
				gom.script.report.report_page_up ()
			except Globals.EXIT_EXCEPTIONS:
				raise
			except:
				pass
		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonNext':
			try:
				gom.script.report.report_page_down ()
			except Globals.EXIT_EXCEPTIONS:
				raise
			except:
				pass

		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonApprove':
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonPrev' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonPrev.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonNext' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonNext.enabled = False
			self.log.info( 'user approved part' )
			project_file = gom.app.project.get( 'project_file' )
			self.after_confirmation( True )
			self.cleanup_project( project_file )
			gom.script.sys.close_user_defined_dialog( dialog = Globals.DIALOGS.CONFIRMDIALOG, result = widget )
		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonDisapprove':
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonPrev' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonPrev.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonNext' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonNext.enabled = False
			self.log.info( 'user disapproved part' )
			project_file = gom.app.project.get( 'project_file' )
			self.after_confirmation( False )
			self.cleanup_project( project_file )
			gom.script.sys.close_user_defined_dialog( dialog = Globals.DIALOGS.CONFIRMDIALOG, result = widget )

	def after_confirmation( self, user_approved_measurement ):
		'''
		This function is called directly after the Approve/Disapprove button is clicked in the confirmation dialog. It stores the
		current project to a directory. You may want to patch this function for example to export measurement
		information to your needs.

		Arguments:
		userApprovedMeasurement - True if user approved measurement data, otherwise False
		'''
		try:
			Evaluate.EvaluationAnalysis.export_results( user_approved_measurement )
		except Exception as error:
			self.log.exception( 'Failed to export results: {}'.format( error ) )

	def cleanup_project( self, project_file ):
		'''
		Called after confirmation to close and remove the project
		'''
		file_name = os.path.basename( project_file )
		gom.script.sys.close_project()
		if ( os.path.exists( os.path.join( Globals.SETTINGS.SavePath, file_name ) ) ):
			os.unlink( os.path.join( Globals.SETTINGS.SavePath, file_name ) )

# main function
def start_workflow( mseries=None ):
	'''
	This function initializes the variables in Globals and starts the workflow
	'''
	# define globals
	Globals.LOCALIZATION = Messages.Localization()
	Globals.SETTINGS = Utils.Settings( should_create=mseries is None )

	# Parameter "mseries" triggers Kiosk oneshot mode
	if mseries is not None:
		if not Globals.SETTINGS.settings_file_found():
			Globals.DIALOGS.show_simple_errormsg('Kiosk Interface not set up',
				'You have to set-up the Kiosk Interface before you can use it for measuring.\n'
				'Use "Scripting > Script Choice > KioskInterface > Setup > Setup" for basic setup.')
			return

		mseries = [(m if isinstance(m, str) else m.name) for m in mseries]
		# Store mseries in Globals
		Globals.FEATURE_SET.ONESHOT_MSERIES = mseries
		# Turning off DRC mode avoids loading DRC extension
		# and setting DRC_PRIMARY_INST below
		Globals.SETTINGS.DoubleRobotCell_Mode = False

	if Globals.SETTINGS.MultiRobot_Mode:
		Globals.FEATURE_SET.DRC_SECONDARY_INST = True
		if len( Globals.SETTINGS.MultiRobot_ClientSavePath) == 1:
			Globals.SETTINGS.SavePath = Globals.SETTINGS.MultiRobot_ClientSavePath[0]
		else:
			Globals.SETTINGS.SavePath = Globals.SETTINGS.MultiRobot_ClientSavePath[Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID]
	elif Globals.FEATURE_SET.DRC_SECONDARY_INST:
		Globals.SETTINGS.SavePath = Globals.SETTINGS.DoubleRobot_ClientSavePath
		Globals.SETTINGS.DoubleRobot_TransferPath = Globals.SETTINGS.DoubleRobot_ClientTransferPath
	elif Globals.SETTINGS.DoubleRobotCell_Mode:
		Globals.FEATURE_SET.DRC_PRIMARY_INST = True

	Globals.SETTINGS.check()

	Globals.PERSISTENTSETTINGS = PersistentSettings.PersistentSettings( Globals.SETTINGS.SavePath )

	workflow = WorkFlow()
	try:
		workflow.execute()
	except ( SystemExit, gom.BreakError ):
		workflow.log.debug( 'Forced Exit' )
	except Exception as error:
		workflow.log.exception( 'Unhandled Exception: {}'.format( error ) )
		Globals.DIALOGS.show_errormsg( 
			Globals.LOCALIZATION.msg_general_failure_title,
			Globals.LOCALIZATION.msg_global_failure_text + '\n'.join(error.args),
			Globals.SETTINGS.SavePath, False )
	finally:
		workflow.exit_handler()
