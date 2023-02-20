# -*- coding: utf-8 -*-
# Script: Default settings definition
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
# 2013-01-22: Removed AutoDetectMeasurementSeries,MaxDigitizeMeasurementDeviation
#             Added PhotogrammetryVerify, MeasurementFailureMargin
# 2015-07-20: Added Language setting (default empty) to Dialog settings.
# 2016-04-26: Burn-In Limits

import os
import logging
import gom

class DefaultSettings( object ):
	'''
	This class contains a default configuration of the scripts parameters.
	'''

	# CFG_NAME contains the location of the config file, which contains the non default configuration of the scripts parameters.
	CFG_NAME = os.path.join( gom.app.get ( 'public_directory' ) if gom.app.get ( 'public_directory' ) is not None else '', 'KioskInterface_settings.cfg' )
	TEMPLATE_MATCH_FILE = os.path.join( gom.app.get ( 'public_directory' ) if gom.app.get ( 'public_directory' ) is not None else '',
									'KioskInterface_TemplateBarCodeAssignment.csv' )
	VERSION = '0.104'

	#######################################################################################################################################
	########################################################### GeneralSettings ###########################################################
	#######################################################################################################################################

	# SavePath specifies the directory where all files created by the script should be stored (except the config file)
	SavePath = 'D:/'

	# ProjectName specifies the name under which the processed project should be stored
	ProjectName = 'GOM-Training-Object'

	# Use only TimeFormatProject defined string as ProjectName
	AutoNameProject = True

	# Format string specifying how time should be represented. Any order of the directives (i.e. everything beginning with %) is possible.
	TimeFormatProject = '%Y_%m_%d_%H_%M_%S'

	# ShowTemplateDialog defines if the StartUp dialog should be displayed
	ShowTemplateDialog = True

	# TemplateName specifies the project template which should be used if the project template is not requested from the user by the StartUp dialog
	TemplateName = 'GOM-Training-Object.project_template'

	# OfflineMode is meant for development and therefore skips any part of the script which needs hardware.
	OfflineMode = False

	# FailedPostfix is the prefix of the filename which were not successfully processed by the script
	FailedPostfix = 'failed'

	# Defines which templates should be displayed, valied values are connected_project, project_template or both
	TemplateCategory = 'project_template'

	# Defines the servers for connected projects
	ConnectedProjectSources = []
  
	# Defines which templates should be displayed, valid values are shared, user or both
	TemplateConfigLevel = 'shared'

	# Batch scan multiple templates
	BatchScan = False

	# pause dialog between BatchScan templates needed
	BatchScanPauseNeeded = False

	# Allow Abort (in the progress bar)
	AllowAbort = True

	# Show measurement series selection dialog
	MSeriesSelection = False
	# Additional mseries selection checkbox for alignment iteration (fixture adjustment pause)
	AlignmentIteration = False

	# SavePath storage limits in MB 
	DiscFullWarningLimitSavePath = 10000
	DiscFullErrorLimitSavePath = 3000
	DiscFullWarningLimitLogPath = 300
	DiscFullErrorLimitLogPath = 100

	#######################################################################################################################################
	######################################################### Keywords ####################################################################
	#######################################################################################################################################

	# If set instead of a username list the current windows login name will be used
	UseLoginName = False

	# Format string specifiying how time should be represented for the project keyword "Date"
	TimeFormatProjectKeyword = '%d/%m/%Y'

	# If set instead of one serial number per part only one overall batch serial number is requested
	MultiPartBatchSerial = False

	#######################################################################################################################################
	######################################################### MeasurementSettings #########################################################
	#######################################################################################################################################

	# If this is False, then the measurements are executed with a cold sensor which may result in bad measurement data
	WaitForSensorWarmUp = True

	# Maximal number of scan. If non of those scans is successful, then the measurement process is aborted with a warning dialog
	MaxDigitizeRepetition = 2

	# How many percent of the measurement can fail due to transformation or projector residual failures
	MeasurementFailureMargin = 0.1

	HigherFaultTolerance = False

	FreePathAlwaysAllowed = False

	# Check Fixture Position
	CheckFixturePosition = False
	CheckFixturePositionOnlyOnTemplateSwitch = False
	KeepCheckFixturePositionElements = False
	CheckFixtureRepeat = False

	# If the time between two calibration attempts is greater than CalibrationMaxTimedelta in minutes, the calibration attempt fails.
	CalibrationMaxTimedelta = 10
	# If the time to the last calibration exceeds CalibrationForcedTimedelta minutes, a new calibration is executed before starting atos measurements. A value of 0 means no timeout.
	CalibrationForcedTimedelta = 0
	# If the flag CalibrationEachCycle is set, a new calibration is executed in each Kiosk cycle before starting atos measurements.
	CalibrationEachCycle = False

	# If PhotogrammetryOnlyIfRequired is False, the photogrammetry measurement series will always be executed before the atos measurement series
	# is executed. Otherwise the script will check if there are valid photogrammetry measurement data for the template from a previous execution
	# of the script
	PhotogrammetryOnlyIfRequired = False

	# If the stored photogrammetry measurement data is older than PhotogrammetryMaxTimedeltaImport minutes it is not used and a new photogrammetry measurement is executed
	PhotogrammetryMaxTimedeltaImport = 24 * 60
	# PhotogrammetryMaxImportCount specifies the number of times stored Photogrammetry data should be used. If set to 0 it will use the stored data as often as possible.
	PhotogrammetryMaxImportCount = 0
	# If the stored phtogrammetry data deviates more than PhotogrammetryMaxTemperatureLimit degrees of celsius from the current temperature it is not used
	PhotogrammetryMaxTemperatureLimit = 5
	# A new photogrammetry measurement will be done if the project template is switched even if a valid backup file is found.
	PhotogrammetryForceOnTemplateSwitch = True
	# If not set it does not export adapter points
	PhotogrammetryExportAdapters = True
	# The location where the photogrammetry data should be stored relative to SavePath
	PhotogrammetrySavePath = 'photogrammetry'
	# if set to false no photogrammetry verification checks are performed. Its not recommended to change this setting!
	PhotogrammetryVerification = True
	# if set use project comprehensive photogrammetry
	PhotogrammetryComprehensive = False
	# defines the number of scalebars which need to be computed
	PhotogrammetryNumberOfScaleBars = 2
	# photogrammetry is independent of the part
	PhotogrammetryIndependent = False

	# ID range of coded reference points used for transformation by common refpoints
	PhotogrammetryCodedPointIDRange = ''

	MoveAllDevicesToHome = True
	
	AsyncAlignmentResidualCheck = False

	#######################################################################################################################################
	########################################################### AnalysisSettings ##########################################################
	#######################################################################################################################################
	# Should the polygonization be performed
	PerformPolygonization = True
	# Defines if polygonize should fill the reference points
	PolygonizeFillReferencePoints = False
	# Defines the postprocessing method used for polygonize, valid values are:
	# "no_postprocessing", "detailed", "standard", "removes_surface_roughness", "rough_inspection"
	PolygonizeProcess = 'removes_surface_roughness'
	# Reduces the memory space during polygonization, but reduces the speed
	PolygonizeLargeDataVolumes = False

	#######################################################################################################################################
	########################################################### EvaluationResult ##########################################################
	#######################################################################################################################################

	ResultAlignment = ''
	MPResultAlignmentPattern = ''
	ExportPDF = True

	#######################################################################################################################################
	########################################################### LoggingSettings ###########################################################
	#######################################################################################################################################

	# LoggingLevel specifies the amount of logging information
	# see http://docs.python.org/release/3.0.1/library/logging.html?highlight=logging#module-logging for more information
	LoggingLevel = logging.DEBUG
	LoggingFormat = '%(asctime)s %(levelname)-10s Class(%(class)s) Func(%(funcName)s) Line(%(lineno)d) %(message)s'
	VerboseTraceback = True
	# Format string specifying how time should be represented. Any order of the directives (i.e. everything beginning with %) is possible.
	TimeFormatLogging = '_%Y_%m_%d_%H_%M_%S'
	
	# should an additional log file be created to log evaluation statistics
	LogStatistics = True

	#######################################################################################################################################
	############################################################ DialogSettings ###########################################################
	#######################################################################################################################################
	# users...

	LogoImage = ''
	InitializeImage = ''
	PhotogrammetryImage = ''
	DigitizeImage = ''
	ReportImage = ''
	CalibrationImage = ''
	TurnaroundFirstImage = ''
	TurnaroundImage = ''
	TurnaroundCalibrationImage = ''
	MultiPartWaitImage = ''

	# Localization setting
	# No setting is equivalent to "en"
	Language = ''

	#######################################################################################################################################
	############################################################ BarCode scanner ##########################################################
	#######################################################################################################################################

	BarCodeScanner = False
	BarCodeCOMPort = 4
	BarCodeDelimiter = '\r\n'
	SeparatedFixtureRegEx = ''

	#######################################################################################################################################
	########################################################### AsyncEvaluation ###########################################################
	#######################################################################################################################################

	# If Async is True, then NumberOfClients are started to do the inspection/evaluation
	Async = False
	NumberOfClients = 1
	HostAddress = 'localhost'
	HostPort = 8081
	# Specifies is the path relative to SavePath, where the successfully measured projects should be stored
	MeasureSavePath = 'measured'
	# should the automatic evaluation be performed
	AutomaticResultEvaluation = True

	#######################################################################################################################################
	########################################################### TrendCreation #############################################################
	#######################################################################################################################################
	BackgroundTrend = False
	TrendMaxStageSize = 10
	TrendShowOnSecondMonitor = False

	#######################################################################################################################################
	############################################################## Inline #################################################################
	#######################################################################################################################################
	Inline = False
	InlinePLC_NetID = '172.17.61.55.1.1'
	InlinePLC_Port = 851
	EnableRecommendedSignals = False
	TemperatureWarningLimit = 3.0

	#######################################################################################################################################
	########################################################### Compatibility #############################################################
	#######################################################################################################################################
	Compat_MeasuringSetup = False
	
	#######################################################################################################################################
	################################################################ DRC ##################################################################
	#######################################################################################################################################
	DoubleRobotCell_Mode = False
	DoubleRobot_SecondaryHostAddress = '192.168.10.2'
	DoubleRobot_SecondaryHostPort = 40234
	DoubleRobot_MainExtension = 'right'
	DoubleRobot_SecondaryExtension = 'left'
	DoubleRobot_KioskExecution = False
	DoubleRobot_RefCubeCheck = False
	DoubleRobot_RefCubeCheckOnce = False
	
	DoubleRobot_TransferPath = 'E:/Share/Transfer'
	DoubleRobot_ClientSavePath = 'E:/DRCTemp'
	DoubleRobot_ClientTransferPath = 'E:/Share/Transfer'
	#######################################################################################################################################
	############################################################# MultiRobot ##############################################################
	#######################################################################################################################################
	MultiRobot_Mode = False
	MultiRobot_HostAddresses = ['192.168.10.1', '192.168.10.2']
	MultiRobot_HostPorts = [40234]
	MultiRobot_ClientSavePath = ['D:/Temp', 'D:/Temp']
	MultiRobot_ClientTransferPath = ['D:/Temp', 'D:/Temp']
	MultiRobot_TransferPath = ['D:/Temp', 'D:/Temp']

	MultiRobot_MeasureTemplate = 'MeasurementTemplate.project_template'
	MultiRobot_MemoryDebug = False
	MultiRobot_TimingDebug = False
	MultiRobot_ConnectionDebug = False
#	MultiRobot_ProjectTimeout = -1
#	MultiRobot_ProjectKeep = []
	MultiRobot_EvalClients = []
	# EvalPerRemote = 1 means [1,2,3,4] are on R1,R2,R3,R4 resp.
	# the rest is controlled locally
	MultiRobot_EvalPerRemote = 0
	MultiRobot_RemoteEvalHostAddress = ''
	MultiRobot_RemoteEvalShare = ''
	MultiRobot_ThermometerIP = ''
	MultiRobot_ThermometerPort = 80
	MultiRobot_CalibRobotProgram = None
	MultiRobot_HyperScaleRobotPrograms = []
	MultiRobot_CalcHyperScale = True
	# Evaluation timeout (in s)
	MultiRobot_EvalTimeout = -1
	# these robot programs use the EvalTimeout, other programs use EvalTimeoutOthers
	MultiRobot_EvalTimeoutPrograms = []
	MultiRobot_EvalTimeoutOthers = -1


	#######################################################################################################################################
	############################################################# IOExtension #############################################################
	#######################################################################################################################################
	IOExtension = False
	IOExtension_NetID = '172.17.61.55.1.1'
	IOExtension_Port = 851

	#######################################################################################################################################
	############################################################# IoTConnection ###########################################################
	#######################################################################################################################################
	IoTConnection = False
	IoTConnection_IP = '127.0.0.1'
	IoTConnection_Port = 10005

	# binary blocks of the images, which should be used in the info/status dialogs during the script( non cfg )
	LogoImageBinary = None
	PhotogrammetryImageBinary = None
	DigitizeImageBinary = None
	ReportImageBinary = None
	CalibrationImageBinary = None
	InitializeImageBinary = None
	TurnaroundFirstImageBinary = None
	TurnaroundImageBinary = None
	TurnaroundCalibrationImageBinary = None
	MultiPartWaitImageBinary = None

	def __init__( self ):
		pass