# -*- coding: utf-8 -*-
# Script: Temperature acquisition from user or software
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

# GOM-Script-Version: 7.6
#
# ChangeLog:
# 2017-04-11: Initial Creation (from the former WuT script)

import gom
from ..Misc import Utils, Globals


class Thermometer( Utils.GenericLogClass ):

	def __init__( self, logger, parent ):
		self.parent = parent
		Utils.GenericLogClass.__init__( self, logger )

	def _get_user_temperature( self ):
		'''
		internal function which asks the user for the current temperature,
		if not already asked. Sets the FixedTemperature setting member
		return temperature in float or None on decline
		'''
		temperature = Globals.SETTINGS.Thermometer_FixedTemperature
		if Globals.SETTINGS.Thermometer_ShowDialog:
			if self.parent.Dialog is not None:
				self.parent.Dialog.close_progressdialog()
			temperature = Globals.DIALOGS.show_temperature_dialog()
			if self.parent.Dialog is not None:
				self.parent.Dialog.open_progressdialog()
			if temperature is None:
				self.log.error( 'user declined temperature input' )
				return None
		Globals.SETTINGS.Thermometer_FixedTemperature = temperature
		Globals.SETTINGS.Thermometer_ShowDialog = False
		return temperature

	def update_temperature( self, calibration = None ):
		'''
		Updates measurement temperature under Acquisition->Acquisition Parameters
		if calibration measurement series is None and temperature acquisition method is one of the '*ask*' methods.
		
		Update both temperatures (calibration and measuring room) of the calibration measurement series
		if it is passed as a parameter to this function.
	
		Returns:
		True  - if the temperature was updated successfully
		False - otherwise
		'''
		# only for storing the user temperature in the acquisition parameters
		if gom.app.sys_measurement_temperature_source not in ["ask_if_required", "ask_per_project"]:
			return True

		temperature = self.get_temperature()
		calib_temperature = self.get_temperature(use_for_calibration=True)
		if temperature is None or calib_temperature is None:
			return False

		self.log.debug( 'Temperature: {}, Calibration temperature: {}'.format( temperature, calib_temperature ) )

		if calibration is not None:
			# set calibration and measuring room temperature for the calibration measurement series
			if isinstance( calibration, str ):
				calibration = gom.app.project.measurement_series[ calibration ]
			gom.script.calibration.edit_measurement_series ( 
				measurement_series = [calibration],
				temperature = calib_temperature,
				room_temperature = temperature )
		else:
			gom.script.sys.set_stage_parameters ( measurement_temperature = temperature )

		return True

	def get_temperature( self, use_for_calibration=False ):
		'''
		Requests the temperature in celsius.
		If "use_for_calibration" is True, get hardware value from special calibration thermometer.
		Returns:
		A float containing the temperature in Celsius or None if the hardware thermometers are not connected.
		'''
		if gom.app.sys_measurement_temperature_source == "use_fixed_room_temperature":
			return gom.app.sys_fixed_room_temperature

		if gom.app.sys_measurement_temperature_source in ["ask_if_required", "ask_per_project"]:
			return self._get_user_temperature()

		# if neither 'user' nor 'fixed' temperature, set a default temperature in offline mode
		if Globals.SETTINGS.OfflineMode:
			return 20.03

		# get hardware temperature
		if use_for_calibration:
			t = gom.app.sys_calibration_thermometer_temperature
			self.log.info( 'hardware temperature (calibration) {}'.format(t) )
			return t
		else:
			t = gom.app.sys_automated_system_thermometer_temperature
			self.log.info( 'hardware temperature {}'.format(t) )
			return t

		# never reached
		return None