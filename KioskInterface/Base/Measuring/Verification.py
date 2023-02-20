# -*- coding: utf-8 -*-
# Script: Measurement Verification Class
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
# 2013-01-22: rewrote verification routines for less calibration processes
#             added ignore for polygonization functionality
# 2016-04-26: Burn-In Limits

import gom
from ..Misc import Utils, Globals
from ..Communication.Inline import InlineConstants

import math
import re

IGNORE_FOR_POLYGONIZATION_POSTFIX = '_IgnoreForPolygonization'

class MeasureChecks( Utils.GenericLogClass ):
	'''
	class for measurement tests
	'''
	parent = None
	def __init__( self, logger, parent ):
		'''
		initialize function
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.last_error_was_estop = False

	def checkphotogrammetry( self, series, errorlog = None, drc_forced=False ):
		'''
		check photogrammetry result
		number of scalebars doesnt matter for the verification, if only one is defined the average scalebar deviation is 0
		'''
		if Globals.DRC_EXTENSION is not None and (Globals.DRC_EXTENSION.SecondarySideActive() or Globals.DRC_EXTENSION.PrimarySideActive()):
			if not drc_forced: # only recalc Tritop in DRC mode when forced (after importing)
				return VerificationState.ErrorFree
		if isinstance( series, str ):
			series = gom.app.project.measurement_series[series]
		# recalulate measurement for tests
		gom.script.sys.recalculate_elements( elements = [series] )
		if Globals.SETTINGS.OfflineMode:
			return VerificationState.ErrorFree
		if not Globals.SETTINGS.PhotogrammetryVerification:
			self.log.info( 'WARNING: No Photogrammetry Verification' )
			return VerificationState.ErrorFree
		success = False

		try:
			used_scalebars = series.scalebars.filter( 'computation_status=="computed"' )
			if len( used_scalebars ) < Globals.SETTINGS.PhotogrammetryNumberOfScaleBars:
				self.log.error( 'failed to identify scale bars' )
				if errorlog is not None:
					errorlog.Error = Globals.LOCALIZATION.msg_verification_scale_bar_identify
				return VerificationState.Failure
			sum_scale_limit = 0
			for scalebar in used_scalebars:
				length = scalebar.nominal_length
				if length is None:
					self.log.error( 'failed to get scale bar length' )
					if errorlog is not None:
						errorlog.Error = Globals.LOCALIZATION.msg_photogrammetry_verification_failed
					return VerificationState.Failure
				scale_limit = length / 50000.0 + 0.005
				sum_scale_limit += scale_limit
			if sum_scale_limit > 0:
				sum_scale_limit /= len( used_scalebars )

			photogrammetry_image_point_limit = 0.08
			img_dev = series.get ( 'average_image_point_deviation' )
			scale_dev = series.get ( 'average_scale_bar_deviation' )
			if series.get( 'number_of_scale_bars' ) == 0:
				scale_dev = -100
				sum_scale_limit = 101
			if img_dev is None:
				self.log.error( 'failed to get image deviation' )
				if errorlog is not None:
					errorlog.Error = Globals.LOCALIZATION.msg_photogrammetry_verification_failed
				return VerificationState.Failure
			if scale_dev is None:
				self.log.error( 'failed to get scale bar deviation' )
				if errorlog is not None:
					errorlog.Error = Globals.LOCALIZATION.msg_photogrammetry_verification_failed
				return VerificationState.Failure

			success = ( ( img_dev < photogrammetry_image_point_limit ) and ( abs( scale_dev ) < abs( sum_scale_limit ) ) )
			if not success:
				self.log.error( 'Photogrammetry test: ImagePointDeviation: {:-f} < {:-f} and ScaleBarDeviation: {:-f} < {:-f} == {}'.format( 
							img_dev, photogrammetry_image_point_limit, scale_dev, sum_scale_limit, success ) )

		except Globals.EXIT_EXCEPTIONS:
			raise
		except Exception as error:
			self.log.exception( str( error ) )
		if success:
			return VerificationState.ErrorFree
		if errorlog is not None:
			errorlog.Error = Globals.LOCALIZATION.msg_photogrammetry_verification_failed
		return VerificationState.Failure


	def get_intersection_limit( self ):
		'''
		returns the projects base intersection limit
		based on acquisition parameter reference point quality scanning
		return float
		'''
		res = 0.2
		if gom.app.project.reference_point_identification_method =='gray_value_adjustment':
			if gom.app.project.get( 'max_residual_edge_point_adjustment' ) >= 0.06:
				res = 0.3
		else:
			if gom.app.project.get( 'max_residual_edge_point_adjustment' ) >= 0.4:
					res = 0.3
		return res

	def has_intersection_error( self, measurement ):
		'''
		checks if given measurement has intersection error
		param measurement reference
		@return: True if check failed, False if error free
		'''
		if not gom.app.project.get ( 'check_decalibrated_sensor' ):
			return False
		name = measurement.get( 'name' )
		intersection_limit = self.get_intersection_limit()
		try:
			if measurement.image_width > 4500:
				intersection_limit *= 1.5
		except:
			pass

		if not measurement.get( 'sensor_operation_temperature_reached' ):
			return False
		try:
			if measurement.multipart_linkage_type == 'global_with_linked_ml_in_parts':
				inters_dev = measurement.linked_measurements_in_parts[0].get( 'mean_intersection_deviation' )
			else:
				inters_dev = measurement.get( 'mean_intersection_deviation' )
			if inters_dev is None:  # not calculatable is treated as no error, since calibration cannot help
				self.log.warning( '{} Intersection Deviation failed {}'.format( name, inters_dev ) )
				return False
			elif inters_dev > intersection_limit:
				self.log.error( '{} Intersection Deviation failed {:-f} > {:f}'.format( name, inters_dev, intersection_limit ) )
				return True
			return False
		except Exception as e:
			self.log.error( 'failed to get Intersection Deviation {} : {}'.format( name, e ) )
			return True

	def get_transformation_limit( self, measurement = None ):
		'''
		returns the measuring volume width based transformation limit
		'''
		volume_width = 0
		if measurement is not None:
			try:
				mlist = measurement.get('measurement_series')
				volume_width = mlist.get ('measuring_setup').get ('sensor_configuration.scan_measuring_volume.volume.width')
			except:
				pass
		if not volume_width:
			try:
				volume_width = gom.app.get ('sys_sensor_configuration.scan_measuring_volume.volume.width')
			except:
				volume_width = 0
		if volume_width:
			return volume_width / 3000.0
		return 0.3  # Fallback

	def get_transformation_alignment_residual_limit( self ):
		'''
		returns the transformation deviation limit based on the measurement mesh/referencepoint alignment residual
		'''
		max_deviation_residual = 1.0e12
		try:
			mesh_residual = gom.app.project.get ( 'measurement_mesh_alignment_residual' )
			ref_point_residual = gom.app.project.get( 'measurement_reference_point_alignment_residual' )
		except:
			return max_deviation_residual
		if mesh_residual is not None and mesh_residual <= 1e-50:
			mesh_residual = None
		if ref_point_residual is not None and ref_point_residual <= 1e-50:
			ref_point_residual = None
		if mesh_residual is not None and ref_point_residual is not None:
			max_deviation_residual = 6.0 * min( mesh_residual, ref_point_residual )
		elif mesh_residual is not None:
			max_deviation_residual = 6.0 * mesh_residual
		elif ref_point_residual is not None:
			max_deviation_residual = 6.0 * ref_point_residual
		return max_deviation_residual

	def is_transformation_check_active( self, measurement ):
		'''
		tests if the given measurement can be checked for transformation
		'''
		if not gom.app.project.get ( 'check_transformation' ):
			return False
		if not measurement.get( 'sensor_operation_temperature_reached' ):
			return False

		return True

	def has_transformation_error( self, measurement ):
		'''
		checks if given measurement has transformation error
		param measurement reference
		@return: True if check failed, False if error free
		'''
		if not self.is_transformation_check_active( measurement ):
			return False
		name = measurement.get( 'name' )
		transformation_limit = self.get_transformation_limit(measurement)
		residual_limit = self.get_transformation_alignment_residual_limit()
		try:
			if measurement.multipart_linkage_type == 'global_with_linked_ml_in_parts':
				trans_devs = [mmt.get( 'transformation_deviation' )
					for mmt in measurement.linked_measurements_in_parts]
			else:
				trans_devs = [measurement.get( 'transformation_deviation' )]
			if any( [trans_dev is None for trans_dev in trans_devs] ):
				self.log.error( '{} Transformation Deviation failed {}'.format( name, str( trans_devs ) ) )
				return True
			elif any( [trans_dev > transformation_limit for trans_dev in trans_devs] ):
				self.log.error( '{} Transformation Deviation failed {:-f} > {:f}'.format(
					name, str( trans_devs ), transformation_limit ) )
				return True
			elif any( [trans_dev >= residual_limit for trans_dev in trans_devs] ):
				self.log.error( '{} Transformation Deviation failed (alignment residual limit) {:-f} >= {:f}'.format(
					name, str( trans_devs ), residual_limit ) )
				return True

			return False
		except Exception as e:
			self.log.error( 'Failed to get Transformation Deviation {} : {}'.format( measurement, e ) )
			return True

	def is_projector_residual_check_active( self, measurement ):
		'''
		tests if the given measurement can be checked for projector residual
		'''
		try:
			if measurement.get( 'avoid_triple_scan_points' ) or not measurement.get( 'is_quality_triple_scan_points_checked' ):
				return False
			if not measurement.get( 'sensor_operation_temperature_reached' ):
				return False
			if measurement.get( 'quality_triple_scan_points' ) == 'not calibrated':  # referencepoint measurement or projector is not calibrated
				return False
		except:  # TODO: on error this measurement should be deeper analysied
			pass

		return True

	def has_projector_residual_error( self, measurement ):
		'''
		checks if given measurement has projector residual error
		param measurement reference
		@return: True if check failed, False if error free
		'''
		if not self.is_projector_residual_check_active( measurement ):
			return False
		name = measurement.get( 'name' )
		try:
			if measurement.get( 'quality_triple_scan_points' ) == 'calculated':
				projector_limit = measurement.get( 'quality_triple_scan_points_threshold' )
				proj_dev = float( measurement.get( 'tr(quality_triple_scan_points)' ).split()[0].split('%')[0] )
				if proj_dev > projector_limit:
					self.log.error( '{} Projector Residual failed: {} > {}'.format( name, proj_dev, projector_limit ) )
					return True

				return False
			else:
				self.log.error( '{} Projector Residual failed: {}'.format( name, measurement.get( 'quality_triple_scan_points' ) ) )
				return True
		except Exception as e:
			self.log.error( 'failed to get Projector Residual {} : {}'.format( measurement, e ) )
			return True

	def has_movement_error( self, measurement ):
		'''
		checks if given measurement has movement error
		param measurement reference
		@return: True if check failed, False if error free
		'''
		if not gom.app.project.get ( 'check_sensor_movement' ):
			return False
		name = measurement.get( 'name' )
		try:
			movement_check = measurement.get( 'sensor_movement_check_result' )
			if movement_check != 'check failed':
				return False
			self.log.error( '{} Movement Check failed: {}'.format( name, movement_check ) )
			return True
		except Exception as e:
			self.log.error( 'failed to get Movement Check {} : {}'.format( measurement, e ) )
			return True

	def has_lighting_error( self, measurement ):
		'''
		checks if given measurement has lighting change error
		param measurement reference
		@return: True if check failed, False if error free
		'''
		if not gom.app.project.get( 'check_lighting_change' ):
			return False
		name = measurement.get( 'name' )
		try:
			lighting_check = measurement.get( 'lighting_change_check_result' )
			if lighting_check != 'check failed':
				return False
			self.log.error( '{} Lighting Check failed: {}'.format( name, lighting_check ) )
			return True
		except Exception as e:
			self.log.error( 'failed to get Lighting Check {} : {}'.format( measurement, e ) )
			return True

	def has_temperature_acq_vs_mmt_error( self, measurement ):
		'''Checks measurement temperature vs acquisition temperature'''
		if not gom.app.project.check_measurement_temperature:
			return False

		maxdelta = gom.app.project.allowed_temperature_difference
		temp_acq = gom.app.project.measurement_temperature
		temp_mmt = measurement.sensor_measurement_temperature
		if temp_acq is None or temp_mmt is None:
			return True
		if maxdelta < abs( temp_acq - temp_mmt ):
			return True
		return False

	def has_temperature_cal_vs_mmt_error( self, measurement ):
		'''Checks measurement temperature vs calibration temperature'''
		if not gom.app.project.check_measurement_temperature:
			return False

		maxdelta = gom.app.project.allowed_temperature_difference
		temp_cal = gom.app.sys_calibration_measurement_temperature
		temp_mmt = measurement.sensor_measurement_temperature
		if temp_cal is None or temp_mmt is None:
			return True
		if maxdelta < abs( temp_cal - temp_mmt ):
			return True
		return False

	def has_temperature_cal_vs_acq_error( self ):
		'''Checks calibration temperature vs acquisition temperature'''
		if not gom.app.project.check_measurement_temperature:
			return False

		maxdelta = gom.app.project.allowed_temperature_difference
		temp_cal = gom.app.sys_calibration_measurement_temperature
		temp_acq = gom.app.project.measurement_temperature
		if temp_cal is None or temp_acq is None:
			return True
		if maxdelta < abs( temp_cal - temp_acq ):
			return True
		return False

	def selective_clear_measuring_data( self, measurements ):
		'''
		clear the measuring data of given measurements
		'''
		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_max_steps()
			self.parent.Dialog.processbar_step()

		self.log.error( 'clearing measurement data: {}'.format( ','.join( ( str( m ) for m in measurements ) ) ) )
		gom.script.automation.clear_measuring_data ( measurements = measurements )

	def checkdigitizing( self, series, retry_allowed = True, errorlog = None ):
		'''
		analyze digitize measurements
		'''
		if isinstance( series, str ):
			series = gom.app.project.measurement_series[series]

		if gom.app.project.measurement_transformation_type != 'by_robot_position':
			gom.script.sys.recalculate_elements( elements = [series] )

		if Globals.SETTINGS.OfflineMode:
				return VerificationState.ErrorFree

		# remove all present ignore postfixes
		# not used anymore, but remove old postfixes to prevent confusion
		_renames = []
		for m in series.measurements:
			if m.name.endswith(IGNORE_FOR_POLYGONIZATION_POSTFIX):
				_renames.append(m)
		if len(_renames) > 0:
			try:
				gom.script.sys.rename_elements(
					elements = _renames,
					expression = 'name[:-{}]'.format(len(IGNORE_FOR_POLYGONIZATION_POSTFIX)))
			except RuntimeError as e:
				pass

		real_data_measurements = series.measurements.filter( 'computation_basis=="real_data"' )

		# is data existent?
		if not len( real_data_measurements ):
			self.log.error( 'no measurements with scandata found' )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_no_scan_data
			return VerificationState.Failure

		# collect measurements with errors
		intersection_error = [m for m in real_data_measurements if self.has_intersection_error( m )]
		if gom.app.project.measurement_transformation_type != 'by_robot_position':
			transformation_error = [m for m in real_data_measurements if self.has_transformation_error( m )]
		else:
			transformation_error = []
		projectorresidual_error = [m for m in real_data_measurements if self.has_projector_residual_error( m )]
		movement_error = [m for m in real_data_measurements if self.has_movement_error( m )]
		lighting_error = [m for m in real_data_measurements if self.has_lighting_error( m )]
		temp_acq_mmt_error = [m for m in real_data_measurements if self.has_temperature_acq_vs_mmt_error( m )]
		temp_cal_mmt_error = [m for m in real_data_measurements if self.has_temperature_cal_vs_mmt_error( m )]
		temp_cal_acq_errorflag = self.has_temperature_cal_vs_acq_error()

		# allow several percent to fail
		count_projectorresidual_active = len( [ m for m in real_data_measurements if self.is_projector_residual_check_active( m )] )
		count_transformation_active = len( [ m for m in real_data_measurements if self.is_transformation_check_active( m )] )
		error_count_limit_projectorresidual = math.ceil( count_projectorresidual_active * Globals.SETTINGS.MeasurementFailureMargin )
		error_count_limit_transformation = math.ceil( count_transformation_active * Globals.SETTINGS.MeasurementFailureMargin )
		error_count_limit_previewpoints = math.ceil( len(real_data_measurements) * Globals.SETTINGS.MeasurementFailureMargin )
		error_count_limit_movement_light = math.ceil( len(real_data_measurements) * Globals.SETTINGS.MeasurementFailureMargin )
		error_count_limit_intersection = math.ceil( len(real_data_measurements) * Globals.SETTINGS.MeasurementFailureMargin )
		
		state = VerificationState.ErrorFree

		# check all errors and if still possible clear measuring data for the retry
		# Order of checks: Abort before Retry before NeedsCalibration

		# If any temperature errors "acq vs mmt" or "cal vs mmt" or "cal vs acq" -> Abort.
		# Also return! Retry/Calibrate cannot repair this.
		if len( temp_acq_mmt_error ) > 0 or len( temp_cal_mmt_error ) > 0 or temp_cal_acq_errorflag:
			state = VerificationState.Abort
			if len( temp_acq_mmt_error ) > 0: self.log.error( 'Temperature error Acquisition/Measurement' )
			if len( temp_cal_mmt_error ) > 0: self.log.error( 'Temperature error Calibration/Measurement' )
			if temp_cal_acq_errorflag: self.log.error( 'Temperature error Calibration/Acquisition' )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_temperature_exception
			return state

		if len( transformation_error ) > error_count_limit_transformation:
			state = VerificationState.Abort
			self.log.error( 'Transformation Limit failed {} > {}'.format( len( transformation_error ), error_count_limit_transformation ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_transformation_failed.format(
					len( transformation_error ), error_count_limit_transformation )

		# For movement and light:
		# if retry is possible trigger always retry, else only if the margin fails  
		if ((len( movement_error ) and retry_allowed and not Globals.SETTINGS.HigherFaultTolerance) or 
			(len( movement_error ) > error_count_limit_movement_light)):
			state = VerificationState.Retry
			self.log.error( 'Movement Check Limit failed: {}'.format( len( movement_error ) ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_movement_check_failed.format( len( movement_error ) )

		if ((len( lighting_error ) and retry_allowed and not Globals.SETTINGS.HigherFaultTolerance) or
			(len( lighting_error ) > error_count_limit_movement_light)):
			state = VerificationState.Retry
			self.log.error( 'Lighting Check Limit failed: {}'.format( len( lighting_error ) ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_lighting_failed.format( len( lighting_error ) )

		if len( projectorresidual_error ) > error_count_limit_projectorresidual:
			state = VerificationState.NeedsCalibration
			self.log.error( 'Projector Residual Limit failed {} > {}'.format( len( projectorresidual_error ), error_count_limit_projectorresidual ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_projector_residual_failed.format(
					len( projectorresidual_error ), error_count_limit_projectorresidual )

		if ((len( intersection_error ) and not Globals.SETTINGS.HigherFaultTolerance) or
			(len( intersection_error ) > error_count_limit_intersection)):
			self.log.error( 'Intersection Check Limit failed: {}'.format( len( intersection_error ) ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_intersection_failed.format( len( intersection_error ) )
			state = VerificationState.NeedsCalibration

		# if a retry should happen clear all errors
		if state in [VerificationState.Retry, VerificationState.NeedsCalibration] and retry_allowed:
			if len( transformation_error ):
				self.log.error( 'clearing transformation errors' )
				self.selective_clear_measuring_data( transformation_error )
			if len( movement_error ):
				self.log.error( 'clearing movement errors' )
				self.selective_clear_measuring_data( movement_error )
			if len( lighting_error ):
				self.log.error( 'clearing lighting errors' )
				self.selective_clear_measuring_data( lighting_error )
			if len( projectorresidual_error ):
				self.log.error( 'clearing projector residual errors' )
				self.selective_clear_measuring_data( projectorresidual_error )
			if len( intersection_error ):
				self.log.error( 'clearing intersection errors' )
				self.selective_clear_measuring_data( intersection_error )
		
		if Globals.FEATURE_SET.ONESHOT_MODE and not retry_allowed and state != VerificationState.ErrorFree:
			self.log.info('Error ignored due to OneShot mode: {}'.format(state))
			state = VerificationState.ErrorFree
			
		return state
	
	
	def collectMeasurementsForPolygonization(self):
		'''
		collects measurement for polygonization
		returns list of measurement references to polygonize and a list to ignore
		'''
		poly_measurements = []
		ignore_measurements = []
		for series in Utils.real_measurement_series( filter='type=="atos_measurement_series"' ):
			real_data_measurements = list(series.measurements.filter( 'computation_basis=="real_data"' ))
		
			for m in real_data_measurements:
				if (self.has_intersection_error( m ) or 
					self.has_transformation_error( m ) or
					self.has_projector_residual_error( m ) or
					self.has_movement_error( m ) or
					self.has_lighting_error( m )):
					ignore_measurements.append( m )
				else:
					poly_measurements.append( m )
			
		return poly_measurements, ignore_measurements

	def recalc_mseries_in_final_mode( self ):
		if gom.app.project.is_part_project:
			try:
				if gom.app.project.project_contains_preliminary_data:
					gom.script.sys.switch_project_into_preliminary_data_mode( preliminary_data=False )
					gom.script.sys.recalculate_elements( elements=gom.app.project.measurement_series )
					gom.script.sys.switch_project_into_preliminary_data_mode( preliminary_data=True )
					self.log.debug( 'Recalculated fine alignment in final mode' )
			except Exception as e:
				self.log.exception( 'Recalculation of fine alignment in final mode failed: ' + str( e ) )

	def checkalignment_residual( self, errorlog = None ):
		'''
		recalculate all measurement series and check the alignment residual between photogrammetry and digitize measurements
		'''
		def _get_token_vals():
			mseries_with_parts = None
			for mseries in gom.app.project.measurement_series:
				if mseries.type == 'calibration_measurement_series':
					continue
				if mseries.part is not None:
					mseries_with_parts = mseries.linked_global_measurement_series
					break

			if mseries_with_parts is not None:
				linked_mseries = mseries_with_parts.linked_measurement_series_in_parts
				return [
						[ms.are_measurements_aligned for ms in linked_mseries],
						[ms.measurement_mesh_alignment_residual for ms in linked_mseries],
						[ms.measurement_reference_point_alignment_residual for ms in linked_mseries],
						[ms.measurement_alignment_residual_diff_too_high for ms in linked_mseries]
					]
			else:
				return [
						[gom.app.project.get( 'are_measurements_aligned' )],
						[gom.app.project.get( 'measurement_mesh_alignment_residual' )],
						[gom.app.project.get( 'measurement_reference_point_alignment_residual' )],
						[gom.app.project.get( 'measurement_alignment_residual_diff_too_high' )]
					]

		def _residual_check_fail():
			if not Globals.SETTINGS.PhotogrammetryVerification:
				self.log.info( 'WARNING: No Photogrammetry Verification' )
				alignment_residual_diff_too_high = False
			else:
				alignment_residual_diff_too_high = False
				try:
					aligneds, mesh_residuals, ref_point_residuals, residual_diff_too_highs = _get_token_vals()
					if (all( [mr is not None for mr in mesh_residuals] )
							and all( [rpr is not None for rpr in ref_point_residuals] )
							and all( [a for a in aligneds] )):
						if any( [rdth for rdth in residual_diff_too_highs] ):
							alignment_residual_diff_too_high = True
							self.log.error( 'Alignment residual diff(s) too large:'
								' aligned {} and mesh_residual {} differs too much'
								' from ref_point_residual {} = {}'.format( 
								str( aligneds ), str( mesh_residuals ),
								str( ref_point_residuals ), str( alignment_residual_diff_too_high ) ) )
					elif any( [rpr is None for rpr in ref_point_residuals] ):
						self.log.warning( 'A reference point residuum is None.'
							' This should not happen in projects with reference points.' )
					else:
						alignment_residual_diff_too_high = True
						self.log.error( 'Alignment residual(s) could not be calculated:'
							' aligned {} , mesh_residual {} ref_point_residual {}'.format( 
							str( aligneds ), str( mesh_residuals ), str( ref_point_residuals ) ) )
				except Exception as e:
					alignment_residual_diff_too_high = True
					self.log.error( 'Failed to get measurement aligned tokens: {}'.format( e ) )
			return alignment_residual_diff_too_high

		# recalculate all measurement series (also those in parts)
		gom.script.sys.recalculate_elements( elements=gom.app.project.measurement_series )

		if Globals.SETTINGS.OfflineMode:
				return DigitizeResult.Success

		# this is the first time the measurement series get calculated when transformation by robot position is active,
		# check here the transformation errors
		if gom.app.project.measurement_transformation_type == 'by_robot_position':
			real_data_measurements = []
			for series in Utils.real_measurement_series( filter='type=="atos_measurement_series"' ):
				real_data_measurements+=series.measurements.filter( 'computation_basis=="real_data"' )
			transformation_error = [m for m in real_data_measurements if self.has_transformation_error( m )]
			count_transformation_active = len( [ m for m in real_data_measurements if self.is_transformation_check_active( m )] )
			error_count_limit_transformation = math.ceil( count_transformation_active * Globals.SETTINGS.MeasurementFailureMargin )
			if len( transformation_error ) > error_count_limit_transformation:
				self.log.error( 'Transformation Limit failed {} > {}'.format( len( transformation_error ), error_count_limit_transformation ) )
				if errorlog is not None:
					errorlog.Error = Globals.LOCALIZATION.msg_verification_transformation_failed.format(
						len( transformation_error ), error_count_limit_transformation )
				return DigitizeResult.TransformationMarginReached

		alignment_residual_diff_too_high = _residual_check_fail()
		if not alignment_residual_diff_too_high:
			return DigitizeResult.Success
		else:
			self.recalc_mseries_in_final_mode()
			alignment_residual_diff_too_high = _residual_check_fail()
			if not alignment_residual_diff_too_high:
				return DigitizeResult.Success

			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_global_digitize_too_large
			return DigitizeResult.RefPointMismatch


	def log_verification_check_states( self ):
		'''
		log current status of project base checks and limits
		'''
		self.log.info( 'Decalibrated Check {} Abort {}'.format( gom.app.project.get ( 'check_decalibrated_sensor' ), gom.app.project.get ( 'exception_decalibrated_sensor_abort' ) ) )
		self.log.info( 'Transformation Check {} Abort {}'.format( gom.app.project.get ( 'check_transformation' ), gom.app.project.get ( 'exception_transformation_abort' ) ) )
		self.log.info( 'Movement Check {} Abort {}'.format( gom.app.project.get ( 'check_sensor_movement' ), gom.app.project.get ( 'exception_sensor_movement_abort' ) ) )
		self.log.info( 'Lighting Check {} Abort {}'.format( gom.app.project.get ( 'check_lighting_change' ), gom.app.project.get ( 'exception_lighting_change_abort' ) ) )
		self.log.info( 'Transformation Limit {:-f}'.format( self.get_transformation_limit() ) )
		self.log.info( 'Intersection Limit {:-f}'.format( self.get_intersection_limit() ) )

	def was_last_error_estop(self):
		return self.last_error_was_estop
	
	def reset_last_error(self):
		self.last_error_was_estop = False
	
	def analyze_error( self, error, series, retry_allowed = False, errorlog = None ):
		'''
		analyze measurement exception
		@return VerificationState value
		'''
		if isinstance( series, str ):
			series = gom.app.project.measurement_series[series]
		
		self.reset_last_error()
		
		if isinstance( error, gom.BreakError ):
			# can happen via progressbar or cancel in EStop/Door/ResetState dialog
			self.log.error( 'User break detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_userabort
			return VerificationState.UserAbort
		elif error.args[0] in ['MATOS-M105']:
			self.log.error( 'Calibration exception detected: {}'.format( error ) )
			if retry_allowed:
				# delete old scandata which have intersection/transformation errors
				real_data_measurements = series.measurements.filter( 'computation_basis=="real_data"' )
				# is data existent?
				if len( real_data_measurements ):
					# collect measurements with errors
					ms_error = ( [m for m in real_data_measurements if self.has_intersection_error( m )]
							+ [m for m in real_data_measurements if self.has_transformation_error( m )]
							+ [m for m in real_data_measurements if self.has_projector_residual_error( m )]
							+ [m for m in real_data_measurements if self.has_movement_error( m )]
							+ [m for m in real_data_measurements if self.has_lighting_error( m )] )

					if len( ms_error ) > 0:  # if found clear
						try:
							self.selective_clear_measuring_data( ms_error )
						except:
							pass
			return VerificationState.NeedsCalibration
		elif error.args[0] in ['MATOS-M134']:
			self.log.error( 'The calibrated measuring volume for reference points does not match: {}'.format( error ) )
			return VerificationState.NeedsCalibration
		elif error.args[0] in ['MPROJ-0056']:
			return self._analyze_temperature_error( error, series, retry_allowed, errorlog )
		elif error.args[0] in ['MATOS-M104']:
			self.log.error( 'Transformation exception detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_transformation_exception
				errorlog.Code = error.args[0]
			return VerificationState.Failure
		elif error.args[0] in ['MPROJ-0038', 'MPROJ-0036']:
			self.log.error( 'Lighting/Movement exception detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_move_light_exception
				errorlog.Code = error.args[0]
			return VerificationState.Failure
		elif error.args[0] in ['MPROJ-0018']:
			self.log.error( 'Measurement not possible detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return VerificationState.Failure

		elif error.args[0] in ['MOVE-0100']:
			self.log.error( 'Emergency Exit detected: {}'.format( error ) )
			self.last_error_was_estop = True
			if self.parent.IsVMRlight:
				self.parent.Sensor.needs_reference_position = True
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_emergency_button
				errorlog.Code = error.args[0]
			return self.waitForDecision(error, VerificationState.Abort)
		elif error.args[0] in ['MOVE-0200']:
			self.log.error( 'Door open error detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return self.waitForDecision(error, VerificationState.Retry)
		elif error.args[0] in ['MOVE-0300']:
			self.log.error( 'Reset state error detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return self.waitForDecision(error, VerificationState.Retry)

		elif error.args[0] in ['MAUTO-0110', 'MPROJ-0021', 'MPROJ-0024']:
			self.log.error( 'Unrecoverable robot position detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_unrecoverable_position
				errorlog.Code = error.args[0]
			return VerificationState.Abort
		elif error.args[0] in ['MPROJ-0027']:
			self.log.error( 'Automation device is not initialized detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return VerificationState.Abort
		elif error.args[0] in ['MOVE-0001', 'MOVE-0003', 'MOVE-0500', 'MOVE-0600']:
			self.log.error( 'Move Server exception detected (reinit): {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return VerificationState.ReInitSensor
		elif error.args[0] in ['MOVE-0002', 'MOVE-0400', 'MOVE-0700', 'MOVE-0800']:
			self.log.error( 'Move Server exception detected (abort): {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return VerificationState.Abort
		elif error.args[0] in ['MOVE-0900']:
			self.log.error( 'Move Server temperature exception detected (abort): {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return VerificationState.Abort
		elif error.args[0] in ['AUTO-0002', 'AUTO-0003']:
			self.log.error( 'Automation exception detected (reinit): {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return VerificationState.ReInitSensor
		elif error.args[0] in ['MATOS-S022', 'FG-0004', 'FG-0010']:
			self.log.error( 'Sensor communication error detected: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]
			return VerificationState.OnlyInitSensor
		elif error.args[0] in ['MAUTO-0200']:
			self.log.error( 'Computer communication error detected: {}'.format( error ) )
			gom.script.sys.delay_script( time = 4 )
			if errorlog is not None:
				errorlog.Error = error.args[1]
				errorlog.Code = error.args[0]

			if Globals.DRC_EXTENSION is not None:
				# check connection even if not "PAIRED"
				res = Globals.DRC_EXTENSION.check_connected_and_alive( timeout=60.0 )
				if not res:
					# No communication => Abort
					return VerificationState.Abort
			return VerificationState.Retry

		else:
			self.log.error( 'Unrecognized exception: {}'.format( error ) )
			if errorlog is not None:
				errorlog.Error = '\n'.join(error.args)
				errorlog.Code = error.args[0]
			return VerificationState.ReInitSensor

	def _analyze_temperature_error( self, error, series, retry_allowed = False, errorlog = None ):
		'''
		Analyze MPROJ-0056 exception.
		If the error came from delta to calibration temperature: force calibration; else: abort
		@return VerificationState TemperatureForcesCalibration or VerificationState.Failure
		'''
		self.log.error( 'Temperature difference exception detected: {}'.format( error ) )

		# get calibration, acquisition and current temperature
		temp_cal = gom.app.sys_calibration_measurement_temperature
		temp_acq = gom.app.project.measurement_temperature
		temp_mmt = self.parent.thermo.get_temperature()
		self.log.debug( 'Temperatures cal {} acq {} cur {}'.format( temp_cal, temp_acq, temp_mmt ) )

		# determine temperature error source
		ldelta = -1.0
		src = None
		if temp_cal is not None and temp_acq is not None:
			if ldelta < abs( temp_cal - temp_acq ):
				ldelta = abs( temp_cal - temp_acq )
				src = 'cal_vs_acq'
		if temp_cal is not None and temp_mmt is not None:
			if ldelta < abs( temp_cal - temp_mmt ):
				ldelta = abs( temp_cal - temp_mmt )
				src = 'cal_vs_mmt'
		if temp_acq is not None and temp_mmt is not None:
			if ldelta < abs( temp_acq - temp_mmt ):
				ldelta = abs( temp_acq - temp_mmt )
				src = 'acq_vs_mmt'

		# Acquisition/Current temperature error or incomplete temperature info => Failure
		# All other cases => Force calibration
		if src == 'acq_vs_mmt' or temp_cal is None or temp_mmt is None:
			if errorlog is not None:
				errorlog.Error = Globals.LOCALIZATION.msg_verification_temperature_exception
				errorlog.Code = error.args[0]
			return VerificationState.Failure
		else:
			return VerificationState.TemperatureForcesCalibration

	def waitForDecision(self, error, verification_state):
		if not Globals.SETTINGS.Inline:
			return verification_state
		if Globals.SETTINGS.MoveDecisionAfterFaultState == InlineConstants.MoveDecision.UNKNOWN:
			if Globals.FEATURE_SET.DRC_SECONDARY_INST:
				error_int = InlineConstants.PLCErrors.MEAS_RESET_STATE
				if error.args[0] == 'MOVE-0100': # emergency
					error_int = InlineConstants.PLCErrors.MEAS_EMERGENCY_STOP
				elif error.args[0] == 'MOVE-0200': # fence open
					error_int = InlineConstants.PLCErrors.MEAS_FENCE_OPEN
				elif error.args[0] == 'MOVE-0300': # reset state
					error_int = InlineConstants.PLCErrors.MEAS_RESET_STATE
				else:
					return verification_state
				if not Globals.DRC_EXTENSION.onMoveDecisionNeeded(error_int, error.args[0], error.args[1]):
					return verification_state
			else:
				if error.args[0] == 'MOVE-0100': # emergency
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_EMERGENCY_STOP, error.args[0], error.args[1])
				elif error.args[0] == 'MOVE-0200': # fence open
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_FENCE_OPEN, error.args[0], error.args[1])
				elif error.args[0] == 'MOVE-0300': # reset state
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_RESET_STATE, error.args[0], error.args[1])
				else:
					return verification_state
				
			self.log.debug("Waiting for decision..")
			aborted=False
			Globals.SETTINGS.AllowAsyncAbort = True
			Globals.SETTINGS.WaitingForMoveDecision = True
			while not aborted:
				try:
					gom.script.sys.delay_script(time=2000)
				except:
					aborted = True
			Globals.SETTINGS.AllowAsyncAbort = False
			Globals.SETTINGS.WaitingForMoveDecision = False
		try:
			if Globals.SETTINGS.MoveDecisionAfterFaultState == InlineConstants.MoveDecision.UNKNOWN:
				self.log.error("Move decision still UNKNOWN")
				return verification_state
			elif Globals.SETTINGS.MoveDecisionAfterFaultState == InlineConstants.MoveDecision.CONTINUE:
				self.log.debug("Move decision is CONTINUE")
				return VerificationState.RetryWithoutCounting
			elif Globals.SETTINGS.MoveDecisionAfterFaultState == InlineConstants.MoveDecision.ABORT:
				self.log.debug("Move decision is ABORT")
				return VerificationState.Abort
			elif Globals.SETTINGS.MoveDecisionAfterFaultState == InlineConstants.MoveDecision.MOVE_REVERSE_HOME:
				self.log.debug("Move decision is MOVE_REVERSE_HOME")
				return VerificationState.MoveReverseHome
			else:
				self.log.error("Invalid move decision: {}".format(Globals.SETTINGS.MoveDecisionAfterFaultState))
				return VerificationState.Abort
		finally:
			Globals.SETTINGS.MoveDecisionAfterFaultState = InlineConstants.MoveDecision.UNKNOWN

	def checkProjectConsistency( self ):
		'''
		tests project consistency with corresponding script cmd
		shows an error msg if an error occurs
		returns True if no error occurs, or if worker pressed "Continue", else False
		'''
		error_details = gom.script.sys.check_project_consistency()
		error = ''
		continue_possible = True  # not possible for VMR errors
		for check, result in error_details.items():
			if not isinstance (result, dict):
				continue
			if ( not result['result'] ):
				if check == 'used_alignments_in_reports':
					check = Globals.LOCALIZATION.project_consistency_report_alignments
				elif check == 'alignment_required':
					check = Globals.LOCALIZATION.project_consistency_required_alignments
				elif check == 'reports':
					check = Globals.LOCALIZATION.project_consistency_report_status
				elif check == 'vmr':
					check = Globals.LOCALIZATION.project_consistency_vmr
					continue_possible = False
				elif check == 'measuring_setups':
					check = Globals.LOCALIZATION.project_consistency_measuring_setups
					continue_possible = False
				elif check == 'computation_status':
					check = Globals.LOCALIZATION.project_consistency_computation_status
					if not Globals.SETTINGS.OfflineMode:
						continue_possible = False
				elif check == 'path_status':
					check = Globals.LOCALIZATION.project_consistency_path_status
					if not Globals.SETTINGS.OfflineMode:
						continue_possible = False
				elif check == 'vmr_measurement_series':
					check = Globals.LOCALIZATION.project_consistency_vmr_measurement_series
					if not Globals.SETTINGS.OfflineMode:
						continue_possible = False
				elif check == 'measurement_parameters':
					check = Globals.LOCALIZATION.project_consistency_measurement_status
					if not Globals.SETTINGS.OfflineMode:
						continue_possible = False
				elif check == 'photogrammetry':
					check = Globals.LOCALIZATION.project_consistency_photogrammetry
					if not Globals.SETTINGS.OfflineMode:
						continue_possible = False
				elif check == 'clipboard':
					check = Globals.LOCALIZATION.project_consistency_nco
					if not Globals.SETTINGS.OfflineMode:
						continue_possible = False
				elif check == 'preview_mode':
					check = Globals.LOCALIZATION.project_consistency_preview_mode
					if not Globals.SETTINGS.OfflineMode:
						continue_possible = False
				elif check == 'non_master_actual_data':
					check = Globals.LOCALIZATION.project_consistency_non_master_actual_data
				elif check == 'non_master_actual_data_all_stages':
					continue

				detail = result['detail']
				if not len( detail ):
					continue
				if len( detail.split( '\n' ) ) > 6:
					detail = '\n'.join( detail.split( '\n' )[:6] )
					detail += '\n...'
				error += check + '<br/>' + detail + '\n'
		if error:
			error = error.rstrip()
			return Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.project_consistency_title,
				error, None, retry_enabled = continue_possible,
				retry_text = Globals.LOCALIZATION.errordialog_button_continue )

		return True

	def checkProjectConsistencyWithSensor( self ):
		'''
		Test project consistency, further checks which need initialized sensor.
		Show an error msg if an error occurs
		returns True, if no error occurs, or if worker pressed "Continue".
		Otherwise, False.
		'''
		# no two independent tritops per msetup allowed
		for wcfg in self.parent.Compatible_wcfgs:
			n = 0
			for tritop in self.parent.Comp_photo_series:
				ms = gom.app.project.measurement_series[tritop]
				if ( self.parent.Sensor.isMListPartOfMeasuringSetups( ms, [wcfg] )
					and ms.reference_points_master_series is None ):
					n += 1
			if n > 1:
				return Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.project_consistency_title,
					Globals.LOCALIZATION.project_consistency_2_indep_tritops, None, retry_enabled = False )

		return True


	def checkcalibration( self, series, errorlog = None ):
		'''
		test calibration result
		@return VerificationState.ErrorFree or VerificationState.Failure
		'''
		if Globals.SETTINGS.OfflineMode:
			return VerificationState.ErrorFree
		if isinstance( series, str ):
			series = gom.app.project.measurement_series[series]
		success = False
		try:
			# perform calibration checks
			calib_dev = float( gom.app.get ( 'sys_calibration_deviation' ) )
			calib_dev_limit = float( gom.app.get ( 'sys_limit_value_calibration_deviation' ) )
			calib_proj_dev = gom.app.get ( 'sys_calibration_projector_deviation' )
			calib_proj_dev_limit = None
			if calib_proj_dev is not None:  # if None: projector wasnt calibrated (on purpose)
				calib_proj_dev = float( calib_proj_dev )
				calib_proj_dev_limit = float( gom.app.get ( 'sys_limit_value_calibration_projector_deviation' ) )
			else:
				calib_proj_dev_limit = -1
				calib_proj_dev = -2
			status = series.get ( 'computation_status' )
			success = ( ( calib_dev < calib_dev_limit ) and ( calib_proj_dev < calib_proj_dev_limit ) and ( status == 'computed' ) )
			self.log.info( 'Calibration test: CalibrationDeviation: {:-f} < {:-f} and ProjectorDeviation {:-f} < {:-f} and ComputationStatus: {} == {}'.format( 
						calib_dev, calib_dev_limit, calib_proj_dev, calib_proj_dev_limit, status, success ) )
		except Globals.EXIT_EXCEPTIONS:
			raise
		except Exception as error:
			self.log.exception( str( error ) )
			success = False

		if success:
			return VerificationState.ErrorFree
		if errorlog is not None:
			errorlog.Error = Globals.LOCALIZATION.msg_verification_calibration_failed
		return VerificationState.Failure


class VerificationState ( Utils.EnumStructure ):
	'''
	Enum like structure for storing current measurement series status
	'''
	ErrorFree = 0  # no errors detected
	NeedsCalibration = 1  # calibration needed
	Failure = 2  # verification failure -> exit
	ReInitSensor = 3  # reinitialize sensor and retry
	Abort = 4  # exit
	UserAbort = 5
	Retry = 6  # retry possible
	RetryWithoutCounting = 7  # retry possible, but does not increase retry count
	MoveReverseHome = 8 # move reverse to home position
	TemperatureForcesCalibration = 9  # calibration needed (reason: temperature delta)
	OnlyInitSensor = 10  # initialize sensor and retry
		# this is for the case when tom server crashed but move server continues to run
		# ReInitSensor=3 will first de-init, this case will just try init, if possible

class DigitizeResult ( Utils.EnumStructure ):
	'''
	Enum like structure for storing digitize measurement result
	'''
	Success = 0
	Failure = 1
	RefPointMismatch = 2  # alignment residual between photogrammetry and digitize to big
	TransformationMarginReached = 3

class ErrorLog:
	'''
	Holder class of error msgs
	'''
	def __init__( self ):
		self._error = ''
		self._code = None

	@property
	def Error( self ):
		'''
		get method for error msg
		'''
		return self._error
	@Error.setter
	def Error( self, value ):
		'''
		set method for error msg, appends linebreak for each msg
		'''
		if len( self._error ):
			self._error += '\n'
		self._error += value
	@Error.deleter
	def Error( self ):
		'''
		clear errors
		'''
		self._error = ''
		self._code = None
	@property
	def Code( self ):
		'''
		get method for error code
		'''
		return self._code
	@Code.setter
	def Code( self, value ):
		'''
		set method for error code
		'''
		self._code = value