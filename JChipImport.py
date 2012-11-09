import Model
import Utils
import JChip
from JChipSetup import GetTagNums
from Utils		import logCall
from Undo		import undo
from HighPrecisionTimeEdit import HighPrecisionTimeEdit
import wx
import wx.lib.intctrl
import wx.lib.masked			as masked
import wx.lib.mixins.listctrl 	as  listmix
import wx.lib.rcsizer			as rcs
import socket
import sys
import os
import datetime

def DoJchipImport( fname, startTime = None, clearExistingData = True, timeAdjustment = 0.0 ):
	# If startTime is None, the first time will be taken as the start time.
	# All first time's for each rider will then be ignored.
	
	errors = []
	raceStart = None
	
	with open(fname) as f, Model.LockRace() as race:
		year, month, day = [int(n) for n in race.date.split('-')]
		raceDate = datetime.date( year=year, month=month, day=day )
		JChip.dateToday = raceDate
		if startTime:
			raceStart = datetime.datetime.combine( raceDate, startTime )
			race.resetStartClockOnFirstTag = False
		else:
			race.resetStartClockOnFirstTag = True
		
		tagNums = GetTagNums( True )
		race.missingTags = set()
		
		tFirst, tLast = None, None
		lineNo = 0
		riderRaceTimes = {}
		for line in f:
			lineNo += 1
			
			if line.startswith('#'):
				continue
			
			try:
				fields = line.split()
				tag = fields[0][1:]
				tStr = fields[1]
			except IndexError:
				errors.append( 'line %d: unrecognized input' % lineNo )
				continue
			
			try:
				t = JChip.parseTime(tStr) + timeAdjustment
			except (IndexError, ValueError):
				errors.append( 'line %d: invalid time' % lineNo )
				continue
				
			if raceStart and t < raceStart:
				errors.append( 'line %d: time before race start (%s)' % (lineNo, tStr) )
				continue
			
				
			if not tFirst:
				tFirst = t
			tLast = t
			try:
				num = tagNums[tag]
				riderRaceTimes.setdefault( num, [] ).append( t )
			except KeyError:
				if tag not in race.missingTags:
					errors.append( 'line %d: tag %s missing from Excel sheet' % (lineNo, tag) )
					race.missingTags.add( tag )
				continue

		#------------------------------------------------------------------------------
		# Populate the race with the times.
		if not riderRaceTimes:
			errors.insert( 0, 'No matching tags found in Excel link.  Import aborted.' )
			return errors
		
		# Put all the rider times into the race.
		if clearExistingData:
			race.clearAllRiderTimes()
			
		if not raceStart:
			raceStart = tFirst
			
		race.startTime = raceStart
		
		for num, lapTimes in riderRaceTimes.iteritems():
			for t in lapTimes:
				raceTime = (t - raceStart).total_seconds()
				if not race.hasTime(num, raceTime):
					race.addTime( num, raceTime )
			
		if tLast:
			race.finishTime = tLast + datetime.timedelta( seconds = 0.0001 )
			
		# Figure out the race minutes from the recorded laps.
		if riderRaceTimes:
			lapNumMax = max( len(ts) for ts in riderRaceTimes.itervalues() )
			if lapNumMax > 0:
				tElapsed = min( ts[-1] for ts in riderRaceTimes.itervalues() if len(ts) == lapNumMax )
				raceMinutes = int((tElapsed - raceStart).total_seconds() / 60.0) + 1
				race.minutes = raceMinutes
		
	return errors

#------------------------------------------------------------------------------------------------
class JChipImportDialog( wx.Dialog ):
	def __init__( self, parent, id = wx.ID_ANY ):
		wx.Dialog.__init__( self, parent, id, "JChip Import",
						style=wx.DEFAULT_DIALOG_STYLE|wx.THICK_FRAME|wx.TAB_TRAVERSAL )
		
		todoList = [
			'Import JChip Data File',
			'',
			'You must first "New" a race and fill in the details.',
			'You must also configure a "Tag" field in your Sign-On Excel Sheet and link it to the race.',
			'This is required so CrossMgr can link the tags in the JChip file back to rider numbers and info.',
			'',
			'Race Data:',
			'If the first chip read is NOT the start of the race, you will need to enter the start time manually.',
			'Otherwise the import will use the first chip read as the race start.',
			'',
			'TimeTrial Data:',
			"The first chip read for each rider will be interpreted as the rider's start time.",
			'',
			'Warning: Importing from JChip will replace all the data in this race.',
			'Proceed with caution.',
		]
		intro = '\n'.join(todoList)
		
		gs = wx.FlexGridSizer( rows=5, cols=3, vgap=10, hgap=5 )
		gs.Add( wx.StaticText(self, wx.ID_ANY, 'JChip Data File:'), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT )
		self.jchipDataFile = wx.TextCtrl( self, -1, '', size=(450,-1) )
		defaultPath = Utils.getFileName()
		if not defaultPath:
			defaultPath = Utils.getDocumentsDir()
		else:
			defaultPath = os.path.join( os.path.split(defaultPath)[0], '' )
		self.jchipDataFile.SetValue( defaultPath )
		gs.Add( self.jchipDataFile, 1, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT|wx.GROW)

		btn = wx.Button( self, wx.ID_ANY, label='Browse...' )
		btn.Bind( wx.EVT_BUTTON, self.onBrowseJChipDataFile )
		gs.Add( btn, 0, wx.ALIGN_CENTER_VERTICAL )
		
		gs.AddSpacer(1)
		self.dataType = wx.StaticText( self, wx.ID_ANY, "Data Is:" )
		gs.Add( self.dataType, 1, wx.ALIGN_LEFT )
		gs.AddSpacer(1)

		gs.Add( wx.StaticText(self, wx.ID_ANY, 'Data Policy:' ), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT )
		self.importPolicy = wx.Choice( self, wx.ID_ANY, choices = [
				'Clear All Existing Data Before Import',
				'Merge New Data with Existing'
			] )
		self.importPolicy.SetSelection( 0 )
		gs.Add( self.importPolicy, 1, wx.ALIGN_LEFT )
		gs.AddSpacer(1)
        
		gs.Add( wx.StaticText(self, wx.ID_ANY, 'Import Data Time Adjustment:' ), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT )
		self.timeAdjustment = HighPrecisionTimeEdit( self, wx.ID_ANY )
		self.behindAhead = wx.Choice( self, wx.ID_ANY, choices=['Behind', 'Ahead'] )
		if JChip.readerComputerTimeDiff:
			rtAdjust = JChip.readerComputerTimeDiff.total_seconds()
			if rtAdjust >= 0.0:
				self.behindAhead.SetSelection( 0 )
			else:
				self.behindAhead.SetSelection( 1 )
				rtAdjust *= -1.0
			self.timeAdjustment.SetSeconds( rtAdjust )
		else:
			self.behindAhead.SetSelection( 0 )
		hb = wx.BoxSizer()
		hb.Add( self.behindAhead, flag=wx.ALIGN_BOTTOM|wx.BOTTOM, border=4 )
		hb.Add( self.timeAdjustment, flag=wx.ALL, border=4 )
		gs.Add( hb, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT )
		gs.AddSpacer(1)
		
		self.manualStartTime = wx.CheckBox(self, wx.ID_ANY, 'Race Start Time (if NOT first recorded time):' )
		self.Bind( wx.EVT_CHECKBOX, self.onChangeManualStartTime, self.manualStartTime )
		gs.Add( self.manualStartTime, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT )
		self.raceStartTime = masked.TimeCtrl( self, wx.ID_ANY, fmt24hr=True, value="10:00:00" )
		self.raceStartTime.Enable( False )
		gs.Add( self.raceStartTime, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT)
		gs.AddSpacer(1)
		
		with Model.LockRace() as race:
			isTimeTrial = getattr(race, 'isTimeTrial', False) if race else False

		if isTimeTrial:
			self.manualStartTime.Enable( False )
			self.manualStartTime.Show( False )
			self.raceStartTime.Enable( False )
			self.raceStartTime.Show( False )
			self.dataType.SetLabel( 'Data will be imported for a Time Trial' )
		else:
			self.dataType.SetLabel( 'Data will be imported for a Race' )
			
		self.okBtn = wx.Button( self, wx.ID_OK, '&OK' )
		self.Bind( wx.EVT_BUTTON, self.onOK, self.okBtn )

		self.cancelBtn = wx.Button( self, wx.ID_CANCEL, '&Cancel' )
		self.Bind( wx.EVT_BUTTON, self.onCancel, self.cancelBtn )
		
		bs = wx.BoxSizer( wx.VERTICAL )
		
		border = 4
		bs.Add( wx.StaticText(self, -1, intro), 0, wx.EXPAND|wx.ALL, border )
		
		#-------------------------------------------------------------------
		bs.AddSpacer( border )
		
		bs.Add( gs, 0, wx.EXPAND | wx.ALL, border )
		
		buttonBox = wx.BoxSizer( wx.HORIZONTAL )
		buttonBox.AddStretchSpacer()
		buttonBox.Add( self.okBtn, flag = wx.RIGHT, border = border )
		self.okBtn.SetDefault()
		buttonBox.Add( self.cancelBtn )
		bs.Add( buttonBox, 0, wx.EXPAND | wx.ALL, border )
		
		self.SetSizerAndFit(bs)
		bs.Fit( self )
		
		self.CentreOnParent(wx.BOTH)
		self.SetFocus()

	def onChangeManualStartTime( self, event ):
		self.raceStartTime.Enable( event.IsChecked() )
		
	def onBrowseJChipDataFile( self, event ):
		defaultPath = self.jchipDataFile.GetValue()
		if not defaultPath:
			defaultPath = Utils.getFileName()
			if defaultPath:
				defaultPath = os.path.split(defaultPath)[0]
			else:
				defaultPath = Utils.getDocumentsDir()
			defaultFile = ''
		else:
			defaultPath, defaultFile = os.path.split(defaultPath)
			
		dlg = wx.FileDialog( self, "Choose a JChip file",
							style=wx.OPEN | wx.CHANGE_DIR,
							wildcard="JChip Data (*.txt)|*.txt",
							defaultDir=defaultPath if defaultPath else '',
							defaultFile=defaultFile if defaultFile else '',
							)
		if dlg.ShowModal() == wx.ID_OK:
			self.jchipDataFile.SetValue( dlg.GetPath() )
		dlg.Destroy()		
	
	def onOK( self, event ):
		fname = self.jchipDataFile.GetValue()
		try:
			with open(fname) as f:
				pass
		except IOError:
			Utils.MessageOK( self, 'Could not open JChip data file for import:\n\n"%s"' % fname,
									title = 'Cannot Open File', iconMask = wx.ICON_ERROR)
			return
			
		clearExistingData = (self.importPolicy.GetSelection() == 0)
		timeAdjustment = self.timeAdjustment.GetSeconds()
		if self.behindAhead.GetSelection() == 1:
			timeAdjustment *= -1
		
		# Get the start time.
		if not clearExistingData:
			if not Model.race or not Model.race.startTime:
				Utils.MessageOK( self, 'Cannot Merge into Unstarted Race.\n\n"Clear All Existing Data" is allowed.',
										title = 'Import Merge Failed', iconMask = wx.ICON_ERROR)
				return
			startTime = Model.race.startTime.time()
		else:
			if self.manualStartTime.IsChecked():
				startTime = datetime.time(*[int(x) for x in self.raceStartTime.GetValue().split(':')])
			else:
				startTime = None
			
		
		undo.pushState()
		errors = DoJchipImport(	fname, startTime,
								clearExistingData,
								datetime.timedelta(seconds = timeAdjustment) )
		
		if errors:
			# Copy the tags to the clipboard.
			clipboard = wx.Clipboard.Get()
			if not clipboard.IsOpened():
				clipboard.Open()
				clipboard.SetData( wx.TextDataObject('\n'.join(errors)) )
				clipboard.Close()
			
			if len(errors) > 10:
				errors = errors[:10]
				errors.append( '...' )
			tagStr = '\n'.join(errors)
			Utils.MessageOK( self,
							'JChip Import File contains errors:\n\n%s\n\nAll errors have been copied to the clipboard.' % tagStr,
							'JChip Import Warning',
							iconMask = wx.ICON_WARNING )
		else:
			Utils.MessageOK( self, 'JChip Import Successful', 'JChip Import Successful' )
		wx.CallAfter( Utils.refresh )
		self.EndModal( wx.ID_OK )
		
	def onCancel( self, event ):
		self.EndModal( wx.ID_CANCEL )
		
if __name__ == '__main__':
	app = wx.PySimpleApp()
	mainWin = wx.Frame(None,title="CrossMan", size=(600,400))
	Model.setRace( Model.Race() )
	mainWin.Show()
	dlg = JChipImportDialog( mainWin )
	dlg.ShowModal()
	dlg.Destroy()

