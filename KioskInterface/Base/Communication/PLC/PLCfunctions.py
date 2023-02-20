# -*- coding: utf-8 -*-
# Script: PLC ADS functions
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

#ChangeLog:
# 2016-01-14: Initial Creation (6f3c962 on 4 Jun 2015)

from ctypes import *
import os
import struct
import winreg

from .PLCconstants import *
from .PLCstructs import *
from .PLCerrorcodes import ERROR_CODES


# load dynamic ADS library
def get_adsdll():
	try:
		path = os.path.join( "Software", "Wow6432Node", "Beckhoff", "TwinCAT3" )
		with winreg.OpenKey( winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ ) as key:
			twincat_dir = winreg.QueryValueEx( key, "TwinCATDir" )[0]
		os.add_dll_directory( os.path.join( twincat_dir, 'Common64' ) )
		return windll.TcAdsDll
	except:
		return None

_adsDLL = get_adsdll()  #: ADS-DLL (Beckhoff TwinCAT)

def isADSLoaded():
	return _adsDLL is not None

class ADSError(Exception):
	def __init__(self, err_code):
		self.err_code = err_code
		self.msg = "{} ({})".format(ERROR_CODES[self.err_code], self.err_code)

	def __str__(self):
		return "ADSError: " + self.msg


def adsGetDllVersion():
	"""
	:summary: Return version, revision and build of the ADS library.
	:rtype: structs.AdsVersion
	:return: version, revision and build of the ads-dll
	"""
	adsGetDllVersionFct = _adsDLL.AdsGetDllVersion
	adsGetDllVersionFct.restype = c_long
	resLong = c_long(adsGetDllVersionFct())
	stVersion = SAdsVersion()
	fit = min(sizeof(stVersion), sizeof(c_long))
	memmove(addressof(stVersion), addressof(resLong), fit)
	return AdsVersion(stVersion)

def adsPortOpen():
	"""
	:summary:  Connect to the TwinCAT message router.
	:rtype: int
	:return: port number
	"""
	adsPortOpenFct = _adsDLL.AdsPortOpen
	adsPortOpenFct.restype = c_long
	portNr = adsPortOpenFct()
	return portNr

def adsPortClose():
	"""
	:summary: Close the connection to the TwinCAT message router.
	:rtype: int
	:return: error state
	"""
	adsPortCloseFct = _adsDLL.AdsPortClose
	adsPortCloseFct.restype = c_long
	errCode = adsPortCloseFct()
	return errCode

def adsGetLocalAddress():
	"""
	:summary: Return the local AMS-address and the port number.
	:rtype: structs.AmsAddr
	:return: AMS-address
	"""
	adsGetLocalAddressFct = _adsDLL.AdsGetLocalAddress
	adsGetLocalAddressFct.argtypes = (POINTER(SAmsAddr),)
	adsGetLocalAddressFct.restype = c_long
	
	stAmsAddr = SAmsAddr()
	errCode = adsGetLocalAddressFct(pointer(stAmsAddr))

	if errCode:
		return None

	adsLocalAddr = AmsAddr(errCode, stAmsAddr)
	return adsLocalAddr

def adsSyncReadStateReq(adr):
	"""
	:summary: Read the current ADS-state and the machine-state from the
		ADS-server
	:param structs.AmsAddr adr: local or remote AmsAddr
	:rtype: (int, int)
	:return: adsState, deviceState
	"""
	adsSyncReadStateReqFct = _adsDLL.AdsSyncReadStateReq
	adsSyncReadStateReqFct.argtypes=(POINTER(SAmsAddr), POINTER(c_int), POINTER(c_int))
	adsSyncReadStateReqFct.restype = c_long

	pAmsAddr = pointer(adr.amsAddrStruct())
	adsState = c_int()
	pAdsState = pointer(adsState)
	deviceState = c_int()
	pDeviceState = pointer(deviceState)

	errCode = adsSyncReadStateReqFct(pAmsAddr, pAdsState, pDeviceState)
	if errCode:
		raise ADSError(errCode)
	return (adsState.value, deviceState.value)

def adsSyncReadDeviceInfoReq(adr):
	"""
	:summary: Read the name and the version number of the ADS-server
	:param structs.AmsAddr adr: local or remote AmsAddr
	:rtype: string, AdsVersion
	:return: device name, version
	"""
	adsSyncReadDeviceInfoReqFct = _adsDLL.AdsSyncReadDeviceInfoReq
	adsSyncReadDeviceInfoReqFct.argtypes=(POINTER(SAmsAddr), c_char_p, POINTER(SAdsVersion))
	adsSyncReadDeviceInfoReqFct.restype = c_long

	pAmsAddr = pointer(adr.amsAddrStruct())
	devNameStringBuffer = create_string_buffer(20)
	stVersion = SAdsVersion()
	pVersion = pointer(stVersion)

	errCode = adsSyncReadDeviceInfoReqFct(pAmsAddr, devNameStringBuffer, pVersion)
	if errCode:
		raise ADSError(errCode)
	return (devNameStringBuffer.value.decode(), AdsVersion(stVersion))

def adsSyncWriteControlReq(adr, adsState, deviceState, data, plcDataType):
	"""
	:summary: Change the ADS state and the machine-state of the ADS-server

	:param structs.AmsAddr adr: local or remote AmsAddr
	:param ushort adsState: new ADS-state, according to ADSTATE constants
	:param ushort deviceState: new machine-state
	:param data: additional data
	:param int plcDataType: plc datatype, according to PLCTYPE constants

	:note: Despite changing the ADS-state and the machine-state it is possible

	to send additional data to the ADS-server. For current ADS-devices
	additional data is not progressed.
	Every ADS-device is able to communicate its current state to other devices.
	There is a difference between the device-state and the state of the
	ADS-interface (AdsState). The possible states of an ADS-interface are
	defined in the ADS-specification.
	"""
	adsSyncWriteControlReqFct = _adsDLL.AdsSyncWriteControlReq
	adsSyncWriteControlReqFct.argtypes=(POINTER(SAmsAddr), c_ushort, c_ushort, c_ulong, c_void_p)
	adsSyncWriteControlReqFct.restype = c_long
	pAddr = pointer(adr.amsAddrStruct())
	nAdsState = c_ushort(adsState)
	nDeviceState = c_ushort(deviceState)

	if plcDataType == PLCTYPE_STRING:
		nData = c_char_p(data.encode())
		pData = nData
		nLength = len(pData.value)+1
	else:
		nData = plcDataType(data)
		pData = pointer(nData)
		nLength = sizeof(nData)

	errCode = adsSyncWriteControlReqFct(pAddr, nAdsState, nDeviceState,
										nLength, pData)
	if errCode:
		raise ADSError(errCode)

def adsSyncWriteReq(adr, indexGroup, indexOffset, value, plcDataType):
	"""
	:summary: Send data synchronous to an ADS-device

	:param structs.AmsAddr adr: local or remote AmsAddr
	:param int indexGroup: PLC storage area, according to the INDEXGROUP
		constants
	:param int indexOffset: PLC storage address
	:param value: value to write to the storage address of the PLC
	:param int plcDataType: type of the data given to the PLC,
		according to PLCTYPE constants
	"""
	adsSyncWriteReqFct = _adsDLL.AdsSyncWriteReq
	adsSyncWriteReqFct.argtypes=(POINTER(SAmsAddr), c_ulong, c_ulong, c_ulong, c_void_p)
	adsSyncWriteReqFct.restype = c_long

	pAmsAddr = pointer(adr.amsAddrStruct())
	nIndexGroup = c_ulong(indexGroup)
	nIndexOffset = c_ulong(indexOffset)

	if plcDataType == PLCTYPE_STRING:
		nData = c_char_p(value)
		pData = nData
		nLength = len(pData.value)+1
	else:
		if type(plcDataType).__name__ == 'PyCArrayType':
			nData = plcDataType(*value)
		else:
			nData = plcDataType(value)
		pData = pointer(nData)
		nLength = sizeof(nData)

	errCode = adsSyncWriteReqFct(pAmsAddr, nIndexGroup, nIndexOffset,
								nLength, pData)
	if errCode:
		raise ADSError(errCode)

def adsSyncReadWriteReq(adr, indexGroup, indexOffset,  plcReadDataType,
						value, plcWriteDataType):
	"""
	:summary: Read and write data synchronous from/to an ADS-device
	:param structs.AmsAddr adr: local or remote AmsAddr
	:param int indexGroup: PLC storage area, according to the INDEXGROUP
		constants
	:param int indexOffset: PLC storage address
	:param int plcDataType: type of the data given to the PLC to respond to,
		according to PLCTYPE constants
	:param value: value to write to the storage address of the PLC
	:param plcWriteDataType: type of the data given to the PLC, according to
		PLCTYPE constants
	:rtype: PLCTYPE
	:return: value: **value**
	"""
	adsSyncReadWriteReqFct = _adsDLL.AdsSyncReadWriteReq
	adsSyncReadWriteReqFct.argtypes=(POINTER(SAmsAddr), c_ulong, c_ulong, c_ulong, c_void_p, c_ulong, c_void_p)
	adsSyncReadWriteReqFct.restype = c_long

	pAmsAddr = pointer(adr.amsAddrStruct())
	nIndexGroup = c_ulong(indexGroup)
	nIndexOffset = c_ulong(indexOffset)

	readData = plcReadDataType()
	nReadLength = c_ulong(sizeof(readData))

	if plcWriteDataType == PLCTYPE_STRING:
		# as we got the value as unicode string (python 3)
		# we have to convert it to ascii
		ascii_string = value.encode()
		data = c_char_p(ascii_string)
		data_length = len(value) + 1
	else:
		nData = plcWriteDataType(value)
		data = pointer(nData)
		data_length = sizeof(nData)

	err_code = adsSyncReadWriteReqFct(
		pAmsAddr, nIndexGroup, nIndexOffset, nReadLength, pointer(readData),
		data_length, data)

	if err_code:
		raise ADSError(err_code)

	if hasattr(readData, 'value'):
		return readData.value
	else:
		if type(plcDataType).__name__ == 'PyCArrayType':
			dout = [i for i in readData]
			return dout
		else:
			# if we return structures, they may not have a value attribute
			return readData

def adsSyncReadReq(adr, indexGroup, indexOffset, plcDataType):
	"""
	:summary: Read data synchronous from an ADS-device
	:param structs.AmsAddr adr: local or remote AmsAddr
	:param int indexGroup: PLC storage area, according to the INDEXGROUP
		constants
	:param int indexOffset: PLC storage address
	:param int plcDataType: type of the data given to the PLC, according to
		PLCTYPE constants
	:rtype: PLCTYPE
	:return: value: **value**
	"""
	adsSyncReadReqFct = _adsDLL.AdsSyncReadReq
	adsSyncReadReqFct.argtypes=(POINTER(SAmsAddr), c_ulong, c_ulong, c_ulong, c_void_p)
	adsSyncReadReqFct.restype = c_long

	pAmsAddr = pointer(adr.amsAddrStruct())
	nIndexGroup = c_ulong(indexGroup)
	nIndexOffset = c_ulong(indexOffset)

	data = plcDataType()
	pData = pointer(data)
	nLength = c_ulong(sizeof(data))
	errCode = adsSyncReadReqFct(
		pAmsAddr, nIndexGroup, nIndexOffset, nLength, pData)

	if errCode:
		raise ADSError(errCode)

	if hasattr(data, 'value'):
		return data.value
	else:
		if type(plcDataType).__name__ == 'PyCArrayType':
			dout = [i for i in data]
			return dout
		else:
			# if we return structures, they may not have a value attribute
			return data

def adsGetHandle(adr, dataName):
	hnl = adsSyncReadWriteReq(adr, ADSIGRP_SYM_HNDBYNAME, 0x0, PLCTYPE_UDINT,
							dataName, PLCTYPE_STRING)
	return hnl

def adsReleaseHandle(adr, handle):
	adsSyncWriteReq(adr, ADSIGRP_SYM_RELEASEHND, 0, handle, PLCTYPE_UDINT)

def adsSyncReadByHandle(adr, handle, plcDataType):
	value = adsSyncReadReq(adr, ADSIGRP_SYM_VALBYHND, handle, plcDataType)
	return value

def adsSyncWriteByHandle(adr, handle, value, plcDataType):
	adsSyncWriteReq(adr, ADSIGRP_SYM_VALBYHND, handle, value, plcDataType)

def adsSyncReadByName(adr, dataName, plcDataType):
	"""
	:summary: Read data synchronous from an ADS-device from data name
	:param structs.AmsAddr adr: local or remote AmsAddr
	:param string dataName: data name
	:param int plcDataType: type of the data given to the PLC, according to
		PLCTYPE constants
	:rtype: PLCTYPE
	:return: value: **value**
	"""
	# Get the handle of the PLC-variable
	hnl = adsGetHandle(adr, dataName)

	# Read the value of a PLC-variable, via handle
	value = adsSyncReadReq(adr, ADSIGRP_SYM_VALBYHND, hnl, plcDataType)

	# Release the handle of the PLC-variable
	adsReleaseHandle(adr, hnl)

	return value

def adsSyncWriteByName(adr, dataName, value, plcDataType):
	"""
	:summary: Send data synchronous to an ADS-device from data name
	:param structs.AmsAddr adr: local or remote AmsAddr
	:param string dataName: PLC storage address
	:param value: value to write to the storage address of the PLC
	:param int plcDataType: type of the data given to the PLC,
		according to PLCTYPE constants
	"""
	# Get the handle of the PLC-variable
	hnl = adsGetHandle(adr, dataName)

	# Write the value of a PLC-variable, via handle
	adsSyncWriteReq(adr, ADSIGRP_SYM_VALBYHND, hnl, value, plcDataType)

	# Release the handle of the PLC-variable
	adsReleaseHandle(adr, hnl)

def adsGetVariableDeclarations(adr):
	"""
	:summary: returns list of description fields of all variables available on the PLC
	:param structs.AmsAddr adr: local or remote AmsAddr
	:return: value: list of SymbolInfo entries
	"""
	class SymbolInfo:
		def __init__(self, entry_field, name, type, comment):
			self.group = entry_field.iGroup
			self.offset = entry_field.iOffs
			self.size = entry_field.size
			self.dataType = entry_field.dataType
			self.flags = entry_field.flags
			self.name = name
			self.type = type
			self.comment = comment
		def __str__(self):
			return 'Name: {}\nType: {}\nComment: {}\nGroup: {}\nOffset: {}\nSize: {}\nDataType: {}\nFlags: {}\n'.format(
					self.name, self.type, self.comment, self.group, self.offset, self.size, self.dataType, self.flags)

	# Read the length of the variable declaration	
	info = adsSyncReadReq(adr, ADSIGRP_SYM_UPLOADINFO, 0x0, SAdsSymbolUploadInfo)
	symbols = c_byte * info.nSymSize
	#Read information about the PLC variables 
	entries = adsSyncReadReq(adr, ADSIGRP_SYM_UPLOAD, 0x0, symbols)

	current=0
	entries = struct.pack('b'*len(entries),*entries)
	sizeEntry=sizeof(SAdsSymbolEntry)
	return_entries = []
	for i in range(info.nSymbols):
		entry = SAdsSymbolEntry.from_buffer_copy(entries, current)
		name =    (c_char*entry.nameLength)   .from_buffer_copy(entries, current+sizeEntry).value
		type =    (c_char*entry.typeLength)   .from_buffer_copy(entries, current+sizeEntry+entry.nameLength+1).value
		comment = (c_char*entry.commentLength).from_buffer_copy(entries, current+sizeEntry+entry.nameLength+1+entry.typeLength+1).value
		current += entry.entryLength
		return_entries.append(SymbolInfo(entry, name.decode('ascii'), type.decode('ascii'), comment.decode('ascii')))
		
	return return_entries