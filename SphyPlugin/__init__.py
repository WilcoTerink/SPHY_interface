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
 SphyPlugin
                                 A QGIS plugin
 Interface for the SPHY model
                             -------------------
        begin                : 2014-09-09
        copyright            : (C) 2014 by Wilco Terink
        email                : terinkw@gmail.com
        git sha              : $Format:%H$
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""

# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load SphyPlugin class from file SphyPlugin.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .sphy_plugin import SphyPlugin
    return SphyPlugin(iface)
