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
import gom
import os


class StartUpV8( Workflow.StartUpV8, metaclass = Utils.MetaClassPatch ):

	def set_additional_project_keywords ( self ):
		# Add new project keywords to the following table as indicated by the given example.
		# You have to patch the start dialog below by adding corresponding input fields to it.
		# The kiosk software will set the user's input as a project keyword.
		Globals.ADDITIONAL_PROJECTKEYWORDS = [
			# specify keywords as tuples of four values
			#   ('name', 'description', 'inputfield', 'optional')
			#        name: Name of your new project keyword (string)
			# description: The keyword description (string)
			#  inputfield: The name of the input field of the start dialog (string)
			#    optional: Specify if the kiosk should allow the start button also for an empty input value
			#              (True or False)
			# Example:
			#   ('mykeyword', 'My keyword description:', 'input_my_keyword', False)
			]


class PatchedEvaluationAnalysis( Evaluate.EvaluationAnalysis, metaclass = Utils.MetaClassPatch ):
	@staticmethod
	def export_results( result ):
		'''
		This function is called directly after the Approve/Disapprove button is clicked in the confirmation dialog or after async evaluation. It stores the
		current project to a directory. You may want to patch this function for example to export measurement
		information to your needs.

		Arguments:
		result - True if user approved measurement data, otherwise False
		'''
		# call of the original function to export ginspect and pdf
		Evaluate.EvaluationAnalysis.original__export_results( result )

		( project_name, export_path ) = Evaluate.Evaluate.export_path_info()
		if not os.path.exists( export_path ):
			os.makedirs( export_path )

		# if the original export_results function was called the failed postfix is already part of the current project name
		# if not result:  # append failed postfix on failure
		# 	project_name += Globals.SETTINGS.FailedPostfix

		# Activate the following line if your custom exports below need to be executed in the result alignment.
		# Alternatively, you can also pass a specific alignment (name) as parameter.
		#Evaluate.EvaluationAnalysis.switch_to_result_alignment()

		# Start recording the custom export here
		# use for your export function as file parameter e.g.
		# file = os.path.join(export_path,project_name+'.txt'),

