# -*- coding: utf-8 -*-
# Script: Custom Patches
#
# PLEASE NOTE that this file is part of the GOM Inspect Professional software
# You are not allowed to distribute this file to a third party without written notice.
#
# Copyright (c) 2016 GOM GmbH
# Author: GOM Software Development Team (M.V.)
# All rights reserved.

# GOM-Script-Version: 7.6
#
# ChangeLog:
# 2012-05-31: Initial Creation
# 2013-04-15: Results are now grouped into different folders based on template
# 2013-09-03: Changed import statements to use relative imports thus the Setupscript can import it
#             (custom configurations will be kept)
# 2014-05-16: Use project token to get the based template name
# 2015-04-23: Added template for table of additional project keywords

from Base.Misc import Globals, Utils, DefaultSettings, Messages
from Base import Workflow, Evaluate
from Base.Measuring import Verification
from Base.Measuring.Verification import DigitizeResult, VerificationState
import gom
import os

class patchedMeasureChecks(Verification.MeasureChecks, metaclass = Utils.MetaClassPatch):
	def __init__( self, logger, parent ):
		'''
		initialize function
		'''
		Verification.MeasureChecks.original____init__(self, logger, parent)
		self.retry_err = 0
		
	def analyze_error( self, error, series, retry_allowed = False, errorlog = None ):
		'''
		analyze measurement exception
		@return VerificationState value
		'''
		self.log.info('start overriding MeasureCheck.analyze_error')
		result = self.original__checkalignment_residual(error, series, retry_allowed,errolog)
		if result == VerificationState.Abort:
			if error.args[0] in ['MPROJ-0021'] and self.retry_err < 1:
				self.retry_err += 1
				self.log.error( 'Unrecoverable robot position detected: {}'.format( error ) )
				if self.try_getting_position():
					return VerificationState.Retry
				else:
					return VerificationState.Abort
			else:
				return result
		else:
			return result
			
	def try_getting_position(self):
		first_last_pos=None
		index=0
		measure=[]
		self.log.info('start try_getting_position')
		try:
			activeMs=[mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==gom.MeasurementListActiveState (True)][0]
		except:
			self.log.info('no active msserie')
			return False
		try:
			activePosition=[mpos for mpos in activeMs.measurements if mpos.get('object_family') == 'measurement_series' and mpos.is_current_position][0]
		except:
			activePosition=''
		if len(activePosition):
			self.log.info('in known position : ' + str(activePosition))
			return True
		for i in activeMs.measurements:
			measure.append(i)
		measure.reverse()
		for i in measure:
			if i.type == "scan":
				if i.measurement_transformation != None:
					first_last_pos=activeMs.measurements[index]
					break
				index += 1
		if first_last_pos!=None:
			try:
				self.log.info('trying to move to position : ' + str(first_last_pos))
				gom.interactive.automation.move_to_position (measurement=first_last_pos)
			except:
				self.log.info("Can't move to position : "+ str(first_last_pos))
		activePosition=[mpos for mpos in activeMs.measurements if mpos.get('object_family') == 'measurement_series' and mpos.is_current_position][0]
		if len(activePosition):
			self.log.info('now in known position')
			return True
		else:
			self.log.info('not in known position')
			return False

