# -*- coding: utf-8 -*-
# Script: Async Server Communication Class
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

import asyncore
import socket
import gom
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
		self.sctmap = sctmap
		self.handlers = list()
		self.parent = parent
		self.AllowOneOnly = False

	def log_info( self, message, logtype = 'info' ):
		'''
		log misc messages from the base dispatcher class
		'''
		self.log.info( logtype + ' ' + message )
	def handle_connect( self ):
		'''
		called during connection events
		'''
		self.log.debug( 'connecting' )
	def handle_close( self ):
		'''
		called during close events
		'''
		self.log.debug( 'close' )

	def clear_alive( self ):
		for client in self.handlers:
			client.alive_ts = None

	def handle_accept( self ):
		'''
		called when a new client is connecting, creates a handler class
		'''
		pair = self.accept()
		if pair is None:
			return
		else:
			sock, addr = pair
			if self.AllowOneOnly and len(self.handlers) >= 1:
				sock.close()
				self.log.info('disallowing connection, already connected with a instance')
				return
			self.log.info( 'Incoming connection from %s' % repr( addr ) )
			self.handlers.append( Communicate.ChatHandler( self.baselog, sock, self.sctmap, self ) )

	def process_signals( self, timeout = 0.1 ):
		'''
		check for new signals and processes them, greps all signals currently in the network stream
		'''
		got_signal = False
		asyncore.loop( timeout = timeout, map = self.sctmap, count = 1 )
		for i in range( len( self.handlers ) - 1, -1, -1 ):
			if not self.handlers[i].connected:
				self.log.info('Lost Connection to {}'.format(self.handlers[i].addr))
				self.handlers.pop( i )
		for client in self.handlers:
			signal = client.process_signals()
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
				result.append( res )
		return result

	@property
	def Handshaked( self ):
		'''
		are all clients fully connected
		'''
		handshaked = False
		if not self.AllowOneOnly:
			try: #  global var is not everywhere defined
				if len( self.handlers ) < len( Globals.ASYNC_CLIENTS ):
					return False
			except:
				pass
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
		self.log.error( 'AsyncServer failed to init, exiting' )
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

	def send_signal( self, signal ):
		'''
		sends a signal to all clients
		'''
		if len( self.handlers ) == 0:
			return False
		self.log.debug('sending: {}'.format(signal))
		self.socket.setblocking( 1 )  # send in blocking mode, so the complete signal gets send
		for client in self.handlers:
			client.push( signal.encode() )
		self.socket.setblocking( 0 )
		return True

	def send_evaluateproject( self, name, force_instance = None ):
		'''
		send a evaluate signal for the given projectname to the first non idle client instance
		'''
		if len( self.handlers ) == 0:
			return False
		send = False
		if force_instance is not None:
			self.log.info( 'force evaluation for client no {} project: {}'.format( force_instance, name ) )
			self.handlers[force_instance].push( Communicate.Signal( Communicate.SIGNAL_EVALUATE, name ).encode() )
		else:
			self.log.info( 'sending evaluation project {}'.format( name ) )
			i = 0
			for client in self.handlers:
				if client.idle:
					client.push( Communicate.Signal( Communicate.SIGNAL_EVALUATE, name ).encode() )
					send = True
					self.log.info( 'send to ' + str( i ) )
					break
				i += 1
			if not send:
				self.log.info( 'all clients busy sending to last' )
				self.handlers[-1].push( Communicate.Signal( Communicate.SIGNAL_EVALUATE, name ).encode() )
		self.process_signals()
		return True

