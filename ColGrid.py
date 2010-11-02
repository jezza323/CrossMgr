
import  wx
import  wx.grid as  Grid
import  copy

#---------------------------------------------------------------------------

class ColTable(Grid.PyGridTableBase):
	"""
	A custom wx.Grid Table using user supplied data
	"""
	def __init__(self, data = None, colnames = None, textColour = None, backgroundColour = None ):
		"""
		data is a list, indexed by col, of a list of row values
		"""
		self.attrs = {}	# Set of unique cell attributes.
		self.rightAlign = False
		
		# The base class must be initialized *first*
		Grid.PyGridTableBase.__init__(self)
		self.data = []
		self.colnames = []
		self.textColour = {}
		self.backgroundColour = {}
		self.Set( data, colnames, textColour, backgroundColour )		

	def __del__( self ):
		# Make sure we free up our allocated attribues.
		#for a in attrs:
		#	a.DecRef()
		pass
		
	def SetRightAlign( self, ra = True ):
		self.rightAlign = ra
	
	def _adjustDimension( self, grid, current, new, isCol ):
		if grid is None:
			return
		
		if isCol:
			delmsg, addmsg = Grid.GRIDTABLE_NOTIFY_COLS_DELETED, Grid.GRIDTABLE_NOTIFY_COLS_APPENDED
		else:
			delmsg, addmsg = Grid.GRIDTABLE_NOTIFY_ROWS_DELETED, Grid.GRIDTABLE_NOTIFY_ROWS_APPENDED
			
		if new < current:
			msg = Grid.GridTableMessage(self,delmsg,new,current-new)
			grid.ProcessTableMessage(msg)
		elif new > current:
			msg = Grid.GridTableMessage(self,addmsg,new-current)
			grid.ProcessTableMessage(msg)		
	
	def Set( self, data = None, colnames = None, textColour = None, backgroundColour = None, grid = None ):
		if colnames is not None:
			self._adjustDimension( grid, len(self.colnames), len(colnames), True )
			self.colnames = list(colnames)
			
		if data is not None:
			current = max( len(c) for c in self.data )	if self.data	else 0
			new     = max( len(c) for c in data )		if data 		else 0
			self._adjustDimension( grid, current, new, False )
			self.data = copy.copy(data)
			
		if textColour is not None:
			self.textColour = dict(textColour)
			
		if backgroundColour is not None:
			self.backgroundColour = dict(backgroundColour)
	
	def GetData( self ):
		return self.data
	
	def isEmpty( self ):
		return True if not self.data else False
	
	def GetNumberCols(self):
		try:
			return len(self.colnames)
		except TypeError:
			return 0

	def GetNumberRows(self):
		try:
			return max( len(c) for c in self.data )
		except (TypeError, ValueError):
			return 0

	def GetColLabelValue(self, col):
		try:
			return self.colnames[col]
		except (TypeError, IndexError):
			return ''

	def GetRowLabelValue(self, row):
		return str(row+1)

	def IsEmptyCell( self, row, col ):
		try:
			v = self.data[col][row]
			return v is None or v == ''
		except (TypeError, IndexError):
			return True
		
	def GetRawValue(self, row, col):
		return '' if self.IsEmptyCell(row, col) else self.data[col][row]

	def GetValue(self, row, col):
		return str(self.GetRawValue(row, col))

	def SetValue(self, row, col, value):
		# Nothing to do - everthings is read-only.
		pass

	def GetAttr(self, row, col, someExtraParameter ):
		rc = (row, col)
		key = (self.textColour.get(rc, None), self.backgroundColour.get(rc, None))
		try:
			attr = self.attrs[key]
		except KeyError:
			# Create an attribute for the cache.
			attr = Grid.GridCellAttr()
			attr.SetReadOnly( 1 )			# All cells read-only.
			if rc in self.textColour:
				attr.SetTextColour( self.textColour[rc] )
			if rc in self.backgroundColour:
				attr.SetBackgroundColour( self.backgroundColour[rc] )
			self.attrs[key] = attr
			
		if self.rightAlign:
			attr.SetAlignment( hAlign = wx.ALIGN_RIGHT, vAlign = wx.ALIGN_CENTRE )
		# We must increment the ref count so the attr does not get GC'd after it is referenced.
		attr.IncRef()
		return attr

	def SetAttr( self, row, col, attr ): pass
	def SetRowAttr( self, row, attr ): pass
	def SetColAttr( self, col, attr ) : pass
	def UpdateAttrRows( self, pos, numRows ) : pass
	def UpdateAttrCols( self, pos, numCols ) : pass
	
	def ResetView(self, grid):
		"""
		(Grid) -> Reset the grid view.   Call this to redraw the grid.
		"""

		for col in xrange(self.GetNumberCols()):
			attr = Grid.GridCellAttr()
			attr.SetAlignment( hAlign = wx.ALIGN_RIGHT if self.rightAlign else wx.ALIGN_CENTRE, vAlign = wx.ALIGN_CENTRE )
			self.SetColAttr( col, attr )

		grid.AdjustScrollbars()
		grid.ForceRefresh()

	def UpdateValues(self, grid):
		"""Update all displayed values"""
		# This sends an event to the grid table to update all of the values
		msg = Grid.GridTableMessage(self, Grid.GRIDTABLE_REQUEST_VIEW_GET_VALUES)
		grid.ProcessTableMessage(msg)

# --------------------------------------------------------------------
# Sample Grid

class ColGrid(Grid.Grid):
	def __init__(self, parent, data = None, colnames = None, textColour = None, backgroundColour = None ):
		"""parent, data, colnames, plugins=None
		Initialize a grid using the data defined in data and colnames
		"""

		# The base class must be initialized *first*
		Grid.Grid.__init__(self, parent, -1)
		self._table = ColTable(data, colnames, textColour, backgroundColour)
		self.SetTable(self._table)
		
		self.zoomLevel = 1.0

	def Reset( self ):
		"""reset the view based on the data in the table.  Call this when rows are added or destroyed"""
		self._table.ResetView(self)

	def Set( self, data = None, colnames = None, textColour = None, backgroundColour = None ):
		self._table.Set( data, colnames, textColour, backgroundColour, self )
	
	def GetData( self ):
		return self._table.GetData()
	
	def Zoom( self, zoomIn = True ):
		factor = 2 if zoomIn else 0.5
		if not 1.0/4.0 <= self.zoomLevel * factor <= 4.0:
			return
		self.zoomLevel *= factor
		
		font = self.GetDefaultCellFont()
		font.SetPointSize( int(font.GetPointSize() * factor) )
		self.SetDefaultCellFont( font )
		
		font = self.GetLabelFont()
		font.SetPointSize( int(font.GetPointSize() * factor) )
		self.SetLabelFont( font )
		
		self.SetColLabelSize( int(self.GetColLabelSize() * factor) )
		self.AutoSize()
		self.Reset()
	
	def SetRightAlign( self, ra = True ):
		self._table.SetRightAlign( ra )
		self.Reset()
	
	def clearGrid( self ):
		self.Set( data = [], colnames = [], textColour = {}, backgroundColour = {} )
		self.Reset()
