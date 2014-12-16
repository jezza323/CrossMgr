import xlwt
import math
import Model
import Utils
import datetime
from GetResults import GetResults, GetCategoryDetails
from FitSheetWrapper import FitSheetWrapper
from ReadSignOnSheet import SyncExcelLink

USACFields = (
	'Race Date',
	'Race Gender',
	'Race Discipline',
	'Race Category',
	'Rider Bib #',
	'Rider Last Name',
	'Rider First Name',
	'Rider Team',
	'Rider License #',
	'Rider Place',
	'Rider Time',
)
lenUSACFields = len(USACFields)

def formatTime( secs, highPrecision = False ):
	if secs is None:
		secs = 0
	if secs < 0:
		sign = '-'
		secs = -secs
	else:
		sign = ''
	f, ss = math.modf(secs)
	secs = int(ss)
	hours = int(secs // (60*60))
	minutes = int( (secs // 60) % 60 )
	secs = secs % 60
	if highPrecision:
		secStr = '{:05.2f}'.format( secs + f )
	else:
		secStr = '{:02d}'.format( secs )
	return "{}{}:{:02d}:{}".format(sign, hours, minutes, secStr)

def toInt( n ):
	try:
		return int(n.split()[0])
	except:
		return n

	
def USACExport( sheet ):
	race = Model.race
	if not race:
		return
		
	SyncExcelLink( race )
	
	raceDiscipline = getattr( race, 'discipline', 'Cyclo-cross' )
	
	# Correct for USAC's picky naming.
	if 'cyclo' in raceDiscipline.lower():
		raceDiscipline = 'Cyclo-cross'
	elif 'road' in raceDiscipline.lower():
		raceDiscipline = 'Road Race'

	sheetFit = FitSheetWrapper( sheet )
	
	titleStyle = xlwt.XFStyle()
	titleStyle.font.bold = True
	
	leftAlignStyle = xlwt.XFStyle()
	
	rightAlignStyle = xlwt.XFStyle()
	rightAlignStyle.alignment.horz = xlwt.Alignment.HORZ_RIGHT
	
	catDetails = dict( (cd['name'], cd) for cd in GetCategoryDetails() )
	hasDistance = None
	
	maxLaps = 0
	
	publishCategories = race.getCategories( startWaveOnly = False, uploadOnly = True )
	for cat in publishCategories:
		results = GetResults( cat, True )
		if not results:
			continue
		cd = catDetails[cat.fullname]
		if cd.get('raceDistance', None):
			hasDistance = True
		maxLaps = max( maxLaps, max(rr.laps for rr in results) )
	
	if maxLaps == 1 or maxLaps > 99:
		maxLaps = 0
	
	lapTimeStartCol = (2 if hasDistance else 0) + lenUSACFields
	
	year, month, day = race.date.split( '-' )
	raceDate = datetime.date( year = int(year), month = int(month), day = int(day) ).strftime( '%m/%d/%Y' )
	
	row = 0
	for cat in publishCategories:
		results = GetResults( cat, True )
		if not results:
			continue
		
		raceGender = getattr(cat, 'gender', 'Open')
		if raceGender == 'Open':
			raceGender = 'All'
		
		cd = catDetails[cat.fullname]
		raceDistance = cd.get('raceDistance', '')
		raceDistanceType = cd.get('distanceUnit', '')
		
		for rr in results:
			if row == 0:
				for col, field in enumerate(USACFields):
					sheetFit.write( row, col, field, titleStyle, bold=True )
				if hasDistance:
					sheetFit.write( row, lenUSACFields  , 'Race Distance', titleStyle, bold=True )
					sheetFit.write( row, lenUSACFields+1, 'Race Distance Type', titleStyle, bold=True )
				for i in xrange(maxLaps):
					sheetFit.write( row, lapTimeStartCol + i, 'Rider Lap {}'.format(i + 1), titleStyle, bold=True )
				row += 1
			
			try:
				finishTime = formatTime(rr.lastTime - rr.raceTimes[0]) if rr.status == Model.Rider.Finisher else ''
			except Exception as e:
				finishTime = ''

			for col, field in enumerate(USACFields):
				{
					'Race Date':		lambda : sheet.write( row, col, raceDate, rightAlignStyle ),
					'Race Gender':		lambda : sheetFit.write( row, col, raceGender, leftAlignStyle ),
					'Race Discipline':	lambda : sheetFit.write( row, col, raceDiscipline, leftAlignStyle ),
					'Race Category':	lambda : sheetFit.write( row, col, cat.name, leftAlignStyle ),
					'Rider Bib #':		lambda : sheetFit.write( row, col, rr.num, rightAlignStyle ),
					'Rider Last Name':	lambda : sheetFit.write( row, col, getattr(rr, 'LastName', ''), leftAlignStyle ),
					'Rider First Name':	lambda : sheetFit.write( row, col, getattr(rr, 'FirstName', ''), leftAlignStyle ),
					'Rider Team':		lambda : sheetFit.write( row, col, getattr(rr, 'Team', ''), leftAlignStyle ),
					'Rider License #':	lambda : sheetFit.write( row, col, getattr(rr, 'License', ''), leftAlignStyle ),
					'Rider Place':		lambda : sheetFit.write( row, col, 'DNP' if rr.pos in {'NP', 'OTL', 'PUL'} else toInt(rr.pos), rightAlignStyle ),
					'Rider Time':		lambda : sheetFit.write( row, col, finishTime, rightAlignStyle ),
				}[field]()
			
			if hasDistance:
				sheetFit.write( row, lenUSACFields  , raceDistance, rightAlignStyle )
				sheetFit.write( row, lenUSACFields+1, raceDistanceType, rightAlignStyle )

			if maxLaps:
				for i, lapTime in enumerate(rr.lapTimes):
					sheetFit.write( row, lapTimeStartCol + i, Utils.formatTime(lapTime), rightAlignStyle )
			row += 1
