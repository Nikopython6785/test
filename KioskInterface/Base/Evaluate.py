# -*- coding: utf-8 -*-
# Script: Evaluation definition, Measuring- and Post-Evalution Classes
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
# 2013-01-22: execute every defined photogrammetry/digitize measurement series
# 			 polygonization can now ignore failed measurements
# 2013-03-26: added support for Programmable Measurement Series
# 			 added support for different measurment setups inside one VMR project
# 2013-04-15: template name now defines the folder structure the project name is only the current date
# 2013-04-26: automatic result evaluation based on report xml export
#             WuT is now a member of the Evaluate class
# 2015-03-30: removed path validation check, its now part of the project consistency check cmd
# 2015-04-23: Evaluate.set_project_keywords no longer sets keyword description if keyword already exists.
#             Handle additional keywords from table in CustomPatches.
# 2015-07-06: EvaluationAnalysis/_parse_xml analyze split part in new function _analyze_export_xml.
# 2015-11-02: Support for multi measurement setup/series.
# 2016-06-21: Execute first all tritop series before verifying them


import gom

import datetime, time, os
import math
import re
import warnings
import tempfile
import xml.etree.ElementTree
import codecs
import subprocess
import pickle
import gom_windows_utils

from .Misc import Utils, Globals
from .Measuring import Calibration, Measure, Verification, Thermometer, FixturePositionCheck
from .Communication import Communicate
from .Communication.Inline import InlineConstants
from KioskInterface.Tools.TrendCreator import create_autowatch_cfg
import KioskInterface.Tools.StatisticalLog as StatisticalLog

class ExecutionMode ( Utils.EnumStructure ):
	'''
	Enum like structure for storing current execution mode
	'''
	Full = 0
	ForceCalibration = 1
	ForceTritop = 2
	PerformAdditionalCalibration = 3

class Evaluate( Utils.GenericLogClass ):
	'''
	This class implements the default evaluation functionality
	'''
	parent = None
	calibration = None
	tritop = None
	atos = None
	checks = None
	sensor = None
	analysis = None

	def __init__( self, logger, parent ):
		'''
		Constructor function to init logging, process dialog and measure classes
		Arguments:
		parent - A reference to the Eval class which is a component in workflow
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		if self.parent is not None:
			self.parent.process_msg( Globals.LOCALIZATION.msg_evaluate_process_text )
			self.parent.process_msg_detail( '' )
		# create measurement class references
		self.thermo = Thermometer.Thermometer( self.baselog, self )
		self.checks = Verification.MeasureChecks( self.baselog, self )
		self.sensor = Measure.Sensor( self.baselog, self )
		self.calibration = Calibration.Calibration( self.baselog, self )
		self.hyper_calibration = Calibration.Calibration(self.baselog, self)
		self.tritop = Measure.MeasureTritop( self.baselog, self )
		self.atos = Measure.MeasureAtos( self.baselog, self )
		self.analysis = EvaluationAnalysis( self.baselog, self )
		self.statistics = EvaluationAnalysis.createStatistics()
		self.position_information = PositionInformation(self)
		self.context = None

		self._isVMRlight = False
		self.first_measurement_series = True
		self._executionMode = ExecutionMode.Full

		# measurement series selection / alignment iteration
		self.alignment_mseries = None
		self.msselect_left_right_check = False   # for drc extension
		self.msselect_max_rows = 10              # layout limit per page
		self.msselect_iter_cols = False          # alignment iteration column
		self.msselect_dialogs = []               # all dialogs
		self.msselect_dialog = None	             # current dialg
		self.msselect_page = 0                   # current page no
		self.msselect_open_row = None            # currently uncollapsed tag
		self.msselect_ctl_info = None            # control information, see _get_mseries_taginfo
		self.msselect_tag_format = '<< {} >>'    # tag checkbox label format
		self.msselect_partial_mark = '(\u2611) ' # mark for tags when partially selected
		self.msselect_all_ms = ''                # localized tag for all untagged mseries

	@property
	def Sensor( self ):
		'''
		readonly sensor class reference
		'''
		return self.sensor
	@property
	def Global_Checks( self ):
		'''
		readonly measurement test class reference
		'''
		return self.checks
	@property
	def Calibration( self ):
		'''
		readonly calibration class reference
		'''
		return self.calibration
	@property
	def HyperScale(self):
		return self.hyper_calibration
	@property
	def Atos( self ):
		'''
		readonly atos class reference
		'''
		return self.atos
	@property
	def Tritop( self ):
		'''
		readonly tritop class reference
		'''
		return self.tritop
	@property
	def Dialog( self ):
		'''
		readonly dialog class reference
		'''
		return self.parent
	@property
	def Thermometer( self ):
		'''
		readonly Thermometer class reference
		'''
		return self.thermo

	@property
	def IsVMRlight( self ):
		'''
		readonly: has project vmr light support, programmable measurement series
		'''
		return self._isVMRlight

	@property
	def hasVMR( self ):
		'''
		has project VMR support
		'''
		try:
			gom.app.project.virtual_measuring_room[0]
			return True
		except:
			return False

	@property
	def Statistics( self ):
		return self.statistics

	def check_VMRlight( self ):
		'''
		check and set IsVMRlight property
		'''
		if self.hasVMR:
			self._isVMRlight = False
		else:
			self._isVMRlight = True
			any_found = False
			for ms in Utils.real_measurement_series():
				for m in ms.measurements:
					try:
						if m.get( 'automation_device' ) is None:
							self._isVMRlight = False
						else:
							any_found = True
					except RuntimeError:
						self._isVMRlight = False
			if not any_found:
				self._isVMRlight = False
		return self._isVMRlight

	@property
	def isComprehensivePhotogrammetryProject( self ):
		'''
		checks if the project only contains photogrammetry in the case of Comprehensive setting
		'''
		try:
			if Globals.SETTINGS.PhotogrammetryComprehensive:
				tritop_ms = len( Utils.real_measurement_series( filter='type=="photogrammetry_measurement_series"' ) )
				atos_ms = len( Utils.real_measurement_series( filter='type=="atos_measurement_series"' ) )
				if tritop_ms and not atos_ms:
					return True
		except:
			pass
		return False

	def setExecutionMode(self, value):
		self._executionMode = value

	def getExecutionMode(self):
		return self._executionMode

	def isForceTritopActive(self):
		return self._executionMode == ExecutionMode.ForceTritop

	def prepareTritop(self):
		if not self.collectCompatibleSeries():
			return
		if not len(self.Comp_photo_series):
			return
		if Globals.DRC_EXTENSION is not None:
			Globals.DRC_EXTENSION.reuse_photogrammetry(self)
			return
		master_series = gom.app.project.measurement_series[self.Comp_photo_series[0]]
		for ms in self.Comp_photo_series:
			ms = gom.app.project.measurement_series[ms]
			if ms.get('reference_points_master_series') is None:
				master_series = ms
				break
		if not self.Tritop.isFailedTemplate():
			if self.Tritop.import_photogrammetry( master_series ):
				self.Comp_photo_series = []


	def showErrorNoCompatibleSeries(self):
		number_of_controllers=0
		try:
			vmr = gom.app.project.virtual_measuring_room[0]
			number_of_controllers = vmr.get('number_of_controllers')
		except:
			pass
		# nothing to do
		realController = self.Sensor.getConnectedController()
		realSensor = self.Sensor.getRealHardware()
		wcfg_settings = [(wcfg.name, self.Sensor.getWCfgSetting(wcfg))
						for wcfg in sorted([wcfg for wcfg in gom.app.project.measuring_setups])]
		self.log.error('Template does not contain any compatible measurement series')
		text = Globals.LOCALIZATION.msg_no_measurement_list + '<br/>' + Globals.LOCALIZATION.msg_no_measurement_list_real + '<br/>'
		if number_of_controllers > 1 and realController is not None:
			text += realController + ' - '
		text += ' / '.join(str(entry) for entry in realSensor if entry is not None)
		for w_s in wcfg_settings:
			text += '<br/><b>' + w_s[0] + '</b><br/>'
			if number_of_controllers > 1 and w_s[1][0] is not None:
				text += w_s[1][0] + ' - '
			if w_s[1][1] is not None:
				text += ' / '.join(str(entry) for entry in [
												w_s[1][1].get('sensor',None),
												w_s[1][1].get('camera_distance',None),
												w_s[1][1].get('mv',None),
												w_s[1][1].get('photogrammetry_mv',None),
												w_s[1][1].get('variant','default'),
												] if entry is not None)
		Globals.DIALOGS.show_errormsg(
			Globals.LOCALIZATION.msg_general_failure_title,
			text,
			None,
			retry_enabled=False )

	def collectCompatibleSeries(self):
		'''Collects lists of names of compatible measuring setups and measuring series in the project.
		'''
		if Globals.SETTINGS.AlreadyExecutionPrepared:
			return True
		self.Compatible_wcfgs = []
		self.Comp_photo_series = []
		self.Comp_atos_series = []
		self.Comp_calib_series = []
		self.Comp_hyperscale_series = []
		with Measure.TemporaryWarmupDisable(self.Sensor) as warmup: # no warmuptime on direct init
			if not self.Sensor.check_for_reinitialize():
				return False
		self.Sensor.logRealHardware()
		self.check_VMRlight()

		self.Compatible_wcfgs = sorted([wcfg.name
			for wcfg in gom.app.project.measuring_setups
				if self.Sensor.same_sensor(wcfg)
					and self.Sensor.correct_controller(wcfg)])
		self.log.info('Compatible Measuring setups: {}'.format(','.join(self.Compatible_wcfgs)))

		if not self.IsVMRlight:
			self.Comp_photo_series = [mseries.name for mseries in Utils.real_measurement_series()
				if mseries.get('type') == 'photogrammetry_measurement_series'
					and self.Sensor.isMListPartOfMeasuringSetups(mseries, self.Compatible_wcfgs)]
			self.Comp_photo_series = self.sort_mseries( self.Comp_photo_series )
			self.log.info('Compatible photogrammetry measurement series {}'.format(
				list(self.Comp_photo_series)))

		self.Comp_atos_series = [mseries.name for mseries in Utils.real_measurement_series()
			if mseries.get('type') == 'atos_measurement_series'
				and self.Sensor.isMListPartOfMeasuringSetups(mseries, self.Compatible_wcfgs)]
		self.Comp_atos_series = self.sort_mseries( self.Comp_atos_series )
		self.log.info('Compatible ATOS measurement series {}'.format(
			list(self.Comp_atos_series)))

		self.Comp_calib_series = [mseries.name for mseries in Utils.real_measurement_series()
			if mseries.get('type') == 'calibration_measurement_series' and mseries.get('calibration_measurement_series_type') == 'sensor'
				and self.Sensor.calibration_ms_compatible(mseries, self.Compatible_wcfgs)]
		self.Comp_calib_series = self.sort_mseries( self.Comp_calib_series )
		self.log.info('Compatible calibration measurement series {}'.format(
			list(self.Comp_calib_series)))

		self.Comp_hyperscale_series = [mseries.name for mseries in gom.app.project.measurement_series
			if mseries.get('type') == 'calibration_measurement_series' and mseries.get('calibration_measurement_series_type') != 'sensor'
				and self.Sensor.calibration_ms_compatible(mseries, self.Compatible_wcfgs)]
		self.Comp_hyperscale_series = self.sort_mseries( self.Comp_hyperscale_series )
		self.log.info('Compatible hyperscale measurement series {}'.format(
			list(self.Comp_hyperscale_series)))

		return True

	def sort_mseries(self, mseries):
		'''
		"mseries" is a list of measurement series names.
		This function returns a list of ms names which is sorted
		- first by name of corresponding measuring setup
		- second by name of the measurement series.
		'''
		# sort into dict per msetup
		res = {}
		for msn in mseries:
			ms = gom.app.project.measurement_series[msn]
			try:
				msetup = ms.get ('measuring_setup').get('name')
			except:
				msetup = ''
			if msetup in res:
				res[msetup].append(msn)
			else:
				res[msetup] = [msn]

		# collect mseries sorted by msetups, also sort mseries per msetup
		sorted_ms = []
		for msetup in sorted(res.keys()):
			sorted_ms += sorted(res[msetup])

		return sorted_ms

	def select_measurement(self, no_shows=None, check_compatible=True ):
		if no_shows is None:
			no_shows = []
		if Globals.DRC_EXTENSION is not None:
			# drc extensions prepare/wait for measurement series selection
			if not Globals.DRC_EXTENSION.prepare_measurement( self ):
				return False
			if Globals.DRC_EXTENSION.SecondarySideActive():
				return True

		# reset measurement series for alignment iteration
		self.alignment_mseries = None

		if Globals.FEATURE_SET.ONESHOT_MSERIES:
			tritop_measurements = []
			atos_measurements = []
			for mseries in Globals.FEATURE_SET.ONESHOT_MSERIES:
				if gom.app.project.measurement_series[mseries].type == 'atos_measurement_series':
					atos_measurements.append( mseries )
				elif gom.app.project.measurement_series[mseries].type == 'calibration_measurement_series':
					self.setExecutionMode( ExecutionMode.PerformAdditionalCalibration )
				else:
					tritop_measurements.append( mseries )
			self.Comp_photo_series = tritop_measurements
			self.Comp_atos_series = atos_measurements
		elif Globals.SETTINGS.BatchScan:
			pass
		elif Globals.SETTINGS.MSeriesSelection:
			if check_compatible:
				# collect all selectable measurements
				accept_empty = Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.PrimarySideActive()
				tritop_measurements = [ml for ml in self.Comp_photo_series
					if self.is_measurement_series_executable( ml, accept_empty=accept_empty ) and ml not in no_shows]
				atos_measurements = [ml for ml in self.Comp_atos_series
					if self.is_measurement_series_executable( ml, accept_empty=accept_empty ) and ml not in no_shows]
			else:
				tritop_measurements = [ml for ml in self.Comp_photo_series if ml not in no_shows]
				atos_measurements = [ml for ml in self.Comp_atos_series if ml not in no_shows]
			series = tritop_measurements + atos_measurements

			# build and show dialog for measurement selection
			try:
				series, self.alignment_mseries = self._show_select_measurement( series )
			except gom.BreakError:
				Globals.SETTINGS.CurrentTemplate = None
				Globals.SETTINGS.CurrentTemplateCfg = None
				if Globals.DRC_EXTENSION is not None:
					# set measurement select failure for drc mode
					Globals.DRC_EXTENSION.set_measurements( self, None )
				return False

			if series is None:
				if Globals.DRC_EXTENSION is not None:
					# set measurement select failure for drc mode
					Globals.DRC_EXTENSION.set_measurements( self, None )
				return False

			# set selected measurements
			self.log.info( 'MSeries selected for execution: ' + ( ', '.join( series ) ) )
			tritop_measurements = []
			atos_measurements = []
			for mseries in series + no_shows:
				if gom.app.project.measurement_series[mseries].type == 'atos_measurement_series':
					atos_measurements.append( mseries )
				elif gom.app.project.measurement_series[mseries].type == 'calibration_measurement_series':
					self.setExecutionMode( ExecutionMode.PerformAdditionalCalibration )
				else:
					tritop_measurements.append( mseries )
			self.Comp_photo_series = self.sort_mseries( tritop_measurements )
			self.Comp_atos_series = self.sort_mseries( atos_measurements )

		if Globals.DRC_EXTENSION is not None:
			if not Globals.DRC_EXTENSION.set_measurements( self, self.Comp_photo_series + self.Comp_atos_series ):
				return False

		return True

	def drc_check_taginfo( self, tag_info, series ):
		'''
		DRC mode: Check master tag_info versus tag_info on master/slave replaced mseries
		Raises ValueError on mismatch.
		'''
		for tag, mss in tag_info.items():
			for ms in mss:
				slave_ms = Utils.left_right_replace( ms )
				if ms != slave_ms:
					slave_mslist = gom.app.project.measurement_series[slave_ms]
					slave_tag = self.get_mseries_tag( slave_mslist )
					if tag != slave_tag:
						raise ValueError( 'Mismatching mseries tags in DRC mode for main/secondary' )

	def get_mseries_tag( self, series ):
		tag = series.depends_on_tag
		if tag is None:
			tag = series.depends_on_part
		if tag is None and series.type != 'calibration_measurement_series':
			# special tag for "all untagged mseries category"
			tag = True
		return tag

	def _get_mseries_taginfo( self, series ):
		# compile dictionary 'tag' => ['mseries']
		# special tag 'True' for untagged mseries
		# special tag 'None' for calibration series
		tag_info = {}
		try:
			mslist = [gom.app.project.measurement_series[msname] for msname in series]

			for ms in mslist:
				tag = self.get_mseries_tag( ms )
				if tag in tag_info:
					tag_info[tag].append( ms.name )
				else:
					tag_info[tag] = [ms.name]

			if Globals.SETTINGS.DoubleRobotCell_Mode:
				# raises exception on mismatch, default below is used
				self.drc_check_taginfo( tag_info, series )
		except Exception as e:
			self.log.warning( str( e ) )
			# default: None => calibration, True(untagged) => all other series
			calibs = []
			others = []
			for ms in series:
				try:
					mslist = gom.app.project.measurement_series[ms]
					if mslist.type == 'calibration_measurement_series':
						calibs.append( ms )
					else:
						others.append( ms )
				except:
					pass
			tag_info = {}
			if calibs:
				tag_info[None] = calibs
			if others:
				tag_info[True] = others

		# sorting, longest tag, necessary rows for layout
		# 'tag_len' is no of rows needed when everything is collapsed
		ctl_info = {}
		ms_rows = 0
		max_tag_len = 0
		tag_len = 0
		for k,v in tag_info.items():
			v.sort()
			if k is None:
				ms_rows += len( v )
				tag_len += len( v )
			else:
				if len( v ) > max_tag_len:
					max_tag_len = len( v )
				ms_rows += 1 + len( v )
				tag_len += 1

		# separate real tags / special tags, sort tags
		key_list = list( tag_info.keys() )
		tag_list = []
		if None in key_list:
			key_list.remove( None )
			tag_list.append( None )
		if True in key_list:
			key_list.remove( True )
			tag_list.append( True )
		tag_list += sorted( key_list )

		ctl_info['rows'] = ms_rows               # needed layout rows
		ctl_info['multi'] = False                # multi page layout
		ctl_info['full'] = False                 # fully uncollapsed layout
		ctl_info['tags'] = len( key_list ) != 0  # real tags
		ctl_info['order'] = tag_list             # sorted tags

		# determine layout mode
		if ms_rows <= self.msselect_max_rows:
			ctl_info['full'] = True
		elif tag_len + max_tag_len <= self.msselect_max_rows:
			ctl_info['multi'] = False
		else:
			ctl_info['multi'] = True

		# compile control info used for dialog building / handling
		box_table = {}  # row => tag, list of mseries, list of sub-rows
		page_table = {} # page no => rows in layout, row offset for layout, box_table
		result = {}     # storage for checkbox states (always includes iter result)
		lrow = 1        # absolute layout row
		frow = 1        # 'fill' row, for deciding if page is full
		page = 0
		page_tagi = 0
		max_tag_len = 1
		for tag in ctl_info['order']:
			if tag is not None and len( tag_info[tag] ) > max_tag_len:
				max_tag_len = len( tag_info[tag] )

			# page break?
			if tag is not None:
				if frow + 1 + max_tag_len > 1 + self.msselect_max_rows:
					page_table[page] = { 'rows': lrow - 1, 'offset': 0, 'boxes': box_table }
					if page > 0:
						page_table[page]['offset'] = page_table[page - 1]['offset'] + page_table[page - 1]['rows']
					box_table = {}
					page += 1
					page_tagi = ctl_info['order'].index( tag )
					frow = 1
					lrow = 1
					max_tag_len = 1
			else:
				if frow + 1 > 1 + self.msselect_max_rows:
					page_table[page] = { 'rows': lrow - 1, 'offset': 0, 'boxes': box_table }
					if page > 0:
						page_table[page]['offset'] = page_table[page - 1]['offset'] + page_table[page - 1]['rows']
					box_table = {}
					page += 1
					page_tagi = ctl_info['order'].index( tag )
					frow = 1
					lrow = 1
					max_tag_len = 1

			# fill one tag into layout, preset result for tag
			tag_row = lrow
			if tag is not None:
				frow += 1
				lrow += 1
			for mseries in tag_info[tag]:
				if tag is None:
					box_table[lrow] = { 'tag': None, 'series': [mseries], 'sub': [] }
					result[mseries] = (False, False)
					frow += 1
				lrow += 1
			if tag is not None:
				box_table[tag_row] = { 'tag': tag, 'series': tag_info[tag], 'sub': list( range( tag_row + 1, lrow ) ) }
				result[tag] = (False, False)
				for mseries in tag_info[tag]:
					result[mseries] = (False, False)

		# finish last page
		page_table[page] = { 'rows': lrow - 1, 'offset': 0, 'boxes': box_table }
		if page > 0:
			page_table[page]['offset'] = page_table[page - 1]['offset'] + page_table[page - 1]['rows']
		box_table = {}

		ctl_info['pages'] = page_table   # page control info
		ctl_info['result'] = result      # storage for checkbox state
		return ctl_info


	def _msselect_create_page( self, page ):
		page_rows = self.msselect_ctl_info['pages'][page]['rows']
		boxes = self.msselect_ctl_info['pages'][page]['boxes']

		dialog = Globals.DIALOGS.MEASUREMENTLISTDIALOGTITLE
		if self.msselect_iter_cols:
			dialog += Globals.DIALOGS.MEASUREMENTLISTDIALOGTITLE_ITERATION

		dialog = dialog.format( page_rows + 3, 2 if self.msselect_iter_cols else 4 )

		row = 1
		for i in boxes:
			tag = boxes[i]['tag']
			mseries_list = boxes[i]['series']
			if tag is not None:
				# tag checkbox
				if self.msselect_iter_cols:
					dialog += Globals.DIALOGS.MEASUREMENTLISTDIALOG_TAG_I.format( row )
				else:
					dialog += Globals.DIALOGS.MEASUREMENTLISTDIALOG_TAG.format( row )
				row += 1

			# sub mseries checkboxes
			for mseries in mseries_list:
				if self.msselect_iter_cols:
					dialog += Globals.DIALOGS.MEASUREMENTLISTDIALOG_MS_I.format( row, mseries )
				else:
					dialog += Globals.DIALOGS.MEASUREMENTLISTDIALOG_MS.format( row, mseries )

				row += 1

		dialog += Globals.DIALOGS.MEASUREMENTLISTDIALOGEND.format( row, row + 1 )

		dlg = gom.script.sys.create_user_defined_dialog( content=dialog )
		return dlg

	def _msselect_create_pages( self ):
		# mseries left/right check for drc extension
		def	_left_right_check( widget, widget_iter, mseries, result ):
			if Utils.left_right_replace( mseries ) == mseries:
				self.log.debug( 'Disable {} - no side mark in name'.format( mseries ) )
				result[mseries] = ( None, None )
				widget.enabled = False
				widget.tooltip = Globals.LOCALIZATION.msg_DC_no_slave_mlist_found
				if self.msselect_iter_cols:
					widget_iter.enabled = False
			try:
				gom.app.project.measurement_series[Utils.left_right_replace( mseries )]
			except:
				self.log.debug( 'Disable {} - no mseries found for other side'.format( mseries ) )
				result[mseries] = ( None, None )
				widget.enabled = False
				widget.tooltip = Globals.LOCALIZATION.msg_DC_no_slave_mlist_found
				if self.msselect_iter_cols:
					widget_iter.enabled = False

		# prepare label for all measurements category
		all_untagged = Globals.LOCALIZATION.dialog_DC_ms_all_untagged
		all_no_tags = Globals.LOCALIZATION.dialog_DC_ms_all
		self.msselect_all_ms = all_untagged if self.msselect_ctl_info['tags'] else all_no_tags

		no_pages = len( self.msselect_ctl_info['pages'] )
		dlgs = []
		for page in range( no_pages ):
			dlg = self._msselect_create_page( page )

			# localize
			dlg.title = Globals.LOCALIZATION.dialog_DC_ms_title
			if Globals.DIALOGS.has_widget( dlg, 'label_title' ):
				dlg.label_title.text = Globals.LOCALIZATION.dialog_DC_ms_text
			if Globals.DIALOGS.has_widget( dlg, 'label' ):
				dlg.label.text = Globals.LOCALIZATION.dialog_DC_ms_align
			if Globals.DIALOGS.has_widget( dlg, 'button_ok' ):
				dlg.button_ok.text = Globals.LOCALIZATION.dialog_DC_ms_start
			if Globals.DIALOGS.has_widget( dlg, 'button_cancel' ):
				dlg.button_cancel.text = Globals.LOCALIZATION.dialog_DC_ms_abort

			# pre-configure layout, preset results
			boxes = self.msselect_ctl_info['pages'][page]['boxes']
			offset = self.msselect_ctl_info['pages'][page]['offset']
			result =  self.msselect_ctl_info['result']
			for row, box in boxes.items():
				if box['tag'] is None:
					widget_iter = None
					if self.msselect_iter_cols:
						# remove Iter option for calibration
						widget_iter = getattr( dlg, 'checkboxIter{}'.format( row ) )
						widget_iter.enabled = False
						widget_iter.visible = False
						mseries = box['series'][0]
						result[mseries] = ( result[mseries][0], None )

					# Note: left/right not necessary for calibration
					continue

				# apply tag formatting
				widget = getattr( dlg, 'checkbox{}'.format( row ) )
				widget.title = self.msselect_tag_format.format(
					box['tag'] if box['tag'] is not True else self.msselect_all_ms )

				# fully uncollapsed dialog
				if self.msselect_ctl_info['full']:
					widget = getattr( dlg, 'button_tag{}'.format( row ) )
					widget.text = '-'
					widget.enabled = False

				# sub mseries for a tag
				for i in range( len( box['series'] ) ):
					mseries = box['series'][i]
					row = box['sub'][i]
					# indent sub mseries a bit
					widget = getattr( dlg, 'checkbox{}'.format( row ) )
					widget.title = '  ' + mseries

					if self.msselect_left_right_check:
						widget_iter = None
						if self.msselect_iter_cols:
							widget_iter = getattr( dlg, widget.name.replace( 'checkbox', 'checkboxIter' ) )
						_left_right_check( widget, widget_iter, mseries, result )

			# button visible / active
			if not self.msselect_ctl_info['multi']:
				dlg.button_prev.enabled = False
				dlg.button_prev.visible = False
				dlg.button_next.enabled = False
				dlg.button_next.visible = False
			else:
				if page == 0:
					dlg.button_prev.enabled = False
					dlg.button_prev.visible = True
				if page == no_pages - 1:
					dlg.button_next.enabled = False
					dlg.button_next.visible = True

			dlgs.append( dlg )

		return dlgs


	def _msselect_configure_page( self, dlg, page ):
		if self.msselect_ctl_info['full']:
			return

		# reset uncollapsed tag
		self.msselect_open_row = None

		boxes = self.msselect_ctl_info['pages'][page]['boxes']
		offset = self.msselect_ctl_info['pages'][page]['offset']
		for row, box in boxes.items():
			if box['tag'] is None:
				continue

			# reset tag button
			mseries = box['tag']
			if not self.msselect_ctl_info['full']:
				btn = getattr( dlg, 'button_tag{}'.format( row ) )
				btn.text = '+'

			# collapse any uncollapsed tag
			for i in range( len( box['series'] ) ):
				mseries = box['series'][i]
				row = box['sub'][i]
				spacer = getattr( dlg, 'spacer_col1_ms{}'.format( row ) )
				widget = getattr( dlg, 'checkbox{}'.format( row ) )
				widget_iter = None
				if self.msselect_iter_cols:
					widget_iter = getattr( dlg, 'checkboxIter{}'.format( row ) )

				spacer.visible = False
				widget.visible = False
				if self.msselect_iter_cols:
					widget_iter.visible = False

	def _msselect_set_results( self, dlg, page ):
		boxes = self.msselect_ctl_info['pages'][page]['boxes']
		offset = self.msselect_ctl_info['pages'][page]['offset']
		result = self.msselect_ctl_info['result']
		for row, box in boxes.items():
			tag_row = row

			# set checkbox state for None tag
			widget = getattr( dlg, 'checkbox{}'.format( row ) )
			if box['tag'] is None:
				mseries = box['series'][0]
				if isinstance( result[mseries][0], bool ):
					widget.value = result[mseries][0]
				continue

			# set tag checkbox
			tag_mseries = box['tag']
			tag_widget = widget
			if isinstance( result[tag_mseries][0], bool ):
				tag_widget.value = result[tag_mseries][0]

			# set state of sub mseries for a tag
			# also determine mixed checkbox state
			mixed = set()
			for i in range( len( box['series'] ) ):
				mseries = box['series'][i]
				row = box['sub'][i]

				widget = getattr( dlg, 'checkbox{}'.format( row ) )
				widget_iter = None
				if self.msselect_iter_cols:
					widget_iter = getattr( dlg, 'checkboxIter{}'.format( row ) )

				mixed.add( result[mseries][0] )
				if isinstance( result[mseries][0], bool ):
					widget.value = result[mseries][0]
				if self.msselect_iter_cols and isinstance( result[mseries][1], bool ):
					widget_iter.value = result[mseries][1]

			# mixed display for tag
			widget = getattr( dlg, 'checkbox{}'.format( tag_row ) )
			if mixed == set( [None] ):
				# no active sub mseries
				# also deactivate tag and set None result
				tag_widget.value = False
				tag_widget.enabled = False
				tag_widget.tooltip = Globals.LOCALIZATION.msg_DC_no_slave_mlist_found
				result[tag_mseries] = ( None, None )
			elif len( mixed ) > 1 and True in mixed and False in mixed:
				widget.title = self.msselect_partial_mark + self.msselect_tag_format.format(
					box['tag'] if box['tag'] is not True else self.msselect_all_ms )
			else:
				widget.title = self.msselect_tag_format.format(
					box['tag'] if box['tag'] is not True else self.msselect_all_ms )


	def _show_select_measurement(self, series):
		'''
		build and show dialog for measurement series selection
		returns list of measurement series names and (optional) mseries selected for alignment iteration
		'''
		if self.Calibration.MeasureList is not None:
			series = [self.Calibration.MeasureList.name] + series
		# should never happen, already catched in 'perform'
		if not len( series ):
			return [None, None]

		# compile tag and dialog control information
		self.msselect_dialogs = []
		self.msselect_dialog = None
		self.msselect_page = 0
		self.msselect_open_row = None
		self.msselect_ctl_info = self._get_mseries_taginfo( series )

		# iteration column ?
		self.msselect_iter_cols = False
		if Globals.SETTINGS.AlignmentIteration:
			self.msselect_iter_cols = True

		# activate additional requirements for mseries selection in drc extension
		self.msselect_left_right_check = (Globals.DRC_EXTENSION is not None
			and Globals.FEATURE_SET.DRC_PRIMARY_INST
			and not Globals.FEATURE_SET.DRC_UNPAIRED)

		# create and localize mseries select dialog(s)
		self.msselect_dialogs = self._msselect_create_pages()
		self.msselect_page = 0
		self.msselect_dialog = self.msselect_dialogs[self.msselect_page]

		try:
			result = False
			while result is not True:
				self._msselect_configure_page( self.msselect_dialog, self.msselect_page )
				self._msselect_set_results( self.msselect_dialog, self.msselect_page )
				self.msselect_dialog.handler = self._handler_measurementlist
				result = gom.script.sys.show_user_defined_dialog( dialog=self.msselect_dialog )

			# collect selected mseries
			no_pages = len( self.msselect_ctl_info['pages'] )
			iter_ms = None
			mmts = []
			for page in range( no_pages ):
				boxes = self.msselect_ctl_info['pages'][page]['boxes']
				for t, box in boxes.items():
					for mseries in box['series']:
						measure, iter = self.msselect_ctl_info['result'][mseries]
						if measure:
							mmts.append( mseries )
						if iter:
							iter_ms = mseries

			return ( mmts, iter_ms )
		except gom.BreakError:
			raise
		except Exception as e:
			self.log.exception( '{}'.format( e ) )
			return [None, None]


	def _handler_measurementlist( self, widget ):
		def find_box( page, target ):
			boxes = self.msselect_ctl_info['pages'][page]['boxes']
			for row, box in boxes.items():
				if target == row:
					return box, 'tag'
				if target in box['sub']:
					return box, box['sub'].index( target )
			# should not happen
			return None, None
		def toggle_tag( row ):
			box, what = find_box( self.msselect_page, row )
			# what must be tag
			widget = getattr( self.msselect_dialog, 'button_tag{}'.format( row ) )
			widget.text = '-' if widget.text == '+' else '+'
			visi = widget.text == '-'
			for i in box['sub']:
				getattr( self.msselect_dialog, 'spacer_col1_ms{}'.format( i ) ).visible = visi
				getattr( self.msselect_dialog, 'checkbox{}'.format( i ) ).visible = visi
				if self.msselect_iter_cols:
					getattr( self.msselect_dialog, 'checkboxIter{}'.format( i ) ).visible = visi
			if not visi:
				self.msselect_open_row = None
			else:
				self.msselect_open_row = row
		def set_iter_result( page, row, value ):
			result = self.msselect_ctl_info['result']
			box, what = find_box( page, row )
			# ignored for tags
			if what == 'tag':
				return
			mseries = box['series'][what]
			result[mseries] = ( result[mseries][0], value )

			# remove other True values
			if value:
				for other_ms in result.keys():
					if result[other_ms][1] and other_ms != mseries:
						result[mseries] = ( result[mseries][0], False )
		def set_mseries_result( page, row, value ):
			result = self.msselect_ctl_info['result']
			box, what = find_box( page, row )
			mseries = None
			if what == 'tag':
				if box['tag'] is None:
					mseries = box['series'][0]
				else:
					mseries = box['tag']
			else:
				mseries = box['series'][what]
			result[mseries] = ( value, result[mseries][1] )

			# de-/select all sub mseries for a tag
			if what == 'tag':
				for mseries in box['series']:
					# do not switch inactive checkbox
					if result[mseries][0] is not None:
						result[mseries] = ( value, result[mseries][1] )
			else:
				# unset/set corresponding tag, if necessary
				states = set()
				for mseries in box['series']:
					states.add( result[mseries][0] )
				if False not in states:
					result[box['tag']] = ( True, result[box['tag']][1] )
				else:
					result[box['tag']] = ( False, result[box['tag']][1] )

		widget_name = ''
		if not isinstance( widget, str ):
			widget_name = widget.name

		if widget_name.startswith( 'button_tag' ):
			# open / close tag
			row = int( widget.name[10:])
			if self.msselect_open_row is not None and self.msselect_open_row != row:
				# close open tag
				toggle_tag( self.msselect_open_row )
			toggle_tag( row )
		elif widget_name.startswith( 'checkboxIter' ):
			# mseries selection for iteration
			row = int( widget.name[12:])
			set_iter_result( self.msselect_page, row, widget.value )
			# also force the corresponding mseries
			if widget.value:
				set_mseries_result( self.msselect_page, row, True )
			# refresh selection boxes
			self._msselect_set_results( self.msselect_dialog, self.msselect_page )
		elif widget_name.startswith( 'checkbox' ):
			# tag or mseries selection for measuring
			row = int( widget.name[8:])
			set_mseries_result( self.msselect_page, row, widget.value )
			# also turn off corresponding alignment iteration checkbox
			if self.msselect_iter_cols and not widget.value:
				set_iter_result( self.msselect_page, row, False )
			# refresh selection boxes
			self._msselect_set_results( self.msselect_dialog, self.msselect_page )

		# control buttons
		if widget == self.msselect_dialog.button_prev:
			old = self.msselect_dialog
			self.msselect_page -= 1
			self.msselect_dialog = self.msselect_dialogs[self.msselect_page]
			gom.script.sys.close_user_defined_dialog( dialog=old )
		elif widget == self.msselect_dialog.button_next:
			old = self.msselect_dialog
			self.msselect_page += 1
			self.msselect_dialog = self.msselect_dialogs[self.msselect_page]
			gom.script.sys.close_user_defined_dialog( dialog=old )
		elif widget == self.msselect_dialog.button_ok:
			gom.script.sys.close_user_defined_dialog( dialog=self.msselect_dialog, result=True )
		elif widget == self.msselect_dialog.button_cancel:
			gom.script.sys.close_user_defined_dialog( dialog=self.msselect_dialog )
			raise gom.BreakError()

		self.msselect_dialog.button_ok.enabled = any( True for res in self.msselect_ctl_info['result'].values() if res[0] is True )


	def manual_mlist_evaluation(self, tritop):
		# select a report, use the first matching report
		reps = gom.app.project.reports.filter( 'report_title == "AlignmentIteration"' )
		if len(reps) == 0:
			reps = gom.app.project.reports.filter( '"AlignmentIteration" in tags' )
		if len(reps) == 0:
			reps = gom.app.project.reports

		gom.script.sys.recalculate_project()

		try:
			gom.script.explorer.apply_selection( selection=reps[0] )
			gom.script.manage_alignment.set_alignment_active ( cad_alignment = gom.app.project.alignments[reps[0].alignment.name] )
			gom.script.sys.recalculate_alignment( alignment = gom.app.project.alignments[reps[0].alignment.name] )
		except:
			pass
		gom.script.sys.switch_to_report_workspace()
		# Dialog result: True => Use, False => Abort, None => Retry
		res = Globals.DIALOGS.show_mlist_retry_dialog()
		gom.script.sys.switch_to_inspection_workspace()
		return res

	def optional_photogrammetry_checks(self):
		do_checks = True
		if Globals.DRC_EXTENSION is not None:
			res = Globals.DRC_EXTENSION.sync_for_iteration_in_tritop( self )
			if res is False:
				return False

			# no checks on secondary side in paired drc
			if Globals.DRC_EXTENSION.SecondarySideActive():
				do_checks = False

		res = True
		if do_checks:
			manual_res = True
			drc_res = True
			if self.alignment_mseries is not None:
				need_validation = False
				try:
					need_validation = gom.app.project.measurement_series[
						self.alignment_mseries].type == 'photogrammetry_measurement_series'
				except:
					pass
				if need_validation:
					manual_res = self.manual_mlist_evaluation( tritop=True )

			if Globals.DRC_EXTENSION is not None:
				drc_res = Globals.DRC_EXTENSION.reference_cube_check()

			# preference: retry over abort
			if manual_res is None or drc_res is None: # retry
				res = None
			elif not manual_res or not drc_res: # abort
				res = False

		if Globals.DRC_EXTENSION is not None:
			res = Globals.DRC_EXTENSION.tritop_continuation( self, res )

		self.log.debug( 'Optional photo checks - result {}'.format( res ) )
		return res

	def check_for_iteration(self, atos_mlist):
		if self.alignment_mseries is None:
			return True
		if self.alignment_mseries != atos_mlist:
			return True

		if Globals.DRC_EXTENSION is not None:
			res = Globals.DRC_EXTENSION.sync_for_iteration_in_atos( self, atos_mlist )
			if res is False:
				return False

		res = True
		if ( Globals.DRC_EXTENSION is None
				or Globals.DRC_EXTENSION.PrimarySideActive()
				or not Globals.DRC_EXTENSION.SecondarySideActive() ):
			res = self.manual_mlist_evaluation( False )

		if Globals.DRC_EXTENSION is not None:
			res = Globals.DRC_EXTENSION.atos_continuation( self, res )

		self.log.debug( 'Alignment iteration check - result {}'.format( res ) )
		return res


	def get_mseries_for_msetups( self, wcfgs, all_photo, all_atos, all_calib, all_hyper ):
		'''Functional variant of collectCompatibleSeries.
		Parameters are lists of names of measuring setups and measuring series.
		It is an error if a setup or series is not present in the project.
		Returns lists of filtered names of measuring series for the given measuring setups.
		'''
		photo_series = [mseries for mseries in all_photo
			if self.Sensor.isMListPartOfMeasuringSetups(gom.app.project.measurement_series[mseries], wcfgs)]
		atos_series = [mseries for mseries in all_atos
			if self.Sensor.isMListPartOfMeasuringSetups(gom.app.project.measurement_series[mseries], wcfgs)]
		calib_series = [mseries for mseries in all_calib
			if self.Sensor.calibration_ms_compatible(gom.app.project.measurement_series[mseries], wcfgs)]
		hyperscale_series = [mseries for mseries in all_hyper
			if self.Sensor.calibration_ms_compatible(gom.app.project.measurement_series[mseries], wcfgs)]
		return (photo_series, atos_series, calib_series, hyperscale_series)

	def filter_mseries_for_msetups( self, wcfgs ):
		(self.Comp_photo_series, self.Comp_atos_series,	self.Comp_calib_series, self.Comp_hyperscale_series) = self.get_mseries_for_msetups(
			wcfgs, self.Backup_photo_series, self.Backup_atos_series, self.Backup_calib_series, self.Backup_hyperscale_series )

		self.log.info('Filtered Compatible photogrammetry measurement series {}'.format(
			list(self.Comp_photo_series)))
		self.log.info('Filtered Compatible ATOS measurement series {}'.format(
			list(self.Comp_atos_series)))
		self.log.info('Filtered Compatible calibration measurement series {}'.format(
			list(self.Comp_calib_series)))
		self.log.info('Filtered Compatible hyperscale measurement series {}'.format(
			list(self.Comp_hyperscale_series)))

		# reset first, then select first compatible ms
		self.Calibration.MeasureList = None
		for ms in self.Comp_calib_series:
			self.Calibration.MeasureList = gom.app.project.measurement_series[ms]
			break
		self.HyperScale.MeasureList = None
		for ms in self.Comp_hyperscale_series:
			self.HyperScale.MeasureList = gom.app.project.measurement_series[ms]
			break

	def detect_msetups_with_different_cad_positions( self ):
		if len( self.Compatible_wcfgs ) < 2:
			return False

		# filter to all wcfgs with an independent photogrammetry
		wcfgs = []
		for msetup in self.Compatible_wcfgs:
			(tritops, _, _, _) = self.get_mseries_for_msetups( [msetup], self.Comp_photo_series, [], [], [] )
			tritop_master = None
			for tritopname in tritops:
				tritop = gom.app.project.measurement_series[tritopname]
				if tritop.reference_points_master_series is None:
					tritop_master = tritop
					break
			if tritop_master is not None:
				wcfgs.append( msetup )

		# Not every setup has a tritop master => Mixed case is not supported, try standard behaviour
		if len( self.Compatible_wcfgs ) != len( wcfgs ):
			return False

		# test all CAD positions against CAD position of first msetup
		# return True, if any difference is found
		test = Utils.CartesianMat4x4( gom.Vec3d( 100, 100, 100 ) )
		ref_trafo = gom.app.project.measuring_setups[self.Compatible_wcfgs[0]].get( 'cad_position.transformation' )
		for msetup in self.Compatible_wcfgs[1:]:
			(eq, _) = test.testValue(
				ref_trafo, gom.app.project.measuring_setups[msetup].get( 'cad_position.transformation' ) )
			if not eq:
				return True

		return False

	@staticmethod
	def get_original_alignment():
		aligns = [a for a in gom.app.project.alignments	if a.get( 'alignment_is_original_alignment' )]
		return aligns[0]
	def get_original_or_initial_alignment( self ):
		aligns = [a for a in gom.app.project.alignments	if a.get( 'alignment_is_original_alignment' )]
		if aligns == []:
			aligns = [a for a in gom.app.project.alignments	if a.get( 'alignment_is_initial' )]
		return aligns[0]


	def checkFreeDiskSpace(self, path, errorlimit, warninglimit, warning_shown=None):
		if warning_shown is None:
			warning_shown = []
		if errorlimit != 0 or warninglimit != 0:
			freespace = gom_windows_utils.get_free_disc_space( os.path.abspath( os.path.normcase( path ) ) )
			if freespace is None:
				self.log.warning( 'Cannot determine free disk space on path "{}"'.format( path ) )
		if errorlimit != 0:
			if freespace is not None and freespace < errorlimit:
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.DISC_SPACE_ERROR, '',
						Globals.LOCALIZATION.msg_disc_space_error.format(freespace, path).replace('<br/>',' '))
					return False
				Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
					Globals.LOCALIZATION.msg_disc_space_error.format(freespace, path),
					None, False )
				return False
		if warninglimit != 0:
			if freespace is not None and freespace < warninglimit:
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceWarning(InlineConstants.PLCWarnings.DISC_SPACE_WARNING, '',
						Globals.LOCALIZATION.msg_disc_space_warning.format(freespace, path).replace('<br/>',' '))
					warning_shown.append(True)
					return True
				return Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
					Globals.LOCALIZATION.msg_disc_space_warning.format(freespace, path),
					None, True, Globals.LOCALIZATION.errordialog_button_continue )

		return True

	def perform( self, start_dialog_input ):
		'''
		This function starts the evaluation process.

		Returns:
		True  - if the successful i.e. all measurements successful and not deviation out of tolerance.
		False - otherwise
		'''
		warning_shown = []
		if (not self.checkFreeDiskSpace(Globals.SETTINGS.SavePath, Globals.SETTINGS.DiscFullErrorLimitSavePath, Globals.SETTINGS.DiscFullWarningLimitSavePath, warning_shown) or
			not self.checkFreeDiskSpace(gom.app.get ( 'local_all_directory' ), Globals.SETTINGS.DiscFullErrorLimitLogPath, Globals.SETTINGS.DiscFullWarningLimitLogPath, warning_shown)):
			if not len(warning_shown) and Globals.SETTINGS.Inline: # reset last warning
				InlineConstants.resetMeasuringInstanceWarning(InlineConstants.PLCWarnings.DISC_SPACE_WARNING)
			if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActiveForError():
				Globals.DRC_EXTENSION.sendStartFailure(Globals.LOCALIZATION.msg_DC_slave_drivefull)
			return None
		if not len(warning_shown) and Globals.SETTINGS.Inline: # reset last warning
			InlineConstants.resetMeasuringInstanceWarning(InlineConstants.PLCWarnings.DISC_SPACE_WARNING)

		# start MultiRobot Measure inline specific evaluation
		if ( Globals.SETTINGS.MultiRobot_Mode and Globals.SETTINGS.Inline
			and Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT ):
			res = Globals.DRC_EXTENSION.evaluation( self, start_dialog_input )
			self.setExecutionMode( ExecutionMode.Full )
			return res

		self.check_VMRlight()  # always set vmrlight flag
		Globals.SETTINGS.ManualMultiPartMode = self.analysis.check_manual_multipart_mseries()
		if Globals.SETTINGS.ManualMultiPartMode:
			self.log.info( 'Activating Manual Multipart Mode' )
		if not self.hasVMR:
			if not self.check_VMRlight():
				Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
					Globals.LOCALIZATION.msg_cannot_execute,
					Globals.SETTINGS.SavePath, False )
				if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActiveForError():
					Globals.DRC_EXTENSION.sendStartFailure(Globals.LOCALIZATION.msg_DC_slave_invalid_project)
				return None  # dont save the project

		# check consistency
		if Globals.FEATURE_SET.ONESHOT_MODE:
			pass # no consistency check
		else:
			if not self.Global_Checks.checkProjectConsistency():
				if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActiveForError():
					Globals.DRC_EXTENSION.sendStartFailure(Globals.LOCALIZATION.msg_DC_slave_invalid_project)
				return None

		# Optional: Build mapping "part" => "evaluation template"
		EvaluationAnalysis.multipart_build_evaluation_map()

		with Measure.TemporaryWarmupDisable( self.Sensor ) as warmup: # no warmuptime on direct init
			if not self.Sensor.initialize():
				if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActiveForError(): #  todo auch für master???
					Globals.DRC_EXTENSION.sendStartFailure('{} - '+Globals.LOCALIZATION.msg_sensor_failed_init)
				return None

		if not self.collectCompatibleSeries():
			if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActiveForError():
				Globals.DRC_EXTENSION.sendStartFailure('{} - '+Globals.LOCALIZATION.msg_sensor_failed_init)
			return None

		# check consistency - part 2: with initialized sensor
		if not self.Global_Checks.checkProjectConsistencyWithSensor():
			if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActiveForError():
				Globals.DRC_EXTENSION.sendStartFailure(Globals.LOCALIZATION.msg_DC_slave_invalid_project)
			return None

		steps = 2  # initialize, reports
		if not self.IsVMRlight:
			for ms in self.Comp_photo_series:
				if not self.is_measurement_series_executable( ms ):
					continue
				steps += 1
		for ms in self.Comp_atos_series:
			if not self.is_measurement_series_executable( ms ):
				continue
			steps += 1

		steps += 1  # polygonize
		if Globals.SETTINGS.Async:
			steps -= 2  # polygonize, reports

		if self.getExecutionMode() == ExecutionMode.ForceCalibration:
			self.Comp_photo_series.clear()
			self.Comp_atos_series.clear()
		elif self.getExecutionMode() == ExecutionMode.ForceTritop:
			self.Comp_atos_series.clear()
			if not len( self.Comp_photo_series ):
				if Globals.SETTINGS.Inline:
					InlineConstants.sendMeasureInstanceError(
						InlineConstants.PLCErrors.MEAS_MLIST_ERROR, '',
						Globals.LOCALIZATION.msg_photogrammetry_no_list_defined )
				self.setExecutionMode( ExecutionMode.Full )
				if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActiveForError():
					Globals.DRC_EXTENSION.sendStartFailure('{} - '+Globals.LOCALIZATION.msg_photogrammetry_no_list_defined)
				return None

		# detect calibration series
		self.Calibration.MeasureList = None  # reset first
		for ms in self.Comp_calib_series:
			# Note, with multiple msetups this is only a placeholder
			# The actually used calibration mseries may be different depending on active msetup
			self.Calibration.MeasureList = gom.app.project.measurement_series[ms]
			break
		self.HyperScale.MeasureList = None  # reset first
		for ms in self.Comp_hyperscale_series:
			self.HyperScale.MeasureList = gom.app.project.measurement_series[ms]
			break

		for ms in self.Comp_photo_series + self.Comp_atos_series:
			if not self.is_measurement_series_executable( ms ):
				continue
			break
		else:
			# no executable photo/atos mseries
			if self.Calibration.MeasureList is not None:  # only calibrationlist defined
				steps = 2  # initialize, calibration
			else:
				self.showErrorNoCompatibleSeries()
				if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActiveForError():
					Globals.DRC_EXTENSION.sendStartFailure(Globals.LOCALIZATION.msg_DC_slave_invalid_project)
				return None

		if Globals.SETTINGS.Inline:
			if len(self.Compatible_wcfgs):
				try:
					not_available = gom.app.project.measuring_setups[self.Compatible_wcfgs[0]].get (
						'sensor_configuration.photogrammetric_measuring_volume') is None
					if not_available:
						Globals.CONTROL_INSTANCE.send_signal(
							Communicate.Signal( Communicate.SIGNAL_CONTROL_PHOTOGRAMMETRY_HARDWARE_NOT_AVAILABLE, str(1) ) )
				except:
					pass

		self.Dialog.process_msg( maxstep = steps )

		# temperature acquisition method '*ask*': activate temperature dialog of Kiosk
		if not Globals.SETTINGS.OfflineMode and gom.app.sys_measurement_temperature_source in ["ask_if_required", "ask_per_project"]:
			if Globals.DRC_EXTENSION is not None and (Globals.DRC_EXTENSION.SecondarySideActive() or Globals.DRC_EXTENSION.PrimarySideActive()):
				if Globals.DRC_EXTENSION.SecondarySideActiveForError():
					Globals.DRC_EXTENSION.sendStartFailure('{} - '+Globals.LOCALIZATION.msg_DC_temperature_error_title)
				else:
					Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_DC_temperature_error_title,
											Globals.LOCALIZATION.msg_DC_temperature_error_text,
											None, False )
				return None
			Globals.SETTINGS.Thermometer_ShowDialog = True

		# template is compatible send drc start acknowledge
		if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActive():
			Globals.DRC_EXTENSION.sendStartSuccess()
		try:
			res = self._evaluate( start_dialog_input )
		except Globals.EXIT_EXCEPTIONS:
			raise
		except (gom.BreakError, RuntimeError) as e:
			if isinstance(e, RuntimeError) and e.args != ('',''):
				raise
			self.log.error('Catched user break {}/{}'.format(type(e), e))
			return False
		finally:
			self.setExecutionMode( ExecutionMode.Full )
			FixturePositionCheck.FixturePositionCheck.tear_down()

		self.log.info( 'evaluation finished with result: {}'.format( res ) )
		return res

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
				gom.script.sys.set_project_keywords (
					keywords = {key: val} )
			else:
				# create new keyword including the description
				gom.script.sys.set_project_keywords (
					keywords = {key: val},
					keywords_description = {key: desc} )

		# set additional project keywords
		for (key, desc, _, _, *_) in Globals.ADDITIONAL_PROJECTKEYWORDS:
			if key is None:
				continue
			val = start_dialog_input.get( key, '' )
			if key in existing_kws:
				# only set value
				gom.script.sys.set_project_keywords (
					keywords = {key: val} )
			else:
				# create new keyword including the description
				gom.script.sys.set_project_keywords (
					keywords = {key: val},
					keywords_description = {key: desc} )

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
		existing_kws = part.element_keywords
		existing_kws = [kw[5:] for kw in existing_kws]

		for kw, val, desc in kw_values:
			if kw in existing_kws:
				gom.script.cad.edit_element_keywords(
					elements=[part],
					set_value={kw: val})
			else:
				gom.script.cad.edit_element_keywords(
					add_keys=[kw],
					description={kw: desc},
					elements=[part],
					set_value={kw: val} )

	def save_project( self ):
		'''
		Saves the project to the directory specified by SavePath in the config.
		'''
		currtime = time.strftime( Globals.SETTINGS.TimeFormatProject )
		if Globals.SETTINGS.AutoNameProject:
			try:
				part_nr = gom.app.project.get( 'user_part_nr' )
				prj_name = '{}_{}'.format( part_nr, currtime )
			except:
				prj_name = currtime
		else:
			prj_name = Globals.SETTINGS.ProjectName + '_' + currtime
		prj_name = Utils.sanitize_filename( prj_name )
		gom.script.sys.set_project_keywords (
			keywords = {'GOM_KIOSK_TimeStamp': currtime},
			keywords_description = {'GOM_KIOSK_TimeStamp': 'internal'} )

		if Globals.FEATURE_SET.ONESHOT_MODE and not(
				Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActive() ):
			try:
				gom.script.sys.save_project() # if save fails its a readonly project/template currently open use the default save_as
				return
			except:
				pass

		if Globals.SETTINGS.CurrentTemplateIsConnected:
			# SW2021-1147: How does this go together with the synchronization process?
			pass
		else:
			gom.script.sys.save_project_as( file_name = os.path.join( Globals.SETTINGS.SavePath, prj_name ) )

	def close_and_move_measured_project_if_needed(self):
		measured_dir = os.path.normpath( os.path.join( Globals.SETTINGS.SavePath, Globals.SETTINGS.MeasureSavePath ) )
		if not os.path.exists( measured_dir ):
			os.mkdir( measured_dir )

		project_file = os.path.normpath( gom.app.project.get ('project_file') )
		gom.script.sys.close_project()
		if os.path.normpath( Globals.SETTINGS.SavePath ) == os.path.dirname(project_file):
			new_file = os.path.join(measured_dir, os.path.basename(project_file))
			os.rename(project_file, new_file)
			return new_file
		return project_file

	@staticmethod
	def export_path_info():
		'''Returns a tuple of the project name and the export path.
		Prerequisite: project must still be open when calling this function.
		'''
		project_name = gom.app.project.get( 'name' )
		try:
			used_template = gom.app.project.get( 'template.relative_path' )
			index = used_template[-1].find( '.project_template' )
			if index > 0:
				used_template[-1] = used_template[-1][:index]
		except:
			used_template=['unknown']
		used_template = [p.rstrip('. ') for p in used_template]
		export_path = os.path.join( Globals.SETTINGS.SavePath, *used_template )
		return ( project_name, export_path )

	@staticmethod
	def project_name_for_part( part, result, partname='' ):
		'''
		Generate a name of the form: <serial>_<partname>_<timestamp> for per-part exports.
		Part keywords must have been activated before calling this (use activate_part_keywords).
		For cases where the original 'part' is not (or no longer) present in the project,
				override the 'part' name with the parameter 'partname'.
		'''
		try:
			timestamp = gom.app.project.user_GOM_KIOSK_TimeStamp
		except:
			timestamp = time.strftime( Globals.SETTINGS.TimeFormatProject )
			gom.script.sys.set_project_keywords (
				keywords = {'GOM_KIOSK_TimeStamp': timestamp},
				keywords_description = {'GOM_KIOSK_TimeStamp': 'internal'} )
		# try to get serial no
		# if part has no nominal, this is the overall project serial no
		try:
			serial = gom.app.project.user_part_nr
		except:
			serial = 'unknown'
		# add the part name as additional identification
		if partname != '':
			serial = serial + '_' + partname
		else:
			serial = serial + '_' + part.name
		project_name = '{}_{}'.format( serial, timestamp )
		if not result:
			project_name += Globals.SETTINGS.FailedPostfix
		return project_name

	def display_measurement_positions( self, show ):
		'''
		Displays or hides the cameras symbolizing the measurement positions in the specified measurement series
		Arguments:
		show - True, 	if the cameras should be displayed
			False, 	otherwise
		'''
		try:
			gom.script.sys.edit_properties (
				data=Utils.real_measurement_series(),
				prim_draw_cameras=show )
		except Exception:
			pass

	def measurement_series_home_pos_check( self ):
		'''
		Checks if all measurement series start and end with an homeposition

		Returns:
		True	-	if all series start/end with an home position
		False	-	otherwise
		'''
		if not gom.app.project.is_part_project:
			for ms in Utils.real_measurement_series():
				if not len( ms.measurements ):
					continue
				if ms.measurements[0].get( 'type' ) != 'home_position' or ms.measurements[-1].get( 'type' ) != 'home_position':
					self.log.error( 'Series "{}" does not start/end with a home position'.format( ms.get( 'name' ) ) )
					return False
		else:
			for ms in gom.app.project.measurement_paths:
				try:
					if not len( ms.measurement_series.measurements ):
						continue
				except:
					pass
				if ms.path_positions[0].get( 'type' ) != 'home_position' or ms.path_positions[-1].get( 'type' ) != 'home_position':
					self.log.error( 'Series "{}" does not start/end with a home position'.format( ms.get( 'name' ) ) )
					return False
		return True

	def define_active_measuring_series( self, series ):
		'''
		define given measuring series as active
		uses the software default behaviour if the compatibility mode is not active:
		old behaviour: also checks for different measuring setup and if different or VMRlight shows
		a confirm dialog

		returns False if user denies the dialog, True otherwise
		'''
		if Globals.SETTINGS.Inline:
			try:
				gom.script.atos.define_active_measurement_series ( measurement_series = series )
			except RuntimeError as e:
				self.log.error('Define active mseries failed ({})'.format(e))
				InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_ERROR, e.args[0], e.args[1])
				return False
			return True
		if not Globals.SETTINGS.Compat_MeasuringSetup:
			# loop to allow for retries
			while True:
				try:
					gom.interactive.atos.define_active_measurement_series ( measurement_series = series )
				except gom.BreakError:
					self.log.error('User abort define active mlist')
					return False

				# re-check if series is really active and sensor still online
				if not(series.get ('is_active') == gom.MeasurementListActiveState(True)
						and (self.sensor.is_initialized() or Globals.SETTINGS.OfflineMode)):
					self.log.error(
						'MSetup failed or Sensor offline after MSetup ({},{})'.format(
							series.get ('is_active'), self.sensor.is_initialized() ) )
					if self.sensor.is_initialized():
						errmsg = Globals.LOCALIZATION.msg_msetup_sensor_offline
					else:
						errmsg = Globals.LOCALIZATION.msg_msetup_define_active_failed
					res = Globals.DIALOGS.show_errormsg(
						Globals.LOCALIZATION.msg_general_failure_title,
						errmsg,
						None )
					# propagate dialog abort to caller
					if res == False:
						return False
					# all else: retry
				else:
					# msetup activated ok
					break
		else:
			old_ms_setup = self.get_active_measuring_setup_name()
			try:
				gom.script.atos.define_active_measurement_series ( measurement_series = series )
			except RuntimeError as e:
				self.log.error('Define active mseries failed ({})'.format(e))
				res = Globals.DIALOGS.show_errormsg(
					Globals.LOCALIZATION.msg_general_failure_title,
					Globals.LOCALIZATION.msg_msetup_define_active_failed,
					None,
					retry_enabled=False)
				return False
			try:
				new_ms_setup = series.get( 'measuring_setup' )
				if new_ms_setup is None:
					if series.get( 'reference_points_master_series' ) is not None:
						new_ms_setup = series.get( 'reference_points_master_series' ).get( 'measuring_setup' )
					if new_ms_setup is None:
						new_ms_setup = old_ms_setup
				new_ms_setup_name = new_ms_setup.get( 'name' )
			except:
				new_ms_setup = None
			if new_ms_setup is None:
				new_ms_setup_name = old_ms_setup

			if self.IsVMRlight or old_ms_setup != new_ms_setup_name:
				if self.Dialog is not None:
					if not self.Dialog.show_measuringsetup_dialog( series, self.first_measurement_series ):
						self.first_measurement_series = False
						return False
				if new_ms_setup is not None:
					gom.script.automation.define_active_measuring_setup ( measuring_setup = new_ms_setup )
			self.first_measurement_series = False
		return True

	def get_active_measuring_setup_name( self ):
		'''
		returns the current active measuring setup name
		'''
		ms_setups = gom.app.project.measuring_setups.filter( 'is_active' )
		if len( ms_setups ):
			return ms_setups[0].get( 'name' )
		return None

	def is_measurement_series_executable(self, ms, accept_empty=False):
		'''
		returns False if measurement series is empty, or only consists of intermediate/home positions
		'''
		if isinstance( ms, str ):
			ms = gom.app.project.measurement_series[ms]
		if accept_empty and len( ms.measurements ) == 0:
			return True
		for m in ms.measurements:
			# Note: In part-based workflow "continue" never happens
			if m.type=='intermediate_position' or m.type =='home_position':
				continue
			return True
		return False

	def moveDevicesToHome(self):
		'''
		if a home path list exists and the current position is a home position
		and the current measurement series is compatible with the home path list
		move the cell to default state (global home)
		'''
		if not Globals.SETTINGS.MoveAllDevicesToHome:
			return

		if self.IsVMRlight:
			return
		try:
			gom.app.project
		except:
			return

		if not gom.app.project.is_part_project:
			active_mlist = Utils.real_measurement_series( filter='is_active==True' )
			if not len(active_mlist) or not len(active_mlist[0].measurements):
				return
		else:
			active_mlist = gom.app.project.measurement_paths.filter( 'is_active==True' )
			if not len(active_mlist) or not len(active_mlist[0].path_positions):
				return
		active_mlist = active_mlist[0]
		active_wcfg = gom.app.project.measuring_setups.filter('is_active==True')
		if not len(active_wcfg):
			return
		active_wcfg = active_wcfg[0]
		if active_wcfg.get('working_area') is None:
			return

		if not gom.app.project.is_part_project:
			active_pos=active_mlist.measurements.filter('is_current_position==True')
		else:
			active_pos=active_mlist.path_positions.filter('is_current_position==True')
		if not len(active_pos):
			return
		if active_pos[0].get ('type') != 'home_position':
			return
		moveretry = True
		number_of_retries = 0
		only_init = False
		while moveretry:
			with Measure.TemporaryWarmupDisable(self.Sensor) as warmup: # no warmuptime for home movement
				if only_init:
					if not self.Sensor.initialize():
						return
					only_init = False
				else:
					if not self.Sensor.check_for_reinitialize():
						return
			try:
				if Globals.SETTINGS.Inline:
					gom.script.automation.move_to_home_position (all_devices_to_home_and_default_safety_area=True)
				else:
					gom.interactive.automation.move_to_home_position (all_devices_to_home_and_default_safety_area=True)
				moveretry = False
			except Globals.EXIT_EXCEPTIONS:
				raise
			except RuntimeError as e:
				self.log.error( 'failed to move devices to home position {}'.format( e ) )
				errorlog = Verification.ErrorLog()
				state = self.Global_Checks.analyze_error( e, active_mlist, True, errorlog )
				if Globals.SETTINGS.Inline:
					if state == Verification.VerificationState.RetryWithoutCounting:
						continue
					elif state in [Verification.VerificationState.ReInitSensor,
											Verification.VerificationState.OnlyInitSensor]:
						number_of_retries += 1
						if number_of_retries > 2:
							InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MOVE_ERROR, errorlog.Code, errorlog.Error)
							return False
						if state == Verification.VerificationState.OnlyInitSensor:
							only_init = True
						continue
					elif state == Verification.VerificationState.Retry:
						continue
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MOVE_ERROR, errorlog.Code, errorlog.Error)
					return False
				moveretry = Globals.DIALOGS.show_errormsg(
					Globals.LOCALIZATION.msg_general_failure_title,
					errorlog.Error,
					Globals.SETTINGS.SavePath, True, error_code = errorlog.Code )
				if not moveretry:
					return

	def move_to_position(self, measurement):
		mlist = None
		if gom.app.project.is_part_project:
			if measurement.object_family == 'measurement_path':
				mlist = measurement.measurement_path.measurement_series
			else:
				mlist = measurement.measurement_series
		else:
			mlist = measurement.measurement_series
		if not self.define_active_measuring_series( mlist ):
			return False
		if measurement.get('is_current_position'):
			return True

		self.log.info( 'moving to position' )
		try:
			_allowReverseMovement = gom.app.project.virtual_measuring_room[0].is_reverse_move_always_safe
		except:
			_allowReverseMovement = False
		move_cmd = gom.interactive.automation.forward_move_to_position
		if Globals.SETTINGS.Inline:
			move_cmd = gom.script.automation.forward_move_to_position
		moveretry = True
		number_of_retries = 0
		only_init = False
		while moveretry:
			try:
				with Measure.TemporaryWarmupDisable(self.Sensor) as warmup: # no warmuptime for movement
					if only_init:
						if not self.Sensor.initialize():
							return False
						only_init = False
					else:
						if not self.Sensor.check_for_reinitialize():
							return False
				if self.Dialog is not None:
					self.Dialog.processbar_max_steps()
					self.Dialog.processbar_step()
				move_cmd ( measurement = measurement )
				moveretry = False
			except Exception as moveerror:
				self.log.exception( str( moveerror ) )
				errorlog = Verification.ErrorLog()
				state = self.Global_Checks.analyze_error( moveerror, mlist, True, errorlog )
				if Globals.SETTINGS.Inline:
					if state == Verification.VerificationState.RetryWithoutCounting:
						continue
					elif state == Verification.VerificationState.MoveReverseHome and _allowReverseMovement:
						if not gom.app.project.is_part_project:
							measurement = measurement.measurement_series.measurements.filter( 'type=="home_position"' )[0]
						else:
							measurement = measurement.measurement_path.path_positions.filter( 'type=="home_position"' )[0]
						move_cmd = gom.interactive.automation.reverse_move_to_position
						if Globals.SETTINGS.Inline:
							move_cmd = gom.script.automation.reverse_move_to_position
						continue
					elif state in [Verification.VerificationState.ReInitSensor,
											Verification.VerificationState.OnlyInitSensor]:
						number_of_retries += 1
						if number_of_retries > 2:
							InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MOVE_ERROR, errorlog.Code, errorlog.Error)
							return False
						if state == Verification.VerificationState.OnlyInitSensor:
							only_init = True
						continue
					elif state == Verification.VerificationState.Retry:
						continue
					InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MOVE_ERROR, errorlog.Code, errorlog.Error)
					return False
				moveretry = Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_safely_move_failed, errorlog.Error, Globals.SETTINGS.SavePath, True,
														error_code = errorlog.Code )
				if not moveretry:
					return False
		return True

	def is_calibration_necessary( self ):
		'''check if calibration necessary, based on timeout and each cycle settings'''
		calib = False
		if Globals.SETTINGS.CalibrationEachCycle or Globals.SETTINGS.CalibrationForcedTimedelta > 0:
			calib = Globals.SETTINGS.CalibrationEachCycle
			if not calib and Globals.SETTINGS.CalibrationForcedTimedelta > 0:
				lastcaltime = gom.app.sys_calibration_date
				if lastcaltime is None:
					self.log.info( 'Force calibration - no last calibration date/time' )
					calib = True
				else:
					lastcaltime = datetime.datetime( *( time.strptime( lastcaltime )[0:6] ) )
					curtime = datetime.datetime.today()
					maxtimediff = datetime.timedelta( minutes = Globals.SETTINGS.CalibrationForcedTimedelta )
					if abs( curtime - lastcaltime ) > maxtimediff:
						if Globals.SETTINGS.Inline and Globals.SETTINGS.EnableRecommendedSignals:
							Globals.CONTROL_INSTANCE.send_signal( Communicate.SIGNAL_CONTROL_CALIBRATION_RECOMMENDED )
						else:
							self.log.info( 'Force calibration - calibration date/time timeout' )
							calib = True
			elif calib:
				self.log.info( 'Force calibration - calibration each cycle' )
		return calib

	def check_calibration_recommendation_temperature( self, dont_signal = False ):
		if not Globals.SETTINGS.Inline or not Globals.SETTINGS.EnableRecommendedSignals:
			return
		with Measure.TemporaryWarmupDisable(self.Sensor) as warmup:
			if not self.Sensor.check_for_reinitialize():
				return
		current_temperature = self.Thermometer.get_temperature()
		temp_cal = gom.app.sys_calibration_measurement_temperature
		if current_temperature is None or temp_cal is None:
			return
		if abs( temp_cal - current_temperature ) > Globals.SETTINGS.TemperatureWarningLimit:
			if dont_signal:
				return True
			Globals.CONTROL_INSTANCE.send_signal( Communicate.SIGNAL_CONTROL_CALIBRATION_RECOMMENDED )
		return

	def _evaluate( self, start_dialog_input ):
		'''
		Main function for evaluation
		Arguments:
		start_dialog_input - the dictionary containing the keywords specified by the user

		Returns:
		True  - if the successful i.e. all measurements successful and not deviation out of tolerance.
		None  - if no confirm dialog and storing is needed
		False - otherwise
		'''
		if not self.IsVMRlight:
			if not self.measurement_series_home_pos_check():
				Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title,
											Globals.LOCALIZATION.msg_evaluate_failed_home_check_series,
											Globals.SETTINGS.SavePath, False )
				return None

		if Globals.DRC_EXTENSION is not None:
			if not Globals.DRC_EXTENSION.precheck_template():
				return None

		# restrict compatible mseries to a user selection
		fpc_mlist = FixturePositionCheck.FixturePositionCheck.get_mlist( self.Comp_atos_series )
		if not self.select_measurement( no_shows=[fpc_mlist] if fpc_mlist is not None else [] ):
			return None

		self.log.info( 'starting evaluation' )
		gom.script.sys.set_kiosk_status_bar(status=2)

		self.first_measurement_series = True
		self.Dialog.process_msg( step = 1 )
		self.Dialog.processbar_max_steps( 2 )
		self.Dialog.processbar_step( 0 )
		self.Dialog.process_msg_detail( Globals.LOCALIZATION.msg_evaluate_detail_msg_initialize )
		self.Dialog.process_image( Globals.SETTINGS.InitializeImageBinary )
		if self.Statistics is not None:
			self.Statistics.prune()
			try:
				used_template = gom.app.project.get( 'template.relative_path' )
				index = used_template[-1].find( '.project_template' )
				if index > 0:
					used_template[-1] = used_template[-1][:index]
			except:
				used_template=['unknown']
			self.Statistics.log_start( used_template[-1], start_dialog_input.get( 'serial', 'unknown' ) )

		force_calibration = False
		if len( [ml for ml in (self.Comp_photo_series + self.Comp_atos_series)
				if self.is_measurement_series_executable( ml )] ) == 0:
			if self.Calibration.MeasureList is not None:
				force_calibration = True
			else:
				return None

		if Globals.SETTINGS.MultiRobot_Mode and Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
			pass
		else:
			self.display_measurement_positions( False )

		if not force_calibration:
			self.Dialog.processbar_step()
			if not Globals.SETTINGS.AlreadyExecutionPrepared:
				if Globals.SETTINGS.MultiRobot_Mode and Globals.FEATURE_SET.MULTIROBOT_MEASUREMENT:
					pass # skipping set_project_keywords and save_project
				else:
					self.set_project_keywords( start_dialog_input )
					self.save_project()
			Globals.SETTINGS.AlreadyExecutionPrepared = False

		# switch to preview mode to have a defined state
		if gom.app.project.is_part_project:
			gom.script.sys.switch_project_into_preliminary_data_mode( preliminary_data=True )

		# Update measuring temperature for the '*ask*' temperature acquisition methods
		# Updating the calibration temperatures has been moved to the Calibration.calibrate method
		# Reinit sensor if needed, no warmup wait
		with Measure.TemporaryWarmupDisable(self.Sensor) as warmup:
			if not self.Sensor.check_for_reinitialize():
				return None
		if not self.Thermometer.update_temperature():
			return None

		self.update_vdi()

		if Globals.DRC_EXTENSION is not None:
			if not Globals.DRC_EXTENSION.signal_start(self):
				return None

		self.Global_Checks.log_verification_check_states()
		if self.Statistics is not None:
			StatisticalLog.StatisticHelper.mark_time( self.Statistics )

		# OrderByMSetups is to be used when the template contains msetups with different CAD positions
		Globals.SETTINGS.OrderByMSetups = self.detect_msetups_with_different_cad_positions()

		# setup order of measuring setups and mseries
		if Globals.SETTINGS.OrderByMSetups and (Globals.DRC_EXTENSION is None or
				(not Globals.DRC_EXTENSION.PrimarySideActive() and not Globals.DRC_EXTENSION.SecondarySideActive())):
			wcfg_iter = [[wcfg] for wcfg in self.Compatible_wcfgs]
			self.log.info( 'Order measurements: by measuring setups' )
		else:
			wcfg_iter = [self.Compatible_wcfgs]
			self.log.info( 'Order measurements: all tritop first, then all atos' )
		self.Backup_photo_series = self.Comp_photo_series[:]
		self.Backup_atos_series = self.Comp_atos_series[:]
		self.Backup_calib_series = self.Comp_calib_series[:]
		self.Backup_hyperscale_series = self.Comp_hyperscale_series[:]

		will_calibration_be_performed=force_calibration
		if not will_calibration_be_performed:
			if ((len( self.Comp_atos_series ) > 0 and self.is_calibration_necessary())
				or self.getExecutionMode() == ExecutionMode.PerformAdditionalCalibration ):
				will_calibration_be_performed=True

		self.position_information.start_measurement_process(
			self.Comp_photo_series, self.Comp_atos_series, self.Comp_calib_series )

		atos_performed = False
		# clear measuring data before starting MeasuringContext
		if ( not Globals.SETTINGS.OfflineMode and not Globals.FEATURE_SET.ONESHOT_MODE
				and len( self.Comp_photo_series + self.Comp_atos_series ) ):
			self.log.debug( 'clearing measurement data: {}'.format( ','.join( self.Comp_photo_series+self.Comp_atos_series ) ) )
			gom.script.automation.clear_measuring_data ( measurements = [ gom.app.project.measurement_series[ml] for ml in self.Comp_photo_series+self.Comp_atos_series] )

		initial_alignments = [a for a in gom.app.project.alignments
			if not a.alignment_is_original_alignment and a.alignment_is_initial]

		with MeasuringContext(self, self.Comp_photo_series, self.Comp_atos_series, self.Comp_calib_series, self.Comp_hyperscale_series, will_calibration_be_performed) as context:
			if not force_calibration:
				self.check_calibration_recommendation_temperature()
			while True: # retry loop
				start_all_over = False
				for wcfgs in wcfg_iter:
					if start_all_over:
						break
					self.log.info( 'Measuring measuring setup(s) {}'.format( ', '.join( list( wcfgs ) ) ) )

					self.filter_mseries_for_msetups( wcfgs )

					if Globals.DRC_EXTENSION is None or Globals.FEATURE_SET.DRC_UNPAIRED or Globals.FEATURE_SET.DRC_SINGLE_SIDE:
						with FixturePositionCheck.FixturePositionCheck (self.baselog, self) as fpc:
							if fpc.is_fixture_position_check_possible ():
								if not fpc.check_fixture_position ():
									return False

					try:
						self.Comp_atos_series.remove( fpc_mlist )
						self.Backup_atos_series.remove( fpc_mlist )
					except:
						pass

					if not self.IsVMRlight:
						with Measure.TemporaryWarmupDisable(self.Sensor) as warmup: # no warmuptime during tritop
							if not self.Tritop.perform_all_measurements(
								[gom.app.project.measurement_series[ms] for ms in self.Comp_photo_series] ):
								if Globals.DRC_EXTENSION is not None:
									Globals.DRC_EXTENSION.sendMeasureFailure()
								return False

						if len( self.Comp_photo_series ):
							# alignment iteration check / drc cube check
							res = self.optional_photogrammetry_checks()
							if res is None: # retry
								for ms in self.Comp_photo_series:
									gom.script.automation.clear_measuring_data ( measurements = gom.app.project.measurement_series[ms] )
								start_all_over = True
								continue
							if not res:
								# DRC failure is handled in optional_photogrammetry_checks
								return False

						if wcfgs == wcfg_iter[0]:
							# After first tritop round:
							# Identify a point component for subsequent trafo by common refpoints
							if not self.option_identify_point_id_range( wcfgs ):
								return False
						else:
							# After subsequent tritop rounds, try to transform
							if not self.option_trafo_by_point_id_range( wcfgs, wcfg_iter[0] ):
								return False

						# force recalculation of initial alignment(s)
						if len( self.Comp_photo_series ):
							for alignment in initial_alignments:
								try:
									gom.script.sys.recalculate_alignment( alignment=alignment )
								except Globals.EXIT_EXCEPTIONS:
									if Globals.DRC_EXTENSION is not None:
										Globals.DRC_EXTENSION.sendMeasureFailure()
									raise
								except RuntimeError as e:
									self.log.error( 'Failed to recalculate alignment {}'.format( e ) )

					# switch to initial alignment(s) for ATOS
					for alignment in initial_alignments:
						gom.script.manage_alignment.set_alignment_active( cad_alignment=alignment )

					atos_performed = False
					if len( self.Comp_photo_series ) and len( self.Comp_atos_series ) and Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.PrimarySideActive():
						Globals.DRC_EXTENSION.signal_atos_measurement()
						

					if not force_calibration: # handled later
						if ((len( self.Comp_atos_series ) > 0 and self.is_calibration_necessary())
								or self.getExecutionMode() == ExecutionMode.PerformAdditionalCalibration ):
							if self.getExecutionMode() == ExecutionMode.PerformAdditionalCalibration:
								self.setExecutionMode(ExecutionMode.Full)
							if not self.Calibration.calibrate( reason = 'force' ):
								if Globals.DRC_EXTENSION is not None:
									Globals.DRC_EXTENSION.sendMeasureFailure()
								return False

					# Reinit sensor if needed, no warmup wait
					with Measure.TemporaryWarmupDisable(self.Sensor) as warmup:
						if not self.Sensor.check_for_reinitialize():
							if Globals.DRC_EXTENSION is not None:
								Globals.DRC_EXTENSION.sendMeasureFailure()
							return False

					error_log = Verification.ErrorLog()
					if not self.comprehensivePhotogrammetry( error_log ):
						self.log.error( 'Failed to load external photogrammetry' )
						if Globals.DRC_EXTENSION is not None:
							Globals.DRC_EXTENSION.sendMeasureFailure()
						raise Utils.NeedComprehensivePhotogrammetry( 'Failed to load external photogrammetry: {}'.format( error_log.Error ) )

					# HyperScale Calibration
					if self.HyperScale.MeasureList is not None and len( self.Comp_atos_series ) and not self.Tritop.hasPerformedHyperScaleMeasurement():
						if not self.HyperScale.calibrate( reason='force' ):
							if Globals.DRC_EXTENSION is not None:
								Globals.DRC_EXTENSION.sendMeasureFailure()
							return False

					for ms in self.Comp_atos_series:
						if not self.is_measurement_series_executable( ms ):
							continue
						self.Dialog.process_msg( step = self.Dialog.Process_msg_step + 1 )
						try:
							result = self.Atos.perform_measurement( gom.app.project.measurement_series[ms] )
							if result == Verification.DigitizeResult.Failure:
								if Globals.DRC_EXTENSION is not None:
									Globals.DRC_EXTENSION.sendMeasureFailure()
								return False
							atos_performed = True
							if self.Statistics is not None:
								self.Statistics.log_measurement_series()
						except Globals.EXIT_EXCEPTIONS:
							if Globals.DRC_EXTENSION is not None:
								Globals.DRC_EXTENSION.sendMeasureFailure()
							raise
						except Utils.CalibrationError as error:  # calibration failed (e.g. not defined)
							self.log.exception( str( error ) )
							if Globals.DRC_EXTENSION is not None:
								Globals.DRC_EXTENSION.sendMeasureFailure()
							Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title, '\n'.join(error.args), Globals.SETTINGS.SavePath, False )
							return False

						# Transform by common refpoints for workflow assistent templates
						if Globals.SETTINGS.ManualMultiPartMode:
							res = self.transform_parts_by_common_refpoints( ms )
							if not res:
								return False

						res = self.check_for_iteration( ms )
						if res is None: # retry
							start_all_over = True
							break
						if not res:
							return False
					if start_all_over:
						break # restart loop

					if Globals.DRC_EXTENSION is not None and len(self.Comp_atos_series):
						context.moved_to_home=True
						self.moveDevicesToHome()
						res = Globals.DRC_EXTENSION.wait_for_atos(self, context)
						if not res:
							return False

				if force_calibration:
					self.Calibration.calibrate( reason = 'force' )
					if self.Statistics is not None:
						self.Statistics.log_end( force_flush = True )
					Globals.SETTINGS.CurrentTemplate = None  # dont preopen this template next time
					Globals.SETTINGS.CurrentTemplateCfg = None
					if Globals.DRC_EXTENSION is not None:
						Globals.DRC_EXTENSION.wait_for_calibration(self)
					return None
				if not start_all_over:
					break # end loop
		#end of MeasuringContext

		# restore measured mseries from backup
		self.Comp_photo_series = self.Backup_photo_series
		self.Comp_atos_series = self.Backup_atos_series
		self.Comp_calib_series = self.Backup_calib_series
		self.Comp_hyperscale_series = self.Backup_hyperscale_series

		gom.script.sys.set_kiosk_status_bar(status=3)

		if Globals.SETTINGS.InAsyncAbort:
			Globals.SETTINGS.InAsyncAbort = False
			return False

		# slave evaluation stops here
		if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActive():
			Globals.DRC_EXTENSION.delete_slave_project(self)
			return None

		if Globals.FEATURE_SET.ONESHOT_MODE:
			return None # current project evaluate exit

		if not self.transform_by_common_refpoints():
			return False
		if atos_performed:  # after performing every digitize measurement series, its possible to check the alignment residual
			if not (Globals.SETTINGS.AsyncAlignmentResidualCheck and Globals.SETTINGS.Async):
				errorlog = Verification.ErrorLog()
				res = self.Global_Checks.checkalignment_residual( errorlog )
				if res == Verification.DigitizeResult.TransformationMarginReached:
					if Globals.SETTINGS.Inline:
						InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_ATOS_VERIFICATION,errorlog.Code,errorlog.Error)
					elif errorlog.Error:
						Globals.DIALOGS.show_errormsg(
							Globals.LOCALIZATION.msg_general_failure_title,
							errorlog.Error,
							Globals.SETTINGS.SavePath, False, error_code = errorlog.Code )
					return False
				elif res == Verification.DigitizeResult.RefPointMismatch:
					if Globals.SETTINGS.Inline:
						InlineConstants.sendMeasureInstanceError(InlineConstants.PLCErrors.MEAS_MLIST_ALIGNMENT_RESIDUAL, '',
																errorlog.Error)
					else:
						Globals.DIALOGS.show_errormsg(
								Globals.LOCALIZATION.msg_general_failure_title,
								Globals.LOCALIZATION.msg_verification_refpointmismatch + '<br/>' + errorlog.Error,
								Globals.SETTINGS.SavePath, False )

					self.Tritop.setFailedTemplate( True )  # force Tritop for the next time
					if Globals.SETTINGS.PhotogrammetryComprehensive:
						if Globals.SETTINGS.CurrentComprehensiveXML is not None:
							self.Tritop.setFailedTemplate( True, Globals.SETTINGS.CurrentComprehensiveXML )
					return False

		if self.Statistics is not None:
			self.Statistics.log_overall_digitizing()

			# Set a temperature for offline mode for the statistics log
			if Globals.SETTINGS.OfflineMode:
				self.Statistics.log_offline_temperature( self.Thermometer.get_temperature() )

		try:
			if self.Statistics is not None:
				StatisticalLog.StatisticHelper.mark_time( self.Statistics )
			if Globals.SETTINGS.Inline:
				if not self.send_measure_userdata_inline():
					return None
			result = self.analysis.post_measuring( start_dialog_input )
		finally:
			if self.Statistics is not None:
				self.Statistics.Logger.set_row( 'EvaluationTime', StatisticalLog.StatisticHelper.mark_time( self.Statistics ) )
				if not Globals.SETTINGS.Async:
					self.Statistics.log_end( force_flush = False )
				self.Statistics.store_values()

		if self.getExecutionMode() == ExecutionMode.ForceTritop:
			if not result: # keep the project
				return False
			else:
				try:
					projectfile = gom.app.project.get ( 'project_file' )
				except:
					projectfile = None
				if projectfile is not None:
					gom.script.sys.close_project()
					if not projectfile.endswith( '.project_template' ):
						if ( os.path.exists( projectfile ) ):
							os.unlink( projectfile )
				return None # no evaluation
		return result

	def comprehensivePhotogrammetry( self, error_log ):
		if not Globals.SETTINGS.PhotogrammetryComprehensive:
			return True

		# TODO part-based case like in MeasureTritop.import_photogrammetry?

		independend_series = []
		for m in sorted( Utils.real_measurement_series( filter='type=="atos_measurement_series"' ) ):
			if m.get( 'reference_points_master_series' ) is None:
				independend_series.append( m )
		if not len( independend_series ):
			return True  # no independent series found
		if not self.Tritop.can_import_refxml( error_log ):
			return False

		external_refxml = self.Tritop.find_external_refxml( error_log )
		if external_refxml is None:
			return False

		self.log.info( 'importing reference points {}'.format( external_refxml ) )
		if self.Dialog is not None:
			self.Dialog.processbar_max_steps()
			self.Dialog.processbar_step()
		# import photogrammetry
		for m in independend_series:
			try:
				gom.script.atos.use_external_reference_points (
					file = external_refxml,
					gsi_file_unit = 'mm',
					load_ascii_as_gsi = False,
					measurement_series = m )
			except Exception as e:
				self.log.error( 'failed to import reference points for ms {} : {}'.format( m, e ) )
				return False
			else:  # only import the external photogrammetry into the first measurement series
				break

		return True

	def option_identify_point_id_range( self, wcfgs ):
		Globals.SETTINGS.PointsUsedForTrafo = None
		if not Globals.SETTINGS.OrderByMSetups:
			return True

		# Recalc in original alignment and collect points for later trafo by common refpoints
		# This is necessary so points are not transformed in any way and thus can be identified by tritop
		#   in other msetups.
		# Original alignment may be used as initial alignment,
		#   in this case initial alignment must be used.
		# Points not found in tritop have no coordinate, so filtering is needed.
		try:
			align = self.get_original_or_initial_alignment()
			gom.script.manage_alignment.set_alignment_active( cad_alignment=align )
			(tritop_series_wcfg0, _, _, _) = self.get_mseries_for_msetups(
					wcfgs, self.Backup_photo_series, [], [], [] )
			tritop_master = None
			for tritopname in tritop_series_wcfg0:
				tritop = gom.app.project.measurement_series[tritopname]
				if tritop.reference_points_master_series is None:
					tritop_master = tritop
					break
			gom.script.sys.recalculate_elements( elements=[tritop_master] )
			allpts = tritop_master.results['points']
			Globals.SETTINGS.PointsUsedForTrafo = list( [
				allpts.get( 'coordinate[{}]'.format( i ) )
				for i in range( allpts.num_points )
				if isinstance( allpts.get( 'coordinate[{}]'.format( i ) ), gom.Vec3d )
					and allpts.get( 'point_type[{}]'.format( i ) ) == 'coded'
					and allpts.get( 'point_id[{}]'.format( i ) ) in Globals.SETTINGS.TrafoCodedPointIDs] )
			self.log.debug( 'Collected {} coded points for trafo by common refpoints'.format (
				len ( Globals.SETTINGS.PointsUsedForTrafo ) ) )
			if len ( Globals.SETTINGS.PointsUsedForTrafo ) < 3:
				raise ValueError( "Less than 3 points found for transform by common refpoints" )
		except Exception as e:
			self.log.exception( str( e ) )
			return Globals.DIALOGS.show_errormsg(
				Globals.LOCALIZATION.msg_general_failure_title,
				Globals.LOCALIZATION.msg_no_points_for_trafo,
				Globals.SETTINGS.SavePath, False )

		return True

	def option_trafo_by_point_id_range( self, wcfgs, master_wcfgs ):
		if not Globals.SETTINGS.OrderByMSetups:
			return True

		try:
			(ref_tritops, _, _, _) = self.get_mseries_for_msetups(
				master_wcfgs, self.Backup_photo_series, [], [], [] )
			ref_tritop_master = None
			for tritopname in ref_tritops:
				tritop = gom.app.project.measurement_series[tritopname]
				if tritop.reference_points_master_series is None:
					ref_tritop_master = tritop
					break
			(src_tritops, _, _, _) = self.get_mseries_for_msetups(
				wcfgs, self.Backup_photo_series, [], [], [] )
			src_tritop_master = None
			for tritopname in src_tritops:
				tritop = gom.app.project.measurement_series[tritopname]
				if tritop.reference_points_master_series is None:
					src_tritop_master = tritop
					break

			self.log.debug( 'trafo by common refpoints from {} into {}'.format(
				src_tritop_master.name, ref_tritop_master.name ) )
			gom.script.atos.transform_measurement_series (
				reference_measurement_series=ref_tritop_master,
				source_measurement_series=src_tritop_master,
				transformation_method='common_reference_points',
				transformation_points=Globals.SETTINGS.PointsUsedForTrafo )
		except Exception as e:
			self.log.exception( str( e ) )
			return Globals.DIALOGS.show_errormsg(
				Globals.LOCALIZATION.msg_general_failure_title,
				Globals.LOCALIZATION.msg_common_refpoint_trafo_error.format( e ),
				Globals.SETTINGS.SavePath, False )

		return True

	def transform_parts_by_common_refpoints( self, series ):
		if len( list( gom.ElementSelection( {'category': ['key', 'elements',
				'explorer_category', 'inspection', 'object_family', 'vdi']} ) ) ):
			return True

		try:
			i = self.Comp_atos_series.index( series )
		except:
			self.log.debug( 'Indexing {} failed.'.format( series ) )
			return False

		if i > 0:
			try:
				into_series = self.Comp_atos_series[i - 1]
				series = gom.app.project.measurement_series[series]
				into_series = gom.app.project.measurement_series[into_series]
				sources = series.linked_measurement_series_in_parts
				targets = into_series.linked_measurement_series_in_parts
			except:
				self.log.debug( 'Getting mseries "{}" for transformation failed.'.format( series ) )
				return False

			for (source, target) in zip( sources, targets ):
				self.log.info( 'Transforming "{}" into "{}"'.format( source, target ) )
				with warnings.catch_warnings( record = True ) as w:
					warnings.simplefilter( "always" )  # grep all warnings
					try:
						gom.script.atos.transform_measurement_series(
							reference_measurement_series=target,
							source_measurement_series=source,
							transformation_method='common_reference_points',
							find_transformation_points_automatically=True )
					except RuntimeError as e:
						self.log.error( e )
						Globals.DIALOGS.show_errormsg(
							Globals.LOCALIZATION.msg_general_failure_title,
							Globals.LOCALIZATION.msg_common_refpoint_trafo_error + '<br/>{}'.format(
								'<br/>'.join(e.args) ),
							Globals.SETTINGS.SavePath, False )
						return False
					if len( w ):
						Globals.DIALOGS.show_errormsg(
							Globals.LOCALIZATION.msg_general_failure_title,
							Globals.LOCALIZATION.msg_common_refpoint_trafo_error.format(
								'<br/>'.join( ( str( _.message ) for _ in w ) ) ),
							Globals.SETTINGS.SavePath, False )
						return False

		return True

	def transform_by_common_refpoints( self ):
		'''
		transforms all independent digitize measurements into the first
		the reference points from the base-plate have to be already imported into the template
		thus all collected points are from the part
		returns True on success False otherwise
		'''
		if len( list( gom.ElementSelection ( {'category': ['key', 'elements', 'explorer_category', 'inspection', 'object_family', 'vdi']} ) ) ):
			return True
		if Globals.SETTINGS.ManualMultiPartMode:
			return True

		dependend_series = []
		independend_series = []
		tritop_dependend_series = []
		for ms in sorted( Utils.real_measurement_series( filter='type=="atos_measurement_series"' ) ):
			if not self.is_measurement_series_executable(ms):
				continue
			if ms.get( 'reference_points_master_series' ) is not None:
				if ms.get( 'reference_points_master_series' ).get( 'type' ) == 'atos_measurement_series':
					dependend_series.append( ms )
				else:
					tritop_dependend_series.append( ms )
			else:
				independend_series.append( ms )
		tritops = len(Utils.real_measurement_series( filter='type=="photogrammetry_measurement_series"' ) )
		if len( independend_series ) == 1 and not tritops:
			return True # only one independend series and no tritop
		if len( dependend_series ) + len( independend_series ) + len( tritop_dependend_series ) < 2:
			return True  # only one series
		if not len( independend_series ):
			return True  # no independent series
		if len( [ms for ms in independend_series if ms.get( 'reference_point_frame_name' ) is not None] ):
			return True  # reference point frame
		master_series = None
		if len( tritop_dependend_series ):
			master_series = tritop_dependend_series[0]
		else:
			master_series = independend_series.pop( 0 )

		# use external
		atos_points = self.get_atos_refpoints( master_series, scale_bar_points=False )
		if len( atos_points ) < 3:
			Globals.DIALOGS.show_errormsg(
				Globals.LOCALIZATION.msg_general_failure_title,
				Globals.LOCALIZATION.msg_common_refpoint_trafo_less_points,
				Globals.SETTINGS.SavePath, False )
			return False
		self.log.info( 'transforming by common refpoints' )
		self.log.debug( 'used points: {}'.format( len( atos_points ) ) )

		for series in independend_series:  # transform every independend ms into the first
			self.log.info( 'transforming "{}" into "{}"'.format( series, master_series ) )
			with warnings.catch_warnings( record = True ) as w:
				warnings.simplefilter( "always" )  # grep all warnings
				try:
					gom.script.atos.transform_measurement_series (
						reference_measurement_series = master_series,
						source_measurement_series = series,
						transformation_method='common_reference_points',
						transformation_points = atos_points )
				except RuntimeError as e:
					self.log.error( e )
					Globals.DIALOGS.show_errormsg(
							Globals.LOCALIZATION.msg_general_failure_title,
							Globals.LOCALIZATION.msg_common_refpoint_trafo_error + '<br/>{}'.format( '<br/>'.join(e.args) ),
							Globals.SETTINGS.SavePath, False )
					return False
				if len( w ):
					Globals.DIALOGS.show_errormsg(
							Globals.LOCALIZATION.msg_general_failure_title,
							Globals.LOCALIZATION.msg_common_refpoint_trafo_error.format( '<br/>'.join( ( str( _.message ) for _ in w ) ) ),
							Globals.SETTINGS.SavePath, False )
					return False
		return True

	def get_atos_refpoints( self, series, scale_bar_points=True ):
		'''
		grep all atos reference points of given measurement series
		'''
		if series.get( 'reference_points_master_series' ) is not None:
			refpoints = series.get( 'reference_points_master_series' ).results['points']
		else:
			refpoints = series.results['points']
		atos_points = [refpoints.get( 'coordinate[{}]'.format( i ) )
			for i in range( refpoints.get( 'num_points' ) )
			if 'atos' in str( refpoints.get( 'point_type[{}]'.format( i ) ) )
				and ( scale_bar_points or 'scale_bar' not in str( refpoints.get( 'point_type[{}]'.format( i ) ) ) )]
		return atos_points

	def update_vdi( self ):
		'''
		if a vdi element is inside the template, update the parameters
		'''
		vdi_elements = list( gom.ElementSelection ( {'category': ['key', 'elements', 'explorer_category', 'inspection', 'object_family', 'vdi']} ) )
		if not len( vdi_elements ):
			return
		if self.IsVMRlight:
			return

		name, id = self.Sensor.get_sensor_information()
		try:
			inspector = gom.app.project.get( 'user_inspector' )
		except:
			inspector = 'Unknown'

		temperature = self.Thermometer.get_temperature()
		if temperature is None:
			self.log.error( 'failed to get temperature' )
			return
		today = time.localtime()

		try:
			gom.script.vdi.edit_test_vdi2634_part3( element = vdi_elements[0],
												inspector = inspector,
												system = '{} {}'.format( name, id ),
												measuring_temperature = temperature,
												date = gom.Date ( today.tm_mday, today.tm_mon, today.tm_year ) )
		except Exception as e:
			self.log.error( 'failed to edit vdi element {}'.format( e ) )

	def send_measure_userdata_inline(self):
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MEASURE_USER_DATA, '' ) )
		return True


class EvaluationAnalysis( Utils.GenericLogClass ):
	'''
	This class contains functionality which is used to evaluate the measured data.
	-update reports
	-polygonize
	-automatic result checks
	'''
	parent = None
	scan_parts = []

	def __init__( self, logger, parent ):
		'''
		Initialize function to init logging
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		# empty part name container, filled in polygonize
		EvaluationAnalysis.scan_parts = []

	def post_measuring( self, start_dialog_input ):
		'''
		This function contains the post measurement parts of the evaluation procedure. It is only called if the
		script runs not in async mode, because otherwise the function AsyncClient.Client.evaluate(..) takes care of the
		evaluation.
		Arguments:
		start_dialog_input - dictionary containing the user input from the start dialog
		'''
		# reset parts container
		EvaluationAnalysis.scan_parts = []
		# no polygonization and recalc on drc slave side
		if Globals.DRC_EXTENSION is not None and Globals.DRC_EXTENSION.SecondarySideActive():
			return True
		if not (Globals.DRC_EXTENSION is not None and Globals.FEATURE_SET.DRC_SECONDARY_INST):
			Communicate.IOExtension.io_extension_measurement_done(self.baselog)

		# in the case of a comprehensive photogrammetry project only recalc and dont try to polygonize or update reports
		if self.parent.isComprehensivePhotogrammetryProject:
			gom.script.sys.recalculate_project (with_reports=False)
			return True

		if Globals.SETTINGS.Async:
			return True

		self.perform_evaluation_steps()
		return True

	def perform_evaluation_steps( self ):
		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_max_steps()
			self.parent.Dialog.processbar_step()

		self.recalculate_project_if_needed()

		if not len( list( gom.ElementSelection ( {'category': ['key', 'elements', 'explorer_category', 'inspection', 'object_family', 'vdi']} ) ) ):
			self.polygonize()

		self.postpoly_recalc_if_needed()

		if self.parent.Dialog is not None:
			self.parent.Dialog.process_msg( step = self.parent.Dialog.Process_msg_step + 1 )
			self.parent.Dialog.process_msg_detail( Globals.LOCALIZATION.msg_evaluate_detail_msg_recalc )
			self.parent.Dialog.process_image( Globals.SETTINGS.ReportImageBinary )
			self.parent.Dialog.processbar_max_steps( 2 )
			self.parent.Dialog.processbar_step( 0 )

		# recalc only if evaluation is not delegated to evaluation templates
		if Globals.SETTINGS.PartEvaluationMap == {}:
			gom.script.sys.recalculate_project()
			EvaluationAnalysis.switch_all_parts_to_result_mesh()
		gom.script.sys.save_project()

		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_step()

	def check_manual_multipart_mseries(self):
		try:
			for ms in gom.app.project.measurement_series:
				if ms.part is not None:
					return True
		except:
			pass
		return False

	def mmp_target_part( self ):
		parts = [p.name for p in gom.app.project.parts if not p.is_element_in_clipboard]
		if len( parts ) == 1:
			return parts[0]
		return 'Part'

	@staticmethod
	def multipart_build_evaluation_map():
		'''
		Example Map:
		Globals.SETTINGS.PartEvaluationMap = {
			'Part 1': 'mmpeval7.project_template', 'Part 2': 'mmpeval7.project_template'}
		'''
		Globals.SETTINGS.PartEvaluationMap = {}

		# read rules
		filename = os.path.join( gom.app.public_directory if gom.app.public_directory is not None else '',
			'KioskInterface_MeasurementEvaluationAssignment.csv' )
		if not os.path.exists( filename ):
			Globals.LOGGER.warning( 'No evaluation template pattern file found ({})'.format( filename ) )
			return

		rules = []
		try:
			with open( filename, 'r', encoding='utf-8' ) as f:
				lines = f.readlines()
				for line in lines:
					if line.startswith( '#' ):
						continue
					if line.strip() == '':
						continue
					elems = line.split( ';' )
					elems = [elem.strip().strip( '"' ) for elem in elems]
					if len( elems ) == 4:
						rules.append( elems )
					else:
						Globals.LOGGER.error(
							'Evaluation template pattern "{}" contains error'.format( elems ) )
		except Exception as e:
			Globals.LOGGER.exception(
				'Failed to read evaluation template patterns: {}'.format( e ) )
			return

		if len( rules ) == 0:
			Globals.LOGGER.error( 'No evaluation template patterns found' )
			return

		# matching templates / parts and building the evaluation map
		eval_map = {}
		# copy of the parts to be measured
		parts_needed = [part.name for part in Utils.multi_part_evaluation_parts()]
		try:
			current_template = gom.app.project.template.relative_path
			current_template = '\x07'.join( current_template )

			for rule in rules:
				res = re.search( rule[0], current_template )
				if res is not None:
					rem_parts = []
					for part in parts_needed:
						res = re.search( rule[1], part )
						if res is not None:
							eval_map[part] = rule[2]
							rem_parts.append( part )

					for rem_part in rem_parts:
						parts_needed.remove( rem_part )
					if len( parts_needed ) == 0:
						break
		except Exception as e:
			Globals.LOGGER.exception( 'Fatal error in evaluation template pattern matching {}'.format( e ) )
			return

		if eval_map == {}:
			Globals.LOGGER.error(
				'No evaluation template pattern or part matched for template {}'.format( current_template ) )
			return

		if parts_needed != []:
			Globals.LOGGER.warning(
				'No evaluation template pattern found for parts {} in template {}'.format(
					parts_needed, current_template ) )

		Globals.LOGGER.info(
			'Evaluation templates for template {}: {}'.format( current_template, eval_map ) )
		Globals.SETTINGS.PartEvaluationMap = eval_map

	# Compatibility: old name from manual motion-replay mode
	manual_multipart_build_evaluation_map = multipart_build_evaluation_map


	def recalculate_project_if_needed( self ):
		# easy cases first vdi or no atos ms: always recalculate complete project
		atos_series = Utils.real_measurement_series( filter='type=="atos_measurement_series"' )
		measured_atos = [ms for ms in atos_series if len( ms.measurements.filter( 'computation_basis=="real_data"' ) )]
		if ( len( list( gom.ElementSelection ( {'category': ['key', 'elements', 'explorer_category', 'inspection', 'object_family', 'vdi']} ) ) )
			or not len( measured_atos ) ):
			self.log.info( 'recalculating project' )
			gom.script.sys.recalculate_project (with_reports=False)
			return

		# recalculate only if any atos measurement series with one cut out mode exists
		# and the initial alignment is uncomputed
		ms_with_cut = [ms for ms in measured_atos if ms.cut_out_points_below_plane or
													ms.cut_out_points_outside_cad or
													ms.cut_out_shadow_points_of_fixture]
		initial_alignments = gom.app.project.alignments.filter( 'alignment_is_initial==True' )
		if len( ms_with_cut ) and len( initial_alignments ):
			self.log.info( 'Recalculating initial alignment(s)' )
			for alignment in initial_alignments:
				if alignment.computation_status != 'computed':
					gom.script.sys.recalculate_alignment( alignment=alignment )
			gom.script.sys.recalculate_elements( elements=Utils.real_measurement_series() )

	def polygonize_part( self, part ):
		try:
			if not part.actual.is_root_mesh_variant:
				acts = gom.app.project.actual_elements.filter(
					'object_family == "actual_part" and part.name == "{}" and is_root_mesh_variant'.format(
					part.name ) )
				gom.script.mesh.define_as_active_actual_mesh( switch_to=acts[0] )
				self.log.info( 'Switched to mesh {} for polygonization'.format( acts[0].name ) )

			if part.actual.alignment_at_calculation != None:
				if part.actual.alignment_at_calculation.computation_status != 'computed':
					self.log.debug( 'Part {} recalc {}'.format( part.name, part.actual.alignment_at_calculation.name ) )
					gom.script.sys.recalculate_elements( elements=[part.actual.alignment_at_calculation] )
				gom.script.manage_alignment.set_alignment_active(
					cad_alignment=part.actual.alignment_at_calculation )

			gom.script.sys.restore_point_selection( elements=[part.actual] )

			if self.parent.Dialog is not None:
				self.parent.Dialog.processbar_step()

			gom.script.sys.edit_creation_parameters( element=part.actual )

			if self.parent.Dialog is not None:
				self.parent.Dialog.processbar_step()

			if part.actual.num_points == 0 and part.actual.num_triangles == 0:
				return None
			else:
				return part.actual
		except Exception as error:
			self.log.exception( 'Polygonization failed for part "{}": {}'.format( part.name, str( error ) ) )

		return None

	def polygonize( self ):
		'''
		Polygonize measurement.

		All parts which have been scanned are polygonized, if PerformPolygonization setting is active.

		For the old non-parts workflow the parameters for gom.script.atos.polygonize_and_recalculate
		from the settings file are used.

		Returns a list of meshes or the empty list if an error occurs.
		'''
		parts = Utils.multi_part_evaluation_parts( alignment_part=False )
		align_parts = Utils.multi_part_evaluation_parts( alignment_part=True )
		EvaluationAnalysis.scan_parts = [p.name for p in align_parts + parts]

		if not Globals.SETTINGS.PerformPolygonization:
			return None

		self.log.info( 'polygonize' )

		if self.parent.Dialog is not None:
			self.parent.Dialog.process_msg( step = self.parent.Dialog.Process_msg_step + 1 )
			self.parent.Dialog.process_msg_detail( Globals.LOCALIZATION.msg_evaluate_detail_msg_polygonize )
			self.parent.Dialog.processbar_step( 0 )
			self.parent.Dialog.processbar_max_steps( 3 )
			if gom.app.project.is_part_project:
				self.parent.Dialog.processbar_max_steps( 2 + 2 * len ( align_parts + parts ) )

		gom.script.cad.show_element ( elements=Utils.real_measurement_series() )

		verify = Verification.MeasureChecks(self.baselog, None) # temp creation for async
		polygonize, ignore = verify.collectMeasurementsForPolygonization()
		if gom.app.project.is_part_project:
			gom.script.sys.exclude_measurement_from_computation (
				elements=ignore,
				exclude=True)
		else:
			try:
				gom.script.cad.show_element ( elements = polygonize )
			except:
				pass
			try:
				gom.script.cad.hide_element ( elements = ignore )
			except:
				pass

		if self.parent.Dialog is not None:
			self.parent.Dialog.processbar_step()

		meshes = []
		if gom.app.project.is_part_project:
			if len( align_parts + parts ) > 1:
				self.log.info( 'Multipart polygonization order: {}'.format(
					', '.join( p.name for p in align_parts + parts ) ) )
			for p in align_parts + parts:
				mesh = self.polygonize_part( p )
				if mesh is not None:
					meshes.append( mesh )
				else:
					EvaluationAnalysis.scan_parts.remove( p.name )
		else:
			gom.script.selection3d.select_all_points_of_element( elements=Utils.real_measurement_series() )

			if self.parent.Dialog is not None:
				self.parent.Dialog.processbar_step()

			try:
				mesh = gom.script.atos.polygonize_and_recalculate(
					fill_reference_points = Globals.SETTINGS.PolygonizeFillReferencePoints,
					polygonization_process = Globals.SETTINGS.PolygonizeProcess,
					polygonize_large_data_volumes = Globals.SETTINGS.PolygonizeLargeDataVolumes )
				meshes = [mesh]
			except Exception as error:
				self.log.exception( str( error ) )

		return meshes

	def postpoly_recalc_if_needed( self ):
		# if evaluation is delegated to evaluation templates,
		# at least all actuals directly depending on mmt data need recalculation
		if Globals.SETTINGS.PartEvaluationMap != {}:
			depends_on_mmt_data = []
			depends_on_mmt_data += list( gom.ElementSelection(
				{'category': ['key', 'elements', 'explorer_category', 'actual',
									'object_family', 'gray_value_feature']} ) )
			depends_on_mmt_data += list( gom.ElementSelection(
				{'category': ['key', 'elements', 'explorer_category', 'actual',
									'object_family', 'adapter']} ) )
			depends_on_mmt_data += list( gom.ElementSelection(
				{'category': ['key', 'elements', 'explorer_category', 'actual',
									'object_family', 'hole_feature']} ) )
			depends_on_mmt_data += list( gom.ElementSelection(
				{'category': ['key', 'elements', 'explorer_category', 'actual',
									'object_family', 'probe_primitive']} ) )

			if len( depends_on_mmt_data ) > 0:
				gom.script.sys.recalculate_elements( elements=depends_on_mmt_data )


	@staticmethod
	def _create_unique_element_list( element_list ):
		_uniquelist = set()
		_fastadd = _uniquelist.add
		uniqueinsert = lambda list: [x for x in list
										if str( x ) not in _uniquelist and not _fastadd( str( x ) )]
		return sorted( uniqueinsert( element_list ) )

	def _parse_xml( self, file, result ):
		'''
		private method for parsing the GOM XML
		'''
		class XML_ELEM:
			'''
			interface class for xml elements
			'''
			def __init__( self, elem ):
				raise NotImplemented
			def start_parse( self, elem ):
				raise NotImplemented
			def end_parse( self, elem ):
				raise NotImplemented
		class Tolerance( XML_ELEM ):
			'''
			parser for tolerance xml element
			'''
			def __init__( self, elem ):
				'''
				store the element tag, for end recognition
				'''
				self.name = elem.attrib.get( 'name', '' )
				self.id = elem.attrib.get( 'sort_id', '' )
				self.type = elem.tag
				self.upper = None
				self.lower = None
				self.upper_warning = None
				self.lower_warning = None
				self.deviation = None
				self.finished = False
				self.keywords=[]
				self._in_keywords=False
			def __repr__( self ):
				'''
				overload for better visualisation
				'''
				inside_tol = ( True if self.deviation is not None and
									( self.upper is not None and self.upper >= self.deviation )
								and ( self.lower is not None and self.lower <= self.deviation ) else False )
				return '{}: {}/{} w{}/{}= {}({})'.format( self.type, self.upper, self.lower, self.upper_warning, self.lower_warning, self.deviation, 'T' if inside_tol else 'F' )
			def start_parse( self, elem ):
				'''
				parse sub elements (tolerance, deviation)
				'''
				if elem.tag == 'tolerance':
					try:
						self.lower = float( elem.attrib.get( 'lower_limit', None ) )
					except ValueError as e:
						self.lower = None
					try:
						self.upper = float( elem.attrib.get( 'upper_limit', None ) )
					except ValueError as e:
						self.upper = None
				elif elem.tag == 'tolerance_warning':
					try:
						self.lower_warning = float( elem.attrib.get( 'lower_limit', None ) )
					except ValueError as e:
						self.lower_warning = None
					try:
						self.upper_warning = float( elem.attrib.get( 'upper_limit', None ) )
					except ValueError as e:
						self.upper_warning = None
				elif elem.tag == 'deviation':
					try:
						self.deviation = float( elem.attrib.get( 'value', None ) )
					except ValueError as e:
						self.deviation = None
				elif elem.tag == 'keywords':
					self._in_keywords=True
				elif self._in_keywords:
					if elem.tag == 'keyword':
						self.keywords.append({'desc': elem.attrib.get( 'desc', None ), 'name' : elem.attrib.get( 'name', None ), 'value': elem.text})
			def end_parse( self, elem ):
				'''
				mark finished
				'''
				if elem.tag == self.type:
					self.finished = True
				elif elem.tag == 'keywords':
					self._in_keywords=False

		class Result( XML_ELEM ):
			'''
			parser for result element
			'''
			def __init__( self, _elem ):
				'''
				initialize tolerances
				'''
				self.tolerances = []
				self.finished = False
			def __repr__( self ):
				'''
				overload for better visualisation
				'''
				return '{}'.format( self.tolerances )
			def start_parse( self, elem ):
				'''
				route parsing to active tolerance class, or generate a new
				'''
				if len( self.tolerances ) and not self.tolerances[-1].finished:  # active tolerance
					self.tolerances[-1].start_parse( elem )
				else:
					self.tolerances.append( Tolerance( elem ) )
			def end_parse( self, elem ):
				'''
				route parsing to active tolerance class, or finish self
				'''
				if len( self.tolerances ) and not self.tolerances[-1].finished:  # active tolerance
					self.tolerances[-1].end_parse( elem )
					if self.tolerances[-1].finished:  # now finished
						if self.tolerances[-1].lower is None and self.tolerances[-1].upper is None:
							self.tolerances.pop()  # only keep tolerances with limits
				elif elem.tag == 'result':  # end of self
					self.finished = True

		class Geometry( XML_ELEM ):
			'''
			parser for geometry element
			'''
			def __init__( self, _elem ):
				'''
				initialize geometry
				'''
				self.finished = False
			def __repr__( self ):
				'''
				overload for better visualisation
				'''
				return '{}'.format( 'Geometry' )
			def start_parse( self, elem ):
				'''
				ignore all elements
				'''
				pass
			def end_parse( self, elem ):
				'''
				finish self
				'''
				if elem.tag == 'geometry':  # end of self
					self.finished = True

		class Element( XML_ELEM ):
			'''
			parser class for nominal xml element
			'''
			def __init__( self, elem ):
				'''
				mark elem tag and store name
				'''
				self.type = elem.tag
				self.name = elem.attrib.get( 'name', '' )
				self.id = elem.attrib.get( 'id', '' )
				self.results = None
				self.geometry = None
				self.computed = False
				self.finished = False
			def __repr__( self ):
				'''
				overload for better visualisation
				'''
				return '{}: "{}" ({}): {}'.format( self.type, self.name, self.computed, self.results )
			def start_parse( self, elem ):
				'''
				only listen to result tag
				route parsing to active result class, or create a new one
				'''
				if self.results is not None and not self.results.finished:  # result class is active
					self.results.start_parse( elem )
				elif elem.tag == 'result':  # create a new one
					self.results = Result( elem )
				elif self.geometry is not None and not self.geometry.finished:  # geometry class is active
					self.geometry.start_parse( elem )
				elif elem.tag == 'geometry':  # create a new one
					self.geometry = Geometry( elem )
			def end_parse( self, elem ):
				'''
				route parsing to active result class, store computiation state, or finish self
				'''
				if self.results is not None and not self.results.finished:  # result class is active
					self.results.end_parse( elem )
				elif elem.tag == 'state':
					self.computed = ( elem.text.lower() == 'ok' )  # store computiation state
				elif self.geometry is not None and not self.geometry.finished:  # geometry class is active
					self.geometry.end_parse( elem )
				elif elem.tag == self.type:  # end of self
					self.finished = True

		class Alignment( XML_ELEM ):
			'''
			parser class for alignments
			'''
			def __init__( self, elem ):
				'''
				store elem name
				'''
				self.name = elem.attrib.get( 'alignment', 'NoName' )
				self.elements = []
				self.finished = False
			def start_parse( self, elem ):
				'''
				every child is an element, route parsing to active or create a new one
				'''
				if len( self.elements ) and not self.elements[-1].finished:  # element class is active
					self.elements[-1].start_parse( elem )
				else:  # create a new one
					self.elements.append( Element( elem ) )
			def end_parse( self, elem ):
				'''
				route parsing to active element, or if non active check end tag of self
				'''
				if len( self.elements ) and not self.elements[-1].finished:  # element class is active
					self.elements[-1].end_parse( elem )
				elif elem.tag == 'nominal':  # no element active, check for end tag
					self.finished = True

		# start of method
		alignments = []  # fill list of alignments
		try:
			with codecs.open ( file, 'r', encoding = "utf-8" ) as f:
				for event, elem in xml.etree.ElementTree.iterparse( f, events = ( "start", "end" ) ):
					if not len( alignments ) or alignments[-1].finished:  # no alignment is active
						if event == 'start' and elem.tag == 'nominal':  # new nominal tag
							alignments.append( Alignment( elem ) )  # create a new alignment
					else:  # active alignment, route based on event type
						if event == 'start':
							alignments[-1].start_parse( elem )
						else:
							alignments[-1].end_parse( elem )
							elem.clear()  # clear memory
		except Exception as e:
			self.log.error( 'Failed to parse XML {}'.format( e ) )

		return self._analyze_export_xml( result, alignments )

	def _calc_element_result_xml(self, result, ele ):
		'''
		possible result keys are: "uncomputed", "out_of_tol", "out_of_tol_warning", "out_of_tol_qstop"
		'''
		for check in ele.results.tolerances:
			if check.deviation is None:
				result['uncomputed'].append( '{}.{}'.format( ele.name, check.type ) )
			elif check.lower is not None and check.lower > check.deviation:
				result['out_of_tol'].append( ele.name )
			elif check.upper is not None and check.upper < check.deviation:
				result['out_of_tol'].append( ele.name )
			elif check.upper_warning is not None and check.upper_warning < check.deviation:
				result['out_of_tol_warning'].append( ele.name )
			elif check.lower_warning is not None and check.lower_warning > check.deviation:
				result['out_of_tol_warning'].append( ele.name )

	def _analyze_export_xml( self, result, xml_structure ):
		# fill result dictionary
		for alignment in xml_structure:
			result['all'] += [ele.name for ele in alignment.elements]
			for ele in alignment.elements:
				try:
					if not ele.computed:
						result['uncomputed'].append( ele.name )
					else:
						self._calc_element_result_xml( result, ele )
				except Exception as e:
					self.log.error( 'Error in Element {}: {}'.format( ele, e ) )
		return result


	def perform_automatic_result_check( self, reports=None ):
		'''
		If the measurement script is in automatic/async mode, this function is meant for patching an automatic result checks into it.
		It is called after the measurement is complete and the reports are created.
		The default behaviour is to analyze the report pages, only elements visible in report pages will be checked:
		* have a tolerance
		* computed
		* inside tolerance
		'''
		if reports is None:
			reports = gom.app.project.reports
		result = dict()
		result['all'] = list()
		result['uncomputed'] = list()
		result['out_of_tol'] = list()
		result['out_of_tol_warning'] = list()
		result['out_of_tol_qstop'] = list()
		result['result'] = False
		result['additional'] = ''
		if Globals.SETTINGS.AutomaticResultEvaluation:
			if len( reports ) > 0:
				fd, file = tempfile.mkstemp( suffix = '.xml', prefix = 'kiosk_' )
				try:
					os.close( fd )
				except:
					pass
				with warnings.catch_warnings( record = True ) as w :
					warnings.simplefilter( "always" )
					try:
						gom.script.sys.export_gom_xml_by_report_pages (
							file = file,
							format = gom.File ( 'giefv20_kioskevaluation.xsl' ),
							pages = reports )
					except RuntimeError as e:
						if e.args[0] == 'MCADImport-0065':  # uncomputed alignments
							result['additional'] = '{}'.format( e.args[1] )
						else:  # different errors result in a direct failure
							result['additional'] = '{}'.format( e.args[1] )
							return result
					if len( w ):  # different alignments is not an error, but log the state
						self.log.warning( 'Some elements were exported in different alignments: {}'.format( '\n'.join( ( str( _.message ) for _ in w ) ) ) )

				try:
					result = self._parse_xml( file, result )
				except Exception as e:
					self.log.exception( 'Failed to parse xml: {}'.format( e ) )
				try:
					os.unlink( file )
				except:
					pass

				result['all'] = self._create_unique_element_list( result['all'] )
				result['uncomputed'] = self._create_unique_element_list( result['uncomputed'] )
				result['out_of_tol'] = self._create_unique_element_list( result['out_of_tol'] )
				result['out_of_tol_qstop'] = self._create_unique_element_list( result['out_of_tol_qstop'] )
				result['out_of_tol_warning'] = self._create_unique_element_list( result['out_of_tol_warning'] )
				result['result'] = not( len( result['uncomputed'] ) > 0 or len( result['out_of_tol'] ) > 0 ) and not len( result['additional'] )
				return result
			else:
				result['additional'] = 'NoReports'
				result['result'] = True
				return result

		else:
			result['additional'] = 'NoCheck'
			result['result'] = True
			return result

	def check_results_all_inspections( self ):
		'''
		This function checks the inspection results automatically. It checks the tolerance of all inspection elements which have tolerances.
		Elements which are not getting checked individual: Curves inspections and GD&T two point distances
		Returns:
		Dictionary result with
		result['all'] = all elements which have tolerances
		result['uncomputed'] = those elements which have tolerances and are not computed
		result['out_of_tol'] = the elements which are out of tolerance
		result['result'] = Boolean False if there exists an element which is uncomputed of out of tolerance, otherwise True
		result['additional'] = string with additional comments
		'''
		result = dict()
		try:
			result['all'] = gom.app.project.inspection.filter( 'explorer_category=="inspection" and ' \
													'(  result_dimension.is_tolerance_used == True '
													'or result_gdat_size.is_tolerance_used == True ' \
													'or result_angle.is_tolerance_used	 == True )' )

			result['uncomputed'] = gom.app.project.inspection.filter( 'explorer_category=="inspection" and computation_status != "computed" and ' \
																	'(result_dimension.is_tolerance_used   == True ' \
																	'or result_gdat_size.is_tolerance_used == True ' \
																	'or result_angle.is_tolerance_used	 == True )' )

			result['out_of_tol'] = gom.app.project.inspection.filter( 'explorer_category=="inspection" and ' \
																'  (result_dimension.out_of_tolerance  != invalid and result_dimension.is_tolerance_used == True) '
																'or (result_gdat_size.out_of_tolerance != invalid and result_gdat_size.is_tolerance_used == True) ' \
																'or (result_angle.out_of_tolerance	 != invalid and result_angle.is_tolerance_used	 == True) ' )

			result['result'] = not( len( result['uncomputed'] ) > 0 or len( result['out_of_tol'] ) > 0 )
			result['additional'] = ''

		except:
			result['all'] = list()
			result['uncomputed'] = list()
			result['out_of_tol'] = list()
			result['result'] = False
			result['additional'] = ''
		return result

	def check_results_elementlist( self, elementlist, result ):
		'''
		automatic result check
		will check all given elements (eg [e for e in gom.ElementSelection ( {'tag': ['user', 'TestElements']} )] ) which tolerance is used
		fills and returns given result dictionary with checked elements, uncomputed elements and out of tolerance elements
		'''
		for element in elementlist:
			is_tol_used = False
			for tol_token in ['result_dimension.is_tolerance_used', 'result_gdat_size.is_tolerance_used', 'result_angle.is_tolerance_used']:
				try:
					is_tol_used = element.get( tol_token )
					break
				except:
					continue
			if is_tol_used:
				result['all'].append( element )
				if element.get( 'computation_status' ) != 'computed':
					result['uncomputed'].append( element )
				else:
					for tol_token in ['result_dimension.out_of_tolerance', 'result_gdat_size.out_of_tolerance', 'result_angle.out_of_tolerance']:
						try:
							if element.get( tol_token ) is not None:
								result['out_of_tol'].append( element )
								break
						except:
							continue
		return result

	def start_automatic_trend_creator( self ):
		'''
		start additional instance for trend creation
		'''
		watch_folder = Globals.SETTINGS.SavePath  # watch complete savefolder

		pid = os.getpid()
		max_stages = Globals.SETTINGS.TrendMaxStageSize
		# ignore root, photogrammetry and async measured folders
		ignore_dirs = [os.path.normpath( Globals.SETTINGS.SavePath ),
			os.path.normpath( os.path.join( Globals.SETTINGS.SavePath, Globals.SETTINGS.PhotogrammetrySavePath ) ),
			os.path.normpath( os.path.join( Globals.SETTINGS.SavePath, Globals.SETTINGS.MeasureSavePath ) )]

		try:
			create_autowatch_cfg( pid, watch_folder, max_stages, ignore_dirs, Globals.SETTINGS.TrendShowOnSecondMonitor )
		except Exception as e:
			self.log.exception( 'failed to write trend configuration {}'.format( e ) )
			return

		scriptname = 'gom.script.userscript.KioskInterface__Tools__TrendCreator (parameters={\'PARAMS\':1 })'

		if Globals.SETTINGS.Inline:
			import gom_atos_log_filter
			watcher=gom_atos_log_filter.startInstance(scriptname, None, None, 'trend_inline', fullscreen=Globals.SETTINGS.TrendShowOnSecondMonitor)
			return

		env = os.environ
		# remote dongle would grab TWO vmr licenses
		sw_dir = gom.app.get ( 'software_directory' )
		args = [sw_dir + '/bin/GOMSoftware.exe', '-kiosk', '-nosplash',
			'-fullscreen' if Globals.SETTINGS.TrendShowOnSecondMonitor else '-minimized', '-eval', scriptname  ]
		process = subprocess.Popen( args, env = env )
		return process

	@staticmethod
	def createStatistics():
		'''
		creates if enabled a additional logfile which logs the evaluation statistics
		'''
		if not Globals.SETTINGS.LogStatistics:
			return None
		logdir = os.path.normpath( os.path.join( gom.app.get ( 'local_all_directory' ), '..', 'log' ) )
		return StatisticalLog.CSVStatistics( os.path.join( logdir, 'KioskInterfaceStatistics.log' ),
													needs_project_storage = Globals.SETTINGS.Async )

	@staticmethod
	def	scan_report_for_parts( partnames ):
		'''
		Return map of part names to reports referencing the part.
		'''	
		prep = {p:[] for p in partnames}
		for rep in gom.app.project.reports:
			parts = set()
			for elem in rep.all_elements_in_report:
				try:
					part = elem.part
				except:
					part = None
				if part is not None:
					parts.add( part.name )

			# No parts referenced
			# => report should be included for all parts (Title,TOC...)
			if len( parts ) == 0:
				for p in prep.keys():
					prep[p].append( rep )
			else:
				for p in parts:
					prep[p].append( rep )

		return prep

	@staticmethod
	def activate_part_keywords( part ):
		'''
		Copy keywords on the nominal of the "part" reference to project keywords.
		Return False, if the part has no nominal.
		Return restore information per keyword, otherwise.
		'''
		try:
			part.element_keywords
		except:
			return False
		shadow_kws = {}
		nom_kws = [kw[5:] for kw in part.element_keywords]
		pro_kws = [kw[5:] for kw in gom.app.project.project_keywords]
		for nkw in nom_kws:
			if nkw in pro_kws:
				shadow_kws[nkw] = gom.app.project.get( 'user_' + nkw )
				gom.script.sys.set_project_keywords (
					keywords = {nkw: part.get( 'user_' + nkw )} )
			else:
				shadow_kws[nkw] = None
				gom.script.sys.set_project_keywords (
					keywords = {nkw: part.get( 'user_' + nkw )},
					keywords_description = {nkw: part.get( 'description(user_' + nkw + ')' )} )

		return shadow_kws
	
	@staticmethod
	def restore_keywords( shadow_kws ):
		'''
		Restore project keywords from the restore information returned by 'activate_part_keywords'.
		If the restore information is <False> do nothing.
		'''
		if shadow_kws is False:
			return
		pro_kws = [kw[5:] for kw in gom.app.project.project_keywords]
		kwdescs = {}
		for pro_kw in pro_kws:
			kwdescs[pro_kw] = (
				gom.app.project.get( 'user_' + pro_kw ),
				gom.app.project.get( 'description(user_' + pro_kw + ')' ) )
		for shadow_kw, val in shadow_kws.items():
			if val is None:
				del kwdescs[shadow_kw]
			else:
				kwdescs[shadow_kw] = (val, gom.app.project.get( 'description(user_' + shadow_kw + ')' ) )

		gom.script.sys.set_project_keywords (
			keywords_definition=[(kw, item[1], item[0]) for (kw, item) in kwdescs.items()],
			keywords={kw: item[0] for (kw, item) in kwdescs.items()} )

	@staticmethod
	def find_alignments( name_pattern, aligns ):
		found = []
		for a in aligns:
			if re.search( name_pattern, a.name, re.IGNORECASE ):
				found.append( a )
	
		return found

	@staticmethod
	def get_last_alignments( aligns=None ):
		'''Get a list of all alignments which are not the parent of another alignment.
		Extend this method to implement a tie breaker for the case
		where more than one "last" alignment exist.
		'''
		if aligns is None:
			aligns = gom.app.project.alignments
	
		leafs = []
		for a in aligns:
			found = False
			for b in aligns:
				try:
					if a.name == b.parent_alignment.name:
						found = True
						break
				except:
					pass
			if not found:
				leafs.append(a)
	
		return leafs

	@staticmethod
	def get_result_alignment( part=None ):
		'''
		Get the result alignment of (a specific part in) the project.
		If an alignment name is specified in the settings, try to find this alignment (in the part).
		If there is more than one alignment matching the setting, choose the first matching alignment.
		Otherwise get the "last" alignment (in the part), i.e. the alignment which is not a parent of another alignment.
		If the "last" alignment is not unique, just choose the last of these alignments.
		If even this fails, choose the last of all alignments (in the part).
		Override this method if you want to implement a completely different selection method.
		'''
		alignment = None
		if part is None:
			aligns = gom.app.project.alignments
		else:
			aligns = gom.ElementSelection ({'category': [
				'key', 'elements', 'part', part, 'explorer_category', 'alignment']})

		# find alignment via setting
		if part is None and len(Globals.SETTINGS.ResultAlignment) > 0:
			try:
				alignment = gom.app.project.alignments[Globals.SETTINGS.ResultAlignment]
			except:
				Globals.LOGGER.warning(
					'Alignment from Kiosk Settings or project keyword "{}" does not exist!'.format(
					Globals.SETTINGS.ResultAlignment ))
		elif part is not None and len( Globals.SETTINGS.MPResultAlignmentPattern ) > 0:
			found_aligns = EvaluationAnalysis.find_alignments( Globals.SETTINGS.MPResultAlignmentPattern, aligns )
			if len( found_aligns ) == 0:
				Globals.LOGGER.warning(
					'Alignment from Kiosk Settings or project keyword "{}" not found (part={})!'.format(
						Globals.SETTINGS.MPResultAlignmentPattern, '-' if part is None else part.name ))
			else:
				if len( found_aligns ) > 1:
					Globals.LOGGER.warning(
						'Alignment from Kiosk Settings or project keyword "{}" not unique (part={})!'.format(
							Globals.SETTINGS.MPResultAlignmentPattern, '-' if part is None else part.name ))
				alignment = found_aligns[0]

		# determine the "last" aligment
		if alignment is None:
			last_aligns = EvaluationAnalysis.get_last_alignments( aligns )
			if len(last_aligns) > 1:
				Globals.LOGGER.warning( '"Last" alignment not unique: {}'.format(
					', '.join( [a.name for a in last_aligns] )))
			if len(last_aligns) > 0:
				alignment = last_aligns[-1]

		# should never happen
		if alignment is None:
			# if this fails, well...
			alignment = aligns[-1]

		return alignment

	@staticmethod
	def switch_to_result_alignment( override_alignment=None, part=None ):
		'''Activate the result alignment or the given override alignment (or name thereof) (for a part).'''
		if override_alignment is None:
			alignment = EvaluationAnalysis.get_result_alignment( part )
		else:
			if isinstance( override_alignment, str ):
				alignment = gom.app.project.alignments[override_alignment]
			else:
				alignment = override_alignment

		gom.script.manage_alignment.set_alignment_active (
			cad_alignment=alignment )

		gom.script.sys.recalculate_project ( with_reports=False )

		Globals.LOGGER.info( 'Switched to alignment "{}"'.format( alignment.name ))

	@staticmethod
	def switch_all_parts_to_result_mesh():
		recalc = False
		if gom.app.project.is_part_project:
			for part in EvaluationAnalysis.scan_parts:
				part = gom.app.project.parts[part]
				if EvaluationAnalysis.switch_to_result_meshvariant( part ):
					recalc = True

		if recalc:
			gom.script.sys.recalculate_project( with_reports=False )

	@staticmethod
	def switch_to_result_meshvariant( part ):
		mesh_variants = part.chain_ordered_actual_part_variants
		if mesh_variants is not None and len( mesh_variants ) > 1:
			if mesh_variants[-1].name != part.actual.name:
				gom.script.mesh.define_as_active_actual_mesh( switch_to=mesh_variants[-1] )
				Globals.LOGGER.info( 'Switched part "{}" to mesh variant "{}"'.format(
					part.name, mesh_variants[-1].name ))
				return True
		return False


	@staticmethod
	def getRelativePDFPath( result, part_id=None, partname=None ):
		if not len( gom.app.project.reports ):
			return ''
		( project_name, export_path ) = Evaluate.export_path_info()
		if Utils.multi_part_evaluation_status():
			part = gom.app.project.parts[partname]
			shadow_kws = EvaluationAnalysis.activate_part_keywords( part )
			project_name = Evaluate.project_name_for_part( part, result )
			EvaluationAnalysis.restore_keywords( shadow_kws )

		# failed postfix is at this point already included in the project name
		return os.path.relpath( os.path.join( export_path, project_name + '.pdf' ), Globals.SETTINGS.SavePath )

	@staticmethod
	def export_results( result ):
		'''
		This function is called directly after the Approve/Disapprove button is clicked in the confirmation dialog or after async evaluation. It stores the
		current project to a directory. You may want to patch this function for example to export measurement
		information to your needs.

		Arguments:
		result - True if user approved measurement data, otherwise False
		'''
		( project_name, export_path ) = Evaluate.export_path_info()
		if not os.path.exists( export_path ):
			os.makedirs( export_path )

		if not result and Globals.SETTINGS.FailedPostfix not in project_name:
			project_name += Globals.SETTINGS.FailedPostfix

		if not Globals.SETTINGS.CurrentTemplateIsConnected:
#			# TODO keep this method for the idea to let Eval keep the template always open, probably remove this later
#			save_mode = 'save_as'
#			if Globals.FEATURE_SET.MULTIROBOT_EVALUATION:
#				save_mode = 'export'
			while True:
				try:
#					if save_mode == 'save_as':
					gom.script.sys.save_project_as( file_name = os.path.join( export_path, project_name ) )
#					elif save_mode == 'export':
#						gom.script.sys.export_gom_inspect_file ( file=os.path.join( export_path, project_name ) )
				except Exception as error:
					if Globals.SETTINGS.Async:
						raise
					res = Globals.DIALOGS.show_errormsg(
						Globals.LOCALIZATION.msg_save_error_title, Globals.LOCALIZATION.msg_save_error_message,
						Globals.SETTINGS.SavePath, True )
					if res == True:
						continue
				break
		else:
			gom.script.sys.save_project()

		if len( gom.app.project.reports ) and Globals.SETTINGS.ExportPDF:
			if not Utils.multi_part_evaluation_status():
				try:
					gom.script.report.export_pdf (
						export_all_reports = True,
						file = os.path.join( export_path, project_name + '.pdf' ),
						jpeg_quality_in_percent = 100,
						reports = gom.app.project.reports )
				except:
					pass
			else:
				# export per part
				reports_per_part = EvaluationAnalysis.scan_report_for_parts( EvaluationAnalysis.scan_parts )
				for partname in reports_per_part.keys():
					part = gom.app.project.parts[partname]
					shadow_kws = EvaluationAnalysis.activate_part_keywords( part )
					gom.script.sys.recalculate_elements (
						elements=gom.ElementSelection( reports_per_part[partname] ) )
					try:
						gom.script.report.export_pdf (
							file = os.path.join( export_path,
								Evaluate.project_name_for_part( part, result ) + '.pdf' ),
							jpeg_quality_in_percent = 100,
							reports = reports_per_part[partname] )
					except:
						pass
					EvaluationAnalysis.restore_keywords( shadow_kws )

		vdi_elements = list( gom.ElementSelection ( {'category': ['key', 'elements', 'explorer_category', 'inspection', 'object_family', 'vdi']} ) )
		if len( vdi_elements ):
			try:
				gom.script.vdi.export_test_protocol (
						element = vdi_elements[0],
						file = os.path.join( export_path, project_name + '_vdi.pdf' ) )
			except:
				pass

class MeasuringContext:
	def __init__(self, parent, comp_photo_series, comp_atos_series, comp_calib_series, comp_hyperscale_series, will_calibration_be_performed):
		self.parent = parent
		self.measure_done_send = False
		self.moved_to_home = False
		all_series=[gom.app.project.measurement_series[ms] for ms in comp_photo_series if self.parent.is_measurement_series_executable(ms)]
		if len(all_series) and isinstance(self.parent.Tritop.import_photogrammetry( all_series[0], True), str): # tritop will be skipped
			all_series=[]
		all_series +=[gom.app.project.measurement_series[ms] for ms in comp_atos_series if self.parent.is_measurement_series_executable(ms)]
		all_series +=[gom.app.project.measurement_series[ms] for ms in comp_hyperscale_series]
		direct_allowed = all([Measure.isDirectMoveAllowed(m) for m in all_series]) # calibration does not need to be checked and is not supported by the function
		if will_calibration_be_performed:
			all_series+= [gom.app.project.measurement_series[ms] for ms in comp_calib_series]

		gom.script.automation.set_measurement_progress_by_script(pending_measurement_series=all_series, demo=Globals.SETTINGS.OfflineMode, direct_movement=direct_allowed)

	def __enter__(self):
		self.parent.context = self
		# Do not init CFP counter in DRC mode as first exec already happened after mseries selection
		if Globals.DRC_EXTENSION is None or not Globals.DRC_EXTENSION.PrimarySideActive():
			FixturePositionCheck.FixturePositionCheck.init_exec_count()
		if Globals.SETTINGS.Inline:
			Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MEASURING, str(1) ) )
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		if not self.moved_to_home:
			self.parent.moveDevicesToHome()
		gom.script.automation.set_measurement_progress_by_script( pending_measurement_series=None )

		# Remove / Clean-up remaining FixtureCheck info
		FixturePositionCheck.FixturePositionCheck.tear_down()

		if not self.measure_done_send:
			if Globals.SETTINGS.Inline:
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MEASURING, str(0) ) )
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_EXECUTION_TIME, str(0) ) )
			if Globals.SETTINGS.IoTConnection:
				Globals.IOT_CONNECTION.send(template=Globals.SETTINGS.CurrentTemplate, execution_time=0)

		self.parent.context = None


class PositionInformation:
	def __init__(self, parent):
		self.parent = parent
		self.Comp_photo_series = []
		self.Comp_atos_series = []
		self.Comp_calibration_series = []
		self.in_mlist = False
		self.current_mlist_name = None
		self.total_mlist_count=0
		self.current_mlist_count=0
		self.in_mlist_last_index = 0
		self.in_continue_mlist = False

	def start_measurement_process(self, Comp_photo_series, Comp_atos_series, Comp_calibration_series):
		self.Comp_photo_series = [ms for ms in Comp_photo_series if self.parent.is_measurement_series_executable(ms)]
		self.Comp_atos_series = [ms for ms in Comp_atos_series if self.parent.is_measurement_series_executable(ms)]
		self.Comp_calibration_series = Comp_calibration_series
		self.total_mlist_count = len(self.Comp_photo_series)+len(self.Comp_atos_series)

		self.current_mlist_name = None
		self.current_mlist_count=0
		self.in_mlist_last_index = 0
		self.in_mlist = False
		self.in_continue_mlist = False
		
		if not Globals.SETTINGS.Inline:
			return

		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_TOTAL, str(self.total_mlist_count) ) )
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_CURRENT,str( 0 ) ) )
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_POSITION, str( 0 ) ) )
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_POSITION_TOTAL, str( 0 ) ) )

	def start_measurement_list(self):
		self.in_mlist=True
		self.in_mlist_last_index = 0
		active_ml = Utils.real_measurement_series( filter='is_active==True' )
		if not len( active_ml ):
			self.in_mlist=False
			return
		active_ml = active_ml[0]
		if self.in_continue_mlist:
			self.in_continue_mlist = False
			return
		
		if not Globals.SETTINGS.Inline:
			return
		
		calibration=False
		for c in self.Comp_calibration_series:
			if c == active_ml.name:
				calibration=True
				break
		if calibration:
			self.total_mlist_count+=1
			Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_TOTAL, str(self.total_mlist_count) ) )
		else:
			if self.current_mlist_name == active_ml.name: # check if after e.g calibration the same ms will be executed
				self.total_mlist_count+=1
				Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_TOTAL, str(self.total_mlist_count) ) )
			self.current_mlist_name = active_ml.name

		if self.current_mlist_count==0 and active_ml.type == 'atos_measurement_series' and len(self.Comp_photo_series): # tritop skipped
			self.current_mlist_count = len(self.Comp_photo_series) + 1
		else:
			self.current_mlist_count+=1
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_CURRENT,str( self.current_mlist_count ) ) )
		Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_POSITION, str( 0 ) ) )
		if gom.app.project.is_part_project:
			Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_POSITION_TOTAL, str( len(active_ml.measurement_path.path_positions) ) ) )
		else:
			Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_POSITION_TOTAL, str( len(active_ml.measurements) ) ) )

	def end_measurement_list(self):
		self.in_mlist=False
		self.in_mlist_last_index = 0
		self.in_continue_mlist = False

	def set_continue_mlist(self):
		self.in_continue_mlist = True

	def updated_position_information(self):
		if not Globals.SETTINGS.Inline and not Globals.SETTINGS.IoTConnection:
			return
		if not self.in_mlist:
			return

		position_changed = False
		if gom.app.project.is_part_project:
			for ml in gom.app.project.measurement_paths.filter('is_active==True'):
				for m in ml.path_positions.filter('is_current_position==True'):
					if self.in_mlist_last_index != m.get ('index_in_path'):
						if Globals.SETTINGS.Inline:
							Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_POSITION, str(m.get ('index_in_path')) ) )
						self.in_mlist_last_index = m.get ('index_in_path')
						position_changed = True
					break
		else:
			for ml in Utils.real_measurement_series( filter='is_active==True' ):
				for m in ml.measurements.filter( 'is_current_position==True' ):
					if self.in_mlist_last_index != m.get( 'index_in_path' ):
						if Globals.SETTINGS.Inline:
							Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_MLIST_POSITION, str(m.get ('index_in_path')) ) )
						self.in_mlist_last_index = m.get( 'index_in_path' )
						position_changed = True
					break
		if not position_changed:
			return
		remaining=gom.app.get('measurement_progress_remaining_time')
		if remaining is None:
			return
		remaining= int(remaining)
		if Globals.SETTINGS.Inline:
			Globals.CONTROL_INSTANCE.send_signal( Communicate.Signal( Communicate.SIGNAL_CONTROL_EXECUTION_TIME, str(remaining) ) )
		if Globals.IOT_CONNECTION is not None:
			Globals.IOT_CONNECTION.send(template=Globals.SETTINGS.CurrentTemplate, 
									execution_time=remaining)