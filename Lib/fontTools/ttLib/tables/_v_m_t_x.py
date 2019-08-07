from __future__ import print_function, division, absolute_import
from fontTools import ttLib

superclass = ttLib.getTableClass("hmtx")

class table__v_m_t_x(superclass):

	headerTag = 'vhea'
	advanceName = 'height'
	sideBearingName = 'tsb'
	numberOfMetricsName = 'numberOfVMetrics'
