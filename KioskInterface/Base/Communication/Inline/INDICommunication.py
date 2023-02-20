# -*- coding: utf-8 -*-
#
# PLEASE NOTE that this file is part of the GOM Software.
# You are not allowed to distribute this file to a third party without written notice.
#
# Please, do not copy and/or modify this script.
# All modifications of KioskInterface should happen in the CustomPatches script.
# Ignoring this advice will make KioskInterface fail after Software update.
#
# Copyright (c) 2020, 2021 Carl Zeiss GOM Metrology GmbH
# All rights reserved.

# GOM-Script-Version: 2020


import gom

import asyncore
import asynchat
import socket
import time

from ...Misc import Globals, Utils, LogClass

from .InlineConstants import *
from .InlineVariables import *
from . import InlineWidgetHelper 


##############################################################################
# IN/OUT-GOING Signals

SIG_IDENT = 0
SIG_ALIVE = 1
SIG_NOTIMPL = 2
SIG_MEAS = 3
SIG_RESULT = 4
SIG_MEAS_ANSWER = 5
SIG_MEAS_WAIT = 6
SIG_MEAS_FINISH = 7
SIG_MEAS_RESULT = 8
SIG_READY = 9
SIG_MEAS_READY = 10
SIG_MEAS_NOTREADY = 11

SIGNAME = {
	SIG_IDENT: 'ident',
	SIG_ALIVE: 'alive',
	SIG_NOTIMPL: 'not implemented',
	SIG_MEAS: 'measurement',
	SIG_RESULT: 'result',
	SIG_MEAS_ANSWER: 'measurement answer',
	SIG_MEAS_WAIT: 'measurement wait',
	SIG_MEAS_FINISH: 'measurement finished',
	SIG_MEAS_RESULT: 'measurement result',
	SIG_READY: 'ready?',
	SIG_MEAS_READY: 'ready for measurement',
	SIG_MEAS_NOTREADY: 'not ready for measurement'
	}
def signame( sig ):
	return SIGNAME.get( sig, 'unknown' )

SIGNALS = {
	SIG_IDENT: b'Identification',
	SIG_ALIVE: b'*',
	SIG_MEAS: b'M',
	SIG_RESULT: b'T',
	SIG_READY: b'ReadyForMeasure'
	}

OUTGOING = {
	SIG_MEAS_ANSWER: 'Q',
	SIG_MEAS_WAIT: 'WaitStart',
	SIG_MEAS_FINISH: 'S',
	SIG_MEAS_RESULT: 'D',
	SIG_MEAS_READY: 'ReadyForMeasureTrue',
	SIG_MEAS_NOTREADY: 'ReadyForMeasureFalse'
	}


##############################################################################
# Task structure for grouping status of one mmt cycle

class Task:
	def __init__(self, data):
		self.data = data
		# TODO result obsolete (old async Kiosk method)
		self.result = None
		# state values: 'unknown', 'prepare', 'measure', 'ok', 'error', 'finished'
		self.state = 'unknown'
		# active state True until prepare & measuring finished, False after that
		self.active_state = True
		# result done is set to True when result has been sent to INDI
		# only used for tasks without evaluation
		self.result_done = False
		self.fail_reason = None
		self.template_info = None
		self.temperature = None
		self.refxml = None
		self.eval_client = None
		self.eval_start = None
		self.eval_result = None

	def __str__(self):
		sync = '?'
		prgid = -1
		try:
			sync = self.get_sync_timestamp()
		except:
			pass
		try:
			prgid = self.get_robot_program_id()
		except:
			pass
		eval = self.eval_client
		return '{}/{:3d}: {} @eval {}'.format( sync, prgid, self.state,
			eval if eval is not None else 'none' )

	def set_status_prepare(self):
		# never overwrite 'error'
		if self.state == 'unknown':
			self.state = 'prepare'
	def set_status_measure(self):
		# never overwrite 'error'
		if self.state == 'prepare':
			self.state = 'measure'
	def set_status_ok(self):
		# never overwrite 'error'
		if self.state == 'measure':
			self.state = 'ok'
	def set_status_finished(self):
		# never overwrite 'error'
		if self.state == 'ok':
			self.state = 'finished'
	def set_status_failed(self, *reasons):
		self.state = 'error'
		# append to previous reasons
		if self.fail_reason is None:
			self.fail_reason = list( reasons )
		else:
			self.fail_reason += list( reasons )

	def activate_task(self):
		self.active_state = True
		return self
	def release_task(self):
		self.active_state = False
		return None

	def set_status_result_done(self):
		self.result_done = True

	def finished(self, log=None):
		if log is not None:
			log('state {} active {} result {} eval? {}'.format( self.state, self.active_state, self.result_done, self.eval_client is not None))
		# always considered not finished until result is sent to INDI
		if not self.result_done:
			return False
		# always considered not finished until mmt finished
		if self.active_state:
			return False
		# completely evaluated
		if self.state == 'finished':
			return True
		# failed
		if self.state == 'error':
			return True
		# mmt done and no evaluation pending
		if self.state == 'ok' and self.eval_client is None:
			return True
		return False
	def failed(self):
		return self.state == 'error'

	def get_serial(self):
		return self.data['prodnumber']

	def get_sync_timestamp(self):
		return self.data['SYNC']

	def get_template_select_info(self):
		return self.data['MEASPLAN']

	def get_robot_program_id(self):
		return int( self.data['RBTPRG'] )

	def get_telegram(self):
		return self.data

	def get_telegram_keywords(self):
		# TODO define a selection of the 'important' data?
		#return {'prodnumber': self.data['prodnumber'], 'SYNC': self.data['SYNC']}
		return self.data

	def set_template(self, *template_info):
		self.template_info = template_info

	def set_temperature(self, temperature):
		self.temperature = temperature

	def set_refxml(self, refxml):
		self.refxml = refxml

	def set_eval_client(self, client):
		self.eval_client = client
		if client is not None:
			self.eval_start = time.time()
	def get_eval_client(self):
		return self.eval_client
	def get_eval_starttime(self):
		return self.eval_start

	def set_eval_failed(self, signal):
		self.eval_result = False
		self.set_status_failed( signal.get_value_as_string() )
	def set_eval_success(self, signal):
		self.eval_result = True

	def add_result(self, result):
		# TODO result obsolete (old async Kiosk method)
		self.result = result


##############################################################################
# XML Result Templates / Values

_template_xml_header = '''<HEADER>
<SYSTEM>ATOS</SYSTEM>
<MEASDATE lextype="yyyy-MM-dd">{date}</MEASDATE>
<MEASTIME lextype="HH.mm.ss">{time}</MEASTIME>
<PRODNUM1>{prod}</PRODNUM1>
<PRODNUM2>UNDEFINED</PRODNUM2>
<PRODNUM3>UNDEFINED</PRODNUM3>
<TYPE>Type</TYPE>
<MODEL>Model</MODEL>
<BLDLEV>-</BLDLEV>
<MODE>Auto</MODE>
</HEADER>
'''
_template_xml_item = '''
<RAWDATAITEM>
<FEATURENAME>{name}</FEATURENAME>
<SENSORNAME>ATOS</SENSORNAME>
<MEASSTATUS>{status}</MEASSTATUS>
<VISION_TRIGGER_ID>{name}</VISION_TRIGGER_ID>
<MODIFIED>False</MODIFIED>
<VISION_STATUS_CATEGORY>{reason}</VISION_STATUS_CATEGORY>
<MEASSYS>ATOS</MEASSYS>
<RAWITEM>
<POINTNAME>1</POINTNAME>
<ACT>
<Existent>1.000</Existent>
</ACT>
<SENSOR>
<Existent>1.000</Existent>
</SENSOR>
</RAWITEM>
</RAWDATAITEM>
'''

# MEASSTATUS "status"
S_NoMeasuring    = -1
S_Mismeasurement = 0
S_OnlyValidation = 1
S_OutOfValidationTolerance = 2
S_OnlyOptical = 3
# ... (unused)
S_GoodResult = 9

# VISION_STATUS_CATEGORY "reason"
R_OKAY    = 'Okay'
R_PERF    = 'PerformanceProblem'
R_UNKNOWN = 'UnknownProblem'
R_CONFIG  = 'ConfigurationProblem'
R_PROCESS = 'ImageProcessingProblem'
R_SYSTEM  = 'SystemProblem'


# ITEM failed measurement
#_template_xml_item = '''
#            <RAWDATAITEM>
#                <FEATURENAME>{}PointWithMismeasurement</FEATURENAME>
#                <SENSORNAME>ATOS</SENSORNAME>
#                <MEASSTATUS>0</MEASSTATUS>
#                <VISION_TRIGGER_ID>PointWithMismeasurement</VISION_TRIGGER_ID>
#                <MODIFIED>False</MODIFIED>
#                <VISION_STATUS_CATEGORY>ImageProcessingProblem</VISION_STATUS_CATEGORY>
#                <MEASSYS>ATOS</MEASSYS>
#            </RAWDATAITEM>
#'''

# ITEM not measured
#            <RAWDATAITEM>
#                <FEATURENAME>PointNotMeasuredDeliberately</FEATURENAME>
#                <SENSORNAME>MVS3D</SENSORNAME>
#                <MEASSTATUS>-1</MEASSTATUS>
#                <VISION_TRIGGER_ID />
#                <MODIFIED>False</MODIFIED>
#                <VISION_STATUS_CATEGORY>Okay</VISION_STATUS_CATEGORY>
#                <MEASSYS>MVS3DAdmin</MEASSYS>
#            </RAWDATAITEM>

# ITEM with data
#            <RAWDATAITEM>
#                <FEATURENAME>PointSucessfullyMeasured</FEATURENAME>
#                <SENSORNAME>MVS3D</SENSORNAME>
#                <MEASSTATUS>9</MEASSTATUS>
#                <VISION_TRIGGER_ID>PointSucessfullyMeasured</VISION_TRIGGER_ID>
#                <MODIFIED>False</MODIFIED>
#                <VISION_STATUS_CATEGORY>Okay</VISION_STATUS_CATEGORY>
#                <MEASSYS>MVS3DAdmin</MEASSYS>
#                <RAWITEM>
#                    <POINTNAME>1</POINTNAME>
#                    <ACT>
#                        <X>1.000</X>
#                        <Y>2.000</Y>
#                        <Z>3.000</Z>
#                        <XVector>-1.000</XVector>
#                        <YVector>-2.000</YVector>
#                        <ZVector>-3.000</ZVector>
#                    </ACT>
#                    <SENSOR>
#                        <X>9.000</X>
#                        <Y>8.000</Y>
#                        <Z>7.000</Z>
#                        <XVector>-9.000</XVector>
#                        <YVector>-8.000</YVector>
#                        <ZVector>-7.000</ZVector>
#                    </SENSOR>
#                </RAWITEM>
#            </RAWDATAITEM>
#            <RAWDATAITEM>
#                <FEATURENAME>PointWithConfigChangeInVisionSW</FEATURENAME>
#                <SENSORNAME>MVS3D</SENSORNAME>
#                <MEASSTATUS>9</MEASSTATUS>
#                <VISION_TRIGGER_ID>PointWithConfigChangeInVisionSW</VISION_TRIGGER_ID>
#                <MODIFIED>True</MODIFIED>
#                <VISION_STATUS_CATEGORY>Okay</VISION_STATUS_CATEGORY>
#                <MEASSYS>MVS3DAdmin</MEASSYS>
#                <RAWITEM>
#                    <POINTNAME>1</POINTNAME>
#                    <ACT>
#                        <X>0.000</X>
#                        <Y>0.000</Y>
#                        <Z>-10.365</Z>
#                        <XVector>-0.002</XVector>
#                        <YVector>-0.113</YVector>
#                        <ZVector>-0.994</ZVector>
#                    </ACT>
#                    <SENSOR>
#                        <X>0.000</X>
#                        <Y>0.000</Y>
#                        <Z>-10.365</Z>
#                        <XVector>-0.002</XVector>
#                        <YVector>-0.113</YVector>
#                        <ZVector>-0.994</ZVector>
#                    </SENSOR>
#                </RAWITEM>
#            </RAWDATAITEM>

_template_xml = '''<MEASUREMENTS>
<MEASUREMENT>
{header}
<MEASDATA />
<RAWDATA>
{items}
</RAWDATA>
</MEASUREMENT>
</MEASUREMENTS>
'''


class INDICommunication(Utils.GenericLogClass):

	class INDI_Client( asynchat.async_chat, Utils.GenericLogClass ):
		'''
		INDI Client Connection
		'''
		def __init__( self, logger, parent, host='localhost', port=2049, sctmap={} ):
			# init logging
			Utils.GenericLogClass.__init__( self, logger )
			self.parent = parent
			self.host = host
			self.port = port
			self.sctmap = sctmap
			self.ReconnectTimeout = 60
			self.AliveTimeout = 60
			asynchat.async_chat.__init__( self, map=sctmap )
			asynchat.async_chat.set_terminator( self, None )

			self.connected = False
			self.handshaked = False
			self.buffer = b''
			self.async_todo = []
			self.async_results = []

			self.log.info( 'Connecting to {} on port {}'.format( host, port ) )
			self.create_socket( socket.AF_INET, socket.SOCK_STREAM )
			self.connect_ts = time.time()
			self.alive_ts = self.connect_ts
			self.connect( ( host, port ) )

		def handle_connect( self ):
			'''
			called during connection to INDI, sets only state and timestamps
			'''
			self.log.info( 'Connected to INDI' )
			self.connect_ts = time.time()
			self.alive_ts = self.connect_ts
			self.connected = True
			self.handshaked = False

		def disconnect( self ):
			self.log.info( 'Disconnect from INDI' )
			self.close()
			self.connected = False
			self.handshaked = False
			self.buffer = b''
			self.async_todo = []
			self.async_results = []
			# set timestamps so re-connect is done after timeout
			self.connect_ts = time.time()
			self.alive_ts = self.connect_ts

		def parse_telegram( self, msg ):
			pairs = msg.split(';')
			prod = pairs.pop(0)
			tele = {'prodnumber': prod}
			tele.update( {p.split(':')[0]:p.split(':')[1] for p in pairs if ':' in p} )
			self.log.debug( 'parse_telegram {}'.format( repr( tele ) ) )
			return tele
			
		def compile_data( self, sig, msg ):
			# returns corrected len of signal
			if sig in [SIG_IDENT]:
				return None

			if sig == SIG_ALIVE:
				# 7 digits
				no = int( msg[1:].decode( 'utf-8' ) )
				return no

			if sig in [SIG_MEAS, SIG_RESULT]:
				tele = self.parse_telegram( msg[1:].decode( 'utf-8' ) )
				return tele

			return None

		def collect_incoming_data( self, data ):
			self.buffer += data
			while b'\x0a' in self.buffer:
				i = self.buffer.find( b'\x0a' )
				onemsg = self.buffer[:i]
				self.buffer = self.buffer[i+1:]

				found = False
				for (sig, msg) in SIGNALS.items():
					if onemsg.startswith( msg ):
						msgdata = self.compile_data( sig, onemsg )
						self.async_todo.append( ( sig, msgdata ) )
						found = True
				if not found:
					self.async_todo.append( ( SIG_NOTIMPL, None ) )

		def handle_close( self ):
			'''
			called during close event
			'''
			if self.connected:  # only log if connection was established
				self.log.debug( 'Closing INDI connection' )
			self.close()

		def send_message( self, msg, attached_xml=None ):
			try:
				msg = msg.strip()

				_xml = b''
				if attached_xml is not None:
					xml_bytes = attached_xml.encode( 'utf-8' )
					xml_len = b'%09d' % len( xml_bytes )
					_xml = xml_len + xml_bytes

				_msgbytes = msg.encode( 'utf-8' ) + _xml
				if not _msgbytes.endswith( b'\n' ):
					_msgbytes += b'\n'

				self.push( _msgbytes )
			except Exception as e:
				self.log.exception( 'Failed send {} / {}'.format( repr(msg), str(e) ) )

		def send_signal( self, sig ):
			msg = OUTGOING[sig]
			self.send_message( msg, None )

		def build_telegram( self, sig, tele ):
			start = OUTGOING[sig]
			prod = tele['prodnumber']
			data = ';'.join( '{}:{}'.format( k, v ) for (k, v) in tele.items() if k != 'prodnumber' )
			msg = '{}{};{}'.format( start, prod, data )
			self.log.debug( 'Message telegram for sig {}: {}'.format( sig, msg ) )
			return msg


		def handle_ident( self, sig ):
			try:
				msg = 'Identification{};VersionName{};VersionNumber{}\n'.format(
					self.parent.Identification,
					self.parent.VersionName,
					self.parent.VersionNumber
					)
				self.push( msg.encode( 'utf-8' ) )
			except Exception as e:
				self.log.exception( 'Failed identification send {}'.format( str(e) ) )

		def handle_alive( self, sig ):
			self.alive_ts = time.time()

		def handle_not_implemented( self, sig ):
			try:
				msg = 'FunctionNotAvailable\n'
				self.push( msg.encode( 'utf-8' ) )
			except Exception as e:
				self.log.exception( 'Failed not_implemented send {}'.format( str(e) ) )


		def process_signals( self ):
			'''
			collect signals from the buffer
			'''
			asyncore.loop( timeout=0, map=self.sctmap, count=1 )
			if not self.connected:
				if time.time() - self.connect_ts > self.ReconnectTimeout:
					self.log.debug( 'Not connected timeout - reconnect' )
					try:
						self.close()
					except Globals.EXIT_EXCEPTIONS:
						raise
					except:
						pass
					try:
						self.create_socket( socket.AF_INET, socket.SOCK_STREAM )
						self.connect_ts = time.time()
						self.alive_ts = self.connect_ts
						self.connect( ( self.host, self.port ) )
					except Globals.EXIT_EXCEPTIONS:
						raise
					except Exception as e:
						pass
				
				return False
			else:
				if time.time() - self.alive_ts > self.AliveTimeout:
					self.log.error( 'INDI Server not alive - disconnecting' )
					self.disconnect()

			anysignals = False
			while len( self.async_todo ) > 0:
				todo = self.async_todo.pop( 0 )
				if todo[0] == SIG_IDENT:
					self.log.debug( 'got Ident Signal {}'.format( todo ) )
					self.handle_ident( todo )
					self.handshaked = True
					# handle_packet starts Kiosk
					self.parent.handle_packet( *todo )
				elif todo[0] == SIG_ALIVE:
					self.handle_alive( todo )
				elif todo[0] == SIG_NOTIMPL:
					self.log.debug( 'got not implemented Signal {}'.format( todo ) )
					self.handle_not_implemented( todo )
				else:
					self.log.debug( 'got Signal {}'.format( todo ) )
					#self.async_results.append( todo )
					self.parent.handle_packet( *todo )
				anysignals = True
			return anysignals

		@property
		def LastAsyncResults( self ):
			if self.connected:
				for result in self.async_results:
					yield result



	def __init__(self, parent, logger, port=2049):
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.port = port
#		self.parent.measuringInstanceState.appendAction( self.onKioskStateChange )
#		self.parent.connectedState.appendAction( self.onConnectionStateChange )
#		self.parent.aliveState.appendAction( self.onAliveStateChange )
#		self.parent.resultState.appendAction( self.onResultStateChange )

		# platform info
		self.protocol_version = '1'
		self.Identification = 'ATOS'
		self.VersionName = 'ATOS'
		self.VersionNumber = (gom.app.application_name + ' '
			+ gom.app.application_build_information.version + ', Rev. '
			+ gom.app.application_build_information.revision + ', Build '
			+ gom.app.application_build_information.date + ', Prot. '
			+ self.protocol_version)


		self.telegram_data = None
		self.tasks = {}

		self.client = INDICommunication.INDI_Client( self.baselog, self, 'localhost', port, {} )


	def connect(self):
		pass

	def onConnectionError(self):
		pass

	def process_signals(self):
		self.parent.cycleTimeStat.updateTick()

		self.client.process_signals()

		if self.client.connected and self.client.handshaked:
			self.parent.indiState.value = State.OK
		elif self.client.connected:
			self.parent.indiState.value = State.UNKNOWN
		else:
			self.parent.indiState.value = State.ERROR


	def handle_packet(self, sig, data):
		self.log.debug( 'Packet {}/{} data {}'.format( sig, signame( sig ), repr( data ) ) )

		if sig == SIG_IDENT:
			# connection to INDI established, start Kiosk eval
			self.parent.actionStart()

		if sig == SIG_MEAS:
			self.telegram_data = data
			sync = self.telegram_data['SYNC']
			self.tasks[sync] = Task( self.telegram_data )
			self.log.debug( 'New task {}: telegram_data {}'.format( sync, repr( self.telegram_data ) ) )

				# TODO handle duplicate task
			# TODO anything todo about duplicate/unknown REQ ???

			self.parent.actionMeasure( self.tasks[sync] )
			return

		if sig == SIG_RESULT:
			#print( 'SIG_RESULT' )
			self.telegram_data = data
			task = None
			try:
				sync = self.telegram_data['SYNC']
				#print( 'sync', sync )
				task = self.tasks[sync]
				#print( 'task', task )
			except:
				pass

			# TODO handle task not exists
			# TODO anything todo about duplicate/unknown REQ ???

			if task is None:
				# TODO protocol error
				self.log.error( 'SIG_RESULT but no task' )
			else:
				tele = self.client.build_telegram( SIG_MEAS_RESULT, self.telegram_data )
				xml_res = self.build_xml_result( task )
				self.client.send_message( tele, xml_res )
				task.set_status_result_done()
				self.log.debug( 'Task {} result done'.format( task ) )

		if sig == SIG_READY:
			self.log.debug( 'READY: {}/{}/{}'.format(
				self.parent.connectedState.value == State.OK,
				self.parent.idleState.value == State.OK,
				self.parent.thermometer_state() ) )
			if (self.parent.connectedState.value == State.OK
				and self.parent.idleState.value == State.OK
				and self.parent.thermometer_state()):
				self.parent.actionReady( True )
				self.client.send_signal( SIG_MEAS_READY )
			else:
				self.parent.actionReady( False )
				self.client.send_signal( SIG_MEAS_NOTREADY )

	# TODO you should search for tasks by SYNC timestamp, not by eval client id
	def find_task(self, client_id):
		if client_id is None:
			return None
		for task in self.tasks.values():
			if task.get_eval_client() == client_id:
				return task
		return None

	def find_task_by_sync(self, sync):
		if sync is None:
			return None
		for task in self.tasks.values():
			if task.get_sync_timestamp() == sync:
				return task
		return None

	def delete_task(self, task=None, sync=None):
		if task is not None:
			sync = task.get_sync_timestamp()

		if sync in self.tasks:
			del self.tasks[sync]
			self.log.debug( 'Evaluation task {} deleted'.format( sync ) )
		else:
			self.log.error( 'Failed to delete evaluation task {}'.format( sync ) )

	def telegram_to_keyword(self, telegram):
		return ';'.join( [telegram['prodnumber'], telegram['SYNC']] )

	def keyword_to_telegram(self, keyword):
		values = keyword.split( ';' )
		telegram = {}
		telegram['prodnumber'] = values[0]
		telegram['SYNC'] = values[1]
		return telegram

	def build_xml_result(self, task):
		kws = task.get_telegram_keywords()
		if task.state == 'error':
			status = S_Mismeasurement
			reason = R_SYSTEM
		elif task.state == 'ok' or task.state == 'finished':
			status = S_GoodResult
			reason = R_OKAY
		else:
			status = S_NoMeasuring
			reason = R_UNKNOWN

		date_ = time.strftime( '%Y-%m-%d' )
		time_ = time.strftime( '%H.%M.%S' )
		prod_ = kws['prodnumber']
		self.log.debug( 'Build XML for {} header {}/{}/{} result {}/{}'.format(
			task, date_, time_, prod_, status, reason ) )
		header = _template_xml_header.format( date=date_, time=time_, prod=prod_ )
		itemlist = []
		item = _template_xml_item.format( name='ResultMS', status=status, reason=reason )
		itemlist.append( item )
		items = '\n'.join( itemlist )
		xml = _template_xml.format( header=header, items=items )
		xml = xml.replace('\n', '')

		return xml


	def sendMeasureAnswer(self, task):
		self.log.debug( 'Send {}/{} for task {}'.format( SIG_MEAS_ANSWER, signame( SIG_MEAS_ANSWER ), task ) )
		telegram_data = task.get_telegram()
		self.client.send_message( self.client.build_telegram( SIG_MEAS_ANSWER, telegram_data ) )

	def sendMeasureFinished(self, task):
		self.log.debug( 'Send {}/{} for task {}'.format( SIG_MEAS_FINISH, signame( SIG_MEAS_FINISH ), task ) )
		telegram_data = task.get_telegram()
		self.client.send_message( self.client.build_telegram( SIG_MEAS_FINISH, telegram_data ) )


	def onErrorInMeasureInstance(self, error, error_desc):
		errmsg = 'Error{}: {}'.format( error, error_desc ).replace( '\n', '\\n' )
		self.client.send_message( errmsg )

	def onWarningInMeasureInstance(self, warning, warn_desc):
		warnmsg = 'Warnung{}: {}'.format( warning, warn_desc ).replace( '\n', '\\n' )
		self.client.send_message( warnmsg )