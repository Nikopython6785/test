# -*- coding: utf-8 -*-
# Script: Async Client start script
#
# PLEASE NOTE that this file is part of the GOM Inspect Professional software
# You are not allowed to distribute this file to a third party without written notice.
#
# Copyright (c) 2016 GOM GmbH
# Author: GOM Software Development Team (M.V.)
# All rights reserved.

# GOM-Script-Version: 7.6
#
#ChangeLog:
# 2012-05-31: Initial Creation

from Base.Communication import AsyncClient
from Base.Misc import Utils, Globals, Messages, PersistentSettings
import gom
import CustomPatches

if __name__ == '__main__':
	#define globals
	Globals.LOCALIZATION = Messages.Localization()
	Globals.SETTINGS = Utils.Settings()
	Globals.PERSISTENTSETTINGS = PersistentSettings.PersistentSettings( Globals.SETTINGS.SavePath )

	AsyncClient.Client.client_start( Globals.SETTINGS.HostAddress, Globals.SETTINGS.HostPort )
