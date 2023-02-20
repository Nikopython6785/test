# -*- coding: utf-8 -*-
# Script: Photogrammetry, Digitize and Sensor Definition
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
# 2012-10-23: Fixed import of photogrammetry refxml, only test against latest file, remove the remaining
# 2012-12-04: check sensor status before executing measurement series
# 2013-01-22: rewrote verification routines for less calibration processes
#             imported photogrammetry is now an extra measurement series
# 2013-05-02: check sensor warmuptime before every measurement
# 2015-11-02: Support for multi measurement setup/series in Sensor class.

'''
	This module contains measurement functionality for Atos and Tritop measurements. It also contains functions to manage
	the Sensor.
'''

from ..Misc import Utils, Globals
from .Verification import VerificationState, DigitizeResult, ErrorLog
from ..Communication.Inline import InlineConstants
from ..Communication import Communicate
import gom
import glob, json, os, datetime, warnings

class MeasureTritop( Utils.GenericLogClass ):
	'''
	This class contains the functionality for the photogrammetry measurement.
	'''
	parent = None
	imported_count = {}
	failed_templates = {}

	def __init__( self, logger, parent ):
		'''
		initializer function to init logging, calibration, dialog
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.imported_count = {}
		self.failed_templates = {}
		self.performed_hyper_scale = False

	def hasPerformedHyperScaleMeasurement(self):
		return self.performed_hyper_scale

	def isFailedTemplate( self, template = None ):
		if template is not None:
			return self.failed_templates.get( template, False )
		else:
			return self.failed_templates.get( Globals.SETTINGS.CurrentTemplate, False )

	def setFailedTemplate( self, value, template = None ):
		if template is not None:
			self.failed_templates[template] = value
		else:
			self.failed_templates[Globals.SETTINGS.CurrentTemplate] = value
		return value

	def execute_active_measurement_series( self, clear_measurement_data = False ):
		'''
		Hook function to add more functionality around executing a measurement series
		'''
		if Globals.SETTINGS.InAsyncAbort:
			Globals.SETTINGS.InAsyncAbort = False
			raise gom.BreakError
		try:
			Globals.SETTINGS.AllowAsyncAbort = True
			self.parent.position_information.start_measurement_list()
			if gom.app.project.is_part_project and Globals.SETTINGS.OfflineMode:
				if self.parent.IsVMRlight:
					# cannot even move. just do some logs for some time
					for i in range(4):
						self.log.debug( 'Measuring...' )
						gom.script.sys.delay_script( time=5 )
				else:
					# just move. new mmt concept does not allow keeping measurement data
					active_ms = Utils.real_measurement_series( filter='is_active==True' )
					gom.script.automation.forward_move_to_position(
						measurement=gom.app.project.measurement_paths[active_ms[0].name].path_positions[-1] )
			else:
				if Globals.SETTINGS.Inline:
					cmd = gom.script.automation.execute_active_measurement_series
				else:
					cmd = gom.interactive.automation.execute_active_measurement_series
				if clear_measurement_data:
					gom.script.automation.clear_measuring_data( measurements = [Utils.real_measurement_series( filter='is_active==True' )[0]] )
					cmd()
				else:
					cmd( direct_movement=isDirectMoveAllowed( Utils.real_measurement_series( filter='is_active==True' )[0] ) )
		finally:
			Globals.SETTINGS.AllowAsyncAbort = False
			self.parent.position_information.end_measurement_list()
		return True
	
	def perform_single_measurements(self, single_measurements):
		if Globals.SETTINGS.InAsyncAbort:
			Globals.SETTINGS.InAsyncAbort = False
			raise gom.BreakError
		gom.script.automation.clear_measuring_data ( measurements = single_measurements )
		save_folder = ''
		if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
			save_folder = Globals.DRC_EXTENSION.getExternalSavePath()
		try:
			Globals.SETTINGS.AllowAsyncAbort = True
			self.parent.position_information.start_measurement_list()
			if Globals.SETTINGS.Inline:
				gom.script.automation.measure_at_selected_positions(
					measurements=single_measurements, save_measurement_data_folder=save_folder,
					direct_movement=isDirectMoveAllowed( Utils.real_measurement_series( filter='is_active==True' )[0] ) )
			else:
				gom.interactive.automation.measure_at_selected_positions(
					measurements=single_measurements, save_measurement_data_folder=save_folder,
					direct_movement=isDirectMoveAllowed( Utils.real_measurement_series( filter='is_active==True' )[0] ) )
		finally:
			Globals.SETTINGS.AllowAsyncAbort = False
			self.parent.position_information.end_measurement_list()
		return True

	def perform_all_measurements(self, measure_series):
		'''
		executes all tritop series and verifies them after all got executed
		returns True on success, False otherwise
		'''
		self.performed_hyper_scale = False
		all_empty = True
		for ms in measure_series:
			if not len( ms.measurements ):
				continue
			all_empty = False
			break
		if all_empty: # nothing to measure
			return True

		master_series = measure_series[0]
		for ms in measure_series:
			if ms.get('reference_points_master_series') is None:
				master_series = ms
				break

		if not self.isFailedTemplate():
			if Globals.DRC_EXTENSION is None or (not Globals.DRC_EXTENSION.SecondarySideActive() and not Globals.DRC_EXTENSION.PrimarySideActive()):
				if self.import_photogrammetry( master_series ):
					return True
		else:
			self.log.info( 'Forcing Photogrammetry due to refpoint mismatch' )
			self.setFailedTemplate( False )

		measureloop = 0
		dialog_shown = False
		errorlog = ErrorLog()
		if Globals.SETTINGS.Inline:
			Globals.CONTROL_INSTANCE.send_signal( Communicate.SIGNAL_CONTROL_PHOTOGRAMMETRY_STARTED )
		while measureloop < Globals.SETTINGS.MaxDigitizeRepetition:
			del errorlog.Error  # clean errorlog
			dialog_shown = False
			for ms in measure_series:
				if not len( ms.measurements ):
					continue
				self.parent.Dialog.process_msg( step = self.parent.Dialog.Process_msg_step + 1 )
				if not self.perform_measurement( ms ):
					dialog_shown = True
					break
				for m in ms.measurements:
					if m.get('type') == 'calibration':
						self.performed_hyper_scale = True
						break

			if self.parent.Dialog is not None:
				self.parent.Dialog.processbar_step()
			if dialog_shown: # execution failed
				break

			state = self.parent.Global_Checks.checkphotogrammetry( master_series, errorlog )
			self.log.debug( 'VerificationState after series check: {}'.format( state ) )
			if self.parent.Statistics is not None:
				self.parent.Statistics.log_measurement_series()
			if state == VerificationState.ErrorFree:
				if Globals.DRC_EXTENSION is None or not Globals.DRC_EXTENSION.PrimarySideActive():
					self.export_photogrammetry( master_series )
				if Globals.SETTINGS.Inline:
					Globals.CONTROL_INSTANCE.send_signal( Communicate.SIGNAL_CONTROL_PHOTOGRAMMETRY_DONE )
				return True
			else:  # Verification failure, ask user
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_TRITOP_VERIFICATION,errorlog.Code,errorlog.Error)
					dialog_shown = True
					break
				elif not Globals.DIALOGS.show_errormsg(
						Globals.LOCALIZATION.msg_photogrammetry_verification_failed,
						errorlog.Error,
						Globals.SETTINGS.SavePath, measureloop < Globals.SETTINGS.MaxDigitizeRepetition - 1 ):
					dialog_shown = True
					break
				else:
					self.log.info( 'user decision to retry' )
					state = VerificationState.Retry

			measureloop += 1

		# on failed photogrammetry force next measurement if import count is set
		if Globals.SETTINGS.PhotogrammetryMaxImportCount > 0:
			self.imported_count[Globals.SETTINGS.CurrentTemplate] = Globals.SETTINGS.PhotogrammetryMaxImportCount + 1
		self.setFailedTemplate( True )
		if not dialog_shown:
			Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
											Globals.LOCALIZATION.msg_photogrammetry_failed_execute + '<br/>' + errorlog.Error,
											Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
		return False


	def perform_measurement( self, measure_series, single_measurements=None ):
		'''
		start measurement
		'''
		if single_measurements is None:
			single_measurements = []
		if isinstance( measure_series, str ):
			if len( measure_series ) == 0:  # no list definied
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_ERROR, '',
															Globals.LOCALIZATION.msg_photogrammetry_no_list_defined)
					return False
				Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
					Globals.LOCALIZATION.msg_photogrammetry_no_list_defined,
					Globals.SETTINGS.SavePath, False )
				return False
			measure_series = gom.app.project.measurement_series[measure_series]

		self.log.info( 'starting tritop measurement "{}"'.format( str( measure_series ) ) )
		errorlog = ErrorLog()
		clear_data = not Globals.SETTINGS.OfflineMode
		if Globals.FEATURE_SET.DRC_ONESHOT:
			clear_data = False
		# retry count as definied in settings
		measureloop = 0
		while measureloop < Globals.SETTINGS.MaxDigitizeRepetition:
			del errorlog.Error  # clean errorlog
			self.log.info( 'retry no. {}'.format( measureloop ) )
			if self.parent.Dialog is not None:
				self.parent.Dialog.process_msg_detail( Globals.LOCALIZATION.msg_evaluate_detail_msg_photogrammetry )
				self.parent.Dialog.process_image( Globals.SETTINGS.PhotogrammetryImageBinary )
				self.parent.Dialog.processbar_max_steps( 2 )
				self.parent.Dialog.processbar_step( 0 )

			state = VerificationState.ErrorFree

			# reinit sensor if needed and check warmup time (disabled from caller site for tritop)
			if not self.parent.Sensor.check_for_reinitialize():
				return False

			if not self.parent.define_active_measuring_series( measure_series ):
				return False

			self.parent.Global_Checks.reset_last_error()
			try:
				if len(single_measurements):
					self.perform_single_measurements(single_measurements)
				elif not self.execute_active_measurement_series( clear_data ):
					return False
			except Globals.EXIT_EXCEPTIONS:
				raise
			except Exception as error:  # something happend (acquisition check abort, or eg sensor loss)
				self.log.error( 'Failed to execute Measurement series\n' + (str( error ) if not isinstance(error, gom.BreakError) else 'BreakError'))
				state = self.parent.Global_Checks.analyze_error( error, measure_series, measureloop < Globals.SETTINGS.MaxDigitizeRepetition - 1, errorlog )
				self.log.debug( 'VerificationState after analyze error: {}'.format( state ) )

			clear_data = False
			self.log.debug( 'VerificationState after measurement series execute: {}'.format( state ) )
			if state == VerificationState.ErrorFree:  # no error happend
				if self.parent.Dialog is not None:
					self.parent.Dialog.processbar_step()
				return True

			if state == VerificationState.NeedsCalibration:
				pass
			elif state == VerificationState.Failure:
				self.log.info( 'Verification Failure exiting' )
				if Globals.SETTINGS.Inline:
					safety_move_to_home( self, measure_series )
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_TRITOP_VERIFICATION,errorlog.Code,errorlog.Error)
				elif errorlog.Error:
					Globals.DIALOGS.show_errormsg(
						Globals.LOCALIZATION.msg_verification_failed,
						errorlog.Error,
						Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
				safety_move_to_home( self, measure_series )
				return False
			elif state == VerificationState.ReInitSensor:
				self.log.info( 'Reinitializing Sensor' )
				if not self.parent.Sensor.reinitialize():
					self.log.error( 'failed to reinitialize sensor exiting' )
					return False
			elif state == VerificationState.OnlyInitSensor:
				self.log.info( 'Initializing Sensor' )
				if not self.parent.Sensor.initialize():
					self.log.error( 'failed to initialize sensor exiting' )
					return False
			elif state == VerificationState.Abort:  # eg emergency exit
				self.log.info( 'Verification abort exiting' )
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_ABORT, errorlog.Code, errorlog.Error)
				elif errorlog.Error:
					Globals.DIALOGS.show_errormsg(
						Globals.LOCALIZATION.msg_general_failure_title,
						errorlog.Error,
						Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
				return False
			elif state == VerificationState.UserAbort:
				self.log.info( 'Failed to execute Measurement series\nDue to break error' )
				safety_move_to_home( self, measure_series )
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_USERABORT,'','')
				return False
			elif state == VerificationState.Retry:
				pass
			elif state == VerificationState.RetryWithoutCounting:
				measureloop -= 1
				self.parent.position_information.set_continue_mlist()
			elif state == VerificationState.MoveReverseHome:
				safety_move_to_home( self, measure_series, True )
				return False

			measureloop += 1

		if Globals.SETTINGS.Inline:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_RETRY,'','')
		return False


	def filename_refpoint_sizes_data( self, filename ):
		sfilename = filename[:-7]
		sfilename = sfilename + '_sizes.json'
		return sfilename

	def save_refpoint_sizes_data( self ):
		return gom.app.project.identify_reference_point_sizes_automatically

	def refpoint_sizes_data( self ):
		refpoint_sizes = {
			'color': 'white_on_black' if gom.app.project.user_defined_reference_point_color == 'white'
				else 'black_on_white',
			'types': {},
			'fixed': {
				'used': gom.app.project.use_reference_point_size,
				'size': gom.app.project.reference_point_size,
				'thickness': gom.app.project.reference_point_thickness,
				'type': gom.app.project.reference_point_type
				}
			}

		sizes = list( gom.app.project.user_defined_reference_point_size )
		thicknesss = list( gom.app.project.user_defined_reference_point_thickness )
		types = list( gom.app.project.user_defined_reference_point_type )
		useds = list( gom.app.project.use_user_defined_reference_point_size )
		rpts = {}
		for i in range( len( sizes ) ):
			if useds[i]:
				rpt = {'size': sizes[i], 'thickness': thicknesss[i], 'type': types[i], 'use': True}
			else:
				rpt = {'size': 0.1, 'thickness': 0.1, 'type': 'user_defined', 'use': False}
			rpts['type' + str(i + 1)] = rpt

		refpoint_sizes['types'] = rpts
		return refpoint_sizes

	def apply_refpoint_sizes_data( self, transferred_refpoint_sizes ):
		gom.script.atos.set_acquisition_parameters(
			compute_reference_point_type_automatically=False,
			ref_point_type=transferred_refpoint_sizes['fixed']['type'],
			reference_point_color=transferred_refpoint_sizes['color'],
			user_defined_reference_point_types=transferred_refpoint_sizes['types'] )


	def can_import_refxml( self, error_log ):
		'''
		check preconditions of importing a refxml

		Note: This function is not allowed to change Kiosk state.
		'''
		if self.parent.isForceTritopActive():
			return False

		if Globals.SETTINGS.PhotogrammetryComprehensive:
			if Globals.SETTINGS.CurrentComprehensiveXML is None and not Globals.SETTINGS.PhotogrammetryIndependent:
				self.log.debug( 'no comprehensive photogrammetry in this run done' )
				error_log.Error += 'No comprehensive photogrammetry performed'
				return False
			if Globals.SETTINGS.PhotogrammetryOnlyIfRequired:
				if Globals.SETTINGS.PhotogrammetryMaxImportCount > 0:
					if self.imported_count.get( Globals.SETTINGS.CurrentComprehensiveXML, 0 ) >= Globals.SETTINGS.PhotogrammetryMaxImportCount:
						self.log.info( 'import count of template exceeded limit' )
						error_log.Error += 'Import count of photogrammetry exceeded'
						return False
		else:
			if not Globals.SETTINGS.PhotogrammetryOnlyIfRequired:
				return False

			# is was an template switch and a measurement is forced
			if Globals.SETTINGS.PhotogrammetryForceOnTemplateSwitch and Globals.SETTINGS.IsPhotogrammetryNeeded:
				self.log.info( 'template is different forcing photogrammetry' )
				error_log.Error += 'Template is different forcing photogrammetry'
				return False

			if Globals.SETTINGS.PhotogrammetryMaxImportCount > 0:
				if self.imported_count.get( Globals.SETTINGS.CurrentTemplate, 0 ) >= Globals.SETTINGS.PhotogrammetryMaxImportCount:
					self.log.info( 'import count of template exceeded limit' )
					error_log.Error += 'Import count of photogrammetry exceeded'
					return False
		return True

	def find_external_refxml( self, error_log, dryrun=False ):
		'''
		finds external refxml and checks time delta + temperature
		- "dryrun": only simulate operations
		returns a usable refxml filename
										None, if no usable file is found
		'''
		maxdiff = datetime.timedelta( minutes = Globals.SETTINGS.PhotogrammetryMaxTimedeltaImport )

		today = datetime.datetime.today()
		path = os.path.join( Globals.SETTINGS.SavePath, Globals.SETTINGS.PhotogrammetrySavePath )
		template_name = Globals.SETTINGS.CurrentTemplate.replace( chr( 0x7 ), '_@_' )[:-len( '.project_template' )]
		if Globals.SETTINGS.PhotogrammetryComprehensive:
			if Globals.SETTINGS.CurrentComprehensiveXML is None:
				error_log.Error += 'No external Photogrammetry defined'
				return None
			template_name = 'ComprehensivePhotogrammetry{}'.format( Globals.SETTINGS.CurrentComprehensiveXML.replace( chr( 0x7 ), '_@_' )[:-len( '.project_template' )] )
		elif Globals.SETTINGS.PhotogrammetryIndependent:
			template_name = 'IndependentPhotogrammetry'
		filename = os.path.join( path, '{}_C*.xmlref'.format( template_name ) )

		files = [( os.path.getmtime( file ), file ) for file in glob.glob( filename )]
		files = sorted( files )

		try:
			latest_file = files.pop()
		except IndexError:
			self.log.info( 'no file found' )
			error_log.Error += 'No external Photogrammetry found'
			return None

		mod_time = datetime.datetime.fromtimestamp( latest_file[0] )
		self.log.info( 'testing {} with mod_time {}'.format( latest_file[1], mod_time ) )

		if ( abs( today - mod_time ) > maxdiff ):
			# for inline only signal a recommendation
			if Globals.SETTINGS.Inline and Globals.SETTINGS.EnableRecommendedSignals:
				if not dryrun:
					Globals.CONTROL_INSTANCE.send_signal( Communicate.SIGNAL_CONTROL_PHOTOGRAMMETRY_RECOMMENDED )
			else:
				self.log.info( 'mod_time out of range' )
				error_log.Error += 'External Photogrammetry is too old'
				return None

		name = Utils.split_folders( latest_file[1] )[-1]
		try:
			file_temp = name[len( template_name + '_C' ):len( name ) - len( '.xmlref' )]
			imported_temperature = float( file_temp )
		except:
			self.log.info( 'failed to extract temperature {}'.format( name ) )
			error_log.Error += 'Failed to get temperature of external Photogrammetry'
			return None

		for _t, file in files:  # remove old files
			try:
				os.remove( file )
			except:
				pass
			try:
				os.unlink( self.filename_refpoint_sizes_data( file ) )
			except:
				pass

		# reinit sensor if needed
		if not self.parent.Sensor.check_for_reinitialize():
			error_log.Error += 'Failed to initialize sensor'
			return None
		current_temperature = self.parent.Thermometer.get_temperature()
		if current_temperature is None:
			self.log.info( 'current temperature is None' )
			error_log.Error += 'Failed to get current temperature'
			return None
		if abs( imported_temperature - current_temperature ) > Globals.SETTINGS.PhotogrammetryMaxTemperatureLimit:
			self.log.info( 'Temperature: imported {} - current {}'.format( imported_temperature, current_temperature ) )
			error_log.Error += 'Temperature delta too high'
			return None
		if Globals.SETTINGS.Inline and Globals.SETTINGS.EnableRecommendedSignals and not dryrun:
			if abs( imported_temperature - current_temperature ) > Globals.SETTINGS.TemperatureWarningLimit:
				Globals.CONTROL_INSTANCE.send_signal( Communicate.SIGNAL_CONTROL_PHOTOGRAMMETRY_RECOMMENDED )

		if Globals.SETTINGS.PhotogrammetryMaxImportCount > 0 and not dryrun:
			if Globals.SETTINGS.PhotogrammetryComprehensive:
				self.imported_count[Globals.SETTINGS.CurrentComprehensiveXML] = self.imported_count.get( Globals.SETTINGS.CurrentComprehensiveXML, 0 ) + 1
			elif Globals.SETTINGS.PhotogrammetryIndependent:
				self.imported_count['IndependentPhotogrammetry'] = self.imported_count.get( 'IndependentPhotogrammetry', 0 ) + 1
			else:
				self.imported_count[Globals.SETTINGS.CurrentTemplate] = self.imported_count.get( Globals.SETTINGS.CurrentTemplate, 0 ) + 1

		return latest_file[1]

	def import_photogrammetry( self, measure_series, dryrun=False, forced_refxml='' ):
		'''
		if set imports photogrammetry if one exists of today.
		compares also old measurement temperature with current.
		- "dryrun" only simulates operations, see return value below.
		- "forced_refxml": mutual exclusive to dryrun, omit searching for usable refxml file,
				caller provides fixed refxml file.
		returns True, if a photogrammetry has been loaded
										False, otherwise
		- "dryrun"-mode:
		returns refxml filename, which would be loaded as photogrammetry
										False, otherwise
		'''
		dryrun_info = {}
		try:
			if Globals.SETTINGS.OrderByMSetups and not forced_refxml:
				return False
			if Globals.SETTINGS.PhotogrammetryComprehensive:
				# None (never run) or different template
				if Globals.SETTINGS.CurrentComprehensiveXML != Globals.SETTINGS.CurrentTemplate:
					if Globals.SETTINGS.PhotogrammetryForceOnTemplateSwitch:  # if set force photogrammetry
						if not dryrun:
							self.log.debug( 'different photogrammetry template force new' )
							Globals.SETTINGS.CurrentComprehensiveXML = Globals.SETTINGS.CurrentTemplate
						return False
				# always set comprehensive to current template
				if dryrun:
					dryrun_info['Comprehensive'] = Globals.SETTINGS.CurrentComprehensiveXML
				Globals.SETTINGS.CurrentComprehensiveXML = Globals.SETTINGS.CurrentTemplate
	
			error_log = ErrorLog()
			if not forced_refxml and not self.can_import_refxml( error_log ):
				return False

			if not forced_refxml:
				filename = self.find_external_refxml( error_log, dryrun )
				if filename is None:  # no file found, ot temperature/date does not match
					return False
				if dryrun:
					return filename
			else:
				filename = forced_refxml
		finally:
			# dryrun value restoration
			if 'Comprehensive' in dryrun_info:
				Globals.SETTINGS.CurrentComprehensiveXML = dryrun_info['Comprehensive']

		self.log.info( 'importing reference points {}'.format( filename ) )
		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_max_steps()
			self.parent.Dialog.processbar_step()

		# import photogrammetry
		if not gom.app.project.is_part_project:
			atos_master = None
			for m in Utils.real_measurement_series(
					filter='type=="atos_measurement_series" and transformation_mode=="depends on other"' ):
				try:
					if m.get( 'reference_points_master_series' ) == measure_series:
						gom.script.atos.use_external_reference_points (
							file = filename,
							gsi_file_unit = 'mm',
							load_ascii_as_gsi = False,
							measurement_series = m )
						atos_master = m
						break
				except Exception as e:
					self.log.error( 'failed to import reference points for ms {} : {}'.format( m, e ) )
					return False

			# import only once and make all other atos series dependend
			if atos_master is not None:
				try:
					for m in Utils.real_measurement_series(
							filter='type=="atos_measurement_series" and transformation_mode=="depends on other"' ):
						if m.name != atos_master.name and m.get( 'reference_points_master_series' ) == measure_series:
							gom.script.atos.edit_measurement_series_dependency (
								master_series=atos_master,
								measurement_series=[m])
				except Exception as e:
					self.log.error( 'failed to set measurement series dependency ms {} to ms {} : {}'.format(
						m, atos_master, e ) )
					return False

			for m in Utils.real_measurement_series(
						filter='type=="photogrammetry_measurement_series" and transformation_mode=="depends on other"' ):
				try:
					if m.get( 'reference_points_master_series' ) == measure_series:
						gom.script.cad.delete_element( elements = m )
				except Exception as e:
					self.log.error( 'failed to delete dependend measurement series {}: {}'.format( m.name, e ) )
			try:
				gom.script.cad.delete_element( elements = measure_series )
			except Exception as e:
				self.log.error( 'failed to delete "master" measurement series {}: {}'.format( measure_series.name, e ) )
		else: # part based workflow
			try:
				gom.script.atos.use_external_reference_points (
					file=filename, 
					gsi_file_unit='mm', 
					load_ascii_as_gsi=False)
			except Exception as e:
				self.log.error( 'failed to import reference points from {}: {}'.format( filename, e ) )
				return False

			# if available, load refpoint size data
			try:
				sfilename = self.filename_refpoint_sizes_data( filename )
				with open( sfilename, 'r', encoding='utf-8' ) as f:
					transferred_refpoint_sizes = json.load( f )

				self.apply_refpoint_sizes_data( transferred_refpoint_sizes )
				self.log.info( 'Applied reference point size data from {}'.format( sfilename ) )
			except:
				pass

			try:
				refpoint_master = None
				for m in gom.app.project.measurement_series:
					if m.type not in ['atos_measurement_series', 'photogrammetry_measurement_series']:
						continue
					if m.reference_points_master_series is None:
						refpoint_master = m
				gom.script.sys.recalculate_elements( elements=[refpoint_master] )
			except Exception as e:
				self.log.error( 'Recalc of photogrammetry failed: {}'.format( e ) )

			try:
				series = gom.app.project.measurement_position_series.filter('type == "atos_measurement_position_series"')
				gom.script.sys.recalculate_elements( elements = series )
			except Exception as e:
				self.log.error( 'Recalc of atos path elements failed: {}'.format( e ) )

		# dont count in the case of comprehensive photogrammetry the import if no atos ms is found
		if Globals.SETTINGS.PhotogrammetryComprehensive:
			if not len( Utils.real_measurement_series(
					filter='type=="atos_measurement_series" and transformation_mode=="depends on other"' ) ):
				self.imported_count[Globals.SETTINGS.CurrentComprehensiveXML] = self.imported_count.get( Globals.SETTINGS.CurrentComprehensiveXML, 1 ) - 1

		return True

	def export_photogrammetry( self, measure_series, temperature=None ):
		'''
		if set exports current photogrammetry
		'''
		if Globals.SETTINGS.OrderByMSetups:
			return None
		if not Globals.SETTINGS.PhotogrammetryOnlyIfRequired and not Globals.SETTINGS.PhotogrammetryComprehensive:
			return None
		if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActive():
			return None

		if temperature is None:
			# reinit sensor if needed
			if not self.parent.Sensor.check_for_reinitialize():
				return None
			temperature = self.parent.Thermometer.get_temperature()

		path = os.path.join( Globals.SETTINGS.SavePath, Globals.SETTINGS.PhotogrammetrySavePath )
		if not os.path.exists( path ):
			os.mkdir( path )

		template_name = Globals.SETTINGS.CurrentTemplate.replace( chr( 0x7 ), '_@_' )[:-len( '.project_template' )]
		if Globals.SETTINGS.PhotogrammetryComprehensive:
			Globals.SETTINGS.CurrentComprehensiveXML = Globals.SETTINGS.CurrentTemplate
			template_name = 'ComprehensivePhotogrammetry{}'.format( template_name )
		elif Globals.SETTINGS.PhotogrammetryIndependent:
			template_name = 'IndependentPhotogrammetry'

		filename = os.path.join( path, '{}_C{}.xmlref'.format( template_name, temperature ) )

		self.log.debug( 'export refxml: {}'.format( filename ) )
		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_max_steps()
			self.parent.Dialog.processbar_step()
		
		gom.script.cad.show_element (elements=[measure_series.results['points']])

		if not Globals.SETTINGS.PhotogrammetryExportAdapters:
			points = measure_series.results['points']
			if self.parent.Dialog is not None:
				self.parent.Dialog.processbar_max_steps()
			select_points = []
			for i in range( points.get ( 'num_points' ) ):
				point_type = points.get( 'point_type[{}]'.format( i ) )
				if point_type.find( 'adapter' ) < 0:
					coordinate = points.get( 'coordinate[{}]'.format( i ) )
					normal = points.get( 'normal[{}]'.format( i ) )
					p_id = -1
					p_type = 'uncoded'
					if point_type.find( 'uncoded' ) < 0:
						p_id = points.get( 'point_id[{}]'.format( i ) )
						p_type = 'coded'

					select_points.append( {'coordinates': coordinate,
						'id': p_id,
						'normal': normal,
						'target': gom.app.project.actual_elements['all_reference_points'],
						'type': p_type} )
			if len( select_points ):
				gom.script.selection3d.select_reference_points (
					points = select_points )
				if self.parent.Dialog is not None:
					self.parent.Dialog.processbar_step()
			gom.script.sys.export_reference_points_xml (
						elements = [measure_series.results['points']],
						file = filename,
						only_selected_points = True )
		else:
			gom.script.sys.export_reference_points_xml (
				elements = [measure_series.results['points']],
				file = filename,
				only_selected_points = False )

		# in automatic detection mode: write refpoint size info
		if gom.app.project.is_part_project and self.save_refpoint_sizes_data():
			sizes_data = self.refpoint_sizes_data()
			sfilename = self.filename_refpoint_sizes_data( filename )
			with open( sfilename, 'w', encoding='utf-8' ) as f:
				json.dump( sizes_data, f, indent=2 )

		# got exported -> set counter to zero
		if Globals.SETTINGS.PhotogrammetryMaxImportCount > 0:
			if Globals.SETTINGS.PhotogrammetryComprehensive:
				self.imported_count[Globals.SETTINGS.CurrentComprehensiveXML] = 0
				self.log.debug( 'setting import count to 0 {}'.format( Globals.SETTINGS.CurrentComprehensiveXML ) )
			elif Globals.SETTINGS.PhotogrammetryIndependent:
				self.imported_count['IndependentPhotogrammetry'] = 0
			else:
				self.imported_count[Globals.SETTINGS.CurrentTemplate] = 0

		return filename


class MeasureAtos( Utils.GenericLogClass ):
	'''
	This class contains the functionality for the Atos measurement.
	'''
	parent = None

	def __init__( self, logger, parent ):
		'''
		Constructor function to init logging, calibration and dialog
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.skipped_measurements = []
		self.single_measurements_left = []


	def execute_active_measurement_series( self, clear_measurement_data = False ):
		'''
		Hook function to add more functionality around executing a measurement series
		'''
		if Globals.SETTINGS.InAsyncAbort:
			Globals.SETTINGS.InAsyncAbort = False
			raise gom.BreakError
		try:
			Globals.SETTINGS.AllowAsyncAbort = True
			self.parent.position_information.start_measurement_list()
			if gom.app.project.is_part_project and Globals.SETTINGS.OfflineMode:
				if self.parent.IsVMRlight:
					# cannot even move. just do some logs for some time
					for i in range(4):
						self.log.debug( 'Measuring...' )
						gom.script.sys.delay_script( time=5 )
				else:
					# just move. new mmt concept does not allow keeping measurement data
					active_ms = Utils.real_measurement_series( filter='is_active==True' )
					gom.script.automation.forward_move_to_position(
						measurement=gom.app.project.measurement_paths[active_ms[0].name].path_positions[-1] )
			else:
				if Globals.SETTINGS.Inline:
					cmd=gom.script.automation.execute_active_measurement_series
				else:
					cmd=gom.interactive.automation.execute_active_measurement_series
				if clear_measurement_data:
					gom.script.automation.clear_measuring_data ( measurements = [gom.app.project.measurement_series.filter( 'is_active==True' )[0]] )
					cmd()
				else:
					cmd(direct_movement = isDirectMoveAllowed(gom.app.project.measurement_series.filter( 'is_active==True' )[0]))
		finally:
			Globals.SETTINGS.AllowAsyncAbort = False
			self.parent.position_information.end_measurement_list()
		return True

	def execute_robot_program( self, robot_program_id, path_ext ):
		'''
		Hook function to add more functionality around executing a measurement series
		'''
		if Globals.SETTINGS.InAsyncAbort:
			Globals.SETTINGS.InAsyncAbort = False
			raise gom.BreakError
		try:
			Globals.SETTINGS.AllowAsyncAbort = True
			if Globals.SETTINGS.OfflineMode:
				# Just do some logs
				for i in range(50):
					self.log.debug( 'Fake execution of robot program {}'.format( robot_program_id ) )
					gom.script.sys.delay_script( time=1.0 )
			else:
				if path_ext is not None:
					save_folder = os.path.join( Globals.DRC_EXTENSION.getExternalSavePath(), path_ext )
				else:
					save_folder = None

				self.log.debug( 'gom.script.automation.execute_measurement({},{},{})'.format(
					save_folder, robot_program_id, False ) )
				if save_folder is not None:
					gom.script.automation.execute_measurement(
						save_measurement_data_folder=save_folder,
						program_id=int( robot_program_id ),
						check_robot_position=False )
				else:
					gom.script.automation.execute_measurement(
						program_id=int( robot_program_id ),
						check_robot_position=False )
		finally:
			Globals.SETTINGS.AllowAsyncAbort = False
		return True

	def perform_single_measurements( self, single_measurements=None ):
		if single_measurements is None:
			single_measurements = []
		if Globals.SETTINGS.InAsyncAbort:
			Globals.SETTINGS.InAsyncAbort = False
			raise gom.BreakError
		measurements = []
		if not len(single_measurements):
			for m in self.single_measurements_left:
				if not m.get('computation_basis=="real_data"'):
					measurements.append(m)
		else:
			measurements = single_measurements
		save_folder = ''
		if Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
			save_folder = Globals.DRC_EXTENSION.getExternalSavePath()
		try:
			Globals.SETTINGS.AllowAsyncAbort = True
			self.parent.position_information.start_measurement_list()
			direct_move = isDirectMoveAllowed( Utils.real_measurement_series( filter='is_active==True' )[0] )
			if Globals.SETTINGS.Inline:
				gom.script.automation.measure_at_selected_positions(
					measurements=measurements, save_measurement_data_folder=save_folder, direct_movement=direct_move )
			else:
				gom.interactive.automation.measure_at_selected_positions(
					measurements=measurements, save_measurement_data_folder=save_folder, direct_movement=direct_move )
		finally:
			Globals.SETTINGS.AllowAsyncAbort = False
			self.parent.position_information.end_measurement_list()
		return True


	def collect_single_measurements(self, measure_series, single_measurements):
		current_position = measure_series.measurements.filter ('is_current_position==True')
		if not len(current_position):
			return False
		current_position = current_position[0]
		self.skipped_measurements.append(current_position)
		all_scans = measure_series.measurements.filter('type == "scan" and index_in_path<={}'.format(current_position.index_in_path))
		count = 0
		index = -1
		for i in range(len(all_scans)-1, -1, -1):
			try:
				if all_scans[i].name == self.skipped_measurements[index].name:
					count +=1
					index -=1
				else:
					break
			except:
				pass

		if count <= 2: # Hardcoded limit
			self.single_measurements_left = measure_series.measurements.filter('index_in_path>{}'.format(current_position.index_in_path))
			while len(single_measurements):
				if single_measurements[0].index_in_path<=current_position.index_in_path:
					del single_measurements[0]
				else:
					break
				
			self.parent.position_information.set_continue_mlist()
			self.log.warning('skipping measurement {} due to intersection error, switching to measure at position'.format(current_position.name))
			return True # no loop counting

		self.log.warning('Intersection error occured in {} measurements perform calibration, switching back to execute mlist'.format(count))
		self.single_measurements_left = []
		self.skipped_measurements = []
		return False

	def perform_measurement( self, measure_series, single_measurements=None, reverse_only=False, unknown_fixture=False ):
		'''
		perform and analyze digitize measurement series
		'''
		if single_measurements is None:
			single_measurements = []
		if isinstance( measure_series, str ):
			if len( measure_series ) == 0:  # no list definied
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_ERROR, '',
															Globals.LOCALIZATION.msg_digitizing_no_list_defined)
					return DigitizeResult.Failure
				Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
										Globals.LOCALIZATION.msg_digitizing_no_list_defined,
											Globals.SETTINGS.SavePath, False )
				return DigitizeResult.Failure
			measure_series = gom.app.project.measurement_series[measure_series]

		measureloop = 0
		already_calibrated = False
		already_calibrated_temp = False

		self.log.info( 'starting atos measurement "{}"'.format( str( measure_series ) ) )

		self.skipped_measurements = []
		self.single_measurements_left = []

		if not Globals.SETTINGS.OfflineMode:  # clear measuring data only once
			if not Globals.FEATURE_SET.DRC_ONESHOT and not len(single_measurements):
				gom.script.automation.clear_measuring_data ( measurements = measure_series )
			elif len(single_measurements): # MultiRobot case
				gom.script.automation.clear_measuring_data ( measurements = single_measurements )

		errorlog = ErrorLog()
		mmp_show_setup_dialog = True
		# retry count as definied in settings
		while measureloop < Globals.SETTINGS.MaxDigitizeRepetition:
			del errorlog.Error  # clean errorlog
			self.log.info( 'retry no. {}'.format( measureloop ) )
			if self.parent.Dialog is not None:
				self.parent.Dialog.process_msg_detail( Globals.LOCALIZATION.msg_evaluate_detail_msg_digitizing )
				self.parent.Dialog.process_image( Globals.SETTINGS.DigitizeImageBinary )
				self.parent.Dialog.processbar_max_steps( 2 )
				self.parent.Dialog.processbar_step( 0 )

			# Reinit sensor if needed and check warmup time
			if not self.parent.Sensor.check_for_reinitialize():
				return DigitizeResult.Failure

			# Define active mseries will implicitly also define active msetup and optionally show msetup instructions
			state = VerificationState.ErrorFree
			if not self.parent.define_active_measuring_series( measure_series ):
				return DigitizeResult.Failure

			self.parent.Global_Checks.reset_last_error()

			# Additional positioning / deletion dialog for manual multipart templates
			if Globals.SETTINGS.ManualMultiPartMode and mmp_show_setup_dialog:
				mmp_show_setup_dialog = False
				try:
					# view for reference point setup
					gom.script.view.set_tab_visible( view='camera', visible=True )
					gom.script.view.toggle_live_image_mapping( enable=True )
					gom.script.view.set_tab_visible( view='left_docking_area', visible=False )
					gom.script.view.set_tab_visible( view='right_docking_area', visible=False )
	
					if not Globals.DIALOGS.show_refpoint_setup_dialog():
						# Dialog cancelled
						return DigitizeResult.Failure
				except Exception as e:
					self.log.warning( 'View setup for refpoint detection failed: {}'.format( e ) )
					# Give the user the chance to continue on his own

				try:
					gom.interactive.atos.position_parts_with_assistance_draft()
				except Exception as e:
					self.log.error( 'Positioning of parts for {} failed: {}'.format(
						measure_series.name, e ) )
					return DigitizeResult.Failure

				# Check, if any parts are left for evaluation
				if len( Utils.multi_part_evaluation_parts() ) < 1:
					# No parts left
					self.log.warning( 'No parts left for measuring after part positioning' )
					return DigitizeResult.Failure

			online_error = False
			try:
				if len(self.single_measurements_left) or len( single_measurements ):
						if not self.perform_single_measurements(single_measurements):
							return DigitizeResult.Failure
				elif not self.execute_active_measurement_series( False ):
					return DigitizeResult.Failure
			except Globals.EXIT_EXCEPTIONS:
				raise
			except Exception as error:  # something happend (acquisition check abort, or eg sensor loss)
				self.log.error( 'Failed to execute Measurement series\n' + (str( error ) if not isinstance(error, gom.BreakError) else 'BreakError'))
				state = self.parent.Global_Checks.analyze_error( error, measure_series, measureloop < Globals.SETTINGS.MaxDigitizeRepetition - 1, errorlog )
				self.log.debug( 'VerificationState after analyze error: {}'.format( state ) )
				online_error = True

			self.log.debug( 'VerificationState after measurement series execute: {}'.format( state ) )
			if state == VerificationState.ErrorFree:  # no error happend, analyze series
				if self.parent.Dialog is not None:
					self.parent.Dialog.processbar_step()
				safety_move_to_home( self, measure_series, reverse=reverse_only )
				if not len(single_measurements): # not possible in MultiRobot Mode
					state = self.parent.Global_Checks.checkdigitizing( measure_series, measureloop < Globals.SETTINGS.MaxDigitizeRepetition - 1, errorlog )
					self.log.debug( 'VerificationState after series check: {}'.format( state ) )

			if state == VerificationState.ErrorFree:
				return DigitizeResult.Success
			elif state in [VerificationState.NeedsCalibration, VerificationState.TemperatureForcesCalibration]:
				if Globals.SETTINGS.ManualMultiPartMode:
					mmp_show_setup_dialog = True
					gom.script.automation.clear_measuring_data( measurements=measure_series )

				if state == VerificationState.NeedsCalibration and Globals.SETTINGS.HigherFaultTolerance:
					if online_error and self.collect_single_measurements(measure_series, single_measurements):
						self.parent.position_information.set_continue_mlist()
						continue # no loop counting
				self.skipped_measurements = []
				self.single_measurements_left = []

				# Never allow a second calibration triggered by same cause (intersection/temperature)
				# Only case allowed: 1st intersection error, 2nd temperature error
				if (( already_calibrated and state == VerificationState.NeedsCalibration )
					or ( already_calibrated_temp and state == VerificationState.TemperatureForcesCalibration )):
					self.log.error( 'already calibrated ' + ( '(temperature)' if already_calibrated_temp else '' ) + 'in this loop' )
					if Globals.SETTINGS.Inline:
						InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_CALIBRATION_COUNT,errorlog.Code,errorlog.Error)
					else:
						Globals.DIALOGS.show_errormsg(
							Globals.LOCALIZATION.msg_general_failure_title,
							Globals.LOCALIZATION.msg_digitizing_failed_already_calibrated + '<br/>' + errorlog.Error,
							Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
					safety_move_to_home( self, measure_series, reverse=reverse_only )
					return DigitizeResult.Failure

				if state == VerificationState.TemperatureForcesCalibration:
					already_calibrated_temp = True
					measureloop -= 1  # add one retry
				already_calibrated = True
				safety_move_to_home( self, measure_series, reverse=reverse_only )

				if unknown_fixture:
					# warning dialog and user response
					res = self.calibration_with_unknown_fixture_pos()
					if res is False:
						self.log.error( 'Calibration with unknown fixture position - user choice: Abort' )
						return DigitizeResult.Failure
					elif res is None:
						self.log.error( 'Calibration with unknown fixture position - user choice: Unknown Fixture in cell' )
					elif res is True:
						self.log.error( 'Calibration with unknown fixture position - user choice: Cell is empty' )
					else:
						self.log.error( 'Calibration with unknown fixture position - user choice: ???' )
						return DigitizeResult.Failure

				if state == VerificationState.TemperatureForcesCalibration and self.parent.HyperScale.MeasureList is not None:
					if not self.parent.HyperScale.calibrate('temperature'):
						return DigitizeResult.Failure
				else:
					if not self.parent.Calibration.calibrate(
						'temperature' if state == VerificationState.TemperatureForcesCalibration else '' ):
						return DigitizeResult.Failure
			elif state == VerificationState.Failure:
				# error detected where no calibration can help, but user can select retry which may help
				if Globals.SETTINGS.Inline:
					self.log.info( 'Verification Failure exiting' )
					safety_move_to_home( self, measure_series, reverse=reverse_only )
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_ATOS_VERIFICATION,errorlog.Code,errorlog.Error)
				elif errorlog.Error:
					if Globals.DIALOGS.show_errormsg(
						Globals.LOCALIZATION.msg_general_failure_title,
						errorlog.Error,
						Globals.SETTINGS.SavePath, True, error_code = errorlog.Code ):
						self.log.info( 'Verification Failure - user selected retry' )
						self.parent.position_information.set_continue_mlist()
						continue # no loop counting
					else:
						self.log.info( 'Verification Failure - user abort' )
				safety_move_to_home( self, measure_series, reverse=reverse_only )
				return DigitizeResult.Failure
			elif state == VerificationState.ReInitSensor:
				self.log.info( 'Reinitializing Sensor' )
				if not self.parent.Sensor.reinitialize():
					self.log.error( 'failed to reinitialize sensor exiting' )
					return DigitizeResult.Failure
			elif state == VerificationState.OnlyInitSensor:
				self.log.info( 'Initializing Sensor' )
				if not self.parent.Sensor.initialize():
					self.log.error( 'failed to initialize sensor exiting' )
					return DigitizeResult.Failure
			elif state == VerificationState.Abort:
				# eg emergency exit or temperature/trafo error in checkdigitizing
				self.log.info( 'Verification abort exiting' )
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_ABORT, errorlog.Code, errorlog.Error)
				elif errorlog.Error:
					Globals.DIALOGS.show_errormsg(
						Globals.LOCALIZATION.msg_general_failure_title,
						errorlog.Error,
						Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
				return DigitizeResult.Failure
			elif state == VerificationState.UserAbort:
				self.log.info( 'Failed to execute Measurement series\nDue to break error' )
				safety_move_to_home( self, measure_series, reverse=reverse_only )
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_USERABORT,'','')
				return DigitizeResult.Failure
			elif state == VerificationState.Retry:
				self.skipped_measurements = []
				self.single_measurements_left = []
			elif state == VerificationState.RetryWithoutCounting:
				measureloop -= 1
				self.parent.position_information.set_continue_mlist()
			elif state == VerificationState.MoveReverseHome:
				safety_move_to_home( self, measure_series, reverse=True )
				return DigitizeResult.Failure

			measureloop += 1

		self.log.error( 'max repetitions are over' )
		if Globals.SETTINGS.Inline:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_RETRY, errorlog.Code,
													Globals.LOCALIZATION.msg_digitizing_failed_maxrepetitions + '\n' + errorlog.Error)
		else:
			Globals.DIALOGS.show_errormsg(
					Globals.LOCALIZATION.msg_general_failure_title,
					Globals.LOCALIZATION.msg_digitizing_failed_maxrepetitions + '<br/>' + errorlog.Error,
					Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
		return DigitizeResult.Failure


	def perform_robot_program( self, robot_program_id, path_ext, errorlog=None ):
		'''
		perform and analyze measurement execution by robot_program_id
		'''
		self.log.info( 'Starting measurements by robot program id "{}"'.format( robot_program_id ) )

		state = VerificationState.ErrorFree
		try:
			if not self.execute_robot_program( robot_program_id, path_ext ):
				# Can never happen, see execute-function
				return DigitizeResult.Failure
		except Globals.EXIT_EXCEPTIONS:
			raise
		except Exception as error:  # something happend (acquisition check abort, or eg sensor loss)
			msg = ('Failed to execute Measurement series\n'
				+ ( str( error ) if not isinstance(error, gom.BreakError) else 'BreakError' ) )
			if errorlog: errorlog.Error = msg
			state = VerificationState.Failure

		self.log.debug( 'VerificationState after measurement series execute: {}'.format( state ) )

		# Re-init sensor / automation controller if needed
		if not Globals.SETTINGS.OfflineMode:
			if not self.parent.Sensor.is_initialized():
				if not self.parent.Sensor.initialize():
					if errorlog: errorlog.Error = 'Failed to initialize sensor - exiting'
					return DigitizeResult.Failure

		if state == VerificationState.ErrorFree:
			return DigitizeResult.Success

		# Errors are returned via the 'errorlog'
		return DigitizeResult.Failure


	def calibration_with_unknown_fixture_pos( self ):
		'''Warning dialog and user response
					for the special case where a calibration is necessary
					before CheckFixturePosition could finish.
					Results:
					False - user chose "Abort" or aborted the dialog
											None  - user confirms calibration with unknown fixture in cell
											True  - user confirms cell is empty
		'''
		res = Globals.DIALOGS.show_fixcheck_calib_decision(
			Globals.LOCALIZATION.dialog_FC_Calib_title,
			Globals.LOCALIZATION.dialog_FC_Calib_msg )

		return res


class Sensor( Utils.GenericLogClass ):
	'''
	This class contains the functionality of the sensor.
	'''
	parent = None

	def __init__( self, logger, parent ):
		'''
		Initialize function
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.needs_reference_position = True
		# IsVMRlight not yet available for check in initializer, hasVMR is next best
		if self.parent.hasVMR:
			self.needs_reference_position = False
		self.warning_shown = False
		self.temp_disable_warmup = False

	def initialize( self ):
		'''
		Initialize sensor and wait for sensor warm-up.

		Returns:
		True  - if the sensor has been initialized successfully.
		False - otherwise
		'''
		if Globals.SETTINGS.OfflineMode:
			return True
		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_max_steps()
			self.parent.Dialog.processbar_step()
		retry = True
		num_retries = 0
		self.log.info( 'starting initializing sensor' )
		while retry:
			try:
				self.log.info( 'initializing sensor' )
				with warnings.catch_warnings( record = True ) as w:
					warnings.simplefilter( "always" )  # grep all warnings
					gom.script.sys.initialize_server( mode='init', move_to_reference_position=self.needs_reference_position )
					if len( w ):
						self.log.warning( 'sensor warning: {}'.format( '\n'.join( str( _.message ) for _ in w ) ) )
						if not self.warning_shown or Globals.SETTINGS.Inline:  # show the warning only once
							self.warning_shown = True
							if Globals.SETTINGS.Inline:
								InlineConstants.sendMeasureInstanceWarning(InlineConstants.PLCWarnings.SENSOR_INIT_WARNING, '',
															Globals.LOCALIZATION.msg_sensor_warning.format( ' '.join( ( str( _.message ) for _ in w ) ) ).replace('<br/>',' '))
							else:
								if not Globals.DIALOGS.show_errormsg(
										Globals.LOCALIZATION.msg_general_failure_title,
										Globals.LOCALIZATION.msg_sensor_warning.format( '<br/>'.join( ( str( _.message ) for _ in w ) ) ),
										Globals.SETTINGS.SavePath, True, Globals.LOCALIZATION.errordialog_button_continue ):
									return False
					elif Globals.SETTINGS.Inline: # reset last warning
						InlineConstants.resetMeasuringInstanceWarning(InlineConstants.PLCWarnings.SENSOR_INIT_WARNING)

				self.needs_reference_position = False
				retry = False
			except Globals.EXIT_EXCEPTIONS:
				raise
			except Exception as error:
				self.log.exception( 'Failed to initialize sensor' + '\n' + str( error ) )
				num_retries += 1
				if num_retries > 1 or error.args[0] == 'GAPP-0001' or error.args[0] == 'MOVE-0300':
					if Globals.SETTINGS.Inline:
						InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_INIT_SENSOR, error.args[0], error.args[1])
						return False
					retry = Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_sensor_failed_init, '\n'.join(error.args),
														sic_path = Globals.SETTINGS.SavePath, retry_enabled = True,
														error_code = error.args[0] )
					self.log.error( 'number of retries exceeded user decision to retry={}'.format( retry ) )
					if not retry:
						return False
				if ( error.args[0] in ['MATOS-S003', 'FG-0004', 'FG-0010'] ):  # known error chance to fix if waiting ~5s
					if self.parent.Dialog is not None:
						self.parent.Dialog.processbar_max_steps()
						self.parent.Dialog.processbar_step()
					gom.script.sys.delay_script( time = 5 )
				if self.parent.Dialog is not None:
					self.parent.Dialog.processbar_max_steps()
					self.parent.Dialog.processbar_step()
		# special handling for ATOS 5X, due to safety the light could be off after initalization
		try:
			gom.script.atos.switch_projector_light (enable=True)
		except:
			pass
		if Globals.SETTINGS.WaitForSensorWarmUp:
			return self.warmup()
		else:
			try:
				gom.script.atos.ignore_sensor_warmup_time ()
			except RuntimeError as error:
				self.log.error( 'failed to set ignore warmup time: {}'.format( error ) )
		return True

	def deinitialize( self ):
		'''
		Deinitialize sensor
		'''
		if Globals.SETTINGS.OfflineMode:
			return
		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_max_steps()
			self.parent.Dialog.processbar_step()
		try:
			self.log.info( 'deinitialize sensor' )
			gom.script.sys.initialize_server( mode = 'deinit' )
		except Globals.EXIT_EXCEPTIONS:
			raise
		except Exception as error:
			self.log.info( 'deinit failed: {}'.format( str( error ) ) )


	def _warmup( self, timeout ):
		'''
		internal function to wait for sensor warmup with given timeout
		on failure it retries two times
		@return: remaining warmuptime in seconds, None on failure
		'''
		num_retries = 0
		retry = True
		result = None
		while retry:
			try:
				result = gom.script.atos.wait_for_sensor_warmup ( timeout = timeout )
				retry = False
			except Globals.EXIT_EXCEPTIONS:
				raise
			except gom.BreakError:
				retry = False
				result = None
			except Exception as error:
				self.log.exception( 'failed: {}' + str( error ) )
				num_retries += 1
				if num_retries > 1:
					if Globals.SETTINGS.Inline:
						InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_INIT_SENSOR, error.args[0], error.args[1])
						return None
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_sensor_failed_warmup, '\n'.join(error.args),
												sic_path = Globals.SETTINGS.SavePath, retry_enabled = False,
												error_code = error.args[0] )
					self.log.error( 'number of retries exceeded' )
					return None
				if error.args[0] in ['MATOS-S022', 'FG-0004', 'FG-0010']:
					self.initialize()
				result = None
		return result

	def warmup( self ):
		'''
		Waits until sensor is warmed up. On errors it tries to wait for the sensor two times.

		Returns:
		True  - if the sensor has warmed up
		False - If both warm-up attempts failed.
		'''
		if Globals.SETTINGS.OfflineMode or self.temp_disable_warmup:
			return True

		self.log.info( 'starting wait for sensor warmup' )
		if Globals.SETTINGS.Inline:
			remaining = self._warmup( 1 )
			if remaining is not None and remaining > 0:
				InlineConstants.sendMeasureInstanceWarning(InlineConstants.PLCWarnings.SENSOR_WARMUP, '', 'Sensor Warmup Time not reached')

		try:
			remaining = self._warmup( 0 )

			if remaining is None:  # error happend
				return False
			if not remaining:  # no warmuptime remaining
				return True

			while remaining:
				remaining = self._warmup( remaining )

			if remaining is None:  # error happend
				return False
			return True
		finally:
			if Globals.SETTINGS.Inline:
				InlineConstants.resetMeasuringInstanceWarning(InlineConstants.PLCWarnings.SENSOR_WARMUP)

	def reinitialize( self ):
		'''
		Function to safety reinitialize sensor, first deinitialize and after 5s initializes again
		'''
		self.deinitialize()
		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_max_steps()
			self.parent.Dialog.processbar_step()
		gom.script.sys.delay_script( time = 5 )
		if self.parent.IsVMRlight:
			self.needs_reference_position = True
		return self.initialize()

	def is_initialized( self ):
		'''
		safe check for initialization status
		returns True if sensor and automation controller are initialized, False otherwise
		'''
		try:
			auto_controller_state = gom.app.sys_is_automation_controller_initialized
		except:
			auto_controller_state = False
		try:
			sensor_state = gom.app.sys_is_sensor_initialized
		except:
			sensor_state = False
		return auto_controller_state and sensor_state

	def check_for_reinitialize( self ):
		'''
		check if sensor needs initialization
		if not checks warmup time if set
		returns True on success, False otherwise
		'''
		res = True
		if not Globals.SETTINGS.OfflineMode:
			if not self.is_initialized() or self.needs_reference_position:
				self.log.error( 'Sensor is deinitialized' )
				if self.needs_reference_position:
					if not self.reinitialize():
						self.log.error( 'failed to reinitialize sensor exiting' )
						return False
				else:
					if not self.initialize():
						self.log.error( 'failed to initialize sensor exiting' )
						return False
			else:
				if Globals.SETTINGS.WaitForSensorWarmUp:
					res = self.warmup()
			# special handling for ATOS 5X, due to safety the light could be off after initalization
			try:
				gom.script.atos.switch_projector_light (enable=True)
			except:
				pass
		return res

	def check_system_configuration ( self ):
		'''
		check if the operating system is correctly configured
		returns True on success, False otherwise
		'''
		if Globals.SETTINGS.OfflineMode:
			return True
		try:
			result = gom.script.sys.check_system_configuration ()
			if not len( result ):
				return True

			self.log.error( 'System configuration: {}'.format( result ) )
			errordetail = []
			for _key, value in result.items():
				if 'abstract' in value:
					errordetail.append( '- ' + value['abstract'] )
			if Globals.SETTINGS.Inline:
				InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_SYSTEM_CONFIG, '', '\n'.join( errordetail ))
				return False
			return Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_system_configuration_failed_title,
										'<br/>'.join( errordetail ),
										Globals.SETTINGS.SavePath,
										True, Globals.LOCALIZATION.errordialog_button_continue )

		except RuntimeError as e:
			if Globals.SETTINGS.Inline:
				InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_SYSTEM_CONFIG, e.args[0], e.args[1])
				return False
			return Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_system_configuration_failed_title,
										'\n'.join(e.args),
										Globals.SETTINGS.SavePath,
										True, Globals.LOCALIZATION.errordialog_button_continue )


	def get_sensor_information( self ):
		'''
		collect connected sensor information
		returns tuple of sensor name and sensor serialnumber
		'''
		if not self.is_initialized():
			if not self.initialize():
				self.log.error( 'failed to initialize sensor exiting' )
				return None
		try:
			name = '{} {}'.format( gom.app.get ('sys_sensor_configuration.name'), gom.app.get ('sys_sensor_configuration.scan_measuring_volume.name') )
			id = gom.app.get ( 'sys_sensor_identifier' )
			if id is None:
				id = 'Unknown'
			return name, id
		except Exception as _e:
			return 'Unknown', 'Unknown'

	def getRealHardware(self):
		real_sensor_name = gom.app.get ('sys_sensor_configuration.name')
		real_sensor_distance = gom.app.get (
			'sys_sensor_configuration.camera_distance')
		real_sensor_atos_mv = gom.app.get (
			'sys_sensor_configuration.scan_measuring_volume.volume.width')
		real_sensor_tritop_mv = gom.app.get (
			'sys_sensor_configuration.photogrammetric_measuring_volume.volume.width')
		real_sensor_variant = gom.app.get (
			'sys_sensor_configuration.variant')
		return real_sensor_name, real_sensor_distance, real_sensor_atos_mv, real_sensor_tritop_mv, real_sensor_variant

	def logRealHardware(self):
		real_sensor_name, real_sensor_distance,	real_sensor_atos_mv, real_sensor_tritop_mv, real_sensor_variant = self.getRealHardware()
		self.log.info(
			'sensor cfg {}/{}/{}/{}/{}'.format(
				real_sensor_name,
				real_sensor_distance,
				real_sensor_atos_mv,
				real_sensor_tritop_mv,
				real_sensor_variant
			))
		self.log.info( 'connected controller {}'.format(self.getConnectedController()))

	def same_sensor(self, wcfg):
		# wcfg is both measuring setup or calibration series
		# Getting Demo-Mode working would be too complicated otherwise:
		if Globals.SETTINGS.OfflineMode:
			return True

		try:
			wcfg_sensor = wcfg.get ('sensor_configuration.key')
		except:
			wcfg_sensor = None
		if wcfg_sensor is None:
			return True
		real_sensor_name, real_sensor_distance,	real_sensor_atos_mv, real_sensor_tritop_mv, real_sensor_variant = self.getRealHardware()
		return (
			wcfg_sensor['sensor'] == real_sensor_name
			and wcfg_sensor['camera_distance'] == real_sensor_distance
			and wcfg_sensor['mv'] == real_sensor_atos_mv
			# and wcfg_sensor.get('photogrammetry_mv', None) == real_sensor_tritop_mv
			and wcfg_sensor.get('variant', 'default') == real_sensor_variant
			)

	def getConnectedController(self):
		try:
			return gom.app.get ('sys_automation_controller.name')
		except:
			return None

	def getConnectedControllerInfo(self):
		try:
			return (gom.app.get ('sys_automation_controller.driver'),
					gom.app.get ('sys_automation_controller.parameters'),
					gom.app.get ('sys_automation_controller.ip_address'),
					gom.app.get ('sys_automation_controller.serial_port'))
		except:
			return None,None,None,None

	def getWCfgSetting(self, wcfg):
		try:
			vmr = gom.app.project.virtual_measuring_room[0]
		except:
			return None,None
		try:
			wcfg_area = wcfg.get ('working_area')
		except:
			wcfg_area = None
		if wcfg_area is None:
			return None,None
		try:
			wcfg_sensor = wcfg.get ('sensor_configuration.key')
		except:
			return None,None
		for i in range(vmr.get ('number_of_working_areas')):
			if vmr.get ('working_area[{}].id'.format(i)) == wcfg_area.id:
				return vmr.get ('working_area[{}].controller.name'.format(i)), wcfg_sensor
		return None, wcfg_sensor

	def correct_controller(self, wcfg):
		real_ctrl_driver, real_ctrl_params, real_ctrl_ip, real_ctrl_serial = self.getConnectedControllerInfo()
		vmr = None
		try:
			vmr = gom.app.project.virtual_measuring_room[0]
		except:
			vmr = None

		if vmr is None and (wcfg is None or wcfg.get('working_area') is None): # vmrlight and no or vmrlight wcfg
			return True
		elif vmr is None: # vmrlight but non vmrlight wcfg
			return False

		wcfg_area = wcfg.get ('working_area')
		if wcfg_area is None: # vmrlight wcfg with vmr
			return False
		for i in range(vmr.get ('number_of_working_areas')):
			if (vmr.get ('working_area[{}].id'.format(i)) == wcfg_area.id
				and vmr.get ('working_area[{}].controller.driver'.format(i))      == real_ctrl_driver
				and vmr.get ('working_area[{}].controller.parameters'.format(i))  == real_ctrl_params
				and vmr.get ('working_area[{}].controller.ip_address'.format(i))  == real_ctrl_ip
				and vmr.get ('working_area[{}].controller.serial_port'.format(i)) == real_ctrl_serial):
				return True

		if vmr.get ('number_of_controllers') == 1 and (real_ctrl_driver is None or Globals.SETTINGS.OfflineMode): # controller undefined but only one controller (Offline)
			return True
		return False

	def isMListPartOfMeasuringSetups(self, mlist, wcfgs):
		if mlist.measuring_setup is None:
			for wcfg in gom.app.project.measuring_setups:
				if wcfg.working_area is not None: # non vmrlight wcfg
					return False
			return True
		else:
			if not len(gom.app.project.measuring_setups):
				return False
			return mlist.measuring_setup.name in wcfgs

	def calibration_ms_compatible(self, mseries, wcfgs):
		'''Check if mseries is compatible with a given set of compatible setups
					"mseries" is a calibration measurement series
					"wcfgs" is the list of compatible measuring setups
		'''
		if self.parent.IsVMRlight:
			return True

		msetup = None
		try:
			msetup = mseries.measuring_setup
		except:
			pass
		if gom.app.project.is_part_project:
			try:
				mseries = mseries.measurement_path
			except:
				pass

		# matches the real hardware?
		if not self.same_sensor(mseries):
			return False

		if msetup is None:
			# check only working_area for new calibration mseries
			try:
				try:
					id = mseries.get('working_area.id')
				except:
					id = mseries.measurement_path.get('working_area.id')
				if id in [gom.app.project.measuring_setups[wcfg].get('working_area.id') for wcfg in wcfgs]:
					return True
				for wcfg in wcfgs:
					if gom.app.project.measuring_setups[wcfg].get('working_area.id') in mseries.get('further_working_area_ids'):
						return True
				return False
			except: # no vmrlight series or vmrlight wcfg
				try:
					mseries.get('working_area') # vmrlight series but non vmrlight wcfg
					return False
				except:
					for wcfg in gom.app.project.measuring_setups:
						if wcfg.get('working_area') is not None: # non vmrlight wcfg
							return False
					return True

				return False
		else:
			# for old calibration mseries:
			return mseries.measuring_setup.name in wcfgs

		return False


class TemporaryWarmupDisable:
	'''
	Helper class to temporary disable the warmup time
	'''
	def __init__(self, sensor):
		self._oldvalue = sensor.temp_disable_warmup
		self._sensor = sensor
	def __enter__(self):
		self._sensor.temp_disable_warmup = True
	def __exit__( self, exc_type, exc_value, traceback ):
		self._sensor.temp_disable_warmup = self._oldvalue
		
def isDirectMoveAllowed(mlist):
	if Globals.SETTINGS.FreePathAlwaysAllowed:
		return True
	try:
		msetup = mlist.measuring_setup
	except:
		return False
	if msetup is None:
		return False
	try:
		enabled = msetup.is_collision_free_paths_uncritical_enabled
		if enabled is None:
			enabled = False
	except:
		return False
	return enabled


def safety_move_to_home( self, measure_series, reverse=False ):
	'''
	utility function which reinitializes the sensor (if needed) and moves to homeposition
	'''
	moveretry = True
	if self.parent.IsVMRlight:
		return

	# is the current position reached
	is_at_position = False
	if gom.app.project.is_part_project:
		curr_pos=measure_series.measurement_path.path_positions.filter ('is_current_position==True')
	else:
		curr_pos=measure_series.measurements.filter ('is_current_position==True')
	if len(curr_pos):
		try:
			is_at_position = curr_pos[0].is_equal_to_real_position
		except:
			pass
		if is_at_position is None:
			is_at_position = False

	if gom.app.project.is_part_project:
		if ( len( measure_series.measurement_path.path_positions.filter( 'is_current_position==true and type=="home_position"' ) )
			and ( is_at_position or Globals.SETTINGS.OfflineMode ) ):
			return
	else:
		if ( len( measure_series.measurements.filter( 'is_current_position==true and type=="home_position"' ) )
				and ( is_at_position or Globals.SETTINGS.OfflineMode ) ):
			return

	if self.parent.Dialog is not None:
		curr_msg = self.parent.Dialog.Process_get_msg_detail
		self.parent.Dialog.process_msg_detail( Globals.LOCALIZATION.msg_evaluate_detail_msg_safety_home )
	self.log.info( 'moving to home' )

	if gom.app.project.is_part_project:
		target_pos = measure_series.measurement_path.path_positions.filter( 'type=="home_position"' )[-1]
	else:
		target_pos = measure_series.measurements.filter( 'type=="home_position"' )[-1]
	move_cmd = gom.interactive.automation.forward_move_to_position
	if Globals.SETTINGS.Inline:
		move_cmd = gom.script.automation.forward_move_to_position

	# estimated the shortest distance and move reverse if shorter
	if len(curr_pos):
		i=curr_pos[0].index_in_path
		if (target_pos.index_in_path - i) > i:
			reverse = True

	# reverse move needs to be explicit enabled
	try:
		_allowReverseMovement = gom.app.project.virtual_measuring_room[0].is_reverse_move_always_safe
	except:
		_allowReverseMovement = False
	if not _allowReverseMovement:
		reverse = False

	freemovement_allowed = isDirectMoveAllowed(measure_series)
	# if current position is not reached only allow reverse move
	if not is_at_position:
		self.log.error('Position not reached only reverse is allowed')
		reverse = True
		freemovement_allowed = False
	# if estop is detected only allow reverse move
	# the application token is only for interactive movement cmds
	if gom.app.get('last_movement_aborted_with_estop') or self.parent.Global_Checks.last_error_was_estop:
		self.log.error('EStop abort detected only reverse is allowed')
		reverse = True
		freemovement_allowed = False

	if reverse and not _allowReverseMovement:
		self.log.error('Reverse movement is not allowed')
		if Globals.SETTINGS.Inline:
			InlineConstants.sendMeasureInstanceError( InlineConstants.PLCErrors.MEAS_MOVE_ERROR, '', Globals.LOCALIZATION.msg_reverse_move_not_allowed )
		else:
			Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_safely_move_failed,
				Globals.LOCALIZATION.msg_reverse_move_not_allowed, Globals.SETTINGS.SavePath, False )
		return

	if reverse:
		if gom.app.project.is_part_project:
			target_pos = measure_series.measurement_path.path_positions.filter( 'type=="home_position"' )[0]
		else:
			target_pos = measure_series.measurements.filter( 'type=="home_position"' )[0]
		move_cmd = gom.interactive.automation.reverse_move_to_position
		if Globals.SETTINGS.Inline:
			move_cmd = gom.script.automation.reverse_move_to_position
	try:
		gom.script.sys.set_kiosk_status_bar(enable_abort=False)
		only_init = False
		while moveretry:
			try:
				with TemporaryWarmupDisable(self.parent.Sensor) as warmup: # no warmuptime for move to home
					if only_init:
						if not self.parent.Sensor.initialize():
							if self.parent.Dialog is not None:
								self.parent.Dialog.process_msg_detail( curr_msg )
							return False
						only_init = False
					else:
						if not self.parent.Sensor.check_for_reinitialize():
							if self.parent.Dialog is not None:
								self.parent.Dialog.process_msg_detail( curr_msg )
							return False
				if self.parent.Dialog is not None:
					self.parent.Dialog.processbar_max_steps()
					self.parent.Dialog.processbar_step()
				if freemovement_allowed:
					if Globals.SETTINGS.Inline:
						gom.script.automation.move_to_home_position(all_devices_to_home_and_default_safety_area=False, direct_movement=True)
					else:
						gom.interactive.automation.move_to_home_position(all_devices_to_home_and_default_safety_area=False, direct_movement=True)
				else:
					move_cmd(measurement = target_pos)
				moveretry = False
			except gom.BreakError:
				continue # do not allow useraborts
			except Exception as moveerror:
				self.log.exception( str( moveerror ) )
				errorlog = ErrorLog()
				state = self.parent.Global_Checks.analyze_error( moveerror, measure_series, True, errorlog )
				if Globals.SETTINGS.Inline:
					if state == VerificationState.RetryWithoutCounting:
						continue
					elif state == VerificationState.MoveReverseHome and _allowReverseMovement:
						if gom.app.project.is_part_project:
							target_pos = measure_series.measurement_path.path_positions.filter( 'type=="home_position"' )[0]
						else:
							target_pos = measure_series.measurements.filter( 'type=="home_position"' )[0]
						move_cmd = gom.script.automation.reverse_move_to_position
						continue
					elif state == VerificationState.ReInitSensor:
						continue
					elif state == VerificationState.OnlyInitSensor:
						only_init = True
						continue
					elif state == VerificationState.Retry:
						continue
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MOVE_ERROR, errorlog.Code, errorlog.Error)
					return
				moveretry = Globals.DIALOGS.show_errormsg(
					Globals.LOCALIZATION.msg_safely_move_failed, errorlog.Error,
					Globals.SETTINGS.SavePath, True, error_code = errorlog.Code )
				if moveretry is False:
					try:
						self.parent.context.moved_to_home = True
					except:
						self.log.warning( 'Failed to tell MeasuringContext not to move to home' )
	finally:
		gom.script.sys.set_kiosk_status_bar(enable_abort=Globals.SETTINGS.AllowAbort)
	if self.parent.Dialog is not None:
		self.parent.Dialog.process_msg_detail( curr_msg )