# -*- coding: utf-8 -*-
# Script: CustomPatches
#
# PLEASE NOTE that this file is part of the GOM Inspect Professional software
# You are not allowed to distribute this file to a third party without written notice.
#
# Copyright (c) 2019 GOM GmbH
# Author: GOM Software Development Team (CustomPatchGenerator)
# All rights reserved.

# GOM-Script-Version: 2018
#
# ChangeLog:
# 2019-05-09: Initial Creation
# v1.1 - 2020/03/09 - 10h
# Version en cours + modif de projection -> fonctionnelle
# + Script Brice

import gom
import os

from Base.Measuring import Measure
from Base import Evaluate, Dialogs, Workflow
from Base.Evaluate import ExecutionMode
from Base.Misc import Globals, Utils, DefaultSettings, Messages
from Base.Measuring import Verification
from Base.Measuring.Verification import DigitizeResult, VerificationState

import ctypes
import time
import math
import sys
import socket
import unicodedata

SendInput = ctypes.windll.user32.SendInput

# C struct redefinitions 
PUL = ctypes.POINTER(ctypes.c_ulong)

############## Custom classes ################

class newDefaultSettings(DefaultSettings.DefaultSettings, metaclass = Utils.MetaClassPatch):	
	
		FailedPostfix = '_rejete'
		aTracerPostfix="_aTracer"
		
		nomMesureSection="Section"
		nomMesureCentre="Centre"
		nomMesureProjection="Projection"
############################
		cheminFichierExcel = 'C:/Users/user/Documents/Résultats/Excel'
############################
		
		excelTemplateName='Overview'

		nomSectionCentrage2="Section de centrage"
		nomCercleSectionCentrage="Cercle section centrage"
		nomSection2="Plan départ hauteur"
		
#		listePageRapportInstruTracage=["instruction de traçage","instruction tracage","instruction traçage","instructions de traçage","instructions tracage","instructions traçage"]
		
		interpollation_maillage = 3.00000000e+01
		
		reduireProjet=False
		
		anglePlanSection=0 #angle entre le plan X par rapport au point centre du cercle ajusté sur la section, et le plan définissant le point d'intersection avec la section => point permettant la création de la position 0 pour la projection de la section.

class newDialogs(Dialogs.Dialogs, metaclass = Utils.MetaClassPatch):

	STARTDIALOG_FIXTURE=gom.script.sys.create_user_defined_dialog (content='<dialog>' \
' <title>Start Dialog</title>' \
' <style>Touch</style>' \
' <control id="Empty"/>' \
' <position>left</position>' \
' <embedding>embedded_in_kiosk</embedding>' \
' <sizemode>automatic</sizemode>' \
' <size height="488" width="422"/>' \
' <content columns="10" rows="13">' \
'  <widget column="0" columnspan="10" row="0" rowspan="1" type="spacer::horizontal">' \
'   <name>spacer_width</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>386</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget column="0" columnspan="10" row="1" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_1</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>30</maximum_size>' \
'  </widget>' \
'  <widget column="0" columnspan="10" row="2" rowspan="1" type="image">' \
'   <name>image</name>' \
'   <tooltip></tooltip>' \
'   <use_system_image>false</use_system_image>' \
'   <system_image>system_message_warning</system_image>' \
'   <data><![CDATA[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]]></data>' \
'   <file_name></file_name>' \
'   <keep_original_size>true</keep_original_size>' \
'   <keep_aspect>true</keep_aspect>' \
'   <width>150</width>' \
'   <height>90</height>' \
'  </widget>' \
'  <widget column="0" columnspan="10" row="3" rowspan="1" type="label">' \
'   <name>label_title</name>' \
'   <tooltip></tooltip>' \
'   <text>Select Options and enter the serial number</text>' \
'   <word_wrap>true</word_wrap>' \
'  </widget>' \
'  <widget column="0" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_11</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="1" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_12</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="2" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_13</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="3" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_14</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="4" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_15</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="5" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_16</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="6" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_17</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="7" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_18</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="8" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_19</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="9" columnspan="1" row="4" rowspan="1" type="spacer::vertical">' \
'   <name>spacer_20</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>60</maximum_size>' \
'  </widget>' \
'  <widget column="0" columnspan="2" row="5" rowspan="1" type="label">' \
'   <name>label_user</name>' \
'   <tooltip></tooltip>' \
'   <text>User:</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget column="2" columnspan="8" row="5" rowspan="1" type="input::list">' \
'   <name>userlist</name>' \
'   <tooltip></tooltip>' \
'   <items>' \
'    <item>John</item>' \
'    <item>Jane</item>' \
'    <item>Max</item>' \
'   </items>' \
'   <default>John</default>' \
'  </widget>' \
'  <widget column="0" columnspan="2" row="6" rowspan="1" type="label">' \
'   <name>label_keyword_of</name>' \
'   <tooltip></tooltip>' \
'   <text>N° OF:</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget column="2" columnspan="8" row="6" rowspan="1" type="input::string">' \
'   <name>input_of</name>' \
'   <tooltip></tooltip>' \
'   <value></value>' \
'   <read_only>false</read_only>' \
'  </widget>' \
'  <widget column="0" columnspan="2" row="7" rowspan="1" type="label">' \
'   <name>label_fixture</name>' \
'   <tooltip></tooltip>' \
'   <text>Fixture:</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget column="2" columnspan="8" row="7" rowspan="1" type="input::string">' \
'   <name>inputFixture</name>' \
'   <tooltip></tooltip>' \
'   <value></value>' \
'   <read_only>false</read_only>' \
'  </widget>' \
'  <widget column="0" columnspan="2" row="8" rowspan="1" type="label">' \
'   <name>label_serial</name>' \
'   <tooltip></tooltip>' \
'   <text>Serial:</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget column="2" columnspan="8" row="8" rowspan="1" type="input::string">' \
'   <name>inputSerial</name>' \
'   <tooltip></tooltip>' \
'   <value></value>' \
'   <read_only>false</read_only>' \
'  </widget>' \
'  <widget column="0" columnspan="2" row="9" rowspan="1" type="label">' \
'   <name>label_template</name>' \
'   <tooltip></tooltip>' \
'   <text>Template:</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget column="2" columnspan="8" row="9" rowspan="1" type="button::pushbutton">' \
'   <name>buttonTemplateChoose</name>' \
'   <tooltip></tooltip>' \
'   <text>Choose</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget column="0" columnspan="10" row="10" rowspan="1" type="spacer::vertical">' \
'   <name>spacer</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget column="0" columnspan="10" row="11" rowspan="1" type="button::pushbutton">' \
'   <name>buttonNext</name>' \
'   <tooltip></tooltip>' \
'   <text>Start</text>' \
'   <type>push</type>' \
'   <icon_type>system</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget column="0" columnspan="10" row="12" rowspan="1" type="button::pushbutton">' \
'   <name>buttonExit</name>' \
'   <tooltip></tooltip>' \
'   <text>Exit</text>' \
'   <type>push</type>' \
'   <icon_type>system</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>cancel</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
' </content>' \
'</dialog>')

	SECONDDIALOG=gom.script.sys.create_user_defined_dialog (content='<dialog>' \
	' <title>Verification du mode opératoire</title>' \
	' <style></style>' \
	' <control id="Empty"/>' \
	' <position>center</position>' \
	' <embedding>always_toplevel</embedding>' \
	' <sizemode>automatic</sizemode>' \
	' <size width="408" height="180"/>' \
	' <content columns="2" rows="3">' \
	'  <widget row="0" rowspan="1" columnspan="2" type="label" column="0">' \
	'   <name>label</name>' \
	'   <tooltip></tooltip>' \
	'   <text>Veuillez vous assurer de la bonne correspondance du mode opératoire.</text>' \
	'   <word_wrap>false</word_wrap>' \
	'  </widget>' \
	'  <widget row="1" rowspan="1" columnspan="2" type="display::text" column="0">' \
	'   <name>text</name>' \
	'   <tooltip></tooltip>' \
	'   <text>&lt;!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">' \
	'&lt;html>&lt;head>&lt;meta name="qrichtext" content="1" />&lt;style type="text/css">' \
	'p, li { white-space: pre-wrap; }' \
	'&lt;/style>&lt;/head>&lt;body style="    ">' \
	'&lt;p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">&lt;span style=" font-size:12pt;">Mode opératoire&lt;/span>&lt;/p>&lt;/body>&lt;/html></text>' \
	'   <wordwrap>false</wordwrap>' \
	'  </widget>' \
	'  <widget row="2" rowspan="1" columnspan="1" type="button::pushbutton" column="0">' \
	'   <name>buttonOui</name>' \
	'   <tooltip></tooltip>' \
	'   <text>Oui</text>' \
	'   <type>push</type>' \
	'   <icon_type>none</icon_type>' \
	'   <icon_size>icon</icon_size>' \
	'   <icon_system_type>ok</icon_system_type>' \
	'   <icon_system_size>default</icon_system_size>' \
	'  </widget>' \
	'  <widget row="2" rowspan="1" columnspan="1" type="button::pushbutton" column="1">' \
	'   <name>buttonNo</name>' \
	'   <tooltip></tooltip>' \
	'   <text>Non</text>' \
	'   <type>push</type>' \
	'   <icon_type>none</icon_type>' \
	'   <icon_size>icon</icon_size>' \
	'   <icon_system_type>ok</icon_system_type>' \
	'   <icon_system_size>default</icon_system_size>' \
	'  </widget>' \
	' </content>' \
	'</dialog>')

	CONFIRMDIALOG=gom.script.sys.create_user_defined_dialog (content='<dialog>' \
' <title>Confirm Dialog</title>' \
' <style>Touch</style>' \
' <control id="Empty"/>' \
' <position>left</position>' \
' <embedding>embedded_in_kiosk</embedding>' \
' <sizemode>automatic</sizemode>' \
' <size width="422" height="503"/>' \
' <content columns="1" rows="15">' \
'  <widget rowspan="1" type="spacer::horizontal" columnspan="1" row="0" column="0">' \
'   <name>spacer_width</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>386</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget rowspan="1" type="spacer::vertical" columnspan="1" row="1" column="0">' \
'   <name>spacer_1</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>30</maximum_size>' \
'  </widget>' \
'  <widget rowspan="1" type="image" columnspan="1" row="2" column="0">' \
'   <name>image</name>' \
'   <tooltip></tooltip>' \
'   <use_system_image>false</use_system_image>' \
'   <system_image>system_message_warning</system_image>' \
'   <data><![CDATA[eAEB8QwO8wAAAAGJUE5HDQoaCgAAAA1JSERSAAAAlgAAAFoIBgAAAForry0AAAAJcEhZcwAADsQAAA7EAZUrDhsAAAAZdEVYdFNvZnR3YXJlAEFkb2JlIEltYWdlUmVhZHlxyWU8AAAMeklEQVR4Ae2dv3cbxxHHZxYUQVr85UKiSMgyxX/ATJfOSOcuSKO4C9ylC/MXBClTBf4LAnWJ8vICd+kMl65Cl2kkhE8ERDrvSQkpiSBxO3mzh4NAELidvQNAgNjPe2rEw2EP973Z2dmZOfB4PB6Px+PxeDwej8fj8XhmABzlEHP3c58RUIGI8qBwDwE3rhxAUCfSdUSsIWD16OToh0n+RDw+jZhHgDwQ7QHCTv8xpHUNUdVRQS3bylafv37+30mOkdne3P45EBYIYQ8B9q6MD+gNgqoRQG35YrEiHd/W1tanoDMFybUDUrVx3PgmzTWkFtbux7vr53fO9wGwOGiwsRDwDSwdvTp6mnYcceQe5H6lCfb7b5IMrGqE8qtXL79L9N0sZtLluGOaPzZ/Bh8EVZb+jkZkBOWly6XyMIGxoDBQJUAouoxbcu44UgkrvGFUvmaZXCHgp2Q/7VMyaHykoeQs+AHw06xQ7bta2QcPHn6uiGpxxzSOj3D7fu5Prje/Cz+gAIX+sW1tPvwNgC6luT+hhYSi671JJCxjpRYvKgBUSPL5oRBUli6z+2mnHx7f+4X3VVQqP9LxMUSlxknj99LDJcLi604squ4p6I0izEfiSiXUASBA+ej46LcOx7sRztWqmmxasUMAB8sX2XxScYV+FNVSW9EY2Hott5cLkjGKhDWqcXXExYIigP1Rn99FXE7CMpZg8bw+zpsGKcQ1CVFFSMc4SWEZjFuRfuqP+YKCZFpU0tOFompN5KaxNeSpzOUzkxQVRGNcbE1OMFLGKirzQFVYC7bjxMJqLbZK45r+BsH+0fb97d9JjuULJYDqpEQVwb+H8WXmCP6NwyhAPCJhsTl3nbN5quA5mZ1d8w+wyj6A253DElsi22FmIZHwSeVxss9kppAkIBRNmGCEhPEkKHLMjVeMJvbGfhOPMy0cSwTc53MuXWQ3kp0brYsCkY+1fT/3QnzjiEqUoUqz2fz3oD+7hgD4gqM4zyBcfRjj4AJWeCXWvzwPV7vnedK077SiJKgvXWb3Bvlb7uPD/ebxy6+H/Z1DCAgUGxcbfvL4Fa3LuZFgLy70krGdwDyNiL+2HcdPviL4onHS+MvZ2dlQh/b07PSHe4v3Km0VPAC0T62IuLN2d616+vb0eNDf1z5arQGCcArEKjvch/85/GbQ+V6fv26dvj3919m7s6d3V9drSJAXnRtho63a56dvT68FUVdW1nY4DiQaHlGpeXL0h7hDzt7+7/u11TW2rk6hHrZKjePGUMFG5169u8oHCx4qejXoervfZ/v49ubDv9viVUlXceJYC0GlcXL01fWx8RSEIieff9jeCP+fHz/+LBMEBULcA603CPEAePpeWKg+eR5ex4cFi8C3JKg3To4e9/+32GIN+fwwtu5tfSu3qlhtHL/8hfTcshkq/pyxPlbo/duDoIqgmCTuxGKRzO2Ew8agRJaAp5dIVH97/PjTZ5988q0KggMCYP+vAOH+IW/5VOjysv7XR4/MooGviR8YfnCsX4Kwk8bXQgSnVTAqFE+HaHxcOYT2cxNQrPBihcX+hnU0RKVUm8kLdovFK5F+J14qen6yIp+FrVS73T6IM/WIuMGCe/bo0T+f7e6umwdG6YJo4UGYfCeCo+8OcCxJNiaou94fiYW1WfH4VSHZpwDepLQdE0fo5AumM3V1LCLR8yWowKxm2VJhu11j4QiHtgdBYG42j5E3ZAWfSbyFlOjh1CSwpGg/ZhRj6SNeWKhihcXT2CjSShDJKizSfaZXIHq2AtHqNAiCkoOoOp+nwrOHDz8H6QOEsCMJHg4YZ6JQh1LKLhrSzsKCjt+c5HMRscIiHcTeCM6rSvPlXbTkIvCKsEzOl/UjoWDZWoF0ZdZPJmMsXvgA2S3ru+yFcxCZc9SSDI3IMS7ogtapzi2OvI8Tiekl0s4BUFLhVNEOguRZDtTjxyV8+ueRqRCWZPpAlXF+gqJpUEG6/bOOxeOpziqsjGW1NC+kFBaO5EcUTR83aC0uIQySalTjm3puGbHCEvhQI0mky9CIEwb7IIBUgvjyxQszVSutrdcbACbbc7xlxAtLWX6klEHBCCL79oRWynmhwFFv89lMJs0io8dSjsZCzwOxwtIoiIoDOkV1+zF52YIN6Y9ai1emQslSO7KExuIkT7brDVxaLRZiMPcWC2zCYufXFs/gCGxuM/fHJF8eRtO1QJh4vQxL4EhroGJ3YeC4rdHh4MnhoYnac1aG7QHgSPiwrI55w+q8K7RHnDlXK6wIkeOS8TkogCqxpr1JaU9evvyOHGJZHCPSmUz3eJPqY/0+9+n6tmIVFhdtSvakOI+HMyFMsYUFFqE4jZj3ugbUHUqsaTiwD8mCvzw8fMriEgQWD2hhIR857cYiC6ZrLiK1jmdOsAornIKUcBqhAmpV53QYdup7RcaONN8gTslgEUrTiLmgddjfJNYUjHWjWq+48M4dFsl+r99lxIac5QrFJ4eHP+mKihMThdmzXJksOW4eWJBcI2cHbG3miuKcd5NjhUXUCNubufD/iPiJdqoL4r3Ixo/NoVXSbE3fL56/sYmU/87i2t7cNoWXnXyrrzv/BhJWeLfKRNIkPRCXu88D4gAp51w556ynwHyXJaXGxZqG4sMqJ8hFYYhBsKDYSp3faR24FHxSRrIImR9EFgs6+3n8xAO4JaQloVvV22xYV1iu1pSzLpGotn0/VzcpJT0Rfd7YPletvDGtDpaVi0YafjV4BbGwoJNclnuQK5JjUpoL/aXiEtiaOtcUGmecdgA/JOchJug4QFDPXma9terDea+QV2hcoTGWaZGg7ioq6FhThTjyknIbnYYZolL7eSPRJjTfSHHliRC+SVphMWn2ohH8CJtgSODfYNI9vmaFxNkNXHs3ymvkaQxJV+McaxuTEldorWU9DOaVRMLimz+OFkEsLk7kN9snCWFxcXXvuFawYf0kVyh7UcWRSFhK01itAi8O0mRNcPe95YulHdfKF8HASlwO5qc/O87CMtH0QdMN9wQIeyBUTJm91rU0vQa4q4mkb8Mw2KHmukVeaKQRmLF8BBVSeofL072jLsMp3MB0+lmGsJi4uFEF1QG7+t0eAVGzVpeAI0+L3EFm9+PdgT0RpHSsy1dbW1ulqLkrgc7HhibCqpkaN7hdai2lanBr0mh0fGqRyqhEqTaco6Z0fGA2SR5bZ0wV0sn7ejkFbkyjVK3qSZvSRtskbgJza1Eoha+FKHNtYzlpE1vPtfsmJ+xXhTtp+4Qa55+0uJ8VO+P+hs8WTj4Wpyqz35LWz4ica2lRJAaBj2zPGCN9gYArnanxQJLr5K3WbHGjdYVs+VDY52ncIQ7PaLE2Xhs33ABN1OwLYe/e4r0yN0fzGph+pqIS2jTcEDTGkHaY8dw8N26xoNOicWVlnR2+L2IPJOR2jH4rZQaYCotlUIG9lZGgZ6lnOpgaYUlrGCc3Ik8apsdihYOxbiFIyss8N89QYSXqTJcSSSOxQdswnuljqLD4FSeTHm3SDVPP9DFQWOEGrVuDeo+nl4HC6qTGTHzKkfSf8swG14Rl3qTVadg/aUdZ0tXYtwmaDa4Ji7uzROksqHGiy3st6D/l2wTNBleEFVqrngYYad604IhJIrTEqdL2HvdMjivCamVbhd7kO54SJxV2wEDwDjzywpoVrgirv7mY9G2aaQnFaxcWCN5g4ZkOusIa1gqRp8ZxWy0jXsEqdOliyce5ZoSusIa1QjRWi1+NOyZMiRcKGuT6/lMzhRGWKWuPtRhUSNrANg62hNwlRnKsVui75c0QJh9rdfluhV+Raxn2TznTM+51rS7wKrCt9D9Q0DudC19fxbzL2DN9GIslfk8NYon7i6b1uYyF1HggTYOhTMZX6cwYRlj8skhxEw2EIlfWJGncwVaKhcmNP8TNbQHKvjpn9uiWf5nuwK49DuJL7LskKbGPzr90mU1VYu+5Ga7UFYrfKj9EBPxCR0TuQ0D16EWVSdsdJWkZ6ZkerhWsur12f5z4xmazzLVN6OX2cuGm9+S4K58X1WwztMQ+1bSYEJ7+CFXBO+uzz9C6Qq7fW1lZf2Ot9RsRnRaMhebx0ffzflNuA9amIOYtXaTL4/K7TEtrgnLDB0BvFdZKaO6tcPbu7Ona6ho3XNsDBHmTfhsc3sjQl83jpvenbhnObYw4as6dXzhXy+lNEBHC2JdntknVHysUmc4Dqj3Swca16bIT2zKv2UU44JdXejF5PB6Px+PxeDwej8fj8Xg8nqkAAP4PNc1K4grS7H0AAAAASUVORK5CYII732VQAVAG]]></data>' \
'   <file_name></file_name>' \
'   <keep_original_size>true</keep_original_size>' \
'   <keep_aspect>true</keep_aspect>' \
'   <width>150</width>' \
'   <height>90</height>' \
'  </widget>' \
'  <widget rowspan="1" type="spacer::vertical" columnspan="1" row="3" column="0">' \
'   <name>spacer_2</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>30</minimum_size>' \
'   <maximum_size>30</maximum_size>' \
'  </widget>' \
'  <widget rowspan="1" type="label" columnspan="1" row="4" column="0">' \
'   <name>label</name>' \
'   <tooltip></tooltip>' \
'   <text>Choisir balançage pour projection</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget rowspan="1" type="input::list" columnspan="1" row="5" column="0">' \
'   <name>list</name>' \
'   <tooltip></tooltip>' \
'   <items>' \
'    <item></item>' \
'   </items>' \
'   <default></default>' \
'  </widget>' \
'  <widget rowspan="1" type="spacer::vertical" columnspan="1" row="6" column="0">' \
'   <name>spacer_3</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget rowspan="1" type="input::checkbox" columnspan="1" row="7" column="0">' \
'   <name>checkbox_1</name>' \
'   <tooltip></tooltip>' \
'   <value>true</value>' \
'   <title>Dégauchi</title>' \
'  </widget>' \
'  <widget rowspan="1" type="input::checkbox" columnspan="1" row="8" column="0">' \
'   <name>checkbox</name>' \
'   <tooltip></tooltip>' \
'   <value>true</value>' \
'   <title>Centrage</title>' \
'  </widget>' \
'  <widget rowspan="1" type="button::pushbutton" columnspan="1" row="9" column="0">' \
'   <name>buttonProj</name>' \
'   <tooltip></tooltip>' \
'   <text>Projeter</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget rowspan="1" type="spacer::horizontal" columnspan="1" row="10" column="0">' \
'   <name>spacer</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget rowspan="1" type="label" columnspan="1" row="11" column="0">' \
'   <name>label_instruction</name>' \
'   <tooltip></tooltip>' \
'   <text>Statut de la pièce mesurée ?</text>' \
'   <word_wrap>true</word_wrap>' \
'  </widget>' \
'  <widget rowspan="1" type="button::pushbutton" columnspan="1" row="12" column="0">' \
'   <name>buttonApprove</name>' \
'   <tooltip></tooltip>' \
'   <text>Accepté</text>' \
'   <type>push</type>' \
'   <icon><![CDATA[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]]></icon>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>full</icon_size>' \
'   <icon_system_type>cancel</icon_system_type>' \
'   <icon_system_size>extra_large</icon_system_size>' \
'  </widget>' \
'  <widget rowspan="1" type="button::pushbutton" columnspan="1" row="13" column="0">' \
'   <name>buttonATracer</name>' \
'   <tooltip></tooltip>' \
'   <text>À tracer</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget rowspan="1" type="button::pushbutton" columnspan="1" row="14" column="0">' \
'   <name>buttonDisapprove</name>' \
'   <tooltip></tooltip>' \
'   <text>Refusé</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
' </content>' \
'</dialog>')

class newConfirm(Workflow.Confirm, metaclass = Utils.MetaClassPatch):
	eval = None
	def __init__( self, logger ):
		self.original____init__(logger)
		self.eval = Workflow.Eval( self.baselog )
		self.toDelete=[]
		self.needToDelete=False
		self.projectionRealisee=False
		self.Eval=Evaluate.Evaluate(self.baselog,self.eval)
		self.parent=Measure.MeasureAtos (self.baselog,self.Eval )
		self.unlock=False
	
	def execute( self ):
		'''
		start the handler
		'''
		self.log.info('start overriding Confirm.execute')
		
		self.min_check(1)
		
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
			Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
			Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = False
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonATracer' ):
			Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = False
		if Globals.DIALOGS.has_widget( Dialogs.Dialogs.CONFIRMDIALOG, 'list' ):
			Globals.DIALOGS.CONFIRMDIALOG.list.enabled = False
			Dialogs.Dialogs.CONFIRMDIALOG.list.items = [align.name for align in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'alignment', 'object_family', 'alignment_main']})]
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonProj' ):
			Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = False
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox' ):
			Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = False
		if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox_1' ):
			Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = False

		result = self.original__execute()

		self.log.info('end overriding Confirm.execute')		
		return result

	def dialog_event_handler (self, widget ):
		'''
		dialog handler function
		'''
		# Prev/Next buttons are removed in KioskInterface
		# Code is left for compatibility with patched confirm dialogs
		try:
			if [reportPage.page_number for reportPage in [report for report in gom.app.project.reports if report.is_selected==True][0].pages][0] == [report.number_of_pages for report in gom.app.project.reports][0]:
				self.log.info("Tries list enabled : "+str([reportPage.page_number for reportPage in [report for report in gom.app.project.reports if report.is_selected==True][0].pages][0]))
				self.unlock=True
				Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = True
				Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = True
				Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = False
				Globals.DIALOGS.CONFIRMDIALOG.list.enabled = True
				Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = True
				Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = True
				Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = True
			else:
				if not self.unlock:
					self.log.info("Disable buttons")
					Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
					Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = False
					Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = False
					Globals.DIALOGS.CONFIRMDIALOG.list.enabled = False
					Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = False
					Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = False
					Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = False
		except:
			pass
		if self.projectionRealisee:
			Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
			Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = True
		if isinstance( widget, gom.Widget ) and widget.name == 'buttonApprove':
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonATracer' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = False 
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonProj' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox' ):
				Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox_1' ):
				Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'list' ):
				Globals.DIALOGS.CONFIRMDIALOG.list.enabled = False
			if self.projectionRealisee==True:
				try:
					self.log.info("Début safety_move_to_home")
		#			self.log.info("Début safety_move_to_home" + str([mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]))
					self.log.info("ms"+str([mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]))
					self.retourHome()
					self.log.info("Fin safety_move_to_home")
				except Exception as e:
					self.log.info("Failed safety_move_to_home " + str(e))
			self.projectionRealisee=False
			self.log.info("Gonna deinit Sensor")
			if self.eval.eval.sensor.is_initialized():
				self.log.info("deinit Sensor")
				self.eval.eval.sensor.deinitialize()
			if self.needToDelete:
				self.log.info("delete needed elements + measurment series")
				self.deleteAllElement()
				self.deleteMeasurementSeries()	
			for page in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'reports']}):
				if 'balancage' in page.report_title.lower().replace('ç','c') or 'tracage' in page.report_title.lower().replace('ç','c'):
					gom.script.cad.delete_element (
						elements=[page], 
						with_measuring_principle=True)	
				
			
			try:
				for page in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'reports']}):
					if 'Page pour visualisation' in page.report_title:
						print(page)
						gom.script.cad.delete_element (
							elements=[page], 
							with_measuring_principle=True)
			except:
				pass
			Globals.DIALOGS.STARTDIALOG_FIXTURE.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
			for i in Globals.ADDITIONAL_PROJECTKEYWORDS:
				if Globals.DIALOGS.has_widget(  Globals.DIALOGS.STARTDIALOG_FIXTURE, 'input_'+str(i[0]) ):
					try:
						getattr( Globals.DIALOGS.STARTDIALOG_FIXTURE, 'input_'+str(i[0]) ).value = ""
					except:
						pass
		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonATracer':
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonATracer' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonPrev' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonPrev.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonNext' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonNext.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonProj' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox' ):
				Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox_1' ):
				Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'list' ):
				Globals.DIALOGS.CONFIRMDIALOG.list.enabled = False
			self.log.info( 'user approved part with projection' )
			project_file = gom.app.project.get( 'project_file' )
			self.needToDelete=False
			Globals.SETTINGS.reduireProjet=False
			if self.projectionRealisee==True:
				try:
					self.log.info("Début safety_move_to_home")
		#			self.log.info("Début safety_move_to_home" + str([mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]))
					self.log.info("ms"+str([mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]))
					self.retourHome()
					self.log.info("Fin safety_move_to_home")
				except Exception as e:
					self.log.info("Failed safety_move_to_home " + str(e))
			self.projectionRealisee=False
			self.log.info("Gonna deinit Sensor")
			if self.eval.eval.sensor.is_initialized():
				self.log.info("deinit Sensor")
				self.eval.eval.sensor.deinitialize()
			if self.needToDelete:
				self.log.info("delete needed elements + measurment series")
				self.deleteAllElement()
				self.deleteMeasurementSeries()	
			try:
				for page in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'reports']}):
					if 'Page pour visualisation' in page.report_title:
						print(page)
						gom.script.cad.delete_element (
							elements=[page], 
							with_measuring_principle=True)
			except:
				pass
			Globals.DIALOGS.STARTDIALOG_FIXTURE.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
			for i in Globals.ADDITIONAL_PROJECTKEYWORDS:
				if Globals.DIALOGS.has_widget(  Globals.DIALOGS.STARTDIALOG_FIXTURE, 'input_'+str(i[0]) ):
					try:
						getattr( Globals.DIALOGS.STARTDIALOG_FIXTURE, 'input_'+str(i[0]) ).value = ""
					except:
						pass
			self.after_confirmation( "tracer" )
			self.cleanup_project( project_file )
			gom.script.sys.close_user_defined_dialog( dialog = Globals.DIALOGS.CONFIRMDIALOG, result = widget )
		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonDisapprove':
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonATracer' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = False 
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonProj' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox' ):
				Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox_1' ):
				Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'list' ):
				Globals.DIALOGS.CONFIRMDIALOG.list.enabled = False
			self.needToDelete=False
			Globals.SETTINGS.reduireProjet=False
			if self.projectionRealisee==True:
				try:
					self.log.info("Début safety_move_to_home")
		#			self.log.info("Début safety_move_to_home" + str([mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]))
					self.log.info("ms"+str([mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]))
					self.retourHome()
					self.log.info("Fin safety_move_to_home")
				except Exception as e:
					self.log.info("Failed safety_move_to_home " + str(e))
			self.projectionRealisee=False
			self.log.info("Gonna deinit Sensor")
			if self.eval.eval.sensor.is_initialized():
				self.log.info("deinit Sensor")
				self.eval.eval.sensor.deinitialize()
			if self.needToDelete:
				self.log.info("delete needed elements + measurment series")
				self.deleteAllElement()
				self.deleteMeasurementSeries()	
			try:
				for page in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'reports']}):
					if 'Page pour visualisation' in page.report_title:
						print(page)
						gom.script.cad.delete_element (
							elements=[page], 
							with_measuring_principle=True)	
			except:
				pass
			Globals.DIALOGS.STARTDIALOG_FIXTURE.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
			for i in Globals.ADDITIONAL_PROJECTKEYWORDS:
				if Globals.DIALOGS.has_widget(  Globals.DIALOGS.STARTDIALOG_FIXTURE, 'input_'+str(i[0]) ):
					try:
						getattr( Globals.DIALOGS.STARTDIALOG_FIXTURE, 'input_'+str(i[0]) ).value = ""
					except:
						pass
		elif isinstance( widget, gom.Widget ) and widget.name == 'list':
			self.log.info("Instance on list")
			rapportTracage=''
			for i in gom.app.project.reports:
				for j in gom.app.project.report_templates:
					try:
						if i.report_template==j.template['Consigne de traçage'].name or i.report_template==j.template['Instructions de traçage'].name:
							rapportTracage=i
					except:
						pass
			if rapportTracage!='':
				self.log.info('Mise à jour de l instruction de tracage.')
				gom.script.report.update_report_page (
					pages=[rapportTracage], 
					used_alignments='current', 
					used_digits='report', 
					used_legends='report', 
					used_stages='current', 
					used_units='report')
			try:
				gom.script.view.adapt_zoom (use_animation=False)
			except:
				pass
			try:
				gom.script.report.create_report_page (
					animated_page=False, 
					imitate_fit_mode='overwrite', 
					master_name='Style_a4', 
					target_index=5, 
					template_name='3D', 
					template_orientation='portrait', 
					title='Page pour visualisation')
			except:
				pass
			gom.script.report.restore_3d_view_from_report_page (page=[report for report in gom.app.project.reports if report.get('name')=='Page pour visualisation'][0])
			gom.script.cad.show_element_exclusively (elements=[comp for comp in gom.app.project.inspection if comp.get('object_family')=='surface_comparison'][0])
			gom.script.cad.show_element_exclusively (elements=[comp.deviation_label for comp in gom.app.project.inspection if comp.get('object_family')=='surface_comparison'][0])
			gom.script.manage_alignment.set_alignment_active (cad_alignment=gom.app.project.alignments[Dialogs.Dialogs.CONFIRMDIALOG.list.value])
			gom.script.sys.recalculate_alignment (alignment=gom.app.project.alignments[Dialogs.Dialogs.CONFIRMDIALOG.list.value])
			gom.script.view.adapt_zoom (use_animation=False)
			gom.script.sys.switch_to_report_workspace ()
			gom.script.explorer.switch_sub_explorer_category (name='related')			
		elif isinstance( widget, gom.Widget ) and widget.name == 'checkbox':
			Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = True
			if not Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.value and not Globals.DIALOGS.CONFIRMDIALOG.checkbox.value:
				Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = False				
		elif isinstance( widget, gom.Widget ) and widget.name == 'checkbox_1':
			Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = True
			if not Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.value and not Globals.DIALOGS.CONFIRMDIALOG.checkbox.value:
				Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = False				
		elif isinstance( widget, gom.Widget ) and widget.name == 'buttonProj':
			self.log.info("Button proj clicked")
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonPrev' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonPrev.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonATracer' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonNext' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonNext.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonProj' ):
				Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'list' ):
				Globals.DIALOGS.CONFIRMDIALOG.list.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox' ):
				Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = False
			if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox_1' ):
				Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = False

			if Globals.DIALOGS.CONFIRMDIALOG.checkbox.value == True and Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.value == True:
				self.projeter("centrageSection",Globals.DIALOGS.CONFIRMDIALOG.list.value)
#				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
#					Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonATracer' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonProj' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'list' ):
					Globals.DIALOGS.CONFIRMDIALOG.list.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox_1' ):
					Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox' ):
					Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = True
			elif Globals.DIALOGS.CONFIRMDIALOG.checkbox.value == True and Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.value == False:
				self.projeter("centre",Globals.DIALOGS.CONFIRMDIALOG.list.value)
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = True
#				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
#					Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonATracer' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonProj' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'list' ):
					Globals.DIALOGS.CONFIRMDIALOG.list.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox_1' ):
					Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox' ):
					Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = True
			elif Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.value == True and Globals.DIALOGS.CONFIRMDIALOG.checkbox.value == False:	
				self.projeter("section",Globals.DIALOGS.CONFIRMDIALOG.list.value)
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonDisapprove' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonDisapprove.enabled = True
#				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonApprove' ):
#					Globals.DIALOGS.CONFIRMDIALOG.buttonApprove.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonATracer' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonATracer.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'buttonProj' ):
					Globals.DIALOGS.CONFIRMDIALOG.buttonProj.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'list' ):
					Globals.DIALOGS.CONFIRMDIALOG.list.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox' ):
					Globals.DIALOGS.CONFIRMDIALOG.checkbox.enabled = True
				if Globals.DIALOGS.has_widget( Globals.DIALOGS.CONFIRMDIALOG, 'checkbox_1' ):
					Globals.DIALOGS.CONFIRMDIALOG.checkbox_1.enabled = True								
			gom.script.sys.switch_to_report_workspace ()
			gom.script.explorer.switch_sub_explorer_category (name='related')
		self.original__dialog_event_handler(widget)
		
	def projeter(self, zone, align):
		self.log.info("Début fonction projeter")
		
		self.eval.eval.sensor.check_for_reinitialize()
		if align=="":
			selg.log.info("No alignment")
		gom.script.manage_alignment.set_alignment_active (cad_alignment=gom.app.project.alignments[align])
		gom.script.sys.recalculate_alignment (alignment=gom.app.project.alignments[align])
		gom.script.view.set_view_direction_and_up_direction (
			rotation_center=gom.Vec3d (-5.39211016e+02, -8.24777399e+01, -1.25448011e+02), 
			use_animation=False, 
			view_direction=gom.Vec3d (0.00000000e+00, 7.07106781e-01, 7.07106781e-01), 
			widget='3d_view')
		allEll=[gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'groups']}),gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'virtual_measuring_room']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'coordinate_systems']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'nominal']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'inspection']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'actual']})]
		for i in allEll:
			try:
				gom.script.cad.hide_element (elements=i)
			except:
				pass
		gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'virtual_measuring_room']}))
		gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'actual', 'object_family', 'mesh']}))
		gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'nominal', 'object_family', 'vmr_fixture']}))
		gom.script.view.adapt_zoom (use_animation=False)
		self.needToDelete=True
		try:
			gom.script.cad.delete_element (
				elements=[gom.app.project.measurement_series['Temp']], 
				with_measuring_principle=True)
				
		except:
			pass
		
		if zone=="centre":
			self.projeterCentre(align)
			try:
				measure_series=gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]]
				self.retourHome()
			except Exception as e:
				self.log.info("Can't use safety_move_to_home" + str(e))
		elif zone=="centrageSection":
			self.projeterCentrageSection(align)
			try:
				measure_series=gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]]
				self.retourHome()
				self.log.info("Projeter safety_move_to_home centrage section")
			except Exception as e:
				self.log.info("Can't use safety_move_to_home" + str(e))		
		elif zone=="section":
			self.projeterSection(align)
			try:
				measure_series=gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]]
				self.retourHome()
				self.log.info("Projeter safety_move_to_home section")
			except Exception as e:
				self.log.info("Can't use safety_move_to_home" + str(e))
		self.projectionRealisee=True
		self.log.info("Fin fonction projeter")
	
	def projeterCentrageSection(self, align):
		self.log.info("Début fonction projeterCentrageSection")
		try:

			#Création position mesure point section
			if not [mseries for mseries in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements if mseries.get('name')==Globals.SETTINGS.nomMesureProjection]:
				gom.script.manage_alignment.set_alignment_active (cad_alignment=gom.app.project.alignments['Original alignment'])
				gom.script.sys.recalculate_project ( with_reports=False )
				self.createCentrageSectionPosition()
				gom.script.manage_alignment.set_alignment_active (cad_alignment=gom.app.project.alignments[align])
				gom.script.sys.recalculate_project ( with_reports=False )
				
			# Affiche uniquement éléments nécessaires
			allEll=[gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'groups']}),gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'virtual_measuring_room']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'coordinate_systems']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'nominal']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'inspection']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'actual']})]
			for i in allEll:
				try:
					gom.script.cad.hide_element (elements=i)
				except:
					pass
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'virtual_measuring_room']}))
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'actual', 'object_family', 'mesh']}))
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'nominal', 'object_family', 'vmr_fixture']}))
			gom.script.view.adapt_zoom (use_animation=False)	
			gom.script.cad.show_element (elements=[gom.app.project.actual_elements[Globals.SETTINGS.nomSection], gom.app.project.actual_elements[Globals.SETTINGS.nomSectionCentrage]])
			gom.script.sys.recalculate_elements (elements=gom.ElementSelection (gom.app.project.inspection[Globals.SETTINGS.nomSection], {'attachment_group': [None, 'criterias']}))
			gom.script.sys.recalculate_elements (elements=gom.ElementSelection (gom.app.project.inspection[Globals.SETTINGS.nomSectionCentrage], {'attachment_group': [None, 'criterias']}))		
	
			#Déplacement
			gom.interactive.automation.move_to_position  (measurement=[mseries for mseries in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements if mseries.get('name')==Globals.SETTINGS.nomMesureProjection][0])
			
			#Projection
			self.project=True
			self.rot=False
			while self.project==True:	
				gom.script.atos.switch_laser (enable=True)	
				DIALOG=gom.script.sys.create_user_defined_dialog (content='<dialog>' \
' <title>Projection du cercle de centrage et de la section</title>' \
' <style></style>' \
' <control id="Empty"/>' \
' <position>center</position>' \
' <embedding></embedding>' \
' <sizemode>fixed</sizemode>' \
' <size width="300" height="267"/>' \
' <content rows="6" columns="2">' \
'  <widget row="0" rowspan="1" type="label" column="0" columnspan="2">' \
'   <name>label</name>' \
'   <tooltip></tooltip>' \
'   <text>Champ de description</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget row="1" rowspan="1" type="spacer::horizontal" column="0" columnspan="2">' \
'   <name>spacer</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget row="2" rowspan="1" type="label" column="0" columnspan="2">' \
'   <name>label_1</name>' \
'   <tooltip></tooltip>' \
'   <text>Champ de description</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget row="3" rowspan="1" type="spacer::horizontal" column="0" columnspan="2">' \
'   <name>spacer_1</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget row="4" rowspan="1" type="button::pushbutton" column="0" columnspan="1">' \
'   <name>buttonRot</name>' \
'   <tooltip></tooltip>' \
'   <text>Rotation 90°</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget row="4" rowspan="1" type="button::pushbutton" column="1" columnspan="1">' \
'   <name>buttonRot45</name>' \
'   <tooltip></tooltip>' \
'   <text>Rotation 45°</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget row="5" rowspan="1" type="button::pushbutton" column="0" columnspan="2">' \
'   <name>buttonFinProj</name>' \
'   <tooltip></tooltip>' \
'   <text>Fin Projection</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
' </content>' \
'</dialog>')
				DIALOG.label.text="Alignement actif : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0])
				try:

					try:
						config=[mseries for mseries in gom.app.project.measuring_setups][0]
						config_name = config.get ('working_area.name')
					except:
						config_name =''
						hauteurPlateau=0
							
					if config_name == 'Zone de travail gauche':
						hauteurPlateau=-float(str(gom.app.project.virtual_measuring_room['Virtual measuring room'].components['Link point Left'].transformation_from_cad)[len("gom.Mat4x4 (["):][:-2].split(',')[7])
						
					elif config_name == 'Zone de travail droite':
						hauteurPlateau=-float(str(gom.app.project.virtual_measuring_room['Virtual measuring room'].components['Link point Right'].transformation_from_cad)[len("gom.Mat4x4 (["):][:-2].split(',')[7])
	
					DIALOG.label_1.text="Hauteur du point : " + str("%.1f"%(gom.app.project.actual_elements['Point centre section 1 p'].center_coordinate.y + hauteurPlateau))+"mm"
				except:
					DIALOG.label_1.text="Hauteur du point non calculée."
				#
				# Event handler function called if anything happens inside of the dialog
				#
				def dialog_event_handler (widget):
					if isinstance( widget, gom.Widget ) and widget.name == 'buttonFinProj':
						self.project=False
						self.log.info("Variable projeter dans isinstance : " + str(self.project))
						PressKey(0x1B)
					elif isinstance( widget, gom.Widget ) and widget.name == 'buttonRot':
						self.rot=90
						PressKey(0x1B)
					elif isinstance( widget, gom.Widget ) and widget.name == 'buttonRot45':
						self.rot=45
						PressKey(0x1B)
					pass

				DIALOG.handler = dialog_event_handler
				
				gom.script.sys.open_user_defined_dialog (dialog=DIALOG)
				self.log.info('Projection des éléments ' + str(Globals.SETTINGS.nomSection) + ' et ' + str(Globals.SETTINGS.nomSectionCentrage) + " dans alignement : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0]))
				gom.interactive.sys.project_elements_on_measuring_object (elements=[gom.app.project.actual_elements[Globals.SETTINGS.nomSection], gom.app.project.actual_elements[Globals.SETTINGS.nomSectionCentrage]])
				gom.script.sys.close_user_defined_dialog (dialog=DIALOG)
				
				if self.rot==90:
					self.rotationPlateau(90.0)
					self.rot=False
				if self.rot==45:
					self.rotationPlateau(45.0)
					self.rot=False
			self.retourHome()
			self.log.info("Fin fonction projeterCentreSection")
		except Exception as e:
			self.log.info("Can't project centre et section" + str(e))
			return False
	
	def projeterCentre(self, align):
		self.log.info("Début fonction projeterCentre")
		try:
			#Création position mesure point centré
			if not [mseries for mseries in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements if mseries.get('name')==Globals.SETTINGS.nomMesureCentre]:
				gom.script.manage_alignment.set_alignment_active (cad_alignment=gom.app.project.alignments['Original alignment'])
				gom.script.sys.recalculate_project ( with_reports=False )
				self.createCentrePosition()
				gom.script.manage_alignment.set_alignment_active (cad_alignment=gom.app.project.alignments[align])
				gom.script.sys.recalculate_project ( with_reports=False )

			# Affiche uniquement éléments nécessaires
			allEll=[gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'groups']}),gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'virtual_measuring_room']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'coordinate_systems']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'nominal']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'inspection']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'actual']})]
			for i in allEll:
				try:
					gom.script.cad.hide_element (elements=i)
				except:
					pass
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'virtual_measuring_room']}))
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'actual', 'object_family', 'mesh']}))
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'nominal', 'object_family', 'vmr_fixture']}))
			gom.script.view.adapt_zoom (use_animation=False)	
			gom.script.cad.show_element (elements=[gom.app.project.actual_elements[Globals.SETTINGS.nomSectionCentrage]])
			gom.script.sys.recalculate_elements (elements=gom.ElementSelection (gom.app.project.inspection[Globals.SETTINGS.nomSectionCentrage], {'attachment_group': [None, 'criterias']}))
			
			#Déplacement
			gom.interactive.automation.move_to_position  (measurement=[mseries for mseries in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements if mseries.get('name')==Globals.SETTINGS.nomMesureCentre][0])
			gom.script.atos.switch_laser (enable=True)
			
			#Projection
			self.project=True
			self.rot=False
			while self.project==True:	
				gom.script.atos.switch_laser (enable=True)	
				DIALOG=gom.script.sys.create_user_defined_dialog (content='<dialog>' \
' <title>Projection du cercle de centrage et de la section</title>' \
' <style></style>' \
' <control id="Empty"/>' \
' <position>center</position>' \
' <embedding></embedding>' \
' <sizemode>fixed</sizemode>' \
' <size width="300" height="267"/>' \
' <content rows="6" columns="2">' \
'  <widget row="0" rowspan="1" type="label" column="0" columnspan="2">' \
'   <name>label</name>' \
'   <tooltip></tooltip>' \
'   <text>Champ de description</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget row="1" rowspan="1" type="spacer::horizontal" column="0" columnspan="2">' \
'   <name>spacer</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget row="2" rowspan="1" type="label" column="0" columnspan="2">' \
'   <name>label_1</name>' \
'   <tooltip></tooltip>' \
'   <text>Champ de description</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget row="3" rowspan="1" type="spacer::horizontal" column="0" columnspan="2">' \
'   <name>spacer_1</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget row="4" rowspan="1" type="button::pushbutton" column="0" columnspan="1">' \
'   <name>buttonRot</name>' \
'   <tooltip></tooltip>' \
'   <text>Rotation 90°</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget row="4" rowspan="1" type="button::pushbutton" column="1" columnspan="1">' \
'   <name>buttonRot45</name>' \
'   <tooltip></tooltip>' \
'   <text>Rotation 45°</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget row="5" rowspan="1" type="button::pushbutton" column="0" columnspan="2">' \
'   <name>buttonFinProj</name>' \
'   <tooltip></tooltip>' \
'   <text>Fin Projection</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
' </content>' \
'</dialog>')
				DIALOG.label.text="Alignement actif : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0])
				try:

					try:
						config=[mseries for mseries in gom.app.project.measuring_setups][0]
						config_name = config.get ('working_area.name')
					except:
						config_name =''
						hauteurPlateau=0
							
					if config_name == 'Zone de travail gauche':
						hauteurPlateau=-float(str(gom.app.project.virtual_measuring_room['Virtual measuring room'].components['Link point Left'].transformation_from_cad)[len("gom.Mat4x4 (["):][:-2].split(',')[7])
						
					elif config_name == 'Zone de travail droite':
						hauteurPlateau=-float(str(gom.app.project.virtual_measuring_room['Virtual measuring room'].components['Link point Right'].transformation_from_cad)[len("gom.Mat4x4 (["):][:-2].split(',')[7])
	
					DIALOG.label_1.text="Hauteur du point : " + str("%.1f"%(gom.app.project.actual_elements['Point centre section 1 c'].center_coordinate.y + hauteurPlateau))+"mm"
				except:
					DIALOG.label_1.text="Hauteur du point non calculée."
				#
				# Event handler function called if anything happens inside of the dialog
				#
				def dialog_event_handler (widget):
					if isinstance( widget, gom.Widget ) and widget.name == 'buttonFinProj':
						self.project=False
						self.log.info("Variable projeter dans isinstance : " + str(self.project))
						PressKey(0x1B)
					elif isinstance( widget, gom.Widget ) and widget.name == 'buttonRot':
						self.rot=90
						PressKey(0x1B)
					elif isinstance( widget, gom.Widget ) and widget.name == 'buttonRot45':
						self.rot=45
						PressKey(0x1B)
					pass

				DIALOG.handler = dialog_event_handler
				
				gom.script.sys.open_user_defined_dialog (dialog=DIALOG)
				self.log.info('Projection de l élément ' + str(Globals.SETTINGS.nomSectionCentrage) + ' dans alignement : ' + str([align.name for align in gom.app.project.alignments if align.is_active == True][0]))
				gom.interactive.sys.project_elements_on_measuring_object (elements=[gom.app.project.actual_elements[Globals.SETTINGS.nomSectionCentrage]])
				gom.script.sys.close_user_defined_dialog (dialog=DIALOG)
				
				if self.rot==90:
					self.rotationPlateau(90.0)
					self.rot=False
				if self.rot==45:
					self.rotationPlateau(45.0)
					self.rot=False
			self.retourHome()
			gom.script.sys.close_user_defined_dialog (dialog=DIALOG)
			gom.script.atos.switch_laser (enable=False)
			self.log.info("Fin fonction projeterCentre")
		except Exception as e:
			self.log.info("Can't project center" + str(e))
			return False
			
	def projeterSection(self, align):
		self.log.info("Début fonction projeterSection")
		try:

			#Création position mesure point section
			if not [mseries for mseries in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements if mseries.get('name')==Globals.SETTINGS.nomMesureSection]:
				self.log.info("Alignement actif : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0]))
				gom.script.manage_alignment.set_alignment_active (cad_alignment=gom.app.project.alignments['Original alignment'])
				gom.script.sys.recalculate_project ( with_reports=False )
				self.createSectionPosition()
				gom.script.manage_alignment.set_alignment_active (cad_alignment=gom.app.project.alignments[align])
				gom.script.sys.recalculate_project ( with_reports=False )
				self.log.info("Alignement actif : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0]))
			
			# Affiche uniquement éléments nécessaires
			allEll=[gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'groups']}),gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'virtual_measuring_room']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'coordinate_systems']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'nominal']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'inspection']}),gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'actual']})]
			for i in allEll:
				try:
					gom.script.cad.hide_element (elements=i)
				except:
					pass
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'virtual_measuring_room']}))
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'actual', 'object_family', 'mesh']}))
			gom.script.cad.show_element (elements=gom.ElementSelection ({'category': ['key', 'elements', 'is_element_in_clipboard', 'False', 'explorer_category', 'nominal', 'object_family', 'vmr_fixture']}))
			gom.script.view.adapt_zoom (use_animation=False)
			gom.script.cad.show_element (elements=[gom.app.project.actual_elements[Globals.SETTINGS.nomSection]])
			gom.script.sys.recalculate_elements (elements=gom.ElementSelection (gom.app.project.inspection[Globals.SETTINGS.nomSection], {'attachment_group': [None, 'criterias']}))
				
			#Déplacement
			gom.interactive.automation.move_to_position  (measurement=[mseries for mseries in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements if mseries.get('name')==Globals.SETTINGS.nomMesureSection][0])
			#Projection
			self.project=True
			self.rot=False
			while self.project==True:	
				gom.script.atos.switch_laser (enable=True)	
				DIALOG=gom.script.sys.create_user_defined_dialog (content='<dialog>' \
' <title>Projection de la section</title>' \
' <style></style>' \
' <control id="Empty"/>' \
' <position>center</position>' \
' <embedding></embedding>' \
' <sizemode>fixed</sizemode>' \
' <size width="300" height="268"/>' \
' <content rows="4" columns="1">' \
'  <widget row="0" rowspan="1" type="label" column="0" columnspan="1">' \
'   <name>label</name>' \
'   <tooltip></tooltip>' \
'   <text>Champ de description</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget row="1" rowspan="1" type="spacer::horizontal" column="0" columnspan="1">' \
'   <name>spacer</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget row="2" rowspan="1" type="button::pushbutton" column="0" columnspan="1">' \
'   <name>buttonRot</name>' \
'   <tooltip></tooltip>' \
'   <text>Rotation 90°</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
'  <widget row="3" rowspan="1" type="button::pushbutton" column="0" columnspan="1">' \
'   <name>buttonFinProj</name>' \
'   <tooltip></tooltip>' \
'   <text>Fin Projection</text>' \
'   <type>push</type>' \
'   <icon_type>none</icon_type>' \
'   <icon_size>icon</icon_size>' \
'   <icon_system_type>ok</icon_system_type>' \
'   <icon_system_size>default</icon_system_size>' \
'  </widget>' \
' </content>' \
'</dialog>')
				DIALOG.label.text="Alignement actif : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0])
				
				#
				# Event handler function called if anything happens inside of the dialog
				#
				def dialog_event_handler (widget):
					if isinstance( widget, gom.Widget ) and widget.name == 'buttonFinProj':
						self.project=False
						self.log.info("Variable projeter dans isinstance : " + str(self.project))
						PressKey(0x1B)
					elif isinstance( widget, gom.Widget ) and widget.name == 'buttonRot':
						self.rot=True
						PressKey(0x1B)
					pass

				DIALOG.handler = dialog_event_handler
				
				gom.script.sys.open_user_defined_dialog (dialog=DIALOG)
				self.log.info('Projection de l élément ' + str(Globals.SETTINGS.nomSection) + ' dans alignement : ' + str([align.name for align in gom.app.project.alignments if align.is_active == True][0]))
				gom.interactive.sys.project_elements_on_measuring_object (elements=[gom.app.project.actual_elements[Globals.SETTINGS.nomSection]])
				gom.script.sys.close_user_defined_dialog (dialog=DIALOG)
				
				if self.rot==True:
					self.rotationPlateau(90.0)
					self.rot=False
			
			self.retourHome()
			self.log.info("Fin fonction projeterSection")
		except Exception as e:
			self.log.info("Can't project section" + str(e))
			return False

	def retourHome(self):
		self.log.info("Début fonction retourHome")
		activeMs=[mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==gom.MeasurementListActiveState (True)][0]
		self.log.info(activeMs)
		lastHomePosition=[mpos for mpos in activeMs.measurements if mpos.get('type') == 'home_position'][-1:]
		self.log.info(lastHomePosition[0])
		activePos=[mPos for mPos in gom.app.project.measurement_series[activeMs.name].measurements if mPos.is_current_position==True][0]
		if lastHomePosition[0] != activePos:
			self.log.info("Go in Home Position")
			gom.interactive.automation.move_to_position (
				direct_movement=False, 
				measurement=lastHomePosition[0])
		self.log.info("Fin fonction retourHome")
	
	def rotationPlateau(self, angle):
		self.log.info("Début fonction rotationPlateau. Angle : "+str(angle))
		activeMs=[mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==gom.MeasurementListActiveState (True)][0]
		activePosition=[mpos for mpos in activeMs.measurements if mpos.get('object_family') == 'measurement_series' and mpos.is_current_position][0]
		axisActivePos=activePosition.automation_axis_position
		for i in axisActivePos.values():
			if len(i) == 7:
				axisPos=i
		for j in axisActivePos.keys():
			clé=j	
		rotAxis=axisPos[-1:][0]
		axisPos.remove(rotAxis)
		if rotAxis + angle < 360.0:	
			axisPos.append(rotAxis+angle)
		else:
			axisPos.append(angle-(360-rotAxis))
			
		newPos={}
		newPos[clé]=axisPos
		gom.script.automation.insert_intermediate_position (position=newPos)
		Position=[mpos for mpos in activeMs.measurements if mpos.get('type') == 'intermediate_position' and mpos.automation_axis_position==newPos][0]
		gom.interactive.automation.move_to_position (
			direct_movement=False, 
			measurement=Position)
		self.log.info("Fin fonction rotationPlateau")
	
	def deleteAllElement(self):
		self.log.info("Début fonction deleteAllElement")
		try:
			gom.script.cad.delete_element (
				elements=self.toDelete, 
				with_measuring_principle=True)
			self.log.info("Fin fonction deleteAllElement deleteAllElement")
		except:
			self.log.info("Error while deleteAllElement")
	
	def deleteMeasurementSeries(self):
		self.log.info("Début fonction deleteMeasurementSeries")
		for i in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements:
			if i.name==Globals.SETTINGS.nomMesureCentre or i.name==Globals.SETTINGS.nomMesureSection or i.name==Globals.SETTINGS.nomMesureProjection:
				try:
					gom.script.cad.delete_element (
						elements=[i], 
						with_measuring_principle=True)
				except:
					self.log.info("Can't delete measurements")
		self.log.info("Fin fonction deleteMeasurementSeries")
	
	def createSectionPosition(self):
		self.log.info("Début fonction createSectionPosition")
		self.log.info("Alignement actif : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0]))
		# Création plan ajusté sur section
		gom.script.cad.show_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
		gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
		MCAD_ELEMENT=gom.script.primitive.create_fitting_plane (
			method='best_fit', 
			name='Plan section s', 
			sigma=3)
		self.toDelete.append(gom.app.project.inspection['Plan section s'])	
		gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Plan section s']])
		
		# Création cercle ajusté sur section
		gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
		MCAD_ELEMENT=gom.script.primitive.create_fitting_circle (
			method='best_fit', 
			name='Cercle section s', 
			sigma=3)
		self.toDelete.append(gom.app.project.inspection['Cercle section s'])
		gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Cercle section s']])
		
		# Création point du centre du cercle
		MCAD_ELEMENT=gom.script.primitive.create_surface_point (
			name='Point section s', 
			point=gom.app.project.inspection['Cercle section s'])
		self.toDelete.append(gom.app.project.inspection['Point section s'])
		gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Point section s']])
		
		# Création d'un plan de rotation à partir du plan X (par défaut 90°) par rapport au point centre du cercle -> devient Z  
		MCAD_ELEMENT=gom.script.primitive.create_plane_by_rotation (
			angle=Globals.SETTINGS.anglePlanSection*math.pi/180, 
			axis=gom.app.project.inspection['Point section s'], 
			name='Plan Section Angle s', 
			normal={'direction': gom.Vec3d (1.00000000e+00, 0.00000000e+00, 0.00000000e+00), 'point': gom.Vec3d (0.00000000e+00, 0.00000000e+00, 0.00000000e+00), 'type': 'projected'}, 
			point=gom.app.project.inspection['Point section s'])
		self.toDelete.append(gom.app.project.inspection['Plan Section Angle s'])
		gom.script.primitive.create_linked_actual_element (elements=[gom.app.project.inspection["Plan Section Angle s"]])
		
		# Création de la droite d'intersection entre les deux plans précédents
		MCAD_ELEMENT=gom.script.primitive.create_line_by_intersection (
			name='Droite section s', 
			plane1=gom.app.project.inspection['Plan Section Angle s'], 
			plane2=gom.app.project.inspection['Plan section s'])
		self.toDelete.append(gom.app.project.inspection['Droite section s'])
		gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Droite section s']])
		
		# Création du point d'intersection entre la droite et la section -> prendre le plus petit sur X
		MCAD_ELEMENT=gom.script.primitive.create_point_by_line_intersection (
			intersect_element={'projection_type': 'curve', 'target': gom.app.project.inspection[Globals.SETTINGS.nomSection]}, 
			line=gom.app.project.inspection['Droite section s'], 
			name="Point section intersec 1 s", 
			point_number=1.00000000e+00)
		self.toDelete.append(gom.app.project.inspection["Point section intersec 1 s"])
		gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection["Point section intersec 1 s"]])
		
		MCAD_ELEMENT=gom.script.primitive.create_point_by_line_intersection (
			intersect_element={'projection_type': 'curve', 'target': gom.app.project.inspection[Globals.SETTINGS.nomSection]}, 
			line=gom.app.project.inspection['Droite section s'], 
			name="Point section intersec 2 s", 
			point_number=2.00000000e+00)
		self.toDelete.append(gom.app.project.inspection["Point section intersec 2 s"])
		gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection["Point section intersec 2 s"]])
		
		pointIntersec="Point section intersec 2 s"
		try:
			if gom.app.project.inspection["Point section intersec 2 s"].center_coordinate.x < gom.app.project.inspection["Point section intersec 1 s"].center_coordinate.x:
				pointIntersec="Point section intersec 2 s"
			else:
				pointIntersec="Point section intersec 1 s"
		except:
			self.log.info("!!!!!!!! Coordonnées y des point intersec non calculables." + str(gom.app.project.inspection["Point section intersec 2 s"]))
		
		MCAD_ELEMENT=gom.script.primitive.create_surface_point (
			name="Point section 2 s", 
			normal=gom.app.project.inspection[pointIntersec], 
			point=gom.app.project.inspection[pointIntersec])
		self.toDelete.append(gom.app.project.inspection["Point section 2 s"])
		gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection["Point section 2 s"]])

		# Duplication du point pour appliquer le principe de mesure intersection avec le maillage (construction référencé devant être utiliser sur ce point également)
		MCAD_ELEMENT=gom.script.primitive.create_surface_point (
			name="pointSection s", 
			point=gom.app.project.inspection["Point section 2 s"])
		self.toDelete.append(gom.app.project.inspection["pointSection s"])
		MCAD_ELEMENT=gom.script.inspection.measure_by_intersection_with_mesh (
			check_plausibility=False, 
			elements=[gom.app.project.inspection["pointSection s"]])
		
		# Création d'une série de mesure
		for i in [mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True]:
			actMs=i
		print(actMs)
		self.log.info("1")
		scan=[]
		for i in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements:
			if i.type == "scan":
				scan.append(i.name)
		self.log.info("2")
		try:
			gom.script.cad.delete_element (
			elements=[gom.app.project.measurement_series['Temp']], 
			with_measuring_principle=True)
		except:
			pass
		gom.script.atos.create_measurement_series (
			measurement_series=gom.app.project.measurement_series[actMs], 
			name='Temp')
		try:
			MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
				consider_only_not_computed_elements=True, 
				consider_reference_points=True, 
				elements=[gom.app.project.inspection['pointSection s']],
				measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
		except:
			try:
				MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
				consider_only_not_computed_elements=False, 
				consider_reference_points=True, 
				elements=[gom.app.project.inspection['pointSection s']],
				measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
			except:
				MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
					consider_only_not_computed_elements=False, 
					consider_reference_points=False, 
					elements=[gom.app.project.inspection['pointSection s']],
					measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])	
		gom.interactive.atos.define_active_measurement_series (measurement_series=gom.app.project.measurement_series[actMs])
		
		gom.script.sys.copy_to_clipboard (elements=[gom.app.project.measurement_series['Temp'].measurements['M1']])
		gom.script.sys.paste_from_clipboard (
			destination=[gom.app.project.measurement_series[actMs].measurements['H2']], 
			insert_before_measurement=True)		
		gom.script.cad.delete_element (
			elements=[gom.app.project.measurement_series['Temp']], 
			with_measuring_principle=True)

		gom.interactive.atos.define_active_measurement_series (measurement_series=gom.app.project.measurement_series[actMs])
		scan2=[]
		self.log.info(scan)
		for i in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements:
			if i.type == "scan":
				if i.name not in scan:
					scan2.append(i.name)
		self.log.info(scan2)
		gom.script.automation.recalculate_path_segment (
			allow_flip=True, 
			allow_re_sorting=False, 
			measurements=[gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements[scan2[0]]], 
			move_additional_axis=True)
		gom.script.sys.edit_properties (
			data=[gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements[scan2[0]]], 
			elem_name=Globals.SETTINGS.nomMesureSection)
		self.log.info("Fin fonction createSectionPosition")
	
	def createCentrePosition(self):
		self.log.info("Début fonction createCentrePosition")
		self.log.info("Alignement actif : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0]))
		
		# Création plan ajusté sur section 1
		try:
			print(gom.app.project.inspection['Plan section 1 c'].nominal_element)
		except:
			gom.script.selection3d.deselect_all ()
			gom.script.cad.show_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
			gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
			MCAD_ELEMENT=gom.script.primitive.create_fitting_plane (
				method='best_fit', 
				name='Plan section 1 c', 
				sigma=3)
			self.toDelete.append(gom.app.project.inspection['Plan section 1 c'])	
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Plan section 1 c']])
		
		# Création cercle sur section 1
		try:
			print(gom.app.project.inspection['Cercle section 1 c'].nominal_element)
		except:
			gom.script.selection3d.deselect_all ()
			gom.script.cad.show_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
			gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
			MCAD_ELEMENT=gom.script.primitive.create_auto_nominal_circle (
				name='Cercle section 1 c')			
			MCAD_ELEMENT=gom.script.inspection.measure_by_fitting_element (
				actual=gom.ActualReference (gom.app.project.inspection[Globals.SETTINGS.nomSection]), 
				elements=[gom.app.project.inspection['Cercle section 1 c']], 
				fill_gaps=True, 
				limit_selection_depending_on_geometry=True, 
				method='best_fit', 
				restrict_actual_selection_to_nominal=True, 
				sigma=3)		
			self.toDelete.append(gom.app.project.inspection['Cercle section 1 c'])
		
		# Création point du centre du cercle
		try:
			print(gom.app.project.inspection['Point centre section 1 c'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_surface_point (
				name='Point centre section 1 c', 
				point=gom.app.project.inspection['Cercle section 1 c'])
			self.toDelete.append(gom.app.project.inspection['Point centre section 1 c'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Point centre section 1 c']])
		
		# Création d'un plan de rotation à partir du plan X (par défaut 0°) par rapport au point centre du cercle  
		try:
			print(gom.app.project.inspection['Plan Coupe projection c'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_plane_by_rotation (
				angle=Globals.SETTINGS.anglePlanSection*math.pi/180, 
				axis=gom.app.project.inspection['Point centre section 1 c'], 
				name='Plan Coupe projection c', 
				normal={'direction': gom.Vec3d (1.00000000e+00, 0.00000000e+00, 0.00000000e+00), 'point': gom.Vec3d (0.00000000e+00, 0.00000000e+00, 0.00000000e+00), 'type': 'projected'}, 
				point=gom.app.project.inspection['Point centre section 1 c'])
			self.toDelete.append(gom.app.project.inspection['Plan Coupe projection c'])
			gom.script.primitive.create_linked_actual_element (elements=[gom.app.project.inspection['Plan Coupe projection c']])
		
		# Création cercle centrage si non existant
		try:
			print(gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage].nominal_element)
		except:
			gom.script.cad.show_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSectionCentrage]])
			gom.script.selection3d.deselect_all ()
			gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSectionCentrage]])
			MCAD_ELEMENT=gom.script.primitive.create_auto_nominal_circle (
				name=Globals.SETTINGS.nomCercleSectionCentrage)
			MCAD_ELEMENT=gom.script.inspection.measure_by_fitting_element (
				actual=gom.ActualReference (gom.app.project.inspection[Globals.SETTINGS.nomSectionCentrage]), 
				elements=[gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage]], 
				fill_gaps=True, 
				limit_selection_depending_on_geometry=True, 
				method='best_fit', 
				restrict_actual_selection_to_nominal=True, 
				sigma=3)		
			self.toDelete.append(gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage])
		
		# Création plan sur cercle centrage
		try:
			print(gom.app.project.inspection['Plan cercle centrage c'].nominal_element)
		except:		
			MCAD_ELEMENT=gom.script.primitive.create_plane_by_point_normal (
				name='Plan cercle centrage c', 
				normal=gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage], 
				point=gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage])
			self.toDelete.append(gom.app.project.inspection['Plan cercle centrage c'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Plan cercle centrage c']])

		# Création droite d'intersec plan cercle / plan coupe
		try:
			print(gom.app.project.inspection['Droite cercle centrage c'].nominal_element)
		except:		
			MCAD_ELEMENT=gom.script.primitive.create_line_by_intersection (
				name='Droite cercle centrage c', 
				plane1=gom.app.project.inspection['Plan cercle centrage c'], 
				plane2=gom.app.project.inspection['Plan Coupe projection c'])
			self.toDelete.append(gom.app.project.inspection['Droite cercle centrage c'])	
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Droite cercle centrage c']])

		try:
			print(gom.app.project.inspection['Point cercle centrage 1 c'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_point_by_line_intersection (
				intersect_element={'projection_type': 'curve', 'target': gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage]}, 
				line=gom.app.project.inspection['Droite cercle centrage c'], 
				name='Point cercle centrage 1 c', 
				point_number=1.00000000e+00)
			self.toDelete.append(gom.app.project.inspection['Point cercle centrage 1 c'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Point cercle centrage 1 c']])

		try:
			print(gom.app.project.inspection['Point cercle centrage 2 c'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_point_by_line_intersection (
				intersect_element={'projection_type': 'curve', 'target': gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage]}, 
				line=gom.app.project.inspection['Droite cercle centrage c'], 
				name='Point cercle centrage 2 c', 
				point_number=2.00000000e+00)
			self.toDelete.append(gom.app.project.inspection['Point cercle centrage 2 c'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Point cercle centrage 2 c']])
		
		pointCercleCentrage='Point cercle centrage 1 c'
		try:
			if gom.app.project.inspection['Point cercle centrage 2 c'].center_coordinate.z < gom.app.project.inspection['Point cercle centrage 1 c'].center_coordinate.z:
				pointCercleCentrage='Point cercle centrage 2 c'
			else:
				pointCercleCentrage='Point cercle centrage 1 c'
		except:
			self.log.info("!!!!!!!! Coordonnées y des point intersec cercle centrage non calculables." + str(gom.app.project.inspection['Point cercle centrage 2 c']))
		
		try:
			print(gom.app.project.inspection['Point cercle centrage c'].nominal_element)
		except:
					
			MCAD_ELEMENT=gom.script.primitive.create_surface_point (
				name='Point cercle centrage c', 
				normal=gom.app.project.inspection['Point centre section 1 c'], 
				point=gom.app.project.inspection[pointCercleCentrage])
			self.toDelete.append(gom.app.project.inspection['Point cercle centrage c'])
			MCAD_ELEMENT=gom.script.inspection.measure_by_intersection_with_mesh (
				elements=[gom.app.project.inspection['Point cercle centrage c']])
				
		try:
			print(gom.app.project.inspection['Point cercle centrage c bis'].nominal_element)
		except:		
			MCAD_ELEMENT=gom.script.primitive.create_surface_point (
				name='Point cercle centrage c bis', 
				normal={'glue_transformed': False, 'inverted': True, 'target': gom.app.project.inspection['Point centre section 1 c'], 'type': 'normal'},
				point=gom.app.project.inspection[pointCercleCentrage])
				
			self.toDelete.append(gom.app.project.inspection['Point cercle centrage c bis'])
			MCAD_ELEMENT=gom.script.inspection.measure_by_intersection_with_mesh (
				elements=[gom.app.project.inspection['Point cercle centrage c bis']])

		# Création d'une série de mesure
		for i in [mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True]:
			actMs=i
		print(actMs)
		scan=[]
		for i in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements:
			if i.type == "scan":
				scan.append(i.name)

		try:
			gom.script.cad.delete_element (
			elements=[gom.app.project.measurement_series['Temp']], 
			with_measuring_principle=True)
		except:
			pass
		gom.script.atos.create_measurement_series (
			measurement_series=gom.app.project.measurement_series[actMs], 
			name='Temp')
		

		try:			
			try:
				MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
					consider_only_not_computed_elements=True, 
					consider_reference_points=True, 
					elements=[gom.app.project.inspection['Point cercle centrage c']],
					measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
			except:
				try:
					MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
					consider_only_not_computed_elements=False, 
					consider_reference_points=True, 
					elements=[gom.app.project.inspection['Point cercle centrage c']],
					measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
				except:
					MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
						consider_only_not_computed_elements=False, 
						consider_reference_points=False, 
						elements=[gom.app.project.inspection['Point cercle centrage c']],
						measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
		except Exception as e:
			self.log.info("Can't create measurement position with Point cercle centrage c : " + str(e.args[0]) + " - " + str(e.args[1]))
			if e.args[0] == "AUTO-0301":
				try:
					try:
						MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
							consider_only_not_computed_elements=True, 
							consider_reference_points=True, 
							elements=[gom.app.project.inspection['Point cercle centrage c bis']],
							measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
					except:
						try:
							MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
							consider_only_not_computed_elements=False, 
							consider_reference_points=True, 
							elements=[gom.app.project.inspection['Point cercle centrage c bis']],
							measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
						except:
							MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
								consider_only_not_computed_elements=False, 
								consider_reference_points=False, 
								elements=[gom.app.project.inspection['Point cercle centrage c bis']],
								measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
				except Exception as e:
					self.log.info("Can't create measurement position with Point cercle centrage c bis : " + str(e.args[0]) + " - " + str(e.args[1]))

		gom.interactive.atos.define_active_measurement_series (measurement_series=gom.app.project.measurement_series[actMs])
		
		gom.script.sys.copy_to_clipboard (elements=[gom.app.project.measurement_series['Temp'].measurements['M1']])
		gom.script.sys.paste_from_clipboard (
			destination=[gom.app.project.measurement_series[actMs].measurements['H2']], 
			insert_before_measurement=True)		
		gom.script.cad.delete_element (
			elements=[gom.app.project.measurement_series['Temp']], 
			with_measuring_principle=True)

		gom.interactive.atos.define_active_measurement_series (measurement_series=gom.app.project.measurement_series[actMs])
		
		scan2=[]
		for i in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements:
			if i.type == "scan":
				if i.name not in scan:
					scan2.append(i.name)
		self.log.info(scan)
		self.log.info(scan2)
		gom.script.automation.recalculate_path_segment (
			allow_flip=True, 
			allow_re_sorting=False, 
			measurements=[gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements[scan2[0]]], 
			move_additional_axis=True)
		gom.script.sys.edit_properties (
			data=[gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements[scan2[0]]], 
			elem_name=Globals.SETTINGS.nomMesureCentre)
		self.log.info("Fin fonction createCentrePosition")

	def createCentrageSectionPosition(self):
		self.log.info("Début fonction createCentrageSectionPosition")
		self.log.info("Alignement actif : " + str([align.name for align in gom.app.project.alignments if align.is_active == True][0]))
		# Création plan ajusté sur section 1
		try:
			print(gom.app.project.inspection['Plan section 1 p'].nominal_element)
		except:
			gom.script.selection3d.deselect_all ()
			gom.script.cad.show_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
			gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
			MCAD_ELEMENT=gom.script.primitive.create_fitting_plane (
				method='best_fit', 
				name='Plan section 1 p', 
				sigma=3)
			self.toDelete.append(gom.app.project.inspection['Plan section 1 p'])	
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Plan section 1 p']])
		
		# Création cercle sur section 1
		try:
			print(gom.app.project.inspection['Cercle section 1 p'].nominal_element)
		except:
			gom.script.selection3d.deselect_all ()
			gom.script.cad.show_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
			gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSection]])
			MCAD_ELEMENT=gom.script.primitive.create_auto_nominal_circle (
				name='Cercle section 1 p')			
			MCAD_ELEMENT=gom.script.inspection.measure_by_fitting_element (
				actual=gom.ActualReference (gom.app.project.inspection[Globals.SETTINGS.nomSection]), 
				elements=[gom.app.project.inspection['Cercle section 1 p']], 
				fill_gaps=True, 
				limit_selection_depending_on_geometry=True, 
				method='best_fit', 
				restrict_actual_selection_to_nominal=True, 
				sigma=3)		
			self.toDelete.append(gom.app.project.inspection['Cercle section 1 p'])
		
		# Création point du centre du cercle
		try:
			print(gom.app.project.inspection['Point centre section 1 p'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_surface_point (
				name='Point centre section 1 p', 
				point=gom.app.project.inspection['Cercle section 1 p'])
			self.toDelete.append(gom.app.project.inspection['Point centre section 1 p'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Point centre section 1 p']])
		
		# Création d'un plan de rotation à partir du plan X (par défaut 0°) par rapport au point centre du cercle  
		try:
			print(gom.app.project.inspection['Plan Coupe projection p'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_plane_by_rotation (
				angle=Globals.SETTINGS.anglePlanSection*math.pi/180, 
				axis=gom.app.project.inspection['Point centre section 1 p'], 
				name='Plan Coupe projection p', 
				normal={'direction': gom.Vec3d (1.00000000e+00, 0.00000000e+00, 0.00000000e+00), 'point': gom.Vec3d (0.00000000e+00, 0.00000000e+00, 0.00000000e+00), 'type': 'projected'}, 
				point=gom.app.project.inspection['Point centre section 1 p'])
			self.toDelete.append(gom.app.project.inspection['Plan Coupe projection p'])
			gom.script.primitive.create_linked_actual_element (elements=[gom.app.project.inspection['Plan Coupe projection p']])
		
		# Création de la droite d'intersection entre les deux plans précédents
		try:
			print(gom.app.project.inspection['Droite section 1 p'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_line_by_intersection (
				name='Droite section 1 p', 
				plane1=gom.app.project.inspection['Plan Coupe projection p'], 
				plane2=gom.app.project.inspection['Plan section 1 p'])
			self.toDelete.append(gom.app.project.inspection['Droite section 1 p'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Droite section 1 p']])
		
		# Création du point d'intersection entre la droite et la section -> prendre le plus petit sur X
		try:
			print(gom.app.project.inspection["Point section intersec 1 p"].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_point_by_line_intersection (
				intersect_element={'projection_type': 'curve', 'target': gom.app.project.inspection[Globals.SETTINGS.nomSection]}, 
				line=gom.app.project.inspection['Droite section 1 p'], 
				name="Point section intersec 1 p", 
				point_number=1.00000000e+00)
			self.toDelete.append(gom.app.project.inspection["Point section intersec 1 p"])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection["Point section intersec 1 p"]])
			
		try:
			print(gom.app.project.inspection["Point section intersec 2 p"].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_point_by_line_intersection (
				intersect_element={'projection_type': 'curve', 'target': gom.app.project.inspection[Globals.SETTINGS.nomSection]}, 
				line=gom.app.project.inspection['Droite section 1 p'], 
				name="Point section intersec 2 p", 
				point_number=2.00000000e+00)
			self.toDelete.append(gom.app.project.inspection["Point section intersec 2 p"])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection["Point section intersec 2 p"]])
		
		pointIntersec="Point section intersec 2 p"
		try:
			if gom.app.project.inspection["Point section intersec 2 p"].center_coordinate.z < gom.app.project.inspection["Point section intersec 1 p"].center_coordinate.z:
				pointIntersec="Point section intersec 2 p"
			else:
				pointIntersec="Point section intersec 1 p"
		except:
			self.log.info("!!!!!!!! Coordonnées y des point intersec non calculables." + str(gom.app.project.inspection["Point section intersec 2 p"]))
		
		try:
			print(gom.app.project.inspection["Point section 2 p"].nominal_element)
		except:		
			MCAD_ELEMENT=gom.script.primitive.create_surface_point (
				name="Point section 2 p", 
				normal=gom.app.project.inspection[pointIntersec], 
				point=gom.app.project.inspection[pointIntersec])
			self.toDelete.append(gom.app.project.inspection["Point section 2 p"])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection["Point section 2 p"]])
		
		# Création cercle centrage si non existant
		try:
			print(gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage].nominal_element)
		except:
			gom.script.cad.show_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSectionCentrage]])
			gom.script.selection3d.deselect_all ()
			gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.inspection[Globals.SETTINGS.nomSectionCentrage]])
			MCAD_ELEMENT=gom.script.primitive.create_auto_nominal_circle (
				name=Globals.SETTINGS.nomCercleSectionCentrage)
			MCAD_ELEMENT=gom.script.inspection.measure_by_fitting_element (
				actual=gom.ActualReference (gom.app.project.inspection[Globals.SETTINGS.nomSectionCentrage]), 
				elements=[gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage]], 
				fill_gaps=True, 
				limit_selection_depending_on_geometry=True, 
				method='best_fit', 
				restrict_actual_selection_to_nominal=True, 
				sigma=3)		
			self.toDelete.append(gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage])
		
		# Création plan sur cercle centrage
		try:
			print(gom.app.project.inspection['Plan cercle centrage p'].nominal_element)
		except:		
			MCAD_ELEMENT=gom.script.primitive.create_plane_by_point_normal (
				name='Plan cercle centrage p', 
				normal=gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage], 
				point=gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage])
			self.toDelete.append(gom.app.project.inspection['Plan cercle centrage p'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Plan cercle centrage p']])

		# Création droite d'intersec plan cercle / plan coupe
		try:
			print(gom.app.project.inspection['Droite cercle centrage p'].nominal_element)
		except:		
			MCAD_ELEMENT=gom.script.primitive.create_line_by_intersection (
				name='Droite cercle centrage p', 
				plane1=gom.app.project.inspection['Plan cercle centrage p'], 
				plane2=gom.app.project.inspection['Plan Coupe projection p'])
			self.toDelete.append(gom.app.project.inspection['Droite cercle centrage p'])	
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Droite cercle centrage p']])

		try:
			print(gom.app.project.inspection['Point cercle centrage 1 p'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_point_by_line_intersection (
				intersect_element={'projection_type': 'curve', 'target': gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage]}, 
				line=gom.app.project.inspection['Droite cercle centrage p'], 
				name='Point cercle centrage 1 p', 
				point_number=1.00000000e+00)
			self.toDelete.append(gom.app.project.inspection['Point cercle centrage 1 p'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Point cercle centrage 1 p']])

		try:
			print(gom.app.project.inspection['Point cercle centrage 2 p'].nominal_element)
		except:
			MCAD_ELEMENT=gom.script.primitive.create_point_by_line_intersection (
				intersect_element={'projection_type': 'curve', 'target': gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage]}, 
				line=gom.app.project.inspection['Droite cercle centrage p'], 
				name='Point cercle centrage 2 p', 
				point_number=2.00000000e+00)
			self.toDelete.append(gom.app.project.inspection['Point cercle centrage 2 p'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Point cercle centrage 2 p']])
		
		pointCercleCentrage='Point cercle centrage 1 p'
		try:
			if gom.app.project.inspection['Point cercle centrage 2 p'].center_coordinate.z < gom.app.project.inspection['Point cercle centrage 1 p'].center_coordinate.z:
				pointCercleCentrage='Point cercle centrage 2 p'
			else:
				pointCercleCentrage='Point cercle centrage 1 p'
		except:
			self.log.info("!!!!!!!! Coordonnées y des point intersec cercle centrage non calculables." + str(gom.app.project.inspection['Point cercle centrage 2 p']))
		
		try:
			print(gom.app.project.inspection['Point cercle centrage p'].nominal_element)
		except:		
			MCAD_ELEMENT=gom.script.primitive.create_surface_point (
				name='Point cercle centrage p', 
				normal=gom.app.project.inspection[Globals.SETTINGS.nomCercleSectionCentrage], 
				point=gom.app.project.inspection[pointCercleCentrage])
			self.toDelete.append(gom.app.project.inspection['Point cercle centrage p'])
			gom.script.inspection.inspect_by_referenced_construction (elements=[gom.app.project.inspection['Point cercle centrage p']])

		try:
			print(gom.app.project.inspection['Point projection p'].nominal_element)
		except:	
			MCAD_ELEMENT=gom.script.primitive.create_theoretical_edge_point (
				distance1=1.00000000e+01, 
				distance2=1.00000000e+01, 
				name='Point projection p', 
				point1=gom.app.project.inspection['Point cercle centrage p'], 
				point2=gom.app.project.inspection[pointIntersec])
			self.toDelete.append(gom.app.project.inspection['Point projection p'])
			MCAD_ELEMENT=gom.script.inspection.measure_by_intersection_with_mesh (
			check_plausibility=True, 
			elements=[gom.app.project.inspection['Point projection p']])

		# Création d'une série de mesure
		for i in [mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True]:
			actMs=i
		print(actMs)
		self.log.info("1")	
		scan=[]
		for i in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements:
			if i.type == "scan":
				scan.append(i.name)
		self.log.info("2")
		try:
			gom.script.cad.delete_element (
			elements=[gom.app.project.measurement_series['Temp']], 
			with_measuring_principle=True)
		except:
			pass
		gom.script.atos.create_measurement_series (
			measurement_series=gom.app.project.measurement_series[actMs], 
			name='Temp')
			
			
		try:
			MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
				consider_only_not_computed_elements=True, 
				consider_reference_points=True, 
				elements=[gom.app.project.inspection['Point projection p']],
				measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
		except:
			try:
				MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
				consider_only_not_computed_elements=False, 
				consider_reference_points=True, 
				elements=[gom.app.project.inspection['Point projection p']],
				measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
			except:
				MCAD_ELEMENT=gom.script.automation.create_measurement_positions (
					consider_only_not_computed_elements=False, 
					consider_reference_points=False, 
					elements=[gom.app.project.inspection['Point projection p']],
					measurement_series_for_reuse=[gom.app.project.measurement_series['Temp']])
		gom.interactive.atos.define_active_measurement_series (measurement_series=gom.app.project.measurement_series[actMs])
		
		gom.script.sys.copy_to_clipboard (elements=[gom.app.project.measurement_series['Temp'].measurements['M1']])
		gom.script.sys.paste_from_clipboard (
			destination=[gom.app.project.measurement_series[actMs].measurements['H2']], 
			insert_before_measurement=True)		
		gom.script.cad.delete_element (
			elements=[gom.app.project.measurement_series['Temp']], 
			with_measuring_principle=True)

		gom.interactive.atos.define_active_measurement_series (measurement_series=gom.app.project.measurement_series[actMs])					
		scan2=[]
		for i in gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements:
			if i.type == "scan":
				if i.name not in scan:
					scan2.append(i.name)
		gom.script.automation.recalculate_path_segment (
			allow_flip=True, 
			allow_re_sorting=False, 
			measurements=[gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements[scan2[0]]], 
			move_additional_axis=True)
		gom.script.sys.edit_properties (
			data=[gom.app.project.measurement_series[[mseries.name for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==True][0]].measurements[scan2[0]]], 
			elem_name=Globals.SETTINGS.nomMesureProjection)

	def min_check(self, opt):
		
		#Recherche de l'étiquette min
		min = []
		for label in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'inspection', 'object_family', 'deviation_label', 'type', 'deviation_label_surface']}) :
			if label.deviation_label_computation_mode == "minimum":
				print(label)
				label_min = label	
			else:
				print("pass")
				pass
				
		print(1)		
		align_list =[]
		for align in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'alignment']}):
			if align.name.lower().find("2") != -1:
				pass
			else:
				align_list.append(align)			
					
		#Calcul de la valeur mini pour chaque alignement
		for align in align_list:
			gom.script.manage_alignment.set_alignment_active (cad_alignment=align)
			gom.script.sys.recalculate_elements (elements=label_min)
			min.append(label_min.get ('result_dimension.deviation'))
			print(min)
		
		inf = [] 
		for value in min :
			if value <= opt:
				inf.append(False)
			else :
				inf.append(True) #retourne True si pour un des alignement, le mini est supérieur à l'optimal
				
		print(inf)
		
		if True in inf:
			pass #Si un des alignement permet un min > opt, alors on s'arrête là
		else: #Sinon on lance le balançage hauteur itératif
			self.balancage_Y()
			
	def balancage_Y(self):
		
		print("Balancage Y")
		
		#Listes
		
		align_list =[] #Liste des alignements réalisés
		min = [] #Liste des valeurs d'écart minimum
		
		
		
		
		gom.script.sys.recalculate_all_elements_automatically (enable=True)
		
		#Recherche de l'alignement RPS
		
		for align in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'alignment']}):
			if align.name.lower().find("1") != -1:
				RPS = align
				
		gom.script.manage_alignment.set_alignment_active (cad_alignment=RPS) #Active l'alignement RPS
		
		#Recherche de l'étiquette min, de la comparaison de surface liée, et de la CAO liée
		for label in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'inspection', 'object_family', 'deviation_label', 'type', 'deviation_label_surface']}) :
		
			if label.deviation_label_computation_mode == "minimum":
				label_min = label
			else:
				pass
				
		comp = label_min.referenced_inspection_1
		CAD = comp.nominal_element
		
	#gom.script.cad.show_element_exclusively (elements=CAD)
		
		
		#TEST : détermine la direction du déplacement à appliquer
		
		min_RPS = label_min.get ('result_dimension.deviation') #Valeur d'écart mini dans l'alignement RPS
		
		test = [-0.5,0.5] #Translations de test
		
		for i in test:
			
			gom.script.manage_alignment.set_alignment_active (
				cad_alignment=RPS, 
				movement_correction=None)
			
			CAD_ALIGNMENT=gom.script.alignment.set_matrix (
				csys=gom.app.project.nominal_elements['system_global_coordinate_system'], 
				name_expression='Balançage hauteur Y='+str("%.2f" %i), 
				parent_alignment=RPS, 
				rotation_mode='X-Y-Z', 
				rotation_x=0.00000000e+00, 
				rotation_y=0.00000000e+00, 
				rotation_z=0.00000000e+00, 
				translate_x=0.00000000e+00, 
				translate_y=i, 
				translate_z=0.00000000e+00)
			
			align_list.append(CAD_ALIGNMENT)
			
			gom.script.sys.recalculate_elements (elements=label_min) #Recalcul de l'écart min
			
			min.append(label_min.get ('result_dimension.deviation'))
		
		
		print(min_RPS)
		print(min)
		print(align_list)
		
		#On détermine l'évolution de l'écart : si il diminue, la translation correspondante sert de première itération
		for value in min:
			if value > min_RPS:
				id = min.index(value) 
				activ_alignement = align_list[id]
				gom.script.manage_alignment.set_alignment_active (cad_alignment=activ_alignement)
				t = test[id]
				align_list.remove(activ_alignement) #Liste de l'alignement inutile
				#On supprime l'alignement inutile
				gom.script.cad.delete_element (
					elements=align_list, 
					with_measuring_principle=True)
			else:
				pass
		
	
		align_list=[] #réinitialisation de la liste des alignements
		align_list.append(activ_alignement) #Alignement actif (première itération) ajouté à la liste	
	
	
		gom.script.cad.show_element (elements=label_min) #Affichage de l'étiquette
		gom.script.sys.recalculate_elements (elements=label_min) #Recalcul de l'écart min
		
		gom.script.cad.show_element_exclusively (elements=label_min)
		
		min = label_min.get ('result_dimension.deviation') #Détermination de l'écart min
		
		min_list = [min] #Liste des écarts min
		
		
		if t > 0:
			for i in range (2,11,1): #9 itérations supplémentaires
				i = i/2
				print("min = " + str(min))
				print("mouvement =" + str(i))
				
	
				
				#Création de l'alignement manuel avec la translation Y de valeur i
				gom.script.manage_alignment.set_alignment_active (
					cad_alignment=RPS, 
					movement_correction=None)
				
				CAD_ALIGNMENT=gom.script.alignment.set_matrix (
					csys=gom.app.project.nominal_elements['system_global_coordinate_system'], 
					name_expression='Balançage hauteur Y='+str("%.2f" %i), 
					parent_alignment=RPS, 
					rotation_mode='X-Y-Z', 
					rotation_x=0.00000000e+00, 
					rotation_y=0.00000000e+00, 
					rotation_z=0.00000000e+00, 
					translate_x=0.00000000e+00, 
					translate_y=i, 
					translate_z=0.00000000e+00)
				
				gom.script.sys.recalculate_elements (elements=label_min) #Recalcul de l'écart min
				
				activ_alignement = CAD_ALIGNMENT
				align_list.append(CAD_ALIGNMENT)
				print(align_list)
				min = label_min.get ('result_dimension.deviation') #Détermination du nouvel écart min	
				min_list.append(min)
				print(min_list)
					
			min_max = max(min_list) #Selection de l'écart min maximum dans la liste
		
			min_id = min_list.index(max(min_list)) #Index dans la liste
		
			activ_alignement = align_list[min_id] #Alignement lié
			
			gom.script.manage_alignment.set_alignment_active (cad_alignment=activ_alignement) #Active l'alignement lié
	
			align_list.remove(activ_alignement) #Liste des alignement inutiles
		
			#Supprime tous les autres alignement
			gom.script.cad.delete_element (
				elements=align_list, 
					with_measuring_principle=True)
	
		else:
			for i in range (-2,-11,-1): #9 itérations supplémentaires
				i = i/2
				print("min = " + str(min))
				print("mouvement =" + str(i))
				
				#Création de l'alignement manuel avec la translation Y de valeur i
				gom.script.manage_alignment.set_alignment_active (
					cad_alignment=RPS, 
					movement_correction=None)
				
				CAD_ALIGNMENT=gom.script.alignment.set_matrix (
					csys=gom.app.project.nominal_elements['system_global_coordinate_system'], 
					name_expression='Balançage hauteur Y='+str("%.2f" %i), 
					parent_alignment=RPS, 
					rotation_mode='X-Y-Z', 
					rotation_x=0.00000000e+00, 
					rotation_y=0.00000000e+00, 
					rotation_z=0.00000000e+00, 
					translate_x=0.00000000e+00, 
					translate_y=i, 
					translate_z=0.00000000e+00)
				
				gom.script.sys.recalculate_elements (elements=label_min) #Recalcul de l'écart min
				
				activ_alignement = CAD_ALIGNMENT
				align_list.append(CAD_ALIGNMENT)
				print(align_list)
				min = label_min.get ('result_dimension.deviation') #Détermination du nouvel écart min	
				min_list.append(min)
				print(min_list)
					
			min_max = max(min_list) #Selection de l'écart min maximum dans la liste
		
			min_id = min_list.index(max(min_list)) #Index dans la liste
		
			activ_alignement = align_list[min_id] #Alignement lié
			
			gom.script.manage_alignment.set_alignment_active (cad_alignment=activ_alignement) #Active l'alignement lié
	
			align_list.remove(activ_alignement) #Liste des alignement inutiles
		
			#Supprime tous les autres alignement
			gom.script.cad.delete_element (
				elements=align_list, 
					with_measuring_principle=True)		
	
	#Création de la page de rapport
		
		for page in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'reports']}):
		
			if page.report_title.lower().replace('ç','c') == 'balancage hauteur':
				
				gom.script.sys.copy_to_clipboard (elements=page)
				
				gom.script.sys.paste_from_clipboard (destination=page)
				
				gom.script.sys.edit_properties (
					data=page, 
					elem_name='BALANCAGE HAUTEUR MACRO')
		
				gom.script.report.update_report_page (
					pages=page, 
					used_alignments='current', 
					used_digits='report', 
					used_legends='report', 
					used_stages='current', 
					used_units='report')
		
class newEvaluate(Evaluate.Evaluate, metaclass = Utils.MetaClassPatch):
	def perform( self, start_dialog_input ):
			'''
			This function starts the evaluation process.
	
			Returns:
			True  - if the successful i.e. all measurements successful and not deviation out of tolerance.
			False - otherwise
			'''
			if not Globals.SETTINGS.OfflineMode:
				self.envoi_info()
			result = self.original__perform( start_dialog_input )
			return result
		
	def envoi_info(self):
		self.log.info("Début fonction envoi_info")
		
		try :
	
			#Récupère l'adresse IP du contrôleur
			ip = gom.app.project.virtual_measuring_room['Virtual measuring room'].get ('controller_info[0].ip_address')
			
			hote = ip
			port = 1025
		except:
			RESULT=gom.script.sys.execute_user_defined_dialog (content='<dialog>' \
			' <title>Erreur d\'ouverture</title>' \
			' <style></style>' \
			' <control id="Close"/>' \
			' <position>center</position>' \
			' <embedding>always_toplevel</embedding>' \
			' <sizemode>automatic</sizemode>' \
			' <size width="289" height="155"/>' \
			' <content rows="1" columns="2">' \
			'  <widget type="image" row="0" column="0" rowspan="1" columnspan="1">' \
			'   <name>image</name>' \
			'   <tooltip></tooltip>' \
			'   <use_system_image>true</use_system_image>' \
			'   <system_image>system_message_warning</system_image>' \
			'   <data><![CDATA[AAAAAAAAAA==]]></data>' \
			'   <file_name></file_name>' \
			'   <keep_original_size>true</keep_original_size>' \
			'   <keep_aspect>true</keep_aspect>' \
			'   <width>0</width>' \
			'   <height>0</height>' \
			'  </widget>' \
			'  <widget type="display::text" row="0" column="1" rowspan="1" columnspan="1">' \
			'   <name>text</name>' \
			'   <tooltip></tooltip>' \
			'   <text>&lt;!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">' \
			'&lt;html>&lt;head>&lt;meta name="qrichtext" content="1" />&lt;style type="text/css">' \
			'p, li { white-space: pre-wrap; }' \
			'&lt;/style>&lt;/head>&lt;body style="    ">' \
			'&lt;p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">Aucun modèle n\'est ouvert !&lt;/p>&lt;/body>&lt;/html></text>' \
			'   <wordwrap>false</wordwrap>' \
			'  </widget>' \
			' </content>' \
			'</dialog>')
			
			sys.exit(0)
			
		try :
		
			#Recherche de la zone de travail active
			config=[mseries for mseries in gom.app.project.measuring_setups][0]
			config_name = config.get ('working_area.name')
		except:
			config_name =''
			
		if config_name == 'Zone de travail gauche':
		
			config_id = '7'
		elif config_name == 'Zone de travail droite':
			config_id = '8'
		else:
			RESULT=gom.script.sys.execute_user_defined_dialog (content='<dialog>' \
			' <title>Erreur d\'initialisation</title>' \
			' <style></style>' \
			' <control id="Close"/>' \
			' <position>center</position>' \
			' <embedding>always_toplevel</embedding>' \
			' <sizemode>automatic</sizemode>' \
			' <size width="336" height="119"/>' \
			' <content rows="1" columns="2">' \
			'  <widget type="image" row="0" column="0" rowspan="1" columnspan="1">' \
			'   <name>image</name>' \
			'   <tooltip></tooltip>' \
			'   <use_system_image>true</use_system_image>' \
			'   <system_image>system_message_warning</system_image>' \
			'   <data><![CDATA[AAAAAAAAAA==]]></data>' \
			'   <file_name></file_name>' \
			'   <keep_original_size>true</keep_original_size>' \
			'   <keep_aspect>true</keep_aspect>' \
			'   <width>0</width>' \
			'   <height>0</height>' \
			'  </widget>' \
			'  <widget type="display::text" row="0" column="1" rowspan="1" columnspan="1">' \
			'   <name>text</name>' \
			'   <tooltip></tooltip>' \
			'   <text>&lt;!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">' \
			'&lt;html>&lt;head>&lt;meta name="qrichtext" content="1" />&lt;style type="text/css">' \
			'p, li { white-space: pre-wrap; }' \
			'&lt;/style>&lt;/head>&lt;body style="    ">' \
			'&lt;p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">Aucune configuration de mesure n\'est active !&lt;/p>&lt;/body>&lt;/html></text>' \
			'   <wordwrap>false</wordwrap>' \
			'  </widget>' \
			' </content>' \
			'</dialog>')
			
			sys.exit(0)
		
		#Connexion
		connexion_avec_serveur = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		connexion_avec_serveur.connect((hote, port))
		self.log.info("Connexion établie avec le serveur sur le port {}".format(port))
		
		#Message binaire
		msg_a_envoyer = b""
		
		#Création du message socket message
		msg_a_envoyer = 'SetActiveSafetyAreaId,' + config_id
		
		#Encodage du message
		msg_a_envoyer = msg_a_envoyer.encode()
		
		#Affichage du message
		self.log.info("Message envoyé : " + str(msg_a_envoyer))
		
		# On envoie le message
		connexion_avec_serveur.send(msg_a_envoyer)
		
		#Affichage de la réponse
		msg_recu = connexion_avec_serveur.recv(1024)
		self.log.info("Message reçu : " + str(msg_recu.decode())) # peut planter s'il y a des accents
		
		#Fermeture de la connexion
		self.log.info("Fermeture de la connexion")
		connexion_avec_serveur.close()
		
		gom.script.sys.delay_script (time=0.1)
		
		
		self.log.info("Fin fonction envoi_info")

class newEvaluationAnalysis(Evaluate.EvaluationAnalysis, metaclass = Utils.MetaClassPatch):
	@staticmethod
	def export_results( result ):
		'''
		This function is called directly after the Approve/Disapprove button is clicked in the confirmation dialog or after async evaluation. It stores the
		current project to a directory. You may want to patch this function for example to export measurement
		information to your needs.

		Arguments:
		result - True if user approved measurement data, otherwise False
		'''
		rapportTracage=''
		for i in gom.app.project.reports:
			for j in gom.app.project.report_templates:
				try:
					if i.report_template==j.template['Consigne de traçage'].name or i.report_template==j.template['Instructions de traçage'].name:
						rapportTracage=i
				except:
					pass
		try:
			if rapportTracage!='':
				print('Fonction export_result mise à jour de l instruction de tracage.')
				gom.script.report.update_report_page (
				pages=[rapportTracage], 
				used_alignments='current', 
				used_digits='report', 
				used_legends='report', 
				used_stages='current', 
				used_units='report')
		except:
			print("Rapport de tracage non mis à jour.")
			
		if Globals.SETTINGS.reduireProjet:
			gom.script.atos.remove_measuring_data_from_project (remove_data='keep_all_images')
		( project_name, export_path ) = Evaluate.Evaluate.export_path_info()
		if not os.path.exists( export_path ):
			os.makedirs( export_path )

		if not result:
			project_name += Globals.SETTINGS.FailedPostfix
		if result=="tracer":
			project_name += Globals.SETTINGS.aTracerPostfix

		while True:
			try:
				print(os.path.join( export_path, project_name ))
				gom.script.sys.save_project_as( file_name = os.path.join( export_path, project_name ) )
			except Exception as error:
				res = Globals.DIALOGS.show_errormsg(
					Globals.LOCALIZATION.msg_save_error_title, Globals.LOCALIZATION.msg_save_error_message,
					Globals.SETTINGS.SavePath, True )
				if res == True:
					continue
			break

		if len( gom.app.project.reports ):
			try:
				gom.script.report.export_pdf ( 
					export_all_reports = True,
					file = os.path.join( export_path, project_name + '.pdf' ),
					jpeg_quality_in_percent = 100,
					reports = gom.app.project.reports )
			except:
				pass
		vdi_elements = list( gom.ElementSelection ( {'category': ['key', 'elements', 'explorer_category', 'inspection', 'object_family', 'vdi']} ) )
		if len( vdi_elements ):
			try:
				gom.script.vdi.export_test_protocol ( 
						element = vdi_elements[0],
						file = os.path.join( export_path, project_name + '_vdi.pdf' ) )
			except:
				pass
		
		custom_path_1 = Globals.SETTINGS.cheminFichierExcel
		if not os.path.exists(custom_path_1):
			os.makedirs(custom_path_1)
		used_template = gom.app.project.get( 'template.relative_path' )
		index = used_template[-1].find( '.project_template' )
		if index > 0:
			used_template = used_template[-1][:index]
		gom.script.table.export_table_contents (
			cell_separator=';', 
			codec='utf-8', 
			decimal_separator=',', 
			elements=gom.ElementSelection ({'category': ['key', 'elements', 'overview_explorer_categories', 'all_elements']}),
			file=os.path.join(custom_path_1, used_template+'_'+project_name + '.csv'),
			header_export=True, 
			line_feed='\r\n', 
			sort_column=0, 
			sort_order='ascending', 
			template_name=Globals.SETTINGS.excelTemplateName, 
			text_quoting='', 
			write_one_line_per_element=False)

	def polygonize( self ):
		mesh = self.original__polygonize( )
		
		gom.script.cad.show_element (elements=[gom.app.project.actual_elements[0]])

		gom.script.selection3d.select_all_points_of_element (elements=[gom.app.project.actual_elements[0]])
		
		gom.script.mesh.close_holes_automatically (
			delete_neighborhood_size=3, 
			filling_result='normal', 
			keep_point_selection=True, 
			max_edges_per_hole=1000, 
			max_hole_size=Globals.SETTINGS.interpollation_maillage)
		
		return mesh

class newStartUpV8(Workflow.StartUpV8, metaclass = Utils.MetaClassPatch):
	def __init__( self, logger ):
		self.original____init__(logger)
		self.resultatOp=True
				
	def set_additional_project_keywords ( self ):
		Globals.ADDITIONAL_PROJECTKEYWORDS = [
			# specify keywords as tuples of four values
			#   ('name', 'description', 'inputfield', 'optional')
			#        name: Name of your new project keyword (string)
			# description: The keyword description (string)
			#  inputfield: The name of the input field of the start dialog (string)
			#    optional: Specify if the kiosk should allow the start button also for an empty input value
			#              (True or False)
			# Example:
			#   ('mykeyword', 'My keyword description:', 'input_my_keyword', False)
			('of', 'N° OF', 'input_of', False)
			]
		
	def start_dialog_handler( self, widget ):
		'''
		The function is the dialog handler function
		'''
		if isinstance( widget, str ):
			pass
		elif widget.name == 'buttonNext':
			if self._check_input_values( self.dialog ):
				if not self.verifPresenceElements():
					Globals.SETTINGS.CurrentTemplate=None
					self.dialog.buttonNext.enabled = False
					self.dialog.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
					gom.script.sys.close_project ()
					return

		self.original__start_dialog_handler(widget)
		if widget == 'initialize':
			if self.is_widget_available( 'input_of' ):
				self.dialog.input_of.focus = True
		
		if isinstance( widget, str ):
			pass
		elif widget.name == 'buttonTemplateChoose':
			self.resultatOp=True
			self.resultatOp=self.checkModeOpe()
			self._enable_start_button()
			if not self.resultatOp:
				Globals.SETTINGS.CurrentTemplate=None
				self.dialog.buttonNext.enabled = False
				self.dialog.buttonTemplateChoose.text = Globals.LOCALIZATION.startdialog_button_template
				gom.script.sys.close_project ()
	
	def _enable_start_button( self ):
		'''
		This function is responsible to enable or disable the Start button depending on the user input.
		It enables the start button only when each input field of the default start dialog is not empty and the user chose a project template.
		'''
		if self.resultatOp:
			self.original___enable_start_button()
		
	def checkModeOpe(self):
		'''
		fonction perso
		'''
		def dialog_event_handler (widget):
			global resultatOpe
			if isinstance( widget, gom.Widget ) and widget.name == 'buttonOui':
				gom.script.sys.close_user_defined_dialog (dialog=Globals.DIALOGS.SECONDDIALOG)
				resultatOpe=True
			if isinstance( widget, gom.Widget ) and widget.name == 'buttonNo':
				gom.script.sys.close_user_defined_dialog (dialog=Globals.DIALOGS.SECONDDIALOG)
				resultatOpe=False
			pass
		
		Globals.DIALOGS.SECONDDIALOG.handler = dialog_event_handler
		used_template = gom.app.project.get( 'template.relative_path' )
		index = used_template[-1].find( '.project_template' )
		if index > 0:
			used_template = used_template[-1][:index]
		Globals.DIALOGS.SECONDDIALOG.text.text='<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd"><html><head><meta name="qrichtext" content="1" /><style type="text/css">p, li { white-space: pre-wrap; }</style></head><body style="    "><p align="center" style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:24pt; font-weight:600;">'+used_template+'</span></p></body></html>'
		gom.script.sys.show_user_defined_dialog (dialog=Globals.DIALOGS.SECONDDIALOG)
		
		return resultatOpe
		
	def createMissingElements(self):
		'''
		fonction perso
		'''
		self.log.info("Début fonction createMissingElements")
		Globals.SETTINGS.nomSectionCentrage = Globals.SETTINGS.nomSectionCentrage2
		print(1,Globals.SETTINGS.nomSectionCentrage)
		Globals.SETTINGS.nomSection = Globals.SETTINGS.nomSection2
		print(2,Globals.SETTINGS.nomSection)
		testSectionCentrage=True
		testNomSectionCentrage = unicodedata.normalize('NFKD', Globals.SETTINGS.nomSectionCentrage).encode('ASCII', 'ignore').decode()
		for i in [section.name for section in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'nominal', 'object_family', 'geometrical_element', 'type', 'nominal_section']})]:
			if testNomSectionCentrage.upper() in unicodedata.normalize('NFKD', i).encode('ASCII', 'ignore').decode().upper():
				Globals.SETTINGS.nomSectionCentrage=i
				testSectionCentrage=False
		testSection=True
		testNomSection = unicodedata.normalize('NFKD', Globals.SETTINGS.nomSection).encode('ASCII', 'ignore').decode()
		for i in [section.name for section in gom.ElementSelection ({'category': ['key', 'elements', 'explorer_category', 'nominal', 'object_family', 'geometrical_element', 'type', 'nominal_section']})]:
			if testNomSection.upper() in unicodedata.normalize('NFKD', i).encode('ASCII', 'ignore').decode().upper():
				Globals.SETTINGS.nomSection=i
				testSection=False		
		
		if testSectionCentrage or testSection:
			DIALOG=gom.script.sys.create_user_defined_dialog (content='<dialog>' \
' <title>Un élément et manquant</title>' \
' <style></style>' \
' <control id="Close"/>' \
' <position></position>' \
' <embedding></embedding>' \
' <sizemode></sizemode>' \
' <size height="217" width="372"/>' \
' <content columns="1" rows="4">' \
'  <widget type="display::text" rowspan="1" columnspan="1" row="0" column="0">' \
'   <name>text</name>' \
'   <tooltip></tooltip>' \
'   <text>&lt;!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">' \
'&lt;html>&lt;head>&lt;meta name="qrichtext" content="1" />&lt;style type="text/css">' \
'p, li { white-space: pre-wrap; }' \
'&lt;/style>&lt;/head>&lt;body style="    ">' \
'&lt;p align="center" style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">Le ou les éléments suivants sont manquants ou mal nommés.&lt;/p>' \
'&lt;p align="center" style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">Veuillez corriger le modèle de projet pour continuer.&lt;/p>&lt;/body>&lt;/html></text>' \
'   <wordwrap>false</wordwrap>' \
'  </widget>' \
'  <widget type="spacer::horizontal" rowspan="1" columnspan="1" row="1" column="0">' \
'   <name>spacer</name>' \
'   <tooltip></tooltip>' \
'   <minimum_size>0</minimum_size>' \
'   <maximum_size>-1</maximum_size>' \
'  </widget>' \
'  <widget type="label" rowspan="1" columnspan="1" row="2" column="0">' \
'   <name>label_1</name>' \
'   <tooltip></tooltip>' \
'   <text>Champ de description</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
'  <widget type="label" rowspan="1" columnspan="1" row="3" column="0">' \
'   <name>label_2</name>' \
'   <tooltip></tooltip>' \
'   <text>Champ de description</text>' \
'   <word_wrap>false</word_wrap>' \
'  </widget>' \
' </content>' \
'</dialog>')
			if testSectionCentrage:
				DIALOG.label_1.text=Globals.SETTINGS.nomSectionCentrage
			else:
				DIALOG.label_1.text=""
			if testSection:
				DIALOG.label_2.text=Globals.SETTINGS.nomSection
			else:
				DIALOG.label_2.text=""				
			
			#
			# Event handler function called if anything happens inside of the dialog
			#
			def dialog_event_handler (widget):
				pass
			
			DIALOG.handler = dialog_event_handler
			
			RESULT=gom.script.sys.show_user_defined_dialog (dialog=DIALOG)
			return True
		else:
			return False
		
	def verifPresenceElements(self):
		'''
		fonction perso
		'''
		self.log.info("Début fonction verifPresenceElements")
		try:
			if not self.createMissingElements():
				self.log.info("Fin fonction verifPresenceElements")
				return True
			else:
				self.log.info("Elements manquants. Fermeture du Kiosk")
				return False
		except:
			self.log.info("Error while createMissingElements function called")
			return False
		return False
	
class patchedMeasureChecks(Verification.MeasureChecks, metaclass = Utils.MetaClassPatch):
	def __init__( self, logger, parent ):
		'''
		initialize function
		'''
		self.original____init__(logger, parent)
		self.retry_err = 0
		
	def analyze_error( self, error, series, retry_allowed = False, errorlog = None ):
		'''
		analyze measurement exception
		@return VerificationState value
		'''
		self.log.info('start overriding MeasureCheck.analyze_error')
		result = self.original__analyze_error(error, series, retry_allowed,errorlog)
		if result == VerificationState.Abort:
			if error.args[0] in ['MPROJ-0021'] and self.retry_err < 1:
				self.retry_err += 1
				self.log.error( 'Unrecoverable robot position detected: {}'.format( error ) )
				if self.try_getting_position():
					return VerificationState.Retry
				else:
					return VerificationState.Abort
			else:
				return result
		else:
			return result
			
	def try_getting_position(self):
		first_last_pos=None
		index=0
		measure=[]
		self.log.info('start try_getting_position')
		try:
			activeMs=[mseries for mseries in gom.app.project.measurement_series if mseries.get('type') == 'atos_measurement_series' and mseries.is_active==gom.MeasurementListActiveState (True)][0]
		except:
			self.log.info('no active msserie')
			return False
		try:
			activePosition=[mpos for mpos in activeMs.measurements if mpos.get('object_family') == 'measurement_series' and mpos.is_current_position][0]
		except:
			activePosition=''
		if len(activePosition):
			self.log.info('in known position : ' + str(activePosition))
			return True
		for i in activeMs.measurements:
			measure.append(i)
		measure.reverse()
		for i in measure:
			if i.type == "scan":
				if i.measurement_transformation != None:
					first_last_pos=activeMs.measurements[index]
					break
				index += 1
		if first_last_pos!=None:
			try:
				self.log.info('trying to move to position : ' + str(first_last_pos))
				gom.interactive.automation.move_to_position (measurement=first_last_pos)
			except:
				self.log.info("Can't move to position : "+ str(first_last_pos))
		activePosition=[mpos for mpos in activeMs.measurements if mpos.get('object_family') == 'measurement_series' and mpos.is_current_position][0]
		if len(activePosition):
			self.log.info('now in known position')
			return True
		else:
			self.log.info('not in known position')
			return False

############## Classes for keyboard input ################

class KeyBdInput(ctypes.Structure):
	_fields_ = [("wVk", ctypes.c_ushort),
				("wScan", ctypes.c_ushort),
				("dwFlags", ctypes.c_ulong),
				("time", ctypes.c_ulong),
				("dwExtraInfo", PUL)]

class HardwareInput(ctypes.Structure):
	_fields_ = [("uMsg", ctypes.c_ulong),
				("wParamL", ctypes.c_short),
				("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
	_fields_ = [("dx", ctypes.c_long),
				("dy", ctypes.c_long),
				("mouseData", ctypes.c_ulong),
				("dwFlags", ctypes.c_ulong),
				("time",ctypes.c_ulong),
				("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
	_fields_ = [("ki", KeyBdInput),
				("mi", MouseInput),
				("hi", HardwareInput)]

class Input(ctypes.Structure):
	_fields_ = [("type", ctypes.c_ulong),
				("ii", Input_I)]

def PressKey(hexKeyCode):
	extra = ctypes.c_ulong(0)
	ii_ = Input_I()
	ii_.ki = KeyBdInput( hexKeyCode, 0x48, 0, 0, ctypes.pointer(extra) )
	x = Input( ctypes.c_ulong(1), ii_ )
	SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


