# -*- coding: utf-8 -*-
# Script: Calibration Class
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
# 2012-12-04: check sensor status before executing measurement series
# 2013-01-22: rewrote the verification process
# 2014-05-14: after successful calibration store the information file into a folder

from ..Misc import Utils, Globals
from . import Measure
from ..Communication.Inline import InlineConstants
from ..Communication import Communicate
from .Verification import VerificationState, ErrorLog
import time, datetime, os
import gom

class Calibration( Utils.GenericLogClass ):
	'''
	Calibration class, holds all measurement tests and calibration functionality
	'''
	parent = None
	calibration_ms = None

	def __init__( self, logger, parent ):
		'''
		Initizalize function to init logging, dialog ref and calibration measurement
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.calibration_ms = None
		self.hyperscale = False

	@property
	def MeasureList( self ):
		return self.calibration_ms
	@MeasureList.setter
	def MeasureList( self, value ):
		self.calibration_ms = value
		if value is not None:
			self.hyperscale = value.get('calibration_measurement_series_type') != 'sensor'
		else:
			self.hyperscale = False


	def execute_active_measurement_series( self, clear_measurement_data = False ):
		'''
		Hook function to add more functionality around executing a measurement series
		'''
		if Globals.SETTINGS.InAsyncAbort:
			Globals.SETTINGS.InAsyncAbort = False
			raise gom.BreakError
		try:
			# Abort is not allowed
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
					gom.script.automation.execute_active_measurement_series( clear_measurement_data = clear_measurement_data )
				else:
					gom.interactive.automation.execute_active_measurement_series( clear_measurement_data = clear_measurement_data )
		finally:
			self.parent.position_information.end_measurement_list()
		return True

	def calibrate( self, reason = '' ):
		'''
		Performs calibration of Atos sensor. It trys to accomplish the calibration 2 times.

		Returns:
		True  - if the sensor was calibrated successfully
		False - otherwise (and no exception was raised)

		Raises Exceptions:
		Utils.CalibrationError - If no calibration series is defined.
		'''
		self.log.info( 'starting calibration{}'.format(' hyperscale' if self.hyperscale else '') )
		if self.calibration_ms is None:
			self.log.error( 'No Calibration Measurement Series defined' )
			raise Utils.CalibrationError( Globals.LOCALIZATION.msg_calibration_no_list_defined )
		if self.parent.Dialog is not None:
			self.parent.Dialog.process_msg_detail( Globals.LOCALIZATION.msg_evaluate_detail_calibrate )
			self.parent.Dialog.process_image( Globals.SETTINGS.CalibrationImageBinary )

		if not self.hyperscale and Globals.PERSISTENTSETTINGS.LastCalibration != 0 and reason not in ['temperature', 'force']:
			last_time = datetime.datetime.fromtimestamp( Globals.PERSISTENTSETTINGS.LastCalibration )
			maxdiff = datetime.timedelta( minutes = Globals.SETTINGS.CalibrationMaxTimedelta )
			current_time = datetime.datetime.today()
			difference = abs( current_time - last_time )
			if difference < maxdiff:
				diff_next_time = last_time + maxdiff - current_time
				difference = datetime.timedelta( days = diff_next_time.days, seconds = diff_next_time.seconds )  # format without microseconds
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_CALIBRATION_COUNT,'',Globals.LOCALIZATION.msg_calibration_too_often.format( difference ))
				else:
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
												Globals.LOCALIZATION.msg_calibration_too_often.format( difference ),
												Globals.SETTINGS.SavePath, False )
				return False

		# reinit sensor if needed and check warmup time
		if not self.parent.Sensor.check_for_reinitialize():
			return False
		if not self.parent.Thermometer.update_temperature( self.calibration_ms ):
			return False

		# activate the first compatible measuring setups if no compatible msetup is active
		active_msetup_name = self.parent.get_active_measuring_setup_name() 
		if ( active_msetup_name is None or
				( active_msetup_name is not None and active_msetup_name not in self.parent.Compatible_wcfgs ) ): 
			try:
				# old calib mseries has msetup reference
				gom.interactive.automation.define_active_measuring_setup(
					measuring_setup = self.calibration_ms.measuring_setup )
			except:
				# new calib mseries: choose first compatible msetup
				# VMRlight might be without measuring setups, in this case no setup is activated
				wcfgs = self.parent.Compatible_wcfgs
				if len(wcfgs) > 0:
					gom.interactive.automation.define_active_measuring_setup(
						measuring_setup = gom.app.project.measuring_setups[wcfgs[0]] )

		if not self.parent.define_active_measuring_series( self.calibration_ms ):
			return False

		if Globals.SETTINGS.Inline:
			Globals.CONTROL_INSTANCE.send_signal( Communicate.SIGNAL_CONTROL_CALIBRATION_STARTED )
		# maximum automatic retries = 2
		measureloop = 0
		errorlog = ErrorLog()
		while measureloop < 2:
			del errorlog.Error  # clean errorlog
			self.log.info( 'retry no. {}'.format( measureloop ) )

			state = VerificationState.ErrorFree

			# reinit sensor if needed and check warmup time
			if not self.parent.Sensor.check_for_reinitialize():
				return False
			
			self.parent.Global_Checks.reset_last_error()
			try:
				if not self.execute_active_measurement_series( True ):
					return False
				if not self.hyperscale:
					Globals.PERSISTENTSETTINGS.LastCalibration = time.time()
			except Globals.EXIT_EXCEPTIONS:
				raise
			except Exception as error:  # something happend (acquisition check abort, or eg sensor loss)
				self.log.error( 'Failed to execute Measurement series\n' + (str( error ) if not isinstance(error, gom.BreakError) else 'BreakError'))
				state = self.parent.Global_Checks.analyze_error( error, self.calibration_ms, measureloop < 2 - 1, errorlog )
				self.log.debug( 'VerificationState after analyze error: {}'.format( state ) )

			self.log.debug( 'VerificationState after measurement series execute: {}'.format( state ) )
			if state == VerificationState.ErrorFree:  # no error happend, analyze series
				state = self.parent.Global_Checks.checkcalibration( self.calibration_ms, errorlog )
				self.log.debug( 'VerificationState after series check: {}'.format( state ) )

			if state == VerificationState.ErrorFree:
				self.store_calibration_information()
				if self.parent.Statistics is not None:
					self.parent.Statistics.log_measurement_series()
				return True
			elif state == VerificationState.NeedsCalibration:
				pass
			elif state == VerificationState.Failure:
				self.log.info( 'Verification Failure retry' )
				Measure.safety_move_to_home( self, self.calibration_ms )
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
					return False
				if errorlog.Error:
					Globals.DIALOGS.show_errormsg( 
						Globals.LOCALIZATION.msg_general_failure_title,
						errorlog.Error,
						Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
				return False
			elif state == VerificationState.UserAbort:
				self.log.info( 'Failed to execute Measurement series\nDue to break error' )
				Measure.safety_move_to_home( self, self.calibration_ms )
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_USERABORT,'','')
				return False
			elif state == VerificationState.Retry:
				pass
			elif state == VerificationState.RetryWithoutCounting:
				measureloop -= 1
				self.parent.position_information.set_continue_mlist()
			elif state == VerificationState.MoveReverseHome:
				Measure.safety_move_to_home( self, self.calibration_ms, True )
				return False

			measureloop += 1
			if self.parent.Dialog is not None:
				self.parent.Dialog.processbar_max_steps()
				self.parent.Dialog.processbar_step()

		# unknown errors (likely calibration errors should stop at the current position, no move to home
		self.log.error( 'number of repetitions exceeded' )
		if Globals.SETTINGS.Inline:
			InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_CALIBRATION_ERROR, errorlog.Code, errorlog.Error)
		else:
			Globals.DIALOGS.show_errormsg( 
				Globals.LOCALIZATION.msg_general_failure_title,
				Globals.LOCALIZATION.msg_calibration_failed_execute + '<br/>' + errorlog.Error,
				Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
		return False

	def store_calibration_information( self ):
		'''
		stores the calibration information into the SavePath
		'''
		try:
			file_path = os.path.join( Globals.SETTINGS.SavePath, 'calibration_results' )
			if not os.path.exists( file_path ):
				os.mkdir( file_path )
			gom.script.calibration.save_calibration_information ( 
				file = os.path.join ( file_path, 'calibration_info_{}.txt'.format( time.strftime( '%Y_%m_%d_%H_%M_%S' ) ) ),
				source = 'system' )
		except Exception as e:
			self.log.exception( 'failed to store calibration info file: {}'.format( e ) )
		
		if Globals.SETTINGS.Inline:
			Globals.CONTROL_INSTANCE.send_signal( Communicate.SIGNAL_CONTROL_CALIBRATION_DONE )
		if Globals.IOT_CONNECTION is not None:
			calib_date, calib_exp = Globals.IOT_CONNECTION.getCalibrationInformation()
			Globals.IOT_CONNECTION.send(exposure_time_calib=calib_exp, calib_time=calib_date)
