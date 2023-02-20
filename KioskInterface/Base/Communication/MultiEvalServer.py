# -*- coding: utf-8 -*-
# Script: Multirobot Evaluation Server Communication Class
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

import asyncore
import pickle
import socket
import sys

from ..Misc import Utils, Globals
from . import Communicate


class CommunicationServer( asyncore.dispatcher, Utils.GenericLogClass ):
	'''
	basic socket server implementation
	'''
	parent = None
	handler = None
	sctmap = None
	remote_todos = None

	def __init__( self, logger, parent, host, port, sctmap ):
		'''
		initialize function creates the socket
		'''
		Utils.GenericLogClass.__init__( self, logger )
		asyncore.dispatcher.__init__( self, map = sctmap )
		self.create_socket( socket.AF_INET, socket.SOCK_STREAM )
		try:
			self.bind( ( host, port ) )
		except Exception as e:
			self.log.error( 'failed to bind, using REUSEADDR {}'.format( e ) )
			self.set_reuse_addr()
			self.bind( ( host, port ) )
		self.listen( 1 )
		self.log.debug( 'Eval Server listening {}/{}'.format( host, port ) )
		self.sctmap = sctmap
		self.handlers = []
		# TODO a bit late, but this should probably move to self.parent
		#   easier to handle connected/disconnected state there
		#   and also to make the connection to the eval task
		#   use three callbacks (connect/lost/handshake)
		self.handler_states = {}
		self.handler_swpids = {}
		self.handler_addrs = {}
		self.terminated_clients = []
		self.parent = parent
		self.remote_todos = Communicate.RemoteTodos( self.baselog )

	# connection (handler) identification and properties
	def handler_id( self, handler ):
		return (handler.addr[0], handler.pid)
	def handler_id_by_addr( self, _ip, pid ):
		return (_ip, pid)
	def id_is_local( self, id_ ):
		return id_[0].startswith( '127.' )
	def handler_ip( self, id_ ):
		return id_[0]

	def log_info( self, message, logtype = 'info' ):
		'''
		log misc messages from the base dispatcher class
		'''
		self.log.info( logtype + ' ' + message )
	def handle_close( self ):
		'''
		called during close events
		'''
		self.remote_todos.clear()
		self.log.debug( 'close' )

	def handle_accept( self ):
		'''
		called when a new client is connecting, creates a handler class
		'''
		pair = self.accept()
		if pair is None:
			return
		else:
			sock, addr = pair
			self.log.info( 'Incoming connection from %s' % repr( addr ) )
			self.handlers.append( Communicate.ChatHandler( self.baselog, sock, self.sctmap, self ) )

	def process_signals( self, timeout=0 ):
		'''
		check for new signals and processes them, greps all signals currently in the network stream
		'''
		got_signal = False
		asyncore.loop( timeout=timeout, map=self.sctmap, count=1 )
		for i in range( len( self.handlers ) - 1, -1, -1 ):
			_id = self.handler_id( self.handlers[i] )
			if _id in self.terminated_clients:
				self.terminated_clients.remove( _id )
				self.log.info( 'Force close connection to {}'.format( _id ) )
				self.handlers[i].close()
				if _id in self.handler_states:
					del self.handler_states[_id]
					del self.handler_swpids[_id]
					del self.handler_addrs[_id]
				self.handlers.pop( i )
			elif not self.handlers[i].connected:
				# TODO Lost connection needs to forwarded to parent for handling
				#   also keep information in case the client reconnects
				#   the parent will investigate via the inline wrapper if the client is still alive
				self.log.info( 'Lost Connection to {}'.format( _id ) )
				if _id in self.handler_states:
					del self.handler_states[_id]
					del self.handler_swpids[_id]
					del self.handler_addrs[_id]
				self.handlers.pop( i )

		self.terminated_clients = []

		for client in self.handlers:
			signal = client.process_signals()
			# Enter new eval client into status maps
			_id = self.handler_id( client )
			if client.handshaked and _id not in self.handler_states:
				self.log.debug( 'New eval client addr {} local? {} id {}'.format(
					client.addr, client.addr[0].startswith( '127.' ), _id ) )	
#				print('new client addr', client.addr)
#				print('local?', client.addr[0].startswith('127.'))
#				print('_id', _id, client.pid, client.addr)
				self.handler_states[_id] = False
				self.handler_swpids[_id] = None
				self.handler_addrs[_id] = client.addr[0]
			if signal:
				got_signal = True

		return got_signal

	def pop_results( self ):
		'''
		grabs all results from all handlers
		'''
		result = []
		for client in self.handlers:
			for res in client.LastAsyncResults:
#				print('MultiEvalServer.pop_results signal from pid', client.pid, res.key)
				if res.key == Communicate.SIGNAL_CONTROL_IDLE.key:
					data = pickle.loads( res.value )
					state = data['idle']
					self.log.debug( 'idle {} received from client pid {} with sw pid {}'.format(
						state, client.pid, data['swpid'] ) )
					if state == 1:
						self.parent.logOverview( 'Eval End {}: -'.format( data['swpid'] ) )
					if 'meminfo_py' in data.keys() and 'meminfo_gom' in data.keys():
						self.parent.logOverview( 'Eval Memory Info {}: Memory PY {} / GOM {}'.format(
							data['swpid'], data['meminfo_py'], data['meminfo_gom'] ) )

					_id = self.handler_id( client )
					self.handler_states[_id] = True if state == 1 else False
					self.handler_swpids[_id] = data['swpid']
					self.handler_addrs[_id] = client.addr[0]
					self.log.debug(
						'New idle state {} client addr {} local? {} id {}'.format(
							state == 1, client.addr,
							self.id_is_local( _id ), _id ) )
#					print('handshake client addr', client.addr)
#					print('local?', client.addr[0].startswith('127.'))
#					print('_id', _id, client.pid, client.addr, data['swpid'])
				else:
					result.append( (res, self.handler_id( client ) ) )
		return result

	@property
	def Handshaked( self ):
		'''
		are all clients fully connected
		'''
		handshaked = False
		for client in self.handlers:
			if not client.handshaked:
				return False
			handshaked = True
		return handshaked

	def wait_for_first_connection( self ):
		'''
		waits for ~40s that all started clients are fully connected
		on failure exit program
		'''
		retries = 0
		while retries < 20:
			Globals.ASYNC_CLIENTS.poll()
			self.process_signals( 5 )
			if self.Handshaked:
				self.log.info( 'handshaked' )
				return True
			retries += 1
		self.log.error( 'MultiEvalServer failed to init, exiting' )
		Globals.DIALOGS.show_errormsg( Globals.LOCALIZATION.msg_async_failure_title,
									Globals.LOCALIZATION.msg_async_failure_communicate_client,
									sic_path = Globals.SETTINGS.SavePath, retry_enabled = False )
		sys.exit( 0 )

	def send_exit( self ):
		'''
		called during exiting, sends to all clients the exit signal
		'''
		return self.send_signal( Communicate.SIGNAL_EXIT )

	def close_all_handlers( self ):
		'''
		close all connections
		'''
		for client in self.handlers:
			client.close()
		self.close()

	def close_handler( self, _id ):
		del_handler = None
		for handler in self.handlers:
			if self.handler_id( handler ) == _id:
			#if handler.pid in self.handler_swpids and sw_pid == self.handler_swpids[handler.pid]:
			#if sw_pid == handler.pid:
				del_handler = handler
				break

		if del_handler is None:
			self.log.warning( 'Close handler {} - not found'.format( _id ) )
		else:
			del_handler.close()


	def send_signal( self, signal ):
		'''
		sends a signal to all clients
		'''
		if len( self.handlers ) == 0:
			return False
		self.log.debug( 'Sending: {}'.format( signal ) )
		self.socket.setblocking( 1 )  # send in blocking mode, so the complete signal gets send
		for client in self.handlers:
			client.push( signal.encode() )
		self.process_signals()
		self.socket.setblocking( 0 )
		return True

# TODO reactivate for teach mode?
#	def send_open_template( self, template_name, template_config ):
#		signal = Communicate.Signal( Communicate.SIGNAL_MULTIROBOT_EVAL,
#			pickle.dumps( {'template': template_name, 'template_config': template_config} ) )
#		for client in self.handlers:
##			if client.idle:
#			client.push( signal.encode() )
#			self.remote_todos.append_todo( signal )

	def send_multi_eval( self, _id, template_name, template_cfg, timestamp, refxml,
						 temperature, keywords, additional_kws, mseries, robot_program_id ):
		signal = Communicate.Signal( Communicate.SIGNAL_MULTIROBOT_EVAL,
			pickle.dumps( {
				'template': template_name, 'template_cfg': template_cfg,
				'timestamp': timestamp, 'refxml': refxml, 'temperature': temperature,
				'keywords': keywords, 'additional_kws': additional_kws,
				'mseries': mseries, 'robot_program_id': robot_program_id} ) )

		found = False
		for client in self.handlers:
			if _id == self.handler_id( client ): # == client.pid:
				found = True
				self.log.debug( 'Sending to eval client {}: {}'.format( _id, signal ) )
				client.push( signal.encode() )
				self.remote_todos.append_todo( signal, _id )
				self.parent.logOverview( 'Eval Start {}: Timestamp {}'.format(
					self.handler_swpids[_id], timestamp ) )
				break

		if not found:
			self.log.error( 'Eval client with id {} not found'.format( _id ) )
			#raise ValueError( 'Eval client with pid {} not found'.format( _id ) )

	def send_mmt_finished( self, _id, id, mseries, robot_program_id, success ):
		signal = Communicate.Signal( Communicate.SIGNAL_MULTIROBOT_MMT_FINISHED,
			pickle.dumps( {'id': id, 'mseries': mseries, 'robot_program_id': robot_program_id,
				'success': success} ) )
		self.log.debug( 'Sending to eval client {}: {}'.format( _id, signal ) )

		found = False
		for client in self.handlers:
			if _id == self.handler_id( client ):
				found = True
				client.push( signal.encode() )
				self.remote_todos.append_todo( signal, _id )
				break

		if not found:
			self.log.error( 'Eval client with pid {} not found'.format( _id ) )
			#raise ValueError( 'Eval client with pid {} not found'.format( _id ) )

	def send_mmt_failed( self, _id ):
		signal = Communicate.Signal( Communicate.SIGNAL_MULTIROBOT_MMT_FAILED )
		self.log.debug( 'Sending to eval client {}: {}'.format( _id, signal ) )
		found = False
		for client in self.handlers:
			if _id == self.handler_id( client ):
				found = True
				client.push( signal.encode() )
				break

		if not found:
			self.log.error( 'Eval client with pid {} not found'.format( _id ) )
			#raise ValueError( 'Eval client with pid {} not found'.format( _id ) )

	def send_eval_terminate( self, _id ):
		signal = Communicate.Signal( Communicate.SIGNAL_MULTIROBOT_EVAL_TERMINATE )
		self.log.debug( 'Sending to eval client {}: {}'.format( _id, signal ) )
		found = False
		for client in self.handlers:
			if _id == self.handler_id( client ):
				found = True
				client.push( signal.encode() )
				self.terminated_clients.append( _id )
				break

		if not found:
			self.log.error( 'Eval client with id {} not found'.format( _id ) )
			#raise ValueError( 'Eval client with id {} not found'.format( _id ) )

		return found