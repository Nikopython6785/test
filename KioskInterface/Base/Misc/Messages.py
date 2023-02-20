# -*- coding: utf-8 -*-
# Script: Definition of all messages for localization
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
# 2015-05-18: Descriptions of default project keywords added.

class Localization:

	msg_general_failure_title = 'Failure'
	msg_global_failure_text = 'Unexpected Failure: '

	msg_evaluate_process_text = '{0} of {1} Measurement steps'
	msg_evaluate_detail_msg_initialize = 'Initialize'
	msg_evaluate_detail_msg_reports = 'Update Reports'
	msg_evaluate_detail_msg_recalc = 'Recalculate Project'
	msg_evaluate_detail_msg_polygonize = 'Polygonize'
	msg_evaluate_detail_msg_photogrammetry = 'Photogrammetry'
	msg_evaluate_detail_msg_digitizing = 'Digitizing'
	msg_evaluate_detail_msg_safety_home = 'Using validated path to home'
	msg_evaluate_detail_calibrate = 'Calibrate'
	msg_evaluate_estimated_time = 'Estimated measurement execution time {} minutes left'

	msg_async_failure_title = 'Communication Failure'
	msg_async_failure_start_server = 'Failed to start Communication Server'
	msg_async_failure_communicate_client = 'Failed to communicate with AsyncClient'
	msg_async_client_process_working = 'Working on Project {}'
	msg_async_client_process_finished = 'Finished Project {}'
	msg_async_client_result = 'Part ID {0}: checked {1} elements, {2} elements uncomputed and {3} elements outside tolerance'

	msg_system_configuration_failed_title = 'System Configuration Check'
	msg_no_measurement_list = 'No compatible measurement series in template'
	msg_no_measurement_list_real = '<b>Connected hardware:</b>'
	msg_calibration_failed_execute = 'Failed to perform calibration series.'
	msg_calibration_no_list_defined = 'No Calibration Measurement Series defined'
	msg_photogrammetry_no_list_defined = 'No photogrammetry measurement series defined'
	msg_photogrammetry_verification_failed = 'Photogrammetry measurement verification failed.'
	msg_photogrammetry_failed_execute = 'Failed to excecute Photogrammetry series'
	msg_digitizing_no_list_defined = 'No digitizing measurement series defined'
	msg_digitizing_failed_execute = 'Failed to excecute Measurement series'
	msg_digitizing_failed_maxrepetitions = 'Failed to perform digitize measurement'
	msg_digitizing_failed_already_calibrated = 'Failed to perform digitize measurement.<br/>Calibration already performed.'
	msg_sensor_failed_init = 'Failed to initialize sensor'
	msg_sensor_failed_warmup = 'Failed to wait for sensor warmup'
	msg_msetup_sensor_offline = 'Sensor is uninitialized'
	msg_msetup_define_active_failed = 'Measuring setup could not be activated'
	msg_safely_move_failed = 'Failed to safely move to home position'
	msg_sensor_warning = 'ATOS ScanBox warning:<br/>{}'
	msg_evaluate_failed_home_check_series = 'Aborting Evaluation, its only possible to execute measurement series which start and end with an home position'
	msg_calibration_too_often = 'Calibration was already performed<br/>next possible Calibration in {}'
	msg_userabort = 'User abort'
	msg_verification_failed = 'Measurement verification failed'
	msg_verification_transformation_exception = 'Aborting due to transformation error.'
	msg_verification_temperature_exception = 'Aborting due to temperature difference error.'
	msg_verification_move_light_exception = 'Aborting due to movement/lighting error.'
	msg_verification_scale_bar_identify = 'Failed to identify scale bars'
	msg_verification_no_scan_data = 'No measurements with scandata found'
	msg_verification_refpointmismatch = 'Alignment residual difference was exceeded.<br/>Photogrammetry does not match digitizing measurements!'
	msg_emergency_button = 'Emergency Button pressed.'
	msg_multi_comprehensive_retries_exceeded = 'Number of retries for comprehensive photogrammetry exceeded.'
	msg_reverse_move_not_allowed = 'After emergency stop: This device does not allow a reverse move to home position.'
	msg_no_points_for_trafo = 'Could not find enough coded points for transform by common reference points.'

	msg_verification_transformation_failed = 'Transformation Limit failed in {0} measurements.<br/>Only {1} are allowed.'
	msg_verification_projector_residual_failed = 'Projector Residual Limit failed in {0} measurements.<br/>Only {1} are allowed.'
	msg_verification_movement_check_failed = 'Movement Check Limit failed in {0} measurements.'
	msg_verification_lighting_failed = 'Lighting Check Limit failed in {0} measurements.'
	msg_verification_intersection_failed = 'Intersection Check Limit failed in {0} measurements.'
	msg_verification_global_digitize_failed = 'Failed to verify measurement alignment'
	msg_verification_global_digitize_too_large = 'Measurement alignment residual is too large.'
	msg_verification_unrecoverable_position = 'Unrecoverable robot position detected'
	msg_verification_calibration_failed = 'Failed to verify calibration.'

	msg_fixture_position_check_title = 'Check fixture position.'
	msg_fixture_position_check_failed = 'Fixture position check failed. Adjust the setup and retry.'
	msg_fixture_position_check_failed_component_not_found = 'Not all point components could be identified.'
	msg_fixture_position_check_failed_missing_points = 'Not enough points were found.'
	msg_fixture_position_check_failed_rotated = 'The part is rotated.'
	msg_fixture_position_check_failed_position = 'The part is positioned incorrectly.'
	msg_fixture_position_check_not_performed = 'Position check of fixture was not performed!<br/>The template does not contain all needed elements.<br/>Please verify that the setup is correct!'

	startdialog_label_title = '<p style="font-size: 48px">Welcome</p>'
	startdialog_label_part = 'Part "{}"'
	startdialog_label_user = 'User:'
	startdialog_label_serial = 'Serial:'
	startdialog_label_batch = 'Batch:'
	startdialog_label_fixture = 'Fixture:'
	startdialog_label_template = 'Template:'
	startdialog_button_template = 'Choose'
	startdialog_button_start = 'Start'
	startdialog_button_exit = 'Exit'
	startdialog_button_next = 'Next'
	startdialog_button_prev = 'Previous'

	multipart_wizard_button_next = 'Next'
	multipart_wizard_button_prev = 'Prev'
	multipart_wizard_label_title = '<p style="font-size: 32px">Fill in serials<br>and choose templates</p>'
	multipart_wizard_label_page = 'Page {} of {}'
	multipart_waitdialog_title = '<p align="center">Adapt the measuring setup for template<br/>{}</p>'
	multipart_waitdialog_button_ok = 'OK'
	multipart_waitdialog_button_cancel = 'Cancel'

	progessdialog_label_title = 'Wait until the measurement is completed'
	progressdialog_multipart_label = 'Total number of projects'

	confirmdialog_label_title = '<p style="font-size: 48px">Approve Component</p>'
	confirmdialog_label_instruction = '<p style="font-size: 32px">Do you want to accept the measurement?</p>'
	confirmdialog_button_approve = 'Approve'
	confirmdialog_button_reject = 'Reject'

	errordialog_button_retry = 'Retry'
	errordialog_button_abort = 'Abort'
	errordialog_button_close = 'Close'
	errordialog_button_gomsic = 'GOMSic'
	errordialog_button_continue = 'Continue'

	waitdialog_title = 'Please Wait'
	waitdialog_client_setup = 'Setting up clients.'
	waitdialog_clients_exit = 'Wait for clients to exit'
	waitdialog_software_execute = 'Connection to other side established.\nPerforming measurements.'

	measuring_setup_title = '<p align="center">Make sure the measurement setup<br/>is ready for measurement series:</p>'
	measuring_setup_button_ok = 'OK'
	measuring_setup_button_cancel = 'Cancel'
	temperature_title = '<p align="center" style="font-size: 32px">Enter current temperature in °C</p>'
	temperature_button_ok = 'OK'
	temperature_button_cancel = 'Cancel'
	msg_common_refpoint_trafo_less_points = 'Transform by common reference points failed: less than three points found!'
	msg_common_refpoint_trafo_error = 'Transform by common reference points failed: {}'

	msg_cannot_execute = 'Not possible to evaluate this project: no VMR, or not all measurements have recorded positions!'

	msg_settings_errortitle = 'Kiosk Settings Error'
	msg_setting_invalid = 'Unexpected Failure: invalid setting {}'
	msg_settings_savepath_failed = 'Failed to create save path folder "{}"<br/>Please contact your administrator and start the setup script which can be found within the script database'
	msg_settings_idrange_failed = 'Interpretation of setting "PhotogrammetryCodedPointIDRange" failed: "{}"<br/>Please correct the value in the Kiosk settings file'
	msg_settings_comprehensive_batchscan = '"PhotogrammetryComprehensive" setting only usable in BatchScan-mode.'
	msg_settings_comprehensive_independent = '"PhotogrammetryComprehensive" does not work with "PhotogrammetryIndependent".'
	msg_settings_secondary_paths = '"DoubleRobot_ClientSavePath" and "DoubleRobot_ClientTransferPath" must be different.'
	msg_settings_aligniter_nomlist = '"AlignmentIteration" requires "MSeriesSelection = True".'
	msg_settings_repetition_value = '"MaxDigitizeRepetition" minimum value is 1 (1 measurement and no repetition).'
	msg_settings_failmargin_value = '"MeasurementFailureMargin" requires a value between 0.0 and 1.0.'
	msg_settings_inline_ioextension = '"Inline" and "IOExtension" cannot be activated at the same time.'

	msg_platform_not_supported = 'Only the Windows platform is supported!'

	msg_barcode_connectionfailed = 'Failed to communicate with BarCode Scanner on port COM{}'

	msg_disc_space_warning = 'Disc space warning limit reached!<br/>Only {}MB free in {}'
	msg_disc_space_error = 'Disc space error limit reached!<br/>Only {}MB free in {}'
	msg_save_error_title = 'Final project save failed'
	msg_save_error_message = 'Not enough disc space for the evaluated project.'

	project_consistency_title = 'Invalid project template'
	project_consistency_report_alignments = '<b>Used alignments in reports:</b>'
	project_consistency_required_alignments = '<b>Alignments required:</b>'
	project_consistency_vmr = '<b>VMR:</b>'
	project_consistency_measuring_setups = '<b>Measuring setups:</b>'
	project_consistency_computation_status = '<b>Computation status:</b>'
	project_consistency_path_status = '<b>Path status:</b>'
	project_consistency_vmr_measurement_series = '<b>VMR measurement series:</b>'
	project_consistency_report_status = '<b>Report status:</b>'
	project_consistency_measurement_status = '<b>Measurement parameters:</b>'
	project_consistency_photogrammetry = '<b>Photogrammetry:</b>'
	project_consistency_nco = '<b>Elements in clipboard:</b>'
	project_consistency_preview_mode = '<b>Project:</b>'
	project_consistency_non_master_actual_data = '<b>Elements with actual data are kept:</b>'
	project_consistency_2_indep_tritops = 'More than one independent photogrammetry in one measuring setup'

	keyword_description_user = 'Inspector'
	keyword_description_serial = 'Part no.'
	keyword_description_fixture = 'Fixture no.'
	keyword_description_date = 'Date'

	statusbar_text_multipart_progress = '<center>Performing measurement {} of {}</center>'

	msg_no_atos_inline_license = 'Inline license is needed!'

	msg_DC_client_failure = 'Secondary Instance failure: {}'
	msg_DC_temperature_error_title = 'Preferences temperature error'
	msg_DC_temperature_error_text = 'In the software preferences the temperature acquisition method "ask user" is selected.<br/>Double robot cells can only work with fixed measuring room temperature or connected hardware thermometers. Please, correct the software preferences.'
	dialog_DC_ms_title = 'Which measurements should be performed?'
	dialog_DC_ms_text = 'Which measurement series should be\nperformed for the measuring process?'
	dialog_DC_ms_align = 'Which measurement series should be\nused for the adjustment process?'
	dialog_DC_ms_all_untagged = 'All untagged measurement series'
	dialog_DC_ms_all = 'All measurement series'
	dialog_DC_ms_start = 'Start'
	dialog_DC_ms_abort = 'Abort'
	status_DC_choose_measurements = 'Choose measurements'
	msg_DC_no_slave_mlist_found = 'No corresponding Secondary Instance measurement series found'
	msg_DC_refcubes_not_unique = 'The template contains more than one nominal reference cubes element. The reference cube check will be skipped.'
	msg_DC_no_refcubes = 'The template uses robogrammetry workflow, but it does not contain simulated reference cubes.'
	msg_DC_refcubes_failed = 'Failed to check the reference cubes.'
	msg_DC_refcube_check_retry = '"Use" the reference cubes as they are or "Correct" their positions?'

	dialog_DC_RefCube_ask_use = 'Use'
	dialog_DC_RefCube_ask_retry = 'Correct'
	dialog_DC_RefCube_ask_abort = 'Abort'
	dialog_DC_RefCube_template_use = 'Continue'

	dialog_FC_Calib_title = 'Calibration with unknown fixture position'
	dialog_FC_Calib_msg = '''Fixture position could not be determined due to decalibrated sensor.\n
		For calibration to proceed you need to confirm that\n
		 - the measuring cell is empty (fixture removed)\n
		 - or the fixture is not obstructing the calibration measurement path'''
	dialog_FC_Calib_empty_cell = 'Cell is empty'
	dialog_FC_Calib_not_obstructed = 'Calibration not obstructed'
	dialog_FC_Calib_abort = 'Abort'
	
	msg_DC_slave_failed_open = '{} - failed to open template'
	msg_DC_slave_drivefull = '{} - Disc space limit reached'
	msg_DC_slave_invalid_project = '{} - Invalid Project'

	msg_DC_slave_measurement_series_not_found = '{} - Measurement series not found'
	msg_DC_slave_measurement_series_not_comp = '{} - Measurement series not compatible'
	msg_DC_slave_failed_to_copy = '{} - Failed to copy measurement file to {}\n{}'

	dialog_mlist_ask_use = 'Use'
	dialog_mlist_ask_retry = 'Retry'
	dialog_mlist_ask_abort = 'Abort'
	msg_mlist_retry = 'Should the measurement series performed again?'

	dialog_oneshot_ask_clear = 'Clear measurement data'
	dialog_oneshot_ask_keep = 'Keep measurement data'
	dialog_oneshot_ask_abort = 'Abort'
	dialog_oneshot = 'The current project will be executed via DRC mode, do you want to keep the measurement data or clear it before execution?'
	msg_oneshot_export_error = 'Failed to export temporary project for secondary instance.'

	dialog_mmp_title = 'Setup Reference Points'
	dialog_mmp_setup_refpoints = 'Setup sensor, lift and exposure times,</br >so that enough reference points are detected'
	dialog_mmp_continue = 'Continue'