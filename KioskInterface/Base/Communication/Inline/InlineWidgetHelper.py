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

from .InlineVariables import State
import time

class ToggleState:
	def __init__(self, init_value, always_update):
		self._value = init_value
		self._actions=[]
		self._always_update = always_update
		
	@property
	def value(self):
		return self._value
	@value.setter
	def value(self, value):
		if self._always_update or self._value != value:
			self._triggerActions(value)
			self._value = value

	def appendAction(self, action):
		self._actions.append(action)
	
	def _triggerActions(self, new_value):
		for a in self._actions:
			a(new_value)
			
class ToggleIcon(ToggleState):
	okIcon = None
	errorIcon = None
	unkIcon = None
	def __init__(self, icon=None, default_value = State.UNKNOWN):
		ToggleState.__init__(self, default_value, False)
		self._icon=icon
		self.appendAction(self._on_change)
		if self._icon is not None:
			self._triggerActions(self.value)
			
	def attachIcon(self, icon, okIcon=None, errorIcon=None, unkIcon=None):
		self._icon = icon
		if okIcon is not None:
			self.okIcon = okIcon
		if errorIcon is not None:
			self.errorIcon = errorIcon
		if unkIcon is not None:
			self.unkIcon = unkIcon
		self._triggerActions(self.value)

	@property
	def icon(self):
		return self._icon
		
	def _on_change(self,new_value):
		if self._icon is not None:
			if new_value == State.UNKNOWN:
				self._icon.data = self.unkIcon
			elif new_value == State.ERROR:
				self._icon.data = self.errorIcon
			elif new_value == State.OK:
				self._icon.data = self.okIcon

class StateWidget(ToggleState):
	def __init__(self, widget=None, default_value = ''):
		ToggleState.__init__(self, default_value, False)
		self._widget=widget
		self.appendAction(self._on_change)
		if self._widget is not None:
			self._triggerActions(self.value)
	def _on_change(self,new_value):
		if self._widget is not None:
			self._widget.text=new_value.name.replace('_',' ').title()

class LogWidget(ToggleState):
	def __init__(self, widget, max_entries):
		self._widget=widget
		self._max_entries = max_entries
		ToggleState.__init__(self, {}, True)
		self.appendAction(self._on_update)
		if self._widget is not None:
			self._triggerActions(self.value)
			self._widget.text=''
	
	def _on_update(self,new_value):
		if self._widget is None:
			return
		if (isinstance(new_value,dict)): # for result
			if len(new_value):
				self._widget.text += '\n'.join("{}: {}".format(key,val) for (key,val) in new_value.items()) + '\n\n'
		elif isinstance(new_value, str) and len(new_value):
			self._widget.text += new_value + ('' if new_value.endswith('\n') else '\n')
		else:
			return
		lines=self._widget.text.split('\n')
		if len(lines) > self._max_entries:
			lines=lines[-self._max_entries:]
			if not len(lines[-1]):
				del lines[-1]
			self._widget.text='\n'.join(lines) +'\n'
				
class StatisticWidget(ToggleState):
	def __init__(self, widget):
		self._widget=widget
		ToggleState.__init__(self, {}, True)
		self.appendAction(self._on_update)
		self._mean = 0
		self._max = 0
		self._min = 100000
		self._count = 0
		self._last_tick = time.time()
		if self._widget is not None:
			self._widget.text = '- / - / -'
		#no direct trigger
	
	def _on_update(self,value):
		self._count += 1
		delta = value - self._mean
		self._mean += delta / self._count
		self._max = max(value, self._max)
		self._min = min(value, self._min)
		if self._widget is not None:
			self._widget.text = '{:.3f} / {:.3f} / {:.3f}'.format(self._min, self._mean, self._max)
	
	def reset(self):
		self._mean = 0
		self._max = 0
		self._min = 100000
		self._count = 0
		self._last_tick = time.time()
		if self._widget is not None:
			self._widget.text = '- / - / -'
		
	def updateTick(self):
		now = time.time()
		self.value = now - self._last_tick
		self._last_tick = now


