# -*- coding: utf-8 -*-
# Script: Fixture Check library Kiosk integration script.
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
from ..Misc import Utils, Globals
from .Verification import DigitizeResult

vmr_license_missing = False
try:
	from Tools.VMR.CheckFixturePosition.check_fixture_position_lib import Components, Feedback
except:
	vmr_license_missing = True


# See get_mlist: special "not initialized" value
# Cannot use None, because this is valid. (any unique object will do)
FPC_NOT_SET = ValueError( 'fpc not set' )


class FixturePositionCheck (Utils.GenericLogClass):
	mlist = FPC_NOT_SET
	nom_comp = FPC_NOT_SET
	exec_count = 0

	def __init__(self, logger, parent):
		self.parent = parent
		Utils.GenericLogClass.__init__( self, logger )
	
		self.actual_point_cloud_created = False
		self.part_actual_name = None
		self.part = None

		# Undo is used as workaround to clean up project (moving polygonization does not work properly)
		self.initial_undo_steps = gom.app.undo_num_undo_steps
	def __enter__ (self):
		# Switch of transformation check
		self.check_transformation_state = gom.app.project.check_transformation
		gom.script.atos.set_acquisition_parameters (do_transformation_check=False)
		
		# Get data from project, so even if position check is disabled, all necessary elements will be removed during exit.
		self.initData ()
		
		return self

	def __exit__(self, type, value, traceback):

		# Change transformation check back
		gom.script.atos.set_acquisition_parameters (do_transformation_check=self.check_transformation_state)

		self.clean_up ()
		return

	def is_fixture_position_check_possible (self):
		if (   vmr_license_missing
			or self.parent.IsVMRlight 
			or Globals.SETTINGS.Inline			    # inline not supported
			or not gom.app.project.is_part_project  # only new part based workflow
			# there are part positions specified in a measuring setup => point components will not work
			or gom.app.project.measuring_setups[0].part_positions is not None
			or not Globals.SETTINGS.CheckFixturePosition
			or ( FixturePositionCheck.exec_count > 0 and not Globals.SETTINGS.CheckFixtureRepeat ) ):
			return False

		# Check if position check is necessary on template switch, but only if last check was successful
		if (Globals.SETTINGS.CheckFixturePositionOnlyOnTemplateSwitch and 
						not Globals.SETTINGS.TemplateWasChanged and
						Globals.SETTINGS.LastFixturePositionCheckWasOk):
			return False

		return True

	def initData (self):
		try:
			FixturePositionCheck.mlist = self.get_mlist_and_remove_it_from_list()
			FixturePositionCheck.nom_comp = self.get_components()

			for nc in FixturePositionCheck.nom_comp:
				self.part = nc.part
				break
			
			for nc in FixturePositionCheck.nom_comp:
				if nc.part != self.part:
					raise ValueError( 'Nominal component not all in same part.' )

			has_actual = False
			try:
				if self.part.actual.name is not None:
					has_actual = True
			except:
				pass
				
			if has_actual:
				self.part_actual_name = self.part.actual.name # Save mesh name

				# Delete actual from part to avoid problems on retry in VC projects
				if gom.app.is_undo_enabled:
					gom.script.cad.delete_element (
						elements=[self.part.actual], 
						with_measuring_principle=True)
		except:
			self.log.exception( 'Init data for Fixture position check was not possible!' )


	def check_fixture_position (self):
		Globals.SETTINGS.LastFixturePositionCheckWasOk = False
		
		# No check or error for old templates
		if FixturePositionCheck.mlist is None and not FixturePositionCheck.nom_comp:
			self.log.info ( 'Fixture position check was not supported by template.' )
			return True
		
		# If number of measurements and components do not match, show an error		
		if (FixturePositionCheck.mlist is None or self.part is None
			or len(FixturePositionCheck.mlist.measurements) != len(FixturePositionCheck.nom_comp)):
			dialog_res = Globals.DIALOGS.show_errormsg(Globals.LOCALIZATION.msg_fixture_position_check_title,
					Globals.LOCALIZATION.msg_fixture_position_check_not_performed,
					None, # sic_path
					True, # retry_enabled
					Globals.LOCALIZATION.errordialog_button_continue, # retry_text
					None, # error_code
					Globals.LOCALIZATION.errordialog_button_abort) # abort_text
			if dialog_res == False:
				return False # abort
			else: # continue will ignore the error
				self.log.info ( 'Fixture position check was not performed because measurement series or components are missing!' )
				return True
		
		# Set original alignment as inital to avoid automatic recalculations
		if gom.app.is_undo_enabled:
			for p in gom.app.project.parts:
				if p.part_function != 'used_for_scanning':
					continue
				try:
					gom.script.manage_alignment.define_original_alignment_as_initial_alignment (part = p)
					gom.script.manage_alignment.set_alignment_active (cad_alignment = p.original_alignment)
				except:
					pass

		if not self.measure_positions ():
			return False
		
		res = self.compute_and_check_fixture_position()
		FixturePositionCheck.exec_count += 1
		return res

	@staticmethod
	def init_exec_count():
		FixturePositionCheck.exec_count = 0

	@staticmethod
	def get_mlist( atos_series ):
		# Find special mlist for fixture position check
		for ml in atos_series:
			try:
				ms = gom.app.project.measurement_series[ml]
			except:
				continue
			
			if 'user_used_for_check_fixture_position' in ms.element_keywords and ms.user_used_for_check_fixture_position == "True":
				FixturePositionCheck.mlist = ms
				return ml

		FixturePositionCheck.mlist = None
		return None

	def get_cached_mlist( self, atos_series ):
		if FixturePositionCheck.mlist is not FPC_NOT_SET:
			if FixturePositionCheck.mlist is None:
				return None
			else:
				return FixturePositionCheck.mlist.name

		return FixturePositionCheck.get_mlist( atos_series )

	def get_mlist_and_remove_it_from_list( self ):
		'''Note: Removal from the list of mseries no longer happens here.'''
		ml = self.get_cached_mlist( self.parent.Comp_atos_series )
		if ml is not None:
			ms = gom.app.project.measurement_series[ml]
			self.log.info ( 'Use ' + ms.name + ' to check fixture position.' )
			return ms

		return None

	def get_components (self):
		if FixturePositionCheck.nom_comp is not FPC_NOT_SET:
			return FixturePositionCheck.nom_comp

		usable_nominal_components = []
		all_nominal_components = gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'nominal', 'object_family', 'point_component']})
		for nc in all_nominal_components:
			if 'user_used_for_check_fixture_position' in nc.element_keywords and nc.user_used_for_check_fixture_position == "True":
				usable_nominal_components.append (nc)
				self.log.info( 'Use ' + nc.name + ' to check fixture position.' )
		
		return usable_nominal_components
	
	def show_error_dialog (self, text):
		error_dialog=gom.script.sys.create_user_defined_dialog (content='<dialog>' \
			' <title>Check fixture position</title>' \
			' <style></style>' \
			' <control id="Empty"/>' \
			' <position>left</position>' \
			' <embedding>embedded_in_kiosk</embedding>' \
			' <sizemode>automatic</sizemode>' \
			' <size height="156" width="249"/>' \
			' <content rows="2" columns="3">' \
			'  <widget row="0" rowspan="1" column="0" columnspan="1" type="image">' \
			'   <name>image</name>' \
			'   <tooltip></tooltip>' \
			'   <use_system_image>true</use_system_image>' \
			'   <system_image>system_message_warning</system_image>' \
			'   <data><![CDATA[AAAAAAAAAA==]]></data>' \
			'   <file_name></file_name>' \
			'   <keep_original_size>true</keep_original_size>' \
			'   <keep_aspect>true</keep_aspect>' \
			'   <width>0</width>' \
			'   <height>0</height>' \
			'  </widget>' \
			'  <widget row="0" rowspan="1" column="1" columnspan="2" type="display::text">' \
			'   <name>text</name>' \
			'   <tooltip></tooltip>' \
			'   <text></text>' \
			'   <wordwrap>false</wordwrap>' \
			'  </widget>' \
			'  <widget row="1" rowspan="1" column="0" columnspan="1" type="spacer::horizontal">' \
			'   <name>spacer</name>' \
			'   <tooltip></tooltip>' \
			'   <minimum_size>0</minimum_size>' \
			'   <maximum_size>-1</maximum_size>' \
			'  </widget>' \
			'  <widget row="1" rowspan="1" column="1" columnspan="1" type="button::pushbutton">' \
			'   <name>button_retry</name>' \
			'   <tooltip></tooltip>' \
			'   <text>Retry</text>' \
			'   <type>push</type>' \
			'   <icon_type>system</icon_type>' \
			'   <icon_size>icon</icon_size>' \
			'   <icon_system_type>ok</icon_system_type>' \
			'   <icon_system_size>default</icon_system_size>' \
			'  </widget>' \
			'  <widget row="1" rowspan="1" column="2" columnspan="1" type="button::pushbutton">' \
			'   <name>button_abort</name>' \
			'   <tooltip></tooltip>' \
			'   <text>Abort</text>' \
			'   <type>push</type>' \
			'   <icon_type>system</icon_type>' \
			'   <icon_size>icon</icon_size>' \
			'   <icon_system_type>cancel</icon_system_type>' \
			'   <icon_system_size>default</icon_system_size>' \
			'  </widget>' \
			' </content>' \
			'</dialog>')
		
		error_dialog.title = Globals.LOCALIZATION.msg_fixture_position_check_title
		error_dialog.text.text = Globals.LOCALIZATION.msg_fixture_position_check_failed + "<br/>" + text
		error_dialog.button_retry.text = Globals.LOCALIZATION.errordialog_button_retry
		error_dialog.button_abort.text = Globals.LOCALIZATION.errordialog_button_abort
		
		def dialog_event_handler (widget):
			if isinstance( widget, gom.Widget ) and widget.name == 'button_retry':
				gom.script.sys.close_user_defined_dialog( dialog = error_dialog, result = True )
			elif isinstance( widget, gom.Widget ) and widget.name == 'button_abort':
				gom.script.sys.close_user_defined_dialog( dialog = error_dialog, result = False )
		
		try:
			error_dialog.handler = dialog_event_handler
			dialog_result = gom.script.sys.show_user_defined_dialog (dialog=error_dialog)
		except gom.BreakError as e:
			dialog_result = False
			
		return dialog_result
	
	def measure_positions (self):
		try:
			result = self.parent.Atos.perform_measurement( FixturePositionCheck.mlist, reverse_only=True, unknown_fixture=True )
			if result == DigitizeResult.Failure:
				return False
		except Globals.EXIT_EXCEPTIONS:
			raise
		except Utils.CalibrationError as error:
			self.log.exception( str( error ) )
			Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_general_failure_title, '\n'.join(error.args), Globals.SETTINGS.SavePath, False )
			return False
		
		return True

	def compute_and_check_fixture_position (self):
		current_position_check = Components.CheckActualPosition(
			self.part, FixturePositionCheck.nom_comp, FixturePositionCheck.mlist )
		results = current_position_check.getResults ()
		self.actual_point_cloud_created = True
		
		all_positions_ok = True
		for r in results:
			self.log.info(r)
			if not r.isPositionOk ():
				all_positions_ok = False
		
		if not all_positions_ok:
			self.log.info ( 'Fixture position is *NOT* ok!' )

			# Show feedback elements and dialog
			dialog_res = False
			with Feedback.Feedback (FixturePositionCheck.mlist, results) as fb:
				error = fb.createFeedback ()

				if error == Feedback.Feedback.ErrorType.NOT_FOUND:
					dialog_res = self.show_error_dialog (Globals.LOCALIZATION.msg_fixture_position_check_failed_component_not_found)	
				elif error == Feedback.Feedback.ErrorType.TOO_FEW_POINTS:
					dialog_res = self.show_error_dialog (Globals.LOCALIZATION.msg_fixture_position_check_failed_missing_points)
				elif error == Feedback.Feedback.ErrorType.TRANSLATION:
					dialog_res = self.show_error_dialog (Globals.LOCALIZATION.msg_fixture_position_check_failed_position)
				elif error == Feedback.Feedback.ErrorType.ROTATION:
					dialog_res = self.show_error_dialog (Globals.LOCALIZATION.msg_fixture_position_check_failed_rotated)
				else:
					dialog_res = self.show_error_dialog ("")
				
			if dialog_res == False:
				self.log.info ( ' -> abort' )
				return False
			else: # Retry
				# Delete actual point cloud, because a new one will be created
				try:
					gom.script.cad.delete_element (
						elements=[gom.ActualReference (self.part)], 
						with_measuring_principle=True)
					self.actual_point_cloud_created = False
				except:
					pass
				
				self.log.info ( ' -> retry' )
				if not self.measure_positions ():
					return False
		
				return self.compute_and_check_fixture_position () 
		
		self.log.info ( 'Fixture position is ok.' )
		
		Globals.SETTINGS.LastFixturePositionCheckWasOk = True
		return True

	def clean_up (self):
		'''Clean-up routine. The result allows a re-setup and repetition of check fixture.'''
		if gom.app.is_undo_enabled: # disabled undo has still one undo step
			active_msetups = gom.app.project.measuring_setups.filter ("is_active==True")
			
			undo_changes = gom.app.undo_num_undo_steps - self.initial_undo_steps
			gom.script.sys.show_undo_steps (num_steps = -undo_changes)
			
			# Reactivate measuring setup, activation could be reverted due to undo and
			# instructions should be only shown once
			if (len(active_msetups) == 1):
				gom.script.automation.define_active_measuring_setup (measuring_setup = active_msetups[0])
		else:
			# Fallback if undo was disabled, does not work for virtual clamping
			# and the polygonization looses the parameters
		
			if self.actual_point_cloud_created:
				# Delete created actual reference point cloud
				gom.script.cad.delete_element (
					elements=[gom.ActualReference (self.part)], 
					with_measuring_principle=True)
				
				# Move mesh from clipboard back to part
				if self.part_actual_name is not None: 
					gom.script.part.add_elements_to_part (
						elements=[gom.app.project.clipboard.actual_elements[self.part_actual_name]],
						import_mode='replace_elements', 
						part = self.part)

			if Globals.SETTINGS.KeepCheckFixturePositionElements:
				if FixturePositionCheck.mlist is not None and FixturePositionCheck.mlist is not FPC_NOT_SET:
					gom.script.automation.clear_measuring_data (measurements=[FixturePositionCheck.mlist])

				if FixturePositionCheck.nom_comp is not FPC_NOT_SET:
					for comp in FixturePositionCheck.nom_comp:
						try:
							gom.script.cad.delete_element (elements=[comp.actual_element])
						except:
							pass
					
					if FixturePositionCheck.nom_comp:
						gom.script.inspection.measure_by_no_measuring_principle(
							elements=FixturePositionCheck.nom_comp )

		if ( FixturePositionCheck.mlist is not None and FixturePositionCheck.mlist is not FPC_NOT_SET
			and FixturePositionCheck.mlist.reference_points_master_series is None ):
			atos_mseries = self.parent.Comp_atos_series
			photo_mseries = self.parent.Comp_photo_series
			master = None
			for ms in photo_mseries + atos_mseries:
				if ms == FixturePositionCheck.mlist.name:
					continue
				mseries = gom.app.project.measurement_series[ms]
				if mseries.reference_points_master_series is not None:
					master = mseries.reference_points_master_series
				else:
					master = mseries 
				break
			if master is not None:
				gom.script.atos.edit_measurement_series_dependency (
					dependency='master_series', 
					master_series=master,
					measurement_series=[FixturePositionCheck.mlist] )
			else:
				self.log.error( 'Unable to correct dependency of FixtureCheck ATOS mseries' )

	@staticmethod
	def tear_down():
		'''Additional clean-up routine. The result does not allow a re-setup and repetition of check fixture,
		except in the case of KeepCheckFixturePositionElements.
		'''
		# Already torn down
		if FixturePositionCheck.mlist is FPC_NOT_SET and FixturePositionCheck.nom_comp is FPC_NOT_SET:
			return

		if not Globals.SETTINGS.KeepCheckFixturePositionElements:
			try:
				# Delete measurement list
				if FixturePositionCheck.mlist is not None and FixturePositionCheck.mlist is not FPC_NOT_SET:
					gom.script.cad.delete_element (
						elements=[FixturePositionCheck.mlist], 
						with_measuring_principle=True)

				# Delete nominal point components
				if FixturePositionCheck.nom_comp is not FPC_NOT_SET and FixturePositionCheck.nom_comp:
					gom.script.cad.delete_element (
						elements=FixturePositionCheck.nom_comp, 
						with_measuring_principle=True)
			except:
				Globals.LOGGER.warning( 'Failed to tear down fixture check elements' )

		FixturePositionCheck.mlist = FPC_NOT_SET
		FixturePositionCheck.nom_comp = FPC_NOT_SET