# -*- coding: utf-8 -*-
# Script: barcode communication
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

# GOM-Script-Version: 8.0
#
# ChangeLog:

import re
import serial
import codecs
import csv
import os

from . import Globals, Utils, LogClass

class BarCode( Utils.GenericLogClass ):
	'''
	Communication class for a bar code scanner
	uses serial port communication
	'''
	def __init__( self, logger, com_port, record_suffix = None ):
		'''
		initialize and register instance in the global timer class
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self._buffer = ''
		self._codes = []
		self._comport = com_port
		self._record_suffix = record_suffix
		if self._record_suffix is not None and not len( self._record_suffix ):
			self._record_suffix = None
		self._serial = None
		Globals.TIMER.registerHandler( self._loop )
		if self._comport is not None:
			self._connect()

	@property
	def connected( self ):
		return self._serial is not None

	def _connect( self ):
		'''
		open serial port
		'''
		if self._comport is not None:
			try:
				# For compatibility reasons: The legacy python interpreter was shipped with an
				# outdated pyserial module which requires the comport to be numeric instead 
				# of, e.g., 'COM3'
				comport = self._comport
				if not hasattr (serial, '__version__') or int (float (serial.__version__)) < 3:
					if isinstance (comport, str):
						comport = int (comport[3:]) - 1
				else:
					if isinstance (comport, int):
						comport = 'com{}'.format (comport + 1)
				
				self._serial = serial.Serial( comport, 9600, timeout = 0,
						parity = serial.PARITY_NONE, rtscts = 0 )
			except Exception as e:
				self.log.error( 'Failed to connect with BarCodeScanner: {}'.format( e ) )
				self._serial = None

	def _loop( self, value ):
		'''
		timer loop gets called via the global timer
		reads from serial port and splits the codes
		'''
		if self._serial is None:
			return
		try:
			binary = self._serial.read( 100 )
			if len( binary ):
				self._buffer += binary.decode( 'ISO-8859-1' )
				self._split_codes()
		except Exception as e:
			self.log.exception( 'Failed to read from BarCodeScanner: {}'.format( e ) )


	def _split_codes( self ):
		'''
		splits codes from buffer based on suffix
		'''
		if self._record_suffix is None:
			return
		if self._buffer.count( self._record_suffix ):
			codes = self._buffer.split( self._record_suffix )
			self._codes += codes[:-1]
			if len( codes[-1] ):  # if last split is not empty the last suffix is missing
				self._buffer = codes[-1]
			else:
				self._buffer = ''

	def __del__( self ):
		try:
			self.close()
		except:
			pass

	def close( self ):
		'''
		unregister handler and close connection
		'''
		if self._serial is not None:
			Globals.TIMER.unregisterHandler( self._loop )
			self._serial.close()
			self._serial = None

	def set_comport( self, value ):
		'''
		set comport and reconnect
		'''
		self._comport = value
		if self._serial is not None:
			self._serial.close()
			self.clear_buffer()
			self._codes = []
		self._connect()

	def set_delimiter( self, value ):
		'''
		set new delimiter
		'''
		self._record_suffix = value
		self._split_codes()

	def pop_codes( self ):
		'''
		returns and clears codes
		'''
		codes = self._codes
		self._codes = []
		return codes

	def get_buffer( self ):
		'''
		return current buffer
		'''
		return self._buffer

	def clear_buffer( self ):
		'''
		clear current buffer
		'''
		self._buffer = ''

	@staticmethod
	def getAllPorts():
		'''
		return list of tuples (port (int), description, id) of all active comports
		'''
		import serial.tools.list_ports as list_ports
		iterator = sorted( list_ports.comports() )
		# list them
		comports = []
		for port, desc, hwid in iterator:
			comports.append( ( int( port[3:] ) - 1, desc, hwid ) )
		return comports

	@staticmethod
	def initialize( com_port, record_suffix, silent = True ):
		'''
		helper function to create a BarCode class outside of the KioskInterface
		in combination with the TemplateDefinition class an example code is the following

		from KioskInterface.Base.Misc.BarCode import BarCode, CodeToTemplateAssignments

		print( BarCode.getAllPorts() ) # list all found COMports with description
		bar = BarCode.initialize (4,'\r\n') # connect to COM5 and use \r\n as delimiter between codes

		# initialize
		template_assignments = CodeToTemplateAssignments.initialize('TemplateBarCodeAssignment.csv')

		while True:
			gom.script.sys.delay_script(time=1)
			codes = bar.pop_codes() # get all codes
			if len(codes):
				code = codes[-1] # only analyze the last code
				print('filter for code {} : {}'.format(code, template_assignments.findMatching(code)))
		'''
		global_logger = LogClass.Logger()
		if not silent:
			global_logger.create_console_streamhandler()
		if Globals.TIMER is None:
			Utils.GlobalTimer.registerInstance( global_logger )
		return BarCode( global_logger, com_port, record_suffix )



class TemplateMatchDef( object ):
	'''
	container per csv line for regex barcode to regex template filter
	'''
	def __init__( self, code, filters ):
		self._code = code
		self._filters = [f for f in filters if len( f )]
		self._re = re.compile( self._code )

	@property
	def code( self ):
		'''
		get method for plain text bar code regex
		'''
		return self._code

	@property
	def filters( self ):
		'''
		get method for plain text template filters
		'''
		return self._filters

	def match( self, code ):
		'''
		returns True if the given BarCode matches the regex
		'''
		result = self._re.match( code )
		if result is None:
			return False
		if result.end() != len( code ):  # no exact match
			return False
		return True


class CodeToTemplateAssignments( Utils.GenericLogClass ):
	'''
	class for the KioskInterface_TemplateBarCodeAssignment.csv
	to generate project template filters based on barcodes
	'''
	def __init__( self, logger, filename ):
		'''
		initialize with given logger and filename
		'''
		Utils.GenericLogClass.__init__( self, logger )
		self._template_defs = []
		self._last_mod_date = 0
		self._filename = filename
		self._parse_csv()

	@property
	def templateDefinitions( self ):
		'''
		returns list of TemplateMatchDef instances
		'''
		return self._template_defs

	def findMatching( self, code ):
		'''
		returns the template filters of the first matching barcode regex of given barcode
		'''
		try:
			if os.path.getmtime( self._filename ) != self._last_mod_date:
				self.log.debug( 'Modification date differs rereading template def' )
				self._parse_csv()
		except:
			pass
		for template in self._template_defs:
			if ( template.match( code ) ):
				return template.filters
		return None

	def _parse_csv( self ):
		'''
		parse csv file
		'''
		self._template_defs = []
		if not os.path.exists( self._filename ):
			self.log.debug( 'file not found {}'.format( self._filename ) )
			return
		try:
			with codecs.open( self._filename, 'r', 'utf-8' ) as f:
				csv.register_dialect( 'template_def', delimiter = ';', quoting = csv.QUOTE_NONE, skipinitialspace = True )
				csvparse = csv.reader( f, dialect = 'template_def' )
				try:
					for row in csvparse:
						for index in range( len( row ) ):
							row[index] = row[index].strip().strip( '"' ).strip()
						if not len( row ):
							continue
						if row[0].startswith( '#' ):
							continue
						all_empty = not any( len( r ) for r in row )
						if all_empty:
							continue
						if len( row ) < 2:
							continue
						self._template_defs.append( TemplateMatchDef( row[0], row[1:] ) )
				except Exception as e:
					self.log.exception( 'failed to parse: {}: {}'.format( csvparse.line_num, e ) )
			self._last_mod_date = os.path.getmtime( self._filename )
		except Exception as e:
			self.log.exception( 'failed to read template definition file {}: {}'.format( self._filename, e ) )
		self.log.debug( 'CSV templates: \n{}\n'.format( '\n'.join( '{} : {}'.format( t.code, t.filters ) for t in self._template_defs ) ) )

	@staticmethod
	def initialize( filename, silent = True ):
		'''
		helper function to create instance outside of the KioskInterface
		see BarCode.initialize() for an example of usage
		'''
		global_logger = LogClass.Logger()
		if not silent:
			global_logger.create_console_streamhandler()
		return CodeToTemplateAssignments( global_logger, filename )

