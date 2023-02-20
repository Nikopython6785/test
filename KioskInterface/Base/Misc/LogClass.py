# -*- coding: utf-8 -*-
# Script: Logging class wrapper
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


import logging
import io
import os, sys
import traceback, linecache

class SrcFile( object ):
	'''
	Hide the Logger wrapper class from the traceback
	'''
	src = []
	def __init__( self ):
		self.src = [logging._srcfile, self.__get_filename()]
		logging._srcfile = self
	def __get_filename( self ):
		if __file__[-4:].lower() in ['.pyc', '.pyo']:
			srcfile = __file__[:-4] + '.py'
		else:
			srcfile = __file__
		srcfile = os.path.normcase( srcfile )
		return str( srcfile )
	def __eq__( self, other ):
		return other in self.src

SrcFile()

def formatException( self, ei ):
	"""
	Format and return the specified exception information as a string.

	This default implementation just uses
	traceback.print_exception()
	"""
	sio = io.StringIO()
	traceback.print_exception( ei[0], ei[1], ei[2], None, sio )
	s = sio.getvalue()
	sio.close()
	if s[-1:] == "\n":
		s = s[:-1]

	limit = None
	if hasattr( sys, 'tracebacklimit' ):
		limit = sys.tracebacklimit
	tracelist = []
	n = 0
	f = logging.currentframe()
	while f is not None and ( limit is None or n < limit ):
		lineno = f.f_lineno
		co = f.f_code
		filename = co.co_filename
		name = co.co_name
		filename_ = os.path.normcase( filename )
		if filename_ == logging._srcfile:
			f = f.f_back
			n = n + 1
			continue
		linecache.checkcache( filename )
		line = linecache.getline( filename, lineno, f.f_globals )
		if line: line = line.strip()
		else: line = None
		tracelist.append( ( filename, lineno, name, line ) )
		f = f.f_back
		n = n + 1
	tracelist.reverse()
	s += '\n'
	s += ''.join( traceback.format_list( tracelist ) )
	return s


class Logger( object ):
	'''
	Wrapper class for the logging module
	'''
	buffer = None
	log = None

	def __init__( self ):
		logging.captureWarnings( True )
		logging.raiseExceptions = False  # dont raise an Exception during logging
		self.log = logging.getLogger( None )  # base Logger receives all warnings/logs
		self.log.setLevel( logging.DEBUG )

	def create_console_streamhandler( self, strformat = None, dateformat = None ):
		'''
		create a console stream handler
		'''
		handler = logging.StreamHandler( sys.stdout )
		if strformat is None:
			strformat = '%(asctime)s %(levelname)-8s Module(%(module)s) Func(%(funcName)s) Line(%(lineno)d) %(message)s'
		if dateformat is None:
			dateformat = None#'%Y-%m-%d %H:%M:%S:%'
		formatter = logging.Formatter( fmt = strformat, datefmt = None )
		handler.setFormatter( formatter )
		self.log.addHandler( handler )
		return handler

	def create_streamhandler( self, strformat = None, dateformat = None ):
		'''
		create a string stream handler
		'''
		self.buffer = io.StringIO()
		handler = logging.StreamHandler( self.buffer )
		if strformat is None:
			strformat = '%(asctime)s %(levelname)-8s Module(%(module)s) Func(%(funcName)s) Line(%(lineno)d) %(message)s'
		if dateformat is None:
			dateformat = '%Y-%m-%d %H:%M:%S'
		formatter = logging.Formatter( fmt = strformat, datefmt = None )
		handler.setFormatter( formatter )
		self.log.addHandler( handler )
		return handler
	def getbuffer( self ):
		'''
		return current string stream buffer
		'''
		if ( self.buffer is not None ):
			return self.buffer.getvalue()
		else:
			return ''

	def create_filehandler( self, filename, mode = 'a', encoding = 'utf-8', strformat = None, dateformat = None ):
		'''
		This function creates a file handler for writing logging information.

		Arguments:
		filename - The name of the file which should be used for logging.
		mode - The mode in which the file should be opened.
		encoding - The character encoding which should be used
		strformat - The format of the string, which will be logged. See
		http://docs.python.org/py3k/library/logging.html#logrecord-attributes
		dateformat - Format for time encoding, e.g. '%Y-%m-%d %H:%M:%S'

		Returns:
		A logging handler
		'''
		handler = logging.FileHandler( filename, mode, encoding )
		if strformat is None:
			strformat = '%(asctime)s %(levelname)-8s Module(%(module)s) Func(%(funcName)s) Line(%(lineno)d) %(message)s'
		if dateformat is None:
			dateformat = '%Y-%m-%d %H:%M:%S'
		formatter = logging.Formatter( fmt = strformat, datefmt = None )
		handler.setFormatter( formatter )
		self.log.addHandler( handler )
		return handler
	def close_filehandle( self, handle ):
		'''
		This function closes and removes the file handler.
		handle - The file handle which should be closed
		'''
		handle.close()
		self.log.removeHandler( handle )