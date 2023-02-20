# -*- coding: utf-8 -*-
# Script: General Signal, Handler definitions
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

import gom

from ..Misc import Utils, Globals
import os, subprocess, time
import asyncore, asynchat
import socket
from collections import deque
import xdrlib
import json
import datetime

from .PLC import PLCfunctions
from .PLC import PLCconstants as plc_const

class Signal( object ):
	'''
	Packet definition class
	'''
	key = None
	value = None
	ALL_SIGNALS = []

	def __init__( self, key, value = None ):
		if type( key ) == type( self ):
			self.key = key.key
			if value is None:
				self.value = key.value
			else:
				if type( value ) == str:
					self.value = str.encode( value )
				else:
					self.value = value
		else:
			self.key = key
			if type( value ) == str:
				self.value = str.encode( value )
			else:
				if value is None:
					self.value = b''
				else:
					self.value = value
			already=False
			for all_s in Signal.ALL_SIGNALS:
				if all_s == self:
					already=True
					break
			if not already:
				Signal.ALL_SIGNALS.append(self)

	def __repr__( self ):
		desc = Signal.getSignalDescription(self)
		try:
			if len( self.value ) > 500:
				return "{}: {} -> {}".format( desc, self.key, bytes.decode( self.value[:100] ) )
			return "{}: {} -> {}".format( desc, self.key, bytes.decode( self.value ) )
		except UnicodeError:
			if len( self.value ) > 500:
				return "{}: {} -> {}".format( desc, self.key, self.value[:100] )
			return "{}: {} -> {}".format( desc, self.key, self.value )

	def encode( self ):
		'''
		encodes signal definition into packet
		'''
		pack = xdrlib.Packer()
		pack.pack_int( self.key )
		pack.pack_bytes( self.value )
		packet = pack.get_buffer()
		del pack
		return packet

	def __eq__( self, other ):
		if isinstance(other, Signal):
			return self.key == other.key
		return False
	def __ne__( self, other ):
		if isinstance(other, Signal):
			return self.key != other.key
		return True
	def get_value_as_string( self ):
		'''
		converts byte representation of value property into a string
		'''
		try:
			return bytes.decode( self.value )
		except UnicodeError:
			return None
		
	@staticmethod
	def getSignalDescription(signal):
		for all_s in Signal.ALL_SIGNALS:
			if all_s == signal:
				return all_s.get_value_as_string()
		return ''

SIGNAL_HANDSHAKE = Signal( 0, 'Handshake' )
SIGNAL_EXIT =      Signal( 1, 'Shutdown' )
SIGNAL_EVALUATE =  Signal( 2, 'Evaluate' )
SIGNAL_RESULT =    Signal( 3, 'RESULT' )
SIGNAL_PROCESS =   Signal( 4, 'PROCESS' )
SIGNAL_IDLE =      Signal( 5, 'IDLE' )
SIGNAL_IMAGE =     Signal( 6, 'BINARY' )
SIGNAL_SERVER_ALIVE = Signal( 7, 'SERVER ALIVE' )
SIGNAL_CLIENT_ALIVE = Signal( 8, 'CLIENT ALIVE' )

# DRC specific signals
SIGNAL_OPEN            = Signal( 10, 'open' )
SIGNAL_FAILURE         = Signal( 11, 'failure' )
SIGNAL_SUCCESS         = Signal( 12, 'success' )
SIGNAL_UNPAIR          = Signal( 13, 'unpair')
SIGNAL_START           = Signal( 14, 'start')
SIGNAL_CLOSE_TEMPLATE  = Signal( 15, 'close_template' )
SIGNAL_MEASURE         = Signal( 16, 'ms_list' )
SIGNAL_SAVE            = Signal( 17, 'save' )
SIGNAL_EXPORTEDFILE    = Signal( 18, 'ExportedFile' )
SIGNAL_REFXML          = Signal( 19, 'refxml' )
SIGNAL_REQUEST_PAIR    = Signal( 20, 'request' )
SIGNAL_ALIGNMENT_ITER  = Signal( 21, 'iter_ms' )
SIGNAL_RESTART         = Signal( 22, 'restart' )
SIGNAL_SINGLE_SIDE     = Signal( 23, 'single_side_eval' )
SIGNAL_DEINIT_SENSOR   = Signal( 24, 'deinit sensor' )
SIGNAL_OPEN_INIT       = Signal( 25, 'open and init')

SIGNAL_INLINE_PREPARE = Signal(30, 'prepare_exec')
SIGNAL_INLINE_DRC_MOVEDECISION = Signal(31, 'move_decision')
SIGNAL_INLINE_DRC_ABORT = Signal(32, 'abort')
SIGNAL_INLINE_DRC_SECONDARY_INST_DATA = Signal(33, 'secondary inst data')

SIGNAL_MULTIROBOT_INLINE_OPTIPREPARE = Signal(50, 'inline optimized start measure')
SIGNAL_MULTIROBOT_MEASUREMENTS = Signal(51, 'measurements')
SIGNAL_MULTIROBOT_CALIB_SERIES = Signal(52, 'calibration')
SIGNAL_MULTIROBOT_DONE = Signal(53, 'projectfinished')
SIGNAL_MULTIROBOT_EVAL = Signal(54, 'multieval')
SIGNAL_MULTIROBOT_MMT_FINISHED = Signal(55, 'multimmt_finished')
SIGNAL_MULTIROBOT_MMT_FAILED = Signal(56, 'multimmt_failed')
SIGNAL_MULTIROBOT_COMP_MMTS = Signal(57, 'compatible measurements')
SIGNAL_MULTIROBOT_INLINE_PRGID = Signal(58, 'inline robot program id')
SIGNAL_MULTIROBOT_MMT_STARTUP_DONE = Signal(59, 'multimmt startup done')
SIGNAL_MULTIROBOT_EVAL_TERMINATE = Signal(60, 'multieval terminate')
SIGNAL_MULTIROBOT_STATUS = Signal(61, 'inline robot status')

#Inline specific signals
SIGNAL_CONTROL_TEMPLATE =  Signal(100, 'Template')
SIGNAL_CONTROL_SERIAL =    Signal(101, 'Serial')
SIGNAL_CONTROL_START =     Signal(102, 'Start')
SIGNAL_CONTROL_RESULT =    Signal(103, 'Result')
SIGNAL_CONTROL_ASYNC_PID = Signal(104, 'PID')
SIGNAL_CONTROL_EXIT =      Signal(105, 'Exit')
SIGNAL_CONTROL_ERROR =     Signal(106, 'Error')
SIGNAL_CONTROL_WARNING =   Signal(107, 'Warning')
SIGNAL_CONTROL_MEASURING = Signal(108, 'Measuring')
SIGNAL_CONTROL_IDLE =      Signal(109, 'Idle')
SIGNAL_CONTROL_CLOSETEMPLATE =  Signal(110, 'CloseTemplate')
SIGNAL_CONTROL_DEINIT_SENSOR =  Signal(111, 'DeInitSensor')
SIGNAL_CONTROL_MOVE_HOME =  Signal(112, 'MoveHome')
SIGNAL_CONTROL_MOVE_POSITION =  Signal(113, 'MovePosition')
SIGNAL_CONTROL_CREATE_GOMSIC = Signal(114, 'GomSic')
SIGNAL_CONTROL_FORCE_CALIBRATION = Signal(115, 'ForceCalibration')
SIGNAL_CONTROL_FORCE_TRITOP = Signal(116, 'ForceTritop')
SIGNAL_CONTROL_ADDITION_INFO = Signal(117, 'Additional Info')
SIGNAL_CONTROL_ABORT = Signal(118, 'Abort')
SIGNAL_CONTROL_MLIST_TOTAL = Signal(119, 'Mlist total count')
SIGNAL_CONTROL_MLIST_CURRENT = Signal(120, 'Mlist current count')
SIGNAL_CONTROL_MLIST_POSITION = Signal(121, 'Mlist Position current')
SIGNAL_CONTROL_MLIST_POSITION_TOTAL = Signal(122, 'Mlist Position count')
SIGNAL_CONTROL_RESULT_NOT_NEEDED = Signal(123, 'Result not needed')
SIGNAL_CONTROL_MOVEMENT_FAULT_STATE = Signal(124, 'Fault state during movement')
SIGNAL_CONTROL_MOVE_DECISION_AFTER_FAULT = Signal(125, 'Move Decision after fault state')
SIGNAL_CONTROL_PHOTOGRAMMETRY_HARDWARE_NOT_AVAILABLE = Signal(126, 'Photogrammetry Hardware not available')
SIGNAL_CONTROL_EXECUTION_TIME = Signal(127, 'Execution time left')
SIGNAL_CONTROL_AVAILABLE_SUBPOSITIONS = Signal(128, 'Available sub positions')
SIGNAL_CONTROL_ADDITION_INFO_RAW = Signal(129, 'Additional Info Raw')
SIGNAL_CONTROL_MEASURE_USER_DATA = Signal(130, 'Measure User Data')
SIGNAL_CONTROL_SERIAL2 = Signal(131, 'Serial2')
SIGNAL_CONTROL_ADDITION_INFO_RAW2 = Signal(132, 'Additional Info Raw2')
SIGNAL_CONTROL_CALIBRATION_DONE = Signal(133, 'Calibration done')
SIGNAL_CONTROL_CALIBRATION_STARTED = Signal(134, 'Calibration started')
SIGNAL_CONTROL_PHOTOGRAMMETRY_DONE = Signal(135, 'Photogrammetry done')
SIGNAL_CONTROL_PHOTOGRAMMETRY_STARTED = Signal(136, 'Photogrammetry started')
SIGNAL_CONTROL_PHOTOGRAMMETRY_RECOMMENDED = Signal(137, 'Photogrammetry recommended')
SIGNAL_CONTROL_CALIBRATION_RECOMMENDED = Signal(138, 'Calibration recommended')
SIGNAL_CONTROL_TEMPERATURE = Signal(139, 'Temperature')

SIGNAL_OPEN_SOFTWARE_DRC = Signal( 200, 'open from software')

# Separator for sending lists of measurement series names
MLIST_SEPARATOR = '@@DRC@@@'


# Exception class for lost client connections
class ConnectionLost( Exception ):
	pass


def get_signal_key_from_result_signal( signal ):
	'''
	return signal key contained in given SUCCESS/FAILURE signal, else return None
	'''
	key = None
	if signal == SIGNAL_SUCCESS or signal == SIGNAL_FAILURE:
		values = signal.value.split( b'-', 1 )
		try:
			key = int( values[0] )
		except:
			pass
	return key


class RemoteTodos( Utils.GenericLogClass ):
	'''
	todo class, for keeping track of remote active tasks
	'''
	def __init__( self, logger ):
		Utils.GenericLogClass.__init__( self, logger )
		self.todos = []

	def clear( self ):
		self.todos = []

	def append_todo( self, signal, value=None ):
		'''
		append given signal as todo
		'''
		self.todos.append( ( signal, value ) )

	def finish( self, signal ):
		'''
		remove and return given signal (on success), if found
		'''
		if signal == SIGNAL_SUCCESS:
			id = int( signal.value )
			for i in range( len( self.todos ) ):
				if self.todos[i][0].key == id:
					self.log.info( 'finished job {}'.format( self.todos[i] ) )
					return self.todos.pop( i )
		return None

	def get_todo( self, signal, match_value=None ):
		'''
		remove and return todo matching the given SUCCESS/FAILURE signal.
		returns None if not found.
		optional "match_value" checks also the appended payload at the todo.
		'''
		if signal == SIGNAL_SUCCESS or signal == SIGNAL_FAILURE:
			values = signal.value.split( b'-', 1 )
			try:
				id = int( values[0] )
			except:
				# TODO this looks wrong
				if len(self.todos):
					return self.todos.pop(0)
				return None
			for i in range( len( self.todos ) ):
				if self.todos[i][0].key == id:
					if match_value is not None and self.todos[i][1] != match_value:
						continue
					return self.todos.pop( i )
		return None

	def get_todo_signal( self, signal ):
		'''
		remove and return todo containing the given signal, returns None if not found
		'''
		for i in range( len( self.todos ) ):
			if self.todos[i][0].key == signal.key:
				return self.todos.pop( i )
		return None

	def has_todo( self, signal ):
		'''
		check if given signal is already in the queue
		'''
		key = signal.key
		for i in range( len( self.todos ) ):
			if self.todos[i][0].key == key:
				return True
		return False


class ChatHandler( asynchat.async_chat, Utils.GenericLogClass ):
	'''
	overloaded async_chat class
	doesnt split based on terminator, instead it reads the given pkt size
	will send/receive whole packets in blocking mode
	'''
	parent = None
	async_todo = None
	handshaked = False
	async_results = None
	idle = True
	pid = None
	alive_ts = None

	def __init__( self, logger, sock, sctmap, parent ):
		asynchat.async_chat.__init__( self, sock, sctmap )
		Utils.GenericLogClass.__init__( self, logger )
		self.parent = parent
		self.async_todo = list()
		self.async_results = list()
		self.idle = True
		self.pid = None
		self.handshaked = False
		self.alive_ts = None

	def handle_read ( self ):
		'''
		patched buildin function
		reads the size definition and splits based on that
		recveives on pkt in blocking mode
		'''
		try:
			data = self.recv ( 10 )
		except socket.error as why:
			self.handle_error()
			return

		if isinstance( data, str ) and self.use_encoding:
			data = bytes( str, self.encoding )
		self.ac_in_buffer = self.ac_in_buffer + data

		unpack = xdrlib.Unpacker( b'' )
		while True:
			if len( self.ac_in_buffer ) > 7:
				unpack.reset( self.ac_in_buffer[:8] )
				key = unpack.unpack_int()
				size = unpack.unpack_uint()
				size = ( ( size + 3 ) // 4 ) * 4  # padded size
				size += 8
				self.socket.setblocking( 1 )
				while len( self.ac_in_buffer ) < size:
					try:
						data = self.recv ( size - len( self.ac_in_buffer ) )
					except socket.error as why:
						self.handle_error()
						return
					self.ac_in_buffer += data
				self.socket.setblocking( 0 )
				unpack.reset( self.ac_in_buffer[:size] )
				key = unpack.unpack_int()
				value = unpack.unpack_bytes()
				self.collect_incoming_data( [key, value] )
				self.ac_in_buffer = self.ac_in_buffer[size:]
			else:
				break
		del unpack

	def initiate_send( self ):
		'''
		patched buildin function
		will send till queue is empty
		'''
		while self.producer_fifo and self.connected:
			first = self.producer_fifo[0]
			# handle empty string/buffer or None entry
			if not first:
				del self.producer_fifo[0]
				if first is None:
					self.handle_close()
					return

			# handle classic producer behavior
			obs = self.ac_out_buffer_size
			try:
				data = first[:obs]
			except TypeError:
				data = first.more()
				if data:
					self.producer_fifo.appendleft( data )
				else:
					del self.producer_fifo[0]
				continue

			if isinstance( data, str ) and self.use_encoding:
				data = bytes( data, self.encoding )

			# send the data
			try:
				num_sent = self.send( data )
			except socket.error:
				self.handle_error()
				return

			if num_sent:
				if num_sent < len( data ) or obs < len( first ):
					self.producer_fifo[0] = first[num_sent:]
				else:
					del self.producer_fifo[0]
			# we tried to send some actual data
			# patched: we send everything
			# return

	def found_terminator( self ):
		'''
		no need for a terminator
		'''
		pass

	def collect_incoming_data( self, data ):
		'''
		buffer incoming signals
		'''
		self.async_todo.append( Signal( *data ) )


	def process_signals( self ):
		'''
		collect signals from the buffer
		default server implementation
		'''
		got_signal = False
		while len( self.async_todo ) > 0:
			todo = self.async_todo.pop( 0 )
			self.log.debug( 'got Signal {}'.format( todo ) )
			got_signal = True
			if todo == SIGNAL_EXIT:
				pass
			elif todo == SIGNAL_EVALUATE:
				pass
			elif todo == SIGNAL_HANDSHAKE:
				self.pid = int( todo.value )
				ownpid = os.getpid()
				self.log.debug( 'Sending handshake from {} to {}'.format( ownpid, self.pid ) )
				self.log.debug( '  local pids os {} / gom {}'.format( os.getpid(), gom.getpid() ) )
				self.push( Signal( SIGNAL_HANDSHAKE, str( ownpid ) ).encode() )
				self.handshaked = True
				self.alive_ts = time.time()
				if Globals.SETTINGS is not None and Globals.SETTINGS.Inline and Globals.CONTROL_INSTANCE is not None:
					# pass through the software pid of async instance
					Globals.CONTROL_INSTANCE.send_signal( Signal( SIGNAL_CONTROL_ASYNC_PID, str( self.pid ) ) )
			elif todo == SIGNAL_SERVER_ALIVE:
				self.push( Signal( SIGNAL_SERVER_ALIVE ).encode() )
			elif todo == SIGNAL_CLIENT_ALIVE:
				self.alive_ts = time.time()
			elif todo == SIGNAL_IDLE:
				self.idle = True
			else:
				self.idle = False
				self.async_results.append( todo )
		return got_signal

	@property
	def LastAsyncResults( self ):
		'''
		interface property for getting the received signals
		'''
		while len( self.async_results ) > 0:
			yield self.async_results.pop( 0 )

class ChatHandlerClient( ChatHandler ):
	'''
	client implementation of the socket handler class
	'''
	def process_signals( self ):
		'''
		collect signals from the buffer
		'''
		anysignals = False
		while len( self.async_todo ) > 0:
			todo = self.async_todo.pop( 0 )
			self.log.debug( 'got Signal {}'.format( todo ) )
			if todo == SIGNAL_EXIT:
				raise gom.BreakError
			elif todo == SIGNAL_HANDSHAKE:
				self.pid = int( todo.value )
				self.log.debug( 'parentpid ' + str( self.pid ) )
				self.handshaked = True
				self.alive_ts = time.time()
			elif todo == SIGNAL_SERVER_ALIVE:
				self.alive_ts = time.time()
			elif todo == SIGNAL_CLIENT_ALIVE:
				self.push( Signal( SIGNAL_CLIENT_ALIVE ).encode() )
			else:
				self.async_results.append( todo )
			anysignals = True
		return anysignals

class ClientRefList( Utils.GenericLogClass ):
	'''
	started client holder class
	'''
	client_list = None

	# scriptname default for backward compatibility
	def __init__( self, logger, scriptname='gom.script.userscript.KioskInterface__ClientStart' ):
		'''
		initialize list and start defined number of clients
		'''
		self.client_list = list()
		self.scriptname = scriptname
		Utils.GenericLogClass.__init__( self, logger )
		for _i in range( Globals.SETTINGS.NumberOfClients ):
			self.client_list.append( self.start_sw() )

	def __len__( self ):
		return len( self.client_list )
	def append( self, client ):
		if Globals.SETTINGS.Inline:
			Globals.CONTROL_INSTANCE.send_signal( Signal( SIGNAL_CONTROL_ASYNC_PID, str( client.pid ) ) )
		self.client_list.append( client )
	def remove( self, client ):
		self.client_list.remove( client )

	def poll( self ):
		'''
		check client instances and restart killed clients
		'''
		new_sw = False
		for client in self.client_list:
			if client.poll() is not None:
				new_sw = True
				self.log.error( 'No Client instance, starting new' )
				this_client_index = self.client_list.index( client )
				self.client_list[this_client_index] = self.start_sw()
				if Globals.SETTINGS.Inline:
					Globals.CONTROL_INSTANCE.send_signal(
						Signal( SIGNAL_CONTROL_ASYNC_PID, str( self.client_list[this_client_index].pid ) ) )
		return new_sw

	def all_killed( self ):
		'''
		test if all clients got killed
		'''
		for client in self.client_list:
			if client.poll() is None:
				return False
		return True

	def start_sw( self ):
		'''
		start client instances
		'''
		if Globals.SETTINGS.Inline:
			import multiprocessing
			import collections
			import ctypes
			import gom_windows_utils
			import gom_atos_log_filter
			sw_pid = multiprocessing.Value(ctypes.c_size_t,0)
			watcher = gom_atos_log_filter.startInstance(
				self.scriptname + ' ()', None, sw_pid, 'eval_inline' )
			while sw_pid.value == 0:
				gom.script.sys.delay_script( time=1 )
			Globals.CONTROL_INSTANCE.send_signal( Signal( SIGNAL_CONTROL_ASYNC_PID, str( watcher.pid ) ) )
			class Client:
				def __init__(self, pid):
					self.pid = pid
				def poll(self):
					if gom_windows_utils.isPidStillActive(self.pid):
						return None
					return True
			return Client(sw_pid.value)

		env = os.environ
		# remote dongle would grab TWO vmr licenses
		sw_dir = gom.app.get ( 'software_directory' )
		args = [sw_dir + '/bin/GOMSoftware.exe', '-kiosk',
			'-eval', self.scriptname + ' ()', '-nosplash', '-minimized']
		process = subprocess.Popen( args, env = env )
		gom.script.sys.delay_script( time = 1 )
		return process

	start_atos = start_sw # old name compatibility


class PLCConnection:
	def __init__(self, logger, netID='172.17.61.55.1.1', port=851):
		Utils.GenericLogClass.__init__( self, logger )
		self.netID = netID
		self.port = port
		self.connection = None

	def connect(self):
		if not PLCfunctions.isADSLoaded():
			self.connection = None
			return
		try:
			port = PLCfunctions.adsPortOpen()
			self.connection = PLCfunctions.adsGetLocalAddress()
			self.connection.setAdr(self.netID)
			self.connection.setPort(self.port)
		except Exception as e:
			self.log.exception('Failed to connect with PLC: {}'.format(e))
			self.connection = None

	def disconnect(self):
		if self.connection is not None:
			PLCfunctions.adsPortClose()

	def on_measuring_done(self):
		if self.connection is None:
			return
		bIdle = PLCVar('bKioskIdle', plc_const.PLCTYPE_BOOL)
		try:
			bIdle.getHandle(self.connection)
		except Exception as e:
			Globals.LOGGER.exception("failed to get handle {} {}".format(bIdle.name,e))
			return
		try:
			bIdle.write(True)
		except Exception as e:
			self.log.exception('Failed to write {} : {}'.format(bIdle.name,e))
		bIdle.releaseHandle(self.connection)

class IOExtension:	
	_ioExtActiveDevices = -1
	_secondary_single_side_done = None
	_batchscan_done = False
	_final_template = True
	@classmethod
	def store_active_devices(cl):
		try:
			count=len(gom.app.project.measuring_setups[0].get ('working_area.devices'))
		except:
			count=0
		if cl._ioExtActiveDevices == -1:
			cl._ioExtActiveDevices = count
		elif count > 0 and count < 3:
			cl._ioExtActiveDevices = count
			

	@classmethod
	def io_extension_measurement_done(cl, log, secondary_side=False):
		if not Globals.SETTINGS.IOExtension:
			return
		if Globals.SETTINGS.BatchScan:
			if cl._secondary_single_side_done == False and not secondary_side:
				cl._batchscan_done=True
				return
			if secondary_side and not cl._batchscan_done:
				return
			if not cl._final_template:
				return
				
		# do not signal rotation table in series7/8
		if cl._ioExtActiveDevices > 0 and cl._ioExtActiveDevices < 3:
			plc = PLCConnection(log, Globals.SETTINGS.IOExtension_NetID, Globals.SETTINGS.IOExtension_Port)
			plc.connect()
			plc.on_measuring_done()
			plc.disconnect()
		cl._secondary_single_side_done = None
		cl._batchscan_done = False
		cl._ioExtActiveDevices = -1
		cl._final_template = True
	
	@classmethod
	def final_run(cl, value):
		cl._final_template = value
	@classmethod
	def multipart_single_side_started(cl):
		cl._secondary_single_side_done = False
	@classmethod
	def multipart_single_side_done(cl, log):
		cl._secondary_single_side_done = True
		cl.io_extension_measurement_done(log, True)
		
		

class PLCVar:
	def __init__(self, name, type):
		self.name = 'GOM_KIOSK.'+name
		self._type = type
		self._handle = None
		self._connection = None
		
	def getHandle(self, adr):
		self._handle = PLCfunctions.adsGetHandle(adr, self.name)
		self._connection = adr
	
	def releaseHandle(self, adr):
		if self._handle is not None:
			try:
				PLCfunctions.adsReleaseHandle(adr, self._handle)
			except:
				pass
		self._handle = None
		self._connection = None
		
	def write(self, value):
		if self._connection is None:
			return
		if self._handle is None:
			raise Exception("Tried to write variable with invalid handle")
		Globals.LOGGER.debug('write {} : {}'.format(self.name, value))
		PLCfunctions.adsSyncWriteByHandle(self._connection, self._handle, value, self._type)


class IoTConnection:
	def __init__(self, ip, port):
		self.ip = ip
		self.port = port
	
	def _pack_serialized_json(self, json_object):
		data = json_object.encode(encoding='utf-8')
		length = len(data)
		length = length.to_bytes(8, byteorder='big')
		return length + data
	
	def send(self, template=None, execution_time=None, exposure_time_calib=None, calib_time=None):
		data={}
		if template is not None:
			data["current_used_template"] = template
		if execution_time is not None:
			data["estimated_execution_time"] = execution_time
		if exposure_time_calib is not None:
			data["exposure_time_first_calibration_position"] = exposure_time_calib
		if calib_time is not None:
			data["calibration_timestamp"] = calib_time
		msg = self._pack_serialized_json(json.dumps(data))
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		sock.sendto(msg, (self.ip, self.port))
		sock.close()
		
	def getCalibrationInformation(self):
		try:
			date=gom.app.sys_calibration_date
			date=datetime.datetime.strptime(date, '%a %b %d %H:%M:%S %Y')
			date=date.timestamp()
		except:
			date=None
		try:
			exp_time = gom.app.sys_calibration_first_exposure_time
		except:
			exp_time = None
		return date, exp_time