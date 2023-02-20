# -*- coding: utf-8 -*-
# Script: Multirobot Evaluation Client Communication Class
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

import ctypes
import fnmatch, itertools, os, pickle, sys, time
import psutil
import asyncore, socket

from . import Communicate
from ..Misc import LogClass, Utils, Globals
from .. import Evaluate
from ..Measuring import Measure, Verification


# Windows socket error code
WSAECONNREFUSED = 10061


def getExternalSavePath(id):
	if len( Globals.SETTINGS.MultiRobot_TransferPath) == 1:
		return Globals.SETTINGS.MultiRobot_TransferPath[0]
	return Globals.SETTINGS.MultiRobot_TransferPath[id]


class MultiClient( asyncore.dispatcher, Utils.GenericLogClass ):
	'''
	async analyse client class
	'''
	Dialog = None  # needed for EvaluationAnalysis
	analysis = None
	fileloghandler = None

	def __init__( self, host='localhost', port=8081, control_param=None, sctmap={},
				log_name='eval_client', use_localization=True ):
		'''
		initialize function, creates logfile and connect socket
		'''
		# init logging
		Utils.GenericLogClass.__init__( self, LogClass.Logger() )
		self.baselog.log.setLevel( Globals.SETTINGS.LoggingLevel )
		log_name = '{}_{}_{}'.format( log_name, control_param, gom.getpid() )
		self.set_logging_filename(log_name, Globals.SETTINGS.TimeFormatLogging)
		self.set_logging_format(Globals.SETTINGS.LoggingFormat)
		self.create_fileloghandler()
		self.consolelog = self.baselog.create_console_streamhandler( strformat = Globals.SETTINGS.LoggingFormat )
		Globals.registerGlobalLogger( self.baselog )

		# Load Localization
		if use_localization:
			Utils.import_localization( Globals.SETTINGS.Language, self.log )

		self.globaltimer_active = False
		Utils.GlobalTimer.registerInstance( self.baselog )
		# default time slice is 1000 (= 1.0s)
		Globals.TIMER.registerHandler( self.timer_process_signals )

		self.log.debug('MultiClient starting')

		if host == Globals.SETTINGS.HostAddress:
			self.log.info( 'Local host address {}/{}'.format( host, port ) )
			self.remote_eval = False
		elif host == Globals.SETTINGS.MultiRobot_RemoteEvalHostAddress:
			self.log.error( 'Remote host address {}/{}'.format( host, port ) )
			self.remote_eval = True
		else:
			self.log.error( 'Unknown host address {}/{}'.format( host, port ) )
			sys.exit( 0 )
		self.host = host
		self.port = port
		self.sctmap = sctmap
		asyncore.dispatcher.__init__( self, map = sctmap )
		self.create_socket( socket.AF_INET, socket.SOCK_STREAM )
		self.connect( ( host, port ) )
		self.handler = None

		self.tritop = Measure.MeasureTritop( self.baselog, self )
		self.analysis = Evaluate.EvaluationAnalysis( self.baselog, self )
		self.checks = Verification.MeasureChecks( self.baselog, self )

		self.control_param = control_param
		self.log.debug( 'control_param {}'.format( self.control_param ) )

		self.measure_clients = []
		for i in range( len( Globals.SETTINGS.MultiRobot_TransferPath ) ):
			self.measure_clients.append( MeasureClient( i, self.baselog ) )

		self.reset_cycle()
		self.idle_state = False

#		self.debugTiming = 0

		self.refxml_loaded = False

	def isForceTritopActive(self):
		return False

	def handle_connect( self ):
		'''
		called during connection creates the communication handler and sends handshake signal
		'''
		self.log.info( 'connected' )
		self.handler = Communicate.ChatHandlerClient( self.baselog, self.socket, self.sctmap, self )
		self.handler.handshaked = False
		ownpid = os.getpid()
		self.handler.push( Communicate.Signal( Communicate.SIGNAL_HANDSHAKE, str( ownpid ) ).encode() )
		self.log.debug( 'Connected and Handshake sent {}'.format( ownpid ) )

	def log_info( self, message, logtype = 'info' ):
		'''
		log misc messages from the socket framework
		'''
		self.log.debug( message )

	def handle_close( self ):
		'''
		called during close event
		'''
		self.log.debug( 'Closing' )
		self.close()

#	def handle_expt_event(self):
#		# handle_expt_event() is called if there might be an error on the
#		# socket, or if there is OOB data
#		# check for the error condition first
#		err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
#		self.log.debug('getsockopt returned {}'.format(err))
#		if err == WSAECONNREFUSED:
#			# expected fail on startup
#			return
#
#		if err != 0:
#			# we can get here when select.select() says that there is an
#			# exceptional condition on the socket
#			# since there is an error, we'll go ahead and close the socket
#			# like we would in a subclassed handle_read() that received no
#			# data
#			self.handle_close()
#		else:
#			self.handle_expt()

	def wait_till_connected( self ):
		'''
		endless loop till a successfull connection was established (with handshake pkt)
		'''
		while True:
			gom.script.sys.delay_script( time=0.2 )
			self.check_for_activity( 10, waitmode=True )
			if self.handler is not None and self.handler.handshaked:
				self.log.debug( 'Handshake successfull' )
				return True


	def timer_process_signals( self, value ):
		if not self.globaltimer_active:
			return

		while self.check_for_activity():  # get all signals
			pass

	def signal_timeslice( self, timeout=0.1 ):
		'''
		Timeslice for asyncore for signal processing
		'''
		asyncore.loop( timeout=timeout, map=self.sctmap, count=1 )
#		res = False
#		if self.handler is not None:
#			res = self.handler.process_signals()

	def check_for_activity( self, timeout=0.1, waitmode=False ):
		'''
		checks for network packets and precesses them
		returns True if any packet was received
		'''
		asyncore.loop( timeout=timeout, map=self.sctmap, count=1 )
		res = False
		if self.handler is not None:
			res = self.handler.process_signals()

		if not self.connecting and not self.connected and waitmode:
			self.log.debug( 'Connect timed out - new socket and reconnect' )
			asyncore.dispatcher.__init__( self, map = self.sctmap )
			self.create_socket( socket.AF_INET, socket.SOCK_STREAM )
			self.connect( ( self.host, self.port ) )
			return False

		if not self.connected and not waitmode:
			try:
				print('close', waitmode)
				self.close()
			except Globals.EXIT_EXCEPTIONS:
				raise
			except:
				pass
			asyncore.dispatcher.__init__( self, map = self.sctmap )
			self.create_socket( socket.AF_INET, socket.SOCK_STREAM )
			self.connect( ( self.host, self.port ) )
			self.log.debug( 'not connected' )

		return res

# TODO Needed for teach mode?
#	def on_template( self, signal ):
#		success = False
#		try:
#			template = None
#			template_cfg = None
#			if signal == Communicate.SIGNAL_OPEN:
#				#serial=''
#				try:
#					value = pickle.loads( signal.value )
#					template = value[0]
#					template_cfg = value[1]
#					#if len(value) > 2:
#					#	serial = value[2]
#				except:
#					#template = signal.get_value_as_string()
#					return # fail
#
#				self.log.debug('open {}/{}'.format( template, template_cfg ) )
#
#			if template is None or template_cfg is None:
#				gom.script.sys.close_project ()
#				Globals.SETTINGS.CurrentTemplate = None
#				Globals.SETTINGS.CurrentTemplateCfg = None
#				success = True
#			else:
#				if (Globals.SETTINGS.CurrentTemplate == template
#					and Globals.SETTINGS.CurrentTemplateCfg == template_cfg):
#					# already open
#					success = True
#					return
#
#				template = gom.script.sys.create_project_from_template (
#					config_level = template_cfg,
#					template_name = template )
#				Globals.SETTINGS.CurrentTemplate = template
#				Globals.SETTINGS.CurrentTemplateCfg = template_cfg
#				success = True
#		finally:
#			if success:
#				self.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key ) ) )
#			else:
#				self.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE, str( signal.key ) ) )

	def open_template( self, template, template_cfg ):
		try:
#			if (Globals.SETTINGS.CurrentTemplate == template
#				and Globals.SETTINGS.CurrentTemplateCfg == template_cfg):
#				# already open
#				self.log.info( 'Template {}/{} already open'.format( template_cfg, template ) )
#				return True

			gom.script.sys.close_project()

			self.log.info( 'Open template {}/{}'.format( template_cfg, template ) )
			opened_template = gom.script.sys.create_project_from_template (
				config_level = template_cfg,
				template_name = template )
			Globals.SETTINGS.CurrentTemplate = template
			Globals.SETTINGS.CurrentTemplateCfg = template_cfg
			return True
		except Exception as e:
			msg = 'failed to open template {}/{}:\n{}'.format( template_cfg, template, str( e ) )
			self.log.error( msg )
			self.send_failure( msg )
			return False

# TODO probably not used
	def clean_project( self ):
		pass

	def import_photogrammetry( self, refxml ):
		self.log.info( 'import photogrammetry from {}'.format( refxml ) )
		done = False
		try:
			tritop=list( gom.app.project.measurement_series.filter( 'type=="photogrammetry_measurement_series"' ) )
			master_series = tritop[0]
			for ms in tritop:
				if ms.get( 'reference_points_master_series' ) is None:
					master_series = ms
					break
			done = self.tritop.import_photogrammetry( master_series, forced_refxml=refxml )
		except Exception as e:
			msg = 'failed to import photogrammetry from {}\n{}'.format( refxml, str( e ) )
			self.log.exception( msg )
			self.send_failure( 'failed to import photogrammetry from {}\n{}'.format( refxml, str( e ) ) )
			return False

		if done:
			return self.recalc_initial_alignments()
		else:
			self.send_failure( 'failed to import photogrammetry from {}'.format( refxml ) )
			return False

	def recalc_initial_alignments(self):
		self.log.debug( 'Recalc initial alignments' )
		# recalculation of initial alignment
		initial_alignment = [a for a in gom.app.project.alignments
			if not a.get( 'alignment_is_original_alignment' ) and a.get( 'alignment_is_initial' )]
		for alignment in initial_alignment:
			try:
				gom.script.sys.recalculate_alignment( alignment=alignment )
			except Globals.EXIT_EXCEPTIONS:
				raise
			except RuntimeError as e:
				msg = 'failed to recalculate alignment {} {}'.format( alignment.name, e )
				self.log.error( msg )
				self.send_failure( msg )
				return False

		return True

	def set_initial_alignments(self):
		self.log.debug( 'Activate initial alignments' )
		initial_alignments = [a for a in gom.app.project.alignments
			if not a.get( 'alignment_is_original_alignment' ) and a.get( 'alignment_is_initial' )]
		for align in initial_alignments:
			gom.script.manage_alignment.set_alignment_active( cad_alignment=align )


###############################################################################################
# copied from Evaluate.Evaluate
# - set_project_keywords optimized for inline
# - save_project uses INDI SYNC timestamp and MEASPLAN, simplified

	def set_project_keywords( self, start_dialog_input ):
		'''
		This function extracts the keywords from the user input requested in the StartUp Dialog and sets them in the project.
		It also sets the current time as a project keyword.

		Arguments:
		start_dialog_input - the dictionary obtained from StartUp.Result, that means it´s the dictionary containing the user input from
		the StartUp dialog.
		'''
		existing_kws = gom.app.project.get ('project_keywords')
		existing_kws = [kw[5:] for kw in existing_kws]

		key_val = {}
		key_val_desc = {}
		key_val_desc_param2 = {}

		for key, val, desc in [
			('inspector', start_dialog_input.get( 'user', '' ),
			Globals.LOCALIZATION.keyword_description_user),
			('part_nr', start_dialog_input.get( 'serial', '' ),
			Globals.LOCALIZATION.keyword_description_serial),
			('fixture_nr', start_dialog_input.get( 'fixture', '' ),
			Globals.LOCALIZATION.keyword_description_fixture),
			('date', time.strftime( Globals.SETTINGS.TimeFormatProjectKeyword ),
			Globals.LOCALIZATION.keyword_description_date)
			]:
			if key in existing_kws:
				# only set value
				key_val[key] = val
			else:
				# create new keyword including the description
				key_val_desc[key] = val
				key_val_desc_param2[key] = desc

		# set additional project keywords
		for (key, desc, _, _, *_) in Globals.ADDITIONAL_PROJECTKEYWORDS:
			if key is None:
				continue
			val = start_dialog_input.get( key, '' )
			if key in existing_kws:
				# only set value
				key_val[key] = val
			else:
				# create new keyword including the description
				key_val_desc[key] = val
				key_val_desc_param2[key] = desc

		if len(key_val.keys()):
			gom.script.sys.set_project_keywords (
				keywords = key_val )
		if len(key_val_desc.keys()):
			gom.script.sys.set_project_keywords (
				keywords = key_val_desc,
				keywords_description = key_val_desc_param2 )

		if '__parts__' in start_dialog_input:
			# mapping info - user/fixture/date are never per part (I hope)
			map = {'serial': ('part_nr', Globals.LOCALIZATION.keyword_description_serial)}
			for (key, desc, _, _, *_) in Globals.ADDITIONAL_PERPARTKEYWORDS:
				map[key] = (key, desc)
			# map res structure to keyword info and set keywords on parts
			for (part, items) in start_dialog_input['__parts__'].items():
				kw_values = [(map[i][0], v, map[i][1]) for (i, v) in items.items()]
				self.set_part_keywords( part, kw_values )

	def set_part_keywords( self, partname, kw_values ):
		part = gom.app.project.parts[partname]
		existing_kws = part.nominal.get( 'element_keywords' )
		existing_kws = [kw[5:] for kw in existing_kws]

		for kw, val, desc in kw_values:
			if kw in existing_kws:
				gom.script.cad.edit_element_keywords(
					elements=[part.nominal],
					set_value={kw: val})
			else:
				gom.script.cad.edit_element_keywords(
					add_keys=[kw],
					description={kw: desc},
					elements=[part.nominal],
					set_value={kw: val} )

	def save_project( self ):
		'''
		Saves the project to the directory specified by SavePath in the config.
		'''
#		currtime = time.strftime( Globals.SETTINGS.TimeFormatProject )
		currtime = self.timestamp
		if Globals.SETTINGS.AutoNameProject:
			try:
#				part_nr = gom.app.project.get( 'user_part_nr' )
				part_nr = gom.app.project.user_MEASPLAN
				rbtprg = gom.app.project.user_RBTPRG
				prj_name = '{}_{}_{}'.format( part_nr, rbtprg, currtime )
			except:
				prj_name = currtime
		else:
			prj_name = Globals.SETTINGS.ProjectName + '_' + currtime
		prj_name = Utils.sanitize_filename( prj_name )
#		gom.script.sys.set_project_keywords (
#			keywords = {'GOM_KIOSK_TimeStamp': currtime},
#			keywords_description = {'GOM_KIOSK_TimeStamp': 'internal'} )

		if Globals.FEATURE_SET.ONESHOT_MODE and not(
				Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActive() ):
			try:
				gom.script.sys.save_project() # if save fails its a readonly project/template currently open use the default save_as
				return
			except:
				pass
		gom.script.sys.save_project_as( file_name = os.path.join( Globals.SETTINGS.SavePath, prj_name ) )

# END: copied from Evaluate.Evaluate
###############################################################################################

	def send_success( self ):
		if self.multi_eval_signal is None:
			self.log.error( 'protocol error - no multi_eval signal on success' )
		self.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( self.multi_eval_signal.key ) ) )
		self.multi_eval_signal = None

	def send_failure( self, msg ):
		if self.multi_eval_signal is None:
			self.log.error( 'protocol error - no multi_eval signal on failure' )
		self.send_signal( Communicate.Signal( Communicate.SIGNAL_FAILURE,
			'{} - {}'.format( self.multi_eval_signal.key, msg ) ) )
		self.multi_eval_signal = None

	def splitall(self, path):
		# oreilly cookbook
		allparts = []
		while 1:
			parts = os.path.split(path)
			if parts[0] == path:  # sentinel for absolute paths
				allparts.insert(0, parts[0])
				break
			elif parts[1] == path: # sentinel for relative paths
				allparts.insert(0, parts[1])
				break
			else:
				path = parts[0]
				allparts.insert(0, parts[1])
		return allparts

	def on_multi_eval( self, signal ):
		self.multi_eval_signal = signal
		value = pickle.loads( signal.value )
		for k,v in value.items():
			self.log.debug('received {}: {}'.format( k, v ) )
		self.timestamp = value['timestamp']
		template = value['template']
		template_cfg = value['template_cfg']
		if self.remote_eval:
			# guess remote location of refxml file
			# TODO check, if this can work in all circumstances
			dirs = self.splitall( value['refxml'] )
			dirs = dirs[2:]
			dirs = [Globals.SETTINGS.MultiRobot_RemoteEvalShare] + dirs
			#self.log.debug('refxml dirs {}'.format(repr(dirs)))
			self.refxml = os.path.join( *dirs )
			self.log.debug('Remote refxml {}'.format(self.refxml))
		else:
			self.refxml = value['refxml']
		self.temperature = value['temperature']
		keywords = value['keywords']
		additional_kws = value['additional_kws']
		mseries = value['mseries']
		robot_program_id = value['robot_program_id']
		Globals.ADDITIONAL_PROJECTKEYWORDS = additional_kws[0]
		Globals.ADDITIONAL_PERPARTKEYWORDS = additional_kws[1]

		if not self.open_template( template, template_cfg ):
			return False

		if robot_program_id is None:
			if self.refxml is not None and not self.import_photogrammetry( self.refxml ):
				return False

		# set temperature in evaluation project
		if self.temperature is not None:
			gom.script.sys.set_stage_parameters( measurement_temperature = self.temperature )

		try:
			self.set_project_keywords( keywords )
		except Exception as e:
			msg = 'Setting keywords failed: {}'.format( e )
			self.log.exception( msg )
			self.send_failure( msg )
			return False

		try:
			self.save_project()
		except Exception as e:
			msg = 'Initial project save failed: {}'.format( e )
			self.log.exception( msg )
			self.send_failure( msg )
			return False

		self.tmp_project_file = gom.app.project.project_file

		# switch to preview mode to have a defined state
		if gom.app.project.is_part_project:
			gom.script.sys.switch_project_into_preliminary_data_mode( preliminary_data=True )

		if robot_program_id is not None:
			self.log.debug( 'Set program ids todo for measure clients' )
			for c in self.measure_clients:
				c.pathExt = self.timestamp
				if robot_program_id == Globals.SETTINGS.MultiRobot_CalibRobotProgram:
					self.log.error( 'Received calibration robot program id for evaluation' )
				else:
					c.robot_program_id = robot_program_id
					self.todo_prgids += 1

				c.tritop_series = mseries[c.id]['tritop']
				self.todo_tritop += 0
				c.calib_series = mseries[c.id]['calib']
				c.atos_series = mseries[c.id]['atos']
				self.todo_atos += 0
		else:
			self.log.debug( 'Set measurement series todo for measure clients' )
			for c in self.measure_clients:
				c.pathExt = self.timestamp
				c.tritop_series = mseries[c.id]['tritop']
				self.todo_tritop += len( c.tritop_series )
				c.calib_series = mseries[c.id]['calib']
				c.atos_series = mseries[c.id]['atos']
				self.todo_atos += len( c.atos_series )

				c.robot_program_id = None
				self.todo_prgids += 0

				mmts = [gom.app.project.measurement_series[ml]
					for ml in c.tritop_series + c.atos_series]
				if not Globals.SETTINGS.OfflineMode and len( mmts ) > 0:
					gom.script.automation.clear_measuring_data ( measurements=mmts )

		self.total_tritop = self.todo_tritop
		self.total_atos = self.todo_atos
		self.total_prgids = self.todo_prgids
		self.log.debug( 'Todo totals: prgids {} tritops {} atos {}'.format(
			self.total_prgids, self.total_tritop, self.total_atos ) )
		if self.todo_tritop == 0 and self.todo_atos > 0:
			self.init_atos_mmts()

		# only forced calibration, nothing to evaluate, finish cycle directly
		# see above, should no longer happen
		if self.todo_tritop == 0 and self.todo_atos == 0 and self.total_prgids == 0:
			self.log.info( 'No measurement import todos - Multi eval finished' )
			for c in self.measure_clients:
				c.remove_import_folder()
			self.send_success()
			self.finish_cycle()
			return True

		self.log.debug( 'Multi eval started - waiting for mmt data files (pathExt: {})'.format( self.timestamp ) )
		return True

	def on_tritop_finished( self ):
		master_series = None
		for c in self.measure_clients:
			if len(c.tritop_series):
				for t in c.tritop_series:
					self.log.debug('tritop :{} {}'.format(t, gom.app.project.measurement_series[t].get('reference_points_master_series')))
					if gom.app.project.measurement_series[t].get('reference_points_master_series') is None:
						master_series = gom.app.project.measurement_series[t]

		if master_series is None:
			msg = 'No photogrammetry master series found in {}'.format(
				', '.join( [ms for ms in itertools.chain( [c.tritop_series for c in self.measure_clients] )] ) )
			self.log.error( msg )
			self.send_failure( msg )
			return False

		errorlog = Verification.ErrorLog()
		state = self.checks.checkphotogrammetry( master_series, errorlog )
		self.log.debug( 'VerificationState after series check: {}'.format( state ) )

		# Failure
		if state != Verification.VerificationState.ErrorFree:
			msg = '{}: {}'.format(
				Globals.LOCALIZATION.msg_photogrammetry_verification_failed,
				errorlog.Error )
			self.log.error( msg )
			self.send_failure( msg )
			return False

		if not self.recalc_initial_alignments():
			# recalc already sends failure
			return False

		self.set_initial_alignments()
		# TODO as it stands, temperature might be None (coming from control)
#		self.log.debug( 'refxml temperature {:.2f} master {}'.format(
#			self.temperature, str( master_series ) ) )
		refxml_result = self.tritop.export_photogrammetry( master_series, temperature=self.temperature )
		self.log.debug( 'Exported refxml {}'.format( refxml_result ) )
		self.refxml_file = refxml_result

## TODO tmp project save for photogrammetry
#		try:
#			Evaluate.EvaluationAnalysis.export_results( True )
#			self.project_file = gom.app.project.project_file
##			self.save_project()
#		except Exception as e:
#			msg = 'Photogrammetry project save failed: {}'.format( e )
#			self.log.exception( msg )
##			self.send_failure( msg )
##			return False

		return True


	def init_atos_mmts( self ):
		for c in self.measure_clients:
			c.first_atos_series()

	def on_atos_series_finished( self, client, mseries ):
		self.log.debug( 'Client {} finish atos series {}'.format( client.name, mseries ) )
#		client.log_stats()
		try:
			ml = gom.app.project.measurement_series[mseries]
		except Exception as e:
			self.log.exception( 'MSeries {} not found'.format( mseries ) )
			# TODO send failure and switch to False, when atos target problem in import_files is solved
			return True
		errorlog = Verification.ErrorLog()
		state = self.checks.checkdigitizing( ml, True, errorlog )
		if state ==  Verification.VerificationState.ErrorFree:
			return True

		state_msg = 'VerificationState {}'.format( state )
		if state == Verification.VerificationState.Abort:
			state_msg = 'VerificationState Abort'
		elif state == Verification.VerificationState.Retry:
			state_msg = 'VerificationState Retry'
		elif state == Verification.VerificationState.NeedsCalibration:
			state_msg = 'VerificationState NeedsCalibration'

		msg = '{}: {}'.format( state_msg, errorlog.Error )
		self.log.error( msg )
		self.send_failure( msg )
		return False


	def on_atos_finished( self ):
		# after performing every digitize measurement series, its possible to check the alignment residual
		errorlog = Verification.ErrorLog()
		res = self.checks.checkalignment_residual( errorlog )
		if res == Verification.DigitizeResult.TransformationMarginReached:
			msg = '{}: {}'.format(
				Globals.LOCALIZATION.msg_general_failure_title, errorlog.Error )
			self.log.error( msg )
			self.send_failure( msg )
			return False
		elif res == Verification.DigitizeResult.RefPointMismatch:
			msg = '{}: {}'.format(
				Globals.LOCALIZATION.msg_general_failure_title,
				Globals.LOCALIZATION.msg_verification_refpointmismatch + '<br/>' + errorlog.Error )
			self.log.error( msg )
			self.send_failure( msg )
			return False

		self.log.info( 'Result alignment residual check: {}'.format( res ) )
		return True

	def import_files(self, clients):
		if self.todo_prgids > 0:
			return self.import_files_inline_mode( clients )
		else:
			return self.import_files_teach_mode( clients )

	def import_files_teach_mode(self, clients):
		# TODO see Client import_files method, mseries cases...
		return True

	def import_files_inline_mode(self, clients, collect_tritop=False):
		tritop_files = []
		import_files = []
		all_files = []
		for client in clients:
			tfiles, ifiles, afiles = client.collect_files( separate=True )
			tritop_files += tfiles
			import_files += ifiles
			all_files += afiles
			self.log.debug( 'Files {} /all {} from {}:{}'.format(
				ifiles, afiles, client.name, client.extSavePath ) )
			if collect_tritop:
				print('collect_tritop', client.name, len( tfiles ), len( afiles ))
				client.tritop_files = tfiles
				client.all_files = afiles

		if len( tritop_files ):
			self.tritop_present = True
			print('tritop early out')
			return True

		if not len( import_files ):
			return True

		start = time.time()
		self.atos_present = True

		# switch to original alignment for any imports
		original_alignment = Evaluate.Evaluate.get_original_alignment()
		gom.script.manage_alignment.set_alignment_active (
			cad_alignment=original_alignment )

		if not self.refxml_loaded:
			if not self.import_photogrammetry( self.refxml ):
				# refxml import includes failure handling
				return False
			self.refxml_loaded = True

		self.log.debug( 'Clients {}: ATOS imports'.format(
			', '.join( [c.name for c in clients] ) ) )
		
		try:
			for i in range(4):
				try:
					gom.script.atos.load_measurement(
						files=import_files,
						import_mode='replace_elements' )
					break
				except Exception as e:
					self.log.error(str(e))
					gom.script.sys.delay_script (time=2)
			else:
				msg = 'Clients {}: Failed to import measurements: {}'.format(
					', '.join( [c.name for c in clients] ), '4 retries' )
				self.log.error( msg )
				self.send_failure( msg )
				return False
		except Exception as e:
			msg = 'Clients {}: Failed to import measurements: {}'.format(
				', '.join( [c.name for c in clients] ), e )
			self.log.exception( msg )
			self.send_failure( msg )
			return False

		end = time.time()
		size = 0
		for f in all_files:
			size += os.stat( f ).st_size
			try:
				os.unlink( f )
			except:
				pass

		self.update_stats( len( import_files ), end - start, size )
		return True


	def finish_imports_inline_mode(self, clients):
		if not self.import_files_inline_mode( clients, collect_tritop=True ):
			return False

		if self.atos_present:
			for c in clients:
				c.remove_import_folder()

#		print('todos', self.todo_prgids, '-', len( clients ))
#		print('mmt state tritop', self.tritop_present, self.tritop_imported, 'atos', self.atos_present)

		self.todo_prgids -= len( clients )
		if self.atos_present:
			for c in clients:
				if not self.on_atos_series_finished( c, c.atos_target ):
					return False

		if self.todo_prgids > 0:
#			print('remaining todos', self.todo_prgids)
			return True

		if self.tritop_present:
			if not self.load_all_photogrammetry_mmts():
				return False

		if self.tritop_present and self.tritop_imported:
			if not self.on_tritop_finished():
				return False

			# RESULT signal
			self.send_result( True )

			# cycle finished
			self.send_success()
			self.finish_cycle()
			return True

#			if self.tritop_executed() and not self.tritop_loaded():
#				msg = 'All tritop finished but not all imported'
#				self.log.error( msg )
#				self.send_failure( msg )
#				return False

		# if not tritop must be atos
		if self.atos_present:
			self.log_stats()
			if not self.on_atos_finished():
				return False

		# measurements finished => success message to inline control
		self.send_success()
		self.log.debug( 'Measurements and their checks finished, next step: project evaluation' )

		if self.atos_present:
			# evaluate the measured project
			# evaluate_project is saving project (so errors can be analysed later)
			# evaluation errors are transmitted in exports done by evaluation
			# only errors in the measurement process are transmitted directly to control (see above)
			self.evaluate_project()

		# RESULT signal
		self.send_result( True )

		# cycle finished
		self.finish_cycle()
		return True


	def load_all_photogrammetry_mmts( self ):
		self.log.debug( 'Load all photogrammetry files' )
		# Collect files to import
		all_tritops = []
		for client in self.measure_clients:
			all_tritops = all_tritops + client.tritop_files
		self.log.debug( 'Importing {} photogrammetry files'.format( len( all_tritops ) ) )

		try:
			gom.script.photogrammetry.load_measurement(
				files=all_tritops,
				import_mode='replace_elements' )
		except Exception as e:
			msg = 'Failed to import photogrammetry measurements: {}'.format( e )
			self.log.exception( msg )
			self.send_failure( msg )
			return False

		# Remove files + folder, update client status
		for client in self.measure_clients:
			for f in client.all_files:
				try:
					os.unlink( f )
				except:
					pass
			client.tritop_files = []
			client.all_files = []
			client.remove_import_folder()

		self.tritop_imported = True
		return True

	def on_mmts_finished( self, signals ):
		self.log.debug( 'MMTS finished for {} clients'.format( len( signals ) ) )
		teach_mode = True
		mseries_list = []
		robot_program_ids = []
		success_list = []
		clients = []
		for signal in signals:
			value = pickle.loads( signal.value )
			id = value['id']
			mseries_list.append( value['mseries'] )
			robot_program_ids.append( value['robot_program_id'] )
			if value['robot_program_id'] is not None:
				teach_mode = False
			success_list.append( value['success'] )
			self.log.info( 'Client {} Finished MSeries {} / RobotPrgID {} OK? {}'.format(
				self.measure_clients[id].name, value['mseries'],
				value['robot_program_id'], value['success'] ) )
			# TODO at the moment, if there is a failed mmt, cancel the whole evaluation
			if value['success']:
				clients.append( self.measure_clients[id] )
			else:
				return False
			# acknowledge mmt finish signal
			# TODO add identification to answer (mmt client no)
			self.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key ) ) )

		if teach_mode:
			# TODO (see old on_mmt_finished below)
			pass
		else:
			return self.finish_imports_inline_mode( clients )

# TODO
#   extract second half of function below for teach mode
#
#	def on_mmt_finished( self, signal ):
#		value = pickle.loads( signal.value )
#		id = value['id']
#		mseries = value['mseries']
#		robot_program_id = value['robot_program_id']
#		success = value['success']
#		client = self.measure_clients[id]
#		# acknowledge mmt finish signal
#		self.log.info( 'Client {} Finished MSeries {} / RobotPrgID {} OK? {}'.format(
#			client.name, mseries, robot_program_id, success ) )
#		self.send_signal( Communicate.Signal( Communicate.SIGNAL_SUCCESS, str( signal.key ) ) )
##		if success is False:
##			return False
#
#		if robot_program_id is not None:
#			target = client.import_files( robot_program_id,
#				refxml_callback=None if self.refxml_loaded()
#					else lambda: self.import_photogrammetry( self.refxml ),
#				fail=self.send_failure )
#			self.log.debug( 'MMT finish - target {}'.format( target ) )
#			if target is False:
#				return False
#
#			if len( client.tritop_files ) == 0:
#				client.remove_import_folder()
#
#			self.todo_prgids -= 1
#			if self.atos_executed():
#				if not self.on_atos_series_finished( client, target ):
#					return False
#
#			if self.todo_prgids == 0:
#				if self.tritop_executed():
#					self.load_all_photogrammetry_mmts( signal )
#
#				if self.tritop_executed() and self.tritop_loaded():
#					if not self.on_tritop_finished():
#						return False
#
#					# cycle finished
#					self.send_success()
#					self.finish_cycle()
#					return True
#
#				if self.tritop_executed() and not self.tritop_loaded():
#					msg = 'All tritop finished but not all imported'
#					self.log.error( msg )
#					self.send_failure( msg )
#					return False
#
#				# if not tritop must be atos
#				if self.atos_executed():
#					self.log_stats()
#					if not self.on_atos_finished():
#						return False
#
#				# no action for calibration
#
#				# measurements finished => success message to inline control
#				self.send_success()
#				self.log.debug( 'measurements and their checks finished, next project evaluation' )
#
#				if self.atos_executed():
#					# evaluate the measured project
#					# evaluate_project is saving project (so errors can be analysed later)
#					# evaluation errors are transmitted in exports done by evaluation
#					# only errors in the measurement process are transmitted directly to control (see above)
#					self.evaluate_project()
#
#				# cycle finished
#				self.finish_cycle()
#				return True
#
#		elif mseries in client.tritop_series:
#			client.import_files( mseries, fail=self.send_failure )
#			self.todo_tritop -= 1
#			if self.todo_tritop == 0:
#				if not self.on_tritop_finished():
#					return False
#				if self.todo_atos > 0:
#					self.init_atos_mmts()
#				else:
#					# cycle finished
#					self.send_success()
#					self.finish_cycle()
#
#		elif mseries in client.atos_series:
#			client.import_files( mseries, fail=self.send_failure )
#			client.next_atos_series()
#			res = self.on_atos_series_finished( client, mseries )
#			if not res:
#				return False
#			self.todo_atos -= 1
#			if self.todo_atos == 0:
#				if not self.on_atos_finished():
#					return False
#
#				# cycle finished
#				self.send_success()
#				self.finish_cycle()
#
#		return True


	########################################################################
	# cycle init/reset, abort and finish
	def reset_cycle( self ):
		for c in self.measure_clients:
			c.reset()

		self.multi_eval_signal = None
		self.tmp_project_file = None
		self.timestamp = None
		self.refxml = None
		self.refxml_loaded = False
		self.temperature = None
		self.total_tritop = 0
		self.total_atos = 0
		self.total_prgids = 0
		self.todo_tritop = 0
		self.todo_atos = 0
		self.todo_prgids = 0
		self.tritop_present = False
		self.tritop_imported = False
		self.atos_present = False

		self.project_file = None
#		self.result_file = None
		self.refxml_file = None

		self.clear_stats()

	def clear_stats(self):
		self.stats = {'time': 0.0, 'size': 0, 'no': 0}
	def update_stats(self, no, time, size):
		self.stats['no'] += no
		self.stats['time'] += time
		self.stats['size'] += size
	def log_stats(self):
		self.log.debug( 'Time stats for import {} uid files: {:.4f}s, total size {:.4f}MB'.format(
			self.stats['no'], self.stats['time'], self.stats['size']/1024/1024 ) )

	def abort_cycle( self ):
		try:
			self.save_project()
		except:
			pass
		gom.script.sys.close_project()

		if self.multi_eval_signal is not None:
			self.log.error( 'protocol error - multi_eval signal not reset at abort cycle' )
		if not self.idle_state:
			self.send_idle( 1 )

		self.reset_cycle()

	def finish_cycle( self ):
		gom.script.sys.close_project()
		if ( os.path.exists( self.tmp_project_file ) ):
			os.unlink( self.tmp_project_file )

		if self.multi_eval_signal is not None:
			self.log.error( 'protocol error - multi_eval signal not reset at finish cycle' )
		if not self.idle_state:
			self.send_idle( 1 )

		self.reset_cycle()

	def terminate_client( self ):
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
		# no more sorrows


#############################################################################################
# TODO evaluation result to be replaced...
#   Replace: send_all_results, send_result/inline_result, export_results, overall_result structure,
#     project_keywords, perform_automatic_result_check

	def evaluate_project( self ):
		'''
		The project evaluation specific parts are done by this function.
		'''
		self.analysis.recalculate_project_if_needed()
		self.analysis.polygonize()

#		gom.script.sys.recalculate_project ()
		robot_program_id = None
		if len(self.measure_clients):
			robot_program_id = self.measure_clients[0].robot_program_id
		found = False
		if robot_program_id is not None:
			for r in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'reports']}):
				if str(robot_program_id) in r.name:
					self.log.debug( 'Recalc single report: {}'.format( r ) )
					gom.script.sys.recalculate_elements( elements=[r] )
					found = True
					break
		if not found:
			gom.script.sys.recalculate_project ()

		try:
			try:
				self.export_results( True )
			except Exception as error:
				self.log.exception( 'Failed to export results: {}'.format( error ) )
		finally:
			pass


	def export_results( self, result ):
		'''
		This function saves the current project in a subdirectory of SavePath.
		'''
		Evaluate.EvaluationAnalysis.export_results( True )
		self.project_file = gom.app.project.project_file

#		( project_name, export_path ) = Evaluate.Evaluate.export_path_info()
#		self.log.debug( 'Project file: {}/{}'.format(
#			os.path.join( export_path, project_name ), gom.app.project.project_file ) )
#
#		# DMO export
#		robot_program_id = None
#		if len( self.measure_clients ):
#			robot_program_id = self.measure_clients[0].robot_program_id
#		found = False
#		report_pages = []
#		if robot_program_id is not None:
#			for r in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'reports']}):
#				if str( robot_program_id ) in r.name:
#					self.log.debug( 'DMIS export report page: {}'.format( r ) )
#					report_pages = [r]
#					found = True
#					break
#		if not found:
#			report_pages = gom.app.project.reports
#
#		gom.script.sys.export_gom_xml_by_report_pages (
#			file=os.path.join(export_path, project_name + '.dmo'),
#			format=gom.File ('giefv20_to_quirl7.xsl'),
#			pages=report_pages )
#		self.log.debug( 'DMIS file: {}'.format( os.path.join(export_path, project_name + '.dmo' ) ) )
#		self.result_file = os.path.join(export_path, project_name + '.dmo' )
#
#		# "CustomPatch" for deleting old projects
##		evali = Globals.SETTINGS.MultiRobot_EvalClients.index( self.control_param )
##		remote_childs = Globals.SETTINGS.MultiRobot_EvalPerRemote * len(
##			Globals.SETTINGS.MultiRobot_HostAddresses )
##
##		# all first remotes + first local eval
##		if ( evali <= len( Globals.SETTINGS.MultiRobot_HostAddresses )
##			or self.control_param == Globals.SETTINGS.MultiRobot_EvalClients[remote_childs] ):
#
#		# Remove old project files
#		self.log.debug( 'Eval Client {} - checking old projects'.format( self.control_param ) )
#		_, export_path = Evaluate.Evaluate.export_path_info()
#		ctime = time.time()
#		try: # better secure this, multiple concurrent accesses possible
#			for pfilename in os.listdir( export_path ):
#				ignore = False
#				for robotprg in Globals.SETTINGS.MultiRobot_ProjectKeep:
#					if '_' + str( robotprg ) + '_' in pfilename:
#						ignore = True
#				if not ignore:
#					pfile = os.path.join( export_path, pfilename )
#					if ctime - os.path.getmtime( pfile ) > Globals.SETTINGS.MultiRobot_ProjectTimeout:
#						try:
#							self.log.debug( 'Remove old project {}'.format( pfilename ) )
#							os.unlink( pfile )
#						except:
#							pass
#		except:
#			pass

	def send_signal( self, signal ):
		'''
		sends any signal
		'''
		if self.handler is not None:
			self.log.info( 'sending signal {}'.format( signal ) )
			self.handler.push ( signal.encode() )

	def send_idle( self, value ):
		'''
		sends idle / non-idle signal
		'''
		self.log.debug( 'IDLE = {}'.format( value ) )
		data = { 'idle': value, 'swpid': gom.getpid()}
		if Globals.SETTINGS.MultiRobot_MemoryDebug and value == 1:
			pproc = psutil.Process( os.getpid() )
			data['meminfo_py'] = pproc.memory_info().vms / 1024 / 1024
			data['meminfo_gom'] =  str( gom.app.memory_information.total )
		sig = Communicate.Signal( Communicate.SIGNAL_CONTROL_IDLE, pickle.dumps( data ) )
		self.send_signal( sig )
		self.idle_state = value == 1


	def collect_result_data( self, result ):
		sync = '-'
		serial = '-'
		robot_program = '-'
		try:
			sync = gom.app.project.user_SYNC
			serial = gom.app.project.user_MEASPLAN
			robot_program = gom.app.project.user_RBTPRG
		except:
			pass

		msg = {
			'result': True,
			'sync': sync,
			'serial': serial,
			'robot_program': robot_program,
			'swpid': gom.getpid(),
			'timestamp': self.timestamp,
			'project_file': self.project_file,
#			'result_file': self.result_file,
			'refxml_file': self.refxml_file
		}
		return msg

	def send_result( self, result ):
		'''
		Collect evaluation result and send it with the result signal
		'''
		msg = self.collect_result_data( result )
		self.log.info( 'Sending result {}'.format( msg ) )
		self.handler.push ( Communicate.Signal(
			Communicate.SIGNAL_RESULT, pickle.dumps( msg ) ).encode() )


	@staticmethod
	def client_start( server_ip, port, control_param, log_name='eval_client', use_localization=True ):
		'''
		start function for clients, creates the class and has the main loop
		'''
		client = MultiClient( server_ip, port, control_param, log_name=log_name, use_localization=use_localization )

		# setup client save path for remote eval instances
		if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID is not None:
			if len( Globals.SETTINGS.MultiRobot_ClientSavePath) == 1:
				Globals.SETTINGS.SavePath = Globals.SETTINGS.MultiRobot_ClientSavePath[0]
			else:
				Globals.SETTINGS.SavePath = Globals.SETTINGS.MultiRobot_ClientSavePath[Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT_ID]
			if not os.path.exists( Globals.SETTINGS.SavePath ):
				os.makedirs( Globals.SETTINGS.SavePath )

		gom.script.sys.close_project ()

		client.wait_till_connected()
		client.send_idle( 1 )
		client.globaltimer_active = True

		try:
			while True:
				res = client.test_rolling_log_file()
				if res:
					client.log.info( gom.app.get( 'application_name') + ' '
						+ gom.app.get( 'application_build_information.version' ) + ', Rev. '
						+ gom.app.get( 'application_build_information.revision' ) + ', Build '
						+ gom.app.get( 'application_build_information.date' ) )

#				while client.check_for_activity():  # get all signals
#					pass

				mmt_finish_sigs = []
				for sig in client.handler.LastAsyncResults:
					if sig == Communicate.SIGNAL_MULTIROBOT_EVAL and not client.idle_state:
						client.send_signal( Communicate.Signal(
							Communicate.SIGNAL_FAILURE,
							'{} - {}'.format( str( Communicate.SIGNAL_MULTIROBOT_EVAL.key ), 'Busy' ) ) )
					if sig == Communicate.SIGNAL_MULTIROBOT_EVAL and client.idle_state:
						client.send_idle( 0 )
						# TODO simple timeslice for asyncore to get the signal out?
						#client.check_for_activity()
						client.signal_timeslice()
						res = client.on_multi_eval( sig )
						# evaluation failure => abort cycle
						if not res:
							client.abort_cycle()
					if sig == Communicate.SIGNAL_MULTIROBOT_MMT_FINISHED:
						# idle? => already failed, just answer the sig with failure
						if client.idle_state:
							# TODO add identification to answer (mmt client no)
							client.send_signal( Communicate.Signal(
								Communicate.SIGNAL_FAILURE,
								'{} - {}'.format( str( sig.key ), 'Aborted' ) ) )
						else:
							mmt_finish_sigs.append( sig )
							# collect more sigs of same type immediately
							continue
					if sig == Communicate.SIGNAL_MULTIROBOT_MMT_FAILED:
						client.log.error( 'Received failure: "{}"'.format( sig ) )
						# TODO save project (?), abort cycle (?)
						client.abort_cycle()
						break
					if sig == Communicate.SIGNAL_MULTIROBOT_EVAL_TERMINATE:
						client.log.error( 'Received terminate: "{}"'.format( sig ) )
						client.terminate_client()

				# handle mmt finished signals
				if len( mmt_finish_sigs ) != 0:
					res = client.on_mmts_finished( mmt_finish_sigs )
					if not res:
						client.abort_cycle()

				# import pending mmts
				if ( client.todo_prgids > 0 or client.todo_tritop > 0 or client.todo_atos > 0 ):
					res = client.import_files( client.measure_clients )
					if res is False:
						client.abort_cycle()

				gom.script.sys.delay_script( time=1 )
		except ( SystemExit, gom.BreakError ):
			pass
		except Exception as error:
			client.log.exception( error )
		finally:
			client.close()
		client.log.info( 'exit' )
		gom.script.sys.exit_program()

# TODO needed for teach mode?
#					if sig == Communicate.SIGNAL_OPEN:
#						client.on_template( sig )
#						break
#					if sig == Communicate.SIGNAL_CLOSE_TEMPLATE:
#						client.on_template( sig )
#						break
#					if sig == Communicate.SIGNAL_EVALUATE:
#						client.on_evaluate( sig )
#						sendidle = True
#						break  # only one between a activity check
#				if sendidle:
#					client.send_idle()


class MeasureClient( Utils.GenericLogClass ):
	def __init__(self, id, logger):
		Utils.GenericLogClass.__init__( self, logger )
		self.id = id
		self.extSavePath = getExternalSavePath( id )
		self.pathExt = None
		self.name = '{}: {}'.format( id, self.extSavePath )
		self.reset()

	def reset( self ):
		self.tritop_series = []
		self.atos_series = []
		self.calib_series = []
		self.active_atos_series = ''

		self.robot_program_id = None
#		self.tritop_present = False
		self.tritop_files = []
		self.all_files = []
#		self.tritop_imported = False
#		self.refxml_loaded = False
#		self.atos_present = False
		self.atos_target = None


	def first_atos_series( self ):
		self.active_atos_series = self.atos_series[0]
	def next_atos_series( self ):
		i = self.atos_series.index( self.active_atos_series )
		try:
			self.active_atos_series = self.atos_series[i + 1]
		except:
			self.active_atos_series = ''

	def remove_import_folder(self):
		path = None
		if self.pathExt is not None:
			path = os.path.join( self.extSavePath, self.pathExt )
		if path is not None and os.path.exists( path ):
			try:
				os.rmdir( path )
			except:
				pass

	def mmt_file_type(self):
		path = None
		if self.pathExt is not None:
			path = os.path.join( self.extSavePath, self.pathExt )
		if path is None or not os.path.exists( path ):
			return None

		files = os.listdir( path )
		f = None
		for f in files:
			if f.endswith( '.uid' ):
				break
		if f is None:
			return None

		mfiles = fnmatch.filter( files, os.path.splitext( f )[0] + '*' )
		print( 'mmt_file_type', mfiles )
		for mf in mfiles:
			if mf.endswith( 'points.data' ):
				return 'atos'
			if mf.endswith( 'points_mask.data' ):
				return 'atos'
			if f.endswith( 'images.data' ):
				return 'atos'
		return 'tritop'

	def collect_files(self, separate=False):
		all_files = []
		import_files = []
		tritop_files = []
		path = None
		if self.pathExt is not None:
			path = os.path.join( self.extSavePath, self.pathExt )
		if path is None or not os.path.exists( path ):
			if separate:
				return tritop_files, import_files, all_files
			else:
				return import_files, all_files

		files = os.listdir( path )
		for _file in fnmatch.filter( files, '*.uid' ):
			name = os.path.splitext( _file )[0]
			atos = False
			imp = None
			for f in fnmatch.filter( files, '{}*.*'.format( name ) ):
				all_files.append( os.path.join( path, f ) )
				if not f.endswith( '.data' ):
					continue
				if f.endswith( 'points.data' ):
					atos = True
					continue
				if f.endswith( 'points_mask.data' ):
					atos = True
					continue
				if f.endswith( 'images.data' ):
					atos = True
					continue
				imp = f

			if imp:
				if separate:
					if atos:
						import_files.append( os.path.join( path, imp ) )
						if self.atos_target is None:
							# guess atos series from uid file
							self.atos_target = self.guess_atos_mseries(
								os.path.join( path, _file ) )
					else:
						tritop_files.append( os.path.join( path, imp ) )
				else:
					import_files.append( os.path.join( path, imp ) )

		if separate:
			return tritop_files, import_files, all_files
		else:
			return import_files, all_files


	def guess_atos_mseries(self, uid_file):
		self.log.debug( 'Guess atos series {} from file {}'.format( self.atos_series, uid_file ) )
		try:
			with open( uid_file, 'r', encoding='utf-8') as f:
				lines = f.readlines()
				# lines: version, mseries name, mmt name, mmt type, mmt uid
				self.log.debug( 'Atos information from file {}: {}'.format(
					uid_file, lines[1].strip() ) )
				return lines[1].strip()
		except Exception as e:
			self.log.error( 'Getting information from file {} failed: {}'.format( uid_file, e ) )

		return None