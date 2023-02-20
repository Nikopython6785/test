# -*- coding: utf-8 -*-
# Script: Persistent Settings class
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
#ChangeLog:
# 2012-06-12: Initial Creation

import configparser, os, time, datetime

class PersistentSettings( object ):
	CFG_NAME = None

	_LastCalibration = 0
	_LastCalibrationFormat = '%Y/%m/%d %H:%M:%S'

	@property
	def LastCalibration( self ):
		return self._LastCalibration
	@LastCalibration.setter
	def LastCalibration( self, value ):
		self._LastCalibration = value
		self.write_settings()

	def __init__( self, savepath ):
		self.CFG_NAME = os.path.join( savepath, 'KioskInterface_persistantsettings.cfg' )
		self.read_settings()

	def read_settings( self ):
		config_parser_object = configparser.RawConfigParser()
		if config_parser_object.read( self.CFG_NAME, encoding='utf-8' ) == []:
			self.write_settings()
			config_parser_object.read( self.CFG_NAME, encoding='utf-8' )

		setting = self._safeget( config_parser_object, 'Calibration', 'LastCalibration' )
		if setting is not None:
			try:
				self._LastCalibration = time.mktime( time.strptime( setting, self._LastCalibrationFormat ) )
			except:
				pass
		self.read_additional_settings( config_parser_object )

	def read_additional_settings( self, config_parser_object ):
		pass

	_header = staticmethod( lambda cfgfile, head:       cfgfile.write( '[{0}]\n'.format( str( head ) ) ) )
	_writeln = staticmethod( lambda cfgfile, key, value:cfgfile.write( '{0} = {1}\n'.format( key, str( value ).replace( '\n', '\n\t' ) ) ) )
	_newline = staticmethod( lambda cfgfile :           cfgfile.write( '\n' ) )

	def write_settings( self ):
		with open( self.CFG_NAME, 'w', encoding='utf-8' ) as cfgfile:
			self._header( cfgfile, 'Calibration' )
			if self._LastCalibration != 0:
				date = datetime.datetime.fromtimestamp( self._LastCalibration )
			else:
				date = datetime.datetime (1970, 1, 1)
			self._writeln( cfgfile, 'LastCalibration', date.strftime( self._LastCalibrationFormat ) )

			self.write_additional_settings( cfgfile )

	def write_additional_settings( self, cfgfile ):
		pass

	@staticmethod
	def _safeget( config_parser_object, section, setting, boolean = False, integer = False, float = False ):
		'''
		Helper function for reading in config data
		'''
		try:
			if boolean:
				return config_parser_object.getboolean( section, setting )
			elif integer:
				return config_parser_object.getint( section, setting )
			elif float:
				return config_parser_object.getfloat( section, setting )
			else:
				return config_parser_object.get( section, setting )
		except:
			return None