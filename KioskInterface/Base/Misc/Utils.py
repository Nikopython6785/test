# -*- coding: utf-8 -*-
# Script: Misc classes and definitions
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
# 2012-11-26: Fixed GomSic path creation
# 2012-12-04: changed encoding to utf-8 with BOM for better compatibility
# 2013-01-22: Removed AutoDetectMeasurementSeries,MaxDigitizeMeasurementDeviation
#             Added PhotogrammetryVerify, MeasurementFailureMargin
# 2013-04-15: Removed SavePathFailed, added FailedPostfix since its now only a postfix
#             changed default value of TimeFormatProject (removed leading underscore)
# 2015-07-20: Added Language setting. New support function for importing language file.
# 2015-08-31: If 'import_localization' detects Messages CustomPatches:
#             Disable new localization and issue Deprecation Warning.
# 2016-04-26: Burn-In Limits, KnownSections List.

import gom

from . import DefaultSettings, LogClass, PersistentSettings, Globals

import codecs
import configparser
import datetime
from functools import wraps
import glob
import importlib
import inspect
import math
import logging
import os
import platform
import re
import sys
import time


class Settings( DefaultSettings.DefaultSettings ):
	'''
	Settings class holds all settings
	'''

	# list of handled configuration sections
	# 'WebThermometer Settings' and 'Burn-In Limits' no longer used
	# - retained for Setup script detection of known/additional sections
	KnownSections = [
		'Version Number', 'Compatibility', 'Background Trend Creation',
		'Asynchronous Evaluation', 'BarCodeScanner Settings',
		'WebThermometer Settings', 'Logging Settings', 'Dialog Settings',
		'Polygonization Settings', 'Photogrammetry Settings',
		'Calibration Settings', 'Digitizing Settings', 'Keywords',
		'Project Naming', 'Project Template Selection',
		'General Settings/Data Storage', 'Burn-In Limits', 'Inline', 'Evaluation Result',
		'DRC', 'MultiRobot', 'IOExtension', 'IoTConnection']

	# misc temp variables
	# Current... is the currently opened template,
	#   certain workflows store special values here (oneshot...)
	CurrentTemplate = None
	CurrentTemplateCfg = None
	CurrentTemplateIsConnected = False
	CurrentTemplateConnectedUrl = ''
	CurrentTemplateConnectedProjectId = ''
	# Copy of CurrentTemplate, when template is actually started
	#   This info is used to detect template switch, stored in TemplateWasChanged
	LastStartedTemplate = None
	TemplateWasChanged = False
	IsPhotogrammetryNeeded = True
	Thermometer_ShowDialog = False
	Thermometer_FixedTemperature = 21.0
	CurrentComprehensiveXML = None
	AllowAsyncAbort = False
	InAsyncAbort = False
	ShouldExit = False
	AlreadyExecutionPrepared = False
	LastFixturePositionCheckWasOk = False

	MoveDecisionAfterFaultState = 0
	WaitingForMoveDecision = False

	OrderByMSetups = False
	TrafoCodedPointIDs = []
	PointsUsedForTrafo = None

	Migrate_PrimaryExtension = None
	Migrate_DR_NoMListSelection = False
	Migrate_DR_AlignmentIteration = False
	Migrate_MultiPart = False
	Migrate_MultiPartPauseNeeded = False
	
	SoftwareDRCMode = None

	# compatibility with SW2019
	MultiPart = False
	MultiPartPauseNeeded = False

	# Special mode for manual multipart templates
	# - different trafo by common refpoints
	# - additional steps for measuring setup
	ManualMultiPartMode = False

	# Evaluation template mapping for multipart templates
	# empty => evaluate in open project
	# else  => contains a map from parts to evaluation templates
	PartEvaluationMap = {}


	def __init__( self, should_create = True, cfg_path = None ):
		'''
		Constructor function reads/writes the settings files
		'''
		DefaultSettings.DefaultSettings.__init__( self )
		self.settings_file_existed = False
		self.initialize( should_create, cfg_path )

	def initialize( self, should_create = True, cfg_path = None ):
		'''
		parse cfg file and stores a cfg file if needed
		'''
		config_parser_object = configparser.RawConfigParser()
		if cfg_path is not None:
			self.CFG_NAME = cfg_path

		if not self.read_file( config_parser_object ):
			self.settings_file_existed = False
			if not should_create:
				return
			self._storedefaultsettings()
			self.read_file( config_parser_object )
		else:
			self.settings_file_existed = True

		self._readsettings( config_parser_object, should_create )

	def settings_file_found( self ):
		return self.settings_file_existed

	def read_file( self, config_parser_object ):
		'''
		open and read configuration file as utf-8
		returns True on success else False
		'''
		if os.path.exists( self.CFG_NAME ):
			with codecs.open( self.CFG_NAME, 'r', encoding = "utf-8-sig" ) as cfgfile:
				config_parser_object.read_file( cfgfile )
				return True
		else:
			return False

	_header = staticmethod( lambda cfgfile, head:       cfgfile.write( '[{0}]\r\n'.format( str( head ) ) ) )
	_writeln = staticmethod( lambda cfgfile, key, value:cfgfile.write( '{0} = {1}\r\n'.format( key, str( value ).replace( '\n', '\n\t' ) ) ) )
	_comment = staticmethod( lambda cfgfile, comment:   cfgfile.write( '# {0}\r\n'.format( str( comment ) ) ) )
	_newline = staticmethod( lambda cfgfile :           cfgfile.write( '\r\n' ) )

	def _storedefaultsettings( self ):
		'''
		writes the settings into a file
		'''
		with codecs.open( self.CFG_NAME, 'w', encoding = "utf-8-sig" ) as cfgfile:
			self._header( cfgfile, 'General Settings/Data Storage' )
			self._comment( cfgfile, 'SavePath specifies the directory where all files' )
			self._comment( cfgfile, 'created by the Kiosk Interface should be stored' )
			self._writeln( cfgfile, 'SavePath', self.SavePath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'DemoMode is meant for development, testing and demonstration.' )
			self._comment( cfgfile, 'In this case the script will skip everything related to real hardware.' )
			self._writeln( cfgfile, 'DemoMode', self.OfflineMode )
			self._newline( cfgfile )
			self._comment( cfgfile, 'FailedPostfix is the postfix of result files which were not successfully processed by the Kiosk.' )
			self._comment( cfgfile, 'Default: failed' )
			self._writeln( cfgfile, 'FailedPostfix', self.FailedPostfix )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines if multiple templates should be executed at once.' )
			self._comment( cfgfile, 'Note: The setting has been renamed from "MultiPart" to avoid confusion with multipart scanning templates.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'BatchScan', self.BatchScan )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines if between multiple templates a pause dialog is needed' )
			self._comment( cfgfile, 'Note: The setting has been renamed from "MultiPartPauseNeeded" to avoid confusion with multipart scanning templates.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'BatchScanPauseNeeded', self.BatchScanPauseNeeded )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Allow abort during processing (in the progress bar)' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'AllowAbort', self.AllowAbort )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If activated the measurement series selection dialog is shown.' )
			self._comment( cfgfile, 'Measurement series can be selected for execution.' )
			self._comment( cfgfile, 'Otherwise, all measurement series are executed.' )
			self._comment( cfgfile, 'Without measurement series selection "AlignmentIteration" cannot be used.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'MSeriesSelection', self.MSeriesSelection )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If activated allows validate and rescan the project after a defined measurement series.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'AlignmentIteration', self.AlignmentIteration )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the warning limit for free disc space at the SavePath in MB' )
			self._comment( cfgfile, 'Set to 0 to disable the check' )
			self._comment( cfgfile, 'Default: 10000' )
			self._writeln( cfgfile, 'DiscFullWarningLimitSavePath', self.DiscFullWarningLimitSavePath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the error limit for free disc space at the SavePath in MB' )
			self._comment( cfgfile, 'Set to 0 to disable the check' )
			self._comment( cfgfile, 'Default: 3000' )
			self._writeln( cfgfile, 'DiscFullErrorLimitSavePath', self.DiscFullErrorLimitSavePath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the warning limit for free disc space at the log path in MB' )
			self._comment( cfgfile, 'Set to 0 to disable the check' )
			self._comment( cfgfile, 'Default: 300' )
			self._writeln( cfgfile, 'DiscFullWarningLimitLogPath', self.DiscFullWarningLimitLogPath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the error limit for free disc space at the log path in MB' )
			self._comment( cfgfile, 'Set to 0 to disable the check' )
			self._comment( cfgfile, 'Default: 100' )
			self._writeln( cfgfile, 'DiscFullErrorLimitLogPath', self.DiscFullErrorLimitLogPath )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Project Template Selection' )
			self._comment( cfgfile, 'ShowTemplateDialog specifies if the template has to be selected by the user or if a template' )
			self._comment( cfgfile, 'is selected by the script automatically. True means manual user selection, False means automatic' )
			self._comment( cfgfile, 'selection. Disable is not supported in combination with BatchScanning.' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'ShowTemplateDialog', self.ShowTemplateDialog )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines which project templates should be displayed, valid values are "shared", "user" or "both".' )
			self._comment( cfgfile, '"shared": project templates from the public folder. This setting is recommended.' )
			self._comment( cfgfile, '"user": project templates from the current user.' )
			self._comment( cfgfile, '"both": project templates from both locations are shown.' )
			self._comment( cfgfile, 'Default: shared' )
			self._writeln( cfgfile, 'TemplateConfigLevel', self.TemplateConfigLevel )
			self._newline( cfgfile )
			self._comment( cfgfile, 'TemplateName specifies the project template which will be used if the project template' )
			self._comment( cfgfile, 'is not requested from the user by the start dialog. See "ShowTemplateDialog".' )
			self._comment( cfgfile, 'Default: GOM-Training-Object.project_template' )
			self._writeln( cfgfile, 'TemplateName', self.TemplateName )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines which templates should be displayed, valied values are connected_project, project_template or both' )
			self._comment( cfgfile, 'Default: project_template' )
			self._writeln( cfgfile, 'TemplateCategory', self.TemplateCategory )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the servers for connected projects' )
			self._comment( cfgfile, 'Default: ""' )
			self._writeln( cfgfile, 'ConnectedProjectSources', ', '.join(self.ConnectedProjectSources) )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Project Naming' )
			self._comment( cfgfile, 'Autonaming will use the serial number and "TimeFormatProject" to name projects.' )
			self._comment( cfgfile, 'Otherwise the fixed "ProjectName" and "TimeFormatProject" will be used.' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'AutoNameProject', self.AutoNameProject )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If "AutoNameProject" is off, this project name will be used as a base name for the result projects.' )
			self._comment( cfgfile, 'Default: GOM-Training-Object' )
			self._writeln( cfgfile, 'ProjectName', self.ProjectName )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting specifies how date and time will be formatted for the project name.' )
			self._comment( cfgfile, 'Any order of the directives (i.e. everything beginning with %) is possible.' )
			self._comment( cfgfile, 'Default: %Y_%m_%d_%H_%M_%S (%Year_%Month_%Day_%Hour_%Minute_%Second) ' )
			self._writeln( cfgfile, 'TimeFormatProject', self.TimeFormatProject )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Keywords' )
			self._comment( cfgfile, 'If activated the current windows login name will be used and the entries in "Users" will be ignored.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'UseLoginName', self.UseLoginName )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting specifies how date and time will be formatted for the project keyword "Date".' )
			self._comment( cfgfile, 'Any order of the directives (i.e. everything beginning with %) is possible.' )
			self._comment( cfgfile, 'Default: %d/%m/%Y (%Day/%Month/%Year)' )
			self._writeln( cfgfile, 'TimeFormatProjectKeyword', self.TimeFormatProjectKeyword )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting controls how serial number input works for multi scanning part templates.' )
			self._comment( cfgfile, 'By standard one serial number per part is requested from the user and stored at the CAD part.' )
			self._comment( cfgfile, 'If you set this setting to True, only one overall batch serial number is used for all parts.' )
			self._comment( cfgfile, 'You can override this setting in a template with a project keyword "GOM_KIOSK_MultiPartBatchSerial".' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'MultiPartBatchSerial', self.MultiPartBatchSerial )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Digitizing Settings' )
			self._comment( cfgfile, 'If this is False, then the measurements are executed' )
			self._comment( cfgfile, 'with a cold sensor which may result in insufficient measurement data' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'WaitForSensorWarmUp', self.WaitForSensorWarmUp )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Maximum number of scan repetions. This means complete execution of a measurement series.' )
			self._comment( cfgfile, 'If none of the cycles are successful, then the measurement process is aborted with a warning dialog.' )
			self._comment( cfgfile, 'Default: 2' )
			self._writeln( cfgfile, 'MaxDigitizeRepetition', self.MaxDigitizeRepetition )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Percent of measurements which are allowed to fail due to transformation or projector residual failures.' )
			self._comment( cfgfile, 'Default: 0.1' )
			self._writeln( cfgfile, 'MeasurementFailureMargin', self.MeasurementFailureMargin )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Allow for higher fault-tolerance' )
			self._comment( cfgfile, 'Intersection online errors only lead to a calibration if three in a row fail, otherwise no scan data will be created')
			self._comment( cfgfile, 'Movement/Light and Intersection errors get ignored for polygonization as long as the failure margin is not reached.')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'HigherFaultTolerance', self.HigherFaultTolerance )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Check Fixture Position' )
			self._comment( cfgfile, 'If associated measurement series and nominal point components are available a position check can be executed')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'CheckFixturePosition', self.CheckFixturePosition )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Position check is only performed after template switch.')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'CheckFixturePositionOnlyOnTemplateSwitch', self.CheckFixturePositionOnlyOnTemplateSwitch )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Measurement series and nominal point components will remain in evaluated projects.')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'KeepCheckFixturePositionElements', self.KeepCheckFixturePositionElements )
			self._newline( cfgfile )
			self._comment( cfgfile, 'With this setting you can activate a check of the fixture when measurements' )
			self._comment( cfgfile, 'are repeated for alignment iteration.')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'CheckFixtureRepeat', self.CheckFixtureRepeat )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Direct Move is always allowed' )
			self._comment( cfgfile, 'Independent of the current setting if collision free paths are uncritical a direct move will be performed.')
			self._comment( cfgfile, 'This results in confirmation dialog blocking the workflow.')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'FreePathAlwaysAllowed', self.FreePathAlwaysAllowed )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Move all devices to global home at the end of the measurement process, e.g. closing gates.')
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'MoveAllDevicesToHome', self.MoveAllDevicesToHome )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Calibration Settings' )
			self._comment( cfgfile, 'If a new calibration becomes necessary less than' )
			self._comment( cfgfile, '"CalibrationMaxTimedelta" minutes after the last calibration,' )
			self._comment( cfgfile, 'the measurement process is aborted with a warning dialog.' )
			self._comment( cfgfile, 'Default: 10' )
			self._writeln( cfgfile, 'CalibrationMaxTimedelta', self.CalibrationMaxTimedelta )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If the time to the last calibration exceeds "CalibrationForcedTimedelta" minutes,' )
			self._comment( cfgfile, 'a new calibration is executed before starting atos measurements.' )
			self._comment( cfgfile, 'A value of 0 means no timeout.' )
			self._comment( cfgfile, 'Default: 0' )
			self._writeln( cfgfile, 'CalibrationForcedTimedelta', self.CalibrationForcedTimedelta )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If the flag CalibrationEachCycle is set, a new calibration is executed' )
			self._comment( cfgfile, 'in each Kiosk cycle before starting atos measurements.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'CalibrationEachCycle', self.CalibrationEachCycle )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Photogrammetry Settings' )
			self._comment( cfgfile, 'If PhotogrammetryOnlyIfRequired is False, the photogrammetry measurement series' )
			self._comment( cfgfile, 'will always be executed. Otherwise the Kiosk will check if there are' )
			self._comment( cfgfile, 'valid photogrammetry measurement data for the template from a previous execution' )
			self._comment( cfgfile, 'of the Kiosk.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'PhotogrammetryOnlyIfRequired', self.PhotogrammetryOnlyIfRequired )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If the stored photogrammetry measurement data is older than' )
			self._comment( cfgfile, '"PhotogrammetryMaxTimedeltaImport" minutes' )
			self._comment( cfgfile, 'a new photogrammetry measurement is executed.' )
			self._comment( cfgfile, 'Default: 1440' )
			self._writeln( cfgfile, 'PhotogrammetryMaxTimedeltaImport', self.PhotogrammetryMaxTimedeltaImport )
			self._newline( cfgfile )
			self._comment( cfgfile, 'PhotogrammetryMaxImportCount specifies the number of times stored Photogrammetry' )
			self._comment( cfgfile, 'data should be re-used. If set to 0 stored photogrammetry data will always be re-used.' )
			self._comment( cfgfile, 'Default: 0' )
			self._writeln( cfgfile, 'PhotogrammetryMaxImportCount', self.PhotogrammetryMaxImportCount )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If the stored photogrammetry data deviates more than "PhotogrammetryMaxTemperatureLimit"' )
			self._comment( cfgfile, 'degrees celsius from the current temperature, a new photogrammetry will be performed.' )
			self._comment( cfgfile, 'Default: 5' )
			self._writeln( cfgfile, 'PhotogrammetryMaxTemperatureLimit', self.PhotogrammetryMaxTemperatureLimit )
			self._newline( cfgfile )
			self._comment( cfgfile, 'A new photogrammetry measurement will be done if the project template' )
			self._comment( cfgfile, 'is switched even if a valid photogrammetry data file is found.' )
			self._comment( cfgfile, 'The recommended setting is "True".' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'PhotogrammetryForceOnTemplateSwitch', self.PhotogrammetryForceOnTemplateSwitch )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If adapters are needed for an analysis, an alignment or similar,' )
			self._comment( cfgfile, '"PhotogrammetryExportAdapters" allows to export those elements along with photogrammetry data.' )
			self._comment( cfgfile, 'The adapters will be stored in the corresponding ReferencePoint.refxml file.' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'PhotogrammetryExportAdapters', self.PhotogrammetryExportAdapters )
			self._newline( cfgfile )
			self._comment( cfgfile, 'PhotogrammetrySavePath is the name of the subfolder inside SavePath where' )
			self._comment( cfgfile, 'the photogrammetry data are stored.' )
			self._comment( cfgfile, 'Default: photogrammetry' )
			self._writeln( cfgfile, 'PhotogrammetrySavePath', self.PhotogrammetrySavePath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If set to "False" no photogrammetry verification checks are performed.' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'PhotogrammetryVerification', self.PhotogrammetryVerification )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If set to "True" project comprehensive photogrammetry will be used.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'PhotogrammetryComprehensive', self.PhotogrammetryComprehensive )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the number of scalebars which needs to be computed.' )
			self._comment( cfgfile, 'Otherwise photogrammetry verification will fail.' )
			self._comment( cfgfile, 'Default: 2' )
			self._writeln( cfgfile, 'PhotogrammetryNumberOfScaleBars', self.PhotogrammetryNumberOfScaleBars )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the ID range of coded reference points to be used for transformation' )
			self._comment( cfgfile, 'by common reference points in templates with more than one measuring setup' )
			self._comment( cfgfile, 'with photogrammetry measurement series. The format is a comma-seperated list' )
			self._comment( cfgfile, 'of individual ID numbers or ID ranges (<start ID> - <end ID>).' )
			self._comment( cfgfile, 'Examples: "30-39" or "5,6,12-14,20,35-38".' )
			self._comment( cfgfile, 'Default: empty' )
			self._writeln( cfgfile, 'PhotogrammetryCodedPointIDRange', self.PhotogrammetryCodedPointIDRange )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines if the photogrammetry is independent of the choosen template' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'PhotogrammetryIndependent', self.PhotogrammetryIndependent )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines if the alignment residual check reference points against mesh will be calculated in the async evaluation instance' )
			self._comment( cfgfile, 'Note: A failure will not force a photogrammetry for the current template')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'AsyncAlignmentResidualCheck', self.AsyncAlignmentResidualCheck )
			self._newline( cfgfile )

			self._header( cfgfile, 'Polygonization Settings' )
			self._comment( cfgfile, 'This section represents all settings which can influence polygonization.' )
			self._comment( cfgfile, 'They will be applied globally, meaning that every project will be treated with' )
			self._comment( cfgfile, 'these same settings.' )
			self._comment( cfgfile, 'IMPORTANT: Except for the "PerformPolygonization" switch, these settings' )
			self._comment( cfgfile, 'are not used in part-based projects!')
			self._comment( cfgfile, 'In part-based projects always the mode defined in the template will be used.')
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines if the polygonization should be performed' )
			self._comment( cfgfile, 'In part-based workflow "False" means to perform only a preview polygonization.' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'PerformPolygonization', self.PerformPolygonization )
			self._newline( cfgfile )

			self._comment( cfgfile, 'Defines if polygonize should fill the reference points' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'PolygonizeFillReferencePoints', self.PolygonizeFillReferencePoints )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the postprocessing method used for polygonize, valid values are:' )
			self._comment( cfgfile, '"no_postprocessing", "detailed", "standard", "removes_surface_roughness", "rough_inspection"' )
			self._comment( cfgfile, 'Default: removes_surface_roughness' )
			self._writeln( cfgfile, 'PolygonizeProcess', self.PolygonizeProcess )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If set to "True" memory consumption during polygonization is reduced at the cost of speed.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'PolygonizeLargeDataVolumes', self.PolygonizeLargeDataVolumes )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Evaluation Result' )
			self._comment( cfgfile, 'This setting is only used for custom exports in CustomPatches and the CustomPatchGenerator.')
			self._comment( cfgfile, 'You can specify the name of an alignment here which will be usable for custom exports.' )
			self._comment( cfgfile, 'If it is empty or the named alignment does not exist, the last alignment in the hierarchy is used.' )
			self._comment( cfgfile, 'If there is no unique last alignment, it is unspecified which one of the last alignments is used.' )
			self._comment( cfgfile, 'You can override this setting in a template with a project keyword "GOM_KIOSK_ResultAlignment".' )
			self._comment( cfgfile, 'Default: empty' )
			self._writeln( cfgfile, 'ResultAlignment', self.ResultAlignment )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting is the same as "ResultAlignment" but for multipart scanning templates.')
			self._comment( cfgfile, 'In multipart templates it is used as a name pattern for finding the alignment for a part.' )
			self._comment( cfgfile, 'For overriding use a project keyword "GOM_KIOSK_MPResultAlignmentPattern".' )
			self._comment( cfgfile, 'Default: empty' )
			self._writeln( cfgfile, 'MPResultAlignmentPattern', self.MPResultAlignmentPattern )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines, if the Kiosk exports the PDF report.' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'ExportPDF', self.ExportPDF )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Dialog Settings' )
			self._comment( cfgfile, 'Defines the selectable user names in the start dialog. Seperate the names with ";".' )
			self._comment( cfgfile, 'If "UseLoginName" is activated this setting is ignored.' )
			try:
				self._writeln( cfgfile, 'Users', ';'.join( Globals.DIALOGS.STARTDIALOG.userlist.items ) )
			except:
				self._writeln( cfgfile, 'Users', '' )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Paths to custom images, or empty for the default images' )
			self._writeln( cfgfile, 'LogoImage', self.LogoImage )
			self._writeln( cfgfile, 'InitializeImage', self.InitializeImage )
			self._writeln( cfgfile, 'PhotogrammetryImage', self.PhotogrammetryImage )
			self._writeln( cfgfile, 'DigitizeImage', self.DigitizeImage )
			self._writeln( cfgfile, 'CalibrationImage', self.CalibrationImage )
			self._writeln( cfgfile, 'ReportImage', self.ReportImage )
			self._writeln( cfgfile, 'TurnaroundFirstImage', self.TurnaroundFirstImage )
			self._writeln( cfgfile, 'TurnaroundImage', self.TurnaroundImage )
			self._writeln( cfgfile, 'TurnaroundCalibrationImage', self.TurnaroundCalibrationImage )
			self._writeln( cfgfile, 'MultiPartWaitImage', self.MultiPartWaitImage )

			self._newline( cfgfile )
			self._comment( cfgfile, 'Localization' )
			self._comment( cfgfile, 'No setting is equivalent to "en"' )
			self._writeln( cfgfile, 'Language', self.Language )

			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Logging Settings' )
			self._comment( cfgfile, 'LoggingLevel specifies the amount of logging information.' )
			self._comment( cfgfile, 'For logging the standard python functions are used. The options can be found here:' )
			self._comment( cfgfile, 'See http://docs.python.org/py3k/library/logging.html#logrecord-attributes for more information.' )
			self._writeln( cfgfile, 'LoggingLevel', logging.getLevelName( self.LoggingLevel ) )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Used logging format.' )
			self._comment( cfgfile, 'Default: %(asctime)s %(levelname)-8s Class(%(class)s) Func(%(funcName)s) Line(%(lineno)d) %(message)s' )
			self._writeln( cfgfile, 'LoggingFormat', self.LoggingFormat )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Detailed Traceback output.' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'VerboseTraceback', self.VerboseTraceback )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Format specifying how date and time will be represented.' )
			self._comment( cfgfile, 'Any order of the directives (i.e. everything beginning with %) is possible.' )
			self._comment( cfgfile, 'Default: _%Y_%m_%d_%H_%M_%S (_%Year_%Month_%Day_%Hour_%Minute_%Second)' )
			self._writeln( cfgfile, 'TimeFormatLogging', self.TimeFormatLogging )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting activates an additional log file in csv format to log evaluation statistics.' )
			self._comment( cfgfile, 'The logfile will be stored inside of the gom log folder as "KioskInterfaceStatistics.log".' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'LogStatistics', self.LogStatistics )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'BarCodeScanner Settings' )
			self._comment( cfgfile, 'Activate a connected barcode scanner.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'BarCodeScanner', self.BarCodeScanner )
			self._newline( cfgfile )
			self._comment( cfgfile, 'COM Port of the barcode scanner.' )
			self._comment( cfgfile, 'Default: 5' )
			self._writeln( cfgfile, 'BarCodeCOMPort', self.BarCodeCOMPort + 1 )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Delimiter sent after a complete barcode.' )
			self._comment( cfgfile, 'Default: \\r\\n' )
			self._writeln( cfgfile, 'BarCodeDelimiter', self.BarCodeDelimiter.encode( "unicode_escape" ).decode() )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If not empty defines the regular expression used to distinguish between fixture barcodes and part barcodes.' )
			self._comment( cfgfile, 'Default: empty' )
			self._writeln( cfgfile, 'SeparatedFixtureRegEx', self.SeparatedFixtureRegEx )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Asynchronous Evaluation' )
			self._comment( cfgfile, 'The Kiosk Interface supports a measuring software instance and additional software instances' )
			self._comment( cfgfile, 'that evaluate in the background.' )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If Async is "True", then "NumberOfClients" additional software instances are started for evaluation.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'Async', self.Async )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Number of software instances started for evaluation.' )
			self._comment( cfgfile, 'Default: 1' )
			self._writeln( cfgfile, 'NumberOfClients', self.NumberOfClients )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Specifies the address of the server, where the additional instance is started.' )
			self._comment( cfgfile, 'Currently, only the value "localhost" is supported.' )
			self._comment( cfgfile, 'Default: localhost' )
			self._writeln( cfgfile, 'HostAddress', self.HostAddress )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Specify the Port for the communication.' )
			self._comment( cfgfile, 'Default: 8081' )
			self._writeln( cfgfile, 'HostPort', self.HostPort )
			self._newline( cfgfile )
			self._comment( cfgfile, 'MeasureSavePath is the name of the subfolder inside SavePath where' )
			self._comment( cfgfile, 'the successfully measured projects are stored temporarily before evaluation.' )
			self._comment( cfgfile, 'Default: measured' )
			self._writeln( cfgfile, 'MeasureSavePath', self.MeasureSavePath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'If set an automatic evaluation of all elements is performed.' )
			self._comment( cfgfile, 'On failure the project gets marked as failed.' )
			self._comment( cfgfile, 'Default: True' )
			self._writeln( cfgfile, 'AutomaticResultEvaluation', self.AutomaticResultEvaluation )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self._header( cfgfile, 'Background Trend Creation' )
			self._comment( cfgfile, 'If enabled an additional software instance is started which creates' )
			self._comment( cfgfile, 'trend projects for all projects found within SavePath.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'BackgroundTrend', self.BackgroundTrend )
			self._comment( cfgfile, 'Defines the maximum number of stages for the trend projects.' )
			self._comment( cfgfile, 'Default: 10' )
			self._writeln( cfgfile, 'TrendMaxStageSize', self.TrendMaxStageSize )
			self._comment( cfgfile, 'If enabled show the trend instance fullscreen on a second monitor' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'ShowOnSecondMonitor', self.TrendShowOnSecondMonitor )
			self._newline( cfgfile )
			self._newline( cfgfile )

			if self.Inline:
				self._header( cfgfile, 'Inline' )
				self._comment( cfgfile, 'If enabled the KioskInterface only works via an external control instance' )
				self._comment( cfgfile, 'Default: False' )
				self._writeln( cfgfile, 'Inline', self.Inline )
				self._newline( cfgfile )
				self._comment( cfgfile, 'Inline PLC NetID' )
				self._comment( cfgfile, 'Default: 172.17.61.55.1.1' )
				self._writeln( cfgfile, 'InlinePLC_NetID', self.InlinePLC_NetID )
				self._newline( cfgfile )
				self._comment( cfgfile, 'Inline PLC Port' )
				self._comment( cfgfile, 'Default: 851' )
				self._writeln( cfgfile, 'InlinePLC_Port', self.InlinePLC_Port )
				self._newline( cfgfile )
				self._comment( cfgfile, 'This setting enables signals to the line plc that photogrammetry / calibration are recommended.' )
				self._comment( cfgfile, 'Activating it will change the meaning of the following settings to only signal a recommendation' )
				self._comment( cfgfile, 'instead of actually performing an action:' )
				self._comment( cfgfile, '"PhotogrammetryMaxTimedeltaImport" defines the time delta for a photogrammetry recommendation.' )
				self._comment( cfgfile, '"CalibrationForcedTimedelta" defines the time delta for a calibration recommendation.' )
				self._comment( cfgfile, 'Default: False' )
				self._writeln( cfgfile, 'EnableRecommendedSignals', self.EnableRecommendedSignals )
				self._newline( cfgfile )
				self._comment( cfgfile, 'Temperature Warning Limit. Triggers recommendation signals for photogrammetry and calibration.' )
				self._comment( cfgfile, 'Default: 3.0°C' )
				self._writeln( cfgfile, 'TemperatureWarningLimit', self.TemperatureWarningLimit )
				self._newline( cfgfile )
				self._newline( cfgfile )

			self._header( cfgfile, 'DRC' )
			self._comment( cfgfile, 'Activates the DoubleRobotCell Mode' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'DoubleRobotCell_Mode', self.DoubleRobotCell_Mode )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the IP Address of the Secondary PC' )
			self._comment( cfgfile, 'Default: 192.168.10.2' )
			self._writeln( cfgfile, 'SecondaryHostAddress', self.DoubleRobot_SecondaryHostAddress )
			self._newline( cfgfile )
			self._comment( cfgfile, 'Defines the TCP/IP port used for communication' )
			self._comment( cfgfile, 'Default: 40234' )
			self._writeln( cfgfile, 'SecondaryHostPort', self.DoubleRobot_SecondaryHostPort )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting defines the name part for measurement series on the Main side.' )
			self._comment( cfgfile, 'This name part is used to filter the measurement series on the Main.' )
			self._comment( cfgfile, 'Note: In demo mode this setting can also be used to load different templates' )
			self._comment( cfgfile, 'on Main/Secondary software instances.' )
			self._comment( cfgfile, 'Default: right' )
			self._writeln( cfgfile, 'MainExtension', self.DoubleRobot_MainExtension )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting defines the name part for measurement series on the Secondary side.' )
			self._comment( cfgfile, 'On the Secondary instance "MainExtension" is replaced by "SecondaryExtension" in the selected measurement series name.' )
			self._comment( cfgfile, 'Note: In demo mode this setting can also be used to load different templates' )
			self._comment( cfgfile, 'on Main/Secondary software instances.' )
			self._comment( cfgfile, 'Default: left' )
			self._writeln( cfgfile, 'SecondaryExtension', self.DoubleRobot_SecondaryExtension )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting controls if the reference cube positions after photogrammetry' )
			self._comment( cfgfile, 'should be checked. If there are any errors,' )
			self._comment( cfgfile, 'a dialog allows to correct the reference cubes and then retry photogrammetry' )
			self._comment( cfgfile, 'or continue operation without correction.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'RefCubeCheck', self.DoubleRobot_RefCubeCheck )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting controls whether the reference cube check controlled' )
			self._comment( cfgfile, 'by the "RefCubeCheck" option is done only once' )
			self._comment( cfgfile, 'or if the reference cube correction can be repeated endlessly.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'RefCubeCheckOnce', self.DoubleRobot_RefCubeCheckOnce )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting defines a folder for data exchange between Main and Secondary PCs.' )
			self._comment( cfgfile, 'This is the name of the folder on the Main PC.' )
			self._comment( cfgfile, 'Recommended setting is a folder in a network share on the Main PC' )
			self._comment( cfgfile, 'Default: D:/Share/Transfer' )
			self._writeln( cfgfile, 'TransferPath', self.DoubleRobot_TransferPath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting defines a temporary save folder for the Secondary PC' )
			self._comment( cfgfile, 'which is used for temporary projects and exports.' )
			self._comment( cfgfile, 'Recommended setting is a local folder on the Secondary PC.' )
			self._comment( cfgfile, 'Default: E:/DRCTemp' )
			self._writeln( cfgfile, 'ClientSavePath', self.DoubleRobot_ClientSavePath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting defines a folder for data exchange between Main and Secondary PCs.' )
			self._comment( cfgfile, 'This is the name of the folder on the Secondary PC.' )
			self._comment( cfgfile, 'Recommended setting is a folder in a network share on the Main PC' )
			self._comment( cfgfile, 'Default: E:/Share/Transfer' )
			self._writeln( cfgfile, 'ClientTransferPath', self.DoubleRobot_ClientTransferPath )
			self._newline( cfgfile )
			self._comment( cfgfile, 'This setting is only used by the Setup to define if the DRC should run in the protected Kiosk mode.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'KioskExecution', self.DoubleRobot_KioskExecution )
			self._newline( cfgfile )

			if self.MultiRobot_Mode: # to not confuse the users
				self._header( cfgfile, 'MultiRobot' )
				self._comment( cfgfile, 'Activates the MultiRobot Mode' )
				self._comment( cfgfile, 'Default: False' )
				self._writeln( cfgfile, 'MultiRobot_Mode', self.MultiRobot_Mode )
				self._newline( cfgfile )
				self._comment( cfgfile, 'Defines the IP Addresses of the Measurement PCs comma separated' )
				self._comment( cfgfile, 'Default: 192.168.10.2' )
				self._writeln( cfgfile, 'HostAddresses', ','.join(self.MultiRobot_HostAddresses) )
				self._newline( cfgfile )
				self._comment( cfgfile, 'Defines the TCP/IP port used for communication comma separated if different ports should be used.' )
				self._comment( cfgfile, 'Default: 40234' )
				self._writeln( cfgfile, 'HostPorts', ','.join([str(p) for p in self.MultiRobot_HostPorts]) )
				self._newline( cfgfile )
				self._comment( cfgfile, 'Defines the client side save path separated if different pathes should be used.' )
				self._comment( cfgfile, 'Default: d:/Temp' )
				self._writeln( cfgfile, 'ClientSavePath', ','.join(self.MultiRobot_ClientSavePath) )
				self._newline( cfgfile )
				self._comment( cfgfile, 'Defines the client side transfer path used for communication comma separated if different pathes should be used.' )
				self._comment( cfgfile, 'Default: d:/Temp' )
				self._writeln( cfgfile, 'ClientTransferPath', ','.join(self.MultiRobot_ClientTransferPath) )
				self._newline( cfgfile )
				self._comment( cfgfile, 'Defines the server side transfer path used for communication comma separated if different pathes should be used.' )
				self._comment( cfgfile, 'Default: d:/Temp' )
				self._writeln( cfgfile, 'TransferPath', ','.join(self.MultiRobot_TransferPath) )
				self._newline( cfgfile )
				
			self._header( cfgfile, 'IOExtension' )
			self._comment( cfgfile, 'If enabled signals the ScanBox IO Extension signals')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'IOExtensionEnabled', self.IOExtension )
			self._newline( cfgfile )
			self._comment( cfgfile, 'PLC NetID' )
			self._comment( cfgfile, 'Default: 172.17.61.55.1.1' )
			self._writeln( cfgfile, 'IOExtension_NetID', self.IOExtension_NetID )
			self._newline( cfgfile )
			self._comment( cfgfile, 'PLC Port' )
			self._comment( cfgfile, 'Default: 851' )
			self._writeln( cfgfile, 'IOExtension_Port', self.IOExtension_Port )
			self._newline( cfgfile )
			
			self._header( cfgfile, 'IoTConnection' )
			self._comment( cfgfile, 'If enabled communicates to IoT Solution')
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'IoTConnectionEnabled', self.IoTConnection )
			self._newline( cfgfile )
			self._comment( cfgfile, 'IoTConnection IP' )
			self._comment( cfgfile, 'Default: 127.0.0.1' )
			self._writeln( cfgfile, 'IoTConnection_IP', self.IoTConnection_IP )
			self._newline( cfgfile )
			self._comment( cfgfile, 'IoTConnection Port' )
			self._comment( cfgfile, 'Default: 10005' )
			self._writeln( cfgfile, 'IoTConnection_Port', self.IoTConnection_Port )
			self._newline( cfgfile )
				
			self._header( cfgfile, 'Compatibility' )
			self._comment( cfgfile, 'if enabled the old measuring setup dialog will be used,' )
			self._comment( cfgfile, 'e.g. for Tilt&Swivel Unit without measuring setups.' )
			self._comment( cfgfile, 'Default: False' )
			self._writeln( cfgfile, 'Compat_MeasuringSetup', self.Compat_MeasuringSetup )
			self._newline( cfgfile )
			self._newline( cfgfile )

			self.write_additional_settings( cfgfile )

			self._header( cfgfile, 'Version Number' )
			self._comment( cfgfile, 'Do not modify' )
			self._comment( cfgfile, 'Modifying will create a new configuration file.' )
			self._writeln( cfgfile, 'VERSION', self.VERSION )
			self._newline( cfgfile )

	def write_additional_settings( self, cfgfile ):
		'''
		placeholder function for patching additional settings into the config
		'''
		pass

	def _readsettings( self, config_parser_object, show_errors = True ):
		'''
		read settings from file
		'''
		if Globals.DIALOGS is None:  # initialize dialogs
			from .. import Dialogs
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'SavePath' )
		if res is not None and not self._is_patched_attribute( 'SavePath' ):
			self.SavePath = res
		self.SavePath = os.path.normpath( self.SavePath )

		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'DemoMode', boolean = True )
		if res is not None and not self._is_patched_attribute( 'OfflineMode' ):
			self.OfflineMode = res
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'FailedPostfix' )
		if res is not None and not self._is_patched_attribute( 'FailedPostfix' ):
			self.FailedPostfix = res
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'BatchScan', boolean = True )
		if res is not None and not self._is_patched_attribute( 'BatchScan' ):
			self.BatchScan = res
			self.MultiPart = res # compatibility
		# read MultiPart for migration
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'MultiPart', boolean = True )
		if res is not None:
			self.Migrate_MultiPart = res
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'BatchScanPauseNeeded', boolean = True )
		if res is not None and not self._is_patched_attribute( 'BatchScanPauseNeeded' ):
			self.BatchScanPauseNeeded = res
			self.MultiPartPauseNeeded = res # compatibility
		# read MultiPartPauseNeeded for migration
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'MultiPartPauseNeeded', boolean = True )
		if res is not None:
			self.Migrate_MultiPartPauseNeeded = res
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'AllowAbort', boolean = True )
		if res is not None and not self._is_patched_attribute( 'AllowAbort' ):
			self.AllowAbort = res
		gom.script.sys.set_kiosk_status_bar(enable_abort=self.AllowAbort)

		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'MSeriesSelection', boolean = True )
		if res is not None and not self._is_patched_attribute( 'MSeriesSelection' ):
			self.MSeriesSelection = res
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'AlignmentIteration', boolean = True )
		if res is not None and not self._is_patched_attribute( 'AlignmentIteration' ):
			self.AlignmentIteration = res

		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'DiscFullWarningLimitSavePath', integer = True )
		if res is not None and not self._is_patched_attribute( 'DiscFullWarningLimitSavePath' ):
			self.DiscFullWarningLimitSavePath = res
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'DiscFullErrorLimitSavePath', integer = True )
		if res is not None and not self._is_patched_attribute( 'DiscFullErrorLimitSavePath' ):
			self.DiscFullErrorLimitSavePath = res
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'DiscFullWarningLimitLogPath', integer = True )
		if res is not None and not self._is_patched_attribute( 'DiscFullWarningLimitLogPath' ):
			self.DiscFullWarningLimitLogPath = res
		res = self._safeget( config_parser_object, 'General Settings/Data Storage', 'DiscFullErrorLimitLogPath', integer = True )
		if res is not None and not self._is_patched_attribute( 'DiscFullErrorLimitLogPath' ):
			self.DiscFullErrorLimitLogPath = res

		res = self._safeget( config_parser_object, 'Project Template Selection', 'ShowTemplateDialog', boolean = True )
		if res is not None and not self._is_patched_attribute( 'ShowTemplateDialog' ):
			self.ShowTemplateDialog = res
		res = self._safeget( config_parser_object, 'Project Template Selection', 'TemplateConfigLevel' )
		if res is not None and not self._is_patched_attribute( 'TemplateConfigLevel' ):
			self.TemplateConfigLevel = res
		res = self._safeget( config_parser_object, 'Project Template Selection', 'TemplateName' )
		if res is not None and not self._is_patched_attribute( 'TemplateName' ):
			self.TemplateName = res
		res = self._safeget( config_parser_object, 'Project Template Selection', 'TemplateCategory' )
		if res is not None and not self._is_patched_attribute( 'TemplateCategory' ):
			self.TemplateCategory = res
		res = self._safeget( config_parser_object, 'Project Template Selection', 'ConnectedProjectSources' )
		if res is not None and not self._is_patched_attribute( 'ConnectedProjectSources' ):
			self.ConnectedProjectSources = [p.strip() for p in res.split(',')]

		res = self._safeget( config_parser_object, 'Project Naming', 'AutoNameProject', boolean = True )
		if res is not None  and not self._is_patched_attribute( 'AutoNameProject' ):
			self.AutoNameProject = res
		res = self._safeget( config_parser_object, 'Project Naming', 'ProjectName' )
		if res is not None  and not self._is_patched_attribute( 'ProjectName' ):
			self.ProjectName = res
		res = self._safeget( config_parser_object, 'Project Naming', 'TimeFormatProject' )
		if res is not None and not self._is_patched_attribute( 'TimeFormatProject' ):
			self.TimeFormatProject = res

		res = self._safeget( config_parser_object, 'Keywords', 'UseLoginName', boolean = True )
		if res is not None and not self._is_patched_attribute( 'UseLoginName' ):
			self.UseLoginName = res
		res = self._safeget( config_parser_object, 'Keywords', 'TimeFormatProjectKeyword' )
		if res is not None and not self._is_patched_attribute( 'TimeFormatProjectKeyword' ):
			self.TimeFormatProjectKeyword = res
		res = self._safeget( config_parser_object, 'Keywords', 'MultiPartBatchSerial', boolean = True )
		if res is not None and not self._is_patched_attribute( 'MultiPartBatchSerial' ):
			self.MultiPartBatchSerial = res

		res = self._safeget( config_parser_object, 'Digitizing Settings', 'WaitForSensorWarmUp', boolean = True )
		if res is not None and not self._is_patched_attribute( 'WaitForSensorWarmUp' ):
			self.WaitForSensorWarmUp = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'MaxDigitizeRepetition', integer = True )
		if res is not None and not self._is_patched_attribute( 'MaxDigitizeRepetition' ):
			self.MaxDigitizeRepetition = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'MeasurementFailureMargin', float = True )
		if res is not None and not self._is_patched_attribute( 'MeasurementFailureMargin' ):
			self.MeasurementFailureMargin = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'HigherFaultTolerance', boolean = True )
		if res is not None and not self._is_patched_attribute( 'HigherFaultTolerance' ):
			self.HigherFaultTolerance = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'CheckFixturePosition', boolean = True )
		if res is not None and not self._is_patched_attribute( 'CheckFixturePosition' ):
			self.CheckFixturePosition = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'CheckFixturePositionOnlyOnTemplateSwitch', boolean = True )
		if res is not None and not self._is_patched_attribute( 'CheckFixturePositionOnlyOnTemplateSwitch' ):
			self.CheckFixturePositionOnlyOnTemplateSwitch = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'KeepCheckFixturePositionElements', boolean = True )
		if res is not None and not self._is_patched_attribute( 'KeepCheckFixturePositionElements' ):
			self.KeepCheckFixturePositionElements = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'CheckFixtureRepeat', boolean = True )
		if res is not None and not self._is_patched_attribute( 'CheckFixtureRepeat' ):
			self.CheckFixtureRepeat = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'FreePathAlwaysAllowed', boolean = True )
		if res is not None and not self._is_patched_attribute( 'FreePathAlwaysAllowed' ):
			self.FreePathAlwaysAllowed = res
		res = self._safeget( config_parser_object, 'Digitizing Settings', 'MoveAllDevicesToHome', boolean = True )
		if res is not None and not self._is_patched_attribute( 'MoveAllDevicesToHome' ):
			self.MoveAllDevicesToHome = res

		res = self._safeget( config_parser_object, 'Calibration Settings', 'CalibrationMaxTimedelta', integer = True )
		if res is not None and not self._is_patched_attribute( 'CalibrationMaxTimedelta' ):
			self.CalibrationMaxTimedelta = res
		res = self._safeget( config_parser_object, 'Calibration Settings', 'CalibrationForcedTimedelta', integer = True )
		if res is not None and not self._is_patched_attribute( 'CalibrationForcedTimedelta' ):
			self.CalibrationForcedTimedelta = res
		res = self._safeget( config_parser_object, 'Calibration Settings', 'CalibrationEachCycle', boolean = True )
		if res is not None and not self._is_patched_attribute( 'CalibrationEachCycle' ):
			self.CalibrationEachCycle = res

		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryOnlyIfRequired', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryOnlyIfRequired' ):
			self.PhotogrammetryOnlyIfRequired = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryMaxTimedeltaImport', integer = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryMaxTimedeltaImport' ):
			self.PhotogrammetryMaxTimedeltaImport = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryMaxImportCount', integer = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryMaxImportCount' ):
			self.PhotogrammetryMaxImportCount = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryMaxTemperatureLimit', float = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryMaxTemperatureLimit' ):
			self.PhotogrammetryMaxTemperatureLimit = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryForceOnTemplateSwitch', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryForceOnTemplateSwitch' ):
			self.PhotogrammetryForceOnTemplateSwitch = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryExportAdapters', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryExportAdapters' ):
			self.PhotogrammetryExportAdapters = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetrySavePath' )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetrySavePath' ):
			self.PhotogrammetrySavePath = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryVerification', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryVerification' ):
			self.PhotogrammetryVerification = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryComprehensive', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryComprehensive' ):
			self.PhotogrammetryComprehensive = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryNumberOfScaleBars', integer = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryNumberOfScaleBars' ):
			self.PhotogrammetryNumberOfScaleBars = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryCodedPointIDRange' )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryCodedPointIDRange' ):
			self.PhotogrammetryCodedPointIDRange = res
		# conversion to TrafoCodedPointIDs happens in "check()"
		self.TrafoCodedPointIDs = []

		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'PhotogrammetryIndependent', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PhotogrammetryIndependent' ):
			self.PhotogrammetryIndependent = res
		res = self._safeget( config_parser_object, 'Photogrammetry Settings', 'AsyncAlignmentResidualCheck', boolean = True )
		if res is not None and not self._is_patched_attribute( 'AsyncAlignmentResidualCheck' ):
			self.AsyncAlignmentResidualCheck = res

		res = self._safeget( config_parser_object, 'Polygonization Settings', 'PerformPolygonization', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PerformPolygonization' ):
			self.PerformPolygonization = res
		res = self._safeget( config_parser_object, 'Polygonization Settings', 'PolygonizeFillReferencePoints', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PolygonizeFillReferencePoints' ):
			self.PolygonizeFillReferencePoints = res
		res = self._safeget( config_parser_object, 'Polygonization Settings', 'PolygonizeProcess' )
		if res is not None and not self._is_patched_attribute( 'PolygonizeProcess' ):
			self.PolygonizeProcess = res
		res = self._safeget( config_parser_object, 'Polygonization Settings', 'PolygonizeLargeDataVolumes', boolean = True )
		if res is not None and not self._is_patched_attribute( 'PolygonizeLargeDataVolumes' ):
			self.PolygonizeLargeDataVolumes = res

		res = self._safeget( config_parser_object, 'Evaluation Result', 'ResultAlignment' )
		if res is not None and not self._is_patched_attribute( 'ResultAlignment' ):
			self.ResultAlignment = res
		res = self._safeget( config_parser_object, 'Evaluation Result', 'MPResultAlignmentPattern' )
		if res is not None and not self._is_patched_attribute( 'MPResultAlignmentPattern' ):
			self.MPResultAlignmentPattern = res
		res = self._safeget( config_parser_object, 'Evaluation Result', 'ExportPDF', boolean = True )
		if res is not None and not self._is_patched_attribute( 'ExportPDF' ):
			self.ExportPDF = res

		users = self._safeget( config_parser_object, 'Dialog Settings', 'users' )
		if users is not None and not self._is_patched_attribute( 'users' ):
			# TODO keep as setting and move the split to Workflow.Startup**
			for dialog in [Globals.DIALOGS.STARTDIALOG, Globals.DIALOGS.STARTDIALOG_FIXTURE]:
				try:
					dialog.userlist.items = users.split( ';' )
				except:
					pass
		res = self._safeget( config_parser_object, 'Dialog Settings', 'LogoImage' )
		if not self._is_patched_attribute( 'LogoImageBinary' ):
			if res is None or len( res ) == 0:
				self.LogoImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_logo.data
				self.LogoImage = ''
			else:
				try:
					self.LogoImage = res
					self.LogoImageBinary = self._load_image( self.LogoImage )
				except:
					self.LogoImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_logo.data
					self.LogoImage = ''

		res = self._safeget( config_parser_object, 'Dialog Settings', 'PhotogrammetryImage' )
		if not self._is_patched_attribute( 'PhotogrammetryImageBinary' ):
			if res is None or len( res ) == 0:
				self.PhotogrammetryImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_photogrammetry.data
				self.PhotogrammetryImage = ''
			else:
				try:
					self.PhotogrammetryImage = res
					self.PhotogrammetryImageBinary = self._load_image( self.PhotogrammetryImage )
				except:
					self.PhotogrammetryImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_photogrammetry.data
					self.PhotogrammetryImage = ''
		res = self._safeget( config_parser_object, 'Dialog Settings', 'DigitizeImage' )
		if not self._is_patched_attribute( 'DigitizeImageBinary' ):
			if res is None or len( res ) == 0:
				self.DigitizeImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_digitize.data
				self.DigitizeImage = ''
			else:
				try:
					self.DigitizeImage = res
					self.DigitizeImageBinary = self._load_image( self.DigitizeImage )
				except:
					self.DigitizeImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_digitize.data
					self.DigitizeImage = ''
		res = self._safeget( config_parser_object, 'Dialog Settings', 'ReportImage' )
		if not self._is_patched_attribute( 'ReportImageBinary' ):
			if res is None or len( res ) == 0:
				self.ReportImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_report.data
				self.ReportImage = ''
			else:
				try:
					self.ReportImage = res
					self.ReportImageBinary = self._load_image( self.ReportImage )
				except:
					self.ReportImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_report.data
					self.ReportImage = ''
		res = self._safeget( config_parser_object, 'Dialog Settings', 'CalibrationImage' )
		if not self._is_patched_attribute( 'CalibrationImageBinary' ):
			if res is None or len( res ) == 0:
				self.CalibrationImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_calibration.data
				self.CalibrationImage = ''
			else:
				try:
					self.CalibrationImage = res
					self.CalibrationImageBinary = self._load_image( self.CalibrationImage )
				except:
					self.CalibrationImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_calibration.data
					self.CalibrationImage = ''
		res = self._safeget( config_parser_object, 'Dialog Settings', 'InitializeImage' )
		if not self._is_patched_attribute( 'InitializeImageBinary' ):
			if res is None or len( res ) == 0:
				self.InitializeImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_init.data
				self.InitializeImage = ''
			else:
				try:
					self.InitializeImage = res
					self.InitializeImageBinary = self._load_image( self.InitializeImage )
				except:
					self.InitializeImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_init.data
					self.InitializeImage = ''

		res = self._safeget( config_parser_object, 'Dialog Settings', 'TurnaroundFirstImage' )
		if not self._is_patched_attribute( 'TurnaroundFirstBinary' ):
			if res is None or len( res ) == 0:
				self.TurnaroundFirstImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_turnaround_first.data
				self.TurnaroundFirstImage = ''
			else:
				try:
					self.TurnaroundFirstImage = res
					self.TurnaroundFirstImageBinary = self._load_image( self.TurnaroundFirstImage )
				except:
					self.TurnaroundFirstImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_turnaround_first.data
					self.TurnaroundFirstImage = ''
		res = self._safeget( config_parser_object, 'Dialog Settings', 'TurnaroundImage' )
		if not self._is_patched_attribute( 'TurnaroundImageBinary' ):
			if res is None or len( res ) == 0:
				self.TurnaroundImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_turnaround.data
				self.TurnaroundImage = ''
			else:
				try:
					self.TurnaroundImage = res
					self.TurnaroundImageBinary = self._load_image( self.TurnaroundImage )
				except:
					self.TurnaroundImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_turnaround.data
					self.TurnaroundImage = ''
		res = self._safeget( config_parser_object, 'Dialog Settings', 'TurnaroundCalibrationImage' )
		if not self._is_patched_attribute( 'TurnaroundCalibrationImageBinary' ):
			if res is None or len( res ) == 0:
				self.TurnaroundCalibrationImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_turnaround_calib.data
				self.TurnaroundCalibrationImage = ''
			else:
				try:
					self.TurnaroundCalibrationImage = res
					self.TurnaroundCalibrationImageBinary = self._load_image( self.TurnaroundCalibrationImage )
				except:
					self.TurnaroundCalibrationImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_turnaround_calib.data
					self.TurnaroundCalibrationImage = ''

		res = self._safeget( config_parser_object, 'Dialog Settings', 'MultiPartWaitImage' )
		if not self._is_patched_attribute( 'MultiPartWaitImageBinary' ):
			if res is None or len( res ) == 0:
				self.MultiPartWaitImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_transparent.data  # no default image
				self.MultiPartWaitImage = ''
			else:
				try:
					self.MultiPartWaitImage = res
					self.MultiPartWaitImageBinary = self._load_image( self.MultiPartWaitImage )
				except:
					self.MultiPartWaitImageBinary = Globals.DIALOGS.IMAGE_CONTAINER_DIALOG.image_transparent.data  # no default image
					self.MultiPartWaitImage = ''

		res = self._safeget( config_parser_object, 'Dialog Settings', 'Language' )
		if res is not None and not self._is_patched_attribute( 'Language' ):
			self.Language = res

		res = self._safeget( config_parser_object, 'Logging Settings', 'LoggingLevel' )
		if res is not None and not self._is_patched_attribute( 'LoggingLevel' ):
			self.LoggingLevel = logging.getLevelName( res )
		res = self._safeget( config_parser_object, 'Logging Settings', 'LoggingFormat' )
		if res is not None and not self._is_patched_attribute( 'LoggingFormat' ):
			self.LoggingFormat = res
		res = self._safeget( config_parser_object, 'Logging Settings', 'VerboseTraceback', boolean = True )
		if res is not None and not self._is_patched_attribute( 'VerboseTraceback' ):
			self.VerboseTraceback = res
		if self.VerboseTraceback:
			logging.Formatter.formatException = LogClass.formatException
		res = self._safeget( config_parser_object, 'Logging Settings', 'TimeFormatLogging' )
		if res is not None and not self._is_patched_attribute( 'TimeFormatLogging' ):
			self.TimeFormatLogging = res
		res = self._safeget( config_parser_object, 'Logging Settings', 'LogStatistics', boolean = True )
		if res is not None and not self._is_patched_attribute( 'LogStatistics' ):
			self.LogStatistics = res

		res = self._safeget( config_parser_object, 'BarCodeScanner Settings', 'BarCodeScanner', boolean = True )
		if res is not None and not self._is_patched_attribute( 'BarCodeScanner' ):
			self.BarCodeScanner = res
		res = self._safeget( config_parser_object, 'BarCodeScanner Settings', 'BarCodeCOMPort', integer = True )
		if res is not None and not self._is_patched_attribute( 'BarCodeCOMPort' ):
			self.BarCodeCOMPort = res - 1
		res = self._safeget( config_parser_object, 'BarCodeScanner Settings', 'BarCodeDelimiter' )
		if res is not None and not self._is_patched_attribute( 'BarCodeDelimiter' ):
			self.BarCodeDelimiter = bytes( res, "utf-8" ).decode( "unicode_escape" )
		res = self._safeget( config_parser_object, 'BarCodeScanner Settings', 'SeparatedFixtureRegEx' )
		if res is not None and not self._is_patched_attribute( 'SeparatedFixtureRegEx' ):
			self.SeparatedFixtureRegEx = res

		res = self._safeget( config_parser_object, 'Asynchronous Evaluation', 'Async', boolean = True )
		if res is not None and not self._is_patched_attribute( 'Async' ):
			self.Async = res
		res = self._safeget( config_parser_object, 'Asynchronous Evaluation', 'NumberOfClients', integer = True )
		if res is not None and not self._is_patched_attribute( 'NumberOfClients' ):
			res = min( 2, res )
			self.NumberOfClients = res
		res = self._safeget( config_parser_object, 'Asynchronous Evaluation', 'HostAddress' )
		if res is not None and not self._is_patched_attribute( 'HostAddress' ):
			self.HostAddress = res
		res = self._safeget( config_parser_object, 'Asynchronous Evaluation', 'HostPort', integer = True )
		if res is not None and not self._is_patched_attribute( 'HostPort' ):
			self.HostPort = res
		res = self._safeget( config_parser_object, 'Asynchronous Evaluation', 'MeasureSavePath' )
		if res is not None and not self._is_patched_attribute( 'MeasureSavePath' ):
			self.MeasureSavePath = res
		res = self._safeget( config_parser_object, 'Asynchronous Evaluation', 'AutomaticResultEvaluation', boolean = True )
		if res is not None and not self._is_patched_attribute( 'AutomaticResultEvaluation' ):
			self.AutomaticResultEvaluation = res

		res = self._safeget( config_parser_object, 'Background Trend Creation', 'BackgroundTrend', boolean = True )
		if res is not None and not self._is_patched_attribute( 'BackgroundTrend' ):
			self.BackgroundTrend = res
		res = self._safeget( config_parser_object, 'Background Trend Creation', 'TrendMaxStageSize', integer = True )
		if res is not None and not self._is_patched_attribute( 'TrendMaxStageSize' ):
			self.TrendMaxStageSize = res
		res = self._safeget( config_parser_object, 'Background Trend Creation', 'ShowOnSecondMonitor', boolean = True )
		if res is not None and not self._is_patched_attribute( 'ShowOnSecondMonitor' ):
			self.TrendShowOnSecondMonitor = res

		res = self._safeget( config_parser_object, 'Inline', 'Inline', boolean = True )
		if res is not None and not self._is_patched_attribute( 'Inline' ):
			self.Inline = res
		res = self._safeget( config_parser_object, 'Inline', 'InlinePLC_NetID' )
		if res is not None and not self._is_patched_attribute( 'InlinePLC_NetID' ):
			self.InlinePLC_NetID = res
		res = self._safeget( config_parser_object, 'Inline', 'InlinePLC_Port', integer = True )
		if res is not None and not self._is_patched_attribute( 'InlinePLC_Port' ):
			self.InlinePLC_Port = res
		res = self._safeget( config_parser_object, 'Inline', 'EnableRecommendedSignals', boolean = True )
		if res is not None and not self._is_patched_attribute( 'EnableRecommendedSignals' ):
			self.EnableRecommendedSignals = res
			
		res = self._safeget( config_parser_object, 'Inline', 'TemperatureWarningLimit', float = True )
		if res is not None and not self._is_patched_attribute( 'TemperatureWarningLimit' ):
			self.TemperatureWarningLimit = res

		res = self._safeget( config_parser_object, 'DRC', 'DoubleRobotCell_Mode', boolean = True )
		if res is not None and not self._is_patched_attribute( 'DoubleRobotCell_Mode' ):
			self.DoubleRobotCell_Mode = res
		res = self._safeget( config_parser_object, 'DRC', 'SecondaryHostAddress' )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_SecondaryHostAddress' ):
			self.DoubleRobot_SecondaryHostAddress = res
		res = self._safeget( config_parser_object, 'DRC', 'SecondaryHostPort', integer = True )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_SecondaryHostPort' ):
			self.DoubleRobot_SecondaryHostPort = res
		res = self._safeget( config_parser_object, 'DRC', 'MainExtension' )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_MainExtension' ):
			self.DoubleRobot_MainExtension = res
		# read PrimaryExtension for migration
		res = self._safeget( config_parser_object, 'DRC', 'PrimaryExtension' )
		if res is not None:
			self.Migrate_PrimaryExtension = res
		res = self._safeget( config_parser_object, 'DRC', 'SecondaryExtension' )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_SecondaryExtension' ):
			self.DoubleRobot_SecondaryExtension = res
		# read AlignmentIteration and NoMlistSelection for migration
		res = self._safeget( config_parser_object, 'DRC', 'AlignmentIteration', boolean = True )
		if res is not None:
			self.Migrate_DR_AlignmentIteration = res
		res = self._safeget( config_parser_object, 'DRC', 'NoMlistSelection', boolean = True )
		if res is not None:
			self.Migrate_DR_NoMListSelection = res
		res = self._safeget( config_parser_object, 'DRC', 'RefCubeCheck', boolean = True )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_RefCubeCheck' ):
			self.DoubleRobot_RefCubeCheck = res
		res = self._safeget( config_parser_object, 'DRC', 'RefCubeCheckOnce', boolean = True )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_RefCubeCheckOnce' ):
			self.DoubleRobot_RefCubeCheckOnce = res
		res = self._safeget( config_parser_object, 'DRC', 'TransferPath' )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_TransferPath' ):
			self.DoubleRobot_TransferPath = res
		res = self._safeget( config_parser_object, 'DRC', 'ClientSavePath' )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_ClientSavePath' ):
			self.DoubleRobot_ClientSavePath = res
		res = self._safeget( config_parser_object, 'DRC', 'ClientTransferPath' )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_ClientTransferPath' ):
			self.DoubleRobot_ClientTransferPath = res
		res = self._safeget( config_parser_object, 'DRC', 'KioskExecution' )
		if res is not None and not self._is_patched_attribute( 'DoubleRobot_KioskExecution' ):
			self.DoubleRobot_KioskExecution = res
			
			
		res = self._safeget( config_parser_object, 'MultiRobot', 'MultiRobot_Mode', boolean = True )
		if res is not None and not self._is_patched_attribute( 'MultiRobot_Mode' ):
			self.MultiRobot_Mode = res
		res = self._safeget( config_parser_object, 'MultiRobot', 'HostAddresses' )
		if res is not None and not self._is_patched_attribute( 'MultiRobot_HostAddresses' ):
			self.MultiRobot_HostAddresses = [ip.strip() for ip in res.split(',')]
		res = self._safeget( config_parser_object, 'MultiRobot', 'HostPorts' )
		if res is not None and not self._is_patched_attribute( 'MultiRobot_HostPorts' ):
			self.MultiRobot_HostPorts = [int(port.strip()) for port in res.split(',')]
		res = self._safeget( config_parser_object, 'MultiRobot', 'ClientSavePath' )
		if res is not None and not self._is_patched_attribute( 'MultiRobot_ClientSavePath' ):
			self.MultiRobot_ClientSavePath = [path.strip() for path in res.split(',')]
		res = self._safeget( config_parser_object, 'MultiRobot', 'ClientTransferPath' )
		if res is not None and not self._is_patched_attribute( 'MultiRobot_ClientTransferPath' ):
			self.MultiRobot_ClientTransferPath = [path.strip() for path in res.split(',')]
		res = self._safeget( config_parser_object, 'MultiRobot', 'TransferPath' )
		if res is not None and not self._is_patched_attribute( 'MultiRobot_TransferPath' ):
			self.MultiRobot_TransferPath = [path.strip() for path in res.split(',')]

		
		res = self._safeget( config_parser_object, 'IOExtension', 'IOExtensionEnabled', boolean = True )
		if res is not None and not self._is_patched_attribute( 'IOExtension' ):
			self.IOExtension = res
		res = self._safeget( config_parser_object, 'IOExtension', 'IOExtension_NetID' )
		if res is not None and not self._is_patched_attribute( 'IOExtension_NetID' ):
			self.IOExtension_NetID = res
		res = self._safeget( config_parser_object, 'IOExtension', 'IOExtension_Port', integer = True )
		if res is not None and not self._is_patched_attribute( 'IOExtension_Port' ):
			self.IOExtension_Port = res
			
		res = self._safeget( config_parser_object, 'IoTConnection', 'IoTConnectionEnabled', boolean = True )
		if res is not None and not self._is_patched_attribute( 'IoTConnection' ):
			self.IoTConnection = res
		res = self._safeget( config_parser_object, 'IoTConnection', 'IoTConnection_IP' )
		if res is not None and not self._is_patched_attribute( 'IoTConnection_IP' ):
			self.IoTConnection_IP = res
		res = self._safeget( config_parser_object, 'IoTConnection', 'IoTConnection_Port', integer = True )
		if res is not None and not self._is_patched_attribute( 'IoTConnection_Port' ):
			self.IoTConnection_Port = res


		res = self._safeget( config_parser_object, 'Compatibility', 'Compat_MeasuringSetup', boolean = True )
		if res is not None and not self._is_patched_attribute( 'Compat_MeasuringSetup' ):
			self.Compat_MeasuringSetup = res

		self.read_additional_settings( config_parser_object )

		res = self._safeget( config_parser_object, 'Version Number', 'VERSION' )
		if res != self.VERSION:
			# settings auto migration hook
			self.migrate_settings( res, self.VERSION )
			self._storedefaultsettings()

	def read_additional_settings( self, config_parser_object ):
		'''
		placeholder function for patching additional settings into the config
		'''
		pass

	def check( self, silent=False ):
		'''
		Check settings. Typically called after reading config file. Abort on inconsistent settings.
		'''
		err_list = []

		if not os.path.exists( self.SavePath ):
			try:
				os.makedirs( self.SavePath )
			except:
				err_list.append( Globals.LOCALIZATION.msg_settings_savepath_failed.format( self.SavePath ) )

		if self.TemplateConfigLevel not in ['shared', 'user', 'both']:
			err_list.append( Globals.LOCALIZATION.msg_setting_invalid.format( 'TemplateConfigLevel' ))
		if not self.ShowTemplateDialog and self.TemplateConfigLevel not in ['shared', 'user']:
			err_list.append( Globals.LOCALIZATION.msg_setting_invalid.format( 'TemplateConfigLevel' ))

		# PhotogrammetryComprehensive and PhotogrammetryIndependent are mutually exclusive.
		#  (Current code gives precedence to PhotogrammetryComprehensive)
		if self.PhotogrammetryIndependent and self.PhotogrammetryComprehensive:
			err_list.append( Globals.LOCALIZATION.msg_settings_comprehensive_independent )

		# conversion step for coded refpoints spec for mmt transformation
		if len( self.PhotogrammetryCodedPointIDRange.strip() ) > 0:
			try:
				ids = self.PhotogrammetryCodedPointIDRange.strip().split( ',' )
				ids = [e.split( '-' ) for e in ids]
				for e in ids:
					if len( e ) == 1:
						self.TrafoCodedPointIDs.append( int( e[0] ) )
					elif len( e ) == 2:
						self.TrafoCodedPointIDs += list( range( int( e[0] ), int( e[1] ) + 1 ) )
					else:
						raise ValueError( "Ill-formed range" )
			except Exception as e:
				err_list.append( Globals.LOCALIZATION.msg_settings_idrange_failed.format(
					self.PhotogrammetryCodedPointIDRange ) )

		if self.PolygonizeProcess not in [
				'no_postprocessing', 'detailed', 'standard', 'removes_surface_roughness', 'rough_inspection']:
			err_list.append( Globals.LOCALIZATION.msg_setting_invalid.format( 'PolygonizeProcess' ) )

		# ClientSavePath and ClientTransferPath must be different.
		if self.DoubleRobot_ClientSavePath == self.DoubleRobot_ClientTransferPath:
			err_list.append( Globals.LOCALIZATION.msg_settings_secondary_paths )

		# MaxDigitizeRepetition >= 1
		if self.MaxDigitizeRepetition < 1:
			err_list.append( Globals.LOCALIZATION.msg_settings_repetition_value )

		# MeasurementFailureMargin [0..1]
		if self.MeasurementFailureMargin < 0.0 or self.MeasurementFailureMargin > 1.0:
			err_list.append( Globals.LOCALIZATION.msg_settings_failmargin_value )
			
		if self.Inline and self.IOExtension:
			err_list.append( Globals.LOCALIZATION.msg_settings_inline_ioextension )

		if len( err_list ) > 0 and not silent:
			if Globals.DIALOGS is not None:
				Globals.DIALOGS.show_errormsg(
					Globals.LOCALIZATION.msg_settings_errortitle,
					'\n'.join( err_list ), self.SavePath, False )
				sys.exit( 0 )

		return err_list

	def check_warnings( self, logger ):
		'''
		Check settings. Log warnings on dubious combinations of settings.
		'''
		warn_list = []

		# PhotogrammetryComprehensive is only usable with BatchScan
		if self.PhotogrammetryComprehensive and not self.BatchScan:
			warn_list.append( Globals.LOCALIZATION.msg_settings_comprehensive_batchscan )

		# AlignmentIteration makes no sense without MSeriesSelection.
		if self.AlignmentIteration and not self.MSeriesSelection:
			warn_list.append( Globals.LOCALIZATION.msg_settings_aligniter_nomlist )

		if len(warn_list) > 0:
			for w in warn_list:
				logger.warn( w )

	def version_info( self, version ):
		'''Helper function to extract Kiosk settings file version from version string as 2-tuple
					Overwrite in sub classes to extract extension version.
		'''
		try:
			m = re.search(r"^([0-9]*)\.([0-9]*)", version)
			# Note: group(0) would be the complete match
			return (int(m.group(1)), int(m.group(2)))
		except:
			return None

	def migrate_settings( self, from_version, to_version ):
		'''Settings migration hook
					This function is called after reading settings
					from a settings file with an older version.
		'''
		from_kiosk = self.version_info( from_version )
		to_kiosk = self.version_info( to_version )

		if from_kiosk is not None and to_kiosk is not None:
			if from_kiosk == (0, 90) and to_kiosk >= (0, 91):
				self.DoubleRobot_MainExtension = self.Migrate_PrimaryExtension
			if ((0, 88) <= from_kiosk <= (0, 93)) and to_kiosk >= (0, 94):
				# For DRC Mode migrate mseries selection and alignment iteration settings
				if self.DoubleRobotCell_Mode:
					self.MSeriesSelection = not self.Migrate_DR_NoMListSelection
					self.AlignmentIteration = self.Migrate_DR_AlignmentIteration
			if from_kiosk <= (0, 95) and to_kiosk >= (0, 96):
				self.BatchScan = self.Migrate_MultiPart
				self.MultiPart = self.Migrate_MultiPart # compatibility
				self.BatchScanPauseNeeded = self.Migrate_MultiPartPauseNeeded
				self.MultiPartPauseNeeded = self.Migrate_MultiPartPauseNeeded # compatibility

	def _is_patched_attribute( self, name ):
		'''
		returns True if the attribute is user patched, else False
		'''
		try:
			getattr( self, 'original__' + name )
			return True
		except:
			return False

	def __getattribute__( self, key ):
		'''
		checks if a projectkeyword with the given name exists and returns the value of it
		instead of the cfg value
		format of the projectkeyword has to be GOM_KIOSK_[name of the settingname]
		'''
		if key in DefaultSettings.DefaultSettings.__dict__:
			try:
				override = gom.app.project.get( 'user_GOM_KIOSK_{}'.format( key ) )
				original = object.__getattribute__( self, key )
				if type( original ) == int:
					return int( override )
				elif type( original ) == float:
					return float( override )
				elif type( original ) == bool:
					if override == 'True':
						return True
					if override == 'False':
						return False
				else:
					return override
			except:
				return object.__getattribute__( self, key )
		return object.__getattribute__( self, key )

	@staticmethod
	def _safeget( config_parser_object, section, setting,
						boolean = False, integer = False, float = False ):
		'''
		helper function for reading
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

	@staticmethod
	def _load_image( file_name ):
		'''
		load and read image from disk
		'''
		file = None
		bytestring = None
		try:
			file = os.open ( file_name, os.O_RDONLY | os.O_BINARY )
			bytestring = os.read ( file, os.fstat ( file ).st_size )
		except Globals.EXIT_EXCEPTIONS:
			raise
		finally:
			try:
				os.close( file )
			except:
				pass
		return bytestring


def RuntimeSafeLoopDelegate( func, errormsg, logger, dialog, sic_path, retry_enabled, *args, **kargs ):
	'''
	helper function
	starts given function, if exception is thrown shows a dialog with the option to retry the function call
	'''
	ret = None
	res = True
	retry = True
	while retry:
		try:
			ret = func( *args, **kargs )
			retry = False
			res = True
		except Globals.EXIT_EXCEPTIONS:
			raise
		except Exception as error:
			logger.exception( errormsg + '\n' + str( error ) )
			retry = dialog( title = errormsg, msg = str( error ), sic_path = sic_path, retry_enabled = retry_enabled )
			res = False
	return res, ret

class GenericLogClass( object ):
	'''
	Basic logging class, all used classes have to derive from
	'''
	log = None
	baselog = None
	def __init__( self, logger, name = None ):
		self.baselog = logger
		if name is None:
			name = self.__class__.__name__
		self.log = logging.LoggerAdapter( logger.log, {'class':name} )
		self._logfile_filename = None
		self._logfile_dateformat = None
		self._logformat = None
		self._logfileDay = None
		self._fileloghandler = None

	def set_logging_filename(self, filename, dateformat='_%Y_%m_%d_%H_%M_%S'):
		self._logfile_filename = filename
		self._logfile_dateformat = dateformat

	def set_logging_format(self, logformat):
		self._logformat = logformat

	def create_fileloghandler( self ):
		'''
		This function creates a new log file
		'''
		if self._logfile_filename is None:
			raise Exception('create filelog called without filename set!')
		logdir = os.path.normpath( os.path.join( gom.app.get ( 'local_all_directory' ), '..', 'log' ) )
		filepath = os.path.join( logdir, self._logfile_filename + time.strftime( self._logfile_dateformat ) + '.log' )
		self._fileloghandler = self.baselog.create_filehandler( filename = filepath, strformat = self._logformat )
		self.remove_old_logs( os.path.join( logdir, self._logfile_filename+'*.log' ) )
		self._logfileDay = datetime.datetime.now().day

	def close_fileloghandler(self):
		if self._fileloghandler is None:
			return
		self.baselog.close_filehandle( self._fileloghandler )

	def remove_old_logs( self, log_files ):
		'''
		Delete all log files, which are older than 4 weeks.
		'''
		today = datetime.datetime.today()
		mindiff = datetime.timedelta( weeks = 4 )
		for file in glob.glob( log_files ):
			try:
				mod_time = datetime.datetime.fromtimestamp( os.path.getmtime( file ) )
				if ( abs( today - mod_time ) > mindiff ):
					os.remove( file )
			except:
				pass

	def test_rolling_log_file(self):
		if self._logfileDay is None:
			return False
		if datetime.datetime.now().day != self._logfileDay:
			self.close_fileloghandler()
			self.create_fileloghandler()
			logdir = os.path.normpath( os.path.join( gom.app.get ( 'local_all_directory' ), '..', 'log' ) )
			self.remove_old_logs( os.path.join( logdir, self._logfile_filename+'*.log' ) )
			return True
		return False

# patching Functions
# CAREFULL if both patch methods are used for one class
# MetaClassPatch will override all function patches!!
# But not vice versa!

def patches( target, name, external_decorator = None ):
	'''
	patches given class method:
	for wrapping stuff, or a complete override
	@staticmethod, or @classmethod if set needs to be given as parameter

	@patches(SomeClass, 'aMethod')
	def aMethodOverride(aMethod, self, foo):
		return aMethod(self,foo)+1
	'''
	def decorator( patch_function ):
		original_function = getattr( target, name )

		@wraps( patch_function )
		def wrapper( *args, **kw ):
			return patch_function( original_function, *args, **kw )
		analyze_patch( target, patch_function.__name__, {name:patch_function}, True, external_decorator )
		if external_decorator is not None:
			wrapper = external_decorator( wrapper )
		setattr( target, name, wrapper )
		return wrapper
	return decorator


def MetaClassPatch( name, bases, namespace ):
	'''Dynamicall add methods of a class to another class
	and keeps the old method/attribute as "__original__"+name

	from <somewhere> import <someclass>
	class <newclass>(<someclass>, metaclass=MetaClassPatch):
		def <method1>(...):...
		def <method2>(...):...
		...
	'''
	assert len( bases ) == 1, 'Exactly one base class required'
	base = bases[0]
	assert inspect.isclass( base ), 'Patching a non class object'
	analyze_patch( base, name, namespace )
	for _name, value in namespace.items():
		if _name not in ['__metaclass__', '__doc__']:
			try:
				original = getattr( base, _name )
				setattr( base, 'original__' + _name, original )
			except:
				pass
			setattr( base, _name, value )
	return base

def analyze_patch( base, patchedname, namespace, ignore_first = False, external_decorator = None ):
	def _getargs( _name, _value, _ignore_first = False ):
		def _inspect_args( _value, _ignore_first ):
			if not _ignore_first:
				_args = inspect.getfullargspec( _value )
				return len( _args[0] ), _args[3], inspect.formatargspec( *_args )
			else:
				args, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations = inspect.getfullargspec( _value )
				if len( args ) >= 1:
					args = args[1:]
				return len( args ), defaults, inspect.formatargspec( args, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations )
		spec_tuple = None
		try:
			spec_tuple = _inspect_args( _value, _ignore_first )
		except:
			try:
				class _tmpobject: pass
				setattr( _tmpobject, _name, _value )
				spec_tuple = _inspect_args( getattr( _tmpobject, _name ), _ignore_first )
			except:
				pass
		return spec_tuple
	try:
		global __logfile
		if __logfile is None:
			__logfile = os.path.join( gom.app.get ( 'local_all_directory' ), '..', 'log', 'KioskInterfacePatches.log' )
			with open( __logfile, 'w', encoding='utf-8' ) as f:
				f.write( 'Applied patches {}\n'.format( time.strftime( '%Y.%m.%d %H:%M:%S' ) ) )

		frameinfo = None
		patch_location = 'unknown'
		try:
			frameinfo = inspect.getouterframes( inspect.currentframe() )[2]
			patch_location = '{} line {}\n'.format( frameinfo[1], frameinfo[2] )
		except:
			pass
		finally:
			if frameinfo is not None:
				del frameinfo
		loglines = [patch_location]
		module_name = 'unknown'
		try:
			module_name = base.original____module__ if hasattr( base, 'original____module__' ) else base.__module__
		except:
			pass
		if module_name.find( 'Workflow' ) >= 0 and base.__name__ == 'StartUp':
			Globals.FEATURE_SET.V8StartDialogs = False

		loglines += ['  {}->{} ({})\n'.format( module_name, base.__name__, patchedname )]
		for attr_name, attr_value in sorted( namespace.items() ):
			try:
				if attr_name not in ['__metaclass__', '__doc__', '__module__', '__qualname__']:
					is_patched = hasattr( base, attr_name )
					patched_spec = _getargs( attr_name, attr_value, ignore_first )
					try:
						orig_spec = _getargs( attr_name, getattr( base, attr_name ) )
					except:
						orig_spec = None
					spec = ''
					if orig_spec is not None and patched_spec is not None:
						error = ''
						if orig_spec[0] != patched_spec[0]:
							error = 'DIFFERENT COUNT OF PARAMETERS'
						elif orig_spec[1] != patched_spec[1]:
							error = 'DIFFERENT DEFAULTS'
						elif orig_spec[2] != patched_spec[2]:
							error = 'DIFFERENT NAMES'
						spec = '{}!={} {}'.format( patched_spec[2], orig_spec[2], error ) if len( error ) else patched_spec[2]
					elif patched_spec is not None:
						spec = '{}'.format( patched_spec[2] )
					equal_type = ''
					if is_patched:
						_orig_val = base.__dict__[attr_name]
						type_cmp_value = attr_value
						if external_decorator is not None:
							type_cmp_value = external_decorator( attr_value )
						if type( type_cmp_value ) != type( _orig_val ):

							equal_type = 'UNEQUAL TYPE {} <-> {}'.format( type( type_cmp_value ), type( _orig_val ) )
						elif isinstance( attr_value, str ):
							if attr_value.count( '{' ) != _orig_val.count( '{' ):
								equal_type = 'DIFFERENT FORMAT COUNT'
					loglines += [ '    {}{} [{}] {}\n'.format( attr_name, spec,
																'patched' if is_patched else 'new',
																equal_type ) ]
					if module_name == 'Base.Evaluate' and base.__name__ == 'EvaluationAnalysis' and attr_name == 'update_all_reports' and is_patched:
						loglines += '    DEPRECATED\n'
			except:
				pass
		with open( __logfile, 'a', encoding='utf-8' ) as f:
			f.writelines( loglines )
	except:
		pass
__logfile = None


def sanitize_filename( name ):
	'''sanitize_filename returns a sanitized filename
				handling the following problematic cases:
				- replace any <>:"/\|?* by _
				- replace control chars (ASCII 0..31) by _
				- remove trailing whitespace
				- replace trailing . by _
				- if basename is one of the reserved names
					('con', 'prn', 'aux', 'nul',
					'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
					'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9')
					append a _ to the basename
				Note: The matter of allowed filenames is extremely complex.
				This function cannot guarantee a valid filename,
				but it avoids the above-mentioned cases.
	'''
	# implemented strategy is (similar to str.encode):
	# errors='replace', replace_char='_'
	nname = []
	# remove trailing whitespace and replace <>:"/\|?* by _
	for n in name.rstrip():
		if n in '<>:"/\\|?*':
			n = '_'
		if ord(n) < 32:
			n = '_'
		nname.append(n)

	# replace trailing dot by _
	if nname[-1] == '.':
		nname[-1] = '_'

	tname = ''.join(nname)
	tname_noext, tname_ext = os.path.splitext( tname )

	# check basename if it is a reserved name
	#   just extend by _ to avoid reserved name
	if tname_noext.lower() in ['con', 'prn', 'aux', 'nul',
			'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
			'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9']:
		tname_noext += '_'

	return tname_noext + tname_ext

def split_folders( path ):
	'''
	splits a given path into a list
	'''
	folders = []
	path = os.path.normpath( path )
	while True:
		path, folder = os.path.split( path )
		if folder:
			folders.append( folder )
		else:
			if path:
				folders.append( path )
			break
	folders.reverse()
	return folders

def check_platform_support():
	'''
	if platform is Linux show Errordialog
	raises SystemExit on failure
	'''
	if platform.system() == 'Linux':
		if Globals.DIALOGS is None:
			from .. import Dialogs
		Globals.DIALOGS.show_errormsg(
					Globals.LOCALIZATION.msg_general_failure_title,
					Globals.LOCALIZATION.msg_platform_not_supported,
					None, False )
		sys.exit( 0 )

class EnumStructureMeta:
	'''
	Typesafe Enum-like structure metaclass
	'''
	class TypeSafeValue:
		'''
		Placeholder class for the enum value
		'''
		def __init__( self, base, name, value ):
			self.base = base  # class name which holds the value
			self.name = name  # name of the value
			self.value = value

		def _is_equal_attribute( self, other ):
			'''
			raise TypeError on compare with different Enum/type
			'''
			if isinstance( other, EnumStructureMeta.TypeSafeValue ):
				if self.base == other.base:
					return True
				return False
			raise TypeError( 'invalid compare between {} and {}'.format( self, type( other ) ) )

		def __eq__( self, other ):
			''' self == other '''
			if self._is_equal_attribute( other ):
				if self.name == other.name:
					return self.value == other.value
			return False
		def __lt__( self, other ):
			''' self < other '''
			if self._is_equal_attribute( other ):
				return self.value < other.value
			return False
		def __le__( self, other ):
			''' self <= other '''
			if self._is_equal_attribute( other ):
				return self.value <= other.value
			return False
		def __ne__( self, other ):
			''' self != other '''
			if self._is_equal_attribute( other ):
				return self.value != other.value
			return False
		def __gt__( self, other ):
			''' self > other '''
			if self._is_equal_attribute( other ):
				return self.value > other.value
			return False
		def __ge__( self, other ):
			''' self >= other '''
			if self._is_equal_attribute( other ):
				return self.value >= other.value
			return False
		def __bool__( self ):
			''' if self '''
			return self.value > 0
		def __repr__( self ):
			return '{}.{}'.format( self.base, self.name )

	def __new__( cls, name, _bases, classdict ):
		'''
		re-map enum values into type safe class
		'''
		obj = object.__new__( cls )
		for _name, _value in classdict.items():
			if not _name.startswith( '__' ):
				obj.__dict__[_name] = EnumStructureMeta.TypeSafeValue( name, _name, _value )
		return obj

	def __setattr__( self, name, value ):
		'''
		do not allow to change enum values
		'''
		if not isinstance( value, EnumStructureMeta.TypeSafeValue ):
			raise TypeError( 'invalid attribute setting of {} with {}'.format( name, value ) )
		return object.__setattr__( self, name, value )

class EnumStructure( metaclass = EnumStructureMeta ):
	'''
	Typesafe Enum-like structure
	'''
	def __init__( self ):
		raise UserWarning( 'This class should never be instantiated' )

class CustomError( Exception ):
	'''
	Custom Exception
	'''
	def __init__( self, value ):
		Exception.__init__( self, value )
		self.value = value
	def __str__( self ):
		return repr( self.value )

class CalibrationError( Exception ):
	'''
	Exception thrown if calibration failed
	'''
	def __init__( self, value ):
		Exception.__init__( self, value )
		self.value = value
	def __str__( self ):
		return repr( self.value )

class NeedCalibrationError( Exception ):
	'''
	Exception thrown if calibration is needed
	'''
	def __init__( self, value ):
		Exception.__init__( self, value )
		self.value = value
	def __str__( self ):
		return repr( self.value )

class NeedComprehensivePhotogrammetry(Exception):
	def __init__(self,value):
		Exception.__init__(self,value)
		self.value = value
	def __str__(self):
		return repr(self.value)

class GlobalTimer( GenericLogClass ):
	'''
	central timer class
	registers itself as gom timer handler and calls any registered functor
	'''
	def __init__( self, logger, time_interval ):
		'''
		initialize
		'''
		GenericLogClass.__init__( self, logger )
		self._handlers = []
		self._interval = time_interval

	def __del__( self ):
		'''
		disable timer
		'''
		try:
			gom.app.timer_enabled = False
		except:
			pass

	@staticmethod
	def registerInstance( logger ):
		'''
		register instance as global with given base logger
		'''
		Globals.TIMER = GlobalTimer( logger, 1000 )

	@staticmethod
	def unregisterInstance():
		'''
		remove instance
		'''
		del Globals.TIMER
		Globals.TIMER = None

	def _global_loop( self, value ):
		'''
		central loop for calling all registered handers
		'''
		if value != 'timer': # only listen to timer events, otherwise this would slowdown the complete software
			return
		for h in self._handlers:
			try:
				h( value )
			except Exception as e:
				self.log.exception( 'Exception during global handler call "{}" {}'.format( h, e ) )

	def setTimeInterval( self, ms ):
		'''
		set time interval (default 1s)
		'''
		self._interval = ms
		try:
			if gom.app.timer_enabled:
				gom.app.timer_interval = self._interval
		except:
			pass

	def registerHandler( self, handler ):
		'''
		register handler function
		on first handler start the timer
		'''
		self._handlers.append( handler )
		if ( len( self._handlers ) == 1 ):
			gom.app.handler = self._global_loop
			gom.app.timer_interval = self._interval
			gom.app.timer_enabled = True

	def unregisterHandler( self, handler ):
		'''
		unregister handler function
		disables timer if last handler was removed
		'''
		try:
			self._handlers.remove( handler )
		except:
			pass
		try:
			if not len( self._handlers ):
				gom.app.timer_enabled = False
		except:
			pass


def import_localization ( lang, logger ):
	if Globals.LOCALIZATION.__class__.__qualname__ != 'Localization' or Globals.LOCALIZATION.__class__.__module__ != 'Base.Misc.Messages':
		logger.warning( 'DEPRECATION WARNING: Old Messages CustomPatches detected. V8.1 Localization is now disabled. Please migrate your CustomPatches to V8.1 Localization.')
		return

	if lang != '' and lang != 'en':
		logger.info( 'Loading localization "{}"'.format( lang ))
	if lang == '':
		lang = 'en'
	try:
		_langmod = importlib.import_module( 'Localization.{}'.format( lang ))
		_langClass = _langmod.Localization()
		Globals.LOCALIZATION = _langClass
	except ImportError as e:
		if lang != 'en':
			logger.error( 'Localization Error: {}'.format(e))


def Vec3dDistance( self_value, other_value ):
	v = gom.Vec3d( other_value.x - self_value.x, other_value.y - self_value.y, other_value.z - self_value.z )
	return math.sqrt( v.x * v.x + v.y * v.y + v.z * v.z )

class Mat4x4:
	ROW = 0
	COLUMN = 1
	def __init__( self, matrix ):
		if not isinstance( matrix, gom.Mat4x4 ):
			raise TypeError( "no 4x4 matrix" )
		self.matrix = list()
		for row in range( 4 ): # initial fill
			self.matrix.append( [0] * 4 )
		for row in range( 4 ):
			for column in range( 4 ):
				self[row, column] = matrix.data[row * 4 + column]

	def __setitem__( self, key, value ):
		"""sets a value, the key is a tuple with row and column"""
		if not isinstance( key, tuple ):
			raise TypeError( "only tuples are supported" )
		if len( key ) != 2:
			raise ValueError( "only 2 dimensions" )
		self.matrix[key[Mat4x4.ROW]][key[Mat4x4.COLUMN]] = value

	def __getitem__( self, key ):
		"""returns a value, key is a tuple of row and column"""
		if isinstance( key, tuple ):
			if len( key ) != 2:
				raise ValueError( "only 2 dimensions" )
			return self.matrix[key[Mat4x4.ROW]][key[Mat4x4.COLUMN]]
		raise TypeError

	def _transformX( self, vec ):
		return ( vec.x * self[0, 0] + vec.y * self[0, 1] + vec.z * self[0, 2] + self[0, 3] ) / self[3, 3]
	def _transformY( self, vec ):
		return ( vec.x * self[1, 0] + vec.y * self[1, 1] + vec.z * self[1, 2] + self[1, 3] ) / self[3, 3]
	def _transformZ( self, vec ):
		return ( vec.x * self[2, 0] + vec.y * self[2, 1] + vec.z * self[2, 2] + self[2, 3] ) / self[3, 3]

	def transformPoint( self, vec ):
		if not isinstance( vec, gom.Vec3d ):
			raise TypeError( "given parameter is no gom.Vec3d" )

		return gom.Vec3d( self._transformX( vec ), self._transformY( vec ), self._transformZ( vec ) )

class CartesianMat4x4:
	def __init__( self, coord1, coord2=None, epsilon=None ):
		'''
		coord1 : defines the edge point of a bounding box, if coord2 is not given the sysmetric oposite will be used
		coord2 : optional the other edge point of the bounding box

		Test will be performed as a transformation of all corner points with both transformation matrixes and the resulting distance will be compared.
		'''
		if epsilon is None:
			self.epsilon = 1e-6
		else:
			self.epsilon = epsilon
		if not isinstance( coord1, gom.Vec3d ):
			raise TypeError( "no gom.Vec3d given as coord1" )
		self.coord1 = coord1
		if coord2 == None:
			self.coord2 = gom.Vec3d( -1*coord1.x, -1*coord1.y, -1*coord1.z )
		elif not isinstance ( coord2, gom.Vec3d ):
			raise TypeError( "no gom.Vec3d given as coord2" )
		else:
			self.coord2 = coord2

	def testValue( self, old_value, actual_value ):
		if not isinstance( old_value, gom.Mat4x4 ) or not isinstance( actual_value, gom.Mat4x4 ):
			raise TypeError( 'No gom.Mat4x4 given as test values' )

		old_matrix = Mat4x4( old_value )
		actual_matrix = Mat4x4( actual_value )
		quader_coords = [
			gom.Vec3d( self.coord1.x, self.coord1.y, self.coord1.z ),
			gom.Vec3d( self.coord1.x, self.coord1.y, self.coord2.z ),
			gom.Vec3d( self.coord1.x, self.coord2.y, self.coord1.z ),
			gom.Vec3d( self.coord1.x, self.coord2.y, self.coord2.z ),
			gom.Vec3d( self.coord2.x, self.coord1.y, self.coord1.z ),
			gom.Vec3d( self.coord2.x, self.coord1.y, self.coord2.z ),
			gom.Vec3d( self.coord2.x, self.coord2.y, self.coord1.z ),
			gom.Vec3d( self.coord2.x, self.coord2.y, self.coord2.z )
		]
		max_distance = 0.0
		for coord in quader_coords:
			old = old_matrix.transformPoint( coord )
			new = actual_matrix.transformPoint( coord )
			max_distance = max( max_distance, Vec3dDistance( old, new ) )

		return ( max_distance < self.epsilon,
			"Maximal Distance: {}\n1st: {}\n2nd: {}".format ( max_distance, old_matrix, actual_matrix ) )

def left_right_replace( string ):
	'''
	replace all occurence of DRC Main/Secondary-extension with each other
	'''
	replace_dict = {
			Globals.SETTINGS.DoubleRobot_MainExtension      : Globals.SETTINGS.DoubleRobot_SecondaryExtension,
			Globals.SETTINGS.DoubleRobot_SecondaryExtension : Globals.SETTINGS.DoubleRobot_MainExtension
			}
	rc = re.compile( '|'.join( map( re.escape, replace_dict ) ) )  # search for Primary or Secondary
	return rc.sub( lambda match: replace_dict[match.group( 0 )], string )  # inplace replace all matches


def multi_part_evaluation_status():
	try:
		if gom.app.project.is_part_project:
			if ( gom.app.project.measuring_setups[0].part_positions is None
				and gom.app.project.measuring_setups[0].current_working_area_partition is None ):
				return False
			parts = [p.name for p in gom.app.project.parts
				if not p.is_element_in_clipboard and p.part_function == 'used_for_scanning']
			return len( parts ) > 1
		else:
			return False
	except:
		return False

def multi_part_evaluation_parts( alignment_part=None, names=False ):
	def align_check( p ):
		if alignment_part is None:
			return True
		return p.is_part_used_for_aligning_measuring_data == alignment_part

	parts = [p.name if names else p for p in gom.app.project.parts
		if not p.is_element_in_clipboard and p.part_function == 'used_for_scanning' and align_check( p )]
	return parts

def real_measurement_series( mseries=None, filter=None ):
	if mseries is None:
		if filter is None:
			mseries = gom.app.project.measurement_series
		else:
			mseries = gom.app.project.measurement_series.filter(filter)
	return [m for m in mseries if m.part is None]