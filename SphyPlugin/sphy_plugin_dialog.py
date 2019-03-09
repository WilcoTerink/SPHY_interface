# -*- coding: utf-8 -*-
# The SPHY model interface plugin for QGIS:
# A QGIS plugin that allows the user to setup the SPHY model, run the model
# and visualize results.
#
# Copyright (C) 2014  Wilco Terink
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Email: terinkw@gmail.com

#-Authorship information-###################################################################
__author__ = "Wilco Terink"
__copyright__ = "Wilco Terink"
__license__ = "GPL"
__version__ = "1.0.0"
__email__ = "terinkw@gmail.com"
__date__ ='1 January 2017'
############################################################################################
"""
/***************************************************************************
 SphyPluginDialog
                                 A QGIS plugin
 Interface for the SPHY model
                             -------------------
        begin                : 2014-09-09
        git sha              : $Format:%H$
        copyright            : (C) 2014 by Wilco Terink
        email                : terinkw@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os, ConfigParser, subprocess, datetime, string, time, shutil, traceback, csv, glob, calendar

from functools import partial

# matlabtools
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from PyQt4 import QtGui, uic, QtCore

import processing

from qgis.utils import iface
from qgis.core import *

# FORM_CLASS, _ = uic.loadUiType(os.path.join(
#     os.path.dirname(__file__), 'sphy_plugin_dialog_base.ui'))


# class SphyPluginDialog(QtGui.QDialog, FORM_CLASS):
from sphy_plugin_dialog_base import Ui_sphyDialog

# worker class to run the model in a thread
class ModelWorker(QtCore.QObject):
    '''Example worker'''
    def __init__(self, filename, ts):
        QtCore.QObject.__init__(self)
        self.filename = filename
        self.killed = False
        self.process = None
        self.steps = ts + 55  # is approx. the number of cmd lines shown before model time steps start
    def run(self):
        try:
            if self.killed is False:
                self.process = subprocess.Popen(
                    self.filename,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=False
                    )
                  
                proc = self.process.stdout
                progress_count = 0  
                for line in iter(proc.readline, ''):
                    progress_count += 1
                    # terminate the model run if there is an error in the path settings of pcraster bin and python exe,
                    # or if the user cancels the model run
                    if line.find("Traceback")>=0 or self.killed:
                        self.process = None
                        break
                    self.progBar.emit(progress_count / float(str(self.steps)) * 100)
                    self.cmdProgress.emit(line)
 
        except Exception, e:
            # forward the exception upstream
            self.error.emit(e, traceback.format_exc())
        self.finished.emit(self.process)
    def kill(self):
        self.killed = True
        self.process.kill()
         
    finished = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(Exception, basestring)
    cmdProgress = QtCore.pyqtSignal(object)
    progBar = QtCore.pyqtSignal(float)
    
    
# Class for converting maps in a worker thread
class convertMapWorker(QtCore.QObject):
    def __init__(self, date, ts, outpath, outputFileNameDict, pcrbinpath):
        QtCore.QObject.__init__(self)
        self.months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        self.dim = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        self.date = date
        self.timeSteps = ts
        self.outputPath = outpath
        self.outputFileNameDict = outputFileNameDict
        self.pcrBinPath = pcrbinpath
    def run(self):
        process = None
        outpath = (self.outputPath).replace("\\","/")
        os.chdir(outpath)
        self.cmdProgress.emit("Converting the output map files. Can take some time depending on number reported ouput maps.")
        self.cmdProgress.emit("...")
        try:
            for i in range(1, self.timeSteps + 1):
                # leap year settings
                if calendar.isleap(self.date.year):
                    self.dim[1] = 29
                    ydays = 366
                else:
                    self.dim[1] = 28
                    ydays = 365
                d = self.date.day
                if d<10:
                    dd = "0" + str(d)
                else:
                    dd = str(d)
                m = self.date.month
                if m<10:
                    mm = "0" + str(m)
                else:
                    mm = str(m)
                # pcraster extension    
                if i<10:
                    pcrext = '00.00'+str(i)
                elif i<100:
                    pcrext = '00.0'+str(i)
                elif i<1000:
                    pcrext = '00.'+str(i)
                elif i<10000:
                    nr = str(i)
                    thous = nr[0]
                    hund = nr[1:4]
                    pcrext = '0'+thous+'.'+hund
                else:
                    nr = str(i)
                    thous = nr[0:2]
                    hund = nr[2:5]
                    pcrext = ''+thous+'.'+hund
                # loop over the output file name dictionary to check if file exists
                for key in self.outputFileNameDict:
                    files = glob.glob(outpath + key + "*" + pcrext)
                    if files:
                        for f in files:
                            file = f.replace("\\", "/")
                            file = file.split(outpath)[1]
                            # check if it concerns a monthly or annual map file
                            if key + "M" in file or key + "Y" in file:
                                # determine if conversion of units is required
                                try:
                                    convertflag = self.outputFileNameDict[key][1]
                                except:
                                    convertflag = None
                                # for monthly maps:
                                if key + "M" in file:
                                    if convertflag:
                                        command = "pcrcalc temp.map = " + file + " / " + str(self.dim[m-1])
                                    else:
                                        command = "pcrcalc temp.map = " + file
                                    outfile = key + "_" + str(self.date.year) + self.months[m-1] + ".map"
                                # for annual maps
                                else:
                                    if convertflag:
                                        command = "pcrcalc temp.map = " + file + " / " + str(ydays)
                                    else:
                                        command = "pcrcalc temp.map = " + file
                                    outfile = key + "_" + str(self.date.year) + ".map"
                                subprocess.Popen(command, env={"PATH": str(self.pcrBinPath)},shell=True).wait()
                                shutil.move(outpath + "temp.map", outpath + outfile)
                                os.remove(outpath + file)
                            else:
                                shutil.move(outpath + file, outpath + key + "_" + str(self.date.year) + mm + dd + ".map")
                self.date = self.date + datetime.timedelta(days=1)
                
            process = True
            
        except Exception, e:
            self.error.emit(e, traceback.format_exc())

        self.finished.emit(process)
            
    cmdProgress = QtCore.pyqtSignal(object)
    finished = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(Exception, basestring)
          
class SphyPluginDialog(QtGui.QDialog, Ui_sphyDialog):
    def __init__(self, parent=None):
        """Constructor."""
        super(SphyPluginDialog, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        self.setWindowIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__),"icon.png")))
        
        #- self.exitDate is used to check whether it needs to update the configfile after dates has been changed. This value is always True
        #- except when a new project is created or a project is openened, because then it already reads the date from the config, so updating the 
        #- config is then not required
        self.exitDate = False
        
        """
        If QGIS is loaded, check if there is a recent SPHY config file in the registry
        if not, then create a reference to the SPHY config template and initialize the plugin
        with that template file.
        """

        # Check if an existing config file is present from the most recent project
        self.currentConfig = ConfigParser.ConfigParser(allow_no_value = True)
        self.settings = QtCore.QSettings()
        #if self.settings.value("sphyplugin/currentConfig"):
        self.currentConfigFileName = self.settings.value("sphyplugin/currentConfig")
        try:
            self.currentConfig.read(self.currentConfigFileName)
            self.currentProject = True
            self.tab.setEnabled(1)
            self.sphyLocationPath = self.settings.value("sphyplugin/sphypath")
            if self.sphyLocationPath is None:
                self.sphyLocationPath = "./"
            self.pcrBinPath = self.settings.value("sphyplugin/pcrBinPath")
            if self.pcrBinPath is None:
                self.pcrBinPath = "./"
            self.pythonExe = self.settings.value("sphyplugin/pythonExe")
            if self.pythonExe is None:
                self.pythonExe = "./"
            self.initGuiConfigMap()
    #                 self.updateDate()
            # try to read crs
            self.crs = self.settings.value("sphyplugin/crs")
            if self.crs is None:
                self.crs = 4326  # set to default EPSG 4326 WGS84 
        except:
            self.currentProject = False
            self.tab.setEnabled(0)
            self.sphyLocationPath = "./"
            self.pcrBinPath = "./"
            self.pythonExe = "./"
            self.crs = 4326 # set to default EPSG 4326 WGS84
        
        self.sphyPathLineEdit.setText(self.sphyLocationPath)
        self.pcrBinPathLineEdit.setText(self.pcrBinPath)
        self.pythonExeLineEdit.setText(self.pythonExe)
        self.crsSpinBox.setValue(self.crs)
            
        self.saveAsButton.setDisabled(1)
        self.saveButton.setDisabled(1)
        
        self.iface = iface
        self.featFinder = None
        
        """
        Four project buttons: New project, open project, save project, and save as. This interacts with the
        file in the registry.
        """
        # If New project button is clicked
        self.newButton.clicked.connect(self.createNewProject)
        # If open project button is clicked
        self.openButton.clicked.connect(self.openProject)
        # If Save as button is clicked
        self.saveAsButton.clicked.connect(self.saveAsProject)
        # If Save button is clicked
        self.saveButton.clicked.connect(self.saveProject)
        
        
        """
        General tab: Folder selection, simulation period, catchment settings
        """
        # Set folders
        self.selectSphyPathButton.clicked.connect(self.updatePath)
        self.selectInputPathButton.clicked.connect(self.updatePath)
        self.selectOutputPathButton.clicked.connect(self.updatePath)
        
        # Simulation period
        self.startDateEdit.dateChanged.connect(self.updateDate)
        self.endDateEdit.dateChanged.connect(self.updateDate)
        
        # EPSG setting changed (CRS)
        self.crsSpinBox.valueChanged.connect(self.changeCRS)
        
        # Catchment settings: Clone, DEM, Slope, Sub-basins, Stations
        self.selectCloneMapFileButton.clicked.connect(partial(self.updateMap, "GENERAL", "mask", "Clone", "Input", "General", 0))
        self.selectDemMapFileButton.clicked.connect(partial(self.updateMap, "GENERAL", "dem", "DEM", "Input", "General", 0))
        self.selectSlopeMapFileButton.clicked.connect(partial(self.updateMap, "GENERAL", "slope", "Slope", "Input", "General", 0))
        self.selectSubbasinMapFileButton.clicked.connect(partial(self.updateMap, "GENERAL", "sub", "Sub-basin", "Input", "General", 0))
        self.selectStationsMapFileButton.clicked.connect(partial(self.updateMap, "GENERAL", "locations", "Stations", "Input", "General", 0, True))
        
        """
        Climate tab: meteorological forcing map-series, meteorological parameters
        """
        # Meteorological forcing map-series
        self.selectPrecMapSeriesButton.clicked.connect(partial(self.updateMapSeries, "CLIMATE", "Prec", "precipitation"))
        self.selectAvgTempMapSeriesButton.clicked.connect(partial(self.updateMapSeries, "CLIMATE", "Tair", "average daily temperature"))
        self.selectMaxTempMapSeriesButton.clicked.connect(partial(self.updateMapSeries, "ETREF", "Tmax", "maximum daily temperature"))
        self.selectMinTempMapSeriesButton.clicked.connect(partial(self.updateMapSeries, "ETREF", "Tmin", "minimum daily temperature"))
        
        # Meteorological parameters
        self.selectLatitudeZonesMapButton.clicked.connect(partial(self.updateMap, "ETREF", "lat", "latitude zones", "Input", "Climate", 1))
        self.solarConstantDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "ETREF", "Gsc"))
        
        """
        Soils tab: rootzone and subzone maps, and parameters
        """
        # Rootzone physical maps
        self.selectRootFieldCapMapButton.clicked.connect(partial(self.updateMap,"SOIL", "RootFieldMap", "rootzone field capacity", "Input", "Soils", 2))
        self.selectRootSatMapButton.clicked.connect(partial(self.updateMap,"SOIL", "RootSatMap", "rootzone saturated content", "Input", "Soils", 2))
        self.selectRootPermWiltMapButton.clicked.connect(partial(self.updateMap, "SOIL", "RootDryMap", "rootzone permanent wilting point", "Input", "Soils", 2))
        self.selectRootWiltMapButton.clicked.connect(partial(self.updateMap, "SOIL", "RootWiltMap", "rootzone wilting point", "Input", "Soils", 2))
        self.selectRootSatCondMapButton.clicked.connect(partial(self.updateMap, "SOIL", "RootKsat", "rootzone saturated hydraulic conductivity", "Input", "Soils", 2))
        
        # Subzone physical maps
        self.selectSubFieldCapMapButton.clicked.connect(partial(self.updateMap, "SOIL", "SubFieldMap", "subzone field capacity", "Input", "Soils", 2))
        self.selectSubSatMapButton.clicked.connect(partial(self.updateMap, "SOIL", "SubSatMap", "subzone saturated content", "Input", "Soils", 2))
        self.selectSubSatCondMapButton.clicked.connect(partial(self.updateMap, "SOIL", "SubKsat", "subzone saturated hydraulic conductivity", "Input", "Soils", 2))

        # Rootzone parameters
        self.rootDepthSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SOILPARS", "RootDepthFlat", "rootDepthSpinBox"))
        self.rootDepthMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SOILPARS", "RootDepthFlat", "rootDepthLineEdit"))
        self.rootDepthSpinBox.valueChanged.connect(partial(self.updateValue, "SOILPARS", "RootDepthFlat"))
        self.selectRootDepthMapButton.clicked.connect(partial(self.updateMap, "SOILPARS", "RootDepthFlat", "rootzone thickness", "Input", "Soils", 2))
        
        # Subzone parameters
        self.subDepthSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SOILPARS", "SubDepthFlat", "subDepthSpinBox"))
        self.subDepthMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SOILPARS", "SubDepthFlat", "subDepthLineEdit"))
        self.subDepthSpinBox.valueChanged.connect(partial(self.updateValue, "SOILPARS", "SubDepthFlat"))
        self.selectSubDepthMapButton.clicked.connect(partial(self.updateMap, "SOILPARS", "SubDepthFlat", "subzone thickness", "Input", "Soils", 2))
        self.maxCapRiseSpinBox.valueChanged.connect(partial(self.updateValue, "SOILPARS", "CapRiseMax"))
        
        """
        Groundwater tab: layer thickness, saturated content, initial storage, basethreshold, deltaGw, alphaGw
        """
        # Groundwater layer thickness
        self.gwDepthSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "GwDepth", "gwDepthSpinBox"))
        self.gwDepthMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "GwDepth", "gwDepthLineEdit"))
        self.gwDepthSpinBox.valueChanged.connect(partial(self.updateValue, "GROUNDW_PARS", "GwDepth"))
        self.selectGwDepthMapButton.clicked.connect(partial(self.updateMap, "GROUNDW_PARS", "GwDepth", "groundwater layer thickness", "Input", "Groundwater", 3))
        
        # Groundwater saturated contents
        self.gwSatSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "GwSat", "gwSatSpinBox"))
        self.gwSatMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "GwSat", "gwSatLineEdit"))
        self.gwSatSpinBox.valueChanged.connect(partial(self.updateValue, "GROUNDW_PARS", "GwSat"))
        self.selectGwSatMapButton.clicked.connect(partial(self.updateMap, "GROUNDW_PARS", "GwSat", "groundwater saturated content", "Input", "Groundwater", 3))
        
        # Groundwater initial storage
        self.gwInitSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_INIT", "Gw", "gwInitSpinBox"))
        self.gwInitMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_INIT", "Gw", "gwInitLineEdit"))
        self.gwInitSpinBox.valueChanged.connect(partial(self.updateValue, "GROUNDW_INIT", "Gw"))
        self.selectGwInitMapButton.clicked.connect(partial(self.updateMap, "GROUNDW_INIT", "Gw", "initial groundwater storage", "Input", "Groundwater", 3))
        
        # Baseflow threshold
        self.baseThreshSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "BaseThresh", "baseThreshSpinBox"))
        self.baseThreshMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "BaseThresh", "baseThreshLineEdit"))
        self.baseThreshSpinBox.valueChanged.connect(partial(self.updateValue, "GROUNDW_PARS", "BaseThresh"))
        self.selectBaseThreshMapButton.clicked.connect(partial(self.updateMap, "GROUNDW_PARS", "BaseThresh", "baseflow threshold", "Input", "Groundwater", 3))
        
        # DeltaGw
        self.deltaGwSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "deltaGw", "deltaGwSpinBox"))
        self.deltaGwMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "deltaGw", "deltaGwLineEdit"))
        self.deltaGwSpinBox.valueChanged.connect(partial(self.updateValue, "GROUNDW_PARS", "deltaGw"))
        self.selectDeltaGwMapButton.clicked.connect(partial(self.updateMap, "GROUNDW_PARS", "deltaGw", "groundwater recharge delay time", "Input", "Groundwater", 3))
        
        # alphaGw
        self.alphaGwSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "alphaGw", "alphaGwDoubleSpinBox"))
        self.alphaGwMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GROUNDW_PARS", "alphaGw", "alphaGwLineEdit"))
        self.alphaGwDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "GROUNDW_PARS", "alphaGw"))
        self.selectAlphaGwMapButton.clicked.connect(partial(self.updateMap, "GROUNDW_PARS", "alphaGw", "alphGw", "Input", "Groundwater", 3))
        
        """
        Landuse tab: Land use map and Kc-table
        """ 
        self.selectLandUseMapButton.clicked.connect(partial(self.updateMap, "LANDUSE", "LandUse", "landuse map", "Input", "Land-use", 4))
        self.selectKcTableButton.clicked.connect(partial(self.updateTable, "LANDUSE", "CropFac", "crop coefficients"))
        
        """
        Glaciers tab: fraction maps and degree-day-factors
        """
        # Glacier fraction maps
        self.selectInitGlacFracMapButton.clicked.connect(partial(self.updateMap, "GLACIER_INIT", "GlacFrac" , "initial glacier fraction", "Input", "Glaciers", 5))
        self.selectCIFracMapButton.clicked.connect(partial(self.updateMap, "GLACIER", "GlacFracCI" , "clean ice covered glacier fraction", "Input", "Glaciers", 5))
        self.selectDBFracMapButton.clicked.connect(partial(self.updateMap, "GLACIER", "GlacFracDB" , "debris-covered glacier fraction", "Input", "Glaciers", 5))
        # Glacier runoff fraction
        self.glacRoFracSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GLACIER", "GlacF", "glacRoFracDoubleSpinBox"))
        self.glacRoFracMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GLACIER", "GlacF", "glacRoFracLineEdit"))
        self.glacRoFracDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "GLACIER", "GlacF"))
        self.selectGlacRoFracMapButton.clicked.connect(partial(self.updateMap, "GLACIER", "GlacF", "glacier runoff fraction", "Input", "Glaciers", 5))
        # DDFDG
        self.DDFDGSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GLACIER", "DDFDG", "DDFDGDoubleSpinBox"))
        self.DDFDGMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GLACIER", "DDFDG", "DDFDGLineEdit"))
        self.DDFDGDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "GLACIER", "DDFDG"))
        self.selectDDFDGMapButton.clicked.connect(partial(self.updateMap, "GLACIER", "DDFDG", "debris covered glacier degree-day-factor", "Input", "Glaciers", 5))
        # DDFG
        self.DDFGSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GLACIER", "DDFG", "DDFGDoubleSpinBox"))
        self.DDFGMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "GLACIER", "DDFG", "DDFGLineEdit"))
        self.DDFGDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "GLACIER", "DDFG"))
        self.selectDDFGMapButton.clicked.connect(partial(self.updateMap, "GLACIER", "DDFG", "clean-ice glacier degree-day-factor", "Input", "Glaciers", 5))        

        """
        Snow tab
        """
        # SnowIni
        self.snowIniSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SNOW_INIT", "SnowIni", "snowIniSpinBox"))
        self.snowIniMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SNOW_INIT", "SnowIni", "snowIniLineEdit"))
        self.snowIniSpinBox.valueChanged.connect(partial(self.updateValue, "SNOW_INIT", "SnowIni"))
        self.selectSnowIniMapButton.clicked.connect(partial(self.updateMap, "SNOW_INIT", "SnowIni", "initial snow storage", "Input", "Snow", 6))
        
        # SnowWatStore
        self.sWatStoreSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SNOW_INIT", "SnowWatStore", "sWatStoreSpinBox"))
        self.sWatStoreMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SNOW_INIT", "SnowWatStore", "sWatStoreLineEdit"))
        self.sWatStoreSpinBox.valueChanged.connect(partial(self.updateValue, "SNOW_INIT", "SnowWatStore"))
        self.selectSWatStoreMapButton.clicked.connect(partial(self.updateMap, "SNOW_INIT", "SnowWatStore", "initial snow water storage", "Input", "Snow", 6))
        
        # SnowSC
        self.snowSCSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SNOW", "SnowSC", "snowSCDoubleSpinBox"))
        self.snowSCMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SNOW", "SnowSC", "snowSCLineEdit"))
        self.snowSCDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "SNOW", "SnowSC"))
        self.selectSnowSCMapButton.clicked.connect(partial(self.updateMap, "SNOW", "SnowSC", "snow pack capacity", "Input", "Snow", 6))
        
        # DDFS
        self.DDFSSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SNOW", "DDFS", "DDFSDoubleSpinBox"))
        self.DDFSMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "SNOW", "DDFS", "DDFSLineEdit"))
        self.DDFSDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "SNOW", "DDFS"))
        self.selectDDFSMapButton.clicked.connect(partial(self.updateMap, "SNOW", "DDFS", "snow degree-day-factor", "Input", "Snow", 6))
        
        # Tcrit
        self.tcritDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "SNOW", "TCrit"))
        
        """
        Routing tab
        """
        # Recession coefficient (kx)
        self.kxSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUTING", "kx", "kxDoubleSpinBox"))
        self.kxMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUTING", "kx", "kxLineEdit"))
        self.kxDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "ROUTING", "kx"))
        self.selectKxMapButton.clicked.connect(partial(self.updateMap, "ROUTING", "kx", "routing recession coefficient", "Input", "Routing", 7))
        
        # Flow direction
        self.selecFlowDirMapButton.clicked.connect(partial(self.updateMap, "ROUTING", "flowdir", "flow direction", "Input", "Routing", 7))
        
        # Total initial runoff
        self.qraInitSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "QRA_init", "qraInitDoubleSpinBox"))
        self.qraInitMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "QRA_init", "qraInitLineEdit"))
        self.qraInitDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "ROUT_INIT", "QRA_init"))
        self.selectQraInitMapButton.clicked.connect(partial(self.updateMap, "ROUT_INIT", "QRA_init", "initial total routed runoff", "Input", "ROUTING", 7))
        
        # Initial routed rainfall runoff
        self.rainRaInitSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "RainRA_init", "rainRaInitDoubleSpinBox"))
        self.rainRaInitMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "RainRA_init", "rainRaInitLineEdit"))
        self.rainRaInitDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "ROUT_INIT", "RainRA_init"))
        self.selectRainRaInitMapButton.clicked.connect(partial(self.updateMap, "ROUT_INIT", "RainRA_init", "initial routed rainfall runoff", "Input", "ROUTING", 7))
        
        # Initial routed baseflow runoff
        self.basRaInitSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "BaseRA_init", "basRaInitDoubleSpinBox"))
        self.basRaInitMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "BaseRA_init", "basRaInitLineEdit"))
        self.basRaInitDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "ROUT_INIT", "BaseRA_init"))
        self.selectBasRaInitMapButton.clicked.connect(partial(self.updateMap, "ROUT_INIT", "BaseRA_init", "initial routed rainfall runoff", "Input", "ROUTING", 7))
        
        # Initial routed snow runoff
        self.snowRaInitSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "SnowRA_init", "snowRaInitDoubleSpinBox"))
        self.snowRaInitMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "SnowRA_init", "snowRaInitLineEdit"))
        self.snowRaInitDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "ROUT_INIT", "SnowRA_init"))
        self.selectSnowRaInitMapButton.clicked.connect(partial(self.updateMap, "ROUT_INIT", "SnowRA_init", "initial routed snow runoff", "Input", "ROUTING", 7))
        
        # Initial routed glacier runoff
        self.glacRaInitSingleRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "GlacRA_init", "glacRaInitDoubleSpinBox"))
        self.glacRaInitMapRadioButton.toggled.connect(partial(self.updateRadioValueMap, "ROUT_INIT", "GlacRA_init", "glacRaInitLineEdit"))
        self.glacRaInitDoubleSpinBox.valueChanged.connect(partial(self.updateValue, "ROUT_INIT", "GlacRA_init"))
        self.selectGlacRaInitMapButton.clicked.connect(partial(self.updateMap, "ROUT_INIT", "GlacRA_init", "initial routed glacier runoff", "Input", "ROUTING", 7))

        """
        Reporting options
        """
        # if reporting item in list is changed, then update checkboxes based on config
        self.reportListWidget.itemSelectionChanged.connect(self.setReportGui)
        
        # update the config based on the list
        self.dailyMapReportCheckBox.stateChanged.connect(self.updateReportCheckBox)
        self.monthlyMapReportCheckBox.stateChanged.connect(self.updateReportCheckBox)
        self.annualMapReportCheckBox.stateChanged.connect(self.updateReportCheckBox)
        self.dailyTSSReportCheckBox.stateChanged.connect(self.updateReportCheckBox)
        
        # set the mm reporting flag
        self.mmRepFlagCheckBox.stateChanged.connect(self.updateReportCheckBox)

        """ Running the model """
        # Set the paths to the pcraster and python environment
        self.selectPcrBinPathButton.clicked.connect(self.updatePath)
        self.selectPythonExeButton.clicked.connect(self.updatePath)
        self.runModelButton.clicked.connect(self.runModel)
        
        """Visualization """
        self.showTimeSeriesButton.clicked.connect(self.showTimeSeries)
        self.showDMapSeriesButton.clicked.connect(partial(self.showOutputMap, "Daily", 2))
        self.showMMapSeriesButton.clicked.connect(partial(self.showOutputMap, "Monthly", 1))
        self.showYMapSeriesButton.clicked.connect(partial(self.showOutputMap, "Annual", 0))
        
        
    # function that emits a point that is linked to the plotGraph function        
    def showTimeSeries(self):
        # create a maptool to select a point feature from the canvas
        if not self.featFinder:
            from MapTools import FeatureFinder
            self.featFinder = FeatureFinder(self.iface.mapCanvas())
            self.featFinder.setAction( None )
            #self.featFinder.setAction( self.action )
            QtCore.QObject.connect(self.featFinder, QtCore.SIGNAL( "pointEmitted" ), self.plotGraph)
        # enable the maptool and set a message in the status bar 
        self.featFinder.startCapture()
        self.iface.mainWindow().statusBar().showMessage( u"Click on a point feature in canvas" )
    
    # plot a time-series graph from a csv file
    def plotGraph(self, point):
        layer = self.iface.activeLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer or layer.geometryType() != QGis.Point:
            QtGui.QMessageBox.information(self.iface.mainWindow(), "Time Series Viewer", u"Select a vector layer and try again.")
            self.iface.mainWindow().statusBar().clearMessage()
            return

        # get the id of the point feature under the mouse click
        from .MapTools import FeatureFinder
        fid = FeatureFinder.findAtPoint(layer, point, canvas=self.iface.mapCanvas(), onlyTheClosestOne=True, onlyIds=True)
        if fid is None:
            QtGui.QMessageBox.information(self.iface.mainWindow(), "Time Series Viewer", u"No point in the active layer has been selected")
            self.showTimeSeries()
            return
        #fid = fid + 1 # somehow fid starts with zero.
        # get the correct station id from the features
        features = layer.getFeatures()
        for feat in features:
            if feat.id()==fid:
                stationId = feat[0]
                fid = int(stationId)
                break
        
        self.iface.mainWindow().statusBar().clearMessage()
        
        # get the item that returns the correct ylabel from the ylabelDictionary
        legenditem = (self.timeSeriesListWidget.currentItem()).text()
        filename = self.outputLegendDict[legenditem][0]
        if "SubBasinTSS" in filename:
            filename = filename + ".csv"
        else:
            filename = filename + "DTS.csv"
            
        f = open(self.outputPath + filename, "r")
        x = []  # date vector
        y = []  # value vector
        for row in f:
            date = row.split(",")[0]
            date = datetime.datetime.strptime(date, ("%Y-%m-%d"))
            mdate = mdates.date2num(date) # convert to matlab format
            x.append(mdate)
            y.append(row.split(",")[fid])
        f.close()
        
        fig = plt.figure(facecolor="white")
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.plot(x,y)
        plt.xlim(x[0],x[-1])
        plt.ylabel(legenditem)
        plt.title("Location ID %d" %fid)
        plt.gcf().autofmt_xdate()
        plt.grid()
        plt.show()
		
		
#         mywindow = QWidget() 
#         self.canvas = FigureCanvas(fig)
#         self.canvas.setParent(mywindow)
#         self.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
#         self.canvas.setFocus()
#         self.toolbar = NavigationToolbar(self.canvas, mywindow)
#         
#         vbox = QtGui.QVBoxLayout(mywindow)
#         vbox.addWidget(self.canvas)
#         vbox.addWidget(self.toolbar)
#         mywindow.setLayout(vbox)
# 
#         QWidget.set

    # function that show a output map in the canvas
    def showOutputMap(self, group, groupPos):
        # read old registry projection settings and set to useGlobal for this function
        oldProjection = self.settings.value( "/Projections/defaultBehaviour")
        self.settings.setValue( "/Projections/defaultBehaviour", "useGlobal" )
        ##    
        # define the filename and legend text
        if group == "Daily":
            legendtext = self.dMapSeriesListWidget.currentItem().text()
        elif group == "Monthly":
            legendtext = self.mMapSeriesListWidget.currentItem().text()
        else:
            legendtext = self.yMapSeriesListWidget.currentItem().text()
        legenditem = legendtext.split(", ")[0]
        date = legendtext.split(", ")[1]
        filename = self.outputLegendDict[legenditem][0]
        filename = "%s%s%s%s" %(filename, "_", date, ".map")

        layer = QgsRasterLayer(self.outputPath + filename, legendtext)
        # set the layer CRS
        layer.setCrs( QgsCoordinateReferenceSystem(self.crs, QgsCoordinateReferenceSystem.EpsgCrsId) )
        # Restore old projection settings in registry
        self.settings.setValue( "/Projections/defaultBehaviour", oldProjection)
        iface.messageBar().popWidget()
        
        # register the layer
        QgsMapLayerRegistry.instance().addMapLayer(layer, False)
        # Loop through the childs in the layertreeroot and create a headgroup, and layer if
        # they don't exist yet. Otherwise remove existing layer, and insert new layer
        headgroup = "Output"
        headgroup_exists = False
        group_exists = False
        root = QgsProject.instance().layerTreeRoot()
        for child in root.children():
            if isinstance(child, QgsLayerTreeGroup):
                if child.name() == headgroup:  
                    headgroup_exists = True
                    headgroupRef = child
                    break
        if headgroup_exists:
            for child in headgroupRef.children():
                if isinstance(child, QgsLayerTreeGroup): 
                    if child.name() == group:
                        group_exists = True
                        groupRef = child
                        break
            if group_exists:
                for l in groupRef.findLayers():
                    if l.layerName() == legendtext:
                        groupRef.removeChildNode(l)
                #groupRef.addLayer(layer)
                groupRef.insertLayer(0, layer)
            else:
                groupRef = headgroupRef.insertGroup(groupPos, group)
                #groupRef.addLayer(layer)
                groupRef.insertLayer(0, layer)
        else:
            headgroupRef = root.insertGroup(1, headgroup)
            groupRef = headgroupRef.insertGroup(groupPos, group)
            #groupRef.addLayer(layer)
            groupRef.insertLayer(0, layer)
        self.updateSaveButtons(1)             

        
       
    # Update the reporting options in the config file depending on the checkboxes that are
    # checked or unchecked in the Gui
    def updateReportCheckBox(self, state):
        sender = self.sender()
        # if mm RepFlagCheckbox is checked or unchecked:
        if sender == self.mmRepFlagCheckBox:
            if state == QtCore.Qt.Unchecked:
                self.updateConfig("REPORTING", "mm_rep_FLAG", 0)
            else:
                self.updateConfig("REPORTING", "mm_rep_FLAG", 1)
        else:
            item = self.reportListWidget.currentItem()
            key = item.text()
            par = self.reportDict[key]
            # if mm dailyTSSReportCheckbox is checked or unchecked:    
            if sender == self.dailyTSSReportCheckBox:
                if state == QtCore.Qt.Unchecked:
                    self.updateConfig("REPORTING", par + "_tsoutput", "NONE")
                else:
                    self.updateConfig("REPORTING", par + "_tsoutput", "D")
            # else do something with the map reporting (D, M, or Y) checked or unchecked
            else:
                widgets = {self.dailyMapReportCheckBox: "D", self.monthlyMapReportCheckBox: "M", self.annualMapReportCheckBox: "Y"}
                repOpt = widgets[sender]
                mapitems = (self.currentConfig.get("REPORTING", par + "_mapoutput")).split(",")
                if state == QtCore.Qt.Unchecked and repOpt in mapitems:
                    mapitems.remove(repOpt)
                    if mapitems == []:
                        self.updateConfig("REPORTING", par + "_mapoutput", "NONE")
                        return
                elif state == QtCore.Qt.Checked:
        
                    if "NONE" in mapitems:
                        self.updateConfig("REPORTING", par + "_mapoutput", repOpt)
                        return
                    elif repOpt not in mapitems:
                        mapitems.append(repOpt)
                reportString = ""
                for map in mapitems:
                    if map is not mapitems[-1]:
                        reportString = reportString + map + ","
                    else:
                        reportString = reportString + map
                self.updateConfig("REPORTING", par + "_mapoutput", reportString)
    
    # Function to run the model          
    def runModel(self):
        self.updateDate()
        self.saveProject()
        # clean the modelrunlogtext window
        self.modelRunLogTextEdit.clear()
        # clean the list items from the tss list widget in the visualization tab
        #self.timeSeriesListWidget.clear()
        # disable the visualization tab during model run
        self.tab.setTabEnabled(10, False)
        # create the most recent output dictionary based on the reporting settings
        self.setOutputDict()

        
        # set the batchfile settings
        disk = (self.sphyLocationPath).split(":")[0] + ":"
        sphydir = self.sphyLocationPath + "/"
        pcrpath = self.pcrBinPath
        pyexe = self.pythonExe
        sphycommand = sphydir + "sphy.py"
        batchfile = sphydir + "runModel.bat"
         
        # copy the project cfg to config to be used with sphy.py
        shutil.copy(self.currentConfigFileName, sphydir + "sphy_config.cfg")
        
        # make a batch file to execute
        f = open(batchfile, "w")
        f.write(disk + "\n")
        f.write("cd " + sphydir + "\n")
        f.write("set PATH=" + pcrpath + "\n")
        f.write(pyexe + " " + sphycommand)
        f.close()
        
        # create a new worker instance
        worker = ModelWorker(batchfile, self.timeSteps)
        
        # kill the worker (model run) if model
        self.cancelModelRunButton.clicked.connect(worker.kill)
        
        # start the worker in a new thread
        thread = QtCore.QThread(self)
        worker.moveToThread(thread)

        # listeners        
        worker.finished.connect(self.modelWorkerFinished)
        worker.error.connect(self.WorkerError)
        worker.cmdProgress.connect(self.modelWorkerListener)
        
        # progressbar
        worker.progBar.connect(self.modelRunProgressBar.setValue)

        thread.started.connect(worker.run)
        thread.start()
        self.thread = thread
        self.worker = worker

        
    def modelWorkerFinished(self, process):
        # clean up the worker and thread
        self.thread.quit()
        self.thread.wait()
        if process is None:
            self.modelRunLogTextEdit.append("Model run was unsuccesfully because of one of these reasons:\n\
            - model run was cancelled by the user, or\n\
            - model input or parameters are missing/incorrect, or\n\
            - environmental settings are incorrect, or\n\
            a combination of these reasons.")
            # set the progress bar to 0%
            self.modelRunProgressBar.setValue(0)
        else:
            self.modelRunLogTextEdit.append("Model run was succesfully!")
            
            # Loop over the TSS and map output files, and convert and rename them to a more suitable format and add them to the correspoding
            # list widget in the visualize tab
            self.modelRunLogTextEdit.append("Converting Time-series TSS files...")
            for root, dirs, files in os.walk(self.outputPath):
                for file in files:
                    if file.endswith('.tss'):
                        self.convertTSS(file)
            
            # Loop over all the map files and convert and rename to correct units and suitable name
            # start a worker instance to convert the map files
            worker = convertMapWorker(self.startdate, self.timeSteps, self.outputPath, self.outputFileNameDict, self.pcrBinPath)
            # start the worker in a new thread
            thread = QtCore.QThread(self)
            worker.moveToThread(thread)
             # listeners 
            worker.cmdProgress.connect(self.convertMapWorkerListener)
            worker.finished.connect(self.convertMapWorkerFinished)
            worker.error.connect(self.WorkerError)
             
            thread.started.connect(worker.run)
            thread.start()
            self.thread = thread
            self.worker = worker
             

#             self.convertMAP()
#             self.modelRunLogTextEdit.append("Converting files completed!")
            
#             # set the progress bar to 100%
#             self.modelRunProgressBar.setValue(100)
#             time.sleep(1)
#             self.modelRunProgressBar.setValue(0)

        # add the daily time-series csv files to the list widget in the visualization tab and enable tab again            
#         self.setVisListWidgets()
#         self.tab.setTabEnabled(10, True)
        
    
    # function that is launched whenever the model is unable to run
    def WorkerError(self, e, exception_string):
        QgsMessageLog.logMessage('Worker thread raised an exception:\n'.format(exception_string), level=QgsMessageLog.CRITICAL)
    
    # function that parses model cmd line output to the text widget in the run model tab    
    def modelWorkerListener(self, line):
        self.modelRunLogTextEdit.append(line)
    
    # function that parses ... info to the text widget in the model run tab during model output map conversion/renaming    
    def convertMapWorkerListener(self, line):
        self.modelRunLogTextEdit.append(line)
     
    # function that is launched when converting of model output maps  is finished
    def convertMapWorkerFinished(self, finished):
        self.thread.quit()
        self.thread.wait()
        if finished:
            self.modelRunLogTextEdit.append("Converting model output maps completed!")
            self.modelRunProgressBar.setValue(100)
        else:
            self.modelRunLogTextEdit.append("Converting model output maps unsuccessfully!!")

        self.setVisListWidgets()
        self.tab.setTabEnabled(10, True)
        time.sleep(1)
        self.modelRunProgressBar.setValue(0)
    
    # function that is used to convert the tss to a more suitable csv file, containing only a date column, and
    # data column for each location    
    def convertTSS(self, fileName):
        date = self.startdate
        with open(self.outputPath + fileName, "rb") as csvfile:
            r = csv.reader(csvfile, delimiter=' ', quoting=csv.QUOTE_NONE)
            for row in r:
                if row[0]=="timestep":
                    break
            # loop over lines until it finds the first record number with data and determine the number of stations
            stations = -1            
            for row in r:
                stations+=1            
                if len(row)>1:
                    break
            #-read the first data record
            line = []
            for i in row:
                if i is not"":
                    line.append(i)
            # write the first record to a temporary file
            f = open(self.outputPath + "tempdata", "w")
            f.write("%s," %(date.strftime("%Y-%m-%d")))
            for s in range(1, stations):
                f.write("%f," %float(line[s]))
            if stations == 1:
                f.write("%f\n" %float(line[1]))
            else:
                f.write("%f\n" %float(line[s+1]))        
            # write the remaining records    
            for row in r:
                date = date + datetime.timedelta(days=1)
                f.write("%s," %(date.strftime("%Y-%m-%d")))
                line = []
                for i in row:
                    if i is not "":
                        line.append(i)
                for s in range(1, stations):
                    f.write("%f," %float(line[s]))
                if stations == 1:
                    f.write("%f\n" %float(line[1]))
                else:
                    f.write("%f\n" %float(line[s+1]))        
            f.close()    
        outFileName = fileName.split(".tss")[0] + ".csv"
        shutil.move(self.outputPath + "tempdata", self.outputPath + outFileName)
        os.remove(self.outputPath + fileName)
        
    # function that disables/enables Widgets, and updates the config value
    def updateRadioValueMap(self, module, par, widget, enabled):
        if enabled:
            widget = eval("self." + widget)
            if isinstance(widget, QtGui.QDoubleSpinBox) or isinstance(widget, QtGui.QSpinBox):
                value = widget.value()
            elif isinstance(widget, QtGui.QLineEdit):
                value = widget.text()
            self.updateConfig(module, par, value)    
            self.initGuiConfigMap()
        
    
    # initialize the Gui with values from the config file
    def initGuiConfigMap(self):
        
        # set the dictionary for the GUI radio buttons, corresponding to either a lineedit (map file) or spinbox (single value)
        self.configRadioDict = {"rootDepthLineEdit": ("SOILPARS", "RootDepthFlat",("rootDepthMapRadioButton", "selectRootDepthMapButton"),("rootDepthSingleRadioButton", "rootDepthSpinBox")),
                                "subDepthLineEdit": ("SOILPARS", "SubDepthFlat",("subDepthMapRadioButton", "selectSubDepthMapButton"),("subDepthSingleRadioButton", "subDepthSpinBox")),
                                "gwDepthLineEdit": ("GROUNDW_PARS", "GwDepth",("gwDepthMapRadioButton", "selectGwDepthMapButton"), ("gwDepthSingleRadioButton", "gwDepthSpinBox")),
                                "gwSatLineEdit": ("GROUNDW_PARS", "GwSat",("gwSatMapRadioButton", "selectGwSatMapButton"), ("gwSatSingleRadioButton", "gwSatSpinBox")),
                                "gwInitLineEdit": ("GROUNDW_INIT", "Gw",("gwInitMapRadioButton", "selectGwInitMapButton"), ("gwInitSingleRadioButton", "gwInitSpinBox")),
                                "baseThreshLineEdit": ("GROUNDW_PARS", "BaseThresh",("baseThreshMapRadioButton", "selectBaseThreshMapButton"), ("baseThreshSingleRadioButton", "baseThreshSpinBox")),
                                "deltaGwLineEdit": ("GROUNDW_PARS", "deltaGw",("deltaGwMapRadioButton", "selectDeltaGwMapButton"), ("deltaGwSingleRadioButton", "deltaGwSpinBox")),
                                "alphaGwLineEdit": ("GROUNDW_PARS", "alphaGw",("alphaGwMapRadioButton", "selectAlphaGwMapButton"), ("alphaGwSingleRadioButton", "alphaGwDoubleSpinBox")),
                                "glacRoFracLineEdit": ("GLACIER", "GlacF",("glacRoFracMapRadioButton", "selectGlacRoFracMapButton"), ("glacRoFracSingleRadioButton", "glacRoFracDoubleSpinBox")),
                                "DDFDGLineEdit": ("GLACIER", "DDFDG",("DDFDGMapRadioButton", "selectDDFDGMapButton"), ("DDFDGSingleRadioButton", "DDFDGDoubleSpinBox")),
                                "DDFGLineEdit": ("GLACIER", "DDFG",("DDFGMapRadioButton", "selectDDFGMapButton"), ("DDFGSingleRadioButton", "DDFGDoubleSpinBox")),
                                "snowIniLineEdit": ("SNOW_INIT", "SnowIni",("snowIniMapRadioButton", "selectSnowIniMapButton"), ("snowIniSingleRadioButton", "snowIniSpinBox")),
                                "sWatStoreLineEdit": ("SNOW_INIT", "SnowWatStore",("sWatStoreMapRadioButton", "selectSWatStoreMapButton"), ("sWatStoreSingleRadioButton", "sWatStoreSpinBox")),
                                "snowSCLineEdit": ("SNOW", "SnowSC",("snowSCMapRadioButton", "selectSnowSCMapButton"), ("snowSCSingleRadioButton", "snowSCDoubleSpinBox")),
                                "DDFSLineEdit": ("SNOW", "DDFS",("DDFSMapRadioButton", "selectDDFSMapButton"), ("DDFSSingleRadioButton", "DDFSDoubleSpinBox")),
                                "kxLineEdit": ("ROUTING", "kx",("kxMapRadioButton", "selectKxMapButton"), ("kxSingleRadioButton", "kxDoubleSpinBox")),
                                "qraInitLineEdit": ("ROUT_INIT", "QRA_init",("qraInitMapRadioButton", "selectQraInitMapButton"), ("qraInitSingleRadioButton", "qraInitDoubleSpinBox")),
                                "rainRaInitLineEdit": ("ROUT_INIT", "RainRA_init",("rainRaInitMapRadioButton", "selectRainRaInitMapButton"), ("rainRaInitSingleRadioButton", "rainRaInitDoubleSpinBox")),
                                "basRaInitLineEdit": ("ROUT_INIT", "BaseRA_init",("basRaInitMapRadioButton", "selectBasRaInitMapButton"), ("basRaInitSingleRadioButton", "basRaInitDoubleSpinBox")),
                                "snowRaInitLineEdit": ("ROUT_INIT", "SnowRA_init",("snowRaInitMapRadioButton", "selectSnowRaInitMapButton"), ("snowRaInitSingleRadioButton", "snowRaInitDoubleSpinBox")),
                                "glacRaInitLineEdit": ("ROUT_INIT", "GlacRA_init",("glacRaInitMapRadioButton", "selectGlacRaInitMapButton"), ("glacRaInitSingleRadioButton", "glacRaInitDoubleSpinBox"))}
        
        self.setRadioGui()

        # set the dictionary for the other Gui widgets 
        self.configDict = {"inputPathLineEdit": ("DIRS", "inputdir"),"outputPathLineEdit": ("DIRS", "outputdir"),
                             "startDateEdit": ("TIMING", ("startyear", "startmonth", "startday")),
                             "endDateEdit": ("TIMING", ("endyear", "endmonth", "endday")), "cloneMapLineEdit": ("GENERAL", "mask"),
                             "demMapLineEdit": ("GENERAL","dem"), "slopeMapLineEdit": ("GENERAL", "slope"),
                             "subbasinMapLineEdit": ("GENERAL", "sub"), "stationsMapLineEdit": ("GENERAL", "locations"),
                             "precMapSeriesLineEdit": ("CLIMATE", "Prec"), "avgTempMapSeriesLineEdit": ("CLIMATE", "Tair"),
                             "maxTempMapSeriesLineEdit": ("ETREF", "Tmax"), "minTempMapSeriesLineEdit": ("ETREF", "Tmin"),
                             "latitudeZonesMapLineEdit": ("ETREF", "Lat"), "solarConstantDoubleSpinBox": ("ETREF", "Gsc"),
                             "rootFieldCapLineEdit": ("SOIL", "RootFieldMap"), "rootSatLineEdit": ("SOIL", "RootSatMap"),
                             "rootPermWiltLineEdit": ("SOIL", "RootDryMap"), "rootWiltLineEdit": ("SOIL", "RootWiltMap"),
                             "rootSatCondLineEdit": ("SOIL", "RootKsat"), "subFieldCapLineEdit": ("SOIL", "SubFieldMap"),
                             "subSatLineEdit": ("SOIL", "SubSatMap"), "subSatCondLineEdit": ("SOIL", "SubKsat"),
                             "maxCapRiseSpinBox": ("SOILPARS", "CapRiseMax"), "landUseLineEdit": ("LANDUSE", "LandUse"),
                             "kcTableLineEdit": ("LANDUSE", "CropFac"), "initGlacFracLineEdit": ("GLACIER_INIT", "GlacFrac"),
                             "cIFracLineEdit": ("GLACIER", "GlacFracCI"), "dBFracLineEdit": ("GLACIER", "GlacFracDB"),
                             "flowDirLineEdit": ("ROUTING", "flowdir"), "mmRepFlagCheckBox": ("REPORTING", "mm_rep_FLAG")}
        self.setGui()

        # set the dictionary for the reporting options
        self.reportDict = {"Precipitation [mm]": "totprec", "Rainfall [mm]": "totrainf", "ETp [mm]": "totetpotf", "ETa [mm]": "totetactf", "Snow [mm]": "totsnowf", "Snow melt [mm]": "totsnowmeltf",
                           "Glacier melt [mm]": "totglacmeltf", "Surface runoff [mm]": "totrootrf", "Rootzone drainage [mm]": "totrootdf", "Rootzone percolation [mm]": "totrootpf",
                           "Subzone percolation [mm]": "totsubpf", "Capillary rise [mm]": "totcaprf", "Glacier percolation [mm]": "totglacpercf", "Groundwater recharge [mm]": "totgwrechargef",
                           "Rain runoff [mm]": "totrainrf", "Snow runoff [mm]": "totsnowrf","Glacier runoff [mm]": "totglacrf", "Baseflow runoff [mm]": "totbaserf", "Total runoff [mm]": "totrf",
                           "Routed rain runoff [m3/s]": "rainratot", "Routed snow runoff [m3/s]": "snowratot", "Routed glacier runoff [m3/s]": "glacratot", "Routed baseflow runoff [m3/s]": "baseratot",
                           "Routed total runoff [m3/s]": "qallratot"}
        
        items = self.reportDict.keys()
        # check if items already exist. If items already exist, then items don't need to be added again
        if self.reportListWidget.item(0) is None:
            self.reportListWidget.addItems(items)
            self.reportListWidget.sortItems()
        # set the first item in the list as being the current item
        self.reportListWidget.setCurrentItem(self.reportListWidget.item(0))
        self.setReportGui()

        # Make two dictionaries: 1) keys = filename, items = legend name. 2) keys = legend name, items = filename
        self.setOutputDict()
        
        # Add the daily time-series csv files and spatial maps to the visualization tab list widgets
        self.setVisListWidgets()
        
    def setGui(self):
        for key in self.configDict:
            widget = eval("self."+key)
            i = self.configDict[key]
            module = i[0]
            pars = i[1]
            if module == "TIMING" and (pars[0] == "startyear" or pars[0] == "endyear"): 
                #self.setGui(widget, module, pars[0], pars[1], pars[2])
                widget.setDate(QtCore.QDate(self.currentConfig.getint(module, pars[0]),self.currentConfig.getint(module, pars[1]),self.currentConfig.getint(module, pars[2])))
            else:
                #self.setGui(widget, module, pars)
                if isinstance(widget, QtGui.QLineEdit):
                    widget.setText(self.currentConfig.get(module, pars))
                elif isinstance(widget, QtGui.QCheckBox):
                    if self.currentConfig.getint(module, pars) == 1:
                        widget.setChecked(1)
                elif isinstance(widget, QtGui.QDoubleSpinBox):
                    widget.setValue(self.currentConfig.getfloat(module, pars))
                elif isinstance(widget, QtGui.QSpinBox):
                    widget.setValue(self.currentConfig.getint(module, pars))
                # define the variables self.inputPath and self.outputPath
                if widget == self.inputPathLineEdit:
                    self.inputPath = os.path.join(self.sphyLocationPath, self.currentConfig.get(module, pars))
                elif widget == self.outputPathLineEdit:
                    self.outputPath = os.path.join(self.sphyLocationPath, self.currentConfig.get(module, pars))

    # set the Gui values for the radio button related fields        
    def setRadioGui(self):
        for key in self.configRadioDict:
            v = self.configRadioDict[key]
            module = v[0]
            par = v[1]
            # the map widgets
            mapWidgets = v[2]
            mapRadioButton = eval("self." + mapWidgets[0])
            mapSelectButton = eval("self." + mapWidgets[1])
            lineEdit = eval("self." + key)
            # the value widgets
            valueWidgets = v[3]
            valueRadioButton = eval("self." + valueWidgets[0])
            valueSpinBox = eval("self." + valueWidgets[1])
            # first try if a float can be extracted from the config
            try:
                value = self.currentConfig.getfloat(module, par)
                valueRadioButton.setChecked(1)
                valueSpinBox.setValue(value)
                valueSpinBox.setEnabled(1)
                mapSelectButton.setEnabled(0)
                lineEdit.setEnabled(0)
            except:
                try: # then try to extract a integer from the config
                    value = self.currentConfig.getint(module, par)
                    valueRadioButton.setChecked(1)
                    valueSpinBox.setValue(value)
                    valueSpinBox.setEnabled(1)
                    mapSelectButton.setEnabled(0)
                    lineEdit.setEnabled(0)
                except: # then it should be a map file
                    lineEdit.setText(self.currentConfig.get(module, par))
                    mapRadioButton.setChecked(1)
                    lineEdit.setEnabled(1)
                    mapSelectButton.setEnabled(1)
                    valueSpinBox.setEnabled(0)
                    
    # Initialize the Reporting options in the GUI based on the config file reporting settings    
    def setReportGui(self):
        widgets = {self.dailyMapReportCheckBox: "D", self.monthlyMapReportCheckBox: "M", self.annualMapReportCheckBox: "Y"}
        item = self.reportListWidget.currentItem()
        key = item.text()
        par = self.reportDict[key]
        tssoutput = (self.currentConfig.get("REPORTING", par + "_tsoutput")).split(",")
        mapitems = self.currentConfig.get("REPORTING", par + "_mapoutput").split(",")

        # update the map reporting checkboxes
        for w in widgets:
            w.setChecked(0)
        for map in mapitems:
            if map == "D":
                self.dailyMapReportCheckBox.setChecked(1)
            elif map == "M":
                self.monthlyMapReportCheckBox.setChecked(1)
            elif map == "Y":
                self.annualMapReportCheckBox.setChecked(1)
        # update the tss reporting checkbox
        if tssoutput[0] == "D":
            self.dailyTSSReportCheckBox.setChecked(1)
        else:
            self.dailyTSSReportCheckBox.setChecked(0)
        
    def setOutputDict(self):
        self.outputFileNameDict = {}
        self.outputLegendDict = {}
        for key in self.reportDict:
            item = self.reportDict[key] # legend name
            fname = self.currentConfig.get("REPORTING", item + "_fname") # filename
            mapoutput = self.currentConfig.get("REPORTING", item + "_mapoutput") # mapoutput
            tsoutput = self.currentConfig.get("REPORTING", item + "_tsoutput") # mapoutput
            # continue with next loop item if no reporting is done for this item
            if mapoutput == "NONE" and tsoutput == "NONE":
                continue
            
            self.outputFileNameDict.setdefault(fname, [])
            self.outputFileNameDict[fname].append(key)
            self.outputLegendDict.setdefault(key, [])
            self.outputLegendDict[key].append(fname)
            if "m3/s" in key:
                 # append a flag of 1 that indicates that it needs to be converted for the M and Y maps
                self.outputFileNameDict[fname].append(1)
                self.outputLegendDict[key].append(1)
        if self.currentConfig.getint("REPORTING", "mm_rep_flag") == 0: # if no reporting of sub-basin average mm fluxes is required then they don't need to be added to the dictionary
            return
        # add the subbasin average tss files to the dictionaries
        self.outputFileNameDict.setdefault("ETaSubBasinTSS", [])
        self.outputFileNameDict["ETaSubBasinTSS"].append("Basin avg. ETa [mm]")
        self.outputFileNameDict.setdefault("PrecSubBasinTSS", [])
        self.outputFileNameDict["PrecSubBasinTSS"].append("Basin avg. precipitation [mm]")
        self.outputFileNameDict.setdefault("GMeltSubBasinTSS", [])
        self.outputFileNameDict["GMeltSubBasinTSS"].append("Basin avg. glacier melt [mm]")
        self.outputFileNameDict.setdefault("QSNOWSubBasinTSS", [])
        self.outputFileNameDict["QSNOWSubBasinTSS"].append("Basin avg. snow runoff [mm]")
        self.outputFileNameDict.setdefault("QRAINSubBasinTSS", [])
        self.outputFileNameDict["QRAINSubBasinTSS"].append("Basin avg. rain runoff [mm]")
        self.outputFileNameDict.setdefault("QGLACSubBasinTSS", [])
        self.outputFileNameDict["QGLACSubBasinTSS"].append("Basin avg. glacier runoff [mm]")
        self.outputFileNameDict.setdefault("QBASFSubBasinTSS", [])
        self.outputFileNameDict["QBASFSubBasinTSS"].append("Basin avg. baseflow runoff [mm]")
        self.outputFileNameDict.setdefault("QTOTSubBasinTSS", [])
        self.outputFileNameDict["QTOTSubBasinTSS"].append("Basin avg. total runoff [mm]")
        self.outputLegendDict.setdefault("Basin avg. ETa [mm]", [])
        self.outputLegendDict["Basin avg. ETa [mm]"].append("ETaSubBasinTSS")
        self.outputLegendDict.setdefault("Basin avg. precipitation [mm]", [])
        self.outputLegendDict["Basin avg. precipitation [mm]"].append("PrecSubBasinTSS")
        self.outputLegendDict.setdefault("Basin avg. glacier melt [mm]", [])
        self.outputLegendDict["Basin avg. glacier melt [mm]"].append("GMeltSubBasinTSS")
        self.outputLegendDict.setdefault("Basin avg. snow runoff [mm]", [])
        self.outputLegendDict["Basin avg. snow runoff [mm]"].append("QSNOWSubBasinTSS")
        self.outputLegendDict.setdefault("Basin avg. rain runoff [mm]", [])
        self.outputLegendDict["Basin avg. rain runoff [mm]"].append("QRAINSubBasinTSS")
        self.outputLegendDict.setdefault("Basin avg. glacier runoff [mm]", [])
        self.outputLegendDict["Basin avg. glacier runoff [mm]"].append("QGLACSubBasinTSS")
        self.outputLegendDict.setdefault("Basin avg. baseflow runoff [mm]", [])
        self.outputLegendDict["Basin avg. baseflow runoff [mm]"].append("QBASFSubBasinTSS")
        self.outputLegendDict.setdefault("Basin avg. total runoff [mm]", [])
        self.outputLegendDict["Basin avg. total runoff [mm]"].append("QTOTSubBasinTSS")
        
        
    # function to add the daily time-series csv files and spatial maps to the visualization tab list widgets
    def setVisListWidgets(self):  
        self.timeSeriesListWidget.clear()
        self.dMapSeriesListWidget.clear()
        self.mMapSeriesListWidget.clear()
        self.yMapSeriesListWidget.clear()
        #if self.timeSeriesListWidget.item(0) is None:
        for root, dirs, files in os.walk(self.outputPath):
            for file in files:
                if file.endswith('.csv'):
                    shortfile = file.split(".csv")[0]
                    try:
                        shortfile = shortfile.split("DTS")[0]
                    except:
                        pass
                    try:
                        legend = self.outputFileNameDict[shortfile]
                        self.timeSeriesListWidget.addItem(legend[0])
                    except:
                        pass
                elif file.endswith('.map'):
                    shortfile = file.split(".map")[0]
                    shortfile = shortfile.split("_")
                    try:
                        legend = self.outputFileNameDict[shortfile[0]][0]
                        if len(shortfile[1]) == 4: # it concerns an annual map
                            self.yMapSeriesListWidget.addItem(legend + ", " + shortfile[1])
                        elif len(shortfile[1]) == 7: # it concerns a monthly map)
                            self.mMapSeriesListWidget.addItem(legend + ", " + shortfile[1])
                        else:
                            self.dMapSeriesListWidget.addItem(legend + ", " + shortfile[1])
                    except:
                        pass
        self.timeSeriesListWidget.sortItems()
        self.dMapSeriesListWidget.sortItems()
        self.mMapSeriesListWidget.sortItems()
        self.yMapSeriesListWidget.sortItems()
        # set the first item in the list as being the current item
        self.timeSeriesListWidget.setCurrentItem(self.timeSeriesListWidget.item(0))
        self.dMapSeriesListWidget.setCurrentItem(self.dMapSeriesListWidget.item(0))
        self.mMapSeriesListWidget.setCurrentItem(self.mMapSeriesListWidget.item(0))
        self.yMapSeriesListWidget.setCurrentItem(self.yMapSeriesListWidget.item(0))

       
    # function launched when new project button is clicked
    def createNewProject(self):
        # check for current project and ask to save
        if self.currentProject:
            mes = QtGui.QMessageBox()
            mes.setWindowTitle("Save current project")
            mes.setText("Do you want to save the current project?")
            mes.setStandardButtons(QtGui.QMessageBox.Save | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel)
            ret = mes.exec_()
            if ret == QtGui.QMessageBox.Save:
                self.saveProject()
                newproject = True
            elif ret == QtGui.QMessageBox.No: # create new project without saving current one
                newproject = True
            else:
                newproject = False
        else:
            newproject = True
        # check if a new project needs/can be created based on the criteria tested above    
        if newproject:
            self.currentConfig.read(os.path.join(os.path.dirname(__file__), "config", "sphy_config_template.cfg"))
            # clear project canvas
            qgsProject = QgsProject.instance()
            qgsProject.clear()
            # save as new project
            self.saveAsProject("new")
            
    # function launched when existing project is opened
    def openProject(self):
        # check for the current project and ask to save
        if self.currentProject:
            mes = QtGui.QMessageBox()
            mes.setWindowTitle("Save current project")
            mes.setText("Do you want to save the current project?")
            mes.setStandardButtons(QtGui.QMessageBox.Save | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel)
            ret = mes.exec_()
            if ret == QtGui.QMessageBox.Save:
                self.saveProject()
                openproject = True
            elif ret == QtGui.QMessageBox.No: # open project without saving current one
                openproject = True
            else:
                openproject = False
        else:
            openproject = True
        # check if a project can be opened based on the criteria tested above
        if openproject:
            tempname = QtGui.QFileDialog.getOpenFileName(self, "Open project *.cfg", self.sphyLocationPath,"*.cfg")
            if tempname:
                # set the new config file
                self.currentConfigFileName = tempname
                self.currentConfig.read(self.currentConfigFileName)
                
                # open the corresponding qgs file
                qgsProjectFileName = ((self.currentConfigFileName).split(".cfg")[0]) + ".qgs"
                qgsProject = QgsProject.instance()
                qgsProject.clear()
                qgsProject.setFileName(qgsProjectFileName)
                qgsProject.read()
                # save the project
                self.saveProject()
                
    # update single value (e.g. from spinbox)     
    def updateValue(self, module, par):
        sender = self.sender().objectName()
        value = eval("self." + sender + ".value()")
        self.updateConfig(module, par, value)
        
    # update a *.tbl file (e.g. for the crop factors)
    def updateTable(self, module, par, name):
        file = (QtGui.QFileDialog.getOpenFileName(self, "Select the "+name+" table", self.inputPath,"*.tbl")).replace("\\","/")
        if file:
            file = os.path.relpath(file, self.inputPath).replace("\\","/")
            self.updateConfig(module, par, file)
            self.initGuiConfigMap()
        
            
    
    # update map-series (e.g. precipitation time-series)
    def updateMapSeries(self, module, par, name):
        file = (QtGui.QFileDialog.getOpenFileName(self, "Select the "+name+" map-series", self.inputPath,"*.001")).replace("\\","/")
        if file:
            file = os.path.relpath(file, self.inputPath).replace("\\","/")
            file = file.rstrip(".001")
            self.updateConfig(module, par, file)
            self.initGuiConfigMap()
        
    # function that is called when a select map or value button is clicked. It then updates the map canvas with the map,
    # updates the GUI with a map name or value, and updates the settings in the config
    def updateMap(self, module, par, name, headgroup, group, groupPos, point=False):
        file = (QtGui.QFileDialog.getOpenFileName(self, "Select the "+name+" map", self.inputPath,"*.map")).replace("\\","/")
        if file:
            # if group=GENERAL, then each new map needs to be inserted on position 1 (after locations shape file)
            # else, new map can be inserted at position zero.
            if group == "General":
                mapPos = 1
            else:
                mapPos = 0
            # read old registry projection settings and set to useGlobal for this function
            oldProjection = self.settings.value( "/Projections/defaultBehaviour")
            self.settings.setValue( "/Projections/defaultBehaviour", "useGlobal" )
            ##    
            layername = (os.path.relpath(file, self.inputPath)).split("/")
            value = layername[-1]
            layername = value.split(".map")
            layername = layername[0]
            headgroup_exists = False
            group_exists = False
            layer_exists = False
            if point:
                locationsfile = (self.inputPath).replace("\\","/") + "locations.shp"
                processing.runalg("saga:gridvaluestopoints", file, None, True, 0,locationsfile)
                
                layer = QgsVectorLayer(locationsfile, layername, "ogr")
                # set the correct IDs in the first column, and finally remove the fourth column
                layer.startEditing()
                iter = layer.getFeatures()
                for feature in iter:
                    feature[0] = feature[3]
                    layer.updateFeature(feature)
                layer.deleteAttribute(3)
                layer.commitChanges()
            else:
                layer = QgsRasterLayer(file, layername)
#                 layer.setDrawingStyle("SingleBandPseudoColor")
#                 layer.ColorShadingAlgorithm(QgsRasterLayer.ColorRampShader)
                
            # set the layer CRS
            layer.setCrs( QgsCoordinateReferenceSystem(self.crs, QgsCoordinateReferenceSystem.EpsgCrsId) )
            # Restore old projection settings in registry
            self.settings.setValue( "/Projections/defaultBehaviour", oldProjection)
            iface.messageBar().popWidget()


            # Register the layer    
            QgsMapLayerRegistry.instance().addMapLayer(layer, False)
            # Loop through the childs in the layertreeroot and create headgroup, group, and layer if
            # they don't exist yet. Otherwise remove existing layer, and insert new layer
            root = QgsProject.instance().layerTreeRoot()
            for child in root.children():
                if isinstance(child, QgsLayerTreeGroup):
                    if child.name() == headgroup:  
                        headgroup_exists = True
                        headgroupRef = child
                        break
            if headgroup_exists:
                for child in headgroupRef.children():
                    if isinstance(child, QgsLayerTreeGroup): 
                        if child.name() == group:
                            group_exists = True
                            groupRef = child
                            break
                if group_exists:
                    for l in groupRef.findLayers():
                        if l.layerName() == layername:
                            groupRef.removeChildNode(l)
                    if point:
                        groupRef.insertLayer(0, layer)
                    else:
                        #groupRef.addLayer(layer)
                        groupRef.insertLayer(mapPos,layer)
                else:
                    groupRef = headgroupRef.insertGroup(groupPos, group)
                    #groupRef = headgroupRef.addGroup(group)
                    if point:
                        groupRef.insertLayer(0, layer)
                    else:
                        #groupRef.addLayer(layer)
                        groupRef.insertLayer(mapPos,layer)
            else:
                headgroupRef = root.insertGroup(0, headgroup)
                groupRef = headgroupRef.insertGroup(groupPos, group)
                #groupRef = headgroupRef.addGroup(group)
                if point:
                    groupRef.insertLayer(0, layer)
                else:
                    #groupRef.addLayer(layer)
                    groupRef.insertLayer(mapPos,layer)
            self.updateConfig(module, par, value)
            self.initGuiConfigMap()    
    
    # function that updates the paths in the Gui, and updates the config file
    def updatePath(self):
        sender =  self.sender().objectName()
        if sender == "selectSphyPathButton":
            tempname = QtGui.QFileDialog.getExistingDirectory(self, "Select path were sphy.py is located", self.sphyLocationPath, QtGui.QFileDialog.ShowDirsOnly)
            if os.path.isfile(os.path.join(tempname, "sphy.py")) == False:
                mes = QtGui.QMessageBox.warning(self, "SPHY model path error", "Error: sphy.py is not found in the specified folder. \nSelect a differnt folder.")
            else:
                self.sphyLocationPath = tempname
                self.sphyPathLineEdit.setText((self.sphyLocationPath + "\\").replace("\\","/"))
                # update also the in and output folders because sphy.py path has been modifed
                self.updateConfig("DIRS", "inputdir", (os.path.relpath(self.inputPath, self.sphyLocationPath)).replace("\\","/") + "/")
                self.updateConfig("DIRS", "outputdir", (os.path.relpath(self.outputPath, self.sphyLocationPath)).replace("\\","/") + "/")
                self.saveProject()
        elif sender == "selectInputPathButton":
            tempname = QtGui.QFileDialog.getExistingDirectory(self, "Select path were the model input is located", self.sphyLocationPath, QtGui.QFileDialog.ShowDirsOnly)
            if tempname:
                self.inputPath = tempname
                self.inputPathLineEdit.setText((self.inputPath + "\\").replace("\\","/"))
                self.updateConfig("DIRS", "inputdir", (os.path.relpath(self.inputPath, self.sphyLocationPath)).replace("\\","/") + "/")
        elif sender == "selectOutputPathButton":
            tempname = QtGui.QFileDialog.getExistingDirectory(self, "Select path were the model output should be written", self.sphyLocationPath, QtGui.QFileDialog.ShowDirsOnly)
            if tempname:
                self.outputPath = tempname
                self.outputPathLineEdit.setText((self.outputPath + "\\").replace("\\","/"))
                self.updateConfig("DIRS", "outputdir", (os.path.relpath(self.outputPath, self.sphyLocationPath)).replace("\\","/") + "/")
        elif sender == "selectPcrBinPathButton":
            tempname = QtGui.QFileDialog.getExistingDirectory(self, "Select the PCRaster bin folder", "c:/", QtGui.QFileDialog.ShowDirsOnly)
            if tempname:
                self.pcrBinPath = tempname
                self.pcrBinPathLineEdit.setText(self.pcrBinPath)
                self.saveProject()
        elif sender == "selectPythonExeButton":
            tempname = QtGui.QFileDialog.getOpenFileName(self, "Select the pyton.exe file", "c:/", "python.exe")
            if tempname:
                self.pythonExe = tempname
                self.pythonExeLineEdit.setText(self.pythonExe)
                self.saveProject()
    
    # validate start and enddate and set in config        
    def updateDate(self):
        if self.exitDate: # don't execute this function if GUI is initialized during new project or open project creation.
            return
        # validate if simulation settings are ok
        startdate = self.startDateEdit.date()
        enddate = self.endDateEdit.date()
        if startdate >= enddate:
            QtGui.QMessageBox.warning(self, "Date error", "End date should be larger than start date")
            if self.sender().objectName() == "startDateEdit":
                enddate = QtCore.QDate(startdate).addDays(1)
                self.endDateEdit.setDate(enddate)
            else:
                startdate = QtCore.QDate(enddate).addDays(-1)
                self.startDateEdit.setDate(startdate)
        self.updateConfig("TIMING", "startyear", QtCore.QDate.year(startdate))
        self.updateConfig("TIMING", "startmonth", QtCore.QDate.month(startdate))
        self.updateConfig("TIMING", "startday", QtCore.QDate.day(startdate))
        self.updateConfig("TIMING", "endyear", QtCore.QDate.year(enddate))
        self.updateConfig("TIMING", "endmonth", QtCore.QDate.month(enddate))
        self.updateConfig("TIMING", "endday", QtCore.QDate.day(enddate))
        self.enddate = datetime.date(QtCore.QDate.year(enddate),QtCore.QDate.month(enddate),QtCore.QDate.day(enddate))
        self.startdate = datetime.date(QtCore.QDate.year(startdate),QtCore.QDate.month(startdate),QtCore.QDate.day(startdate))
        self.timeSteps = ((self.enddate-self.startdate).days + 1)
    
    # update crs    
    def changeCRS(self):
        self.crs = self.crsSpinBox.value()
        self.settings.setValue("sphyplugin/crs", self.crs)
    
    # update the config file        
    def updateConfig(self, module, par, value):
        self.currentConfig.set(module, par, str(value))
        self.updateSaveButtons(1)
        
    # Save as project
    def saveAsProject(self, ptype=False):
        if ptype:
            tempname = QtGui.QFileDialog.getSaveFileName(self, "Save "+ptype+" project as", self.sphyLocationPath, "*.cfg")
        else:
            tempname = QtGui.QFileDialog.getSaveFileName(self, "Save current project as", self.sphyLocationPath, "*.cfg")
        if tempname:
            self.currentConfigFileName = tempname
            self.saveProject()
    
    # Save the project
    def saveProject(self):
        with open(self.currentConfigFileName, 'wb') as f:
            self.currentConfig.write(f)
        
        if self.currentProject is False:
            temp = self.currentConfigFileName
            self.sphyLocationPath = temp.split(":")[0] + ":"
        
        self.settings.setValue("sphyplugin/currentConfig", self.currentConfigFileName)
        self.settings.setValue("sphyplugin/sphypath", self.sphyLocationPath.replace("\\","/"))
        self.settings.setValue("sphyplugin/pcrBinPath", self.pcrBinPath.replace("\\","/"))
        self.settings.setValue("sphyplugin/pythonExe", self.pythonExe.replace("\\","/"))
        
        # write the qgs project file
        qgsProjectFileName = ((self.currentConfigFileName).split(".cfg")[0]) + ".qgs"
        qgsProject = QgsProject.instance()
        qgsProject.setFileName(qgsProjectFileName)
        qgsProject.write()
        self.settings.setValue("sphyplugin/qgsProjectFileName", qgsProjectFileName.replace("\\","/"))
        
        # update tab, project settings, and gui
        self.currentProject = True
        self.tab.setEnabled(1)
        self.exitDate = True
        self.initGuiConfigMap()
        self.exitDate = False
        self.updateSaveButtons(0)

    
    # enable save buttons after gui has been modified
    def updateSaveButtons(self, flag):
        if self.currentProject:
            self.saveAsButton.setEnabled(flag)
            self.saveButton.setEnabled(flag)
            
