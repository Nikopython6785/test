# -*- coding: utf-8 -*-
#
# PLEASE NOTE that this file is part of the GOM Software.
# You are not allowed to distribute this file to a third party without written notice.
#
# Please, do not copy and/or modify this script.
# All modifications of KioskInterface should happen in the CustomPatches script.
# Ignoring this advice will make KioskInterface fail after Software update.
#
# Copyright (c) 2017 Carl Zeiss GOM Metrology GmbH
# All rights reserved.

import gom

import multiprocessing
import gom_windows_utils
import gom_atos_log_filter
import ctypes, ctypes.wintypes
import time

from ...Misc import Utils

class ChildInstance (Utils.GenericLogClass):
	def __init__( self, logger, scriptname, logname='measure_inline', control_param=None ):
		Utils.GenericLogClass.__init__( self, logger )
		self.queue = multiprocessing.Queue()
		self.scriptname = scriptname
		self.logname = logname
		self.control_param = control_param
		self.child = None
		self.child_pid = None
		self.child_pids = set()
		self.sw_pid = None

	def startProcess( self, getpid=False ):
		self.child_pids = set()
		sw_pid = None
		if getpid:
			sw_pid = multiprocessing.Value( ctypes.c_size_t, 0 )
		self.child = gom_atos_log_filter.startInstance( self.scriptname, self.queue, sw_pid, self.logname )
		self.child_pid = self.child.pid
		if getpid:
			while sw_pid.value == 0:
				gom.script.sys.delay_script( time=1 )
			self.log.debug( 'Child SW pid {}'.format( sw_pid.value ) )
			self.sw_pid = sw_pid.value

	def debug_setpid( self, pid ):
		self.sw_pid = pid

	def collectOutput(self):
		output=[]
		while not self.queue.empty():
			data = self.queue.get()
			if data==gom_atos_log_filter.QueueData.CHILD_PID:
				self.child_pids.add(data.data)
			else:
				output.append(data)
		return output

	def isAlive(self):
		if self.child is not None:
			#cleanup other pids
			self.child_pids = {pid for pid in self.child_pids 
										if gom_windows_utils.isPidStillActive(pid)}
			return self.child.is_alive()
		return False

	def killRemainingAsyncChilds(self):
		if not self.isAlive() and len(self.child_pids):
			self.child_pids = {pid for pid in self.child_pids 
										if gom_windows_utils.isPidStillActive(pid)}
			if len(self.child_pids):
				self.log.debug('Killing remaining child async instances')
				self.terminate()
			
	def terminate(self):
		OpenProcess = ctypes.windll.kernel32.OpenProcess
		OpenProcess.argtypes = (ctypes.wintypes.DWORD, ctypes.wintypes.BOOL,ctypes.wintypes.DWORD)
		OpenProcess.restype = ctypes.wintypes.HANDLE
		TerminateProcess = ctypes.windll.kernel32.TerminateProcess
		TerminateProcess.argtypes = (ctypes.wintypes.HANDLE,ctypes.c_uint)
		TerminateProcess.restype = ctypes.wintypes.BOOL
		CloseHandle = ctypes.windll.kernel32.CloseHandle
		CloseHandle.argtypes = (ctypes.wintypes.HANDLE,)
		CloseHandle.restype = ctypes.wintypes.BOOL
		PROCESS_TERMINATE = 1
		
		self.child_pids.add(self.child_pid)
		for pid in self.child_pids:
			if pid is None or not gom_windows_utils.isPidStillActive(pid):
				continue
			self.log.debug('killing pid {}'.format(pid))
			handle = OpenProcess (PROCESS_TERMINATE, False, pid)
			TerminateProcess(handle, 1)
			CloseHandle(handle)

		self.child_pid = None
		self.child_pids = set()