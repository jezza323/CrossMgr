
import wx
import os
import xlwt
import Utils
import Model
import math
from GetResults import GetResults, GetCategoryDetails
from ReadSignOnSheet import Fields, IgnoreFields
from FitSheetWrapper import FitSheetWrapper
import qrcode
import urllib
from reportlab.lib.pagesizes import letter, A4

#---------------------------------------------------------------------------

# Sort sequence by rider status.
statusSortSeq = Model.Rider.statusSortSeq

brandText = 'Powered by CrossMgr (sites.google.com/site/crossmgrsoftware)'

def ImageToPil( image ):
	"""Convert wx.Image to PIL Image."""
	w, h = image.GetSize()
	data = image.GetData()

	redImage = Image.new("L", (w, h))
	redImage.fromstring(data[0::3])
	greenImage = Image.new("L", (w, h))
	greenImage.fromstring(data[1::3])
	blueImage = Image.new("L", (w, h))
	blueImage.fromstring(data[2::3])

	if image.HasAlpha():
		alphaImage = Image.new("L", (w, h))
		alphaImage.fromstring(image.GetAlphaData())
		pil = Image.merge('RGBA', (redImage, greenImage, blueImage, alphaImage))
	else:
		pil = Image.merge('RGB', (redImage, greenImage, blueImage))
	return pil

class ExportGrid( object ):
	def __init__( self, title = '', colnames = [], data = [] ):
		self.title = title
		self.colnames = colnames
		self.data = data
		self.leftJustifyCols = set()
		self.infoColumns = set()
		self.iLapTimes = 0
	
	def _getFont( self, pixelSize = 28, bold = False ):
		return wx.FontFromPixelSize( (0,pixelSize), wx.FONTFAMILY_SWISS, wx.NORMAL,
									 wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL, False, 'Ariel' )
	
	def _setFontPDF( self, canvas, pointSize = 24, bold = False ):
		canvas.setFont( 'Helvetica' + (' Bold' if bold else ''), pointSize )
	
	def _getColSizeTuple( self, dc, font, col ):
		wSpace, hSpace, lh = dc.GetMultiLineTextExtent( '    ', font )
		extents = [ dc.GetMultiLineTextExtent(self.colnames[col], font) ]
		extents.extend( dc.GetMultiLineTextExtent(str(v), font) for v in self.data[col] )
		return max( e[0] for e in extents ), sum( e[1] for e in extents ) + hSpace/4
	
	def _getDataSizeTuple( self, dc, font ):
		wSpace, hSpace, lh = dc.GetMultiLineTextExtent( '    ', font )
		
		wMax, hMax = 0, 0
		
		# Sum the width of each column.
		for col, c in enumerate(self.colnames):
			w, h = self._getColSizeTuple( dc, font, col )
			wMax += w + wSpace
			hMax = max( hMax, h )
			
		if wMax > 0:
			wMax -= wSpace
		
		return wMax, hMax
	
	def _drawMultiLineText( self, dc, text, x, y ):
		if not text:
			return
		wText, hText, lineHeightText = dc.GetMultiLineTextExtent( text, dc.GetFont() )
		for line in text.split( '\n' ):
			dc.DrawText( line, x, y )
			y += lineHeightText

	def _getFontToFit( self, widthToFit, heightToFit, sizeFunc, isBold = False ):
		left = 1
		right = max(widthToFit, heightToFit)
		
		while right - left > 1:
			mid = (left + right) / 2.0
			font = self._getFont( mid, isBold )
			widthText, heightText = sizeFunc( font )
			if widthText <= widthToFit and heightText <= heightToFit:
				left = mid
			else:
				right = mid - 1
		
		return self._getFont( left, isBold )
			
	def _setFontToFitPDF( self, canvas, widthToFit, heightToFit, sizeFunc, isBold = False ):
		left = 1
		right = max(widthToFit, heightToFit)
		
		while right - left > 1:
			mid = (left + right) / 2.0
			font = self._setFontPDF( mid, isBold )
			widthText, heightText = sizeFunc( font )
			if widthText <= widthToFit and heightText <= heightToFit:
				left = mid
			else:
				right = mid - 1
		
		return self._getFont( left, isBold )
			
	def getHeaderBitmap( self ):
		''' Get the header bitmap if specified, or use a default. '''
		if Utils.getMainWin():
			graphicFName = Utils.getMainWin().getGraphicFName()
			extension = os.path.splitext( graphicFName )[1].lower()
			bitmapType = {
				'.gif': wx.BITMAP_TYPE_GIF,
				'.png': wx.BITMAP_TYPE_PNG,
				'.jpg': wx.BITMAP_TYPE_JPEG,
				'.jpeg':wx.BITMAP_TYPE_JPEG }.get( extension, wx.BITMAP_TYPE_PNG )
			bitmap = wx.Bitmap( graphicFName, bitmapType )
		else:
			bitmap = wx.Bitmap( os.path.join(Utils.getImageFolder(), 'CrossMgrHeader.png'), wx.BITMAP_TYPE_PNG )
		return bitmap
	
	def getQRCodeImage( self, url, graphicHeight ):
		''' Get a QRCode image for the results url. '''
		qrWidth = graphicHeight
		qr = qrcode.QRCode()
		qr.add_data( 'http://' + url )
		qr.make()
		border = 0
		img = wx.EmptyImage( qr.modules_count + border * 2, qr.modules_count + border * 2 )
		bm = img.ConvertToMonoBitmap( 0, 0, 0 )
		canvasQR = wx.Memorycanvas()
		canvasQR.SelectObject( bm )
		canvasQR.SetBrush( wx.WHITE_BRUSH )
		canvasQR.Clear()
		canvasQR.SetPen( wx.BLACK_PEN )
		for row in xrange(qr.modules_count):
			for col, v in enumerate(qr.modules[row]):
				if v:
					canvasQR.DrawPoint( border + col, border + row )
		canvasQR.SelectObject( wx.NullBitmap )
		img = bm.ConvertToImage()
		img.Rescale( qrWidth, qrWidth, wx.IMAGE_QUALITY_NORMAL )
		return img
	
	def drawToFitDC( self, dc ):
		# Get the dimentions of what we are printing on.
		(widthPix, heightPix) = dc.GetSizeTuple()
		
		# Get a reasonable border.
		borderPix = max(widthPix, heightPix) / 20
		
		widthFieldPix = widthPix - borderPix * 2
		heightFieldPix = heightPix - borderPix * 2
		
		xPix = borderPix
		yPix = borderPix
		
		# Draw the graphic.
		bitmap = self.getHeaderBitmap()
		bmWidth, bmHeight = bitmap.GetWidth(), bitmap.GetHeight()
		graphicHeight = heightPix * 0.15
		graphicWidth = float(bmWidth) / float(bmHeight) * graphicHeight
		graphicBorder = int(graphicWidth * 0.15)

		# Rescale the graphic to the correct size.
		# We cannot use a GraphicContext because it does not support a PrintDC.
		image = bitmap.ConvertToImage()
		image.Rescale( graphicWidth, graphicHeight, wx.IMAGE_QUALITY_HIGH )
		if dc.GetDepth() == 8:
			image = image.ConvertToGreyscale()
		bitmap = image.ConvertToBitmap( dc.GetDepth() )
		dc.DrawBitmap( bitmap, xPix, yPix )
		image, bitmap = None, None
		
		# Get the race URL (if defined).
		with Model.LockRace() as race:
			url = getattr( race, 'urlFull', None )
		if url and url.startswith( 'http://' ):
			url = urllib.quote( url[7:] )
			
		qrWidth = 0
		if url:
			img = getQRCodeImage( url, graphicHeight ):
			img = img.ConvertToGreyscale()
			bm = img.ConvertToBitmap( dc.GetDepth() )
			dc.DrawBitmap( bm, widthPix - borderPix - qrWidth, borderPix )
			qrWidth += graphicBorder
		
		# Draw the title.
		font = self._getFontToFit( widthFieldPix - graphicWidth - graphicBorder - qrWidth, graphicHeight,
									lambda font: dc.GetMultiLineTextExtent(self.title, font)[:-1], True )
		dc.SetFont( font )
		self._drawMultiLineText( dc, self.title, xPix + graphicWidth + graphicBorder, yPix )
		# wText, hText, lineHeightText = dc.GetMultiLineTextExtent( self.title, font )
		# yPix += hText + lineHeightText/4
		yPix += graphicHeight + graphicBorder
		
		heightFieldPix = heightPix - yPix - borderPix
		
		# Draw the table.
		font = self._getFontToFit( widthFieldPix, heightFieldPix, lambda font: self._getDataSizeTuple(dc, font) )
		dc.SetFont( font )
		wSpace, hSpace, textHeight = dc.GetMultiLineTextExtent( '    ', font )
		
		yPixTop = yPix
		yPixMax = yPix
		for col, c in enumerate(self.colnames):
			isSpeed = (c == 'Speed')
			if isSpeed and self.data[col]:
				c = self.colnames[col] = self.data[col][0].split()[1]
		
			colWidth = self._getColSizeTuple( dc, font, col )[0]
			yPix = yPixTop
			w, h, lh = dc.GetMultiLineTextExtent( c, font )
			if col in self.leftJustifyCols:
				self._drawMultiLineText( dc, str(c), xPix, yPix )					# left justify
			else:
				self._drawMultiLineText( dc, str(c), xPix + colWidth - w, yPix )	# right justify
			yPix += h + hSpace/4
			if col == 0:
				yLine = yPix - hSpace/8
				for r in xrange(max(len(cData) for cData in self.data) + 1):
					dc.DrawLine( borderPix, yLine + r * textHeight, widthPix - borderPix, yLine + r * textHeight )
					
			for v in self.data[col]:
				vStr = str(v)
				if vStr:
					if isSpeed:
						vStr = vStr.split()[0]
					w, h, lh = dc.GetMultiLineTextExtent( vStr, font )
					if col in self.leftJustifyCols:
						self._drawMultiLineText( dc, vStr, xPix, yPix )					# left justify
					else:
						self._drawMultiLineText( dc, vStr, xPix + colWidth - w, yPix )	# right justify
				yPix += textHeight
			yPixMax = max(yPixMax, yPix)
			xPix += colWidth + wSpace
			
			if isSpeed:
				self.colnames[col] = 'Speed'
				
		if url:
			yPix = yPixMax + textHeight
			w, h, lh = dc.GetMultiLineTextExtent( url, font )
			self._drawMultiLineText( dc, url, widthPix - borderPix - w, yPix )
			
		# Put CrossMgr branding at the bottom of the page.
		font = self._getFont( borderPix // 5, False )
		dc.SetFont( font )
		w, h, lh = dc.GetMultiLineTextExtent( brandText, font )
		self._drawMultiLineText( dc, brandText, borderPix, heightPix - borderPix + h )
	
	def drawToFitPDF( self, canvas, pageSize = letter, blackAndWhite = True ):
		# Get the dimensions of what we are printing on.
		widthPix, heightPix = pageSize
		# Transform to landscape.
		canvas.translate( 0, widthPix )
		canvas.rotate( 90 )
		widthPix, heightPix = heightPix, widthPix
	
		# Get a reasonable border.
		borderPix = max(widthPix, heightPix) / 20
		
		widthFieldPix = widthPix - borderPix * 2
		heightFieldPix = heightPix - borderPix * 2
		
		xPix = borderPix
		yPix = heightPix - borderPix
		
		# Draw the graphic.
		bitmap = self.getHeaderBitmap()
		bmWidth, bmHeight = bitmap.GetWidth(), bitmap.GetHeight()
		graphicHeight = heightPix * 0.15
		graphicWidth = float(bmWidth) / float(bmHeight) * graphicHeight
		graphicBorder = int(graphicWidth * 0.15)

		# Rescale the graphic to the correct size.
		image = bitmap.ConvertToImage()
		image.Rescale( graphicWidth, graphicHeight, wx.IMAGE_QUALITY_HIGH )
		if blackAndWhite:
			image = image.ConvertToGreyscale()
		pil = ImageToPil( image )
		canvas.DrawImage( pil, xPix, yPix - graphicHeight )
		image, bitmap, pil = None, None, None
		
		# Get the race URL (if defined).
		with Model.LockRace() as race:
			url = getattr( race, 'urlFull', None )
		if url and url.startswith( 'http://' ):
			url = urllib.quote( url[7:] )
			
		qrWidth = 0
		if url:
			img = self.getQRCodeImage(url, graphicHeight)
			img = img.ConvertToGreyscale()
			pil = ImageToPil( img )
			qrWidth = graphicHeight
			canvas.DrawBitmap( bm, widthPix - borderPix - graphicHeight, yPix - qrWidth )
			qrWidth += graphicBorder
			img, pil = None, None
		
		# Draw the title.
		font = self._getFontToFit( widthFieldPix - graphicWidth - graphicBorder - qrWidth, graphicHeight,
									lambda font: canvas.GetMultiLineTextExtent(self.title, font)[:-1], True )
		canvas.SetFont( font )
		self._drawMultiLineText( canvas, self.title, xPix + graphicWidth + graphicBorder, yPix )
		# wText, hText, lineHeightText = canvas.GetMultiLineTextExtent( self.title, font )
		# yPix += hText + lineHeightText/4
		yPix += graphicHeight + graphicBorder
		
		heightFieldPix = heightPix - yPix - borderPix
		
		# Draw the table.
		font = self._getFontToFit( widthFieldPix, heightFieldPix, lambda font: self._getDataSizeTuple(canvas, font) )
		canvas.SetFont( font )
		wSpace, hSpace, textHeight = canvas.GetMultiLineTextExtent( '    ', font )
		
		yPixTop = yPix
		yPixMax = yPix
		for col, c in enumerate(self.colnames):
			isSpeed = (c == 'Speed')
			if isSpeed and self.data[col]:
				c = self.colnames[col] = self.data[col][0].split()[1]
		
			colWidth = self._getColSizeTuple( canvas, font, col )[0]
			yPix = yPixTop
			w, h, lh = canvas.GetMultiLineTextExtent( c, font )
			if col in self.leftJustifyCols:
				self._drawMultiLineText( canvas, str(c), xPix, yPix )					# left justify
			else:
				self._drawMultiLineText( canvas, str(c), xPix + colWidth - w, yPix )	# right justify
			yPix += h + hSpace/4
			if col == 0:
				yLine = yPix - hSpace/8
				for r in xrange(max(len(cData) for cData in self.data) + 1):
					canvas.DrawLine( borderPix, yLine + r * textHeight, widthPix - borderPix, yLine + r * textHeight )
					
			for v in self.data[col]:
				vStr = str(v)
				if vStr:
					if isSpeed:
						vStr = vStr.split()[0]
					w, h, lh = canvas.GetMultiLineTextExtent( vStr, font )
					if col in self.leftJustifyCols:
						self._drawMultiLineText( canvas, vStr, xPix, yPix )					# left justify
					else:
						self._drawMultiLineText( canvas, vStr, xPix + colWidth - w, yPix )	# right justify
				yPix += textHeight
			yPixMax = max(yPixMax, yPix)
			xPix += colWidth + wSpace
			
			if isSpeed:
				self.colnames[col] = 'Speed'
				
		if url:
			yPix = yPixMax + textHeight
			w, h, lh = canvas.GetMultiLineTextExtent( url, font )
			self._drawMultiLineText( canvas, url, widthPix - borderPix - w, yPix )
			
		# Put CrossMgr branding at the bottom of the page.
		font = self._getFont( borderPix // 5, False )
		canvas.SetFont( font )
		w, h, lh = canvas.GetMultiLineTextExtent( brandText, font )
		self._drawMultiLineText( canvas, brandText, borderPix, heightPix - borderPix + h )
		
	def toExcelSheet( self, sheet ):
		''' Write the contents of the grid to an xlwt excel sheet. '''
		titleStyle = xlwt.XFStyle()
		titleStyle.font.bold = True
		titleStyle.font.height += titleStyle.font.height / 2

		rowTop = 0
		if self.title:
			for line in self.title.split('\n'):
				sheet.write(rowTop, 0, line, titleStyle)
				rowTop += 1
			rowTop += 1
		
		sheetFit = FitSheetWrapper( sheet )
		
		# Write the colnames and data.
		rowMax = 0
		for col, c in enumerate(self.colnames):
			isSpeed = (c == 'Speed')
			if isSpeed and self.data[col]:
				c = self.colnames[col] = self.data[col][0].split()[1]

			headerStyle = xlwt.XFStyle()
			headerStyle.borders.bottom = xlwt.Borders.MEDIUM
			headerStyle.font.bold = True
			headerStyle.alignment.horz = xlwt.Alignment.HORZ_LEFT if col in self.leftJustifyCols \
																	else xlwt.Alignment.HORZ_RIGHT
			headerStyle.alignment.wrap = xlwt.Alignment.WRAP_AT_RIGHT
			
			style = xlwt.XFStyle()
			style.alignment.horz = xlwt.Alignment.HORZ_LEFT if col in self.leftJustifyCols \
																	else xlwt.Alignment.HORZ_RIGHT
			
			sheetFit.write( rowTop, col, c, headerStyle, bold=True )
			for row, v in enumerate(self.data[col]):
				if isSpeed and v:
					v = str(v).split()[0]
				rowCur = rowTop + 1 + row
				if rowCur > rowMax:
					rowMax = rowCur
				sheetFit.write( rowCur, col, v, style )
			
			if isSpeed:
				self.colnames[col] = 'Speed'
				
		# Add branding at the bottom of the sheet.
		style = xlwt.XFStyle()
		style.alignment.horz = xlwt.Alignment.HORZ_LEFT
		sheet.write( rowMax + 2, 0, brandText, style )
	
	def _setRC( self, row, col, value ):
		if self.data:
			maxRow = max( len(c) for c in self.data )
		else:
			maxRow = 0
		while col >= len(self.data):
			self.data.append( [''] * maxRow )
		if row >= maxRow:
			growSize = row + 1 - maxRow
			for c in self.data:
				c.extend( [''] * growSize )
		
		self.data[col][row] = value
	
	def setResultsOneList( self, category = None, getExternalData = True, showLapsFrequency = None ):
		''' Format the results into columns. '''
		self.data = []
		self.colnames = []

		results = GetResults( category, getExternalData )
		if not results:
			return
		catDetails = GetCategoryDetails()
		cd = catDetails[category.fullname] if category else None
		
		leader = results[0]
		hasSpeeds = bool( getattr(leader, 'lapSpeeds', None) or getattr(leader, 'raceSpeeds', None) )
		
		if showLapsFrequency is None:
			# Compute a reasonable number of laps to show (max around 12).
			# Get the maximum laps in the data.
			maxLaps = 0
			for r in results:
				try:
					maxLaps = max(maxLaps, len(r.lapTimes))
				except:
					pass
			showLapsFrequency = max( 1, int(math.ceil(maxLaps / 12)) )
		
		with Model.LockRace() as race:
			catStr = 'All' if not category else category.fullname
			if cd and cd.get('raceDistance', None):
				catStr += ', %.2f %s, ' % (cd['raceDistance'], cd['distanceUnit'])
				if cd.get('lapDistance', None) and cd.get('laps', 0) > 1:
					if cd.get('firstLapDistance', None) and cd['firstLapDistance'] != cd['lapDistance']:
						catStr += '1st lap %.2f %s, %d more laps of %.2f %s, ' % (
									cd['firstLapDistance'], cd['distanceUnit'],
									cd['laps'] - 1,
									cd['lapDistance'], cd['distanceUnit']
								)
					else:
						catStr += '%d laps of %.2f %s, ' % (cd['laps'], cd['lapDistance'], cd['distanceUnit']);
				catStr += 'winner: %s at %s' % (Utils.formatTime(leader.lastTime - cd['startOffset']), leader.speed);
		
			self.title = '\n'.join( [race.name, Utils.formatDate(race.date), catStr] )
			isTimeTrial = getattr( race, 'isTimeTrial', False )

		startOffset = category.getStartOffsetSecs() if category else 0.0
		
		infoFields = ['LastName', 'FirstName', 'Team', 'Category', 'License'] if getExternalData else []
		infoFieldsPresent = set( infoFields ) & set( dir(leader) )
		infoFields = [f for f in infoFields if f in infoFieldsPresent]
		
		self.colnames = ['Pos', 'Bib'] + infoFields + (['Start','Finish'] if isTimeTrial else []) + ['Time', 'Gap']
		if hasSpeeds:
			self.colnames += ['Speed']
		self.colnames = [name[:-4] + ' Name' if name.endswith('Name') else name for name in self.colnames]
		self.iLapTimes = len(self.colnames)
		lapsMax = len(leader.lapTimes) if leader.lapTimes else 0
		if leader.lapTimes:
			self.colnames.extend( ['Lap %d' % lap for lap in xrange(1, lapsMax+1) \
					if lap % showLapsFrequency == 0 or lap == 1 or lap == lapsMax] )
		
		highPrecision = Utils.highPrecisionTimes()
		data = [ [] for i in xrange(len(self.colnames)) ]
		colsMax = len(self.colnames)
		rrFields = ['pos', 'num'] + infoFields + (['startTime','finishTime'] if isTimeTrial else []) + ['lastTime', 'gap']
		if hasSpeeds:
			rrFields += ['speed']
		for col, f in enumerate( rrFields ):
			for row, r in enumerate(results):
				if f == 'lastTime':
					lastTime = getattr( r, f, 0.0 )
					if lastTime <= 0.0:
						data[col].append( '' )
					else:
						if not isTimeTrial:
							lastTime = max( 0.0, lastTime - startOffset )
						data[col].append( Utils.formatTimeCompressed(lastTime, highPrecision) )
				elif f in ['startTime', 'finishTime']:
					sfTime = getattr( r, f, None )
					if sfTime is not None:
						data[col].append( Utils.formatTimeCompressed(sfTime, highPrecision) )
					else:
						data[col].append( '' )
				else:
					data[col].append( getattr(r, f, '') )
		
		for row, r in enumerate(results):
			iCol = self.iLapTimes
			for i, t in enumerate(r.lapTimes):
				lap = i + 1
				if lap % showLapsFrequency == 0 or lap == 1 or lap == lapsMax:
					data[iCol].append( Utils.formatTimeCompressed(t, highPrecision) )
					iCol += 1
					if iCol >= colsMax:
						break
			# Pad out the rest of the columns.
			for i in xrange(len(r.lapTimes), lapsMax):
				lap = i + 1
				if lap % showLapsFrequency == 0 or lap == 1 or lap == lapsMax:
					data[iCol].append( '' )
					iCol += 1
		
		self.data = data
		self.infoColumns     = set( xrange(2, 2+len(infoFields)) ) if infoFields else set()
		self.leftJustifyCols = set( xrange(2, 2+len(infoFields)) ) if infoFields else set()
		
			
if __name__ == '__main__':
	pass
