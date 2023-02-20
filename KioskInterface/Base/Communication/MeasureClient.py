# -*- coding: utf-8 -*-
# Script: Connection handling script for a connection to a Multirobot measure client
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


from ..Misc import Utils, Globals
from . import AsyncClient, Communicate
from .Inline import InlineConstants

import gom
import pickle


class MeasureClient( Utils.GenericLogClass ):
	def __init__(self, id, host, port, logger):
		Utils.GenericLogClass.__init__( self, logger )
		self.remote_todos = Communicate.RemoteTodos( self.baselog )
		self.connected = False
		self.ready = False
		self.delayed_pkts = []
		self.pushback_pkts = []
#		self.auto_ctrl = []
		self.comp_mmts = None
		self.device_status = None
		self.wcfgs = []
		self.tritop_series = []
		self.atos_series = []
		self.calib_series = []
		self.active_series = ''
		self.robot_program_id = None
		self.id = id
		self.host = host
		self.port = port
		self.name = '{} {}:{}'.format(id, host, port)
		self.log.debug('measure client {} init'.format(self.name))
		self.con = AsyncClient.DoubleRobotClient( self.baselog, self, host, port, {} )

	def reset_mseries(self):
		self.tritop_series = []
		self.atos_series = []
		self.calib_series = []
		self.active_series = ''

	# collect pkts in background timer
	def collect_pkts(self):
		while self.con.check_for_activity(timeout=0):
			pass
		was_connected = self.connected
		self.connected = self.con.check_first_connection()
		if not was_connected and self.connected:
			self.on_first_connection()
		elif was_connected and not self.connected:
			self.remote_todos.clear()
			self.ready = False
		for last_result in self.con.LastAsyncResults:
			if last_result == Communicate.SIGNAL_INLINE_DRC_SECONDARY_INST_DATA:
				continue

			if last_result == Communicate.SIGNAL_MULTIROBOT_MMT_STARTUP_DONE:
				self.log.debug( 'Client {}: Startup done'.format( self.name ) )
				self.unpack_comp_mmts_from_signal( last_result )
				self.ready = True
				continue

			if last_result == Communicate.SIGNAL_MULTIROBOT_STATUS:
				self.log.debug( 'Client {}: Status'.format( self.name ) )
				self.device_status = pickle.loads( last_result.value )
				continue

			self.log.debug( 'Client {}: Sig {}'.format( self.name, repr( last_result ) ) )
			self.delayed_pkts.append( last_result )

#			if last_result == Communicate.SIGNAL_FAILURE:
##				if Globals.SETTINGS.AllowAsyncAbort:
##					self.log.debug('Triggering async abort')
##					gom.app.abort = True # TODO hier muss man nicht abbrechen oder?
##				else:
##					self.log.debug( 'Flagging abort' )
##					Globals.SETTINGS.InAsyncAbort = True
#				self.log.debug( 'Client {}: Failure received {}'.format( self.name, repr( last_result ) ) )
#				self.delayed_pkts.append( last_result )
#
#			elif last_result == Communicate.SIGNAL_SUCCESS:
##				last_todo = self.remote_todos.finish( last_result )
##				self.log.debug( 'Client {}: Finished todo {}'.format( self.name, repr( last_todo ) ) )
##				if last_todo is None:
##					self.log.error( 'Client {}: Unknown reason for SUCCESS signal'.format( self.name ) )
#				# defer reaction to handler
#				self.delayed_pkts.append( last_result )
#			elif last_result == Communicate.SIGNAL_MULTIROBOT_COMP_MMTS:
#				self.comp_mmts = pickle.loads( last_result.value )
#				self.log.debug( 'Client {}: Compatible measurements info: {}'.format( self.name, self.comp_mmts ) )
#			else:
#				self.log.debug( 'Client {}: other sig received {}'.format( self.name, repr( last_result ) ) )
#				self.delayed_pkts.append( last_result )

	def unpack_comp_mmts_from_signal( self, sig ):
		try:
			self.comp_mmts = pickle.loads( sig.value )
			self.log.debug( 'Client {}: Compatible measurements: {}'.format( self.name, self.comp_mmts ) )
		except:
			self.log.error( 'Client {}: Failed to extract compatible mmts: {}'.format( self.name, sig ) )
			self.comp_mmts = None

	def pump_pkts(self):
		for pkt in self.pushback_pkts:
			self.delayed_pkts.append( pkt )
		self.pushback_pkts = []

	def on_first_connection(self):
		self.delayed_pkts = []
		self.pushback_pkts = []
		self.ready = False